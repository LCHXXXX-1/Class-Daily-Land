"""内置功能的数据目录。

这些功能原本是 `plugins/` 里的插件，现在直接编进主程序（用户要求"不以插件形式存在"），
但**数据仍要放在 settings/ 下**：程序目录在打包后可能是只读的，
往 `builtin/` 包里写 json 会失败（而且卸载/升级会丢）。
"""
from __future__ import annotations

import os

from paths import CONFIG_DIR


def builtin_dir(key: str) -> str:
    """内置功能 `key` 的数据目录（settings/builtin/<key>/），保证存在。"""
    path = os.path.join(CONFIG_DIR, "builtin", str(key))
    os.makedirs(path, exist_ok=True)
    return path
