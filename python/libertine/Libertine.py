# Copyright 2015-2016 Canonical Ltd.
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranties of
# MERCHANTABILITY, SATISFACTORY QUALITY, or FITNESS FOR A PARTICULAR
# PURPOSE.  See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program.  If not, see <http://www.gnu.org/licenses/>.

from .AppDiscovery import AppLauncherCache
from gi.repository import Libertine
import abc
import contextlib
import libertine.utils
import os
import shutil

from . import utils
from libertine.ContainersConfig import ContainersConfig
from libertine.HostInfo import HostInfo


def _apt_args_for_verbosity_level():
    """
    Maps debug levels to APT command-line arguments.
    """
    if 'LIBERTINE_DEBUG' not in os.environ or os.environ['LIBERTINE_DEBUG'] == '0':
        return '--quiet=2'

    if os.environ['LIBERTINE_DEBUG'] == '1':
        return '--quiet=1 --assume-yes'

    return '--assume-yes --option APT::Status-Fd=1'


def _apt_command_prefix():
    return '/usr/bin/apt-get ' + _apt_args_for_verbosity_level() + \
           ' --option Apt::Cmd::Disable-Script-Warning=true --option Dpkg::Progress-Fancy=1' + \
           ' --option Apt::Color=1 '


def handle_runtime_error(error):
    utils.get_logger().error("%s" % error)
    return False


class NoContainer(object):
    """
    A containerless class used for launching apps with libertine-launch.
    """
    def connect(self):
        """
        A no-op function used by the Session class.
        """
        pass

    def disconnect(self):
        """
        A no-op function used by the Session class.
        """
        pass

    def start_application(self, app_exec_line, environ):
        import psutil

        app = psutil.Popen(app_exec_line, env=environ)
        return app

    def finish_application(self, app):
        app.wait()


class BaseContainer(metaclass=abc.ABCMeta):
    """
    An abstract base container to provide common functionality for all
    concrete container types.

    :param container_id: The machine-readable container name.
    """
    def __init__(self, container_id, containers_config=None):
        if containers_config is None:
            containers_config = ContainersConfig()

        self.container_type = 'unknown'
        self.container_id = container_id
        self.root_path = libertine.utils.get_libertine_container_rootfs_path(self.container_id)
        self.locale = containers_config.get_container_locale(container_id)
        self.language = self._get_language_from_locale()
        self.default_packages = ['matchbox-window-manager',
                                 'libnss-extrausers',
                                 'humanity-icon-theme',
                                 'maliit-inputcontext-gtk2',
                                 'maliit-inputcontext-gtk3',
                                 'maliit-framework']

    def _get_language_from_locale(self):
        language = None

        if self.locale is not None:
            language = self.locale.split('.')[0]
            if not language.startswith('zh_'):
                language = language.split('_')[0]
            elif language.startswith('zh_CN'):
                language = 'zh-hans'
            else:
                language = 'zh-hant'
                
        return language

    def _binary_exists(self, binary):
        return self.run_in_container("bash -c \"which {} &> /dev/null\"".format(binary)) == 0

    def setup_window_manager(self, enable_toolbars=False):
        if self._binary_exists('matchbox-window-manager'):
            if enable_toolbars:
                return ['matchbox-window-manager']

            return ['matchbox-window-manager', '-use_titlebar', 'no']
        else:
            return ['compiz']
            

    def check_language_support(self):
        if not self._binary_exists('check-language-support'):
            self.install_package('language-selector-common', update_cache=False)

        self.run_in_container("bash -c \"{} install $(check-language-support -l {})\"".format(_apt_command_prefix(), self.language))

    def update_locale(self):
        self.run_in_container("locale-gen {}".format(self.locale))

    def install_base_language_packs(self):
        base_language_packs = ['language-pack-{}', 'language-pack-gnome-{}']

        for language_pack in [p.format(self.language) for p in base_language_packs]:
            self.install_package(language_pack, update_cache=False)

    def create_libertine_container(self, password=None, multiarch=False):
        self.install_base_language_packs()

    def destroy_libertine_container(self):
        pass

    def copy_file_to_container(self, source, dest):
        """
        Copies a file from the host to the given path in the container.

        :param source: The full path to the file on the host.
        :param   dest: The relative path to the file in the container without
                       the root path.
        """
        if os.path.exists(os.path.join(self.root_path, dest)):
            return False

        shutil.copy2(source, os.path.join(self.root_path, dest.lstrip('/')))
        return True

    def delete_file_in_container(self, path):
        """
        Deletes a file within the container.

        :param path: The path to the file without the container root path.
        """
        os.remove(os.path.join(self.root_path, path.lstrip('/')))

    def start_container(self):
        """
        Starts the container.  To start the container means to put it into a
        'running' state, the meaning of which depends on the type of the
        container.
        """
        pass

    def stop_container(self):
        """
        Stops the container.  The opposite of start_container().
        """
        pass

    @abc.abstractmethod
    def run_in_container(self, command_string):
        """
        Runs a command inside the container context.

        :param command_string: The command line to execute in the container context.
        """
        pass

    def update_apt_cache(self):
        """
        Updates the apt cache in the container.
        """
        return self.run_in_container(_apt_command_prefix() + 'update')

    def update_packages(self, new_locale=None):
        """
        Updates all packages installed in the container.
        """
        self.update_apt_cache()

        if new_locale:
            self.locale = new_locale
            self.language = self._get_language_from_locale()
            self.update_locale()
            self.install_base_language_packs()

        return self.run_in_container(_apt_command_prefix() + '--force-yes dist-upgrade') == 0

    def install_package(self, package_name, no_dialog=False, update_cache=True):
        """
        Installs a named package in the container.

        :param package_name: The name of the package as APT understands it or
                             a full path to a Debian package on the host.
        """
        if update_cache:
            self.update_apt_cache()

        if package_name.endswith('.deb'):
            if not os.path.exists(package_name):
                utils.get_logger().error("File {} does not exist.".format(package_name))
                return False

            dest = os.path.join('/', 'tmp', package_name.split('/')[-1])
            file_created = self.copy_file_to_container(package_name, dest)

            self.run_in_container('dpkg -i {}'.format(dest))
            ret = self.run_in_container(_apt_command_prefix() + " install -f") == 0

            if file_created:
                self.delete_file_in_container(dest)

            return ret
        else:
            if no_dialog:
                os.environ['DEBIAN_FRONTEND'] = 'teletype'
            ret = self.run_in_container(_apt_command_prefix() + " install '" + package_name + "'") == 0

        self.check_language_support()

        return ret

    def remove_package(self, package_name):
        """
        Removes a package from the container.

        :param package_name: The name of the package to be removed.
        """
        if self.run_in_container(_apt_command_prefix() + " purge '" + package_name + "'") != 0:
            return False
        return self.run_in_container(_apt_command_prefix() + "autoremove --purge") == 0

    def configure_multiarch(self, should_enable):
        """
        Enables or disables multiarch repositories.

        :param should_enable: Whether or not to enable multiarch support.
        """
        if should_enable:
            ret = self.run_in_container("dpkg --add-architecture i386")
            if ret or ret == 0:
                self.update_apt_cache()
            return ret
        else:
            self.run_in_container(_apt_command_prefix() + "purge \".*:i386\"")
            return self.run_in_container("dpkg --remove-architecture i386")

    def configure_add_archive(self, archive, public_key_file):
        """
        Adds the given archive. If this archive requires a key, prompt user.

        :param archive: The configuration command to run.
        :param public_key_file: file containing the public key used to sign this archive
        """
        if not self._binary_exists('add-apt-repository'):
            self.install_package("software-properties-common")
        if 'https://' in archive and not os.path.exists(os.path.join(self.root_path, 'usr', 'lib', 'apt', 'methods', 'https')):
            self.install_package("apt-transport-https")

        retcode = self.run_in_container("add-apt-repository -y " + archive)
        if retcode is 0 and public_key_file is not None:
            with open(public_key_file, 'r') as keyfile:
                return self.run_in_container("bash -c 'echo \"%s\" | apt-key add -'" % keyfile.read())

        return retcode

    def configure_remove_archive(self, archive):
        """
        Removes the given archive.

        :param archive: The configuration command to run.
        """
        return self.run_in_container("add-apt-repository -y -r " + archive)

    @property
    def name(self):
        """
        The human-readable name of the container.
        """
        name = Libertine.container_name(self.container_id)
        if not name:
            name = 'Unknown'
        return name


class LibertineMock(BaseContainer):
    """
    A concrete mock container type.  Used for unit testing.
    """
    def __init__(self, container_id, containers_config=None):
        super().__init__(container_id, containers_config)
        self.container_type = "mock"

    def create_libertine_container(self, password=None, multiarch=False):
        return True

    def destroy_libertine_container(self):
        return True

    def update_packages(self, new_locale=None):
        return True

    def install_package(self, package_name, no_dialog=False, update_cache=True):
        return True

    def remove_package(self, package_name, no_dialog=False):
        return True

    def run_in_container(self, command_string):
        return True

    def start_application(self, app_exec_line, environ):
        import subprocess

        app = subprocess.Popen(app_exec_line, env=environ)
        return app

    def finish_application(self, app):
        app.wait()


class ContainerRunning(contextlib.ExitStack):
    """
    Helper object providing a running container context.

    Starts the container running if it's not already running, and shuts it down
    when the context is destroyed if it was not running at context creation.
    """
    def __init__(self, container):
        super().__init__()
        container.start_container()
        self.callback(lambda: container.stop_container())


class LibertineContainer(object):
    """
    A sandbox for DEB-packaged X11-based applications.
    """

    def __init__(self, container_id, containers_config=None):
        """
        Initializes the container object.

        :param container_id: The machine-readable container name.
        """
        super().__init__()

        if containers_config is None:
            containers_config = ContainersConfig()
        self.containers_config = containers_config

        container_type = self.containers_config.get_container_type(container_id)

        if container_type == "lxc":
            from  libertine.LxcContainer import LibertineLXC
            self.container = LibertineLXC(container_id)
        elif container_type == "lxd":
            from libertine.LxdContainer import LibertineLXD
            self.container = LibertineLXD(container_id, self.containers_config)
        elif container_type == "chroot":
            from  libertine.ChrootContainer import LibertineChroot
            self.container = LibertineChroot(container_id)
        elif container_type == "mock":
            self.container = LibertineMock(container_id, self.containers_config)
        else:
            raise RuntimeError("Unsupported container type %s" % container_type)

    @property
    def container_id(self):
        return self.container.container_id

    @property
    def name(self):
        return self.container.name

    @property
    def container_type(self):
        return self.container.container_type

    @property
    def root_path(self):
        return self.container.root_path

    def destroy_libertine_container(self):
        """
        Destroys the container and releases all its system resources.
        """
        return self.container.destroy_libertine_container()

    def create_libertine_container(self, password=None, multiarch=False):
        """
        Creates the container.
        """
        self.container.architecture = HostInfo().get_host_architecture()
        self.container.installed_release = self.containers_config.get_container_distro(self.container_id)

        return self.container.create_libertine_container(password, multiarch)

    def update_libertine_container(self, new_locale=None):
        """
        Updates the contents of the container.
        """
        try:
            with ContainerRunning(self.container):
                return self.container.update_packages(new_locale)
        except RuntimeError as e:
            return handle_runtime_error(e)

    def install_package(self, package_name, no_dialog=False, update_cache=True):
        """
        Installs a package in the container.
        """
        try:
            with ContainerRunning(self.container):
                return self.container.install_package(package_name, no_dialog, update_cache)
        except RuntimeError as e:
            return handle_runtime_error(e)

    def remove_package(self, package_name, no_dialog=False):
        """
        Removes a package from the container.

        :param package_name: The name of the package to be removed.
        """
        try:
            with ContainerRunning(self.container):
                if no_dialog:
                    os.environ['DEBIAN_FRONTEND'] = 'teletype'

                return self.container.remove_package(package_name)
        except RuntimeError as e:
            return handle_runtime_error(e)

    def search_package_cache(self, search_string):
        """
        Searches the container's package cache for a named package.

        :param search_string: the (regex) to use to search the package cache.
            The regex is quoted to sanitize it.
        """
        try:
            with ContainerRunning(self.container):
                return self.container.run_in_container("/usr/bin/apt-cache search '" + search_string + "'")
        except RuntimeError as e:
            return handle_runtime_error(e)

    def connect(self):
        """
        Connects to the container in preparation to launch an application.  May
        do something like start up daemons or bind-mount directories, I dunno,
        it's up to the concrete container class.  Maybe it does nothing.
        """
        pass

    def disconnect(self):
        """
        The inverse of connect() above.
        """
        pass

    def start_application(self, app_exec_line, environ):
        """
        Launches an application in the container.

        :param app_exec_line: the application exec line as passed in by
            ubuntu-app-launch
        """
        return self.container.start_application(app_exec_line, environ)

    def finish_application(self, app):
        """
        Finishes the currently running application in the container.
        """
        self.container.finish_application(app)

    def list_app_launchers(self, use_json=False):
        """
        Enumerates all application launchers (based on .desktop files) available
        in the container.

        :param use_json: Indicates the returned string should be i JSON format.
            The default format is some human-readble format.
        :rtype: A printable string containing a list of application launchers
            available in the container.
        """
        if use_json:
            return AppLauncherCache(self.container.name,
                                    self.container.root_path).to_json()
        else:
            return str(AppLauncherCache(self.container.name,
                                        self.container.root_path))

    def exec_command(self, exec_line):
        """
        Runs an arbitrary application in the container.  Mainly used for status
        reporting, etc. in the container.

        :param exec_line: The exec line to run inside the container.  For
            example, 'apt-cache policy package-foo'
        :rtype: The output of the given command.
        """
        try:
            with ContainerRunning(self.container):
                return self.container.run_in_container(exec_line) == 0
        except RuntimeError as e:
            return handle_runtime_error(e)

    def configure_multiarch(self, should_enable):
        try:
            with ContainerRunning(self.container):
                return self.container.configure_multiarch(should_enable)
        except RuntimeError as e:
            return handle_runtime_error(e)

    def configure_add_archive(self, archive, key):
        try:
            with ContainerRunning(self.container):
                return self.container.configure_add_archive(archive, key)
        except RuntimeError as e:
            return handle_runtime_error(e)

    def configure_remove_archive(self, archive):
        try:
            with ContainerRunning(self.container):
                return self.container.configure_remove_archive(archive)
        except RuntimeError as e:
            return handle_runtime_error(e)
