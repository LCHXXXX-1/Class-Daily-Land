import os

from PySide6.QtWidgets import QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QAction
from utils import ICON_PATH


class AppTray(QSystemTrayIcon):
    def __init__(self, app, on_settings, on_add_plugin, on_exit, parent=None):
        icon = QIcon(ICON_PATH) if os.path.exists(ICON_PATH) else QIcon()
        super().__init__(icon, parent)
        self.app = app
        self._on_settings = on_settings

        menu = QMenu()
        act_add = QAction("添加插件...", menu)
        act_add.triggered.connect(on_add_plugin)
        menu.addAction(act_add)
        menu.addSeparator()

        act_set = QAction("设置...", menu)
        act_set.triggered.connect(on_settings)
        menu.addAction(act_set)
        menu.addSeparator()

        act_exit = QAction("退出", menu)
        act_exit.triggered.connect(on_exit)
        menu.addAction(act_exit)

        self.setContextMenu(menu)
        self.setToolTip("ClassBoard")
        self.activated.connect(self._on_activated)

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self._on_settings()