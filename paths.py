import os
import sys


def get_app_root():
    """可写数据（settings / plugins）的根目录。

    打包后是 exe 所在目录；源码运行时是包目录。
    注意：这只用于「数据目录」，资源文件请用 get_resource_root()。
    """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_resource_root():
    """只读资源（icon.ico 等）的根目录。

    onedir 打包后资源随 --add-data 落到 _internal（即 sys._MEIPASS），
    **不在** exe 旁边；老代码按 APP_ROOT 找 icon.ico 必然找不到，
    结果就是打包后窗口 / 托盘图标丢失。这里统一按 _MEIPASS 优先查找。
    """
    meipass = getattr(sys, '_MEIPASS', None)
    if meipass:
        return meipass
    return get_app_root()


APP_ROOT = get_app_root()
RESOURCE_ROOT = get_resource_root()
CONFIG_DIR = os.path.join(APP_ROOT, 'settings')
PLUGINS_DIR = os.path.join(APP_ROOT, 'plugins')


def _find_icon():
    """按「_MEIPASS → exe 目录」的顺序找 icon.ico，两处都没有就返回首选路径。

    打包后优先 _internal；兼容有人手工把 icon.ico 放到 exe 旁边的场景。
    """
    candidates = [RESOURCE_ROOT, APP_ROOT]
    for d in candidates:
        p = os.path.join(d, 'icon.ico')
        if os.path.isfile(p):
            return p
    return os.path.join(RESOURCE_ROOT, 'icon.ico')


ICON_PATH = _find_icon()
# 插件市场：GitHub plugins 分支的本地缓存（放在 settings/ 内，更新器升级时保留）
MARKET_CACHE_DIR = os.path.join(CONFIG_DIR, 'plugin-repo')


def ensure_dirs():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    os.makedirs(PLUGINS_DIR, exist_ok=True)
    os.makedirs(MARKET_CACHE_DIR, exist_ok=True)
