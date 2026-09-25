import os
import json
from PySide6.QtWidgets import QMessageBox
from utils import get_app_root


def get_version():
    root = get_app_root()
    candidates = [
        os.path.join(root, '_internal', 'config.json'),
        os.path.join(root, 'config.json'),
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8-sig') as f:
                    v = str(json.load(f).get('version', '')).strip()
                if v:
                    return v.lstrip('v')
            except Exception:
                pass
    return '未知版本'


def show_about(parent=None):
    version = get_version()
    info = (
        f"Class Daily Land v{version}\n\n"
        "一个轻量级的班级日常管理工具\n\n"
        "作者: LCHXXXX、hexwisp72\n"
        "反馈: 2352240265@qq.com"
    )
    box = QMessageBox(parent)
    box.setWindowTitle("关于")
    box.setText(info)
    box.setIcon(QMessageBox.Information)
    box.exec()