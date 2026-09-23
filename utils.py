import os
import sys
from PySide6.QtGui import QIcon


def get_app_root():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


APP_ROOT = get_app_root()
ICON_PATH = os.path.join(APP_ROOT, 'icon.ico')


def set_window_icon(window):
    if os.path.exists(ICON_PATH):
        window.setWindowIcon(QIcon(ICON_PATH))