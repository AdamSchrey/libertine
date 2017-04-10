/**
 * @file PackageInfoView.qml
 * @brief Container package info view
 */
/*
 * Copyright 2016 Canonical Ltd
 *
 * Libertine is free software: you can redistribute it and/or modify it under
 * the terms of the GNU General Public License, version 3, as published by the
 * Free Software Foundation.
 *
 * Libertine is distributed in the hope that it will be useful, but WITHOUT ANY
 * WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
 * A PARTICULAR PURPOSE.  See the GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 */
import Libertine 1.0
import QtQuick 2.4
import QtQuick.Layouts 1.0
import Ubuntu.Components 1.3
import Ubuntu.Components.ListItems 1.3 as ListItem


Page {
    id: packageInfoView
    header: PageHeader {
        id: pageHeader
        title: i18n.tr("%1 - %2").arg(currentContainer).arg(currentPackage)
    }
    property string currentContainer: null
    property var currentPackage: null
    property var statusText: containerConfigList.getAppStatus(currentContainer, currentPackage)
    property var packageVersionText: i18n.tr("Obtaining package version…")
    property string currentDetails: ""
    property var worker: null
    property bool showDetails: false

    signal sendOperationInteraction(string text)

    Flickable {
        anchors {
            topMargin: pageHeader.height
            fill: parent
        }
        contentHeight: contentItem.childrenRect.height
        boundsBehavior: (contentHeight > packageInfoView.height) ?
                            Flickable.DragAndOvershootBounds :
                            Flickable.StopAtBounds
        flickableDirection: Flickable.VerticalFlick

        Column {
            anchors.left: parent.left
            anchors.right: parent.right

            ListItem.Standard {
                id: packageListItem
                text: i18n.tr("Package version")
                control: Label {
                    text: packageVersionText
                }
            }

            ListItem.Standard {
                id: statusListItem
                text: i18n.tr("Install status")
                control: Label {
                    text: statusText
                }
            }

            ListItem.Standard {
                id: showDetailsView
                control: Button {
                    text: enabled ?
                              showDetails ? i18n.tr('Hide') : i18n.tr('Show')
                            : i18n.tr('None')
                    enabled: currentDetails != ""
                    onClicked: {
                        showDetails = !showDetails
                    }
                }
                text: i18n.tr("Operation details")
            }

            TextArea {
                id: packageDetailsView
                visible: showDetails
                anchors.left: parent.left
                anchors.right: parent.right
                height: Math.max(packageInfoView.height - pageHeader.height - packageListItem.height - showDetailsView.height - statusListItem.height - 35, units.gu(35))
                readOnly: true
                text: currentDetails
            }

            TextField {
                id: packageInputField
                visible: showDetails && (statusText === "installing" || statusText === "removing")
                anchors.left: parent.left
                anchors.right: parent.right
                text: ""
                onAccepted: {
                    sendOperationInteraction(text)
                    text = ""
                }
            }
        }
    }

    Component.onCompleted: {
        containerConfigList.configChanged.connect(reloadStatus)
        var command = "apt-cache policy " + currentPackage
        var worker = Qt.createComponent("ContainerManager.qml").createObject(parent)
        worker.finishedCommand.connect(getPackageVersion)

        currentDetails = packageOperationDetails.details(currentContainer, currentPackage)
        packageDetailsView.cursorPosition = packageDetailsView.length
        if (currentDetails != "") {
            showDetails = !showDetails
        }

        packageOperationDetails.updated.connect(updatePackageDetails)
        sendOperationInteraction.connect(packageOperationDetails.send)

        worker.error.connect(onError)
        worker.error.connect(packageOperationDetails.error)
        worker.runCommand(currentContainer, containerConfigList.getContainerName(currentContainer), command)
    }

    Component.onDestruction: {
        containerConfigList.configChanged.disconnect(reloadStatus)
        packageOperationDetails.updated.disconnect(updatePackageDetails)
        sendOperationInteraction.disconnect(packageOperationDetails.send)
    }

    function updatePackageDetails(container_id, package_name, details) {
        if (container_id === currentContainer && package_name === currentPackage) {
            currentDetails += details
            packageDetailsView.cursorPosition = packageDetailsView.length
        }
    }

    function reloadStatus() {
        statusText = containerConfigList.getAppStatus(currentContainer, currentPackage)

        if (!statusText) {
            statusText = i18n.tr("removed")
        }
    }

    function getPackageVersion(command_output) {
        if (packageInfoView) {
            packageVersionText = containerConfigList.getAppVersion(command_output, statusText === "installed")
        }
    }

    function onError() {
        packageVersionText = i18n.tr("Unknown")
    }
}
