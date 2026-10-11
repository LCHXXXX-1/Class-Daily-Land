"""灾害预警插件的自绘模块。

**重要**：`draw_main_extra` / `draw_sub` 必须是本模块的模块级函数。
副岛的 spec 身份判定包含 `id(spec['draw'])`，若用闭包/lambda 现造，
每次 spec 调用 id 都会变化，会导致副岛反复触发"新内容自动展开"。

本模块不导入 main，避免循环依赖；显示数据由 main 通过 `update_view()`
写入模块级 `_view`，draw 函数只做绘制（微秒级、不联网、不算数）。
"""
import math

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import (QColor, QFont, QPainter, QPainterPath, QPen,
                           QFontMetricsF)

# 等级 -> 颜色（默认值与 quake_calc.LEVEL_COLORS 保持一致；
# 此处本地定义是为了让本模块不依赖同目录其他模块——插件被 importlib
# 按文件路径加载时，插件目录并不在 sys.path 上。
# 用户自定义配色通过 view 的 "colors" 传入，见 _level_color()）
_LEVEL_COLORS = {
    "blue": "#4da3ff",
    "yellow": "#ffd23f",
    "orange": "#ff9f0a",
    "red": "#ff453a",
}

# main 每 tick 更新的显示视图
_view = {
    "kind": None,        # None | 'quake' | 'weather'
    "level": "blue",     # 烈度/预警等级色键
    "colors": None,      # 自定义配色 dict（可空，空则用默认）
    "main": "",          # 主岛 extra 文本
    "sub": "",           # 副岛展开文本
    "icon": "quake",     # 'quake' | 'weather'
    "pulse": False,      # 是否脉冲动画（地震预警中）
}


def view():
    """当前显示视图的只读快照（供 main 计算宽度等）。"""
    return dict(_view)


def update_view(**kw):
    _view.update(kw)


def clear_view():
    _view.update({"kind": None, "main": "", "sub": "",
                  "icon": "quake", "pulse": False})


def has_content():
    return _view.get("kind") is not None


def _level_color():
    level = _view.get("level") or "blue"
    colors = _view.get("colors")
    if isinstance(colors, dict):
        c = colors.get(level)
        if isinstance(c, str) and c.strip():
            return QColor(c.strip())
    return QColor(_LEVEL_COLORS.get(level, "#4da3ff"))


def _font(size=13, bold=True):
    f = QFont("Microsoft YaHei UI")
    f.setPixelSize(size)
    f.setBold(bool(bold))
    return f


# ---------------- 矢量图标 ----------------
def paint_quake_wave(p, rect, t, color, phase=0.0):
    """同心圆弧"地震波"：两层扩散圆弧 + 中心点。"""
    p.save()
    p.setPen(Qt.NoPen)
    p.setBrush(color)
    cx = rect.center().x()
    cy = rect.center().y()
    base = max(2.0, min(rect.width(), rect.height()) * 0.16)
    p.drawEllipse(QPointF(cx, cy), base, base)

    pen = QPen(color)
    pen.setWidthF(1.4)
    p.setBrush(Qt.NoBrush)
    for k in range(2):
        # 0..1 循环扩散
        prog = ((t * 0.9 + phase + k * 0.5) % 1.0)
        r = base + prog * base * 2.4
        alpha = int(200 * (1.0 - prog) ** 1.4)
        if alpha <= 3:
            continue
        c = QColor(color)
        c.setAlpha(alpha)
        pen.setColor(c)
        p.setPen(pen)
        p.drawArc(int(cx - r), int(cy - r), int(r * 2), int(r * 2),
                  40 * 16, 100 * 16)
        p.drawArc(int(cx - r), int(cy - r), int(r * 2), int(r * 2),
                  220 * 16, 100 * 16)
    p.restore()


def paint_warn_triangle(p, rect, color):
    """警告三角（气象灾害）。"""
    p.save()
    w = min(rect.width(), rect.height())
    x = rect.center().x() - w / 2.0
    y = rect.center().y() - w / 2.0
    h = w * 0.86

    path = QPainterPath()
    path.moveTo(x + w / 2.0, y)
    path.lineTo(x + w, y + h)
    path.lineTo(x, y + h)
    path.closeSubpath()
    p.setPen(Qt.NoPen)
    p.setBrush(color)
    p.drawPath(path)

    p.setPen(QPen(QColor("#1c1c1e"), max(1.2, w * 0.09)))
    p.drawLine(QPointF(x + w / 2.0, y + h * 0.24),
               QPointF(x + w / 2.0, y + h * 0.60))
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#1c1c1e"))
    p.drawEllipse(QPointF(x + w / 2.0, y + h * 0.78), w * 0.055, w * 0.055)
    p.restore()


def paint_pulse_dot(p, rect, t, color):
    """脉冲圆点（地震预警进行中）。"""
    p.save()
    p.setPen(Qt.NoPen)
    cx = rect.center().x()
    cy = rect.center().y()
    r = max(3.0, min(rect.width(), rect.height()) * 0.18)
    prog = (t * 0.8) % 1.0
    c = QColor(color)
    c.setAlpha(int(170 * (1.0 - prog)))
    p.setBrush(c)
    rr = r + prog * r * 2.2
    p.drawEllipse(QPointF(cx, cy), rr, rr)
    p.setBrush(color)
    p.drawEllipse(QPointF(cx, cy), r, r)
    p.restore()


def _paint_icon(p, rect, t):
    color = _level_color()
    if _view.get("icon") == "weather":
        paint_warn_triangle(p, rect, color)
    elif _view.get("pulse"):
        paint_quake_wave(p, rect, t, color)
    else:
        paint_pulse_dot(p, rect, t, color)


# ---------------- 文字：放不下就滚动 ----------------
MARQ_SPEED = 30.0        # px/s
MARQ_PAUSE = 0.9         # 每轮先停一下
MARQ_GAP = 36.0          # 首尾间隔


def _draw_marquee(painter, rect, text, t, font):
    """文字超出矩形宽度时左右循环滚动（跑马灯），否则直接绘制。

    t 由宿主按 ~60fps 传入（time.monotonic()），无需额外定时器。
    """
    if not text or rect.width() <= 4:
        return
    fm = QFontMetricsF(font)
    w = fm.horizontalAdvance(text)
    if w <= rect.width():
        painter.drawText(rect, Qt.AlignVCenter | Qt.AlignLeft, text)
        return

    span = w + MARQ_GAP
    cycle = span / MARQ_SPEED + MARQ_PAUSE
    phase = t % cycle
    offset = 0.0 if phase < MARQ_PAUSE else (phase - MARQ_PAUSE) * MARQ_SPEED

    painter.save()
    painter.setClipRect(rect)
    for k in (0, 1):
        x = rect.left() - offset + k * span
        if x > rect.right():
            break
        painter.drawText(QRectF(x, rect.top(), w + 4.0, rect.height()),
                         Qt.AlignVCenter | Qt.AlignLeft, text)
    painter.restore()


# ---------------- 主岛加长片段 ----------------
def draw_main_extra(painter, rect, t):
    """主岛右侧加长片段：图标 + 一行状态文本（超长自动滚动）。"""
    if not has_content():
        return
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)
    h = rect.height()
    icon_box = QRectF(rect.left() + 4, rect.top() + (h - 20) / 2.0, 20, 20)
    _paint_icon(painter, icon_box, t)

    font = _font(13)
    painter.setFont(font)
    painter.setPen(QColor("#ffffff"))
    tx = icon_box.right() + 7
    text_rect = QRectF(tx, rect.top(), max(0.0, rect.right() - tx - 6), h)
    _draw_marquee(painter, text_rect, _view.get("main") or "", t, font)
    painter.restore()


# ---------------- 副岛 ----------------
def draw_sub(painter, rect, t):
    """副岛：收起（宽<=46）只画图标；展开画图标 + 文本（超长自动滚动）。"""
    if not has_content():
        return
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)
    h = rect.height()

    if rect.width() <= 46:                      # 收起为圆形
        size = min(22.0, h - 16)
        box = QRectF(rect.center().x() - size / 2.0,
                     rect.center().y() - size / 2.0, size, size)
        _paint_icon(painter, box, t)
        painter.restore()
        return

    icon_box = QRectF(rect.left() + 8, rect.top() + (h - 20) / 2.0, 20, 20)
    _paint_icon(painter, icon_box, t)

    font = _font(13)
    painter.setFont(font)
    painter.setPen(QColor("#e6e6e6"))
    tx = icon_box.right() + 8
    text_rect = QRectF(tx, rect.top(), max(0.0, rect.right() - tx - 10), h)
    _draw_marquee(painter, text_rect, _view.get("sub") or "", t, font)
    painter.restore()


# ---------------- 工具：文本测量 ----------------
def text_width(text, size=13, bold=True):
    return QFontMetricsF(_font(size, bold)).horizontalAdvance(text or "")
