"""内置功能的登记表。

加一个内置功能 = 在 `BUILTINS` 里加一行 + 在 `builtin/` 下放一个 `register(api)` 的模块。
注册走的还是 `PluginAPI`，所以界面上（岛文本 / 加长片段 / 副岛 / 面板 / 设置页）
与第三方插件完全同构，不需要任何特殊分支。
"""
from __future__ import annotations

BUILTINS: tuple[dict[str, str], ...] = (
    {
        "key": "audio",
        "name": "媒体播放",
        "desc": "用 Windows SMTC 显示正在播放的媒体（歌名/歌手/暂停），"
                "可显示在主岛或副岛，停止后自动隐藏",
        "module": "builtin.audio.main",
        "icon": "ic_fluent_music_note_2_20_regular",
    },
    {
        "key": "disaster",
        "name": "灾害预警",
        "desc": "地震预警（ICL/Wolfx 数据源，按经纬度计算横波到达倒计时）"
                "与气象灾害预警（中央气象台）",
        "module": "builtin.disaster.main",
        "icon": "ic_fluent_alert_20_regular",
    },
)
