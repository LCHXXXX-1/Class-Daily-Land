"""路径管理：数据目录与 QML 资源目录。

对应源项目 paths.py 的语义：**严格区分「可写数据目录」与「只读资源目录」**。
打包后 exe 所在目录才是可写位置，资源可能被解到别处，所以不能混用一个根。

对外开放的 `Paths` 是给 QML 用的：RinUI 的 NavigationView 内部靠
`Qt.createComponent(page)` 加载页面，相对路径会按 RinUI 包所在目录解析（必然找不到），
所以必须给它**绝对 file:// URL** —— 这也是 Class Widgets 2 要写一个 PathManager 的原因。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Slot

# ---------------------------------------------------------------- 目录

def _app_root() -> Path:
    """可写数据的根。打包后是 exe 所在目录，源码运行时是项目根。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


APP_ROOT = _app_root()
RESOURCE_ROOT = Path(__file__).resolve().parent.parent
QML_DIR = RESOURCE_ROOT / "qml"

# 数据根允许用环境变量覆盖，方便自检 / 出图时用临时目录、不碰真实配置
DATA_ROOT = Path(os.environ.get("CDL_DATA_ROOT") or (APP_ROOT / "data"))
CONFIG_DIR = DATA_ROOT / "settings"
HOMEWORK_FILE = CONFIG_DIR / "homework.json"
NAME_FILE = CONFIG_DIR / "name.json"
PLUGINS_DIR = DATA_ROOT / "plugins"


class Paths(QObject):
    """给 QML 用的路径助手。所有返回值都是绝对 file:// URL 或本地路径字符串。"""

    # 宿主要求「打开设置就落在某一页」时填这里（导航标题，如「灵动岛」）。
    # 必须**在 QML 加载前**写进去：Settings.qml 的 defaultPage 绑定要读它，
    # 而 defaultPage 在那个时机决定了 NavigationView 的**首次 push**。
    # 为什么不用「显示后再 safePush」：那条路在 stackView 还没有 currentItem 时
    # replace(null) 会失败，表现为「左侧高亮跳过去了、右侧还停在首页」。
    _start_page: str = ""

    @Slot(str)
    def setStartPage(self, title: str) -> None:
        type(self)._start_page = str(title or "")

    @Slot(result=str)
    def startPage(self) -> str:
        return type(self)._start_page

    @Slot(str, result=str)
    def qml(self, name: str) -> str:
        """qml("pages/General.qml") → 绝对 file:// URL（NavigationView 要的就是这个）。"""
        return QUrl.fromLocalFile(str((QML_DIR / name).resolve())).toString()

    @Slot(str, result=str)
    def asset(self, name: str) -> str:
        return QUrl.fromLocalFile(str((RESOURCE_ROOT / "assets" / name).resolve())).toString()

    @Slot(result=str)
    def configDir(self) -> str:
        return str(CONFIG_DIR)

    @Slot(result=str)
    def pluginsDir(self) -> str:
        return str(PLUGINS_DIR)

    @Slot(result=str)
    def dataDir(self) -> str:
        return str(DATA_ROOT)


def ensure_dirs() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
