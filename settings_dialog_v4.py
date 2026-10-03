"""设置窗口 V4 —— 与 Windows 11「设置」1:1 的二级导航设计。

相对 V3 的变化：
- 窗口默认 1218×717（与 Win11 设置默认尺寸一致），最小 940×600
- 搜索框移到窗口顶部居中（原生位置），侧栏只留纯导航（去掉分组标签）
- 二级页面：课表编辑器 / 课表管理 / 周末作息 / 假期与调休 /
  值日生名单 / 状态测试 / 插件市场 / 第三方包管理 / 插件设置页
  全部收进设置窗口，顶部左侧圆形返回键 + 面包屑，不再弹独立窗口
- 主窗口的「作业编辑」也收进来（顶级导航「作业」）
- 去掉底部栏（原生没有）；提示改为右下角浮层 toast
- 链接卡片带左侧矢量图标（原生链接卡样式）
- 浅色 / 深色 / Win11 云母 / Win10 自绘圆角窗框，全部沿用 V3 的机制

功能与旧设置界面一致，入口签名保持不变：

    from settings_dialog_v4 import SettingsDialog
    SettingsDialog(settings, schedule_manager=..., plugin_manager=...,
                   controller=..., on_apply=..., parent=...)
"""
import os
import sys

from PySide6.QtCore import (Qt, QEvent, QTimer, QPoint, QRect, QRectF, QSize,
                            QPropertyAnimation, QEasingCurve,
                            QAbstractAnimation, QParallelAnimationGroup,
                            QSequentialAnimationGroup, Property)
from PySide6.QtGui import (QColor, QFont, QGuiApplication, QPainter, QPen,
                           QPixmap, QCursor, QPainterPath)
from PySide6.QtWidgets import (QAbstractButton, QApplication, QDialog,
                               QFileDialog, QFrame, QGraphicsDropShadowEffect,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPushButton,
                               QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

from ui_common import (setup_dialog_style as _setup_dialog_style,
                       apply_window_material, disable_mica, set_dark_titlebar,
                       setup_touch_scroll)

import theme
from about import get_version
from utils import (APP_NAME, is_windows_11, windows_display_name,
                   set_window_icon)
from settings_manager import DEFAULTS
from settings_widgets import StaggerPlayer

# 复用 V3 的整套 Fluent 控件库与材质机制
from settings_dialog_v3 import (
    PageStack, SettingCard, SettingRow, RowWidget, LinkRow, FluentNav,
    SearchLineEdit,
    draw_fluent_icon, VECTOR_ICONS, EMOJI_FAMILIES,
    _rgba, _qcolor, _app_pixmap, _v3_qss, _TitleBar)


# ============================================================
# 副岛 → 设置窗口 的形变过渡
# ============================================================
class _MorphOverlay(QWidget):
    """从灵动岛/副岛的胶囊几何形变滑动到设置窗口的过渡层。
    深色胶囊一边滑向窗口位置一边长大、圆角从全圆收成 8px，
    到位后淡出，真正的设置窗口同时淡入。"""

    DURATION = 300

    def __init__(self, start_rect, end_rect, on_done):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool |
                            Qt.WindowStaysOnTopHint |
                            Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self._on_done = on_done
        self._progress = 0.0

        self.setGeometry(start_rect)
        self.show()
        self.raise_()

        a_geo = QPropertyAnimation(self, b"geometry", self)
        a_geo.setDuration(self.DURATION)
        a_geo.setStartValue(start_rect)
        a_geo.setEndValue(end_rect)
        a_geo.setEasingCurve(QEasingCurve.OutCubic)

        a_r = QPropertyAnimation(self, b"progress", self)
        a_r.setDuration(self.DURATION)
        a_r.setStartValue(0.0)
        a_r.setEndValue(1.0)
        a_r.setEasingCurve(QEasingCurve.OutCubic)

        self._group = QParallelAnimationGroup(self)
        self._group.addAnimation(a_geo)
        self._group.addAnimation(a_r)
        self._group.finished.connect(self._finish)
        self._group.start(QAbstractAnimation.DeleteWhenStopped)

    def _get_progress(self):
        return self._progress

    def _set_progress(self, v):
        self._progress = float(v)
        self.update()

    progress = Property(float, _get_progress, _set_progress)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        # 圆角：胶囊（h/2）→ 窗口圆角（8）
        radius = self.height() / 2 + (8 - self.height() / 2) * self._progress
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), radius, radius)
        # 颜色：灵动岛深黑 → 轻微提亮，避免生硬
        base = QColor("#1c1c1e")
        base.setAlphaF(0.96 - 0.25 * self._progress)
        p.fillPath(path, base)
        p.end()

    def _finish(self):
        cb, self._on_done = self._on_done, None
        # 自身快速淡出后销毁
        a = QPropertyAnimation(self, b"windowOpacity", self)
        a.setDuration(120)
        a.setStartValue(1.0)
        a.setEndValue(0.0)
        a.finished.connect(self.close)
        a.finished.connect(self.deleteLater)
        a.start(QAbstractAnimation.DeleteWhenStopped)
        if cb is not None:
            cb()


# ============================================================
# 返回键（原生：顶栏左侧圆形按钮）
# ============================================================
class BackButton(QAbstractButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("v4Back")
        self.setFixedSize(32, 32)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("返回")

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self.underMouse() or self.isDown():
            if theme.is_dark():
                p.setBrush(_qcolor("#ffffff",
                                   0.08 if self.isDown() else 0.05))
            else:
                p.setBrush(_qcolor("#000000",
                                   0.07 if self.isDown() else 0.04))
            p.setPen(Qt.NoPen)
            p.drawEllipse(self.rect())
        draw_fluent_icon(p, self.rect().adjusted(8, 8, -8, -8),
                         "back", QColor(theme.color("text")))
        p.end()


# ============================================================
# 设置窗口
# ============================================================
class SettingsDialog(QDialog):

    COMPACT_WIDTH = 980          # 小于此宽度时侧栏收成纯图标栏

    def __init__(self, settings, schedule_manager=None,
                 plugin_manager=None, controller=None, on_apply=None,
                 parent=None, morph_from=None):
        super().__init__(parent)
        self.settings = settings
        self.schedule = schedule_manager
        self.plugin_manager = plugin_manager
        self.controller = controller
        self.on_apply = on_apply
        # 打开时的形变起点（副岛/灵动岛的全局矩形，None = 普通淡入）
        self._morph_from = morph_from
        self._morph_overlay = None

        self.rows = []
        self.pages = []            # 全部页面（含二级页）
        self.nav_pages = []        # 顶级导航页
        self.cards = []
        self._search_index = []
        self._opened = False
        self._compact = False
        self._suppress_search = False
        self._last_page = 0
        self._results_idx = -1
        self._test_seconds = int(self.settings.get("island_countdown_sec", 60))
        self.market_page = None
        self.package_page = None
        self._embedded = []        # 内嵌的对话框（保活）

        # Windows 11 云母（Mica）材质
        self.win11 = is_windows_11()
        self._mica_active = bool(self.win11 and
                                 self.settings.get("settings_mica", True))

        # Windows 10：无边框 + 自绘圆角窗框
        self._custom_chrome = bool(sys.platform == "win32" and not self.win11)

        self.setObjectName("settingsV4")
        self.setWindowTitle("设置")
        self.resize(1218, 717)                     # 与 Win11 设置同尺寸
        self.setMinimumSize(940, 600)
        self._center_on_screen()
        if self._morph_from is not None:
            # 形变过渡期间窗口先隐形，避免第一帧闪现
            self.setWindowOpacity(0.0)
        if self._custom_chrome:
            self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
            self.setAttribute(Qt.WA_TranslucentBackground, True)
            set_window_icon(self)
        else:
            _setup_dialog_style(self, translucent=self._mica_active)
        self._apply_qss()
        if self._mica_active:
            ok = apply_window_material(self, mica=True, dark=theme.is_dark())
            if not ok:
                self._mica_active = False
                self.setAttribute(Qt.WA_TranslucentBackground, False)
                disable_mica(self)
                self._apply_qss()
        theme.theme_changed_connect(self._on_theme_changed)

        self._build_root()
        self._build_pages()
        self._build_results_page()
        self._build_nav()
        self._apply_card_shadows()

    # ==================================================
    # 样式
    # ==================================================
    def _center_on_screen(self):
        """把窗口摆到鼠标所在屏幕的正中央（Win11 设置的开窗位置）。"""
        try:
            screen = QGuiApplication.screenAt(QCursor.pos()) \
                or QGuiApplication.primaryScreen()
            geo = screen.availableGeometry()
            self.move(geo.center() - self.rect().center())
        except Exception:
            pass

    @property
    def _translucent(self):
        """窗口是透明的（云母或 Win10 自绘窗框）。
        透明窗里的 QGraphicsEffect（投影/透明度）会在重绘时留下
        黑色残影，这类窗口下一律不用栅格特效。"""
        return bool(self._mica_active or self._custom_chrome)

    def _apply_qss(self):
        self.setStyleSheet(_v4_qss(glass=self._mica_active,
                                   chrome=self._custom_chrome))

    def _apply_card_shadows(self):
        if self._translucent:
            # 透明窗里的投影特效会产生黑色残影，用发丝描边分层即可
            for card in self.cards:
                try:
                    card.setGraphicsEffect(None)
                except RuntimeError:
                    pass
            return
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

        # Win10 自绘窗框
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

    def _build_sidebar(self):
        bar = QFrame()
        bar.setObjectName("v3Sidebar")
        bar.setFixedWidth(264)
        lay = QVBoxLayout(bar)
        lay.setContentsMargins(10, 66, 10, 12)   # 顶部让位，与搜索条对齐
        lay.setSpacing(0)

        self.nav_scroll = QScrollArea()
        self.nav_scroll.setObjectName("v3NavScroll")
        self.nav_scroll.setWidgetResizable(True)
        self.nav_scroll.setFrameShape(QFrame.NoFrame)
        self.nav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.nav = FluentNav()
        self.nav.item_clicked.connect(self._on_nav_clicked)
        self.nav_scroll.setWidget(self.nav)
        lay.addWidget(self.nav_scroll, 1)
        setup_touch_scroll(self.nav_scroll, mouse_drag=True)
        return bar

    def _build_content(self):
        wrap = QFrame()
        wrap.setObjectName("v3Content")
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.stack = PageStack()
        # 透明窗不用透明度特效，页面切换只位移动画（防黑色残影）
        self.stack.fade_enabled = not self._translucent
        lay.addWidget(self.stack, 1)

        # 顶栏：返回键（左）+ 居中搜索框（原生布局）。
        # 用绝对定位浮在内容区上方，进插件页时整条「滑下来」。
        self._strip = QFrame(wrap)
        self._strip.setObjectName("v4Strip")
        strip = QHBoxLayout(self._strip)
        strip.setContentsMargins(16, 8, 16, 4)
        strip.setSpacing(8)
        self.btn_back = BackButton()
        self.btn_back.clicked.connect(self._go_back)
        self.btn_back.hide()
        back_holder = QWidget()
        back_holder.setFixedWidth(40)
        bh = QHBoxLayout(back_holder)
        bh.setContentsMargins(0, 0, 0, 0)
        bh.addWidget(self.btn_back, 0, Qt.AlignVCenter)
        strip.addWidget(back_holder)
        strip.addStretch(1)

        self.search = SearchLineEdit(self._strip)
        self.search.setObjectName("v4SearchTop")
        self.search.setPlaceholderText("查找设置")
        self.search.setFixedSize(440, 32)
        self.search.textChanged.connect(self._on_search)
        if not self._translucent:
            se = QGraphicsDropShadowEffect(self.search)
            se.setBlurRadius(14)
            se.setXOffset(0)
            se.setYOffset(1)
            se.setColor(QColor(0, 0, 0, 14 if not theme.is_dark() else 50))
            self.search.setGraphicsEffect(se)
            self._search_shadow = se
        else:
            self._search_shadow = None
        strip.addWidget(self.search)
        strip.addStretch(1)
        spacer = QWidget()
        spacer.setFixedWidth(40)
        strip.addWidget(spacer)
        self._strip.raise_()

        # 右下角浮层提示（替代原来的底栏）
        self.toast = QLabel("", self)
        self.toast.setObjectName("v4Toast")
        self.toast.hide()
        return wrap

    STRIP_H = 44

    def _layout_strip(self):
        """顶栏几何：浮在内容区顶部；页面堆栈给它让出上边界。"""
        if not hasattr(self, "_strip"):
            return
        w = self.content.width()
        if self._strip.y() < 0:
            # 正在播滑下动画，只更新宽度
            self._strip.resize(w, self.STRIP_H)
        else:
            self._strip.setGeometry(0, 0, w, self.STRIP_H)
        self.stack.setContentsMargins(0, self.STRIP_H, 0, 0)

    def _slide_strip_down(self):
        """顶栏从窗口上缘滑下来（进入插件页的过渡）。"""
        if self._translucent:
            # 透明窗位移动画没问题（无栅格特效），照常播
            pass
        strip = self._strip
        w = self.content.width()
        strip.setGeometry(0, -self.STRIP_H, w, self.STRIP_H)
        a = QPropertyAnimation(strip, b"geometry", self)
        a.setDuration(230)
        a.setStartValue(QRect(0, -self.STRIP_H, w, self.STRIP_H))
        a.setEndValue(QRect(0, 0, w, self.STRIP_H))
        a.setEasingCurve(QEasingCurve.OutCubic)
        a.finished.connect(self._layout_strip)
        a.start(QAbstractAnimation.DeleteWhenStopped)
        self._strip_anim = a

    # ==================================================
    # Win10 自绘窗框（与 V3 相同机制）
    # ==================================================
    def _update_chrome_state(self):
        if not self._custom_chrome:
            return
        maxed = self.isMaximized()
        if maxed:
            self._outer_lay.setContentsMargins(0, 0, 0, 0)
        else:
            self._outer_lay.setContentsMargins(14, 14, 14, 14)
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
                import ctypes
                from ctypes import wintypes
                if bytes(eventType) != b"windows_generic_MSG":
                    return super().nativeEvent(eventType, message)
                msg = wintypes.MSG.from_address(int(message))
                WM_NCHITTEST = 0x0084
                WM_GETMINMAXINFO = 0x0024
                if msg.message == WM_NCHITTEST and not self.isMaximized():
                    border = 6
                    gx = msg.lParam & 0xFFFF
                    gy = (msg.lParam >> 16) & 0xFFFF
                    if gx >= 32768:
                        gx -= 65536
                    if gy >= 32768:
                        gy -= 65536
                    pos = self.mapFromGlobal(QPoint(gx, gy))
                    x, y = pos.x(), pos.y()
                    w, h = self.width(), self.height()
                    left = x < border
                    right = x >= w - border
                    top = y < border
                    bottom = y >= h - border
                    if top and left:
                        return True, 13
                    if top and right:
                        return True, 14
                    if bottom and left:
                        return True, 16
                    if bottom and right:
                        return True, 17
                    if left:
                        return True, 10
                    if right:
                        return True, 11
                    if top:
                        return True, 12
                    if bottom:
                        return True, 15
                elif msg.message == WM_GETMINMAXINFO:
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
                    monitor = ctypes.windll.user32.MonitorFromWindow(
                        ctypes.c_void_p(int(self.winId())), 2)
                    if monitor:
                        mi = MONITORINFO()
                        mi.cbSize = ctypes.sizeof(MONITORINFO)
                        if ctypes.windll.user32.GetMonitorInfoW(
                                ctypes.c_void_p(monitor), ctypes.byref(mi)):
                            info = MINMAXINFO.from_address(msg.lParam)
                            work, mon = mi.rcWork, mi.rcMonitor
                            info.ptMaxSize.x = work.right - work.left
                            info.ptMaxSize.y = work.bottom - work.top
                            info.ptMaxPosition.x = work.left - mon.left
                            info.ptMaxPosition.y = work.top - mon.top
                            return True, 0
            except Exception:
                pass
        return super().nativeEvent(eventType, message)

    # ==================================================
    # 紧凑模式
    # ==================================================
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._set_compact(self.width() < self.COMPACT_WIDTH)
        self._layout_strip()
        self._reposition_toast()

    def _set_compact(self, on):
        on = bool(on)
        if on == self._compact:
            return
        self._compact = on
        self.sidebar.setFixedWidth(64 if on else 264)
        self.search.setFixedWidth(240 if on else 440)
        self.nav.set_compact(on)

    # ==================================================
    # 页面骨架
    # ==================================================
    def _make_page(self, title, parent=None):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(36, 10, 24, 6)
        v.setSpacing(4)

        crumb = QLabel("")
        crumb.setObjectName("v4Crumb")
        crumb.setVisible(parent is not None)
        v.addWidget(crumb)
        page._crumb_lbl = crumb

        t = QLabel(title)
        t.setObjectName("v3PageTitle")
        v.addWidget(t)
        v.addSpacing(10)

        scroll = QScrollArea()
        scroll.setObjectName("v3PageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        inner = QWidget()
        inner.setObjectName("v3PageInner")
        il = QVBoxLayout(inner)
        il.setContentsMargins(2, 2, 10, 24)
        il.setSpacing(6)               # 原生索引卡间距很紧
        il.setAlignment(Qt.AlignTop)
        scroll.setWidget(inner)
        v.addWidget(scroll, 1)
        setup_touch_scroll(scroll, mouse_drag=False)

        page._inner = inner
        page._inner_layout = il
        page._scroll = scroll
        page._anim = []
        page._info = {"icon": "", "title": title, "widget": page,
                      "anim": page._anim, "index": -1, "parent": parent,
                      "nav_index": -1}
        return page

    def _register_page(self, icon, title, page, parent=None, in_nav=True):
        info = page._info
        info["icon"] = icon
        info["title"] = title
        info["parent"] = parent
        info["index"] = len(self.pages)
        if parent is not None:
            # 面包屑显示完整路径：课表与提醒 › 课表管理 › 课表编辑器
            chain = []
            node = parent
            while node is not None:
                chain.append(node["title"])
                node = node.get("parent")
            chain.reverse()
            page._crumb_lbl.setText("  ›  ".join(chain))
            info["nav_index"] = parent["nav_index"]
            path = " · ".join(chain + [title])
        elif in_nav:
            info["nav_index"] = len(self.nav_pages)
            self.nav_pages.append(info)
            path = title
        else:
            path = title
        self.pages.append(info)
        self.stack.add_page(page)
        self._register_search(title, info, None, path)
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

    def _add_link(self, page, card, title, hint, cb, danger=False, icon=None):
        row = LinkRow(title, hint, danger=danger, icon=icon)
        row.clicked.connect(cb)
        card.add_row(row)
        return row

    def _add_section_label(self, page, text):
        lbl = QLabel(text)
        lbl.setObjectName("v4Section")
        page._inner_layout.addWidget(lbl)
        page._anim.append(lbl)
        return lbl

    def _add_link_card(self, page, icon, title, hint, cb,
                       tint=None, icon_bg=None, icon_pixmap=None):
        """原生二级页索引样式：独立大卡 + 左侧彩色图标。"""
        row = LinkRow(title, hint, icon=icon, card=True,
                      tint=tint, icon_bg=icon_bg, icon_pixmap=icon_pixmap)
        row.clicked.connect(cb)
        page._inner_layout.addWidget(row)
        page._anim.append(row)
        return row

    # ==================================================
    # 内嵌对话框（原来的独立窗口收进设置里）
    # ==================================================
    def _embed_dialog(self, page, dlg, hide_btns=(), on_accept=None):
        """把 QDialog 变成页面内的普通控件。
        - embedded 构造时未走窗口化（menu.py/test_dialog.py 的 embedded 参数）
        - accept/reject 在实例上遮蔽：内嵌时不再关闭页面，
          保存类按钮走完业务逻辑后改调 on_accept（如通知灵动岛刷新）
        - hide_btns：按文案隐藏「取消 / 关闭 / 关掉」这类按钮
        """
        dlg.setWindowFlags(Qt.Widget)
        dlg.accept = lambda *a, **k: (on_accept() if on_accept else None)
        dlg.reject = lambda *a, **k: None
        for b in dlg.findChildren(QPushButton):
            try:
                if b.text() in hide_btns:
                    b.hide()
            except RuntimeError:
                pass
        # apply_modern_dialog 给它套了不透明底色，内嵌时改透明让材质透出
        try:
            dlg.setStyleSheet(
                dlg.styleSheet() +
                "\nQDialog#settingsDialog { background: transparent; }")
        except Exception:
            pass
        page._inner_layout.addWidget(dlg)
        page._anim.append(dlg)
        dlg.show()
        self._embedded.append(dlg)
        return dlg

    def _embed_subpage(self, icon, title, parent_info, factory,
                       hide_btns=(), on_accept=None, unavailable=""):
        page = self._make_page(title, parent=parent_info)
        w = None
        try:
            w = factory()
        except Exception:
            w = None
        if w is None:
            card = self._add_card(page)
            lbl = QLabel(unavailable or "此功能当前不可用。")
            lbl.setObjectName("hint")
            lbl.setWordWrap(True)
            card.add_widget(lbl)
        else:
            self._embed_dialog(page, w, hide_btns=hide_btns,
                               on_accept=on_accept)
        return self._register_page(icon, title, page, parent=parent_info,
                                   in_nav=False)

    def _main_window(self):
        """主窗口（ClassBoardApp），取不到返回 None。"""
        if self.controller is not None:
            return getattr(self.controller, "window", None)
        return None

    # ==================================================
    # 页面内容
    # ==================================================
    def _build_pages(self):
        general = self._page_general()
        appearance = self._page_appearance()
        island = self._page_island()
        schedule = self._page_schedule_hub()
        homework = self._page_homework()
        plugins = self._page_plugins_hub()
        advanced = self._page_advanced()
        about = self._page_about()
        # 二级页（收进设置窗口的原独立窗口）
        self._build_schedule_subpages(schedule)
        self._build_plugin_subpages(plugins)

    # ---------- 通用 ----------
    def _page_general(self):
        page = self._make_page("通用")
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
        return self._register_page("gear", "通用", page)

    # ---------- 外观 ----------
    def _page_appearance(self):
        page = self._make_page("外观")
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
        return self._register_page("palette", "外观", page)

    # ---------- 灵动岛 ----------
    def _page_island(self):
        page = self._make_page("灵动岛")
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
        return self._register_page("island", "灵动岛", page)

    # ---------- 课表与提醒（Hub）----------
    def _page_schedule_hub(self):
        page = self._make_page("课表与提醒")

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

        info = self._register_page("calendar", "课表与提醒", page)
        # 索引链接在二级页注册后补齐；课表编辑器收在「课表管理」里面，
        # 先选课表再编辑（三级页面）
        self._hub_page = page
        self._schedule_links = [
            ("list", "课表管理", "切换、备份与导入导出课表", "#107c10"),
            ("clock", "周末作息", "单独设置周末上课时间", "#8661c5"),
            ("sun", "假期与调休", "设置假期与调休日", "#f7630c"),
            ("people", "值日生名单", "设置值日轮流安排", "#038387"),
            ("play", "状态测试", "完整演示一节课的状态变化", "#5b5fc7"),
        ]
        return info

    def _build_schedule_subpages(self, hub):
        import menu as menu_mod
        self._menu_mod = menu_mod
        subs = []
        if self.schedule is not None:
            # 课表管理（二级），它的「编辑」跳到课表编辑器（三级）
            mgr_info = self._embed_subpage(
                "list", "课表管理", hub,
                lambda: menu_mod.TimetableManagerDialog(
                    self.schedule, on_change=self._notify_island,
                    embedded=True),
                hide_btns=("关闭",),
                unavailable="课表管理器不可用。")
            subs.append(mgr_info)
            mgr = self._embedded[-1] if self._embedded else None
            self._timetable_mgr = mgr
            if mgr is not None:
                mgr.edit_requested = self._open_course_editor

            # 课表编辑器（三级页）：先占位，从课表管理里选了课表再加载
            editor_page = self._make_page("课表编辑器", parent=mgr_info)
            self._course_editor_info = self._register_page(
                "pencil", "课表编辑器", editor_page,
                parent=mgr_info, in_nav=False)
            self._course_editor_name = None
            self._show_editor_placeholder()

            subs.append(self._embed_subpage(
                "clock", "周末作息", hub,
                lambda: menu_mod.WeekendScheduleDialog(self.schedule,
                                                       embedded=True),
                hide_btns=("取消",), on_accept=self._notify_island,
                unavailable="课表管理器不可用。"))
            subs.append(self._embed_subpage(
                "sun", "假期与调休", hub,
                lambda: menu_mod.HolidayDialog(self.schedule, embedded=True),
                hide_btns=("关闭",),
                unavailable="课表管理器不可用。"))
            win = self._main_window()
            subs.append(self._embed_subpage(
                "people", "值日生名单", hub,
                (lambda: menu_mod.DutyEditor(win.duty_manager, win,
                                             embedded=True))
                if win is not None else (lambda: None),
                hide_btns=("取消",),
                unavailable="主窗口不可用，无法编辑值日生。"))
            subs.append(self._embed_subpage(
                "play", "状态测试", hub,
                lambda: self._make_status_test(),
                hide_btns=("关掉",),
                unavailable="课表管理器不可用。"))
        # Hub 页补索引大卡
        if subs:
            self._add_section_label(self._hub_page, "课表与值日")
        for (icon, title, hint, tint), sub in zip(self._schedule_links, subs):
            row = self._add_link_card(
                self._hub_page, icon, title, hint,
                lambda _=False, s=sub: self._select(s["index"]),
                tint=tint)
            self._register_search(row.search_text, sub, None,
                                  f"{hub['title']} · {title}")

    def _show_editor_placeholder(self):
        """课表编辑器未选课表时的占位页。"""
        info = self._course_editor_info
        page = info["widget"]
        card = self._add_card(page)
        lbl = QLabel("先在「课表管理」里选中一张课表，再点「编辑」进入本页。")
        lbl.setObjectName("hint")
        lbl.setWordWrap(True)
        card.add_widget(lbl)
        row = self._add_link_card(
            page, "list", "前往课表管理", "选择要编辑的课表",
            lambda _=False: self._select(info["parent"]["index"]),
            tint="#107c10")

    def _open_course_editor(self, name):
        """课表管理里点了「编辑」：把编辑器加载成它的三级子页。"""
        info = self._course_editor_info
        page = info["widget"]
        from ui_common import clear_layout
        clear_layout(page._inner_layout)
        page._anim.clear()
        try:
            dlg = self._menu_mod.CourseEditor(
                self.schedule, timetable_name=name, embedded=True)
            mgr = getattr(self, "_timetable_mgr", None)

            def _saved():
                self._notify_island()
                if mgr is not None:
                    try:
                        mgr.refresh()
                    except Exception:
                        pass

            self._embed_dialog(page, dlg, hide_btns=("取消",),
                               on_accept=_saved)
            self._course_editor_name = name
        except Exception as e:
            card = self._add_card(page)
            lbl = QLabel(f"课表编辑器加载失败：{e}")
            lbl.setObjectName("hint")
            lbl.setWordWrap(True)
            card.add_widget(lbl)
        self._select(info["index"])

    def _make_status_test(self):
        if self.schedule is None:
            return None
        from test_dialog import StatusTestDialog
        return StatusTestDialog(self.schedule, self.settings,
                                self.controller, embedded=True)

    # ---------- 作业 ----------
    def _page_homework(self):
        import menu as menu_mod
        page = self._make_page("作业")
        win = self._main_window()
        if win is not None and getattr(win, "homework_manager", None):
            try:
                dlg = menu_mod.HomeworkEditor(win.homework_manager, win,
                                              embedded=True)
                self._embed_dialog(page, dlg, hide_btns=("取消", "确认"))
            except Exception as e:
                card = self._add_card(page)
                lbl = QLabel(f"作业编辑器加载失败：{e}")
                lbl.setObjectName("hint")
                lbl.setWordWrap(True)
                card.add_widget(lbl)
        else:
            card = self._add_card(page)
            lbl = QLabel("主窗口不可用，无法编辑作业。")
            lbl.setObjectName("hint")
            lbl.setWordWrap(True)
            card.add_widget(lbl)
        return self._register_page("book", "作业", page)

    # ---------- 插件（Hub）----------
    def _page_plugins_hub(self):
        page = self._make_page("插件")
        self._plugin_hub_page = page
        info = self._register_page("plugin", "插件", page)
        self._plugins_hub_info = info
        if self.plugin_manager is None:
            card = self._add_card(page)
            lbl = QLabel("插件管理器不可用，插件中心暂不可用。")
            lbl.setObjectName("hint")
            lbl.setWordWrap(True)
            card.add_widget(lbl)
        return info

    @staticmethod
    def _resolve_plugin_icon(entry):
        """插件设置页图标：矢量名 / emoji / 图片路径 + 可选颜色。
        返回 (icon, tint, icon_bg, pixmap)。"""
        icon = entry.get("icon") or "plugin"
        if icon == "🧩":
            icon = "plugin"
        pm = None
        path = entry.get("icon_path")
        if path:
            try:
                if not os.path.isabs(path):
                    path = os.path.join(os.path.dirname(
                        os.path.abspath(__file__)), path)
                if os.path.exists(path):
                    cand = QPixmap(path)
                    if not cand.isNull():
                        pm = cand
            except Exception:
                pm = None
        return icon, entry.get("icon_color"), entry.get("icon_bg"), pm

    def _build_plugin_subpages(self, hub):
        if self.plugin_manager is None:
            return
        from market_page import MarketPage
        from package_page import PackagePage

        def make_widget_page(icon, title, builder, attr):
            page = self._make_page(title, parent=hub)
            holder = QWidget()
            hl = QVBoxLayout(holder)
            hl.setContentsMargins(0, 0, 0, 0)
            w = builder()
            w.setObjectName("v3PageInner")
            hl.addWidget(w, 1)
            holder.setProperty("noUnfold", True)
            page._inner_layout.addWidget(holder, 1)
            page._anim.append(holder)
            setattr(self, attr, w)
            return self._register_page(icon, title, page, parent=hub,
                                       in_nav=False)

        market = make_widget_page(
            "market", "插件市场",
            lambda: MarketPage(self.plugin_manager, self.settings),
            "market_page")
        packages = make_widget_page(
            "box", "第三方包管理",
            lambda: PackagePage(self.plugin_manager, self.settings),
            "package_page")

        self._add_section_label(self._plugin_hub_page, "插件中心")
        for icon, title, hint, tint, sub in (
                ("market", "插件市场", "从远程仓库安装与更新插件",
                 "#0078d4", market),
                ("box", "第三方包管理", "插件依赖的第三方包",
                 "#ca5010", packages)):
            row = self._add_link_card(
                self._plugin_hub_page, icon, title, hint,
                lambda _=False, s=sub: self._select(s["index"]),
                tint=tint)
            self._register_search(row.search_text, sub, None,
                                  f"插件 · {title}")

        # 插件自带的设置页 → 也收为二级页（图标/颜色由插件自定义）
        try:
            plugin_pages = self.plugin_manager.get_settings_pages()
        except Exception:
            plugin_pages = []
        if plugin_pages:
            self._add_section_label(self._plugin_hub_page, "已安装的插件")
        self._plugin_root_infos = []
        for entry in plugin_pages:
            title = str(entry.get("title", "插件设置"))
            icon, tint, icon_bg, pm = self._resolve_plugin_icon(entry)
            page = self._make_page(title, parent=hub)
            sub = self._register_page(icon, title, page, parent=hub,
                                      in_nav=False)
            # 本页内容（factory 可为 None，纯目录页）
            factory = entry.get("factory")
            if factory is not None:
                try:
                    content = factory(entry.get("api"))
                except Exception as e:
                    content = QLabel(f"插件设置加载失败：{e}")
                    content.setObjectName("hint")
                    content.setWordWrap(True)
                if content is not None:
                    card = self._add_card(page)
                    card.add_widget(content)
            # 子页面（三级菜单）
            children = entry.get("children") or ()
            if children:
                self._add_section_label(page, "子页面")
            for child in children:
                c_title = str(child.get("title", "子页面"))
                c_icon, c_tint, c_bg, c_pm = self._resolve_plugin_icon(child)
                c_factory = child.get("factory")
                c_page = self._make_page(c_title, parent=sub)
                if c_factory is not None:
                    try:
                        c_content = c_factory(entry.get("api"))
                    except Exception as e:
                        c_content = QLabel(f"插件设置加载失败：{e}")
                        c_content.setObjectName("hint")
                        c_content.setWordWrap(True)
                    if c_content is not None:
                        c_card = self._add_card(c_page)
                        c_card.add_widget(c_content)
                c_sub = self._register_page(c_icon, c_title, c_page,
                                            parent=sub, in_nav=False)
                row = self._add_link_card(
                    page, c_icon, c_title, "",
                    lambda _=False, s=c_sub: self._select(s["index"]),
                    tint=c_tint, icon_bg=c_bg, icon_pixmap=c_pm)
                self._register_search(row.search_text, c_sub, None,
                                      f"插件 · {title} · {c_title}")

            row = self._add_link_card(
                self._plugin_hub_page, icon, title,
                "插件设置",
                lambda _=False, s=sub: self._select(s["index"]),
                tint=tint, icon_bg=icon_bg, icon_pixmap=pm)
            self._register_search(row.search_text, sub, None,
                                  f"插件 · {title}")
            self._plugin_root_infos.append(sub)

    # ---------- 高级 ----------
    def _page_advanced(self):
        page = self._make_page("高级")
        card = self._add_card(page, "本地插件", "程序启动时会加载这些插件")
        text = self._local_plugins_text()
        lbl = QLabel(text)
        lbl.setObjectName("hint")
        lbl.setWordWrap(True)
        lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        card.add_widget(lbl)
        self._add_link(page, card, "安装本地插件…", "从 .cblplugin 文件安装",
                       self._import_plugin, icon="box")
        self._add_link(page, card, "打开插件文件夹", "在文件资源管理器中打开",
                       self._open_plugins_dir, icon="wrench")

        card = self._add_card(page, "日常维护")
        self._add_link(page, card, "打开配置文件夹", "查看 settings.json 等配置文件",
                       self._open_config_dir, icon="gear")
        self._add_link(page, card, "恢复全部默认", "将所有设置恢复为默认值",
                       self._reset_all, danger=True, icon="back")
        return self._register_page("wrench", "高级", page)

    # ---------- 关于 ----------
    def _page_about(self):
        page = self._make_page("关于")
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
        return self._register_page("info", "关于", page)

    # ==================================================
    # 搜索结果页
    # ==================================================
    def _build_results_page(self):
        page = self._make_page("搜索结果")
        self.results = QListWidget()
        self.results.setObjectName("v3Results")
        self.results.setFrameShape(QFrame.NoFrame)
        self.results.itemClicked.connect(self._on_result_clicked)
        page._inner_layout.addWidget(self.results, 1)

        bar = QFrame()
        bar.setObjectName("v4ResultsBar")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(6, 6, 6, 2)
        hint = QLabel("按 Enter 打开第一项，Esc 返回")
        hint.setObjectName("hint")
        bl.addWidget(hint)
        bl.addStretch(1)
        btn_clear = QPushButton("清除")
        btn_clear.setCursor(Qt.PointingHandCursor)
        btn_clear.clicked.connect(self._clear_search)
        bl.addWidget(btn_clear)
        page._inner_layout.addWidget(bar)

        self._results_idx = len(self.pages)
        page._info["index"] = self._results_idx
        self.pages.append(page._info)
        self.stack.add_page(page)

    # ==================================================
    # 导航
    # ==================================================
    def _build_nav(self):
        for p in self.nav_pages:
            self.nav.add_item(p["icon"], p["title"])
        self.nav.finish()

    def _on_nav_clicked(self, nav_idx):
        if not (0 <= nav_idx < len(self.nav_pages)):
            return
        self._clear_search()
        self._select(self.nav_pages[nav_idx]["index"])

    def _select(self, idx, animate=True, direction=None):
        idx = max(0, min(len(self.pages) - 1, int(idx)))
        info = self.pages[idx]
        smooth = bool(animate and self._opened)
        if direction is None:
            # 钻取导航方向：进二级页从右滑入，返回从左滑入（原生手感）
            cur = self.stack.current_index()
            if 0 <= cur < len(self.pages) and cur != self._results_idx:
                old_depth = self._page_depth(self.pages[cur])
                new_depth = self._page_depth(info)
                direction = (1 if new_depth > old_depth
                             else (-1 if new_depth < old_depth else 0))
            else:
                direction = 0
        self.stack.set_current(idx, animate=smooth, direction=direction)
        nav_idx = info.get("nav_index", -1)
        if 0 <= nav_idx < self.nav.count():
            self.nav.select(nav_idx, animate=smooth)
        # 二级页显示返回键
        parent = info.get("parent")
        self.btn_back.setVisible(parent is not None)
        if idx != self._results_idx:
            self._last_page = idx
        self._update_search_mode(info)

    @staticmethod
    def _page_depth(info):
        d = 0
        while info.get("parent") is not None:
            info = info["parent"]
            d += 1
        return d

    @staticmethod
    def _top_ancestor(info):
        while info.get("parent") is not None:
            info = info["parent"]
        return info

    @staticmethod
    def _in_subtree(info, root):
        while info is not None:
            if info is root:
                return True
            info = info.get("parent")
        return False

    def _update_search_mode(self, info):
        """搜索框随页面换语境：
        - 插件目录页：「搜索插件的设置」，搜全部插件页
        - 某个插件页（含其子页）：「搜索 XX 插件的设置」，只搜这个插件
        进入插件子树时整条搜索栏从顶部滑下来。"""
        hub = getattr(self, "_plugins_hub_info", None)
        scope = None          # None=全局；"hub"=全部插件页；info=某个插件子树
        placeholder = "查找设置"
        if hub is not None and self._in_subtree(info, hub):
            node = info
            while node.get("parent") is not hub and node.get("parent"):
                node = node["parent"]
            roots = getattr(self, "_plugin_root_infos", [])
            if node is not hub and node in roots:
                scope = node
                t = node["title"]
                placeholder = (f"搜索{t}的设置" if str(t).endswith("插件")
                               else f"搜索{t}插件的设置")
            else:
                scope = "hub"
                placeholder = "搜索插件的设置"

        new_mode = (scope is not None)
        old_mode = bool(getattr(self, "_plugin_search_mode", None))
        self._search_scope = scope
        self._plugin_search_mode = new_mode
        if self.search.placeholderText() != placeholder:
            self.search.setPlaceholderText(placeholder)
        if new_mode and not old_mode:
            self._slide_strip_down()
        elif not new_mode and old_mode:
            self._clear_search()

    def _go_back(self):
        info = self.pages[self.stack.current_index()]
        parent = info.get("parent")
        if parent is not None:
            self._select(parent["index"])

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

    def _clear_search(self):
        if self.search.text():
            self._suppress_search = True
            self.search.clear()
            self._suppress_search = False

    def _on_search(self, text):
        if self._suppress_search:
            return
        q = text.strip().lower()
        if not q:
            if self.stack.current_index() == self._results_idx:
                self._select(self._last_page)
            return
        scope = getattr(self, "_search_scope", None)
        hub = getattr(self, "_plugins_hub_info", None)
        if scope == "hub" and hub is not None:
            # 插件目录语境：搜全部插件页
            pool = [e for e in self._search_index
                    if self._in_subtree(e["page"], hub)]
        elif scope not in (None, "hub"):
            # 某个插件语境：只搜这个插件（含其子页面）
            pool = [e for e in self._search_index
                    if self._in_subtree(e["page"], scope)]
        else:
            pool = self._search_index
        hits = [e for e in pool if q in e["text"]][:60]
        self._search_hits = hits
        self.results.clear()
        if not hits:
            it = QListWidgetItem("未找到匹配的设置项")
            it.setFlags(Qt.NoItemFlags)
            self.results.addItem(it)
        else:
            for i, e in enumerate(hits):
                item = QListWidgetItem(e["label"])
                item.setData(Qt.UserRole, i)
                self.results.addItem(item)
        self.stack.set_current(self._results_idx, animate=False)

    def _on_result_clicked(self, item):
        i = item.data(Qt.UserRole)
        if i is None or not (0 <= i < len(self._search_hits)):
            return
        e = self._search_hits[i]
        self._clear_search()
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
    # 恢复默认 / 提示
    # ==================================================
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
        self.toast.setText(text)
        self.toast.adjustSize()
        self._reposition_toast()
        self.toast.show()
        self.toast.raise_()
        StaggerPlayer.fade(self.toast, duration=180)
        QTimer.singleShot(2200, self, self._hide_toast)

    def _hide_toast(self):
        StaggerPlayer.fade(self.toast, duration=240, end=0.0)
        QTimer.singleShot(260, self, self.toast.hide)

    def _reposition_toast(self):
        if not hasattr(self, "toast"):
            return
        self.toast.adjustSize()
        x = self.width() - self.toast.width() - 28
        y = self.height() - self.toast.height() - 22
        self.toast.move(max(0, x), max(0, y))

    # ==================================================
    # 操作入口
    # ==================================================
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
        super().showEvent(event)
        if self._mica_active and not getattr(self, "_material_done", False):
            # 云母只在首次显示时应用一次，反复重设 DWM 属性会闪
            self._material_done = True
            ok = apply_window_material(self, mica=True, dark=theme.is_dark())
            if not ok:
                self._mica_active = False
                self.setAttribute(Qt.WA_TranslucentBackground, False)
                disable_mica(self)
                self.setWindowOpacity(1.0)
                self._apply_qss()
        if not self._opened:
            self._opened = True
            if self._morph_from is not None:
                QTimer.singleShot(0, self, self._play_morph)
            else:
                if not self._translucent:
                    self.setWindowOpacity(0.0)
                QTimer.singleShot(30, self, self._play_open)

    def _play_morph(self):
        """副岛/灵动岛 → 设置窗口 的形变过渡。"""
        try:
            start = QRect(self._morph_from)
            if start.width() < 10 or start.height() < 10:
                raise ValueError("起点太小")
            self.setWindowOpacity(0.0)
            target = self.frameGeometry()
            self._morph_overlay = _MorphOverlay(
                start, target, self._on_morph_done)
        except Exception:
            self._morph_from = None
            self.setWindowOpacity(1.0)
            self._play_open()

    def _on_morph_done(self):
        self._morph_overlay = None
        # 窗口淡入与内容入场一起上
        a = QPropertyAnimation(self, b"windowOpacity", self)
        a.setDuration(160)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.setEasingCurve(QEasingCurve.OutCubic)
        a.start(QAbstractAnimation.DeleteWhenStopped)
        self._play_open()

    def _play_open(self):
        if not self._translucent:
            self._fade_window()
        # 透明窗里不用透明度特效（防黑色残影），导航错峰只在不透明窗播
        if not self._translucent:
            StaggerPlayer(duration=200, step=36, delay=110).play(
                self.nav.items())
        self.stack.set_current(0, animate=True)
        self.nav.select(0, animate=False)

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
# 样式表：V3 全套 + V4 增量（返回键 / 顶部搜索 / 面包屑 / toast）
# ============================================================
def _v4_qss(glass=False, chrome=False):
    base = _v3_qss(glass=glass, chrome=chrome)
    base = base.replace("settingsV3", "settingsV4")
    c = theme.PALETTES[theme.current()]
    dark = theme.is_dark()
    inp = _rgba(c['input_bg'], 0.7) if glass else c['input_bg']
    hover = _rgba(c['hover'], 0.8) if glass else c['hover']
    btn_bottom = _rgba("#000000", 0.22) if not dark else _rgba("#000000", 0.5)
    card = (_rgba("#2e2e2e", 0.72) if dark else _rgba("#ffffff", 0.72)) \
        if glass else ("#2b2b2b" if dark else "#ffffff")
    extra = f"""
/* ---------- V4：顶部搜索（原生位置，窗口顶部居中） ---------- */
QFrame#v4Strip {{ background: transparent; border: none; }}
QLineEdit#v4SearchTop {{
    background: {inp}; border: 1px solid {c['border']};
    border-bottom: 1px solid {btn_bottom};
    border-radius: 5px; padding: 4px 12px; font-size: 13px;
    color: {c['text']};
}}
QLineEdit#v4SearchTop:hover {{ background: {card}; }}
QLineEdit#v4SearchTop:focus {{
    border: 1px solid {c['accent']};
    border-bottom: 2px solid {c['accent']};
}}

/* ---------- V4：面包屑 / 分组小标题 ---------- */
QLabel#v4Crumb {{ font-size: 12px; color: {c['hint']}; }}
QLabel#v4Section {{
    font-size: 12px; font-weight: 600; color: {c['sub_text']};
    padding-left: 6px; padding-top: 6px;
}}

/* ---------- V4：右下角浮层提示 ---------- */
QLabel#v4Toast {{
    background: {card}; border: 1px solid {c['border']};
    border-radius: 8px; padding: 8px 16px;
    font-size: 12px; color: {c['text']};
}}
"""
    return base + extra
