"""JSON 读写：原子写 + 逐字段容错。

对应源项目 storage.py 的语义，两条约定照搬：
  · **原子写**：先写临时文件再 os.replace，避免崩溃时把配置截断成半个文件
  · **逐字段容错**：单个字段类型不对只丢那一个字段，不让整份配置失效
  · 中文不转义（ensure_ascii=False）—— .NET 那边踩过 System.Text.Json 默认转义 \\uXXXX 的坑
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def read_json(path: Path, default: Any) -> Any:
    """读不到 / 解析失败一律回落默认值，不抛异常。"""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return default


def write_json_atomic(path: Path, data: Any) -> None:
    """原子写：临时文件 + os.replace。父目录不存在会自动建。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def merge_known(raw: Any, coerce) -> dict[str, Any]:
    """把磁盘上的任意 JSON 收敛成「键 → 合法值」。

    coerce 是 `(key, value) -> value` —— 逐字段校验，坏字段单独丢弃。
    """
    result: dict[str, Any] = {}
    if not isinstance(raw, dict):
        return result
    for key, value in raw.items():
        coerced = coerce(key, value)
        if coerced is not None:
            result[key] = coerced
    return result
