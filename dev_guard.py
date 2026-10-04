import os

# 这些目录里出现 py 一律不看（数据目录、缓存、打包产物、虚拟环境…）
SKIP_DIRS = {
    "settings", "plugins", "__pycache__", "_internal", "build", "dist",
    ".git", ".hg", ".svn", ".venv", "venv", "env", "node_modules",
    ".idea", ".vscode", ".workbuddy", "site-packages",
}

# 主入口候选文件名（大小写 / 空格 / 下划线 / 横线 全部归一化后比较）
ENTRY_NAMES = {
    "classdailyland", "classdaily", "classdailyl", "main", "app", "start",
    "run", "classdailylandapp",
}

# 本项目核心模块，出现在主入口特征里才算数
CORE_IMPORTS = (
    "from paths import", "import paths",
    "from theme import", "import theme",
    "from gui import", "import gui",
    "from controller import", "import controller",
)

MAX_DEPTH = 2          # 相对 root 的路径层数上限（root 本身 + 一层子目录）
MAX_LINES = 3000       # 只看文件开头这么多行（正常主入口都在这范围）
MAX_BYTES = 512 * 1024  # 单个文件最多读这么多，避免扫大文件卡住


def _norm_stem(name):
    """`Class Daily Land` / `class_daily_land` / `ClassDailyLand` 一律归一。"""
    s = os.path.splitext(name)[0]
    for ch in (" ", "_", "-"):
        s = s.replace(ch, "")
    return s.lower()


def _looks_like_entry(path):
    """返回 'name' / 'pattern' / '' —— 空串表示不是主入口。

    注意：只在「真实代码行」上做特征判断，必须跳过注释和 docstring。
    否则本模块自己写在文档字符串里的 `from paths import` 字样也会被算成
    命中，命中列表里就会多出一个无关文件。
    """
    try:
        stem = _norm_stem(os.path.basename(path))
    except Exception:
        return ""
    if stem in ENTRY_NAMES:
        return "name"
    try:
        with open(path, "r", encoding="utf-8-sig", errors="ignore") as f:
            lines = f.readlines(MAX_BYTES)
    except Exception:
        return ""
    if not lines:
        return ""
    # 本模块自己只是扫描工具（内部也 from paths import + 带 __main__ 块），
    # 不该出现在命中列表里吓人
    if _norm_stem(os.path.basename(path)) == "devguard":
        return ""
    core = False
    main = False
    in_doc = False
    for raw in lines[:MAX_LINES]:
        s = raw.strip()
        if s.startswith('"""') or s.startswith("'''"):
            in_doc = not in_doc
            continue
        if in_doc or s.startswith("#"):
            continue
        if not core and (s.startswith("import ") or s.startswith("from ")):
            if any(k in s for k in CORE_IMPORTS):
                core = True
        # 顶层 `if __name__ == '__main__':` 才算主入口，行内字符串不算
        if not main and s.startswith("if ") and "__main__" in s:
            main = True
        if core and main:
            return "pattern"
    return ""


def scan_source_entry(root, max_depth=MAX_DEPTH):
    """扫描 root（含一层子目录）里命中的主入口 py。

    返回 [(绝对路径, 命中原因), ...]，按路径排序；找不到就返回空列表。
    """
    hits = []
    if not root or not os.path.isdir(root):
        return hits
    for dirpath, dirnames, filenames in os.walk(root):
        rel = os.path.relpath(dirpath, root)
        depth = 0 if rel == "." else (rel.count(os.sep) + rel.count("/") + 1)
        if depth > max_depth:
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames
                       if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            if not fn.lower().endswith(".py"):
                continue
            path = os.path.join(dirpath, fn)
            try:
                if os.path.islink(path) or not os.path.isfile(path):
                    continue
            except Exception:
                continue
            how = _looks_like_entry(path)
            if how:
                hits.append((path, how))
    hits.sort(key=lambda h: h[0])
    return hits


def is_source_tree(root):
    """当前目录是不是「源码运行模式」（命中的主入口存在即为 True）。"""
    try:
        return bool(scan_source_entry(root))
    except Exception:
        return False


def brief_names(hits, limit=3):
    """把命中的文件名拼成一句话，给弹窗文案用。"""
    names = [os.path.basename(p) for p, _ in hits]
    if len(names) <= limit:
        return "、".join(names)
    return "、".join(names[:limit]) + f" 等 {len(names)} 个文件"


def guard_enabled():
    """读 settings.json 的 block_update_on_source，默认True（保护开启）。"""
    try:
        from paths import CONFIG_DIR
        import json
        with open(os.path.join(CONFIG_DIR, "settings.json"), "r",
                  encoding="utf-8") as f:
            data = json.load(f)
        return bool(data.get("block_update_on_source", True))
    except Exception:
        return True


if __name__ == "__main__":
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(
        os.path.abspath(__file__))
    found = scan_source_entry(root)
    print(f"扫描 {root}")
    if not found:
        print("  没找到主入口源码 —— 正常打包版的行为")
    else:
        for p, how in found:
            print(f"  命中 [{how}] {p}")
