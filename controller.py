"""应用级协调器：持有各窗口/组件引用，集中处理设置应用与可见性联动。

替代原先通过 QApplication.topLevelWidgets() + 类名字符串匹配的通信方式。
"""
from PySide6.QtCore import QObject, Signal


class AppController(QObject):
    main_visibility_changed = Signal(bool)
    island_visibility_changed = Signal(bool)
    sub_visibility_changed = Signal(bool)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.window = None
        self.island = None
        self.sub_island = None
        self.tray = None

    def bind(self, window=None, island=None, sub_island=None, tray=None):
        if window is not None:
            self.window = window
        if island is not None:
            self.island = island
        if sub_island is not None:
            self.sub_island = sub_island
        if tray is not None:
            self.tray = tray

    # ---------- 可见性 ----------
    def show_main(self, visible):
        visible = bool(visible)
        if self.window is not None:
            self.window.setVisible(visible)
        self.main_visibility_changed.emit(visible)

    def show_island(self, visible):
        visible = bool(visible)
        if self.island is not None:
            self.island.set_enabled(visible)
        self.island_visibility_changed.emit(visible)

    def show_sub_island(self, visible):
        visible = bool(visible)
        if self.sub_island is not None:
            self.sub_island.set_enabled(visible)
        self.sub_visibility_changed.emit(visible)

    def set_main_opacity(self, value):
        if self.window is not None:
            self.window.apply_opacity(value)

    def test_countdown(self, seconds=None):
        """让真实灵动岛强制演示一次倒计时。"""
        if self.island is None:
            return False
        return self.island.start_test_countdown(seconds)

    def run_scenario_test(self, advance_sec, countdown_sec, end_hold_sec,
                          speed=10.0):
        """让真实灵动岛跑完整情景：提前 → 倒计时 → 上课 → 下课 → 恢复。"""
        if self.island is None:
            return False
        return self.island.start_scenario_test(
            advance_sec, countdown_sec, end_hold_sec, speed)

    # ---------- 联动 ----------
    def on_island_geometry(self, geom):
        if self.sub_island is None:
            return
        self.sub_island.reposition(geom)
        state = self.island._state if self.island is not None else 'hidden'
        self.sub_island.set_main_state(state)

    def notify_island_dirty(self):
        if self.island is not None:
            if hasattr(self.island, 'refresh_plugins'):
                self.island.refresh_plugins()
            else:
                self.island._last_key = None
                self.island.update()

    def refresh_tray(self):
        if self.tray is not None:
            self.tray.sync_state()

    # ---------- 设置应用 ----------
    def apply_settings(self):
        if self.window is not None:
            self.window.apply_main_settings()
        if self.island is not None:
            self.island.apply_settings()
        if self.sub_island is not None:
            self.sub_island.apply_settings()

        self.show_main(self.settings.get('show_main_window', True))
        self.show_island(self.settings.get('show_island', True))
        self.show_sub_island(self.settings.get('show_sub_island', True))
        self.set_main_opacity(self.settings.get('main_opacity', 1.0))

        self.notify_island_dirty()
        self.refresh_tray()
