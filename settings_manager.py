import os
import json

SETTINGS_FILE = "settings.json"

DEFAULTS = {
    # 外观
    "theme_mode": "system",   # system / light / dark
    # Windows 11 云母材质（仅 Win11 生效；Win10 自动忽略）
    "settings_mica": True,

    # 主窗口
    "main_width_ratio": 0.25,
    "main_font_size": 14,
    "main_auto_scroll": True,
    "main_scroll_interval": 50,
    "main_scroll_step": 1,
    "main_scroll_pause": 60,
    "main_opacity": 1.0,
    "show_main_window": True,

    # 灵动岛
    "island_top_margin": 6,
    "island_hide_on_fullscreen": True,
    "island_show_wakeup_anim": True,
    "island_alert_width": 300,
    "island_alert_hold_ms": 600,
    "island_countdown_sec": 60,
    "show_island": True,

    # 副岛
    "show_sub_island": True,
    "sub_island_collapsed": False,
    "sub_island_auto_collapse_sec": 5,

    # 渐显效果
    "anim_fade_window": True,
    "anim_fade_panel": True,
    "anim_fade_text": True,
    "anim_duration": 320,

    # 更新
    "check_update_on_start": True,

    # 插件市场
    "disabled_plugins": [],        # 被禁用的插件目录名列表
    "market_source": "official",     # 插件市场索引来源：official / github / gitee
    # 第三方依赖包下载源：gitee / github（见 plugin_deps.PACKAGE_SOURCES）
    "packages_source": "gitee",
    # 自定义依赖清单服务器（空串 = 按 packages_source 取内置地址）
    "packages_base_url": "",
}


class SettingsManager:
    def __init__(self, config_dir):
        self.path = os.path.join(config_dir, SETTINGS_FILE)
        self.data = dict(DEFAULTS)
        self.load()

    @staticmethod
    def _valid_type(v, d):
        """校验存档值与默认值的类型是否兼容（不兼容则回退默认值）。"""
        if isinstance(d, bool):
            return isinstance(v, bool)
        if isinstance(d, (int, float)):
            return isinstance(v, (int, float)) and not isinstance(v, bool)
        return isinstance(v, type(d))

    def load(self):
        if not os.path.exists(self.path):
            self.save()
            return
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                saved = json.load(f)
            for k in DEFAULTS:
                if k in saved and self._valid_type(saved[k], DEFAULTS[k]):
                    self.data[k] = saved[k]
        except Exception:
            self.data = dict(DEFAULTS)

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def get(self, key, default=None):
        if key in self.data:
            return self.data[key]
        if default is not None:
            return default
        return DEFAULTS.get(key)

    def set(self, key, value):
        self.data[key] = value

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        self.data[key] = value