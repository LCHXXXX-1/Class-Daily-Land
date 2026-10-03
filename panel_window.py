import time

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import (Qt, QTimer, QPropertyAnimation, QEasingCurve, QRect,
                            QAbstractAnimation)
from PySide6.QtGui import (QPainter, QColor, QPainterPath, QFont,
                           QLinearGradient)

PANEL_FADE_MS = 160

# 触屏滑动：位移超过阈值才算拖动，松手够快就带一段惯性
DRAG_START_PX = 6
FLICK_MIN_SPEED = 0.25        # px/ms，松手时低于它就当场停住
FLICK_DECAY = 0.92            # 惯性每帧剩多少速度
FLICK_FRAME_MS = 16
FLICK_STOP_SPEED = 0.05


class PanelWindow(QWidget):
    """独立面板窗口，从高度 0 长到目标高度，可选淡入/淡出。"""

    def __init__(self, width, height, fade=False, duration=240):
        super().__init__()
        self.w = width
        self.target_h = height
        self.fade = bool(fade)
        self._base_x = 0
        self._base_y = 0
        self._scroll_offset = 0
        self._text = ""
        # 触屏滑动：拖动面板滚内容，回调由灵动岛注入（返回真正生效的位移）
        self._drag_target = None
        self._drag_y = None
        self._dragging = False
        self._last_y = None
        self._last_t = 0.0
        self._velocity = 0.0
        self._flick_timer = QTimer(self)
        self._flick_timer.setInterval(FLICK_FRAME_MS)
        self._flick_timer.timeout.connect(self._flick_tick)

        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool |
            Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self.anim = QPropertyAnimation(self, b"geometry")
        self.anim.setDuration(max(80, int(duration)))
        self.anim.setEasingCurve(QEasingCurve.OutCubic)

    def set_content(self, text):
        self._text = text
        self.update()

    def place(self, x, y_top):
        self._base_x = x
        self._base_y = y_top
        self._apply_geometry()

    def set_scroll(self, offset):
        self._scroll_offset = offset
        self._apply_geometry()

    def set_drag_target(self, fn):
        """注入滚动回调：fn(dy) 返回真正生效的位移（px）。

        返回 0 说明已经滑到头了，这时候手指的位移先攒着不算，
        回头反向拖能立刻跟上（就是 overscroll 的手感）。
        """
        self._drag_target = fn

    # ---------- 触屏滑动 ----------
    def _scroll_by(self, dy):
        if self._drag_target is None or not dy:
            return 0
        try:
            return int(self._drag_target(int(dy)))
        except Exception:
            return 0

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._drag_target is not None:
            self._flick_timer.stop()
            self._drag_y = event.position().y()
            self._last_y = self._drag_y
            self._last_t = time.monotonic()
            self._velocity = 0.0
            self._dragging = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_y is None:
            super().mouseMoveEvent(event)
            return
        y = event.position().y()
        if not self._dragging:
            if abs(y - self._drag_y) < DRAG_START_PX:
                return                     # 手指轻微抖，不算滑动
            self._dragging = True
        now = time.monotonic()
        dt = max(1.0, (now - self._last_t) * 1000.0)
        self._velocity = (y - self._last_y) / dt
        self._last_y = y
        self._last_t = now

        wanted = y - self._drag_y
        moved = self._scroll_by(wanted)
        if moved:
            # 没被吃掉的位移留下来，反向拖时手感才跟得上
            self._drag_y = y - (wanted - moved)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drag_y is not None:
            dragged = self._dragging
            idle = time.monotonic() - self._last_t
            self._drag_y = None
            self._dragging = False
            if (dragged and idle < 0.15
                    and abs(self._velocity) >= FLICK_MIN_SPEED):
                self._flick_timer.start()      # 松得快 → 甩起来滑一段
            else:
                self._velocity = 0.0
        super().mouseReleaseEvent(event)

    def _flick_tick(self):
        """松手后的惯性：按松手速度继续滑，慢慢减速停下。"""
        moved = self._scroll_by(self._velocity * FLICK_FRAME_MS)
        self._velocity *= FLICK_DECAY
        if not moved or abs(self._velocity) < FLICK_STOP_SPEED:
            self._velocity = 0.0
            self._flick_timer.stop()

    def _apply_geometry(self):
        y = self._base_y + self._scroll_offset
        self.setGeometry(self._base_x, y, self.w, self.target_h)

    def _start_opacity(self, start, end):
        if not self.fade:
            return
        a = QPropertyAnimation(self, b"windowOpacity", self)
        a.setDuration(PANEL_FADE_MS)
        a.setEasingCurve(QEasingCurve.OutCubic)
        a.setStartValue(start)
        a.setEndValue(end)
        a.start(QAbstractAnimation.DeleteWhenStopped)

    def animate_in(self):
        self.show()
        y = self._base_y + self._scroll_offset
        self.anim.stop()
        # 起始位置下沉 6px，展开时轻微上浮，增强弹性
        self.anim.setStartValue(QRect(self._base_x, y + 6, self.w, 0))
        self.anim.setEndValue(QRect(self._base_x, y, self.w, self.target_h))
        self._start_opacity(0.0, 1.0)
        self.anim.start()

    def animate_out(self, on_done=None):
        self.anim.stop()
        try:
            self.anim.finished.disconnect()
        except Exception:
            pass
        # 从当前实际几何收起，避免展开途中被打断时先跳到满高
        cur = self.geometry()
        self.anim.setStartValue(cur)
        self.anim.setEndValue(QRect(cur.x(), cur.y(), cur.width(), 0))
        if on_done:
            self.anim.finished.connect(on_done)
        self._start_opacity(1.0, 0.0)
        self.anim.start()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 8, 8)
        p.fillPath(path, QColor("#1c1c1e"))

        if not self._text:
            return

        font = QFont("Microsoft YaHei UI")
        font.setPixelSize(13)
        p.setFont(font)
        p.setPen(QColor("#e6e6e6"))

        margin = 12
        rect = self.rect().adjusted(margin, margin, -margin, -margin)
        p.drawText(rect, Qt.AlignTop | Qt.AlignLeft | Qt.TextWordWrap,
                   self._text)


class FadeMask(QWidget):
    """底部渐变遮罩，暗示"下面还有内容" """

    def __init__(self, width, height=24):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool |
            Qt.WindowDoesNotAcceptFocus |
            Qt.WindowTransparentForInput
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.resize(width, height)

    def paintEvent(self, event):
        p = QPainter(self)
        grad = QLinearGradient(0, 0, 0, self.height())
        grad.setColorAt(0.0, QColor(28, 28, 30, 0))
        grad.setColorAt(1.0, QColor(28, 28, 30, 255))
        p.fillRect(self.rect(), grad)
