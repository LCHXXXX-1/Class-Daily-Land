"""ClassDailyLand-QML —— 设置中心（QML + RinUI 试水版）。

这是 ClassDailyLand 的 **Python 版设置中心**，用 QML + RinUI 重写，
构图照 Class Widgets 2 的 Windows/Settings.qml：
FluentWindow + navigationItems（分组、父项可展开子项）+ SettingCard / SettingExpander。

与现有两个项目的关系：
  · ClassDailyLand-Py（Python + PySide6 + HTML 设置窗）—— 本项目是它的**候选替代**，尚未接回
  · ClassDailyLand-Net（C# + WPF + WebView2）—— 不动，包括它那份共用 ui/
数据格式仍走 settings/settings.json（snake_case 键），与两端可互读。
"""

__version__ = "0.1.0"
