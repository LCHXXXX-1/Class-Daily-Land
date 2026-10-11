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
        # 上一次下发时各组字段的签名，见 apply_settings
        self._applied_island_signature = None
        self._applied_visibility_signature = None

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
        # ★ 按变化量分级下发。
        #
        #   设置一变就全量重做的话，拖滑块时每秒要走好几次 —— 灵动岛重绘
        #   （apply_settings 里带 _push_up + update）、插件内容重建、
        #   托盘菜单重建，全都是白做，表现出来就是「整个窗口一闪一闪」。
        #   所以每件重活都由一组字段签名把关：签名没变就不做。
        island_signature = self._signature(('island_', 'sub_island_'))
        visibility_signature = (
            self.settings.get('show_main_window', True),
            self.settings.get('show_island', True),
            self.settings.get('show_sub_island', True),
        )

        # 首次下发（启动）时两个签名都是 None，自然全量做一遍。
        island_changed = island_signature != self._applied_island_signature
        visibility_changed = visibility_signature != self._applied_visibility_signature

        self._applied_island_signature = island_signature
        self._applied_visibility_signature = visibility_signature

        if self.window is not None:
            self.window.apply_main_settings()

        if island_changed or visibility_changed:
            if self.island is not None:
                self.island.apply_settings()
            if self.sub_island is not None:
                self.sub_island.apply_settings()

        if visibility_changed:
            self.show_main(self.settings.get('show_main_window', True))
            self.show_island(self.settings.get('show_island', True))
            self.show_sub_island(self.settings.get('show_sub_island', True))

        self.set_main_opacity(self.settings.get('main_opacity', 1.0))

        if island_changed:
            self.notify_island_dirty()
        if visibility_changed:
            self.refresh_tray()

    def _signature(self, prefixes):
        """把以这些前缀开头的设置项拼成一份可比较的快照。

        字段按前缀挑，以后加了设置项会自动纳入，不用回来改这里。
        """
        data = getattr(self.settings, 'data', None) or {}
        return tuple(sorted(
            (key, value) for key, value in data.items() if key.startswith(prefixes)
        ))
