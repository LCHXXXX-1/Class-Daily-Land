import os
import json
from PySide6.QtWidgets import QMessageBox
from utils import get_app_root, APP_NAME
from paths import RESOURCE_ROOT


def get_version():
    """从 config.json 读版本号（与 Launcher 同源），打包后优先 _internal。"""
    roots = []
    for root in (RESOURCE_ROOT, get_app_root(),
                 os.path.join(get_app_root(), '_internal')):
        if root and root not in roots:
            roots.append(root)
    for root in roots:
        path = os.path.join(root, 'config.json')
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8-sig') as f:
                    data = json.load(f)
                version = str(data.get('version', '')).strip().lstrip('v')
                if version:
                    return version
            except Exception:
                pass
    return '版本成谜'


def show_about(parent=None):
    version = get_version()
    info = (
        f"{APP_NAME} v{version}\n\n一个轻量级的班级日常管理小工具 🎒\n\n作者: LCHXXXX、hexwisp72\n反馈: 2352240265@qq.com"
    )
    box = QMessageBox(parent)
    box.setWindowTitle("关于这个项目")
    box.setText(info)
    box.setIcon(QMessageBox.Information)
    box.exec()