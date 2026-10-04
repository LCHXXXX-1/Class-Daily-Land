import os
import sys
import subprocess

LAUNCHER_EXE = "Launcher.exe"
LAUNCHER_PY = "launcher.py"

# 与 installer.signal_quit 保持一致：%TEMP%/ClassDailyLandLauncher/quit.flag
QUIT_FLAG_NAME = os.path.join("ClassDailyLandLauncher", "quit.flag")


def _app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _search_dirs():
    app = _app_dir()
    parent = os.path.dirname(app)
    dirs = [parent, app, os.path.join(app, "_internal")]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        dirs.append(meipass)
    return dirs


def _find_file(name):
    for d in _search_dirs():
        p = os.path.join(d, name)
        if os.path.isfile(p):
            return p
    return None


# ==================================================
# 源码运行保护：检测到主入口 py 就不拉起更新器
# 弹窗统一收在这里，gui.py / settings_dialog_v4.py 三个入口都不必自己管，
# 以后也不会从某个旁路绕过这段拦截。
# ==================================================
def _guard_hits():
    """返回 [(路径, 命中原因), ...]；没有源码 / 保护被关掉时是空列表。"""
    try:
        import dev_guard
    except Exception:
        return []
    if not dev_guard.guard_enabled():
        return []
    try:
        return dev_guard.scan_source_entry(_app_dir())
    except Exception:
        return []


def _backup_tip(hits):
    try:
        from dev_guard import brief_names
        names = brief_names(hits)
    except Exception:
        names = f"{len(hits)} 个文件"
    return (
        "建议先手动备份：把整个程序目录复制一份（或先 git commit），"
        "否则更新会用发布版直接覆盖这些文件，你本地没保存的改动会丢。\n"
        f"命中文件：{names}"
    )


def _notify_source_detected(hits):
    """启动时后台检查命中：不拉起更新器，弹一次说明为什么没更新。

    只给一个「知道了」，不需要用户做决定；延迟 1.2 秒弹，等主窗口露出来，
    免得刚开机就被框住。
    """
    try:
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication, QMessageBox
    except Exception:
        return
    text = (
        "检测到程序目录下有未打包的主入口源码，已跳过自动更新。\n\n"
        f"{_backup_tip(hits)}\n\n"
        "（想更新可以在「关于 → 检查更新」里手动触发，届时会再确认一次）"
    )

    def _show():
        try:
            box = QMessageBox()
            box.setWindowTitle("源码运行 · 已跳过自动更新")
            box.setIcon(QMessageBox.Information)
            box.setText(text)
            box.setMinimumWidth(420)
            box.addButton("知道了", QMessageBox.AcceptRole)
            box.exec()
        except Exception:
            pass

    try:
        if QApplication.instance() is not None:
            QTimer.singleShot(1200, _show)
            return
    except Exception:
        pass
    _show()


def _confirm_force_update(hits):
    """用户主动检查更新时命中：不拉起，先弹窗提醒备份并请求确认。

    返回 True = 用户坚持要更新（此时由调用方放行）；
    返回 False = 取消 / 关闭，一律不拉起更新器。
    """
    try:
        from PySide6.QtWidgets import QMessageBox
    except Exception:
        # 连 Qt 都起不来（极端情况），给个纯文本提示，仍然不拉起
        print("[更新] 检测到本地源码，已跳过：", _backup_tip(hits))
        return False
    box = QMessageBox()
    box.setWindowTitle("检测到本地源码，未执行更新")
    box.setIcon(QMessageBox.Warning)
    box.setText(
        "程序目录下检测到未打包的主入口源码，继续更新会用发布版覆盖这些"
        "源文件，导致你本地的改动丢失。\n\n"
        + _backup_tip(hits)
    )
    box.setMinimumWidth(460)
    btn_cancel = box.addButton("取消，不更新", QMessageBox.NoRole)
    btn_force = box.addButton("仍然更新（已备份）", QMessageBox.YesRole)
    box.setDefaultButton(btn_cancel)
    box.exec()
    return box.clickedButton() is btn_force


def _spawn(cmd, cwd):
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
    try:
        subprocess.Popen(cmd, cwd=cwd, creationflags=flags)
        return True, ""
    except Exception as e:
        return False, f"启动更新器失败：{e}"


def _run(silent, force=False):
    app_dir = _app_dir()

    # ---- 源码运行保护：命中主入口就别拉起更新器 ----
    # 只有两种结果：要么直接走人（不拉起），要么让用户确认后**继续往下**。
    # 千万不能在用户点了「仍然更新」之后这里就 return，那样等于没更新。
    if not force:
        hits = _guard_hits()
        if hits:
            if silent:
                # 启动时：不拉起，弹一次说明（只有一个「知道了」，不要求做决定）
                _notify_source_detected(hits)
                return False, ""            # 关键：拦下即返回，不 spawn
            if not _confirm_force_update(hits):
                # 主动检查：用户取消 / 关窗 —— 一律不拉起，也不算失败
                return True, ""
            # 用户点了「仍然更新（已备份）」—— 不 return，继续下面的 spawn

    base_args = ["--target", app_dir, "--pid", str(os.getpid())]
    if silent:
        base_args.append("--silent")

    # 1) 优先用 exe
    exe = _find_file(LAUNCHER_EXE)
    if exe:
        return _spawn([exe] + base_args, os.path.dirname(exe))

    # 2) exe 不可用 → 用源码 launcher.py 兜底（编辑器环境）
    py = _find_file(LAUNCHER_PY)
    if py:
        python = sys.executable or "python"
        return _spawn([python, py] + base_args, os.path.dirname(py))

    return False, f"既没找到 {LAUNCHER_EXE}，也没找到 {LAUNCHER_PY}"


def launch_hidden(force=False):
    """启动时后台静默检查更新。

    force=False（默认）：检测到本地源码就只弹说明，不拉起更新器。
    force=True：无视保护（仅由用户在确认弹窗里显式选择后使用）。
    """
    return _run(silent=True, force=force)


def launch_visible(force=False):
    """用户主动检查更新。

    force=False（默认）：检测到本地源码先弹窗提醒备份并确认，
    用户不点「仍然更新（已备份）」就不会拉起更新器。
    """
    return _run(silent=False, force=force)


def get_quit_flag_path():
    """退出信号标志文件路径（Launcher 写它，主程序轮询它）。"""
    import tempfile
    return os.path.join(tempfile.gettempdir(), QUIT_FLAG_NAME)


def clear_quit_flag():
    try:
        os.remove(get_quit_flag_path())
    except Exception:
        pass