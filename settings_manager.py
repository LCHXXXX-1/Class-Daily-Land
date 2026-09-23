import os
import json

SETTINGS_FILE = "settings.json"

DEFAULTS = {
    # 主窗口
    "main_width_ratio": 0.25,
    "main_font_size": 14,
    "main_auto_scroll": True,
    "main_scroll_interval": 50,
    "main_scroll_step": 1,
    "main_scroll_pause": 60,

    # 灵动岛
    "island_top_margin": 6,
    "island_hide_on_fullscreen": True,
    "island_show_wakeup_anim": True,
    "island_alert_width": 300,
    "island_alert_hold_ms": 600,

    # 渐显效果
    "anim_fade_window": True,
    "anim_fade_panel": True,
    "anim_fade_text": True,
    "anim_duration": 320,

    # 更新
    "check_update_on_start": True,
}


class SettingsManager:
    def __init__(self, config_dir):
        self.path = os.path.join(config_dir, SETTINGS_FILE)
        self.data = dict(DEFAULTS)
        self.load()

    def load(self):
        if not os.path.exists(self.path):
            self.save()
            return
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                saved = json.load(f)
            for k in DEFAULTS:
                if k in saved:
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