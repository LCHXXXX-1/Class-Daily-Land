import os

from PySide6.QtWidgets import QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QAction
from utils import ICON_PATH


class AppTray(QSystemTrayIcon):
    def __init__(self, app, controller, on_settings, on_add_plugin, on_exit,
                 on_holidays=None, on_weekend=None, parent=None):
        icon = QIcon(ICON_PATH) if os.path.exists(ICON_PATH) else QIcon()
        super().__init__(icon, parent)
        self.app = app
        self.controller = controller
        self._on_settings = on_settings
        self._syncing = False

        menu = QMenu()

        self.act_main = QAction("显示班级日常", menu)
        self.act_main.setCheckable(True)
        self.act_main.toggled.connect(
            lambda v: self._toggle('show_main_window', v,
                                   self.controller.show_main))

        self.act_island = QAction("显示灵动岛", menu)
        self.act_island.setCheckable(True)
        self.act_island.toggled.connect(
            lambda v: self._toggle('show_island', v,
                                   self.controller.show_island))

        self.act_sub = QAction("显示副岛", menu)
        self.act_sub.setCheckable(True)
        self.act_sub.toggled.connect(
            lambda v: self._toggle('show_sub_island', v,
                                   self.controller.show_sub_island))

        menu.addAction(self.act_main)
        menu.addAction(self.act_island)
        menu.addAction(self.act_sub)
        menu.addSeparator()

        if on_holidays is not None:
            act_holiday = QAction("假期与调休...", menu)
            act_holiday.triggered.connect(on_holidays)
            menu.addAction(act_holiday)
        if on_weekend is not None:
            act_weekend = QAction("周末作息...", menu)
            act_weekend.triggered.connect(on_weekend)
            menu.addAction(act_weekend)
        menu.addSeparator()

        act_set = QAction("设置...", menu)
        act_set.triggered.connect(on_settings)
        menu.addAction(act_set)

        act_add = QAction("添加插件...", menu)
        act_add.triggered.connect(on_add_plugin)
        menu.addAction(act_add)
        menu.addSeparator()

        act_exit = QAction("退出", menu)
        act_exit.triggered.connect(on_exit)
        menu.addAction(act_exit)

        self.setContextMenu(menu)
        self.setToolTip("Class Daily Land")
        self.activated.connect(self._on_activated)
        self.sync_state()

    def _toggle(self, key, value, apply_fn):
        if self._syncing:
            return
        self.controller.settings[key] = bool(value)
        self.controller.settings.save()
        apply_fn(bool(value))

    def sync_state(self):
        self._syncing = True
        settings = getattr(self.controller, 'settings', None)
        if settings is not None:
            self.act_main.setChecked(bool(settings.get('show_main_window', True)))
            self.act_island.setChecked(bool(settings.get('show_island', True)))
            self.act_sub.setChecked(bool(settings.get('show_sub_island', True)))
        self._syncing = False

    def _on_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self._on_settings()