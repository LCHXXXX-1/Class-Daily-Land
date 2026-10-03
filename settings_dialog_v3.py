"""设置窗口 V3 —— Windows 11 Fluent 全新设计（独立文件，与旧设置代码无关）。

设计语言（对齐 WinUI 3 / Windows 11 设置应用）：
- 导航：单色线性矢量图标（不依赖 emoji 字体）+ 选中项左侧圆角
  指示条与高亮块同步滑动；窗口变窄（<860px）自动收成纯图标栏，
  适配小屏窗口与触屏一体机
- 内容：大号页头 + Win11 分层卡片（8px 圆角、发丝描边、极轻投影），
  行间发丝分隔线；操作项为「标题 + 说明 + ›」可点行
- 控件：Win11 规格开关（滑动时旋钮果冻拉伸、按压变大）、
  分段选择器指示块平滑滑动、白环滑杆、5px 圆角输入框、
  带底部描边的标准按钮与亚克力观感主按钮
- 动画：页面交叉淡入 + 10px 上滑、导航错峰入场、指示条滑动，
  统一 OutCubic 缓动，时长 150~230ms，细腻不拖沓
- 材质：浅色 / 深色 / Windows 11 云母（Mica）全量适配，
  卡片在半透明层上再叠一层，主题切换即时刷新
- Windows 10 兼容：DWM 不支持圆角属性时自动切换为「无边框 +
  自绘圆角窗框 + Win11 风格自绘标题栏（最小化 / 最大化 / 关闭）+
  阴影 + 原生边缘缩放与 Aero 吸附」，Win10 同样有圆角窗口

功能与旧设置界面完全一致（通用 / 外观 / 灵动岛 / 课表与提醒 /
插件市场 / 第三方包管理 / 高级 / 插件页 / 关于），入口签名保持不变：

    from settings_dialog_v3 import SettingsDialog
    SettingsDialog(settings, schedule_manager=..., plugin_manager=...,
                   controller=..., on_apply=..., parent=...)
"""
import math
import os
import sys

from PySide6.QtCore import (Qt, QEvent, QTimer, QPoint, QPointF, QRect,
                            QRectF, QSize, Property, Signal,
                            QPropertyAnimation, QEasingCurve,
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
from utils import (APP_NAME, ICON_PATH, is_windows_11, windows_display_name,
                   set_window_icon)
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


def _qcolor(hex_color, alpha=1.0):
    """QPainter 用的半透明颜色。
    注意：QPainter 侧的 QColor 不解析 CSS 风格的 "rgba(...,0.x)" 字符串
    （那是 QSS 解析器的语法），直接用会得到非法颜色 → 画成黑色。
    半透明颜色必须走 setAlphaF。"""
    qc = QColor(hex_color)
    if alpha < 1.0:
        qc.setAlphaF(max(0.0, min(1.0, float(alpha))))
    return qc


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
class PageStack(QWidget):
    """一次只显示一页；切换时新页淡入并滑动到位，旧页立即隐藏。

    direction（与 Win11 设置的钻取导航一致）：
    -  1 前进（进入二级页）：新页从右侧滑入（从右往左）
    - -1 后退（返回上级）：新页从左侧滑入（从左往右）
    -  0 同级切换：10px 上滑淡入
    fade_enabled=False 时不用透明度特效（云母/自绘透明窗里
    QGraphicsOpacityEffect 会产生黑色残影），只做位移动画。
    """

    SLIDE_Y = 10
    SLIDE_X = 28
    DURATION = 210

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("v3Stack")
        self._pages = []
        self._current = -1
        self._group = None
        self.fade_enabled = True

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

    def set_current(self, idx, animate=True, direction=0):
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

        if direction > 0:
            start = QPoint(self.SLIDE_X, 0)
        elif direction < 0:
            start = QPoint(-self.SLIDE_X, 0)
        else:
            start = QPoint(0, self.SLIDE_Y)

        if not animate or not self.isVisible():
            new.move(0, 0)
            new.show()
            new.raise_()
            return

        new.move(start)
        new.show()
        new.raise_()

        anims = []
        if self.fade_enabled:
            eff = QGraphicsOpacityEffect(new)
            eff.setOpacity(0.0)
            new.setGraphicsEffect(eff)
            a_op = QPropertyAnimation(eff, b"opacity", self)
            a_op.setDuration(self.DURATION)
            a_op.setStartValue(0.0)
            a_op.setEndValue(1.0)
            a_op.setEasingCurve(QEasingCurve.OutCubic)
            anims.append(a_op)

        a_pos = QPropertyAnimation(new, b"pos", self)
        a_pos.setDuration(self.DURATION)
        a_pos.setStartValue(start)
        a_pos.setEndValue(QPoint(0, 0))
        a_pos.setEasingCurve(QEasingCurve.OutCubic)
        anims.append(a_pos)

        self._group = QParallelAnimationGroup(self)
        for a in anims:
            self._group.addAnimation(a)
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
# Win11 开关（果冻拉伸 + 按压变大）
# ============================================================
class WinToggle(QAbstractButton):
    """Windows 11 规格开关：40×20 细轨道，滑动时旋钮沿运动方向拉伸，
    按住时旋钮略微变大（WinUI 3 ToggleSwitch 手感）。"""

    TRACK_W = 40
    TRACK_H = 20
    PAD = 4.0
    KNOB = 12.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self._knob = 0.0
        self._stretch = 0.0
        self._group = None
        self._mute = False
        self.toggled.connect(self._on_toggled)

    def _get_knob(self):
        return self._knob

    def _set_knob(self, v):
        self._knob = 0.0 if v < 0 else (1.0 if v > 1 else float(v))
        self.update()

    knob = Property(float, _get_knob, _set_knob)

    def _get_stretch(self):
        return self._stretch

    def _set_stretch(self, v):
        self._stretch = max(0.0, min(1.0, float(v)))
        self.update()

    stretch = Property(float, _get_stretch, _set_stretch)

    def sizeHint(self):
        return QSize(self.TRACK_W + 4, self.TRACK_H + 8)

    def set_state(self, checked):
        checked = bool(checked)
        self._mute = True
        self.setChecked(checked)
        self._mute = False
        self._stop_anim()
        self._knob = 1.0 if checked else 0.0
        self._stretch = 0.0
        self.update()

    def _on_toggled(self, on):
        if self._mute:
            return
        self._animate_to(1.0 if on else 0.0)

    def _animate_to(self, target):
        self._stop_anim()
        a_pos = QPropertyAnimation(self, b"knob", self)
        a_pos.setDuration(180)
        a_pos.setStartValue(self._knob)
        a_pos.setEndValue(target)
        a_pos.setEasingCurve(QEasingCurve.OutCubic)

        a_st = QPropertyAnimation(self, b"stretch", self)
        a_st.setDuration(180)
        a_st.setStartValue(0.0)
        a_st.setKeyValueAt(0.45, 1.0)
        a_st.setEndValue(0.0)
        a_st.setEasingCurve(QEasingCurve.InOutCubic)

        self._group = QParallelAnimationGroup(self)
        self._group.addAnimation(a_pos)
        self._group.addAnimation(a_st)
        self._group.start(QAbstractAnimation.DeleteWhenStopped)
        self._group.finished.connect(self._on_anim_done)

    def _on_anim_done(self):
        self._group = None

    def _stop_anim(self):
        if self._group is not None:
            try:
                self._group.stop()
            except RuntimeError:
                pass
            self._group = None

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        on = self.isChecked()
        tw, th = float(self.TRACK_W), float(self.TRACK_H)
        x = (self.width() - tw) / 2.0
        y = (self.height() - th) / 2.0

        if on:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.color(
                "accent_hover" if self.underMouse() else "accent")))
            p.drawRoundedRect(QRectF(x, y, tw, th), th / 2, th / 2)
        else:
            # Win11 关态：近透明底 + 次级文字描边，悬停垫一层浅底
            p.setPen(QPen(QColor(theme.color("sub_text")), 1))
            if self.underMouse():
                p.setBrush(QColor(theme.color("hover")))
            else:
                p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(QRectF(x + 0.5, y + 0.5, tw - 1, th - 1),
                              th / 2 - 0.5, th / 2 - 0.5)

        d = self.KNOB + (2.0 if self.isDown() else 0.0)
        travel = tw - 2 * self.PAD - self.KNOB
        extra = 6.0 * self._stretch
        kw = d + extra
        # 拉伸时保持「运动方向的后缘」不动，像果冻被拖着走
        cx = x + self.PAD + travel * self._knob - extra * self._knob
        cy = y + th / 2.0 - d / 2.0
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#ffffff") if on
                   else QColor(theme.color("sub_text")))
        p.drawRoundedRect(QRectF(cx, cy, kw, d), d / 2, d / 2)
        p.end()


# ============================================================
# 分段选择器（自绘，指示块平滑滑动）
# ============================================================
class FluentSegmented(QWidget):
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
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 6, 6)

        seg_w = (w - 2 * self.PAD) / n
        ix = self.PAD + seg_w * self._pos
        ind = QRectF(ix, self.PAD, seg_w, h - 2 * self.PAD)
        # 指示块：下方 1px 柔和投影 + 卡片面 + 发丝描边
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 22))
        p.drawRoundedRect(ind.translated(0, 1), 4.5, 4.5)
        p.setPen(QPen(QColor(theme.color("divider")), 1))
        p.setBrush(QColor(theme.color("window_bg")))
        p.drawRoundedRect(ind.adjusted(0.5, 0.5, -0.5, -0.5), 4, 4)

        f = QFont(self.font())
        f.setPixelSize(12)
        for i, (label, _v) in enumerate(self._options):
            f.setBold(i == self._index)
            p.setFont(f)
            p.setPen(QColor(theme.color("text") if i == self._index
                            else theme.color("sub_text")))
            p.drawText(QRectF(self.PAD + seg_w * i, 0, seg_w, h),
                       Qt.AlignCenter, str(label))
        p.end()


# ============================================================
# 左侧导航：Win11 单色线性矢量图标 + 选中指示条
# ============================================================
VECTOR_ICONS = {"gear", "palette", "island", "calendar", "market",
                "box", "wrench", "plugin", "info", "book", "pencil",
                "list", "people", "sun", "play", "clock", "back"}

# emoji 字体回退链：QSS 字体不走 Qt 的自动字形回退，
# 导致 emoji 在自绘控件里渲染不出，必须显式指定
EMOJI_FAMILIES = ["Segoe UI Emoji", "Segoe UI Symbol",
                  "Apple Color Emoji", "Noto Color Emoji"]


def draw_fluent_icon(p, rect, name, color):
    """在 rect 内绘制 Win11 风格的单色线性矢量图标。"""
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(color, max(1.0, rect.width() * 0.07),
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
        path = QPainterPath()
        path.moveTo(cx, cy - r)
        path.arcTo(box, 90, 180)     # 左半圆
        path.closeSubpath()
        fill = QColor(color)
        fill.setAlpha(140)
        p.setBrush(fill)
        p.setPen(Qt.NoPen)
        p.drawPath(path)

    elif name == "island":           # 灵动岛：胶囊 + 前置镜头点
        bw, bh = 12.4 * u, 5.6 * u
        p.drawRoundedRect(QRectF(cx - bw / 2, cy - bh / 2, bw, bh),
                          bh / 2, bh / 2)
        dot = 1.4 * u
        p.setBrush(color)
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
        p.setBrush(color)
        p.setPen(Qt.NoPen)
        p.drawEllipse(QRectF(cx - d / 2, y0 + 5.6 * u, d, d))

    elif name == "market":           # 商店：购物袋
        bw, bh = 10.4 * u, 8.6 * u
        x0, y0 = cx - bw / 2, cy - bh / 2 + 1.2 * u
        p.drawRoundedRect(QRectF(x0, y0, bw, bh), 1.8 * u, 1.8 * u)
        p.drawArc(QRectF(cx - 2.6 * u, y0 - 3.4 * u, 5.2 * u, 5.2 * u),
                  0, 180 * 16)

    elif name == "box":              # 第三方包：纸箱
        bw, bh = 10.6 * u, 8.6 * u
        x0, y0 = cx - bw / 2, cy - bh / 2 + 0.8 * u
        p.drawRoundedRect(QRectF(x0, y0, bw, bh), 1.4 * u, 1.4 * u)
        p.drawLine(QPointF(x0, y0 + 2.6 * u), QPointF(x0 + bw, y0 + 2.6 * u))
        p.drawLine(QPointF(cx, y0), QPointF(cx, y0 + 2.6 * u))

    elif name == "wrench":           # 高级：三根调谐滑杆
        for i, knob in enumerate((0.68, 0.32, 0.55)):
            yy = cy + (i - 1) * 3.6 * u
            p.drawLine(QPointF(cx - 5.6 * u, yy), QPointF(cx + 5.6 * u, yy))
            kx = cx - 5.6 * u + 11.2 * u * knob
            r = 1.6 * u
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
                    fill = QColor(color)
                    fill.setAlpha(160)
                    p.setBrush(fill)
                else:
                    p.setBrush(Qt.NoBrush)
                p.setPen(pen)
                p.drawRoundedRect(r, 1.2 * u, 1.2 * u)

    elif name == "book":             # 作业：翻开的书
        bw, bh = 12.0 * u, 9.0 * u
        x0, y0 = cx - bw / 2, cy - bh / 2
        path = QPainterPath()
        path.moveTo(cx, y0 + 1.6 * u)
        # 左页
        path.cubicTo(cx - 2.2 * u, y0, cx - 4.6 * u, y0, x0, y0 + 1.2 * u)
        path.lineTo(x0, y0 + bh - 1.2 * u)
        path.cubicTo(cx - 4.6 * u, y0 + bh - 2.4 * u, cx - 2.2 * u,
                     y0 + bh - 2.4 * u, cx, y0 + bh)
        # 右页
        path.moveTo(cx, y0 + 1.6 * u)
        path.cubicTo(cx + 2.2 * u, y0, cx + 4.6 * u, y0, x0 + bw, y0 + 1.2 * u)
        path.lineTo(x0 + bw, y0 + bh - 1.2 * u)
        path.cubicTo(cx + 4.6 * u, y0 + bh - 2.4 * u, cx + 2.2 * u,
                     y0 + bh - 2.4 * u, cx, y0 + bh)
        p.drawPath(path)
        p.drawLine(QPointF(cx, y0 + 1.6 * u), QPointF(cx, y0 + bh))

    elif name == "pencil":           # 编辑器：斜铅笔
        p.save()
        p.translate(cx, cy)
        p.rotate(45)
        bw, bh = 3.2 * u, 10.4 * u
        p.drawRoundedRect(QRectF(-bw / 2, -bh / 2, bw, bh - 2.4 * u),
                          0.8 * u, 0.8 * u)
        path = QPainterPath()
        path.moveTo(-bw / 2, bh / 2 - 2.4 * u)
        path.lineTo(0, bh / 2)
        path.lineTo(bw / 2, bh / 2 - 2.4 * u)
        p.drawPath(path)
        p.restore()

    elif name == "list":             # 课表管理：三行列表
        for i in range(3):
            yy = cy + (i - 1) * 3.6 * u
            d = 1.1 * u
            p.setBrush(color)
            p.setPen(Qt.NoPen)
            p.drawEllipse(QRectF(cx - 5.8 * u, yy - d / 2, d, d))
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawLine(QPointF(cx - 3.2 * u, yy), QPointF(cx + 5.8 * u, yy))

    elif name == "people":           # 值日生：两个人形
        r = 1.9 * u
        p.drawEllipse(QRectF(cx - 3.4 * u - r, cy - 5.4 * u, 2 * r, 2 * r))
        p.drawArc(QRectF(cx - 3.4 * u - 3.0 * u, cy - 0.6 * u,
                         6.0 * u, 5.6 * u), 0, 180 * 16)
        r2 = 1.5 * u
        p.drawEllipse(QRectF(cx + 3.2 * u - r2, cy - 4.4 * u, 2 * r2, 2 * r2))
        p.drawArc(QRectF(cx + 3.2 * u - 2.4 * u, cy - 0.2 * u,
                         4.8 * u, 4.4 * u), 0, 180 * 16)

    elif name == "sun":              # 假期：太阳
        r = 3.4 * u
        p.drawEllipse(QRectF(cx - r, cy - r, 2 * r, 2 * r))
        for i in range(8):
            a = math.pi / 4 * i
            p.drawLine(QPointF(cx + math.cos(a) * (r + 1.0 * u),
                               cy + math.sin(a) * (r + 1.0 * u)),
                       QPointF(cx + math.cos(a) * (r + 2.2 * u),
                               cy + math.sin(a) * (r + 2.2 * u)))

    elif name == "play":             # 状态测试：播放键
        path = QPainterPath()
        path.moveTo(cx - 2.4 * u, cy - 3.6 * u)
        path.lineTo(cx + 3.6 * u, cy)
        path.lineTo(cx - 2.4 * u, cy + 3.6 * u)
        path.closeSubpath()
        p.drawPath(path)

    elif name == "clock":            # 周末作息：时钟
        r = 5.4 * u
        p.drawEllipse(QRectF(cx - r, cy - r, 2 * r, 2 * r))
        p.drawLine(QPointF(cx, cy), QPointF(cx, cy - 3.2 * u))
        p.drawLine(QPointF(cx, cy), QPointF(cx + 2.4 * u, cy + 1.4 * u))

    elif name == "back":             # 返回：左箭头
        p.drawLine(QPointF(cx + 3.0 * u, cy - 4.4 * u),
                   QPointF(cx - 2.4 * u, cy))
        p.drawLine(QPointF(cx - 2.4 * u, cy),
                   QPointF(cx + 3.0 * u, cy + 4.4 * u))

    else:                            # info：圆圈 + i
        r = 5.4 * u
        p.drawEllipse(QRectF(cx - r, cy - r, 2 * r, 2 * r))
        d = 1.3 * u
        p.setBrush(color)
        p.setPen(Qt.NoPen)
        p.drawEllipse(QRectF(cx - d / 2, cy - 3.2 * u, d, d))
        p.setPen(pen)
        p.drawLine(QPointF(cx, cy - 1.0 * u), QPointF(cx, cy + 3.2 * u))

    p.restore()


class NavButton(QAbstractButton):
    """自绘导航项：单色矢量图标 + 标题；紧凑模式只留图标。"""

    H = 36
    ICON = 18
    ICON_X = 11
    TEXT_X = 40

    def __init__(self, icon, title, parent=None):
        super().__init__(parent)
        self._icon = icon            # 矢量图标名（gear/palette/...）或 emoji
        self._title = title
        self._tint = None            # 自定义图标颜色（彩色图标 API）
        self._icon_pixmap = None     # 自定义图标图片（插件 icon_path）
        self._compact = False
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setFixedHeight(self.H)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(title)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_compact(self, on):
        on = bool(on)
        if on == self._compact:
            return
        self._compact = on
        self.update()

    def set_tint(self, color):
        """自定义图标颜色（None 恢复默认主题色）。"""
        self._tint = QColor(color) if color else None
        self.update()

    def set_icon_pixmap(self, pixmap):
        """自定义图标图片（插件提供的 icon_path）。"""
        self._icon_pixmap = pixmap if (pixmap and not pixmap.isNull()) else None
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        checked = self.isChecked()

        # hover 底色（选中项的高亮块由 FluentNav 的 pill 负责）；
        # 原生悬停同样极淡
        if (self.underMouse() or self.isDown()) and not checked:
            if theme.is_dark():
                p.setBrush(_qcolor("#ffffff",
                                   0.08 if self.isDown() else 0.045))
            else:
                p.setBrush(_qcolor("#000000",
                                   0.06 if self.isDown() else 0.035))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(QRectF(0, 0, w, h), 6, 6)

        # 图标
        if self._compact:
            ix = (w - self.ICON) / 2.0
        else:
            ix = float(self.ICON_X)
        tile = QRectF(ix, (h - self.ICON) / 2.0, self.ICON, self.ICON)
        if self._tint is not None:
            tint = QColor(self._tint)
        else:
            tint = QColor(theme.color("accent") if checked
                          else theme.color("sub_text"))
        if self._icon_pixmap is not None:
            p.drawPixmap(tile.toRect(), self._icon_pixmap)
        elif self._icon in VECTOR_ICONS:
            draw_fluent_icon(p, tile, self._icon, tint)
        else:
            f = QFont()
            f.setFamilies(EMOJI_FAMILIES + [self.font().family()])
            f.setPixelSize(15)
            p.setFont(f)
            p.setPen(tint)
            p.drawText(tile, Qt.AlignCenter, self._icon)

        # 标题
        if not self._compact:
            f = QFont(self.font())
            f.setPixelSize(13)
            f.setWeight(QFont.DemiBold if checked else QFont.Normal)
            p.setFont(f)
            p.setPen(QColor(theme.color("text")))
            p.drawText(QRectF(self.TEXT_X, 0, w - self.TEXT_X - 8, h),
                       Qt.AlignVCenter | Qt.AlignLeft, self._title)
        p.end()


class FluentNav(QWidget):
    """导航容器：选中项背后的高亮块 + 左侧 Win11 指示条同步滑动。"""

    item_clicked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("v3Nav")
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(8, 4, 8, 4)
        self._lay.setSpacing(2)
        self._buttons = []
        self._groups = []
        self._compact = False

        self._pill = QFrame(self)
        self._pill.setObjectName("v3NavPill")
        self._bar = QFrame(self)
        self._bar.setObjectName("v3NavBar")
        self._anims = []
        self.restyle()

    def add_group(self, title):
        lbl = QLabel(title, self)
        lbl.setObjectName("v3NavGroup")
        self._lay.addSpacing(10 if self._groups else 2)
        self._lay.addWidget(lbl)
        self._groups.append(lbl)
        lbl.setVisible(not self._compact)

    def add_item(self, icon, title):
        idx = len(self._buttons)
        btn = NavButton(icon, title, self)
        btn.set_compact(self._compact)
        btn.clicked.connect(lambda _=False, i=idx: self.item_clicked.emit(i))
        self._lay.addWidget(btn)
        self._buttons.append(btn)
        return idx

    def set_item_tint(self, idx, color):
        if 0 <= idx < len(self._buttons):
            self._buttons[idx].set_tint(color)

    def set_item_pixmap(self, idx, pixmap):
        if 0 <= idx < len(self._buttons):
            self._buttons[idx].set_icon_pixmap(pixmap)

    def finish(self):
        self._lay.addStretch(1)

    def count(self):
        return len(self._buttons)

    def items(self):
        return list(self._buttons)

    def set_compact(self, on):
        on = bool(on)
        if on == self._compact:
            return
        self._compact = on
        self._lay.setContentsMargins(6, 4, 6, 4)
        for b in self._buttons:
            b.set_compact(on)
        for g in self._groups:
            g.setVisible(not on)
        # 布局变化后重贴高亮块
        QTimer.singleShot(0, self, self._snap_pill)

    def _snap_pill(self):
        idx = next((i for i, b in enumerate(self._buttons)
                    if b.isChecked()), 0)
        if self._buttons:
            g = self._buttons[idx].geometry()
            self._pill.setGeometry(g)
            self._bar.setGeometry(self._bar_rect(g))

    def restyle(self):
        # 原生 Win11 选中底色极淡（约 4~6% 黑/白），若有似无
        if theme.is_dark():
            pill = _rgba("#ffffff", 0.06)
        else:
            pill = _rgba("#000000", 0.045)
        self._pill.setStyleSheet(
            f"background:{pill};border:none;border-radius:6px;")
        self._bar.setStyleSheet(
            f"background:{theme.color('accent')};"
            "border:none;border-radius:1.5px;")
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
        self._stop_anims()
        if not animate:
            self._pill.setGeometry(target)
            self._bar.setGeometry(bar_target)
            return
        for w, end in ((self._pill, target), (self._bar, bar_target)):
            a = QPropertyAnimation(w, b"geometry", self)
            a.setDuration(180)
            a.setStartValue(w.geometry())
            a.setEndValue(end)
            a.setEasingCurve(QEasingCurve.OutCubic)
            a.start(QAbstractAnimation.DeleteWhenStopped)
            self._anims.append(a)

    def _stop_anims(self):
        for a in self._anims:
            try:
                a.stop()
            except RuntimeError:
                pass
        self._anims = []

    @staticmethod
    def _bar_rect(btn_rect):
        # Win11 指示条：3px 宽、16px 高、两端全圆角，贴在条目左缘
        return QRect(btn_rect.x() + 2,
                     btn_rect.y() + (btn_rect.height() - 16) // 2,
                     3, 16)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._snap_pill()


# ============================================================
# 搜索框（自绘清晰的 ✕ 清除按钮）
# ============================================================
class SearchLineEdit(QLineEdit):
    """带自绘清除按钮的输入框。
    Qt 自带的 clearButton 图标在高 DPI 下发虚，这里用 QPainter
    画一个 Win11 风格的 ×：常态次级色，悬停出圆形浅底并加深。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setClearButtonEnabled(False)
        self.setTextMargins(0, 0, 26, 0)
        self.setMouseTracking(True)
        self._hover_clear = False

    def _clear_rect(self):
        return QRect(self.width() - 26, (self.height() - 16) // 2, 16, 16)

    def mousePressEvent(self, event):
        if self.text() and self._clear_rect().contains(
                event.position().toPoint()):
            self.clear()
            self.setFocus()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        hov = bool(self.text()) and self._clear_rect().contains(
            event.position().toPoint())
        if hov != self._hover_clear:
            self._hover_clear = hov
            self.setCursor(Qt.PointingHandCursor if hov else Qt.IBeamCursor)
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        if self._hover_clear:
            self._hover_clear = False
            self.unsetCursor()
            self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.text():
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self._clear_rect())
        if self._hover_clear:
            p.setPen(Qt.NoPen)
            p.setBrush(_qcolor("#ffffff", 0.08) if theme.is_dark()
                       else _qcolor("#000000", 0.06))
            p.drawEllipse(r)
        c = r.center()
        d = 3.4
        pen = QPen(QColor(theme.color("text") if self._hover_clear
                          else theme.color("sub_text")),
                   1.4, Qt.SolidLine, Qt.RoundCap)
        p.setPen(pen)
        p.drawLine(QPointF(c.x() - d, c.y() - d),
                   QPointF(c.x() + d, c.y() + d))
        p.drawLine(QPointF(c.x() - d, c.y() + d),
                   QPointF(c.x() + d, c.y() - d))
        p.end()


class SearchField(SearchLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("v3Search")
        self.setPlaceholderText("搜索设置")


# ============================================================
# 卡片 / 设置行 / 操作行
# ============================================================
class SettingCard(QFrame):
    """Win11 分层卡片：标题 + 内容行，行间自动插发丝分隔线。"""

    def __init__(self, title="", subtitle="", parent=None):
        super().__init__(parent)
        self.setObjectName("v3Card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 10)
        lay.setSpacing(0)
        self.body = lay
        self._row_count = 0
        if title:
            lbl = QLabel(title)
            lbl.setObjectName("v3CardTitle")
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
        line.setObjectName("v3Divider")
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
        self.setObjectName("v3Row")
        self.row = row
        self.ctx = ctx
        self._loading = False
        self._flash_timer = None

        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 11, 2, 11)
        lay.setSpacing(20)

        left = QVBoxLayout()
        left.setSpacing(3)
        title = QLabel(row.title)
        title.setObjectName("v3RowTitle")
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
            w = WinToggle()
            w.toggled.connect(lambda on: self._commit(bool(on)))
            return w

        if r.kind == "segmented":
            w = FluentSegmented(r.options)
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
            val.setObjectName("v3SliderVal")
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
    """「图标 + 标题 + 说明 + ›」的可点击操作行（Win11 设置风格）。

    card=False：卡片内列表行（发丝分隔线样式）；
    card=True ：独立大卡（原生二级页索引样式：更高、自带描边圆角），
    图标 20px，可用 tint 指定彩色图标、icon_bg 加底色圆角块。
    """

    def __init__(self, title, hint="", danger=False, parent=None,
                 icon=None, card=False, tint=None, icon_bg=None,
                 icon_pixmap=None):
        super().__init__(parent)
        self.setObjectName("v4LinkCard" if card else "v3LinkRow")
        self._card = bool(card)
        self._tint = QColor(tint) if tint else None
        self._icon_bg = QColor(icon_bg) if icon_bg else None
        self._icon_pixmap = (icon_pixmap
                             if (icon_pixmap is not None
                                 and not icon_pixmap.isNull()) else None)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self._icon = icon
        lay = QHBoxLayout(self)
        if self._card:
            lay.setContentsMargins(18, 15, 16, 15)
            lay.setSpacing(16)
        else:
            lay.setContentsMargins(10, 10, 12, 10)
            lay.setSpacing(14)

        if icon:
            icon_lbl = QLabel()
            icon_lbl.setFixedSize(20, 20)
            icon_lbl.setObjectName("v3LinkIcon")
            lay.addWidget(icon_lbl, 0, Qt.AlignVCenter)
            self._icon_lbl = icon_lbl
        else:
            self._icon_lbl = None

        left = QVBoxLayout()
        left.setSpacing(3)
        t = QLabel(title)
        t.setObjectName("v3LinkDanger" if danger else "v3RowTitle")
        left.addWidget(t)
        if hint:
            s = QLabel(hint)
            s.setObjectName("hint")
            s.setWordWrap(True)
            left.addWidget(s)
        lay.addLayout(left, 1)

        arrow = QLabel("›")
        arrow.setObjectName("v3Chevron")
        lay.addWidget(arrow, 0, Qt.AlignVCenter)
        self.search_text = " ".join((title, hint)).lower()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(0, 0, self.width(), self.height())
        radius = 8 if self._card else 6
        if self._card:
            # 独立大卡：卡片底 + 发丝描边（颜色与 v3Card 一致）
            dark = theme.is_dark()
            p.setPen(QPen(_qcolor("#ffffff", 0.07) if dark
                          else _qcolor("#000000", 0.05), 1))
            p.setBrush(QColor("#2b2b2b") if dark else QColor("#ffffff"))
            p.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5),
                              radius, radius)
            if self.isDown():
                p.setBrush(_qcolor("#000000", 0.05) if not dark
                           else _qcolor("#ffffff", 0.05))
                p.setPen(Qt.NoPen)
                p.drawRoundedRect(rect, radius, radius)
            elif self.underMouse():
                p.setBrush(_qcolor("#000000", 0.025) if not dark
                           else _qcolor("#ffffff", 0.03))
                p.setPen(Qt.NoPen)
                p.drawRoundedRect(rect, radius, radius)
        else:
            if self.isDown():
                bg = theme.color("pressed")
            elif self.underMouse():
                bg = theme.color("hover")
            else:
                bg = None
            if bg:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(bg))
                p.drawRoundedRect(rect, radius, radius)
        # 左侧图标（QLabel 只用来占位，图由这里画，颜色才能跟主题）
        if self._icon and self._icon_lbl:
            g = self._icon_lbl.geometry()
            tile = QRectF(g.x(), g.y(), g.width(), g.height())
            if self._icon_bg is not None:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(self._icon_bg))
                p.drawRoundedRect(tile.adjusted(-5, -5, 5, 5), 7, 7)
            tint = QColor(self._tint) if self._tint is not None \
                else QColor(theme.color("sub_text"))
            if self._icon_pixmap is not None:
                p.drawPixmap(tile.toRect(), self._icon_pixmap)
            elif self._icon in VECTOR_ICONS:
                draw_fluent_icon(p, tile, self._icon, tint)
            else:
                f = QFont()
                f.setFamilies(EMOJI_FAMILIES + [self.font().family()])
                f.setPixelSize(15)
                p.setFont(f)
                p.setPen(tint)
                p.drawText(tile, Qt.AlignCenter, self._icon)
        p.end()


# ============================================================
# Win10 自绘标题栏（无边框圆角窗口用）
# ============================================================
class _TitleBar(QFrame):
    """Win11 风格的自绘标题栏：图标 + 标题 + 最小化 / 最大化 / 关闭。
    拖拽使用系统级移动（startSystemMove），支持 Aero 吸附。"""

    H = 32
    BTN_W = 46

    def __init__(self, dlg):
        super().__init__(dlg)
        self.setObjectName("v3TitleBar")
        self._dlg = dlg
        self.setFixedHeight(self.H)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 0, 0)
        lay.setSpacing(8)

        pm = _app_pixmap(16)
        if pm is not None:
            icon = QLabel()
            icon.setObjectName("v3TbIcon")
            icon.setFixedSize(16, 16)
            icon.setPixmap(pm)
            lay.addWidget(icon, 0, Qt.AlignVCenter)
        title = QLabel("设置")
        title.setObjectName("v3TbTitle")
        lay.addWidget(title, 0, Qt.AlignVCenter)
        lay.addStretch(1)

        self.btn_min = self._make_btn("\uE921", "v3TbMin", "最小化")
        self.btn_min.clicked.connect(dlg.showMinimized)
        self.btn_max = self._make_btn("\uE922", "v3TbMax", "最大化")
        self.btn_max.clicked.connect(self._toggle_max)
        self.btn_close = self._make_btn("\uE8BB", "v3TbClose", "关闭")
        self.btn_close.clicked.connect(dlg.reject)
        lay.addWidget(self.btn_min)
        lay.addWidget(self.btn_max)
        lay.addWidget(self.btn_close)

    def _make_btn(self, glyph, name, tip):
        b = QPushButton(glyph, self)
        b.setObjectName(name)
        b.setProperty("tbBtn", True)
        b.setFixedSize(self.BTN_W, self.H)
        b.setCursor(Qt.ArrowCursor)
        b.setToolTip(tip)
        return b

    def _toggle_max(self):
        if self._dlg.isMaximized():
            self._dlg.showNormal()
        else:
            self._dlg.showMaximized()

    def set_maximized(self, maxed):
        self.btn_max.setText("\uE923" if maxed else "\uE922")
        self.btn_max.setToolTip("还原" if maxed else "最大化")

    def mousePressEvent(self, event):
        # 系统级拖动：和原生标题栏手感一致，拖到屏幕边缘自动吸附
        if event.button() == Qt.LeftButton:
            wh = self.window().windowHandle()
            if wh is not None and wh.startSystemMove():
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._toggle_max()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


# ============================================================
# 设置窗口
# ============================================================
class SettingsDialog(QDialog):

    COMPACT_WIDTH = 860          # 小于此宽度时侧栏收成纯图标栏

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
        self._compact = False
        self._test_seconds = int(self.settings.get("island_countdown_sec", 60))
        self.market_page = None
        self.package_page = None

        # Windows 11 云母（Mica）材质
        self.win11 = is_windows_11()
        self._mica_active = bool(self.win11 and
                                 self.settings.get("settings_mica", True))
        self._last_material_ok = False

        # Windows 10：DWM 没有圆角属性，改用无边框 + 自绘圆角窗框
        self._custom_chrome = bool(sys.platform == "win32" and not self.win11)

        self.setObjectName("settingsV3")
        self.setWindowTitle("设置")
        self.resize(1000, 680)
        self.setMinimumSize(620, 480)
        if self._custom_chrome:
            self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
            self.setAttribute(Qt.WA_TranslucentBackground, True)
            set_window_icon(self)
        else:
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
        self.setStyleSheet(_v3_qss(glass=self._mica_active,
                                   chrome=self._custom_chrome))

    def _apply_card_shadows(self):
        # 原生卡片阴影若有似无：极小偏移 + 大柔化 + 低透明度
        alpha = 10 if not theme.is_dark() else 40
        for card in self.cards:
            try:
                eff = QGraphicsDropShadowEffect(card)
                eff.setBlurRadius(16)
                eff.setXOffset(0)
                eff.setYOffset(1)
                eff.setColor(QColor(0, 0, 0, alpha))
                card.setGraphicsEffect(eff)
            except RuntimeError:
                pass

    def _on_theme_changed(self):
        self._apply_qss()
        self.nav.restyle()
        self._apply_card_shadows()
        try:
            self._search_shadow.setColor(
                QColor(0, 0, 0, 50 if theme.is_dark() else 14))
        except Exception:
            pass
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
        self.sidebar = self._build_sidebar()
        self.content = self._build_content()

        if not self._custom_chrome:
            root = QHBoxLayout(self)
            root.setContentsMargins(0, 0, 0, 0)
            root.setSpacing(0)
            root.addWidget(self.sidebar)
            root.addWidget(self.content, 1)
            return

        # Win10 自绘窗框：外层留出阴影空间，chrome 画圆角与描边
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)
        outer.setSpacing(0)
        self._outer_lay = outer

        chrome = QFrame(self)
        chrome.setObjectName("v3Chrome")
        self._chrome = chrome
        shadow = QGraphicsDropShadowEffect(chrome)
        shadow.setBlurRadius(32)
        shadow.setXOffset(0)
        shadow.setYOffset(6)
        shadow.setColor(QColor(0, 0, 0, 90))
        chrome.setGraphicsEffect(shadow)
        self._chrome_shadow = shadow

        cl = QVBoxLayout(chrome)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        self._titlebar = _TitleBar(self)
        cl.addWidget(self._titlebar)

        body = QWidget()
        bl = QHBoxLayout(body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(0)
        bl.addWidget(self.sidebar)
        bl.addWidget(self.content, 1)
        cl.addWidget(body, 1)
        outer.addWidget(chrome)

    # ==================================================
    # Win10 自绘窗框：圆角 / 缩放 / 吸附
    # ==================================================
    def _update_chrome_state(self):
        """最大化时去掉圆角与阴影（与 Win11 原生窗口行为一致）。"""
        if not self._custom_chrome:
            return
        maxed = self.isMaximized()
        self._outer_lay.setContentsMargins(
            0, 0, 0, 0) if maxed else self._outer_lay.setContentsMargins(
            14, 14, 14, 14)
        self._chrome.setProperty("maximized", bool(maxed))
        self._chrome_shadow.setEnabled(not maxed)
        self._titlebar.set_maximized(maxed)
        for w in (self._chrome, self.sidebar, self._titlebar):
            w.style().unpolish(w)
            w.style().polish(w)

    def changeEvent(self, event):
        if (self._custom_chrome and
                event.type() == QEvent.WindowStateChange):
            self._update_chrome_state()
        super().changeEvent(event)

    def nativeEvent(self, eventType, message):
        if self._custom_chrome:
            try:
                handled, code = self._chrome_native_event(eventType, message)
                if handled:
                    return True, code
            except Exception:
                pass
        return super().nativeEvent(eventType, message)

    def _chrome_native_event(self, eventType, message):
        """无边框窗口的原生支持：边缘缩放（NCHITTEST）+
        最大化不盖任务栏（GETMINMAXINFO）。"""
        import ctypes
        from ctypes import wintypes
        if bytes(eventType) != b"windows_generic_MSG":
            return False, 0
        msg = wintypes.MSG.from_address(int(message))

        WM_NCHITTEST = 0x0084
        WM_GETMINMAXINFO = 0x0024

        if msg.message == WM_NCHITTEST:
            if self.isMaximized():
                return False, 0
            border = 6
            gx = msg.lParam & 0xFFFF
            gy = (msg.lParam >> 16) & 0xFFFF
            if gx >= 32768:
                gx -= 65536
            if gy >= 32768:
                gy -= 65536
            pos = self.mapFromGlobal(QPoint(gx, gy))
            x, y, w, h = pos.x(), pos.y(), self.width(), self.height()
            left = x < border
            right = x >= w - border
            top = y < border
            bottom = y >= h - border
            if top and left:
                return True, 13            # HTTOPLEFT
            if top and right:
                return True, 14            # HTTOPRIGHT
            if bottom and left:
                return True, 16            # HTBOTTOMLEFT
            if bottom and right:
                return True, 17            # HTBOTTOMRIGHT
            if left:
                return True, 10            # HTLEFT
            if right:
                return True, 11            # HTRIGHT
            if top:
                return True, 12            # HTTOP
            if bottom:
                return True, 15            # HTBOTTOM
            return False, 0

        if msg.message == WM_GETMINMAXINFO:
            # 无边框窗口最大化默认会盖住任务栏，把工作区尺寸报给系统
            class MINMAXINFO(ctypes.Structure):
                _fields_ = [("ptReserved", wintypes.POINT),
                            ("ptMaxSize", wintypes.POINT),
                            ("ptMaxPosition", wintypes.POINT),
                            ("ptMinTrackSize", wintypes.POINT),
                            ("ptMaxTrackSize", wintypes.POINT)]

            class MONITORINFO(ctypes.Structure):
                _fields_ = [("cbSize", ctypes.c_ulong),
                            ("rcMonitor", wintypes.RECT),
                            ("rcWork", wintypes.RECT),
                            ("dwFlags", ctypes.c_ulong)]

            MONITOR_DEFAULTTONEAREST = 2
            monitor = ctypes.windll.user32.MonitorFromWindow(
                ctypes.c_void_p(int(self.winId())), MONITOR_DEFAULTTONEAREST)
            if not monitor:
                return False, 0
            mi = MONITORINFO()
            mi.cbSize = ctypes.sizeof(MONITORINFO)
            if not ctypes.windll.user32.GetMonitorInfoW(
                    ctypes.c_void_p(monitor), ctypes.byref(mi)):
                return False, 0
            info = MINMAXINFO.from_address(msg.lParam)
            work, mon = mi.rcWork, mi.rcMonitor
            info.ptMaxSize.x = work.right - work.left
            info.ptMaxSize.y = work.bottom - work.top
            info.ptMaxPosition.x = work.left - mon.left
            info.ptMaxPosition.y = work.top - mon.top
            return True, 0

        return False, 0

    def _build_sidebar(self):
        bar = QFrame()
        bar.setObjectName("v3Sidebar")
        bar.setFixedWidth(264)
        lay = QVBoxLayout(bar)
        lay.setContentsMargins(14, 20, 14, 12)
        lay.setSpacing(10)

        # 品牌区：真实应用图标 + 名称
        brand = QHBoxLayout()
        brand.setSpacing(10)
        logo = QLabel()
        logo.setObjectName("v3BrandLogo")
        logo.setFixedSize(36, 36)
        logo.setAlignment(Qt.AlignCenter)
        pm = _app_pixmap(26)
        if pm is not None:
            logo.setPixmap(pm)
        else:
            logo.setText("🏫")
        brand.addWidget(logo, 0, Qt.AlignVCenter)
        col = QVBoxLayout()
        col.setSpacing(1)
        t = QLabel(APP_NAME)
        t.setObjectName("v3BrandTitle")
        s = QLabel("设置")
        s.setObjectName("v3BrandSub")
        col.addWidget(t)
        col.addWidget(s)
        self._brand_text = col
        brand_wrap = QWidget()
        brand_wrap.setLayout(col)
        brand.addWidget(brand_wrap)
        self._brand_text_wrap = brand_wrap
        brand.addStretch(1)
        brand_holder = QWidget()
        brand_holder.setLayout(brand)
        lay.addWidget(brand_holder)
        self._brand_holder = brand_holder
        lay.addSpacing(4)

        # 搜索（白底 + 轻投影，浮在材质上）
        self.search = SearchField()
        self.search.textChanged.connect(self._on_search)
        se = QGraphicsDropShadowEffect(self.search)
        se.setBlurRadius(14)
        se.setXOffset(0)
        se.setYOffset(1)
        se.setColor(QColor(0, 0, 0, 14 if not theme.is_dark() else 50))
        self.search.setGraphicsEffect(se)
        self._search_shadow = se
        lay.addWidget(self.search)

        # 搜索结果（与导航二选一显示）
        self.results = QListWidget()
        self.results.setObjectName("v3Results")
        self.results.setFrameShape(QFrame.NoFrame)
        self.results.setMaximumHeight(320)
        self.results.itemClicked.connect(self._on_result_clicked)
        self.results.hide()
        lay.addWidget(self.results)

        # 导航
        self.nav_scroll = QScrollArea()
        self.nav_scroll.setObjectName("v3NavScroll")
        self.nav_scroll.setWidgetResizable(True)
        self.nav_scroll.setFrameShape(QFrame.NoFrame)
        self.nav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.nav = FluentNav()
        self.nav.item_clicked.connect(self._select)
        self.nav_scroll.setWidget(self.nav)
        lay.addWidget(self.nav_scroll, 1)

        # 触屏：左侧导航也能手指上下滑
        setup_touch_scroll(self.nav_scroll, mouse_drag=True)

        # 版本
        ver = QLabel(f"v{get_version()}")
        ver.setObjectName("v3Version")
        lay.addWidget(ver)
        self._version_lbl = ver
        return bar

    def _build_content(self):
        wrap = QFrame()
        wrap.setObjectName("v3Content")
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.stack = PageStack()
        lay.addWidget(self.stack, 1)

        footer = QFrame()
        footer.setObjectName("v3Footer")
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(30, 10, 30, 14)
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
    # 紧凑模式（窄窗口 / 小屏触屏）：侧栏收成纯图标栏
    # ==================================================
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._set_compact(self.width() < self.COMPACT_WIDTH)

    def _set_compact(self, on):
        on = bool(on)
        if on == self._compact:
            return
        self._compact = on
        self.sidebar.setFixedWidth(64 if on else 264)
        self.search.setVisible(not on)
        if on:
            self.results.hide()
            self.nav_scroll.show()
        self._brand_text_wrap.setVisible(not on)
        self._version_lbl.setVisible(not on)
        self.nav.set_compact(on)

    # ==================================================
    # 页面骨架
    # ==================================================
    def _make_page(self, title, subtitle):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(34, 26, 22, 8)
        v.setSpacing(6)

        t = QLabel(title)
        t.setObjectName("v3PageTitle")
        v.addWidget(t)
        page._title_lbl = t
        page._sub_lbl = None
        if subtitle:
            s = QLabel(subtitle)
            s.setObjectName("v3PageSub")
            s.setWordWrap(True)
            v.addWidget(s)
            page._sub_lbl = s
        v.addSpacing(10)

        scroll = QScrollArea()
        scroll.setObjectName("v3PageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        inner = QWidget()
        inner.setObjectName("v3PageInner")
        il = QVBoxLayout(inner)
        il.setContentsMargins(6, 4, 18, 22)
        il.setSpacing(14)
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
                      "group": ""}
        return page

    def _add_page(self, icon, title, page, subtitle="", group=""):
        info = page._info
        info["icon"] = icon
        info["title"] = title
        if subtitle:
            info["sub"] = subtitle
        info["group"] = group
        info["index"] = len(self.pages)
        self.pages.append(info)
        self.stack.add_page(page)
        self._register_search(title, info, None, title)
        return info

    def _add_card(self, page, title="", subtitle=""):
        card = SettingCard(title, subtitle)
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
            self._add_page("market", "插件市场", page, "插件系统未启用",
                           group="扩展")
            return

        from market_page import MarketPage
        holder = QWidget()
        hl = QVBoxLayout(holder)
        hl.setContentsMargins(0, 0, 0, 0)
        self.market_page = MarketPage(self.plugin_manager, self.settings)
        self.market_page.setObjectName("v3PageInner")
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
        self.package_page.setObjectName("v3PageInner")
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
        logo.setObjectName("v3AboutLogo")
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
        title.setObjectName("v3AboutTitle")
        ver = QLabel(f"版本 {get_version()}")
        ver.setObjectName("v3AboutVer")
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
            self.nav.add_item(p["icon"], p["title"])
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
# 样式表（浅色 / 深色 / 云母 全适配，Win11 Fluent 规格）
# ============================================================
def _v3_qss(glass=False, chrome=False):
    c = theme.PALETTES[theme.current()]
    dark = theme.is_dark()
    # 原生 Win11 质感：侧栏与内容区是同一整块材质（无侧栏底色、无竖线），
    # 卡片比窗口更亮，靠极轻阴影与淡描边分层
    card_border = _rgba("#ffffff", 0.07) if dark else _rgba("#000000", 0.05)
    # 非云母浅色下窗口微灰，让纯白卡片能「浮」起来（原生纯色回退同理）
    solid_win = c['window_bg'] if dark else "#f5f5f5"
    if glass:
        win = _rgba(c['window_bg'], 0.45)
        bg = "transparent"
        sidebar = "transparent"
        card = _rgba("#2e2e2e", 0.72) if dark else _rgba("#ffffff", 0.72)
        card2 = _rgba(c['card_bg_2'], 0.8)
        card_hover = _rgba(c['card_hover'], 0.9)
        inp = _rgba(c['input_bg'], 0.7)
        hover = _rgba(c['hover'], 0.8)
        btn_border = _rgba(c['border'], 0.6)
    elif chrome:
        # Win10 自绘窗框：对话框本身透明，圆角底色由 v3Chrome 提供
        win = "transparent"
        bg = "transparent"
        sidebar = "transparent"
        card = "#2b2b2b" if dark else "#ffffff"
        card2 = c['card_bg_2']
        card_hover = c['card_hover']
        inp = c['input_bg']
        hover = c['hover']
        btn_border = c['border']
    else:
        win = solid_win
        bg = solid_win
        sidebar = "transparent"
        card = "#2b2b2b" if dark else "#ffffff"
        card2 = c['card_bg_2']
        card_hover = c['card_hover']
        inp = c['input_bg']
        hover = c['hover']
        btn_border = c['border']
    # Win11 标准按钮的「底部加深描边」
    btn_bottom = _rgba("#000000", 0.22) if not theme.is_dark() \
        else _rgba("#000000", 0.5)

    # Win10 自绘窗框（圆角 + 标题栏）的附加样式
    chrome_qss = ""
    if chrome:
        chrome_qss = f"""
/* ---------- Win10 自绘圆角窗框 ---------- */
QFrame#v3Chrome {{
    background: {solid_win};
    border: 1px solid {c['border']};
    border-radius: 8px;
}}
QFrame#v3Chrome[maximized="true"] {{
    border: none; border-radius: 0px;
}}
QFrame#v3Sidebar {{
    border-top-left-radius: 7px; border-bottom-left-radius: 7px;
}}
QFrame#v3Chrome[maximized="true"] QFrame#v3Sidebar {{
    border-radius: 0px;
}}
QFrame#v3TitleBar {{ background: transparent; border: none; }}
QLabel#v3TbTitle {{ font-size: 12px; color: {c['text']}; }}
QPushButton[tbBtn="true"] {{
    background: transparent; border: none; border-radius: 0px;
    color: {c['text']}; padding: 0;
    font-family: "Segoe MDL2 Assets"; font-size: 10px;
}}
QPushButton[tbBtn="true"]:hover {{ background: {hover}; }}
QPushButton[tbBtn="true"]:pressed {{ background: {c['pressed']}; }}
QPushButton#v3TbClose:hover {{ background: #e81123; color: #ffffff; }}
QPushButton#v3TbClose:pressed {{ background: #c50f1f; color: #ffffff; }}
QPushButton#v3TbClose {{
    border-top-right-radius: 7px;
}}
QFrame#v3Chrome[maximized="true"] QPushButton#v3TbClose {{
    border-top-right-radius: 0px;
}}
"""

    return chrome_qss + f"""
QDialog#settingsV3 {{
    background: {win};
    font-family: "Segoe UI Variable Text", "Segoe UI", "Microsoft YaHei UI";
}}
QLabel {{ color: {c['text']}; background: transparent; }}
QLabel#hint {{ font-size: 12px; color: {c['hint']}; }}

/* ---------- 侧栏（与内容区同一整块材质，无色差无竖线） ---------- */
QFrame#v3Sidebar {{
    background: {sidebar}; border: none;
}}
QLabel#v3BrandLogo {{
    background: transparent; border-radius: 9px; font-size: 19px;
}}
QLabel#v3BrandTitle {{ font-size: 14px; font-weight: 700; color: {c['text']}; }}
QLabel#v3BrandSub {{ font-size: 11px; color: {c['hint']}; }}
QLabel#v3Version {{ font-size: 11px; color: {c['hint']}; padding-left: 12px; }}

QLineEdit#v3Search {{
    background: {inp}; border: 1px solid {c['border']};
    border-bottom: 1px solid {btn_bottom};
    border-radius: 5px; padding: 7px 12px; font-size: 13px;
    color: {c['text']};
}}
QLineEdit#v3Search:hover {{ background: {card}; }}
QLineEdit#v3Search:focus {{
    border: 1px solid {c['accent']};
    border-bottom: 2px solid {c['accent']};
}}

QListWidget#v3Results {{
    background: {card}; border: 1px solid {c['border']};
    border-radius: 8px; outline: none; padding: 4px;
}}
QListWidget#v3Results::item {{
    padding: 8px 10px; border-radius: 5px; color: {c['text']};
}}
QListWidget#v3Results::item:hover {{ background: {hover}; }}
QListWidget#v3Results::item:selected {{
    background: {c['accent_soft']}; color: {c['accent']};
}}

QScrollArea#v3NavScroll {{ background: transparent; border: none; }}
QScrollArea#v3NavScroll > QWidget {{ background: transparent; }}
QWidget#v3Nav {{ background: transparent; }}
QLabel#v3NavGroup {{
    font-size: 11px; font-weight: 600; color: {c['hint']};
    padding-left: 12px; padding-top: 4px; padding-bottom: 3px;
}}

/* ---------- 内容区 ---------- */
QWidget#v3Content {{ background: {bg}; }}
QWidget#v3Stack {{ background: {bg}; }}
QScrollArea#v3PageScroll {{ background: {bg}; border: none; }}
QScrollArea#v3PageScroll > QWidget {{ background: {bg}; }}
QWidget#v3PageInner {{ background: {bg}; }}
QScrollArea#marketScroll {{ background: {bg}; border: none; }}
QScrollArea#marketScroll > QWidget {{ background: {bg}; }}
QLabel#v3PageTitle {{ font-size: 26px; font-weight: 700; color: {c['text']}; }}
QLabel#v3PageSub {{ font-size: 12px; color: {c['hint']}; }}

QFrame#v3Footer {{
    background: {bg}; border: none;
    border-top: 1px solid {c['divider']};
}}

/* ---------- 卡片（Win11 分层：8px 圆角 + 几乎看不见的发丝描边） ---------- */
QFrame#v3Card {{
    background: {card}; border: 1px solid {card_border};
    border-radius: 8px;
}}
QLabel#v3CardTitle {{
    font-size: 13px; font-weight: 600; color: {c['text']};
    padding-bottom: 2px;
}}
QFrame#v3Divider {{ background: {c['divider']}; border: none; }}

/* ---------- 设置行 ---------- */
QWidget#v3Row {{ background: transparent; border-radius: 6px; }}
QWidget#v3Row[flash="true"] {{ background: {c['accent_soft']}; }}
QLabel#v3RowTitle {{ font-size: 13px; color: {c['text']}; }}
QLabel#v3SliderVal {{ font-size: 13px; color: {c['text']}; }}

/* ---------- 操作行（列表项 + ›，背景由 paintEvent 自绘） ---------- */
QLabel#v3LinkDanger {{ font-size: 13px; color: {c['danger']}; }}
QLabel#v3Chevron {{ font-size: 17px; color: {c['hint']}; }}

/* ---------- 输入控件（Win11：5px 圆角 + 底部描边） ---------- */
QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {inp}; border: 1px solid {c['border']};
    border-bottom: 1px solid {btn_bottom};
    border-radius: 5px; padding: 5px 10px; min-width: 112px;
    color: {c['text']}; font-size: 13px;
}}
QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover {{
    background: {card};
}}
QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border: 1px solid {c['accent']};
    border-bottom: 2px solid {c['accent']};
}}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{ width: 0; }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox QAbstractItemView {{
    background: {card}; color: {c['text']};
    border: 1px solid {c['border']}; border-radius: 6px;
    selection-background-color: {c['accent_soft']};
    selection-color: {c['accent']}; outline: none;
}}
QLineEdit {{
    background: {inp}; border: 1px solid {c['border']};
    border-bottom: 1px solid {btn_bottom};
    border-radius: 5px; padding: 5px 10px; color: {c['text']};
    font-size: 13px;
}}
QLineEdit:focus {{
    border: 1px solid {c['accent']};
    border-bottom: 2px solid {c['accent']};
}}
QDateEdit, QDateTimeEdit {{
    background: {inp}; border: 1px solid {c['border']};
    border-bottom: 1px solid {btn_bottom};
    border-radius: 5px; padding: 4px 9px; color: {c['text']};
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
QSlider::handle:horizontal:hover {{
    background: {c['accent_soft']};
}}
QSlider::handle:horizontal:pressed {{
    width: 14px; height: 14px; margin: -5px 0; border-radius: 7px;
}}

/* ---------- 按钮（Win11：标准按钮带底部描边，主按钮纯色） ---------- */
QPushButton {{
    background: {inp}; border: 1px solid {btn_border};
    border-bottom: 1px solid {btn_bottom};
    border-radius: 5px; padding: 6px 18px; font-size: 13px;
    color: {c['text']};
}}
QPushButton:hover {{ background: {hover}; }}
QPushButton:pressed {{ background: {c['pressed']}; color: {c['sub_text']}; }}
QPushButton:disabled {{ color: {c['hint']}; }}
QPushButton#primary {{
    background: {c['accent']}; color: #ffffff;
    border: none; font-weight: 600;
}}
QPushButton#primary:hover {{ background: {c['accent_hover']}; }}
QPushButton#primary:pressed {{ background: {c['accent']}; color: #e8e8e8; }}
QPushButton#ghost {{
    background: transparent; border: none;
    color: {c['hint']}; padding: 6px 10px;
}}
QPushButton#ghost:hover {{ color: {c['text']}; background: {hover}; }}
QPushButton[cardAction="true"] {{ padding: 4px 14px; font-size: 12px; }}

QCheckBox {{ color: {c['text']}; font-size: 13px; spacing: 8px;
            background: transparent; }}
QCheckBox::indicator {{
    width: 17px; height: 17px;
    border: 1px solid {c['sub_text']}; border-radius: 4px;
    background: transparent;
}}
QCheckBox::indicator:hover {{ border: 1px solid {c['accent']}; }}
QCheckBox::indicator:checked {{
    background: {c['accent']}; border: 1px solid {c['accent']};
}}

/* ---------- 关于页 ---------- */
QLabel#v3AboutLogo {{
    background: {c['accent_soft']}; border-radius: 13px; font-size: 28px;
}}
QLabel#v3AboutTitle {{ font-size: 19px; font-weight: 700; color: {c['text']}; }}
QLabel#v3AboutVer {{ font-size: 12px; color: {c['hint']}; }}

/* ---------- 插件市场（沿用其控件命名） ---------- */
QFrame#restartBanner {{
    background: {c['accent_soft']}; border: 1px solid {c['accent']};
    border-radius: 8px;
}}
QLabel#bannerText {{ color: {c['accent']}; font-size: 12px; }}
QFrame#marketCard {{
    background: {card}; border: 1px solid {c['divider']};
    border-radius: 8px;
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
    border-radius: 6px; color: {c['sub_text']}; font-size: 11px;
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
    border: 1px solid {c['divider']}; border-radius: 6px;
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
    border-radius: 6px; outline: none; padding: 4px; color: {c['text']};
}}
QListWidget::item {{ padding: 7px 8px; border-radius: 5px; }}
QListWidget::item:selected {{
    background: {c['accent_soft']}; color: {c['accent']};
}}

/* ---------- 滚动条（Win11 悬浮细条：6px 半透明，几乎隐形） ---------- */
QScrollBar:vertical {{
    background: transparent; width: 6px; margin: 3px 2px 3px 0;
}}
QScrollBar::handle:vertical {{
    background: {_rgba(c['scroll_handle'], 0.55)};
    border-radius: 3px; min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: {c['scroll_handle']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0; background: none;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
}}
QScrollBar:horizontal {{ height: 0; }}
"""
