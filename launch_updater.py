"""主程序 → Launcher 的启动桥。

主程序不做版本比较、不做下载、不做解压。
一切更新逻辑都由 Launcher 承担。

- launch_hidden(): 启动时后台静默检查（Launcher_hide.exe）
- launch_visible(): 用户主动检查（Launcher.exe）

优先用 exe；exe 不可用时自动回退到源码 launcher.py / launcher_hide.py。
"""
import os
import sys
import tempfile
import subprocess

LAUNCHER_EXE = "Launcher.exe"
LAUNCHER_HIDE_EXE = "Launcher_hide.exe"
LAUNCHER_PY = "launcher.py"
LAUNCHER_HIDE_PY = "launcher_hide.py"

# 与 installer.py 的 QUIT_FLAG_DIR / QUIT_FLAG_NAME 保持一致
QUIT_FLAG_DIR = "ClassDailyLandLauncher"
QUIT_FLAG_NAME = "quit.flag"


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


def _spawn(cmd, cwd):
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
    try:
        subprocess.Popen(cmd, cwd=cwd, creationflags=flags)
        return True, ""
    except Exception as e:
        return False, f"启动更新器失败：{e}"


def _run(silent):
    app_dir = _app_dir()
    base_args = ["--target", app_dir, "--pid", str(os.getpid())]
    if silent:
        base_args.append("--silent")

    # 静默模式：优先 Launcher_hide.exe
    if silent:
        exe = _find_file(LAUNCHER_HIDE_EXE)
        if exe:
            return _spawn([exe] + base_args, os.path.dirname(exe))

    # 可见模式：优先 Launcher.exe（静默模式也作为兜底）
    exe = _find_file(LAUNCHER_EXE)
    if exe:
        return _spawn([exe] + base_args, os.path.dirname(exe))

    # 回退到源码脚本
    py_name = LAUNCHER_HIDE_PY if silent else LAUNCHER_PY
    py = _find_file(py_name)
    if py is None and silent:
        py = _find_file(LAUNCHER_PY)      # 找不到 hide 就退回 launcher.py + --silent
    if py:
        python = sys.executable or "python"
        return _spawn([python, py] + base_args, os.path.dirname(py))

    return False, "未找到更新器（Launcher.exe / Launcher_hide.exe 均不存在）"


def launch_hidden():
    """启动时后台静默检查更新。"""
    return _run(silent=True)


def launch_visible():
    """用户主动检查更新。"""
    return _run(silent=False)


def get_quit_flag_path():
    """退出信号标志文件路径（Launcher 写它，主程序轮询它）。

    必须与 installer.py 的 signal_quit() 写入位置完全一致。
    """
    return os.path.join(tempfile.gettempdir(), QUIT_FLAG_DIR, QUIT_FLAG_NAME)


def clear_quit_flag():
    try:
        os.remove(get_quit_flag_path())
    except Exception:
        pass