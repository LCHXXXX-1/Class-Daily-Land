"""接入项目内置的 QML 设置中心。"""
import os
import sys

from paths import RESOURCE_ROOT

_BUNDLED_DIR = os.path.join(RESOURCE_ROOT, "settings_qml")


def _has_settings_qml(root):
    """目录像不像一个 QML 设置中心项目（有 qml/Settings.qml 才算）。"""
    return bool(root) and os.path.isfile(os.path.join(root, "qml", "Settings.qml"))


def _qml_project_root():
    """使用显式开发覆盖项；否则加载随应用发布的设置界面。"""
    override = os.environ.get("CDL_QML_SETTINGS_DIR")
    if override:
        if _has_settings_qml(override):
            return os.path.normpath(override)
        print("[settings] CDL_QML_SETTINGS_DIR does not contain qml/Settings.qml: %s" % override)
    if _has_settings_qml(_BUNDLED_DIR):
        return os.path.normpath(_BUNDLED_DIR)
    return None


def _ensure_importable(root):
    if root not in sys.path:
        sys.path.insert(0, root)


def is_available():
    """QML 设置中心能不能起（缺 RinUI / 缺 QtQuick / 找不到项目都算不能）。"""
    root = _qml_project_root()
    if root is None:
        print("[settings] Bundled QML settings directory is missing")
        return False
    _ensure_importable(root)
    try:
        import app.embed as embed
    except Exception as exc:
        print("[settings] QML/RinUI backend unavailable: %s" % exc)
        return False
    return embed.is_available()


def create_dialog(parent, *, settings, schedule_manager=None, duty_manager=None,
                  homework_manager=None, plugin_manager=None, controller=None,
                  app=None, start_page=None):
    """构建 QML 设置窗口；不可用返回 None（调用方回退原生 settings_dialog_v4）。"""
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
