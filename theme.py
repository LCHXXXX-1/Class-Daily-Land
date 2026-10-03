"""主题机制：跟随系统 / 浅色 / 深色，统一色板与 QSS 生成。

用法：
- 启动时（ClassBoard.py）：theme.init(settings) → theme.apply_theme(app)
- 窗口级 QSS：settings_dialog / test_dialog 使用 theme.dialog_qss()
- 代码取色：theme.color("hint") / theme.color("disabled_row_bg")
- 主题变更回调：theme.theme_changed_connect(self._apply_theme)（弱引用）

注意：灵动岛 / 副岛 / 下拉面板为深色自绘组件，不走本模块。
"""
import sys
import weakref

from PySide6.QtCore import Qt

LIGHT = "light"
DARK = "dark"
SYSTEM = "system"

PALETTES = {
    LIGHT: {
        "window_bg": "#ffffff",
        "nav_bg": "#f3f3f3",
        "card_bg": "#fafafa",
        "input_bg": "#ffffff",
        "list_bg": "#fafafa",
        "text": "#1b1b1b",
        "sub_text": "#555555",
        "hint": "#888888",
        "border": "#d0d0d0",
        "divider": "#e5e5e5",
        "list_border": "#e0e0e0",
        "item_border": "#eeeeee",
        "hover": "#f5f5f5",
        "pressed": "#ececec",
        "nav_hover": "#e9e9e9",
        "nav_checked_bg": "#e2e2e2",
        "nav_checked_text": "#0067c0",
        "accent": "#0067c0",
        "accent_hover": "#1975c5",
        "accent_soft": "#e7f0fa",
        "success": "#2ea043",
        "warn": "#b8770f",
        "danger": "#d13b3b",
        "card_bg_2": "#f4f5f7",
        "card_hover": "#f2f4f7",
        "sidebar_bg": "#f6f7f9",
        "scroll_handle": "#c9c9c9",
        "disabled_row_bg": "#ebebeb",
        "detail_bg": "#f7f7f7",
        "detail_border": "#e0e0e0",
    },
    DARK: {
        "window_bg": "#202020",
        "nav_bg": "#2b2b2b",
        "card_bg": "#2b2b2b",
        "input_bg": "#2d2d2d",
        "list_bg": "#262626",
        "text": "#e8e8e8",
        "sub_text": "#c0c0c0",
        "hint": "#9a9a9a",
        "border": "#3f3f3f",
        "divider": "#3f3f3f",
        "list_border": "#3a3a3a",
        "item_border": "#383838",
        "hover": "#383838",
        "pressed": "#404040",
        "nav_hover": "#383838",
        "nav_checked_bg": "#3a3a3a",
        "nav_checked_text": "#4da3e8",
        "accent": "#0067c0",
        "accent_hover": "#1975c5",
        "accent_soft": "#1d3b57",
        "success": "#4cc38a",
        "warn": "#e0a83a",
        "danger": "#ff6b60",
        "card_bg_2": "#242424",
        "card_hover": "#313131",
        "sidebar_bg": "#262626",
        "scroll_handle": "#4a4a4a",
        "disabled_row_bg": "#3c3c3c",
        "detail_bg": "#2b2b2b",
        "detail_border": "#3f3f3f",
    },
}

_settings = None
_watchers = []
_scheme_connected = False


def init(settings):
    """注入 SettingsManager（读取 theme_mode）。"""
    global _settings
    _settings = settings


def mode():
    """用户设置的主题模式：system / light / dark。"""
    if _settings is not None:
        try:
            m = str(_settings.get("theme_mode", SYSTEM))
            if m in (LIGHT, DARK, SYSTEM):
                return m
        except Exception:
            pass
    return SYSTEM


def detect_system_theme():
    """检测系统主题，返回 light / dark（QStyleHints 优先，注册表兜底）。"""
    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is not None:
            cs = app.styleHints().colorScheme()
            if cs == Qt.ColorScheme.Dark:
                return DARK
            if cs == Qt.ColorScheme.Light:
                return LIGHT
    except Exception:
        pass
    if sys.platform == 'win32':
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes"
                r"\Personalize")
            val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.CloseKey(key)
            return LIGHT if int(val) else DARK
        except Exception:
            pass
    return LIGHT


def current():
    """最终生效的主题：light / dark。"""
    m = mode()
    return detect_system_theme() if m == SYSTEM else m


def is_dark():
    return current() == DARK


def color(name):
    return PALETTES[current()].get(name, "#ff00ff")


def theme_changed_connect(cb):
    """注册主题变更回调（弱引用，对象销毁后自动清理）。"""
    try:
        ref = weakref.WeakMethod(cb)
    except TypeError:
        ref = weakref.ref(cb)
    _watchers.append(ref)


def _notify_watchers():
    alive = []
    for ref in _watchers:
        cb = ref()
        if cb is None:
            continue
        alive.append(ref)
        try:
            cb()
        except Exception:
            pass
    _watchers[:] = alive


def apply_theme(app=None):
    """应用全局 QSS 并通知所有 watcher；启动和主题切换时调用。"""
    from PySide6.QtWidgets import QApplication
    app = app or QApplication.instance()
    if app is None:
        return
    app.setStyleSheet(_global_qss())
    global _scheme_connected
    if not _scheme_connected:
        _scheme_connected = True
        try:
            app.styleHints().colorSchemeChanged.connect(_on_system_change)
        except Exception:
            pass
    _notify_watchers()


def _on_system_change(*_):
    if mode() == SYSTEM:
        apply_theme()


# ---------- 全局兜底 QSS（无样式对话框：menu.py / randoms.py / QMessageBox） ----------
def _global_qss():
    c = PALETTES[current()]
    bg = c['window_bg']
    inp = c['input_bg']
    return f"""
QDialog {{ background: {bg}; color: {c['text']}; }}
QLabel {{ color: {c['text']}; }}
QLabel#hint {{ color: {c['hint']}; }}
QLineEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QDateEdit, QDateTimeEdit,
QComboBox {{
    background: {inp}; color: {c['text']};
    border: 1px solid {c['border']}; border-radius: 4px; padding: 4px 8px;
}}
QComboBox QAbstractItemView {{
    background: {inp}; color: {c['text']};
    border: 1px solid {c['border']};
    selection-background-color: {c['accent']}; selection-color: #ffffff;
}}
QPushButton {{
    background: {inp}; color: {c['text']};
    border: 1px solid {c['border']}; border-radius: 4px; padding: 6px 18px;
}}
QPushButton:hover {{ background: {c['hover']}; }}
QPushButton:pressed {{ background: {c['pressed']}; }}
QPushButton#primary {{ background: {c['accent']}; color: #ffffff; border: none; }}
QPushButton#primary:hover {{ background: {c['accent_hover']}; }}
QCheckBox {{ color: {c['text']}; }}
QListWidget, QTableWidget {{
    background: {c['list_bg']}; color: {c['text']};
    border: 1px solid {c['list_border']};
}}
QListWidget::item:selected, QTableWidget::item:selected {{
    background: {c['accent']}; color: #ffffff;
}}
QHeaderView::section {{
    background: {c['nav_bg']}; color: {c['text']};
    border: none; border-bottom: 1px solid {c['border']}; padding: 4px;
}}
QMenu {{
    background: {bg}; color: {c['text']};
    border: 1px solid {c['border']};
}}
QMenu::item:selected {{ background: {c['accent']}; color: #ffffff; }}
QMessageBox {{ background: {bg}; }}
QMessageBox QLabel {{ color: {c['text']}; }}
QToolTip {{
    background: {c['nav_bg']}; color: {c['text']};
    border: 1px solid {c['border']}; padding: 4px;
}}
QScrollArea {{ background: {bg}; }}
"""


# ---------- 窗口级 QSS（设置窗口 / 状态测试窗口） ----------
def dialog_qss():
    c = PALETTES[current()]
    bg = c['window_bg']
    inp = c['input_bg']
    return f"""
QDialog {{ background: {bg}; }}
QLabel {{ color: {c['text']}; }}
QLabel#pageTitle {{ font-size: 22px; font-weight: 600; color: {c['text']}; }}
QLabel#sectionTitle {{ font-size: 14px; font-weight: 600; color: {c['text']};
                      padding-top: 6px; }}
QLabel#formLabel {{ color: {c['text']}; font-size: 13px; }}
QLabel#hint {{ color: {c['hint']}; font-size: 12px; }}
QLabel#detailCard {{
    background: {c['detail_bg']}; border: 1px solid {c['detail_border']};
    border-radius: 6px; padding: 10px; color: {c['text']}; font-size: 13px;
}}

QPushButton#navButton {{
    text-align: left; padding-left: 16px; height: 42px;
    border: none; border-radius: 6px;
    font-size: 14px; color: {c['text']}; background: transparent;
}}
QPushButton#navButton:hover {{ background: {c['nav_hover']}; }}
QPushButton#navButton:checked {{ background: {c['nav_checked_bg']};
                                color: {c['nav_checked_text']}; }}

QScrollArea#navScroll {{ background: {c['nav_bg']}; border: none; }}
QWidget#navContainer {{ background: {c['nav_bg']}; }}
QScrollArea#pageScroll {{ background: {bg}; border: none; }}

QSpinBox, QDoubleSpinBox {{
    background: {inp}; border: 1px solid {c['border']};
    border-radius: 4px; padding: 4px 8px; min-width: 110px; color: {c['text']};
}}
QLineEdit, QComboBox, QDateEdit, QDateTimeEdit {{
    background: {inp}; border: 1px solid {c['border']};
    border-radius: 4px; padding: 4px 8px; color: {c['text']};
}}
QSpinBox:hover, QDoubleSpinBox:hover, QLineEdit:hover, QComboBox:hover,
QDateEdit:hover, QDateTimeEdit:hover {{ border: 1px solid {c['hint']}; }}
QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus, QComboBox:focus,
QDateEdit:focus, QDateTimeEdit:focus {{ border: 1px solid {c['accent']}; }}
QComboBox QAbstractItemView {{
    background: {inp}; color: {c['text']};
    border: 1px solid {c['border']};
    selection-background-color: {c['accent']}; selection-color: #ffffff;
}}

QSlider::groove:horizontal {{
    height: 4px; background: {c['border']}; border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: {c['accent']}; border-radius: 2px;
}}
QSlider::handle:horizontal {{
    width: 16px; height: 16px; margin: -6px 0;
    border-radius: 8px; background: {c['accent']};
}}

QCheckBox {{ color: {c['text']}; font-size: 13px; spacing: 8px; }}
QCheckBox::indicator {{
    width: 18px; height: 18px;
    border: 1px solid {c['border']}; border-radius: 4px;
    background: {inp};
}}
QCheckBox::indicator:hover {{ border: 1px solid {c['accent']}; }}
QCheckBox::indicator:checked {{ background: {c['accent']};
                               border: 1px solid {c['accent']}; }}

QPushButton {{
    background: {inp}; border: 1px solid {c['border']};
    border-radius: 4px; padding: 6px 18px; font-size: 13px; color: {c['text']};
}}
QPushButton:hover {{ background: {c['hover']}; }}
QPushButton:pressed {{ background: {c['pressed']}; }}
QPushButton#primary {{ background: {c['accent']}; color: #ffffff;
                      border: none; }}
QPushButton#primary:hover {{ background: {c['accent_hover']}; }}

QFrame#divider {{ border: none; border-top: 1px solid {c['divider']}; }}

QListWidget#pluginList {{
    border: 1px solid {c['list_border']}; border-radius: 6px;
    background: {c['list_bg']}; outline: none;
}}
QListWidget#pluginList::item {{
    height: 40px; padding-left: 10px;
    border-bottom: 1px solid {c['item_border']};
}}
"""


# ---------- 全新设置窗口 QSS ----------
def _rgba(hex_color, alpha):
    """把 #rrggbb 颜色转成带透明度的 rgba() 字符串。"""
    h = str(hex_color).lstrip('#')
    if len(h) == 3:
        h = ''.join(ch * 2 for ch in h)
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except Exception:
        return str(hex_color)
    return f"rgba({r}, {g}, {b}, {alpha})"


def settings_qss(glass=False):
    """新设置界面（左侧导航 + 卡片内容区 + 插件市场）专用样式。

    glass=True：窗口背景透明、侧栏与卡片半透明，用于配合
    Windows 11 云母（Mica）材质；Windows 10 请保持 False（不透明）。
    """
    c = PALETTES[current()]
    if glass:
        # 整窗统一底色：侧栏与内容区都透明，由窗口这一层均匀铺底色，
        # 左右透明度一致，云母从同一层透出
        win = _rgba(c['window_bg'], 0.45)
        bg = "transparent"
        sidebar = "transparent"
        card = _rgba(c['card_bg'], 0.85)
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
QDialog#settingsDialog {{ background: {win}; }}
QLabel {{ color: {c['text']}; background: transparent; }}
QLabel#brandTitle {{ font-size: 18px; font-weight: 700; color: {c['text']}; }}
QLabel#brandSub {{ font-size: 11px; color: {c['hint']}; }}
QLabel#versionLbl {{ font-size: 11px; color: {c['hint']}; }}
QLabel#pageTitle {{ font-size: 24px; font-weight: 700; color: {c['text']}; }}
QLabel#pageSub {{ font-size: 12px; color: {c['hint']}; }}
QLabel#sectionTitle {{ font-size: 13px; font-weight: 600;
                      color: {c['sub_text']}; }}
QLabel#rowTitle {{ font-size: 13px; color: {c['text']}; }}
QLabel#hint {{ font-size: 11px; color: {c['hint']}; }}
QLabel#emptyTip {{ font-size: 13px; color: {c['hint']}; }}
QLabel#detailCard {{
    background: {card2}; border: 1px solid {c['divider']};
    border-radius: 10px; padding: 12px; color: {c['text']};
    font-size: 13px;
}}

QTableWidget {{
    background: {inp}; alternate-background-color: {card2};
    border: 1px solid {c['divider']}; border-radius: 8px;
    gridline-color: {c['divider']}; color: {c['text']};
    selection-background-color: {c['accent_soft']};
    selection-color: {c['text']}; outline: none;
}}
QTableWidget::item {{ padding: 2px 4px; }}
QHeaderView::section {{
    background: {card2}; color: {c['sub_text']};
    border: none; border-bottom: 1px solid {c['divider']};
    padding: 6px; font-weight: 600;
}}
QTableCornerButton::section {{
    background: {card2}; border: none;
}}
QListWidget {{
    background: {inp}; border: 1px solid {c['divider']};
    border-radius: 8px; outline: none; padding: 4px; color: {c['text']};
}}
QListWidget::item {{ padding: 7px 8px; border-radius: 6px; }}
QListWidget::item:selected {{
    background: {c['accent_soft']}; color: {c['accent']};
}}
QDateEdit, QDateTimeEdit {{
    background: {inp}; border: 1px solid {c['border']};
    border-radius: 7px; padding: 5px 9px; color: {c['text']};
    font-size: 13px;
}}
QDateEdit:hover, QDateTimeEdit:hover {{ border: 1px solid {c['hint']}; }}
QDateEdit:focus, QDateTimeEdit:focus {{ border: 1px solid {c['accent']}; }}
QLineEdit {{
    background: {inp}; border: 1px solid {c['border']};
    border-radius: 7px; padding: 6px 9px; color: {c['text']};
    font-size: 13px;
}}
QLineEdit:focus {{ border: 1px solid {c['accent']}; }}

QFrame#sidebar {{ background: {sidebar}; border: none;
                 border-right: 1px solid {c['divider']}; }}
QWidget#sidebarInner {{ background: {sidebar}; }}
QWidget#navRail {{ background: transparent; }}

QPushButton#navButton {{
    text-align: left; padding-left: 14px; height: 40px;
    border: none; border-radius: 8px; font-size: 13px;
    color: {c['text']}; background: transparent;
}}
QPushButton#navButton:hover {{ background: {c['nav_hover']}; }}
QPushButton#navButton:checked {{ color: {c['accent']}; font-weight: 600; }}

QWidget#contentWrap {{ background: {bg}; }}
QScrollArea#pageScroll {{ background: {bg}; border: none; }}
QScrollArea#pageScroll > QWidget {{ background: {bg}; }}
QScrollArea#marketScroll {{ background: {bg}; border: none; }}
QScrollArea#marketScroll > QWidget {{ background: {bg}; }}
QScrollArea#navScroll > QWidget {{ background: transparent; }}
QWidget#pageInner {{ background: {bg}; }}

QFrame#card {{
    background: {card}; border: 1px solid {c['divider']};
    border-radius: 12px;
}}
QWidget#rowWidget {{ background: transparent; border-radius: 8px; }}
QWidget#rowWidget[flash="true"] {{ background: {c['accent_soft']}; }}

QLineEdit#searchBox {{
    background: {inp}; border: 1px solid {c['border']};
    border-radius: 8px; padding: 7px 10px; font-size: 13px;
    color: {c['text']};
}}
QLineEdit#searchBox:focus {{ border: 1px solid {c['accent']}; }}

QListWidget#searchResults {{
    background: {card}; border: 1px solid {c['border']};
    border-radius: 8px; outline: none; padding: 4px;
}}
QListWidget#searchResults::item {{
    padding: 7px 8px; border-radius: 6px; color: {c['text']};
}}
QListWidget#searchResults::item:selected {{
    background: {c['accent_soft']}; color: {c['accent']};
}}

QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {inp}; border: 1px solid {c['border']};
    border-radius: 7px; padding: 5px 9px; min-width: 96px;
    color: {c['text']}; font-size: 13px;
}}
QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover {{
    border: 1px solid {c['hint']};
}}
QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border: 1px solid {c['accent']};
}}
QComboBox QAbstractItemView {{
    background: {inp}; color: {c['text']};
    border: 1px solid {c['border']};
    selection-background-color: {c['accent']}; selection-color: #ffffff;
}}

QSlider::groove:horizontal {{
    height: 5px; background: {c['border']}; border-radius: 3px;
}}
QSlider::sub-page:horizontal {{
    background: {c['accent']}; border-radius: 3px;
}}
QSlider::handle:horizontal {{
    width: 16px; height: 16px; margin: -6px 0;
    border-radius: 8px; background: #ffffff;
    border: 2px solid {c['accent']};
}}

QPushButton {{
    background: {inp}; border: 1px solid {c['border']};
    border-radius: 8px; padding: 6px 16px; font-size: 13px;
    color: {c['text']};
}}
QPushButton:hover {{ background: {hover}; }}
QPushButton:pressed {{ background: {c['pressed']}; }}
QPushButton:disabled {{ color: {c['hint']}; }}
QPushButton#primary {{ background: {c['accent']}; color: #ffffff;
                      border: none; font-weight: 600; }}
QPushButton#primary:hover {{ background: {c['accent_hover']}; }}
QPushButton#ghost {{ background: transparent; border: none;
                    color: {c['hint']}; padding: 6px 10px; }}
QPushButton#ghost:hover {{ color: {c['text']}; }}
QPushButton[cardAction="true"] {{ padding: 5px 14px; font-size: 12px; }}

QFrame#restartBanner {{
    background: {c['accent_soft']}; border: 1px solid {c['accent']};
    border-radius: 8px;
}}
QLabel#bannerText {{ color: {c['accent']}; font-size: 12px; }}

QFrame#marketCard {{
    background: {card}; border: 1px solid {c['divider']};
    border-radius: 10px;
}}
QFrame#marketCard:hover {{ border: 1px solid {c['border']};
                          background: {card_hover}; }}
QLabel#marketName {{ font-size: 14px; font-weight: 600; color: {c['text']}; }}
QLabel#marketVer {{ font-size: 11px; color: {c['hint']}; }}
QLabel#marketDesc {{ font-size: 12px; color: {c['sub_text']}; }}
QLabel#marketStatus {{ font-size: 11px; color: {c['hint']}; }}
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
