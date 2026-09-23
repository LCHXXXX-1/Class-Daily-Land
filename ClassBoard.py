import os
import sys
import shutil

from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
from PySide6.QtCore import Qt

from utils import get_app_root, set_window_icon
from gui import ClassBoardApp
from schedule import ScheduleManager
from dynamic_island import DynamicIsland
from settings_manager import SettingsManager
from plugin_manager import PluginManager
from tray_icon import AppTray
from single_instance import acquire_single_instance_lock
import agreement

APP_ROOT = get_app_root()
CONFIG_DIR = os.path.join(APP_ROOT, 'settings')
CONFIG_FILE = os.path.join(CONFIG_DIR, 'config.json')
PLUGINS_DIR = os.path.join(APP_ROOT, 'plugins')
os.makedirs(CONFIG_DIR, exist_ok=True)
os.makedirs(PLUGINS_DIR, exist_ok=True)


if __name__ == '__main__':
    lock = acquire_single_instance_lock()
    if lock is None:
        sys.exit(0)

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    set_window_icon(app)

    if not agreement.check_agreement(CONFIG_DIR):
        sys.exit(0)

    settings = SettingsManager(CONFIG_DIR)
    schedule_manager = ScheduleManager(CONFIG_DIR)

    plugin_manager = PluginManager(
        PLUGINS_DIR,
        on_refresh=lambda: (island.update(), window.update()))

    window = ClassBoardApp(CONFIG_DIR, CONFIG_FILE, schedule_manager,
                           settings, plugin_manager)
    window.show()

    island = DynamicIsland(schedule_manager, settings, plugin_manager)
    island.show()
    island._pin_top()

    plugin_manager.load_all()

    def open_settings():
        window.open_settings()

    def add_plugin():
        path, _ = QFileDialog.getOpenFileName(
            None, "选择插件文件", "", "ClassBoard 插件 (*.cbplugin);;所有文件 (*)")
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
        app.quit()

    tray = AppTray(app, open_settings, add_plugin, do_exit)
    tray.show()
    app._tray = tray

    sys.exit(app.exec())