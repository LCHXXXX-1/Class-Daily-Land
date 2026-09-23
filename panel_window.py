from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QRect
from PySide6.QtGui import (QPainter, QColor, QPainterPath, QFont,
                           QLinearGradient)


class PanelWindow(QWidget):
    """独立面板窗口，从高度 0 长到目标高度"""

    def __init__(self, width, height):
        super().__init__()
        self.w = width
        self.target_h = height
        self._base_x = 0
        self._base_y = 0
        self._scroll_offset = 0
        self._text = ""

        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool |
            Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self.anim = QPropertyAnimation(self, b"geometry")
        self.anim.setDuration(240)
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

    def _apply_geometry(self):
        y = self._base_y + self._scroll_offset
        self.setGeometry(self._base_x, y, self.w, self.target_h)

    def animate_in(self):
        self.show()
        y = self._base_y + self._scroll_offset
        self.anim.stop()
        self.anim.setStartValue(QRect(self._base_x, y, self.w, 0))
        self.anim.setEndValue(QRect(self._base_x, y, self.w, self.target_h))
        self.anim.start()

    def animate_out(self, on_done=None):
        self.anim.stop()
        y = self._base_y + self._scroll_offset
        self.anim.setStartValue(QRect(self._base_x, y, self.w, self.target_h))
        self.anim.setEndValue(QRect(self._base_x, y, self.w, 0))
        if on_done:
            self.anim.finished.connect(on_done)
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