import os
import sys


def get_app_root():
    """可写数据（settings / plugins）的根目录。

    打包后是 exe 所在目录；源码运行时是入口所在的 app 目录
    （本文件位于 Core/paths.py，所以向上两级）。
    注意：这只用于「数据目录」，资源文件请用 get_resource_root()。
    """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_resource_root():
    """只读资源（icon.ico 等）的根目录。

    onedir 打包后资源随 --add-data 落到 _internal（即 sys._MEIPASS），
    但有些打包方式也会把 icon.ico 放到 exe 旁边。这里只负责给出
    _MEIPASS 路径；实际查找顺序由 _find_icon() 控制（exe 同级优先）。
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
    """按「exe 同级目录 → sys._MEIPASS（_internal）」的顺序找 icon.ico。

    onedir 打包后，--add-data 放进来的资源通常在 _internal；
    但也有人会手工把 icon.ico 放到 exe 旁边。exe 同级优先，
    这样两种部署方式都能取到图标，取不到时再回退到默认资源路径。
    """
    candidates = []
    for d in (APP_ROOT, RESOURCE_ROOT):
        if d and d not in candidates:
            candidates.append(d)
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
