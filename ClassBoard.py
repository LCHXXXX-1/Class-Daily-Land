import os
import sys
import shutil

from PySide6.QtWidgets import (QApplication, QFileDialog, QMessageBox,
                               QSystemTrayIcon)
from PySide6.QtCore import Qt

from paths import CONFIG_DIR, PLUGINS_DIR, ensure_dirs
from utils import set_window_icon
from gui import ClassBoardApp
from schedule import ScheduleManager
from dynamic_island import DynamicIsland
from sub_island import SubIsland
from settings_manager import SettingsManager
from plugin_manager import PluginManager
from controller import AppController
from tray_icon import AppTray
from single_instance import acquire_single_instance_lock
import agreement

CONFIG_FILE = os.path.join(CONFIG_DIR, 'config.json')


if __name__ == '__main__':
    lock = acquire_single_instance_lock()
    if lock is None:
        sys.exit(0)

    ensure_dirs()

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    set_window_icon(app)

    if not agreement.check_agreement(CONFIG_DIR):
        sys.exit(0)

    settings = SettingsManager(CONFIG_DIR)
    schedule_manager = ScheduleManager(CONFIG_DIR)
    controller = AppController(settings)

    def on_refresh():
        controller.notify_island_dirty()
        if island is not None:
            island.update()
        if sub_island is not None:
            sub_island.refresh_content()
        if window is not None:
            window.update()

    def on_notify(text, is_end=False):
        if island is not None:
            island.notify(text, is_end)

    plugin_manager = PluginManager(
        PLUGINS_DIR, on_refresh=on_refresh, on_notify=on_notify)
    plugin_manager.set_schedule_status_provider(schedule_manager.get_status)

    window = ClassBoardApp(CONFIG_DIR, CONFIG_FILE, schedule_manager,
                           settings, plugin_manager, controller)
    island = DynamicIsland(schedule_manager, settings, plugin_manager,
                           controller)
    sub_island = SubIsland(settings, plugin_manager, controller)

    controller.bind(window=window, island=island, sub_island=sub_island)

    island.set_geometry_callback(controller.on_island_geometry)
    plugin_manager.set_subisland_control(
        lambda collapsed: (sub_island.collapse() if collapsed
                           else sub_island.expand()))

    window.show()
    island.show()
    island._pin_top()

    controller.show_main(settings.get('show_main_window', True))
    controller.show_island(settings.get('show_island', True))
    controller.show_sub_island(settings.get('show_sub_island', True))
    controller.set_main_opacity(settings.get('main_opacity', 1.0))

    plugin_manager.load_all()

    def open_settings():
        window.open_settings()

    def add_plugin():
        path, _ = QFileDialog.getOpenFileName(
            None, "选择插件文件", "",
            "ClassBoard 插件 (*.cbplugin);;所有文件 (*)")
        if not path:
            return
        target = os.path.join(PLUGINS_DIR, os.path.basename(path))
        try:
            shutil.copy(path, target)
        except Exception as e:
            QMessageBox.critical(None, "导入失败", f"复制失败：{e}")
            return
        QMessageBox.information(None, "已导入", "插件已导入，重启后生效。")

    def do_exit():
        plugin_manager.stop_all()
        app.quit()

    tray = AppTray(app, controller, open_settings, add_plugin, do_exit,
                   on_holidays=window.open_holidays,
                   on_weekend=window.open_weekend)
    controller.bind(tray=tray)
    tray.show()

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.warning(None, "提示", "系统托盘不可用，改用设置窗口进行操作。")

    sys.exit(app.exec())
