"""探针：把原生 QWidget 塞进 QQuickWindow（WindowContainer）能不能成。

★ 判断依据不是截图 —— WindowContainer 里是**原生子窗口**，由系统合成，
  `QQuickWindow.grabWindow()` 抓不到它（只会得到一块空白，看着像失败，
  其实可能已经好了；抓屏幕又会抓到用户桌面，不能这么干）。

  所以改看**几何与父子关系**：嵌成功的话，那个 QWindow 的
  parent 会变成 Quick 窗口、geometry 会跟着容器走、isVisible 为真。
"""
from __future__ import annotations

import os
import sys

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QWindow
from PySide6.QtQuick import QQuickView
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QVBoxLayout,
                               QWidget)

QML = """
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root
    property var hostWindow: null
    property rect slot: Qt.rect(0, 0, 0, 0)

    Rectangle { anchors.fill: parent; color: "#eeeeee" }

    Rectangle {
        id: box
        anchors.fill: parent
        anchors.margins: 20
        anchors.topMargin: 60
        color: "white"
        border.color: "#cccccc"
        onWidthChanged: root.slot = Qt.rect(0, 0, width, height)
        onHeightChanged: root.slot = Qt.rect(0, 0, width, height)

        WindowContainer {
            id: container
            anchors.fill: parent
            window: root.hostWindow
        }
    }
}
"""


def build_widget() -> QWidget:
    page = QWidget()
    lay = QVBoxLayout(page)
    lay.setContentsMargins(18, 18, 18, 18)
    lay.setSpacing(10)
    title = QLabel("插件的原生设置页")
    title.setStyleSheet("font-size: 18px; font-weight: 600;")
    lay.addWidget(title)
    lay.addWidget(QLabel("确认 QWidget 真的挂上了。"))
    lay.addWidget(QCheckBox("启用某个开关"))
    box = QComboBox()
    box.addItems(["选项一", "选项二"])
    lay.addWidget(box)
    lay.addWidget(QLineEdit("可以输入文字"))
    row = QHBoxLayout()
    row.addWidget(QPushButton("取消"))
    row.addWidget(QPushButton("保存"))
    row.addStretch(1)
    lay.addLayout(row)
    lay.addStretch(1)
    return page


def main() -> int:
    app = QApplication(sys.argv[:1])
    page = build_widget()
    page.resize(600, 400)
    win = QWindow.fromWinId(int(page.winId()))
    print("原生句柄:", int(page.winId()))

    qml_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_host_probe.qml")
    with open(qml_path, "w", encoding="utf-8") as f:
        f.write(QML)

    view = QQuickView()
    # ★ QQuickView 默认是 SizeViewToRootObject：视图跟着根元素走，
    #   根 Item 没有隐式尺寸 → 根宽度恒为 0 → 容器宽度 -40 → 嵌入件 0x0。
    #   这里要反过来。
    view.setResizeMode(QQuickView.ResizeMode.SizeRootObjectToView)
    view.setSource(QUrl.fromLocalFile(qml_path))
    view.rootObject().setProperty("hostWindow", win)
    view.resize(760, 560)
    view.show()

    result = {"ok": False}

    def check() -> None:
        view_win = view
        box = view.rootObject().property("slot")
        print("嵌入件 parent:", win.parent(), " type:", type(win.parent()).__name__)
        print("嵌入件 visible:", win.isVisible(), " geometry:", win.geometry().getRect())
        print("容器槽位(相对 view):", box)
        print("view 全局位置:", view_win.geometry().getRect())
        embedded = win.parent() is not None and win.isVisible()
        sized = win.width() > 100 and win.height() > 100
        print("→ 父窗口已挂上:", embedded, " 已被布局撑开:", sized)
        result["ok"] = bool(embedded and sized)
        app.exit(0 if result["ok"] else 1)

    QTimer.singleShot(1200, check)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
