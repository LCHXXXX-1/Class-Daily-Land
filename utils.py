import os
import sys
import platform

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont

from paths import APP_ROOT, CONFIG_DIR, PLUGINS_DIR, ICON_PATH, get_app_root

APP_NAME = "Class Daily Land"
APP_NAME_CN = "班级日常"

__all__ = ['APP_ROOT', 'CONFIG_DIR', 'PLUGINS_DIR', 'ICON_PATH',
           'get_app_root', 'set_window_icon', 'app_icon',
           'APP_NAME', 'APP_NAME_CN',
           'windows_build', 'is_windows_11', 'is_windows_10',
           'windows_display_name']


def set_window_icon(window):
    window.setWindowIcon(app_icon())


_APP_ICON = None


def app_icon():
    """应用图标（窗口 / 托盘共用），始终返回一个可用的 QIcon。"""
    global _APP_ICON
    if _APP_ICON is not None:
        return _APP_ICON

    src = QIcon(ICON_PATH) if os.path.exists(ICON_PATH) else QIcon()
    out = QIcon()
    for sz in src.availableSizes():
        pm = src.pixmap(sz)
        if not pm.isNull() and pm.width() > 0 and pm.height() > 0:
            out.addPixmap(pm)

    have = {s.width() for s in out.availableSizes()}
    for n in (16, 20, 24, 32, 48, 64, 128, 256):
        if n in have:
            continue
        pm = src.pixmap(n, n)
        if not pm.isNull() and pm.width() > 0 and pm.height() > 0:
            out.addPixmap(pm)

    if out.availableSizes():
        _APP_ICON = out
    else:
        _APP_ICON = _fallback_icon()
    return _APP_ICON


def _fallback_icon():
    pm = QPixmap(32, 32)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#0067c0"))
    p.drawRoundedRect(1, 1, 30, 30, 8, 8)
    p.setPen(QColor("white"))
    f = QFont("Microsoft YaHei UI")
    f.setPixelSize(19)
    f.setBold(True)
    p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignCenter, "班")
    p.end()
    return QIcon(pm)


def windows_build():
    if sys.platform != 'win32':
        return 0
    try:
        return int(sys.getwindowsversion().build)
    except Exception:
        return 0


def is_windows_11():
    return windows_build() >= 22000


def is_windows_10():
    b = windows_build()
    return bool(b) and b < 22000


def windows_display_name():
    if sys.platform != 'win32':
        return platform.system() or "Unknown"
    b = windows_build()
    if b >= 22000:
        return f"Windows 11（Build {b}）"
    if b:
        return f"Windows 10（Build {b}）"
    return "Windows"