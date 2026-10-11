"""QML 设置中心（ClassDailyLand-QML）接入层。

真正的实现在独立项目 ``../ClassDailyLand-QML``（QML + RinUI）里，
本模块只做三件事：

1. 定位那个项目：环境变量 ``CDL_QML_SETTINGS_DIR`` 优先，其次找
   APP_ROOT 旁边的 ``ClassDailyLand-QML`` 目录；
2. 把它插进 sys.path，导入其 ``app.embed``；
3. 把 gui.py 传来的真实服务转发给 embed，返回模态窗口适配器。

打不到 / 起不来一律返回 None，gui.py 据此走下一层回退
（Web 版 ui/ → 原生 settings_dialog_v4），任何一层不允许白屏。

注意：QML 项目不在本仓库里、也没有版本历史，改它之前先在那边备份。
"""
import os
import sys

from paths import APP_ROOT


def _qml_project_root():
    override = os.environ.get("CDL_QML_SETTINGS_DIR")
    candidates = [override] if override else []
    sibling = os.path.normpath(os.path.join(APP_ROOT, "..", "ClassDailyLand-QML"))
    candidates.append(sibling)
    for root in candidates:
        if root and os.path.isfile(os.path.join(root, "qml", "Settings.qml")):
            return root
    return None


def _ensure_importable(root):
    if root not in sys.path:
        sys.path.insert(0, root)


def is_available():
    """QML 设置中心能不能起（缺 RinUI / 缺 QtQuick / 找不到项目都算不能）。"""
    root = _qml_project_root()
    if root is None:
        return False
    _ensure_importable(root)
    try:
        import app.embed as embed
    except Exception:
        return False
    return embed.is_available()


def create_dialog(parent, *, settings, schedule_manager=None, duty_manager=None,
                  homework_manager=None, plugin_manager=None, controller=None,
                  app=None, start_page=None):
    """构建 QML 设置窗口；不可用返回 None（调用方回退 Web 版 / 原生窗）。"""
    root = _qml_project_root()
    if root is None:
        return None
    _ensure_importable(root)
    import app.embed as embed
    return embed.create_settings_dialog(
        parent=parent,
        settings=settings,
        schedule_manager=schedule_manager,
        duty_manager=duty_manager,
        homework_manager=homework_manager,
        plugin_manager=plugin_manager,
        controller=controller,
        app=app,
        start_page=start_page,
    )
