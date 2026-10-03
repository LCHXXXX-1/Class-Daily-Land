"""设置窗口 V3 —— 从零全新设计（独立文件，与旧设置代码无关）。

设计概念：iOS / Windows 11 混合的「设置中心」——
- 左侧导航：每个分类一枚**彩色圆角图标瓦片 + 手绘矢量线条图标**
  （齿轮/调色盘/胶囊/日历/购物袋/滑杆/拼图/信息，不依赖 emoji 字体），
  选中项高亮块 + 左侧指示条平滑滑动
- 右侧内容：大号页头 + 圆角卡片（柔和投影，随主题调透明度），
  卡片内行间发丝分隔线；操作项为「标题 + 说明 + ›」可点行
- 自研 AnimatedStack：页面切换 = 交叉淡入 + 14px 上滑（并行动画组），
  告别 QStackedWidget 的生硬跳变；开关 / 分段选择器 / 滑杆全部自绘动画
- 品牌区与关于页使用真实应用图标（icon.ico）
- 浅色 / 深色 / Windows 11 云母材质全量适配，主题切换即时刷新

功能与旧设置界面完全一致（通用 / 外观 / 灵动岛 / 课表与提醒 /
插件市场 / 高级 / 插件页 / 关于），入口签名保持不变：

    from settings_dialog_v2 import SettingsDialog
    SettingsDialog(settings, schedule_manager=..., plugin_manager=...,
                   controller=..., on_apply=..., parent=...)
"""
import math
import os

from PySide6.QtCore import (Qt, QTimer, QPoint, QPointF, QRect, QRectF, QSize,
                            Property, Signal, QPropertyAnimation, QEasingCurve,
                            QAbstractAnimation, QParallelAnimationGroup)
from PySide6.QtGui import (QColor, QFont, QIcon, QPainter, QPainterPath,
                           QPen, QPixmap)
from PySide6.QtWidgets import (QAbstractButton, QApplication, QComboBox,
                               QDialog, QDoubleSpinBox, QFileDialog, QFrame,
                               QGraphicsDropShadowEffect, QGraphicsOpacityEffect,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPushButton,
                               QScrollArea, QSizePolicy, QSlider, QSpinBox,
                               QVBoxLayout, QWidget)

from ui_common import (setup_dialog_style as _setup_dialog_style,
                       apply_window_material, disable_mica, set_dark_titlebar,
                       setup_touch_scroll)

import theme
from about import get_version
from utils import APP_NAME, ICON_PATH, is_windows_11, windows_display_name
from settings_manager import DEFAULTS
from settings_widgets import StaggerPlayer


# ============================================================
# 小工具
# ============================================================
def _rgba(hex_color, alpha):
    h = str(hex_color).lstrip('#')
    if len(h) == 3:
        h = ''.join(ch * 2 for ch in h)
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except Exception:
        return str(hex_color)
    return f"rgba({r}, {g}, {b}, {alpha})"


def _app_pixmap(size):
    """应用图标（icon.ico），取不到返回 None。"""
    try:
        if os.path.exists(ICON_PATH):
            pm = QIcon(ICON_PATH).pixmap(QSize(size, size))
            if not pm.isNull():
                return pm
    except Exception:
        pass
    return None


# ============================================================
# 动画页面栈：交叉淡入 + 上滑
# ============================================================
class AnimatedStack(QWidget):
    """一次只显示一页；切换时新页从 y+14 淡入上滑，旧页立即隐藏。"""

    SLIDE = 14
    DURATION = 230

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("v2Stack")
        self._pages = []
        self._current = -1
        self._group = None

    def add_page(self, w):
        w.setParent(self)
        w.hide()
        w.resize(self.size())
        self._pages.append(w)
        return len(self._pages) - 1

    def count(self):
        return len(self._pages)

    def current_index(self):
        return self._current

    def set_current(self, idx, animate=True):
        if not (0 <= idx < len(self._pages)) or idx == self._current:
            return
        old = self._pages[self._current] if self._current >= 0 else None
        new = self._pages[idx]
        self._current = idx

        self._stop_anim()
        if old is not None:
            old.hide()
            self._clear_effect(old)
        new.resize(self.size())

        if not animate or not self.isVisible():
            new.move(0, 0)
            new.show()
            new.raise_()
            return

        eff = QGraphicsOpacityEffect(new)
        eff.setOpacity(0.0)
        new.setGraphicsEffect(eff)
        new.move(0, self.SLIDE)
        new.show()
        new.raise_()

        a_op = QPropertyAnimation(eff, b"opacity", self)
        a_op.setDuration(self.DURATION)
        a_op.setStartValue(0.0)
        a_op.setEndValue(1.0)
        a_op.setEasingCurve(QEasingCurve.OutCubic)

        a_pos = QPropertyAnimation(new, b"pos", self)
        a_pos.setDuration(self.DURATION)
        a_pos.setStartValue(QPoint(0, self.SLIDE))
        a_pos.setEndValue(QPoint(0, 0))
        a_pos.setEasingCurve(QEasingCurve.OutCubic)

        self._group = QParallelAnimationGroup(self)
        self._group.addAnimation(a_op)
        self._group.addAnimation(a_pos)
        self._group.finished.connect(lambda: self._clear_effect(new))
        self._group.start(QAbstractAnimation.DeleteWhenStopped)

    def _stop_anim(self):
        if self._group is not None:
            try:
                self._group.stop()
            except RuntimeError:
                pass
            self._group = None
        for w in self._pages:
            self._clear_effect(w)
            if w.isVisible():
                w.move(0, 0)

    @staticmethod
    def _clear_effect(w):
        try:
            if isinstance(w.graphicsEffect(), QGraphicsOpacityEffect):
                w.setGraphicsEffect(None)
        except RuntimeError:
            pass

    def resizeEvent(self, event):
        super().resizeEvent(event)
        for w in self._pages:
            w.resize(self.size())


# ============================================================
# 开关（自绘，旋钮带柔和投影）
# ============================================================
class Toggle(QAbstractButton):
    TRACK_W = 46
    TRACK_H = 26
    PAD = 3

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self._knob = 0.0
        self._anim = None
        self._mute = False
        self.toggled.connect(self._on_toggled)

    def _get_knob(self):
        return self._knob

    def _set_knob(self, v):
        self._knob = 0.0 if v < 0 else (1.0 if v > 1 else float(v))
        self.update()

    knob = Property(float, _get_knob, _set_knob)

    def sizeHint(self):
        return QSize(self.TRACK_W + 4, self.TRACK_H + 4)

    def set_state(self, checked):
        checked = bool(checked)
        self._mute = True
        self.setChecked(checked)
        self._mute = False
        self._stop_anim()
        self._knob = 1.0 if checked else 0.0
        self.update()

    def _on_toggled(self, on):
        if self._mute:
            return
        self._animate_to(1.0 if on else 0.0)

    def _animate_to(self, target):
        self._stop_anim()
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(170)
        self._anim.setStartValue(self._knob)
        self._anim.setEndValue(target)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.start()

    def _stop_anim(self):
        if self._anim is not None:
            self._anim.stop()
            self._anim.deleteLater()
            self._anim = None

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        on = self.isChecked()
        tw, th = self.TRACK_W, self.TRACK_H
        x = (self.width() - tw) / 2.0
        y = (self.height() - th) / 2.0

        if on:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.color(
                "accent_hover" if self.underMouse() else "accent")))
            p.drawRoundedRect(QRectF(x, y, tw, th), th / 2, th / 2)
        else:
            p.setPen(QPen(QColor(theme.color("border")), 1))
            p.setBrush(QColor(theme.color("input_bg")))
            p.drawRoundedRect(QRectF(x + 0.5, y + 0.5, tw - 1, th - 1),
                              th / 2 - 0.5, th / 2 - 0.5)

        d = th - 2 * self.PAD
        travel = tw - th
        cx = x + self.PAD + travel * self._knob
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 40))
        p.drawEllipse(QRectF(cx, y + self.PAD + 1.5, d, d))
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(QRectF(cx, y + self.PAD, d, d))
        p.end()


# ============================================================
# 分段选择器（自绘，指示块平滑滑动）
# ============================================================
class Segmented(QWidget):
    changed = Signal(object)
    PAD = 3

    def __init__(self, options, parent=None):
        super().__init__(parent)
        self._options = list(options)
        self._index = 0
        self._pos = 0.0
        self._anim = None
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(32)
        self.setMinimumWidth(58 * len(self._options) + 2 * self.PAD)

    def _get_pos(self):
        return self._pos

    def _set_pos(self, v):
        self._pos = float(v)
        self.update()

    pos = Property(float, _get_pos, _set_pos)

    def value(self):
        return self._options[self._index][1]

    def set_value(self, value, animate=False):
        idx = next((i for i, (_t, v) in enumerate(self._options)
                    if v == value), 0)
        if idx == self._index:
            return
        self._index = idx
        if not animate:
            self._stop_anim()
            self._pos = float(idx)
            self.update()
        else:
            self._animate_to(float(idx))

    def _animate_to(self, target):
        self._stop_anim()
        self._anim = QPropertyAnimation(self, b"pos", self)
        self._anim.setDuration(190)
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(target)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.start()

    def _stop_anim(self):
        if self._anim is not None:
            self._anim.stop()
            self._anim.deleteLater()
            self._anim = None

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton or not self._options:
            return
        n = len(self._options)
        seg_w = (self.width() - 2 * self.PAD) / n
        idx = int((event.position().x() - self.PAD) // seg_w)
        idx = max(0, min(n - 1, idx))
        if idx != self._index:
            self._index = idx
            self._animate_to(float(idx))
            self.changed.emit(self.value())

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        n = len(self._options)
        if n == 0:
            return
        w, h = self.width(), self.height()
        p.setPen(QPen(QColor(theme.color("border")), 1))
        p.setBrush(QColor(theme.color("input_bg")))
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 9, 9)

        seg_w = (w - 2 * self.PAD) / n
        ix = self.PAD + seg_w * self._pos
        ind = QRectF(ix, self.PAD, seg_w, h - 2 * self.PAD)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 24))
        p.drawRoundedRect(ind.translated(0, 1), 7, 7)
        p.setPen(QPen(QColor(theme.color("divider")), 1))
        p.setBrush(QColor(theme.color("window_bg")))
        p.drawRoundedRect(ind.adjusted(0.5, 0.5, -0.5, -0.5), 6.5, 6.5)

        f = QFont(self.font())
        f.setPixelSize(13)
        for i, (label, _v) in enumerate(self._options):
            f.setBold(i == self._index)
            p.setFont(f)
            p.setPen(QColor(theme.color("text") if i == self._index
                            else theme.color("sub_text")))
            p.drawText(QRectF(self.PAD + seg_w * i, 0, seg_w, h),
                       Qt.AlignCenter, str(label))
        p.end()


# ============================================================
# 左侧导航：彩色图标瓦片 + 矢量图标 + 选中指示条
# ============================================================
VECTOR_ICONS = {"gear", "palette", "island", "calendar", "market",
                "wrench", "plugin", "info"}

# emoji 字体回退链：QSS 字体不走 Qt 的自动字形回退，
# 导致 emoji 在自绘控件里渲染不出（只剩纯色瓦片），必须显式指定
EMOJI_FAMILIES = ["Segoe UI Emoji", "Segoe UI Symbol",
                  "Apple Color Emoji", "Noto Color Emoji"]


def draw_nav_icon(p, rect, name, tint):
    """在 rect 内绘制 1.6px 线性矢量图标（不依赖 emoji 字体）。"""
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(tint, max(1.5, rect.width() * 0.105),
               Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    w = rect.width()
    cx, cy = rect.center().x(), rect.center().y()
    u = w / 16.0                     # 以 16×16 为设计网格

    if name == "gear":               # 齿轮：外圈 + 内圈 + 8 齿
        r1, r2 = 5.0 * u, 1.9 * u
        p.drawEllipse(QRectF(cx - r1, cy - r1, 2 * r1, 2 * r1))
        p.drawEllipse(QRectF(cx - r2, cy - r2, 2 * r2, 2 * r2))
        for i in range(8):
            a = math.pi / 4 * i + math.pi / 8
            p.drawLine(QPointF(cx + math.cos(a) * (r1 + 0.4 * u),
                               cy + math.sin(a) * (r1 + 0.4 * u)),
                       QPointF(cx + math.cos(a) * (r1 + 1.7 * u),
                               cy + math.sin(a) * (r1 + 1.7 * u)))

    elif name == "palette":          # 主题：左半填充的圆
        r = 5.2 * u
        box = QRectF(cx - r, cy - r, 2 * r, 2 * r)
        p.drawEllipse(box)
        half = QRectF(box)
        path = QPainterPath()
        path.moveTo(cx, cy - r)
        path.arcTo(box, 90, 180)     # 左半圆
        path.closeSubpath()
        fill = QColor(tint)
        fill.setAlpha(150)
        p.setBrush(fill)
        p.setPen(Qt.NoPen)
        p.drawPath(path)

    elif name == "island":           # 灵动岛：胶囊 + 前置镜头点
        bw, bh = 12.4 * u, 5.6 * u
        p.drawRoundedRect(QRectF(cx - bw / 2, cy - bh / 2, bw, bh),
                          bh / 2, bh / 2)
        dot = 1.4 * u
        p.setBrush(tint)
        p.setPen(Qt.NoPen)
        p.drawEllipse(QRectF(cx + bw / 2 - 3.0 * u - dot / 2,
                             cy - dot / 2, dot, dot))

    elif name == "calendar":         # 日历
        bw, bh = 11.0 * u, 10.0 * u
        x0, y0 = cx - bw / 2, cy - bh / 2 + 0.6 * u
        p.drawRoundedRect(QRectF(x0, y0, bw, bh), 1.6 * u, 1.6 * u)
        p.drawLine(QPointF(x0, y0 + 3.0 * u), QPointF(x0 + bw, y0 + 3.0 * u))
        for dx in (-2.6 * u, 2.6 * u):
            p.drawLine(QPointF(cx + dx, y0 - 1.6 * u),
                       QPointF(cx + dx, y0 + 1.2 * u))
        d = 1.3 * u
        p.setBrush(tint)
        p.setPen(Qt.NoPen)
        p.drawEllipse(QRectF(cx - d / 2, y0 + 5.6 * u, d, d))

    elif name == "market":           # 商店：购物袋
        bw, bh = 10.4 * u, 8.6 * u
        x0, y0 = cx - bw / 2, cy - bh / 2 + 1.2 * u
        p.drawRoundedRect(QRectF(x0, y0, bw, bh), 1.8 * u, 1.8 * u)
        p.drawArc(QRectF(cx - 2.6 * u, y0 - 3.4 * u, 5.2 * u, 5.2 * u),
                  0, 180 * 16)

    elif name == "wrench":           # 高级：三根调谐滑杆
        for i, knob in enumerate((0.68, 0.32, 0.55)):
            yy = cy + (i - 1) * 3.6 * u
            p.drawLine(QPointF(cx - 5.6 * u, yy), QPointF(cx + 5.6 * u, yy))
            kx = cx - 5.6 * u + 11.2 * u * knob
            r = 1.6 * u
            p.setBrush(QColor(theme.color("window_bg")))
            p.setPen(pen)
            p.drawEllipse(QRectF(kx - r, yy - r, 2 * r, 2 * r))

    elif name == "plugin":           # 拼图：2×2 方块，右上为实心
        s = 4.6 * u
        gap = 1.4 * u
        for i in range(2):
            for j in range(2):
                x0 = cx - s - gap / 2 + j * (s + gap)
                y0 = cy - s - gap / 2 + i * (s + gap)
                r = QRectF(x0, y0, s, s)
                if i == 0 and j == 1:
                    fill = QColor(tint)
                    fill.setAlpha(170)
                    p.setBrush(fill)
                else:
                    p.setBrush(Qt.NoBrush)
                p.setPen(pen)
                p.drawRoundedRect(r, 1.2 * u, 1.2 * u)

    elif name == "box":              # 第三方包：纸箱
        bw, bh = 10.6 * u, 8.6 * u
        x0, y0 = cx - bw / 2, cy - bh / 2 + 0.8 * u
        p.drawRoundedRect(QRectF(x0, y0, bw, bh), 1.4 * u, 1.4 * u)
        p.drawLine(QPointF(x0, y0 + 2.6 * u), QPointF(x0 + bw, y0 + 2.6 * u))
        p.drawLine(QPointF(cx, y0), QPointF(cx, y0 + 2.6 * u))

    else:                            # info：圆圈 + i
        r = 5.4 * u
        p.drawEllipse(QRectF(cx - r, cy - r, 2 * r, 2 * r))
        d = 1.3 * u
        p.setBrush(tint)
        p.setPen(Qt.NoPen)
        p.drawEllipse(QRectF(cx - d / 2, cy - 3.2 * u, d, d))
        p.setPen(pen)
        p.drawLine(QPointF(cx, cy - 1.0 * u), QPointF(cx, cy + 3.2 * u))

    p.restore()


class NavItem(QAbstractButton):
    """自绘导航项：彩色圆角瓦片（矢量图标）+ 标题。"""

    H = 40
    TILE = 26
    TILE_X = 10
    TEXT_X = 46

    def __init__(self, icon, title, tint, parent=None):
        super().__init__(parent)
        self._icon = icon            # 矢量图标名（gear/palette/...）
        self._title = title
        self._tint = QColor(tint)
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setFixedHeight(self.H)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        checked = self.isChecked()

        # hover 底色（选中项的高亮块由 SideNav 的 pill 负责）
        if self.underMouse() and not checked:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.color("nav_hover")))
            p.drawRoundedRect(QRectF(0, 0, w, h), 8, 8)

        # 彩色图标瓦片
        ty = (h - self.TILE) / 2.0
        tile = QRectF(self.TILE_X, ty, self.TILE, self.TILE)
        tint = QColor(self._tint)
        tint.setAlpha(42 if not theme.is_dark() else 64)
        p.setPen(Qt.NoPen)
        p.setBrush(tint)
        p.drawRoundedRect(tile, 7, 7)

        # 图标：内置页用矢量图标；插件页用插件 API 提供的 emoji
        icon_rect = tile.adjusted(5, 5, -5, -5)
        if self._icon in VECTOR_ICONS:
            draw_nav_icon(p, icon_rect, self._icon, QColor(self._tint))
        else:
            f = QFont()
            f.setFamilies(EMOJI_FAMILIES + [self.font().family()])
            f.setPixelSize(14)
            p.setFont(f)
            p.setPen(QColor(theme.color("text")))
            p.drawText(tile, Qt.AlignCenter, self._icon)

        # 标题
        f = QFont(self.font())
        f.setPixelSize(13)
        f.setBold(checked)
        p.setFont(f)
        p.setPen(QColor(theme.color("accent") if checked
                        else theme.color("text")))
        p.drawText(QRectF(self.TEXT_X, 0, w - self.TEXT_X - 8, h),
                   Qt.AlignVCenter | Qt.AlignLeft, self._title)
        p.end()


class SideNav(QWidget):
    item_clicked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("v2Nav")
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(12, 4, 12, 4)
        self._lay.setSpacing(2)
        self._buttons = []
        self._groups = []

        self._pill = QFrame(self)
        self._pill.setObjectName("v2NavPill")
        self._bar = QFrame(self)
        self._bar.setObjectName("v2NavBar")
        self._pill_anim = None
        self.restyle()

    def add_group(self, title):
        lbl = QLabel(title, self)
        lbl.setObjectName("v2NavGroup")
        self._lay.addSpacing(12 if self._groups else 4)
        self._lay.addWidget(lbl)
        self._groups.append(lbl)

    def add_item(self, icon, title, tint="#0067c0"):
        idx = len(self._buttons)
        btn = NavItem(icon, title, tint, self)
        btn.clicked.connect(lambda _=False, i=idx: self.item_clicked.emit(i))
        self._lay.addWidget(btn)
        self._buttons.append(btn)
        return idx

    def finish(self):
        self._lay.addStretch(1)

    def count(self):
        return len(self._buttons)

    def items(self):
        return list(self._buttons)

    def restyle(self):
        self._pill.setStyleSheet(
            f"background:{theme.color('nav_checked_bg')};"
            "border:none;border-radius:8px;")
        self._bar.setStyleSheet(
            f"background:{theme.color('accent')};"
            "border:none;border-radius:2px;")
        for b in self._buttons:
            b.update()

    def select(self, idx, animate=True):
        if not (0 <= idx < len(self._buttons)):
            return
        btn = self._buttons[idx]
        btn.setChecked(True)
        target = btn.geometry()
        bar_target = self._bar_rect(target)
        self._pill.raise_()
        self._bar.raise_()
        for b in self._buttons:
            b.raise_()
        if self._pill_anim is not None:
            try:
                self._pill_anim.stop()
            except RuntimeError:
                pass
            self._pill_anim = None
        if not animate:
            self._pill.setGeometry(target)
            self._bar.setGeometry(bar_target)
            return
        self._pill_anim = QPropertyAnimation(self._pill, b"geometry", self)
        self._pill_anim.setDuration(190)
        self._pill_anim.setStartValue(self._pill.geometry())
        self._pill_anim.setEndValue(target)
        self._pill_anim.setEasingCurve(QEasingCurve.InOutCubic)
        self._pill_anim.start()
        bar_anim = QPropertyAnimation(self._bar, b"geometry", self)
        bar_anim.setDuration(190)
        bar_anim.setStartValue(self._bar.geometry())
        bar_anim.setEndValue(bar_target)
        bar_anim.setEasingCurve(QEasingCurve.InOutCubic)
        bar_anim.start(QAbstractAnimation.DeleteWhenStopped)

    @staticmethod
    def _bar_rect(btn_rect):
        return QRect(btn_rect.x() + 3, btn_rect.y() + 10,
                     3, btn_rect.height() - 20)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        idx = next((i for i, b in enumerate(self._buttons)
                    if b.isChecked()), 0)
        if self._buttons:
            g = self._buttons[idx].geometry()
            self._pill.setGeometry(g)
            self._bar.setGeometry(self._bar_rect(g))


# ============================================================
# 搜索框
# ============================================================
class SearchField(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("v2Search")
        self.setPlaceholderText("搜索设置")
        self.setClearButtonEnabled(True)


# ============================================================
# 卡片 / 设置行 / 操作行
# ============================================================
class Card(QFrame):
    """圆角卡片：标题 + 内容行，行间自动插发丝分隔线；带柔和投影。"""

    def __init__(self, title="", subtitle="", parent=None):
        super().__init__(parent)
        self.setObjectName("v2Card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 12)
        lay.setSpacing(0)
        self.body = lay
        self._row_count = 0
        if title:
            lbl = QLabel(title)
            lbl.setObjectName("v2CardTitle")
            lay.addWidget(lbl)
            if subtitle:
                sub = QLabel(subtitle)
                sub.setObjectName("hint")
                sub.setWordWrap(True)
                lay.addWidget(sub)
                lay.addSpacing(4)
            else:
                lay.addSpacing(2)
        elif subtitle:
            sub = QLabel(subtitle)
            sub.setObjectName("hint")
            sub.setWordWrap(True)
            lay.addWidget(sub)
            lay.addSpacing(4)

    def _divider(self):
        line = QFrame()
        line.setObjectName("v2Divider")
        line.setFixedHeight(1)
        return line

    def add_widget(self, w, divider=False):
        if divider and self._row_count > 0:
            self.body.addWidget(self._divider())
        self.body.addWidget(w)
        self._row_count += 1
        return w

    def add_row(self, w):
        return self.add_widget(w, divider=True)


class SettingRow:
    """一个设置项的描述（不含控件）。与旧版字段保持一致。"""

    def __init__(self, key, title, kind, *, hint="", options=None,
                 vmin=0, vmax=100, suffix="", decimals=0, step=None,
                 scale=1.0, get=None, setv=None, default=None, keywords=""):
        self.key = key
        self.title = title
        self.kind = kind
        self.hint = hint
        self.options = options or []
        self.vmin = vmin
        self.vmax = vmax
        self.suffix = suffix
        self.decimals = decimals
        self.step = step
        self.scale = scale
        self.getter = get
        self.setter = setv
        self.default = default
        self.keywords = keywords

    @property
    def has_default(self):
        if self.default is not None:
            return True
        return bool(self.key) and self.key in DEFAULTS

    def default_value(self):
        if self.default is not None:
            return self.default
        return DEFAULTS.get(self.key)


class RowWidget(QWidget):
    """设置项的一行。ctx 需提供 .settings 与 .on_row_change(row_widget)。"""

    def __init__(self, row, ctx, parent=None):
        super().__init__(parent)
        self.setObjectName("v2Row")
        self.row = row
        self.ctx = ctx
        self._loading = False
        self._flash_timer = None

        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 10, 2, 10)
        lay.setSpacing(20)

        left = QVBoxLayout()
        left.setSpacing(3)
        title = QLabel(row.title)
        title.setObjectName("v2RowTitle")
        left.addWidget(title)
        if row.hint:
            hint = QLabel(row.hint)
            hint.setObjectName("hint")
            hint.setWordWrap(True)
            left.addWidget(hint)
        lay.addLayout(left, 1)

        right = QHBoxLayout()
        right.setSpacing(8)
        self.control = self._build_control()
        right.addStretch(1)
        right.addWidget(self.control, 0, Qt.AlignVCenter)
        lay.addLayout(right, 0)

        self.search_text = " ".join((row.title, row.hint, row.keywords,
                                     str(row.key or ""))).lower()
        self.refresh()

    # ---------- 控件 ----------
    def _build_control(self):
        r = self.row
        if r.kind == "switch":
            w = Toggle()
            w.toggled.connect(lambda on: self._commit(bool(on)))
            return w

        if r.kind == "segmented":
            w = Segmented(r.options)
            w.changed.connect(lambda v: self._commit(v))
            return w

        if r.kind == "spin":
            w = QSpinBox()
            w.setRange(int(r.vmin), int(r.vmax))
            if r.step:
                w.setSingleStep(int(r.step))
            w.setSuffix(r.suffix)
            w.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            w.valueChanged.connect(
                lambda v: self._commit(v * r.scale if r.scale != 1.0 else v))
            return w

        if r.kind == "dspin":
            w = QDoubleSpinBox()
            w.setRange(float(r.vmin), float(r.vmax))
            w.setDecimals(r.decimals)
            if r.step:
                w.setSingleStep(float(r.step))
            w.setSuffix(r.suffix)
            w.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            w.valueChanged.connect(
                lambda v: self._commit(v * r.scale if r.scale != 1.0 else v))
            return w

        if r.kind == "slider":
            box = QWidget()
            bl = QHBoxLayout(box)
            bl.setContentsMargins(0, 0, 0, 0)
            bl.setSpacing(12)
            slider = QSlider(Qt.Horizontal)
            slider.setRange(int(r.vmin), int(r.vmax))
            slider.setSingleStep(int(r.step or 1))
            slider.setMinimumWidth(190)
            slider.setCursor(Qt.PointingHandCursor)
            val = QLabel()
            val.setMinimumWidth(48)
            val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            val.setObjectName("v2SliderVal")
            slider.valueChanged.connect(lambda v: self._on_slider(v))
            bl.addWidget(slider, 1)
            bl.addWidget(val)
            box._slider = slider
            box._label = val
            return box

        if r.kind == "combo":
            w = QComboBox()
            for text, data in r.options:
                w.addItem(text, data)
            w.currentIndexChanged.connect(
                lambda _=0: self._commit(w.currentData()))
            return w

        raise ValueError(f"未知控件类型: {r.kind}")

    # ---------- 读写 ----------
    def _read_stored(self):
        r = self.row
        if r.getter is not None:
            return r.getter()
        if not r.key:
            return r.default_value()
        return self.ctx.settings.get(r.key)

    def value(self):
        r = self.row
        c = self.control
        if r.kind == "switch":
            return bool(c.isChecked())
        if r.kind == "segmented":
            return c.value()
        if r.kind == "spin":
            raw = int(c.value())
        elif r.kind == "dspin":
            raw = float(c.value())
        elif r.kind == "slider":
            return float(c._slider.value()) * r.scale
        elif r.kind == "combo":
            return c.currentData()
        else:
            return None
        return raw * r.scale if r.scale != 1.0 else raw

    def _on_slider(self, v):
        self.control._label.setText(f"{int(v)}{self.row.suffix}")
        self._commit(v * self.row.scale)

    def _commit(self, value):
        if self._loading:
            return
        r = self.row
        if r.setter is not None:
            r.setter(value)
        elif r.key:
            self.ctx.settings[r.key] = value
        self.ctx.on_row_change(self)

    # ---------- 刷新 ----------
    def refresh(self):
        r = self.row
        value = self._read_stored()
        if value is None:
            value = r.default_value()
        self._loading = True
        try:
            c = self.control
            if r.kind == "switch":
                c.set_state(bool(value))
            elif r.kind == "segmented":
                c.set_value(value, animate=False)
            elif r.kind == "spin":
                c.setValue(int(round(float(value) / (r.scale or 1.0))))
            elif r.kind == "dspin":
                c.setValue(float(value) / (r.scale or 1.0))
            elif r.kind == "slider":
                iv = int(round(float(value) / (r.scale or 1.0)))
                iv = max(c._slider.minimum(), min(c._slider.maximum(), iv))
                c._slider.setValue(iv)
                c._label.setText(f"{iv}{r.suffix}")
            elif r.kind == "combo":
                idx = c.findData(value)
                if idx >= 0:
                    c.setCurrentIndex(idx)
        finally:
            self._loading = False

    def load_default(self):
        """恢复默认值并写回；返回是否有默认值。"""
        r = self.row
        if not r.has_default:
            return False
        value = r.default_value()
        if r.setter is not None:
            r.setter(value)
        elif r.key:
            self.ctx.settings[r.key] = value
        self.refresh()
        return True

    # ---------- 搜索定位高亮 ----------
    def flash(self):
        self.setProperty("flash", True)
        self.style().unpolish(self)
        self.style().polish(self)
        if self._flash_timer is not None:
            self._flash_timer.stop()
        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(self._unflash)
        self._flash_timer.start(1300)

    def _unflash(self):
        self.setProperty("flash", False)
        self.style().unpolish(self)
        self.style().polish(self)


class LinkRow(QAbstractButton):
    """「标题 + 说明 + ›」的可点击操作行（Win11 设置风格）。"""

    def __init__(self, title, hint="", danger=False, parent=None):
        super().__init__(parent)
        self.setObjectName("v2LinkRow")
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 10, 12, 10)
        lay.setSpacing(14)

        left = QVBoxLayout()
        left.setSpacing(3)
        t = QLabel(title)
        t.setObjectName("v2LinkDanger" if danger else "v2RowTitle")
        left.addWidget(t)
        if hint:
            s = QLabel(hint)
            s.setObjectName("hint")
            s.setWordWrap(True)
            left.addWidget(s)
        lay.addLayout(left, 1)

        arrow = QLabel("›")
        arrow.setObjectName("v2Chevron")
        lay.addWidget(arrow, 0, Qt.AlignVCenter)
        self.search_text = " ".join((title, hint)).lower()

    def paintEvent(self, _event):
        # QAbstractButton.paintEvent 是纯虚函数，必须自己画背景
        if self.isDown():
            bg = theme.color("pressed")
        elif self.underMouse():
            bg = theme.color("hover")
        else:
            bg = None
        if bg:
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(bg))
            p.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), 8, 8)
            p.end()


# ============================================================
# 导航图标瓦片配色（按分类）
# ============================================================
NAV_TINTS = {
    "通用": "#3b82f6",       # 蓝
    "外观": "#8b5cf6",       # 紫
    "灵动岛": "#14b8a6",     # 青
    "课表与提醒": "#f59e0b",  # 橙
    "插件市场": "#22c55e",   # 绿
    "第三方包管理": "#0ea5e9",  # 天蓝
    "高级": "#64748b",       # 灰蓝
    "关于": "#ec4899",       # 粉
}
PLUGIN_TINT = "#a855f7"      # 插件页默认紫


# ============================================================
# 设置窗口
# ============================================================
class SettingsDialog(QDialog):
    def __init__(self, settings, schedule_manager=None,
                 plugin_manager=None, controller=None, on_apply=None,
                 parent=None):
        super().__init__(parent)
        self.settings = settings
        self.schedule = schedule_manager
        self.plugin_manager = plugin_manager
        self.controller = controller
        self.on_apply = on_apply

        self.rows = []
        self.pages = []
        self.cards = []              # 所有卡片（主题切换时刷新投影）
        self._search_index = []
        self._search_hits = []
        self._opened = False
        self._test_seconds = int(self.settings.get("island_countdown_sec", 60))
        self.market_page = None
        self.package_page = None

        # Windows 11 云母（Mica）材质
        self.win11 = is_windows_11()
        self._mica_active = bool(self.win11 and
                                 self.settings.get("settings_mica", True))
        self._last_material_ok = False

        self.setObjectName("settingsV2")
        self.setWindowTitle("设置")
        self.resize(1020, 690)
        self.setMinimumSize(860, 570)
        _setup_dialog_style(self, translucent=self._mica_active)
        self._apply_qss()
        if self._mica_active:
            ok = apply_window_material(self, mica=True, dark=theme.is_dark())
            self._last_material_ok = ok
            if not ok:
                self._mica_active = False
                self.setAttribute(Qt.WA_TranslucentBackground, False)
                disable_mica(self)
                self._apply_qss()
        theme.theme_changed_connect(self._on_theme_changed)

        self._build_root()
        self._build_pages()
        self._build_nav()
        self._apply_card_shadows()

    # ==================================================
    # 样式
    # ==================================================
    def _apply_qss(self):
        self.setStyleSheet(_v2_qss(glass=self._mica_active))

    def _apply_card_shadows(self):
        alpha = 24 if not theme.is_dark() else 70
        for card in self.cards:
            try:
                eff = QGraphicsDropShadowEffect(card)
                eff.setBlurRadius(26)
                eff.setXOffset(0)
                eff.setYOffset(3)
                eff.setColor(QColor(0, 0, 0, alpha))
                card.setGraphicsEffect(eff)
            except RuntimeError:
                pass

    def _on_theme_changed(self):
        self._apply_qss()
        self.nav.restyle()
        self._apply_card_shadows()
        self._repolish(self)
        if self._mica_active:
            set_dark_titlebar(self, theme.is_dark())
        self.update()

    @staticmethod
    def _repolish(widget):
        try:
            for w in widget.findChildren(QWidget):
                w.style().unpolish(w)
                w.style().polish(w)
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        except Exception:
            pass

    # ==================================================
    # 骨架
    # ==================================================
    def _build_root(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.sidebar = self._build_sidebar()
        root.addWidget(self.sidebar)
        self.content = self._build_content()
        root.addWidget(self.content, 1)

    def _build_sidebar(self):
        bar = QFrame()
        bar.setObjectName("v2Sidebar")
        bar.setFixedWidth(268)
        lay = QVBoxLayout(bar)
        lay.setContentsMargins(16, 22, 16, 14)
        lay.setSpacing(12)

        # 品牌区：真实应用图标 + 名称
        brand = QHBoxLayout()
        brand.setSpacing(12)
        logo = QLabel()
        logo.setObjectName("v2BrandLogo")
        logo.setFixedSize(40, 40)
        logo.setAlignment(Qt.AlignCenter)
        pm = _app_pixmap(28)
        if pm is not None:
            logo.setPixmap(pm)
        else:
            logo.setText("🏫")
        brand.addWidget(logo)
        col = QVBoxLayout()
        col.setSpacing(1)
        t = QLabel(APP_NAME)
        t.setObjectName("v2BrandTitle")
        s = QLabel("设置")
        s.setObjectName("v2BrandSub")
        col.addWidget(t)
        col.addWidget(s)
        brand.addLayout(col)
        brand.addStretch(1)
        lay.addLayout(brand)
        lay.addSpacing(6)

        # 搜索
        self.search = SearchField()
        self.search.textChanged.connect(self._on_search)
        lay.addWidget(self.search)

        # 搜索结果（与导航二选一显示）
        self.results = QListWidget()
        self.results.setObjectName("v2Results")
        self.results.setFrameShape(QFrame.NoFrame)
        self.results.setMaximumHeight(320)
        self.results.itemClicked.connect(self._on_result_clicked)
        self.results.hide()
        lay.addWidget(self.results)

        # 导航
        self.nav_scroll = QScrollArea()
        self.nav_scroll.setObjectName("v2NavScroll")
        self.nav_scroll.setWidgetResizable(True)
        self.nav_scroll.setFrameShape(QFrame.NoFrame)
        self.nav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.nav = SideNav()
        self.nav.item_clicked.connect(self._select)
        self.nav_scroll.setWidget(self.nav)
        lay.addWidget(self.nav_scroll, 1)

        # 触屏：左侧导航也能手指上下滑
        setup_touch_scroll(self.nav_scroll, mouse_drag=True)

        # 版本
        ver = QLabel(f"v{get_version()}")
        ver.setObjectName("v2Version")
        lay.addWidget(ver)
        return bar

    def _build_content(self):
        wrap = QFrame()
        wrap.setObjectName("v2Content")
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.stack = AnimatedStack()
        lay.addWidget(self.stack, 1)

        footer = QFrame()
        footer.setObjectName("v2Footer")
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(32, 10, 32, 14)
        fl.setSpacing(12)
        self.btn_reset = QPushButton("本页恢复默认")
        self.btn_reset.setObjectName("ghost")
        self.btn_reset.setCursor(Qt.PointingHandCursor)
        self.btn_reset.clicked.connect(self._reset_current_page)
        fl.addWidget(self.btn_reset)
        self.saved_hint = QLabel("改动会立刻保存并生效")
        self.saved_hint.setObjectName("hint")
        fl.addWidget(self.saved_hint)
        fl.addStretch(1)
        btn_close = QPushButton("完成")
        btn_close.setObjectName("primary")
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.setMinimumWidth(96)
        btn_close.clicked.connect(self.accept)
        fl.addWidget(btn_close)
        lay.addWidget(footer)
        return wrap

    # ==================================================
    # 页面骨架
    # ==================================================
    def _make_page(self, title, subtitle):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(38, 28, 26, 8)
        v.setSpacing(6)

        t = QLabel(title)
        t.setObjectName("v2PageTitle")
        v.addWidget(t)
        page._title_lbl = t
        page._sub_lbl = None
        if subtitle:
            s = QLabel(subtitle)
            s.setObjectName("v2PageSub")
            s.setWordWrap(True)
            v.addWidget(s)
            page._sub_lbl = s
        v.addSpacing(12)

        scroll = QScrollArea()
        scroll.setObjectName("v2PageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        inner = QWidget()
        inner.setObjectName("v2PageInner")
        il = QVBoxLayout(inner)
        il.setContentsMargins(8, 6, 20, 24)
        il.setSpacing(18)
        il.setAlignment(Qt.AlignTop)
        scroll.setWidget(inner)
        v.addWidget(scroll, 1)

        # 触屏：页面内容手指拖拽 + 惯性滑动
        # 页面里有滑杆 / 开关这类要拖的控件，鼠标左键手势就不开了，
        # 免得和它们抢拖拽；触摸（TouchGesture）不受影响照样能滑。
        setup_touch_scroll(scroll, mouse_drag=False)

        page._inner = inner
        page._inner_layout = il
        page._scroll = scroll
        page._anim = []
        page._info = {"icon": "", "title": title, "sub": subtitle,
                      "widget": page, "anim": page._anim, "index": -1,
                      "group": "", "tint": "#0067c0"}
        return page

    def _add_page(self, icon, title, page, subtitle="", group=""):
        info = page._info
        info["icon"] = icon
        info["title"] = title
        if subtitle:
            info["sub"] = subtitle
        info["group"] = group
        info["tint"] = NAV_TINTS.get(title, PLUGIN_TINT)
        info["index"] = len(self.pages)
        self.pages.append(info)
        self.stack.add_page(page)
        self._register_search(title, info, None, title)
        return info

    def _add_card(self, page, title="", subtitle=""):
        card = Card(title, subtitle)
        page._inner_layout.addWidget(card)
        page._anim.append(card)
        self.cards.append(card)
        return card

    def _add_rows(self, page, card, specs):
        for spec in specs:
            rw = RowWidget(spec, self)
            rw._page_info = page._info
            card.add_row(rw)
            self.rows.append(rw)
            self._register_search(rw.search_text, page._info, rw, spec.title)
        return card

    def _add_link(self, page, card, title, hint, cb, danger=False):
        row = LinkRow(title, hint, danger=danger)
        row.clicked.connect(cb)
        card.add_row(row)
        self._register_search(row.search_text, page._info, None, title)
        return row

    # ==================================================
    # 页面内容
    # ==================================================
    def _build_pages(self):
        self._page_general()
        self._page_appearance()
        self._page_island()
        self._page_schedule()
        self._page_market()
        self._page_packages()
        self._page_advanced()
        self._add_plugin_pages()
        self._page_about()

    # ---------- 通用 ----------
    def _page_general(self):
        page = self._make_page("通用", "主窗口显示、作业滚动与更新检查")
        card = self._add_card(page, "主窗口")
        self._add_rows(page, card, [
            SettingRow("show_main_window", "显示班级日常窗口", "switch",
                       hint="关掉之后，托盘菜单里还能再打开"),
            SettingRow("main_width_ratio", "窗口宽度", "slider",
                       vmin=15, vmax=50, suffix="%", scale=0.01,
                       hint="占屏幕宽度的百分之多少"),
            SettingRow("main_opacity", "窗口透明度", "slider",
                       vmin=0, vmax=100, suffix="%", scale=0.01,
                       hint="设为 0 表示完全透明"),
            SettingRow("main_font_size", "正文字号", "spin",
                       vmin=8, vmax=30, suffix=" px"),
        ])
        card = self._add_card(page, "作业滚动")
        self._add_rows(page, card, [
            SettingRow("main_auto_scroll", "自动滚动作业", "switch"),
            SettingRow("main_scroll_interval", "滚动间隔", "spin",
                       vmin=20, vmax=200, suffix=" ms"),
            SettingRow("main_scroll_step", "每步滚动距离", "spin",
                       vmin=1, vmax=10, suffix=" px"),
            SettingRow("main_scroll_pause", "到底暂停", "spin",
                       vmin=0, vmax=200, suffix=" 次"),
        ])
        card = self._add_card(page, "启动与更新")
        self._add_rows(page, card, [
            SettingRow("check_update_on_start", "启动时检查更新", "switch",
                       hint="由独立更新器处理，可随时手动检查"),
        ])
        self._add_page("gear", "通用", page, "主窗口显示、作业滚动与更新检查",
                       group="基本")

    # ---------- 外观 ----------
    def _page_appearance(self):
        page = self._make_page("外观", "主题、动画与窗口材质")
        card = self._add_card(page, "颜色主题")
        self._add_rows(page, card, [
            SettingRow("theme_mode", "颜色模式", "segmented",
                       options=[("跟随系统", "system"), ("浅色", "light"),
                                ("深色", "dark")],
                       get=lambda: self.settings.get("theme_mode", "system"),
                       setv=self._set_theme, default="system"),
        ])
        card = self._add_card(page, "淡入淡出")
        self._add_rows(page, card, [
            SettingRow("anim_fade_window", "窗口打开时渐显", "switch"),
            SettingRow("anim_fade_panel", "面板展开时渐显", "switch"),
            SettingRow("anim_fade_text", "文字变化时渐显", "switch"),
            SettingRow("anim_duration", "动画时长", "spin",
                       vmin=100, vmax=2000, step=50, suffix=" ms"),
        ])

        card = self._add_card(page, "窗口材质",
                              f"当前系统：{windows_display_name()}")
        if self.win11:
            self._add_rows(page, card, [
                SettingRow("settings_mica", "云母材质（Mica）", "switch",
                           hint="Windows 11 的半透明云母背板，会跟着系统明暗变",
                           get=lambda: self.settings.get("settings_mica", True),
                           setv=self._set_mica),
            ])
        else:
            lbl = QLabel("云母材质需要 Windows 11，当前系统使用普通窗口。")
            lbl.setObjectName("hint")
            lbl.setWordWrap(True)
            card.add_widget(lbl)
        self._add_page("palette", "外观", page, "主题、动画与窗口材质",
                       group="基本")

    # ---------- 灵动岛 ----------
    def _page_island(self):
        page = self._make_page("灵动岛", "灵动岛与副岛的显示和动画")
        card = self._add_card(page, "主岛")
        self._add_rows(page, card, [
            SettingRow("show_island", "显示灵动岛", "switch"),
            SettingRow("island_top_margin", "距屏幕顶部距离", "spin",
                       vmin=0, vmax=100, suffix=" px"),
            SettingRow("island_alert_width", "提醒条宽度", "spin",
                       vmin=200, vmax=800, suffix=" px"),
            SettingRow("island_alert_hold_ms", "提醒条停留", "spin",
                       vmin=100, vmax=5000, step=50, suffix=" ms"),
            SettingRow("island_hide_on_fullscreen", "仅全屏时隐藏", "switch"),
            SettingRow("island_show_wakeup_anim", "启用唤醒动画", "switch",
                       hint="收起时为圆形，展开后为胶囊"),
        ])
        card = self._add_card(page, "副岛")
        self._add_rows(page, card, [
            SettingRow("show_sub_island", "显示副岛", "switch",
                       hint="显示在主岛右侧"),
            SettingRow("sub_island_collapsed", "默认收成圆形", "switch"),
            SettingRow("sub_island_auto_collapse_sec", "无内容自动收起",
                       "spin", vmin=0, vmax=120, suffix=" 秒",
                       hint="设为 0 表示不自动收起"),
        ])
        self._add_page("island", "灵动岛", page, "灵动岛与副岛的显示和动画",
                       group="基本")

    # ---------- 课表与提醒 ----------
    def _page_schedule(self):
        page = self._make_page("课表与提醒", "上课提醒、时间校准与课表工具")

        card = self._add_card(page, "上课提醒")
        specs = [
            SettingRow("island_countdown_sec", "倒计时时长", "spin",
                       vmin=5, vmax=600, suffix=" 秒",
                       hint="上课前显示蓝色倒计时"),
        ]
        if self.schedule is not None:
            specs.insert(0, SettingRow(
                "", "提前提醒", "spin", vmin=0, vmax=60, suffix=" 分钟",
                get=lambda: int(self.schedule.advance_minutes),
                setv=lambda v: self.schedule.set_advance_minutes(int(v)),
                default=2,
                hint="整体提前几分钟进上课状态（下课时间不变）"))
            specs.append(SettingRow(
                "", "时间偏移", "spin", vmin=-1800, vmax=1800, suffix=" 秒",
                get=lambda: int(self.schedule.time_offset_seconds),
                setv=lambda v: self.schedule.set_time_offset_seconds(int(v)),
                default=0,
                hint="负数为提前，正数为延后"))
        self._add_rows(page, card, specs)

        card = self._add_card(page, "课表与值日",
                              "管理多张课表、导入导出与假期安排")
        self._add_link(page, card, "值日生名单", "设置值日轮流安排",
                       self._open_duty)
        self._add_link(page, card, "课表编辑器", "调整课表与上课时间",
                       self._open_course)
        self._add_link(page, card, "课表管理", "切换、备份与导入导出课表",
                       self._open_timetable_manager)
        self._add_link(page, card, "假期与调休", "设置假期与调休日",
                       self._open_holidays)
        self._add_link(page, card, "周末作息", "单独设置周末上课时间",
                       self._open_weekend)

        card = self._add_card(page, "灵动岛测试", "在灵动岛上演示倒计时与状态")
        self._add_rows(page, card, [
            SettingRow("", "测试时长", "spin", vmin=3, vmax=600,
                       suffix=" 秒", default=self._test_seconds,
                       get=lambda: self._test_seconds,
                       setv=lambda v: setattr(self, "_test_seconds", int(v)),
                       hint="只是演示用，不影响真实的上课时间"),
        ])
        self._add_link(page, card, "倒计时演示", "立即在灵动岛演示一次倒计时",
                       self._test_countdown)
        self._add_link(page, card, "状态测试…", "完整演示一节课的状态变化",
                       self._open_status_test)
        self._add_page("calendar", "课表与提醒", page, "上课提醒、时间校准与课表工具",
                       group="课程")

    # ---------- 插件市场 ----------
    def _page_market(self):
        page = self._make_page(
            "插件市场", "从远程仓库安装与更新插件")
        if self.plugin_manager is None:
            card = self._add_card(page, "插件系统未启用")
            lbl = QLabel("插件管理器不可用，插件市场暂不可用。")
            lbl.setObjectName("hint")
            lbl.setWordWrap(True)
            card.add_widget(lbl)
            self._add_page("🧩", "插件市场", page, "插件系统未启用",
                           group="扩展")
            return

        from market_page import MarketPage
        holder = QWidget()
        hl = QVBoxLayout(holder)
        hl.setContentsMargins(0, 0, 0, 0)
        self.market_page = MarketPage(self.plugin_manager, self.settings)
        self.market_page.setObjectName("v2PageInner")
        hl.addWidget(self.market_page, 1)
        holder.setProperty("noUnfold", True)
        page._inner_layout.addWidget(holder, 1)
        page._anim.append(holder)
        self._add_page("market", "插件市场", page, "从远程仓库安装与更新插件",
                       group="扩展")

    # ---------- 第三方包管理 ----------
    def _page_packages(self):
        page = self._make_page(
            "第三方包管理", "插件依赖的第三方包：下载源、使用者与安装")
        if self.plugin_manager is None:
            card = self._add_card(page, "插件系统未启用")
            lbl = QLabel("插件管理器不可用，第三方包管理暂不可用。")
            lbl.setObjectName("hint")
            lbl.setWordWrap(True)
            card.add_widget(lbl)
            self._add_page("box", "第三方包管理", page, "插件系统未启用",
                           group="扩展")
            return

        from package_page import PackagePage
        holder = QWidget()
        hl = QVBoxLayout(holder)
        hl.setContentsMargins(0, 0, 0, 0)
        self.package_page = PackagePage(self.plugin_manager, self.settings)
        self.package_page.setObjectName("v2PageInner")
        hl.addWidget(self.package_page, 1)
        holder.setProperty("noUnfold", True)
        page._inner_layout.addWidget(holder, 1)
        page._anim.append(holder)
        self._add_page("box", "第三方包管理", page,
                       "插件依赖的第三方包：下载源、使用者与安装",
                       group="扩展")

    # ---------- 高级 ----------
    def _page_advanced(self):
        page = self._make_page("高级", "本地插件和日常维护")
        card = self._add_card(page, "本地插件", "程序启动时会加载这些插件")
        text = self._local_plugins_text()
        lbl = QLabel(text)
        lbl.setObjectName("hint")
        lbl.setWordWrap(True)
        lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        card.add_widget(lbl)
        self._add_link(page, card, "安装本地插件…", "从 .cblplugin 文件安装",
                       self._import_plugin)
        self._add_link(page, card, "打开插件文件夹", "在文件资源管理器中打开",
                       self._open_plugins_dir)

        card = self._add_card(page, "日常维护")
        self._add_link(page, card, "打开配置文件夹", "查看 settings.json 等配置文件",
                       self._open_config_dir)
        self._add_link(page, card, "恢复全部默认", "将所有设置恢复为默认值",
                       self._reset_all, danger=True)
        self._add_page("wrench", "高级", page, "本地插件和维护", group="扩展")

    # ---------- 插件设置页 ----------
    def _add_plugin_pages(self):
        if self.plugin_manager is None:
            return
        try:
            pages = self.plugin_manager.get_settings_pages()
        except Exception:
            pages = []
        for entry in pages:
            title = str(entry.get("title", "插件设置"))
            # 插件 API 提供的 emoji 图标原样显示；默认 🧩 用矢量拼图图标
            icon = entry.get("icon") or "plugin"
            if icon == "🧩":
                icon = "plugin"
            try:
                content = entry["factory"](entry.get("api"))
            except Exception as e:
                content = QLabel(f"插件设置加载失败：{e}")
                content.setObjectName("hint")
                content.setWordWrap(True)
            page = self._make_page(title, "插件自己带来的设置页")
            card = self._add_card(page)
            if content is not None:
                card.add_widget(content)
            self._add_page(icon, title, page, "插件页", group="扩展")

    # ---------- 关于 ----------
    def _page_about(self):
        page = self._make_page("关于", "版本与更新")
        card = self._add_card(page)

        head = QHBoxLayout()
        head.setSpacing(14)
        logo = QLabel()
        logo.setObjectName("v2AboutLogo")
        logo.setFixedSize(56, 56)
        logo.setAlignment(Qt.AlignCenter)
        pm = _app_pixmap(40)
        if pm is not None:
            logo.setPixmap(pm)
        else:
            logo.setText("🏫")
        head.addWidget(logo)
        col = QVBoxLayout()
        col.setSpacing(3)
        title = QLabel(APP_NAME)
        title.setObjectName("v2AboutTitle")
        ver = QLabel(f"版本 {get_version()}")
        ver.setObjectName("v2AboutVer")
        col.addWidget(title)
        col.addWidget(ver)
        head.addLayout(col)
        head.addStretch(1)
        holder = QWidget()
        holder.setLayout(head)
        card.add_widget(holder)

        for text in ("一个轻量级的班级日常管理小工具",
                     "作者：LCHXXXX、hexwisp72",
                     "反馈：2352240265@qq.com",
                     f"系统：{windows_display_name()}",
                     ("窗口材质：Windows 11 云母（Mica）"
                      if self._mica_active else "窗口材质：普通")):
            lbl = QLabel(text)
            lbl.setObjectName("hint")
            lbl.setWordWrap(True)
            card.add_widget(lbl)

        btn = QPushButton("检查更新")
        btn.setObjectName("primary")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setMinimumWidth(110)
        btn.clicked.connect(self._open_updater)
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 8, 0, 2)
        btn_row.addWidget(btn)
        btn_row.addStretch(1)
        btn_holder = QWidget()
        btn_holder.setLayout(btn_row)
        card.add_widget(btn_holder)
        self._add_page("info", "关于", page, "版本与更新", group="更多")

    # ==================================================
    # 导航
    # ==================================================
    def _build_nav(self):
        last_group = None
        for p in self.pages:
            if p["group"] != last_group:
                last_group = p["group"]
                self.nav.add_group(last_group)
            self.nav.add_item(p["icon"], p["title"], p["tint"])
        self.nav.finish()

    def _select(self, idx, animate=True):
        idx = max(0, min(len(self.pages) - 1, int(idx)))
        smooth = bool(animate and self._opened)
        self.stack.set_current(idx, animate=smooth)
        self.nav.select(idx, animate=smooth)
        self.btn_reset.setEnabled(bool(self._page_rows(self.pages[idx])))

    def _page_rows(self, page_info):
        return [r for r in self.rows
                if getattr(r, "_page_info", None) is page_info]

    # ==================================================
    # 搜索
    # ==================================================
    def _register_search(self, text, page_info, widget, label):
        self._search_index.append({
            "text": str(text).lower(),
            "page": page_info,
            "widget": widget,
            "label": label,
        })

    def _on_search(self, text):
        q = text.strip().lower()
        if not q:
            self.results.hide()
            self.nav_scroll.show()
            return
        self._search_hits = [e for e in self._search_index
                             if q in e["text"]][:60]
        self.results.clear()
        if not self._search_hits:
            it = QListWidgetItem("未找到匹配的设置项")
            it.setFlags(Qt.NoItemFlags)
            self.results.addItem(it)
        else:
            for i, e in enumerate(self._search_hits):
                item = QListWidgetItem(f"{e['label']}    ·    "
                                       f"{e['page']['title']}")
                item.setData(Qt.UserRole, i)
                self.results.addItem(item)
        self.nav_scroll.hide()
        self.results.show()
        StaggerPlayer.fade(self.results, duration=160, delay=0)

    def _on_result_clicked(self, item):
        i = item.data(Qt.UserRole)
        if i is None or not (0 <= i < len(self._search_hits)):
            return
        e = self._search_hits[i]
        self._goto(e)

    def _goto(self, entry):
        page = entry["page"]
        self._select(page["index"])
        widget = entry["widget"]
        if widget is None:
            return

        def _scroll():
            try:
                inner = page["widget"]._inner
                y = widget.mapTo(inner, QPoint(0, 0)).y()
                bar = page["widget"]._scroll.verticalScrollBar()
                bar.setValue(max(0, y - 24))
                if isinstance(widget, RowWidget):
                    widget.flash()
            except RuntimeError:
                pass

        QTimer.singleShot(120, self, _scroll)

    # ==================================================
    # 设置写入
    # ==================================================
    def on_row_change(self, row_widget):
        if row_widget.row.key == "theme_mode":
            return
        self._apply()

    def _apply(self):
        try:
            self.settings.save()
        except Exception:
            pass
        if self.controller is not None:
            try:
                self.controller.apply_settings()
            except Exception:
                pass
        elif self.on_apply is not None:
            try:
                self.on_apply()
            except Exception:
                pass

    def _set_theme(self, value):
        self.settings["theme_mode"] = str(value)
        self._apply()
        app = QApplication.instance()
        if app is not None:
            theme.apply_theme(app)

    # ==================================================
    # Windows 11 云母材质
    # ==================================================
    def _set_mica(self, value):
        value = bool(value)
        self.settings["settings_mica"] = value
        want = bool(value and self.win11)
        if want == self._mica_active:
            return

        was_visible = self.isVisible()
        if was_visible:
            self.hide()

        self.setAttribute(Qt.WA_TranslucentBackground, want)
        self._mica_active = bool(want)
        flags = self.windowFlags()
        self.setWindowFlags(flags ^ Qt.WindowStaysOnTopHint)
        self.setWindowFlags(flags)

        ok = False
        if want:
            ok = apply_window_material(self, mica=True, dark=theme.is_dark())
            if not ok:
                self._mica_active = False
                self.setAttribute(Qt.WA_TranslucentBackground, False)
                disable_mica(self)
                self.win11 = False
                flags = self.windowFlags()
                self.setWindowFlags(flags ^ Qt.WindowStaysOnTopHint)
                self.setWindowFlags(flags)
        else:
            disable_mica(self)

        if was_visible:
            self.show()
        self._apply_qss()
        self._repolish(self)
        self._flash_hint("已开启云母材质" if self._mica_active
                         else "已关闭云母材质")

    # ==================================================
    # 恢复默认
    # ==================================================
    def _reset_current_page(self):
        idx = self.stack.current_index()
        if not (0 <= idx < len(self.pages)):
            return
        page = self.pages[idx]
        changed = False
        for rw in self._page_rows(page):
            changed = rw.load_default() or changed
        if changed:
            self._apply()
            self._flash_hint("本页已恢复默认")

    def _reset_all(self):
        if QMessageBox.question(
                self, "恢复默认",
                "确定要将所有设置恢复为默认值吗？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No) != QMessageBox.Yes:
            return
        for rw in self.rows:
            rw.load_default()
        self._apply()
        self._flash_hint("所有设置已恢复默认")

    def _flash_hint(self, text):
        self.saved_hint.setText(text)
        QTimer.singleShot(2500, self,
                          lambda: self.saved_hint.setText("改动会立刻保存并生效"))

    # ==================================================
    # 操作入口
    # ==================================================
    def _open_duty(self):
        if self.controller is not None and self.controller.window is not None:
            self.controller.window.edit_duty()

    def _open_course(self):
        if self.schedule is None:
            return
        import menu as menu_mod
        dlg = menu_mod.CourseEditor(self.schedule, self)
        if dlg.exec():
            self._notify_island()

    def _open_holidays(self):
        if self.schedule is None:
            return
        import menu as menu_mod
        menu_mod.HolidayDialog(self.schedule, self).exec()
        self._notify_island()

    def _open_weekend(self):
        if self.schedule is None:
            return
        import menu as menu_mod
        menu_mod.WeekendScheduleDialog(self.schedule, self).exec()
        self._notify_island()

    def _open_timetable_manager(self):
        if self.schedule is None:
            return
        import menu as menu_mod
        dlg = menu_mod.TimetableManagerDialog(
            self.schedule, on_change=self._notify_island, parent=self)
        dlg.exec()
        self._notify_island()

    def _test_countdown(self):
        if self.controller is None:
            QMessageBox.information(self, "提示", "灵动岛不可用，无法演示。")
            return
        self.controller.test_countdown(int(self._test_seconds))

    def _open_status_test(self):
        if self.schedule is None:
            return
        from test_dialog import StatusTestDialog
        StatusTestDialog(self.schedule, self.settings, self.controller,
                         self).exec()

    def _import_plugin(self):
        if self.plugin_manager is None:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "选择插件文件", "",
            f"{APP_NAME} 插件 (*.cblplugin);;所有文件 (*)")
        if not path:
            return
        import shutil
        target = os.path.join(self.plugin_manager.plugins_dir,
                              os.path.basename(path))
        try:
            shutil.copy(path, target)
        except Exception as e:
            QMessageBox.critical(self, "安装失败", f"复制文件失败：{e}")
            return
        QMessageBox.information(self, "安装完成",
                                f"{os.path.basename(path)} 已安装，重启后生效。")

    def _open_plugins_dir(self):
        if self.plugin_manager is None:
            return
        d = self.plugin_manager.plugins_dir
        if os.path.isdir(d):
            os.startfile(d)

    def _open_config_dir(self):
        d = os.path.dirname(self.settings.path)
        if os.path.isdir(d):
            os.startfile(d)

    def _open_updater(self):
        from launch_updater import launch_visible
        ok, msg = launch_visible()
        if not ok:
            QMessageBox.warning(self, "更新", msg)

    def _notify_island(self):
        if self.controller is not None:
            self.controller.notify_island_dirty()

    def _local_plugins_text(self):
        if self.plugin_manager is None:
            return "（插件系统还没启用）"
        loaded = list(getattr(self.plugin_manager, "loaded", []) or [])
        if not loaded:
            return "（还没有插件）"
        lines = []
        for name, ok, msg in loaded:
            mark = "✓" if ok else "✗"
            lines.append(f"{mark}  {name}    {msg}")
        return "\n".join(lines)

    # ==================================================
    # 入场 / 关闭
    # ==================================================
    def showEvent(self, event):
        if not self._opened and not self._mica_active:
            self.setWindowOpacity(0.0)
        super().showEvent(event)
        if self._mica_active:
            ok = apply_window_material(self, mica=True, dark=theme.is_dark())
            self._last_material_ok = ok
            if not ok:
                self._mica_active = False
                self.setAttribute(Qt.WA_TranslucentBackground, False)
                disable_mica(self)
                self.setWindowOpacity(1.0)
                self._apply_qss()
        if not self._opened:
            self._opened = True
            QTimer.singleShot(30, self, self._play_open)

    def _play_open(self):
        if not self._mica_active:
            self._fade_window()
        # 导航逐条淡入 + 首页整页淡入上滑
        StaggerPlayer(duration=200, step=36, delay=110).play(self.nav.items())
        self.stack.set_current(0, animate=True)
        self.nav.select(0, animate=False)
        if self.pages:
            self.btn_reset.setEnabled(bool(self._page_rows(self.pages[0])))

    def _fade_window(self):
        a = QPropertyAnimation(self, b"windowOpacity", self)
        a.setDuration(170)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.setEasingCurve(QEasingCurve.OutCubic)
        a.start(QAbstractAnimation.DeleteWhenStopped)

    def closeEvent(self, event):
        if self.market_page is not None:
            try:
                self.market_page.shutdown()
            except Exception:
                pass
        if self.package_page is not None:
            try:
                self.package_page.shutdown()
            except Exception:
                pass
        super().closeEvent(event)


# ============================================================
# 样式表（浅色 / 深色 / 云母 全适配）
# ============================================================
def _v2_qss(glass=False):
    c = theme.PALETTES[theme.current()]
    if glass:
        win = _rgba(c['window_bg'], 0.45)
        bg = "transparent"
        sidebar = _rgba(c['sidebar_bg'], 0.55)
        card = _rgba(c['card_bg'], 0.88)
        card2 = _rgba(c['card_bg_2'], 0.85)
        card_hover = _rgba(c['card_hover'], 0.92)
        inp = _rgba(c['input_bg'], 0.92)
        hover = _rgba(c['hover'], 0.85)
    else:
        win = c['window_bg']
        bg = c['window_bg']
        sidebar = c['sidebar_bg']
        card = c['card_bg']
        card2 = c['card_bg_2']
        card_hover = c['card_hover']
        inp = c['input_bg']
        hover = c['hover']
    return f"""
QDialog#settingsV2 {{
    background: {win};
    font-family: "Segoe UI Variable Text", "Segoe UI", "Microsoft YaHei UI";
}}
QLabel {{ color: {c['text']}; background: transparent; }}
QLabel#hint {{ font-size: 12px; color: {c['hint']}; }}

/* ---------- 侧栏 ---------- */
QFrame#v2Sidebar {{
    background: {sidebar}; border: none;
    border-right: 1px solid {c['divider']};
}}
QLabel#v2BrandLogo {{
    background: {c['accent_soft']}; border-radius: 11px; font-size: 21px;
}}
QLabel#v2BrandTitle {{ font-size: 15px; font-weight: 700; color: {c['text']}; }}
QLabel#v2BrandSub {{ font-size: 11px; color: {c['hint']}; }}
QLabel#v2Version {{ font-size: 11px; color: {c['hint']}; padding-left: 14px; }}

QLineEdit#v2Search {{
    background: {inp}; border: 1px solid {c['border']};
    border-radius: 9px; padding: 8px 12px; font-size: 13px;
    color: {c['text']};
}}
QLineEdit#v2Search:hover {{ border: 1px solid {c['hint']}; }}
QLineEdit#v2Search:focus {{ border: 1px solid {c['accent']}; }}

QListWidget#v2Results {{
    background: {card}; border: 1px solid {c['border']};
    border-radius: 10px; outline: none; padding: 4px;
}}
QListWidget#v2Results::item {{
    padding: 8px 10px; border-radius: 6px; color: {c['text']};
}}
QListWidget#v2Results::item:hover {{ background: {hover}; }}
QListWidget#v2Results::item:selected {{
    background: {c['accent_soft']}; color: {c['accent']};
}}

QScrollArea#v2NavScroll {{ background: transparent; border: none; }}
QScrollArea#v2NavScroll > QWidget {{ background: transparent; }}
QWidget#v2Nav {{ background: transparent; }}
QLabel#v2NavGroup {{
    font-size: 11px; font-weight: 600; color: {c['hint']};
    padding-left: 12px; padding-top: 4px; padding-bottom: 3px;
}}

/* ---------- 内容区 ---------- */
QWidget#v2Content {{ background: {bg}; }}
QWidget#v2Stack {{ background: {bg}; }}
QScrollArea#v2PageScroll {{ background: {bg}; border: none; }}
QScrollArea#v2PageScroll > QWidget {{ background: {bg}; }}
QWidget#v2PageInner {{ background: {bg}; }}
QScrollArea#marketScroll {{ background: {bg}; border: none; }}
QScrollArea#marketScroll > QWidget {{ background: {bg}; }}
QLabel#v2PageTitle {{ font-size: 27px; font-weight: 700; color: {c['text']}; }}
QLabel#v2PageSub {{ font-size: 12px; color: {c['hint']}; }}

QFrame#v2Footer {{
    background: {bg}; border: none;
    border-top: 1px solid {c['divider']};
}}

/* ---------- 卡片 ---------- */
QFrame#v2Card {{
    background: {card}; border: 1px solid {c['divider']};
    border-radius: 14px;
}}
QLabel#v2CardTitle {{
    font-size: 13px; font-weight: 600; color: {c['text']};
    padding-bottom: 2px;
}}
QFrame#v2Divider {{ background: {c['divider']}; border: none; }}

/* ---------- 设置行 ---------- */
QWidget#v2Row {{ background: transparent; border-radius: 8px; }}
QWidget#v2Row[flash="true"] {{ background: {c['accent_soft']}; }}
QLabel#v2RowTitle {{ font-size: 13px; color: {c['text']}; }}
QLabel#v2SliderVal {{ font-size: 13px; color: {c['text']}; }}

/* ---------- 操作行（列表项 + ›，背景由 paintEvent 自绘） ---------- */
QLabel#v2LinkDanger {{ font-size: 13px; color: {c['danger']}; }}
QLabel#v2Chevron {{ font-size: 18px; color: {c['hint']}; }}

/* ---------- 输入控件 ---------- */
QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {inp}; border: 1px solid {c['border']};
    border-radius: 8px; padding: 6px 10px; min-width: 118px;
    color: {c['text']}; font-size: 13px;
}}
QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover {{
    border: 1px solid {c['hint']};
}}
QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border: 1px solid {c['accent']};
}}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{ width: 0; }}
QComboBox QAbstractItemView {{
    background: {inp}; color: {c['text']};
    border: 1px solid {c['border']};
    selection-background-color: {c['accent']}; selection-color: #ffffff;
}}
QLineEdit {{
    background: {inp}; border: 1px solid {c['border']};
    border-radius: 8px; padding: 6px 10px; color: {c['text']};
    font-size: 13px;
}}
QLineEdit:focus {{ border: 1px solid {c['accent']}; }}
QDateEdit, QDateTimeEdit {{
    background: {inp}; border: 1px solid {c['border']};
    border-radius: 8px; padding: 5px 9px; color: {c['text']};
    font-size: 13px;
}}

QSlider::groove:horizontal {{
    height: 4px; background: {c['border']}; border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: {c['accent']}; border-radius: 2px;
}}
QSlider::handle:horizontal {{
    width: 18px; height: 18px; margin: -7px 0;
    border-radius: 9px; background: #ffffff;
    border: 2px solid {c['accent']};
}}
QSlider::handle:horizontal:hover {{ background: {c['accent_soft']}; }}

/* ---------- 按钮 ---------- */
QPushButton {{
    background: {inp}; border: 1px solid {c['border']};
    border-radius: 8px; padding: 7px 18px; font-size: 13px;
    color: {c['text']};
}}
QPushButton:hover {{ background: {hover}; }}
QPushButton:pressed {{ background: {c['pressed']}; }}
QPushButton:disabled {{ color: {c['hint']}; }}
QPushButton#primary {{
    background: {c['accent']}; color: #ffffff;
    border: none; font-weight: 600;
}}
QPushButton#primary:hover {{ background: {c['accent_hover']}; }}
QPushButton#primary:pressed {{ background: {c['accent']}; }}
QPushButton#ghost {{
    background: transparent; border: none;
    color: {c['hint']}; padding: 7px 10px;
}}
QPushButton#ghost:hover {{ color: {c['text']}; background: transparent; }}
QPushButton[cardAction="true"] {{ padding: 5px 14px; font-size: 12px; }}

/* ---------- 关于页 ---------- */
QLabel#v2AboutLogo {{
    background: {c['accent_soft']}; border-radius: 15px; font-size: 30px;
}}
QLabel#v2AboutTitle {{ font-size: 20px; font-weight: 700; color: {c['text']}; }}
QLabel#v2AboutVer {{ font-size: 12px; color: {c['hint']}; }}

/* ---------- 插件市场（沿用其控件命名） ---------- */
QFrame#restartBanner {{
    background: {c['accent_soft']}; border: 1px solid {c['accent']};
    border-radius: 8px;
}}
QLabel#bannerText {{ color: {c['accent']}; font-size: 12px; }}
QFrame#marketCard {{
    background: {card}; border: 1px solid {c['divider']};
    border-radius: 12px;
}}
QFrame#marketCard:hover {{
    border: 1px solid {c['border']}; background: {card_hover};
}}
QLabel#marketName {{ font-size: 14px; font-weight: 600; color: {c['text']}; }}
QLabel#marketVer {{ font-size: 11px; color: {c['hint']}; }}
QLabel#marketDesc {{ font-size: 12px; color: {c['sub_text']}; }}
QLabel#marketStatus {{ font-size: 11px; color: {c['hint']}; }}
QLabel#emptyTip {{ font-size: 13px; color: {c['hint']}; }}
QPlainTextEdit#marketLog {{
    background: {card2}; border: 1px solid {c['divider']};
    border-radius: 8px; color: {c['sub_text']}; font-size: 11px;
    font-family: Consolas, "Courier New", monospace;
}}
QProgressBar#marketProgress {{
    background: {c['border']}; border: none; border-radius: 2px;
}}
QProgressBar#marketProgress::chunk {{
    background: {c['accent']}; border-radius: 2px;
}}

/* ---------- 表格 / 列表（插件设置页可能用到） ---------- */
QTableWidget {{
    background: {inp}; alternate-background-color: {card2};
    border: 1px solid {c['divider']}; border-radius: 8px;
    gridline-color: {c['divider']}; color: {c['text']};
    selection-background-color: {c['accent_soft']};
    selection-color: {c['text']}; outline: none;
}}
QHeaderView::section {{
    background: {card2}; color: {c['sub_text']};
    border: none; border-bottom: 1px solid {c['divider']};
    padding: 6px; font-weight: 600;
}}
QListWidget {{
    background: {inp}; border: 1px solid {c['divider']};
    border-radius: 8px; outline: none; padding: 4px; color: {c['text']};
}}
QListWidget::item {{ padding: 7px 8px; border-radius: 6px; }}
QListWidget::item:selected {{
    background: {c['accent_soft']}; color: {c['accent']};
}}

/* ---------- 滚动条 ---------- */
QScrollBar:vertical {{
    background: transparent; width: 10px; margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {c['scroll_handle']}; border-radius: 5px; min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: {c['hint']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0; background: none;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
}}
QScrollBar:horizontal {{ height: 0; }}
"""
