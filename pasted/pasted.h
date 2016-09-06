/**
 * @file pasted.h
 * @brief Copy & Paste daemon between X apps, other X apps, and native apps
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

#ifndef _PASTED_H_
#define _PASTED_H_

#include <memory>

#include <QApplication>
#include <QClipboard>
#include <QMimeData>
#include <QString>

#include <com/ubuntu/content/hub.h>
#include <X11/Xlib.h>

namespace cuc = com::ubuntu::content;


class Pasted
: public QApplication
{
  Q_OBJECT

  public:
    Pasted(int argc, char** argv);
    virtual ~Pasted() = default;

  private:
    void updateLastMimeData(const QMimeData *source);
    void updateXMimeData(const QMimeData *source);
    void handleContentHubPasteboard();
    void setPersistentSurfaceId();

    static bool compareMimeData(const QMimeData *a, const QMimeData *b);
    static void copyMimeData(QMimeData& target, const QMimeData *source);

  private slots:
    void handleXClipboard();
    void checkForAppFocus();

  private:
    QClipboard *clipboard_;
    cuc::Hub *content_hub_;
    QMimeData *mimeDataX_;
    std::unique_ptr<QMimeData> lastMimeData_;
    bool rootWindowHasFocus_;
    Window firstSeenWindow_;
    QString persistentSurfaceId_;
};

#endif /* _PASTED_H_ */
