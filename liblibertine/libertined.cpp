/*
 * Copyright 2017 Canonical Ltd
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


#include "libertined.h"

#include <QDBusMessage>
#include <QDBusInterface>
#include <QDebug>
#include <thread>
#include <chrono>
#include <QJsonDocument>
#include <QJsonArray>
#include <QJsonObject>


namespace
{

constexpr auto SERVICE_INTERFACE            = "com.canonical.libertine.Service";
constexpr auto OPERATIONS_INTERFACE         = "com.canonical.libertine.Service.Operations";
constexpr auto OPERATIONS_OBJECT            = "/com/canonical/libertine/Service/Operations";
constexpr auto OPERATIONS_MONITOR_INTERFACE = "com.canonical.libertine.Service.OperationsMonitor";
constexpr auto OPERATIONS_MONITOR_OBJECT    = "/com/canonical/libertine/Service/OperationsMonitor";

static QVariantList
dbusCall(QDBusConnection const& bus, QString const& iface, QString const& path,
         QString const& method, QVariantList const& args = QVariantList())
{
  auto message = QDBusMessage::createMethodCall(SERVICE_INTERFACE, path, iface, method);
  message.setArguments(args);
  auto response = bus.call(message);
  if (response.type() == QDBusMessage::ErrorMessage)
  {
    qWarning() << "error calling result" << response.errorMessage();
    return QVariantList();
  }

  return response.arguments();
}

static bool
isRunning(QDBusConnection const& bus, QString const& path)
{
  auto args = dbusCall(bus, OPERATIONS_MONITOR_INTERFACE, OPERATIONS_MONITOR_OBJECT, "running", QVariantList{path});

  if (args.isEmpty())
  {
    qWarning() << "lastError - no arguments?";
    return false;
  }

  return args.first().toBool();
}

static QString
result(QDBusConnection const& bus, QString const& path)
{
  auto args = dbusCall(bus, OPERATIONS_MONITOR_INTERFACE, OPERATIONS_MONITOR_OBJECT, "result", QVariantList{path});

  if (args.isEmpty())
  {
    qWarning() << "lastError - no arguments?";
    return QString();
  }

  return args.first().toString();
}

static QString
lastError(QDBusConnection const& bus, QString const& path)
{
  auto args = dbusCall(bus, OPERATIONS_MONITOR_INTERFACE, OPERATIONS_MONITOR_OBJECT, "last_error", QVariantList{path});

  if (args.isEmpty())
  {
    qWarning() << "lastError - no arguments?";
    return QString();
  }

  return args.first().toString();
}

static QString
call(QDBusConnection const& bus, QString const& method, QVariantList const& args)
{
  auto results = dbusCall(bus, OPERATIONS_INTERFACE, OPERATIONS_OBJECT, method, args);

  if (results.isEmpty())
  {
    return QString();
  }

  return qvariant_cast<QDBusObjectPath>(results.first()).path();
}

static bool
waitForFinish(QDBusConnection const& bus, QString const& path)
{
  std::chrono::microseconds wait(500);
  for (auto i = 0; i < 2000; ++i)
  {
    if (!isRunning(bus, path))
    {
      return true;
    }
    std::this_thread::sleep_for(wait);
  }
  return !isRunning(bus, path);
}

QString
container_info(char const* container_id, QString const& key)
{
  auto bus = QDBusConnection::sessionBus();
  auto path = call(bus, "container_info", QVariantList{QVariant(container_id)});

  if (!waitForFinish(bus, path))
  {
    return QString();
  }

  auto error = lastError(bus, path);
  if (!error.isEmpty())
  {
    qWarning() << "error:" << error;
    return QString();
  }

  return QJsonDocument::fromJson(result(bus, path).toLatin1()).object().value(key).toString();
}
}


QJsonArray
libertined_list()
{
  auto bus = QDBusConnection::sessionBus();
  auto path = call(bus, "list", QVariantList());

  if (!waitForFinish(bus, path))
  {
    return QJsonArray();
  }

  auto error = lastError(bus, path);
  if (!error.isEmpty())
  {
    qWarning() << "error:" << error;
    return QJsonArray();
  }

  return QJsonDocument::fromJson(result(bus, path).toLatin1()).array();
}

QJsonArray
libertined_list_app_ids(char const* container_id)
{
  auto bus = QDBusConnection::sessionBus();
  auto path = call(bus, "list_app_ids", QVariantList{QVariant(container_id)});

  if (!waitForFinish(bus, path))
  {
    return QJsonArray();
  }

  auto error = lastError(bus, path);
  if (!error.isEmpty())
  {
    qWarning() << "error:" << error;
    return QJsonArray();
  }

  return QJsonDocument::fromJson(result(bus, path).toLatin1()).array();
}

QString
libertined_container_path(char const* container_id)
{
  return container_info(container_id, "root");
}

QString
libertined_container_home_path(char const* container_id)
{
  return container_info(container_id, "home");
}

QString
libertined_container_name(char const* container_id)
{
  return container_info(container_id, "name");
}
