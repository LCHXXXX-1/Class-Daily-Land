"""主程序 → Launcher 的启动桥。

主程序不做版本比较、不做下载、不做解压。
一切更新逻辑都由根目录的 ClassBoardLauncher.exe 承担。
"""
import os
import sys
import shutil
import tempfile
import subprocess

LAUNCHER_EXE = "ClassBoardLauncher.exe"


def _app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _find_launcher():
    """launcher 与 app 同级，平铺在项目根。"""
    app = _app_dir()
    parent = os.path.dirname(app)
    candidates = [
        os.path.join(parent, LAUNCHER_EXE),       # <root>/ClassBoardLauncher.exe  ← 首选
        os.path.join(app, LAUNCHER_EXE),          # 兜底
        os.path.join(app, "_internal", LAUNCHER_EXE),
        os.path.join(getattr(sys, "_MEIPASS", parent), LAUNCHER_EXE),
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    return None


def launch(auto=False, silent=False):
    """
    auto   : 发现新版本时直接开始下载（不再询问）
    silent : 无新版本时静默退出，不弹窗

    返回 (ok: bool, message: str)
    """
    src = _find_launcher()
    if not src:
        return False, f"未找到 {LAUNCHER_EXE}，请确认它与 app 目录同级"

    # 关键：复制到 %TEMP% 再运行，避免覆盖自己
    tmp_dir = os.path.join(tempfile.gettempdir(), "ClassBoardLauncher")
    try:
        os.makedirs(tmp_dir, exist_ok=True)
        dst = os.path.join(tmp_dir, LAUNCHER_EXE)
        if os.path.abspath(src) != os.path.abspath(dst):
            shutil.copy2(src, dst)
    except Exception as e:
        return False, f"复制更新器失败：{e}"

    app_dir = _app_dir()
    exe_name = (os.path.basename(sys.executable)
                if getattr(sys, "frozen", False) else "ClassBoard.exe")

    args = [dst, "--target", app_dir, "--exe", exe_name,
            "--pid", str(os.getpid())]
    if auto:
        args.append("--auto")
    if silent:
        args.append("--silent")

    flags = 0
    if sys.platform == "win32":
        flags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS

    try:
        subprocess.Popen(args, cwd=tmp_dir, creationflags=flags)
    except Exception as e:
        return False, f"启动更新器失败：{e}"
    return True, ""