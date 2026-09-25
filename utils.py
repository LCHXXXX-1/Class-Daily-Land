import os

from PySide6.QtGui import QIcon

from paths import APP_ROOT, CONFIG_DIR, PLUGINS_DIR, ICON_PATH, get_app_root

__all__ = ['APP_ROOT', 'CONFIG_DIR', 'PLUGINS_DIR', 'ICON_PATH',
           'get_app_root', 'set_window_icon']


def set_window_icon(window):
    if os.path.exists(ICON_PATH):
        window.setWindowIcon(QIcon(ICON_PATH))
