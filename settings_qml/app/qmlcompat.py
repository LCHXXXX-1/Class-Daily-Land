"""QML ↔ Python 的边界类型转换。

★ 这个模块存在的唯一原因（实测踩出来的坑，别删）：
  QML 里的 JS 数组 / 对象传给 `@Slot(..., "QVariant", ...)` 时，
  **PySide6 原样把 QJSValue 递过来，不会转成 Python 的 list / dict**。

  实测（QML 传 `[{name:"第1节",...}]` 与 `{"0": ["语文"]}`）：

      Slot 收到的是QJSValue，而不是 list / dict。

  于是任何 `isinstance(value, list) / isinstance(value, dict)` 的校验
  都会当场失败。踩到的三处：
    - TimetableStore.update   → 课表永远存不进去
    - TimetableStore.setTempAdjust → 临时调课课程被丢空
    - ListStore.add(holidays / makeup) → 假期、调休加不进去

  凡是收到 QML 传来的 JS 结构，都要先过 `py()`。
"""
from __future__ import annotations

from typing import Any

__all__ = ["py"]


def py(value: Any) -> Any:  # noqa: ANN401
    """把 QJSValue（含嵌套的）递归转成 Python 原生结构。

    - QJSValue 数组 → list
    - QJSValue 对象 → dict（键统一成 str；QML 对象键本来就是字符串）
    - 其它 QJSValue → toVariant() 的结果，再递归一次
    - 已有的 dict / list / tuple → 逐项递归（深拷贝，顺便隔离 QML 侧的对象）
    - 标量 / None / Qt 枚举 → 原样返回（不碰不认识的东西）
    """
    # 延迟导入 QtQml：没有它时整套 QML 界面本来就起不来，
    # 但这个模块仍必须能被 import（headless 自检会直接 import 它）。
    try:
        from PySide6.QtQml import QJSValue  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        QJSValue = None  # type: ignore[assignment]

    if QJSValue is not None and isinstance(value, QJSValue):
        if value.isArray():
            return [py(item) for item in value.toVariant()]
        if value.isObject():
            variant = value.toVariant()
            # QML 对象 → toVariant() 通常已经是 dict，但 QJSValue 包装过的要再解一层
            return py(variant) if isinstance(variant, QJSValue) else _map(variant)
        return py(value.toVariant())

    return _map(value)


def _map(value: Any) -> Any:
    """dict / list / tuple 的逐项递归；其它类型原样返回。"""
    if isinstance(value, dict):
        return {str(k): py(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [py(item) for item in value]
    return value