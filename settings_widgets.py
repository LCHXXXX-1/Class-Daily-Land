from PySide6.QtCore import (Qt, QSize, QRectF, Property, QTimer, Signal,
                            QPropertyAnimation, QEasingCurve,
                            QAbstractAnimation)
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QAbstractButton, QFrame, QGraphicsOpacityEffect,
                               QLabel, QLineEdit, QPushButton, QVBoxLayout,
                               QWidget)

import theme


# ============================================================
# 动画开关
# ============================================================
class ToggleSwitch(QAbstractButton):
    """iOS / Fluent 风格开关。圆角轨道 + 平滑滑动圆钮。"""

    TRACK_W = 44
    TRACK_H = 24
    KNOB_PAD = 3

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self._knob = 0.0
        self._anim = None
        self._mute = False
        self.toggled.connect(self._on_toggled)

    # ---- Qt 属性：驱动圆钮位置 ----
    def _get_knob(self):
        return self._knob

    def _set_knob(self, v):
        self._knob = 0.0 if v < 0 else (1.0 if v > 1 else float(v))
        self.update()

    knob = Property(float, _get_knob, _set_knob)

    def sizeHint(self):
        return QSize(self.TRACK_W + 6, self.TRACK_H + 6)

    # ---- 外部无动画设置 ----
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
        self._anim.setDuration(150)
        self._anim.setStartValue(self._knob)
        self._anim.setEndValue(target)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.start()

    def _stop_anim(self):
        if self._anim is not None:
            self._anim.stop()
            self._anim.deleteLater()
            self._anim = None

    # ---- 绘制 ----
    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        on = self.isChecked()
        tw, th = self.TRACK_W, self.TRACK_H
        x = (self.width() - tw) / 2.0
        y = (self.height() - th) / 2.0
        track = QRectF(x, y, tw, th)

        if on:
            base = QColor(theme.color("accent_hover")
                          if self.underMouse() else theme.color("accent"))
            p.setPen(Qt.NoPen)
            p.setBrush(base)
            p.drawRoundedRect(track, th / 2, th / 2)
        else:
            p.setPen(QColor(theme.color("border")))
            p.setBrush(QColor(theme.color("input_bg")))
            p.drawRoundedRect(track, th / 2 - 0.5, th / 2 - 0.5)

        r = th / 2 - self.KNOB_PAD
        travel = tw - th
        cx = x + self.KNOB_PAD + travel * self._knob
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#ffffff") if on else QColor(theme.color("hint")))
        p.drawEllipse(QRectF(cx, y + self.KNOB_PAD, 2 * r, 2 * r))
        p.end()


# ============================================================
# 分段选择器
# ============================================================
class SegmentedControl(QWidget):
    """分段选择器：选中项下方 / 后方指示块平滑移动。"""

    changed = Signal(object)

    PAD = 3

    def __init__(self, options, parent=None):
        super().__init__(parent)
        self._options = list(options)      # [(label, value)]
        self._index = 0
        self._pos = 0.0
        self._anim = None
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(34)
        self.setMinimumWidth(44 * len(self._options) + 8)

    # ---- Qt 属性：驱动指示块位置（以段为单位） ----
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
        self._anim.setDuration(180)
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
        p.setPen(QColor(theme.color("border")))
        p.setBrush(QColor(theme.color("input_bg")))
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 8, 8)

        seg_w = (w - 2 * self.PAD) / n
        ix = self.PAD + seg_w * self._pos
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.color("accent_soft")))
        p.drawRoundedRect(
            QRectF(ix, self.PAD, seg_w, h - 2 * self.PAD), 6, 6)

        f = QFont(self.font())
        f.setPixelSize(13)
        for i, (label, _v) in enumerate(self._options):
            f.setBold(i == self._index)
            p.setFont(f)
            p.setPen(QColor(theme.color("accent") if i == self._index
                            else theme.color("sub_text")))
            p.drawText(QRectF(self.PAD + seg_w * i, 0, seg_w, h),
                       Qt.AlignCenter, str(label))
        p.end()


# ============================================================
# 卡片 / 徽章 / 动画播放器
# ============================================================
class SectionCard(QFrame):
    """一组设置项的卡片容器。"""

    def __init__(self, title="", subtitle="", parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(6)
        self.body = lay
        if title:
            lbl = QLabel(title)
            lbl.setObjectName("sectionTitle")
            lay.addWidget(lbl)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setObjectName("hint")
            sub.setWordWrap(True)
            lay.addWidget(sub)
        if title or subtitle:
            lay.addSpacing(2)

    def add_widget(self, w):
        self.body.addWidget(w)
        return w


class Badge(QLabel):
    """状态徽章（插件市场状态）。"""

    KINDS = {
        "not_installed": "hint",
        "installed": "success",
        "update": "accent",
        "disabled": "warn",
        "failed": "danger",
        # 索引记录本身有问题（sha256/版本/地址不合法）：照样渲染出来，
        # 只是装不了，并在卡片上写清原因
        "invalid": "danger",
    }

    def __init__(self, kind="not_installed", text="", parent=None):
        super().__init__(text, parent)
        self._kind = kind
        self.set_status(kind, text or None)

    def set_status(self, kind, text=None):
        if kind not in self.KINDS:
            kind = "not_installed"
        self._kind = kind
        if text is not None:
            self.setText(text)
        color = theme.color(self.KINDS[kind])
        self.setStyleSheet(
            f"color:{color}; border:1px solid {color}; border-radius:9px;"
            "padding:1px 9px; font-size:11px; font-weight:600;"
            "background:transparent;")


class BusySpinner(QWidget):
    """旋转的加载指示器（自动跟随主题色）；用 QPropertyAnimation 无限循环。"""

    def __init__(self, parent=None, size=16, thickness=2):
        super().__init__(parent)
        self._size = int(size)
        self._thickness = int(thickness)
        self._angle = 0.0
        self.setFixedSize(self._size + 6, self._size + 6)
        self._anim = QPropertyAnimation(self, b"angle", self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(360.0)
        self._anim.setDuration(900)
        self._anim.setLoopCount(-1)
        self._anim.setEasingCurve(QEasingCurve.Linear)
        self.setVisible(False)

    def _get_angle(self):
        return self._angle

    def _set_angle(self, v):
        self._angle = float(v)
        self.update()

    angle = Property(float, _get_angle, _set_angle)

    def start(self):
        if not self.isVisible():
            self.setVisible(True)
        if self._anim.state() != QAbstractAnimation.Running:
            self._anim.start()

    def stop(self):
        self._anim.stop()
        self.setVisible(False)

    def is_spinning(self):
        return self._anim.state() == QAbstractAnimation.Running

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pad = 3
        rect = QRectF(pad, pad, self.width() - 2 * pad, self.height() - 2 * pad)
        p.setPen(QPen(QColor(theme.color("border")), self._thickness,
                      Qt.SolidLine, Qt.RoundCap))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(rect)
        p.setPen(QPen(QColor(theme.color("accent")), self._thickness,
                      Qt.SolidLine, Qt.RoundCap))
        p.drawArc(rect, int(-self._angle * 16), int(110 * 16))
        p.end()


class StaggerPlayer:
    """列表错峰进场动画。

    - 淡入：透明度 0 → 1
    - 展开（unfold=True）：同时把 maximumHeight 0 → 目标高度，产生「卡片展开」效果
    动画结束即摘除透明度特效并恢复高度上限，避免滚动残影 / 裁剪。
    """

    MAX_H = 16777215

    def __init__(self, duration=240, step=48, delay=0, unfold=False):
        self.duration = duration
        self.step = step
        self.delay = delay
        self.unfold = unfold

    def play(self, widgets):
        widgets = [w for w in widgets if w is not None]
        if self.duration <= 0:
            for w in widgets:
                self._clear(w)
            return
        for i, w in enumerate(widgets):
            eff = self._effect(w)
            eff.setOpacity(0.0)
            end_h = None
            if self.unfold and not w.property("noUnfold"):
                h = w.sizeHint().height()
                if h > 4:
                    w.setMaximumHeight(0)
                    end_h = h
            QTimer.singleShot(
                self.delay + i * self.step,
                lambda w=w, e=eff, h=end_h: self._enter(w, e, h))

    @staticmethod
    def _effect(w):
        eff = w.graphicsEffect()
        if not isinstance(eff, QGraphicsOpacityEffect):
            eff = QGraphicsOpacityEffect(w)
            w.setGraphicsEffect(eff)
        return eff

    @staticmethod
    def _clear(w):
        try:
            eff = w.graphicsEffect()
            if isinstance(eff, QGraphicsOpacityEffect):
                w.setGraphicsEffect(None)
        except RuntimeError:
            pass

    def _enter(self, w, eff, end_h):
        try:
            if w.graphicsEffect() is not eff:
                return
        except RuntimeError:
            return
        if end_h is not None:
            self._unfold(w, end_h)
        a = QPropertyAnimation(eff, b"opacity", w)
        a.setDuration(self.duration)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.setEasingCurve(QEasingCurve.OutCubic)
        a.finished.connect(lambda w=w: self._clear(w))
        a.start(QAbstractAnimation.DeleteWhenStopped)

    def _unfold(self, w, end_h):
        # 先停掉同属性上的旧动画，避免快速切页时互相打架
        for child in w.findChildren(QPropertyAnimation):
            try:
                if child.propertyName() == b"maximumHeight":
                    child.stop()
            except RuntimeError:
                pass
        a = QPropertyAnimation(w, b"maximumHeight", w)
        a.setDuration(self.duration + 60)
        a.setStartValue(0)
        a.setEndValue(end_h)
        a.setEasingCurve(QEasingCurve.OutCubic)
        a.finished.connect(lambda w=w: w.setMaximumHeight(self.MAX_H))
        a.start(QAbstractAnimation.DeleteWhenStopped)

    @staticmethod
    def fade(widget, duration=200, delay=0, start=0.0, end=1.0):
        """单个控件的淡入（可延迟）。"""
        if widget is None:
            return
        eff = StaggerPlayer._effect(widget)
        eff.setOpacity(start)

        def _go():
            try:
                if widget.graphicsEffect() is not eff:
                    return
            except RuntimeError:
                return
            a = QPropertyAnimation(eff, b"opacity", widget)
            a.setDuration(duration)
            a.setStartValue(start)
            a.setEndValue(end)
            a.setEasingCurve(QEasingCurve.OutCubic)
            a.finished.connect(lambda w=widget: StaggerPlayer._clear(w)
                               if end >= 1.0 else None)
            a.start(QAbstractAnimation.DeleteWhenStopped)

        if delay > 0:
            QTimer.singleShot(delay, _go)
        else:
            _go()



# ============================================================
# 左侧导航
# ============================================================
class NavRail(QWidget):
    """导航按钮 + 选中项背后平滑滑动的高亮块。"""

    item_clicked = Signal(int)

    BTN_H = 40
    GAP = 4

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("navRail")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 2, 10, 2)
        lay.setSpacing(self.GAP)
        self._lay = lay
        self._buttons = []

        # 高亮块：先创建 → 位于按钮之下
        self._pill = QFrame(self)
        self._pill.setObjectName("navPill")
        self.restyle()

    def add_item(self, icon, title):
        idx = len(self._buttons)
        btn = QPushButton(f"  {icon}   {title}", self)
        btn.setObjectName("navButton")
        btn.setCheckable(True)
        btn.setAutoExclusive(True)
        btn.setFixedHeight(self.BTN_H)
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(lambda _=False, i=idx: self.item_clicked.emit(i))
        self._lay.addWidget(btn)
        self._buttons.append(btn)
        return idx

    def count(self):
        return len(self._buttons)

    def items(self):
        return list(self._buttons)

    def restyle(self):
        self._pill.setStyleSheet(
            f"background:{theme.color('accent_soft')};"
            "border:none;border-radius:8px;")

    def select(self, idx, animate=True):
        if not (0 <= idx < len(self._buttons)):
            return
        btn = self._buttons[idx]
        btn.setChecked(True)
        target = btn.geometry()
        self._pill.raise_()
        for b in self._buttons:
            b.raise_()
        old = getattr(self, "_pill_anim", None)
        if old is not None:
            try:
                old.stop()
            except RuntimeError:
                pass
            self._pill_anim = None
        if not animate:
            self._pill.setGeometry(target)
            return
        self._pill_anim = QPropertyAnimation(self._pill, b"geometry",
                                             self._pill)
        self._pill_anim.setDuration(160)
        self._pill_anim.setStartValue(self._pill.geometry())
        self._pill_anim.setEndValue(target)
        self._pill_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._pill_anim.start()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        idx = next((i for i, b in enumerate(self._buttons)
                    if b.isChecked()), 0)
        if self._buttons:
            self._pill.setGeometry(self._buttons[idx].geometry())


class SearchBox(QLineEdit):
    """设置搜索框。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("searchBox")
        self.setPlaceholderText("搜索设置…")
        self.setClearButtonEnabled(True)


# ============================================================
# 现代对话框通用助手
# ============================================================
def apply_modern_dialog(dlg):
    """给普通对话框套用新界面样式（圆角卡片、控件、表格，浅/深色自适应）。"""
    dlg.setObjectName("settingsDialog")
    dlg.setStyleSheet(theme.settings_qss())

    def _retheme():
        try:
            dlg.setStyleSheet(theme.settings_qss())
            for w in dlg.findChildren(QWidget):
                w.style().unpolish(w)
                w.style().polish(w)
            dlg.style().unpolish(dlg)
            dlg.style().polish(dlg)
        except Exception:
            pass

    dlg._theme_cb = _retheme          # 强引用，避免弱引用立即回收
    theme.theme_changed_connect(_retheme)
    return dlg


def play_entrance(widgets, unfold=False, delay=30):
    """对话框打开时的错峰入场动画（轻量：默认只淡入）。"""
    StaggerPlayer(duration=180, step=36, delay=delay,
                  unfold=unfold).play(widgets)

