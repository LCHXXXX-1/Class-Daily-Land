"""统一的应用路径来源，避免各模块重复计算。"""
import os
import sys


def get_app_root():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


APP_ROOT = get_app_root()
CONFIG_DIR = os.path.join(APP_ROOT, 'settings')
PLUGINS_DIR = os.path.join(APP_ROOT, 'plugins')
ICON_PATH = os.path.join(APP_ROOT, 'icon.ico')


def ensure_dirs():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    os.makedirs(PLUGINS_DIR, exist_ok=True)
