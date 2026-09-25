"""主程序 → Launcher 的启动桥。

主程序不做版本比较、不做下载、不做解压。
一切更新逻辑都由 Launcher 承担。

- launch_hidden(): 启动时后台静默检查（用 Launcher.exe / launcher.py + --silent）
- launch_visible(): 用户主动检查（用 Launcher.exe / launcher.py）

优先用 exe；exe 不可用时自动回退到源码 launcher.py。
"""
import os
import sys
import subprocess

LAUNCHER_EXE = "Launcher.exe"
LAUNCHER_PY = "launcher.py"

QUIT_FLAG_NAME = "ClassBoard_quit.flag"


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

    # 1) 优先用 exe
    exe = _find_file(LAUNCHER_EXE)
    if exe:
        return _spawn([exe] + base_args, os.path.dirname(exe))

    # 2) exe 不可用 → 用源码 launcher.py 兜底（编辑器环境）
    py = _find_file(LAUNCHER_PY)
    if py:
        python = sys.executable or "python"
        return _spawn([python, py] + base_args, os.path.dirname(py))

    return False, f"未找到 {LAUNCHER_EXE}，也没找到 {LAUNCHER_PY}"


def launch_hidden():
    """启动时后台静默检查更新。"""
    return _run(silent=True)


def launch_visible():
    """用户主动检查更新。"""
    return _run(silent=False)


def get_quit_flag_path():
    """退出信号标志文件路径（Launcher 写它，主程序轮询它）。"""
    import tempfile
    return os.path.join(tempfile.gettempdir(), QUIT_FLAG_NAME)


def clear_quit_flag():
    try:
        os.remove(get_quit_flag_path())
    except Exception:
        pass