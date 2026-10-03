"""插件第三方依赖库：按需「从服务器下载 → 校验 → 落盘」与卸载回收。

插件在 plugin.json 用 ``requires`` 声明第三方包名（小写、不写版本），
宿主从 ``{基础地址}/<包名>.json`` 拉安装清单（基础地址默认指向
``https://plugins.class-daily-land.de5.net/packages``），清单格式：

    {
      "name": "requests",                    ← 包名（必须与请求的一致）
      "version": "2.31.0",                   ← 固定版本（服务器说了算）
      "requires": ["urllib3", "certifi"],    ← 其它依赖（递归安装，去重防环）
      "files": [                             ← 全部文件，逐文件 sha256 校验
        {
          "path": "requests/__init__.py",    ← 包内相对路径（防目录穿越）
          "sha256": "…64 位十六进制…",
          "urls": ["https://镜像1/…", "https://镜像2/…"],  ← 多镜像逐个试
          "size": 4096                       ← 可选，仅展示用
        }
      ]
    }

安装位置 ``plugins/packages/<包名>/``，所有包共用这一层目录（已在 sys.path，
装好后插件里 ``import requests`` 之类直接可用）。
登记表 ``plugins/packages/packages.json`` 记录每个包的固定版本与
``used_by``（哪些插件在用）；插件卸载时把自己从 used_by 摘掉，
used_by 空了的包才真正删目录。

进度回调 emit(ev)，ev 是 dict：
    stage   manifest / download / verify / extract / done / failed
    plugin  触发安装的插件名（可为空串）
    package 正在处理的包名
    label   文案用描述（依赖会写成 “requests 的依赖 urllib3”）
    file    当前文件名（download / verify 阶段）
    pct     当前文件百分比 0-100（总数未知时为 -1）
    done    当前文件已下载字节
    total   当前文件总字节（未知为 0）
    speed   实时速度字符串（如 “1.23 MB/s”）
    index   第几个包 ｜ count 共几个包
    text    预先拼好的一行中文，UI 可直接显示

约定：全部函数都在后台线程调用；不做版本约束解析、不查 PyPI、
不多版本共存、不在主线程发网络请求。错误 kind 只有三种：
MISSING_DEP / DOWNLOAD_FAILED / LOAD_ERROR。

清单里的 URL 必须是**纯 ASCII**：urllib 拼请求行时会按 ASCII 编码，
地址里混进省略号 … / 全角标点 / 空格 会直接抛 UnicodeEncodeError
（不是网络问题，换镜像也没用），这类地址在 parse_manifest 阶段就被拦下。

wheel 型清单只能放**一个** wheel（``wheel = 文件只有一个且以 .whl 结尾``，
为真时只解包这一个），因此必须挑对 ABI 标签：cp311 的包在 3.12 上装得好好的
却 import 不了（``_imaging.cp311-win_amd64.pyd`` 3.12 根本不会去找），
落盘后会做一次 ABI 自检，不适配直接报 LOAD_ERROR，不留假成功。
"""
import hashlib
import importlib.machinery
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import zipfile

from storage import read_json, write_json

# 依赖包根目录下的登记表文件名
DB_NAME = 'packages.json'
# 临时目录前缀（建在 packages/ 内部，保证同盘、可原子改名）
TMP_PREFIX = '.tmp_'
# ---------------- 下载源 ----------------
# 每个源指向一个“依赖清单目录”，目录里是 <包名>.json（见 fetch_manifest）。
# base    primary 清单地址（raw 直链）
# mirrors 备用镜像，按顺序重试（GitHub raw 在国内常连不通，配 jsDelivr）
# list    如何列出该源有哪些包：目前两个源都是调各自的 Contents API
# api     Contents API 地址（返回文件列表 JSON）
PACKAGE_SOURCES = {
    'gitee': {
        'label': 'Gitee',
        'base': 'https://gitee.com/lchxxxx/class-daily-land/raw/plugins/packages',
        'list': 'api',
        'api': ('https://gitee.com/api/v5/repos/lchxxxx/class-daily-land'
                '/contents/packages?ref=plugins'),
    },
    'github': {
        'label': 'GitHub',
        'base': ('https://raw.githubusercontent.com/LCHXXXX-1'
                 '/Class-Daily-Land/plugins/packages'),
        'mirrors': [
            ('https://cdn.jsdelivr.net/gh/LCHXXXX-1'
             '/Class-Daily-Land@plugins/packages'),
        ],
        'list': 'api',
        'api': ('https://api.github.com/repos/LCHXXXX-1'
                '/Class-Daily-Land/contents/packages?ref=plugins'),
    },
}
DEFAULT_SOURCE = 'gitee'
# 清单服务器兜底地址（settings.packages_base_url 为空时按 packages_source 取）。
# 直接指向依赖清单目录，fetch_manifest 会再拼上 /<包名>.json。
DEFAULT_BASE = PACKAGE_SOURCES[DEFAULT_SOURCE]['base']


def resolve_bases(source_id='', custom_url=''):
    """解析清单 base 候选列表（主地址 + 镜像）。

    custom_url（packages_base_url）非空时只认它；未知 / 空的 source_id
    回退到 DEFAULT_SOURCE。
    """
    custom = str(custom_url or '').strip().rstrip('/')
    if custom:
        return [custom]
    src = PACKAGE_SOURCES.get(str(source_id or '').strip().lower())
    if src is None:
        src = PACKAGE_SOURCES[DEFAULT_SOURCE]
    return [src['base']] + list(src.get('mirrors') or [])


def resolve_base(source_id='', custom_url=''):
    """单个主清单地址（取 resolve_bases 的第一个）。"""
    return resolve_bases(source_id, custom_url)[0]

USER_AGENT = 'ClassDailyLand-DepInstaller/1.0'
# urlopen 的 timeout 必须是单个秒数（元组会直接抛 TypeError）
TIMEOUT = 30
CHUNK = 65536
MAX_FILE_BYTES = 300 * 1024 * 1024      # 单文件 300MB 封顶，防清单写飞

# 包名：小写字母开头，允许小写字母 / 数字 / 点 / 下划线 / 短横线
PKG_NAME_RE = re.compile(r'^[a-z][a-z0-9._-]*$')
_SHA_RE = re.compile(r'^[0-9a-fA-F]{64}$')


class DepError(Exception):
    """依赖安装错误：kind ∈ MISSING_DEP / DOWNLOAD_FAILED / LOAD_ERROR。"""

    def __init__(self, kind, msg):
        Exception.__init__(self, msg)
        self.kind = kind
        self.msg = str(msg)


class AbortInstall(Exception):
    """宿主退出等原因中止安装循环。"""


# ---------------- 小工具 ----------------
def now_iso():
    try:
        return time.strftime('%Y-%m-%dT%H:%M:%S')
    except Exception:
        return ''


def fmt_mb(n):
    """字节数 → 展示字符串（自动 B / KB / MB）。"""
    try:
        n = float(n)
    except (TypeError, ValueError):
        return '?'
    if n >= 1048576:
        return '%.1f MB' % (n / 1048576.0)
    if n >= 1024:
        return '%.0f KB' % (n / 1024.0)
    return '%d B' % int(n)


def fmt_speed(bps):
    """字节/秒 → 实时速度展示字符串。"""
    try:
        bps = float(bps)
    except (TypeError, ValueError):
        return '? MB/s'
    if bps >= 1048576:
        return '%.2f MB/s' % (bps / 1048576.0)
    return '%.0f KB/s' % (bps / 1024.0)


def safe_join(base, rel):
    """防目录穿越：只允许落在 base 内部，非法返回 None。

    含 ".." 段的一律拒绝（不给“静默清洗”留余地），绝对路径同样拒绝。
    """
    rel = str(rel or '').replace('\\', '/')
    if rel.startswith('/'):
        return None
    parts = [p for p in rel.split('/') if p not in ('', '.')]
    if not parts or any(p == '..' for p in parts):
        return None
    dest = os.path.join(base, *parts)
    base_abs = os.path.abspath(base)
    dest_abs = os.path.abspath(dest)
    if not (dest_abs == base_abs
            or dest_abs.startswith(base_abs + os.sep)):
        return None
    return dest


def normalize_requires(raw, self_name=''):
    """requires 字段 → 合法小写包名列表（去重、去自环）。

    不合法的条目直接忽略：宁可放过作者拼写手滑，也别把整个插件卡死。
    """
    if isinstance(raw, str):
        raw = [raw]
    out = []
    if isinstance(raw, (list, tuple)):
        for item in raw:
            n = str(item or '').strip().lower()
            if PKG_NAME_RE.match(n) and n != self_name and n not in out:
                out.append(n)
    return out


def _url_reject_reason(url):
    """地址「注定请求不出去」时返回中文原因，否则返回空串。

    重点是非 ASCII：省略号 …、全角标点、中文、空格 都会让 urllib 在编码
    请求行时抛 UnicodeEncodeError。这不是网络问题——换镜像、重试都没用，
    只能改清单。典型成因是清单生成时把长路径截断成了 "…"。
    """
    try:
        url.encode('ascii')
    except UnicodeEncodeError:
        bad = ''.join(sorted({c for c in url if ord(c) > 0x7e}))
        return '含非 ASCII 字符 %r' % bad
    if any(c.isspace() for c in url):
        return '含空白字符'
    return ''


def _https_urls(item):
    """从清单条目提取 https 镜像列表（urls 列表或 url 单值都收）。

    返回 (可用地址列表, 被剔除的 [(地址, 原因)])。剔除的是注定请求不出去的
    地址：留着只会让每个镜像都失败一次，最后报一个用户看不懂的
    UnicodeEncodeError。全被剔除时由调用方给出可读的错误说明。
    """
    raw = item.get('urls')
    if raw is None:
        raw = item.get('url')
    cands = raw if isinstance(raw, (list, tuple)) else [raw]
    urls, bad = [], []
    for u in cands:
        u = str(u or '').strip()
        if not u or u in urls or not u.startswith('https://'):
            continue
        reason = _url_reject_reason(u)
        if reason:
            bad.append((u, reason))
        else:
            urls.append(u)
    return urls, bad


# ---------------- 清单 ----------------
def parse_manifest(data, pkg):
    """校验清单结构，返回 (manifest, None) 或 (None, 错误说明)。"""
    if not isinstance(data, dict):
        return None, '清单不是 JSON 对象'
    name = str(data.get('name') or '').strip().lower()
    if name != pkg:
        return None, '清单里的包名 %r 与请求的 %r 不一致' % (name, pkg)
    version = str(data.get('version') or '').strip()
    if not version or len(version) > 64:
        return None, 'version 为空或过长'
    if any(c in version for c in '\\/:*?"<>|'):
        return None, 'version 含非法字符: %r' % version

    reqs = normalize_requires(data.get('requires'), pkg)

    raw_files = data.get('files')
    if not isinstance(raw_files, list) or not raw_files:
        return None, 'files 缺失或为空'
    files = []
    for item in raw_files:
        if not isinstance(item, dict):
            continue
        # 兼容两种清单写法：path（逐文件清单）与 name（wheel 文件名）
        rel = str(item.get('path') or item.get('name') or '').strip()
        rel = rel.replace('\\', '/')
        if not rel or rel in ('.', '..'):
            continue
        if rel.startswith('/') or re.match(r'^[A-Za-z]:', rel):
            return None, '文件路径不合法: %s' % rel
        if safe_join(os.sep + 'base', rel) is None:
            return None, '文件路径不合法: %s' % rel
        sha = str(item.get('sha256') or '').strip().lower()
        if not _SHA_RE.match(sha):
            return None, '文件 %s 的 sha256 非法' % rel
        urls, bad = _https_urls(item)
        if not urls:
            if bad:
                # 典型场景：清单生成时把路径截断成了省略号 …
                return None, ('文件 %s 的下载地址全都不合法（%s，例如 %s）'
                              '——这类地址一请求就抛 UnicodeEncodeError，'
                              '请重新生成依赖清单，别手写 URL'
                              % (rel, '；'.join(r for _u, r in bad),
                                 bad[0][0][:90]))
            return None, '文件 %s 没有可用的 https 镜像' % rel
        for _u, _r in bad:
            print('[plugin_deps] 清单 %s 跳过不可用地址（%s）：%s'
                  % (pkg, _r, _u[:90]))
        size = 0
        try:
            size = max(0, int(item.get('size') or 0))
        except (TypeError, ValueError):
            size = 0
        files.append({'rel': rel, 'sha256': sha,
                      'urls': urls, 'size': size})
    if not files:
        return None, 'files 里没有任何合法条目'
    wheel = (len(files) == 1
             and str(files[0]['rel']).lower().endswith('.whl'))
    return {'name': pkg, 'version': version,
            'requires': reqs, 'files': files, 'wheel': wheel}, None


def fetch_manifest(base_url, pkg, timeout=TIMEOUT):
    """从 {base}/<pkg>.json 拉清单并校验；失败抛 DepError。

    base_url 可以是单个字符串，也可以是候选列表（主地址 + 镜像），
    按顺序重试，全部失败才抛最后一个错误。地址指向依赖清单目录
    （默认 ``.../packages``）；为兼容只给站点根（不含 /packages）的
    旧写法，会自动补上 /packages 再拼包名。
    """
    bases = ([base_url] if isinstance(base_url, str)
             else [b for b in (base_url or ()) if b])
    if not bases:
        bases = [DEFAULT_BASE]
    last = None
    for b in bases:
        try:
            return _fetch_manifest_one(b, pkg, timeout)
        except DepError as e:
            last = e
    raise last or DepError('DOWNLOAD_FAILED', '没有可用的清单地址')


def _fetch_manifest_one(base_url, pkg, timeout=TIMEOUT):
    """单个地址拉清单：服务器明确说没有这个包（HTTP 404）→ MISSING_DEP，
    其它网络问题 → DOWNLOAD_FAILED。"""
    base = str(base_url or DEFAULT_BASE).strip().rstrip('/')
    if base and not base.endswith('/packages'):
        base = '%s/packages' % base
    url = '%s/%s.json' % (base, pkg)
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            blob = resp.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise DepError('MISSING_DEP', '服务器上没有 %s 的清单' % pkg)
        raise DepError('DOWNLOAD_FAILED',
                       '拉取 %s 清单失败: HTTP %s' % (pkg, e.code))
    except Exception as e:
        raise DepError('DOWNLOAD_FAILED', '拉取 %s 清单失败: %s' % (pkg, e))
    try:
        data = json.loads(blob.decode('utf-8-sig'))
    except Exception as e:
        raise DepError('DOWNLOAD_FAILED', '清单 %s 不是有效 JSON: %s'
                       % (pkg, e))
    manifest, err = parse_manifest(data, pkg)
    if err:
        raise DepError('DOWNLOAD_FAILED', '清单 %s 不合法: %s' % (pkg, err))
    return manifest


# ---------------- 登记表 packages.json ----------------
class PackageDB:
    """plugins/packages/packages.json 的读写（进程内加锁 + 原子写）。

    结构::

        {"packages": {"requests": {"version": "2.31.0",
                                   "used_by": ["clock"],
                                   "files": 12,
                                   "installed_at": "2026-…"}},
         "updated_at": "2026-…"}
    """

    def __init__(self, root):
        self.root = root
        self.path = os.path.join(root, DB_NAME)
        self._lock = threading.Lock()

    def _read(self):
        data = read_json(self.path, default={}) or {}
        pkgs = data.get('packages') if isinstance(data, dict) else None
        return pkgs if isinstance(pkgs, dict) else {}

    def entry(self, pkg):
        """某包的登记 dict；未登记返回 {}。"""
        try:
            with self._lock:
                ent = self._read().get(pkg)
            return dict(ent) if isinstance(ent, dict) else {}
        except Exception:
            return {}

    def installed_version(self, pkg):
        """已安装版本号；目录实际不存在也给空串（与磁盘不一致视为未装）。"""
        ent = self.entry(pkg)
        if not ent:
            return ''
        try:
            if not os.path.isdir(os.path.join(self.root, pkg)):
                return ''
        except Exception:
            return ''
        return str(ent.get('version') or '')

    def record_use(self, pkg, version, plugin, files=0):
        """登记 “pkg version 被 plugin 在用”；同版本重复只合并 used_by。"""
        with self._lock:
            try:
                pkgs = self._read()
                ent = pkgs.get(pkg)
                if not isinstance(ent, dict):
                    ent = {}
                ent['version'] = str(version or ent.get('version')
                                     or 'unknown')
                used = ent.get('used_by')
                if not isinstance(used, list):
                    used = []
                if plugin:
                    if plugin not in used:
                        used.append(plugin)
                else:
                    ent['manual'] = True      # 手动安装：不随插件卸载回收
                ent['used_by'] = used
                if files:
                    ent['files'] = int(files)
                if not ent.get('installed_at'):
                    ent['installed_at'] = now_iso()
                pkgs[pkg] = ent
                write_json(self.path, {'packages': pkgs,
                                       'updated_at': now_iso()})
            except Exception:
                pass

    def release(self, plugin):
        """插件卸载：把自己从所有包的 used_by 里摘掉，used_by 空了才删。

        返回被删除目录的包名列表。
        """
        removed = []
        with self._lock:
            try:
                pkgs = self._read()
                dirty = False
                for name in list(pkgs):
                    ent = pkgs.get(name)
                    if not isinstance(ent, dict):
                        continue
                    used = ent.get('used_by')
                    if not isinstance(used, list):
                        used = []
                    if plugin in used:
                        used = [u for u in used if u != plugin]
                        ent['used_by'] = used
                        dirty = True
                    if not used and not ent.get('manual'):
                        # used_by 空了且非手动安装 → 删目录 + 销登记
                        try:
                            pdir = safe_join(self.root, name)
                            if pdir and os.path.isdir(pdir):
                                shutil.rmtree(pdir, ignore_errors=True)
                        except Exception:
                            pass
                        pkgs.pop(name, None)
                        removed.append(name)
                        dirty = True
                if dirty:
                    write_json(self.path, {'packages': pkgs,
                                           'updated_at': now_iso()})
            except Exception:
                pass
        return removed

    def all_entries(self):
        """全部登记（包名 → 条目 dict）；只返回 dict 项，读失败给空。"""
        try:
            with self._lock:
                pkgs = self._read()
            return {k: dict(v) for k, v in pkgs.items()
                    if isinstance(v, dict)}
        except Exception:
            return {}

    def remove(self, pkg):
        """彻底删除一个包（目录 + 登记）；返回是否删掉了目录。"""
        try:
            with self._lock:
                pkgs = self._read()
                pkgs.pop(pkg, None)
                write_json(self.path, {'packages': pkgs,
                                       'updated_at': now_iso()})
        except Exception:
            pass
        removed = False
        try:
            pdir = safe_join(self.root, pkg)
            if pdir and os.path.isdir(pdir):
                shutil.rmtree(pdir, ignore_errors=True)
                removed = True
        except Exception:
            pass
        return removed


# ---------------- 单个文件：多镜像下载 + 边下边校验 ----------------
def download_file(manifest_file, dest, on_progress=None, should_abort=None):
    """按多镜像顺序下载一个文件；sha256 边下边算，齐了才改名落盘。

    返回命中的镜像 url。sha 不匹配换下一个镜像重试，
    所有镜像都失败抛 DepError(DOWNLOAD_FAILED)。
    on_progress(done, total) 在下载循环里被调用，供上层统计百分比与车速。
    """
    rel = manifest_file['rel']
    want = manifest_file['sha256']
    part = dest + '.part'
    parent = os.path.dirname(dest)
    if parent:
        os.makedirs(parent, exist_ok=True)

    last_err = ''
    try:
        for url in manifest_file['urls']:
            h = hashlib.sha256()
            done = 0
            try:
                req = urllib.request.Request(
                    url, headers={'User-Agent': USER_AGENT})
                with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                    total = int(resp.headers.get('content-length') or 0)
                    if total <= 0:
                        total = int(manifest_file.get('size') or 0)
                    with open(part, 'wb') as f:
                        while True:
                            if (should_abort is not None
                                    and should_abort()):
                                raise AbortInstall('安装已中止')
                            chunk = resp.read(CHUNK)
                            if not chunk:
                                break
                            f.write(chunk)
                            h.update(chunk)
                            done += len(chunk)
                            if done > MAX_FILE_BYTES:
                                raise DepError(
                                    'DOWNLOAD_FAILED',
                                    '文件超过 %s 上限'
                                    % fmt_mb(MAX_FILE_BYTES))
                            if on_progress is not None:
                                try:
                                    on_progress(done, total)
                                except Exception:
                                    pass
                got = h.hexdigest()
                if got != want:
                    last_err = ('sha256 不符（实际 %s…，期望 %s…）'
                                % (got[:12], want[:12]))
                else:
                    os.replace(part, dest)
                    return url
            except AbortInstall:
                raise
            except DepError:
                raise
            except Exception as e:
                last_err = str(e) or e.__class__.__name__
            try:
                if os.path.isfile(part):
                    os.remove(part)
            except OSError:
                pass
        fname = rel.rsplit('/', 1)[-1]
        raise DepError('DOWNLOAD_FAILED',
                       '文件 %s 所有镜像都没成功: %s' % (fname, last_err))
    finally:
        try:
            if os.path.isfile(part):
                os.remove(part)
        except OSError:
            pass


# ---------------- 依赖闭包 ----------------
def _plan_closure(names, base_url, emit=None, should_abort=None):
    """递归拉全部清单 → (安装顺序, 清单 dict, 引入原因 dict)。

    安装顺序为后序（依赖排在前面）；reasons 记录“是谁把包装进来的”，
    供文案 “正在安装 requests 的依赖 urllib3…”。环依赖自动剪掉。
    任一清单失败抛 DepError。
    """
    manifests = {}
    reasons = {}
    order = []
    visiting = set()

    def visit(pkg, reason):
        if pkg in manifests:
            return
        if pkg in visiting:
            return                       # 环：谁先来谁先装，剪掉即可
        if emit is not None:
            emit({'stage': 'manifest', 'package': pkg, 'label': pkg,
                  'text': '正在拉取清单：%s（已发现 %d 个包）'
                          % (pkg, len(manifests) + 1)})
        manifest = fetch_manifest(base_url, pkg)
        manifests[pkg] = manifest
        reasons[pkg] = reason
        visiting.add(pkg)
        for dep in manifest['requires']:
            visit(dep, pkg)
        visiting.discard(pkg)
        order.append(pkg)

    for n in names:
        if should_abort is not None and should_abort():
            raise AbortInstall('安装已中止')
        visit(n, '')
    return order, manifests, reasons


def label_for(pkg, reason):
    """依赖的展示名：“requests 的依赖 urllib3” / “urllib3”。"""
    return '%s 的依赖 %s' % (reason, pkg) if reason else pkg


# ---------------- wheel 的 ABI 自检 ----------------
def _interpreter_abi_tags():
    """当前解释器认识的扩展模块 ABI 标签集合，如 {'cp311-win_amd64'}。

    CPython 上 EXTENSION_SUFFIXES 形如 ['.cp311-win_amd64.pyd', '.pyd']，
    剥掉首尾 `.` 与 `.pyd` 就是标签；裸 `.pyd`（无标签）不属于任何标签，
    任何版本都能加载，天然放行。
    """
    tags = set()
    for suf in importlib.machinery.EXTENSION_SUFFIXES:
        s = str(suf)
        if s.lower().endswith('.pyd'):
            s = s[:-4]
        s = s.lstrip('.').lower()
        if s and s != 'pyd':
            tags.add(s)
    return tags


def scan_wheel_abi(root):
    """扫已解包的 wheel，返回 (ABI 标签集合, {标签: 示例文件名})。

    只看带标签的 .pyd（``PIL/_imaging.cp311-win_amd64.pyd`` → cp311-win_amd64）；
    ``_imaging.pyd`` 这种不带标签的跳过。没有任何标签 = 纯 Python 包或没带
    扩展模块，视为适配任何版本。
    """
    tags, sample = set(), {}
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in filenames:
            if not fn.lower().endswith('.pyd'):
                continue
            stem = fn[:-4]
            if '.' not in stem:
                continue
            tag = stem.split('.', 1)[1].lower()
            if tag:
                tags.add(tag)
                sample.setdefault(tag, os.path.join(
                    os.path.relpath(dirpath, root), fn))
    return tags, sample


def check_wheel_abi(root, pkg):
    """装完 wheel 后自检：包里的扩展模块适不适配当前 Python。

    不适配就抛 DepError(LOAD_ERROR)。不检的话会出现「依赖报装好了、
    插件一加载才 ImportError」的假成功——cp311 的 pillow 装在 3.12 上
    正是如此：目录、文件全都在，``from PIL import Image`` 直接挂。
    """
    tags, _sample = scan_wheel_abi(root)
    if not tags:
        return                          # 纯 Python 包，无 ABI 顾虑
    mine = _interpreter_abi_tags()
    if tags & mine:
        return
    raise DepError(
        'LOAD_ERROR',
        '%s 不适配当前 Python %s：包里是 %s，本机需要 %s'
        % (pkg, sys.version.split()[0], '、'.join(sorted(tags)),
           '、'.join(sorted(mine)) or '（未知标签）'))


def _unpack_wheel(mf, tmp, pkg, label, emit, should_abort, index, count):
    """wheel 型清单：下载 .whl 并解包到 tmp（tmp 即 packages/<pkg>/ 的内容）。

    wheel 里的 *.dist-info 元数据用不上，跳过；其余按原始路径落盘。
    """
    whl = tmp + '.whl'
    try:
        download_file(mf, whl, None, should_abort)
        if should_abort is not None and should_abort():
            raise AbortInstall('安装已中止')
        fname = str(mf.get('rel') or '').rsplit('/', 1)[-1] or 'package.whl'
        if emit is not None:
            emit({'stage': 'extract', 'package': pkg, 'label': label,
                  'file': fname, 'pct': 100,
                  'index': index, 'count': count,
                  'text': '正在解包 %s…（%d/%d）%s'
                          % (label, index, count, fname)})
        try:
            zf = zipfile.ZipFile(whl)
        except Exception as e:
            raise DepError('DOWNLOAD_FAILED',
                           '%s 不是有效的 wheel/zip：%s' % (fname, e))
        with zf:
            for n in zf.namelist():
                if n.endswith('/'):
                    continue
                top = n.split('/', 1)[0].lower()
                if top.endswith('.dist-info'):
                    continue
                dest = safe_join(tmp, n)
                if dest is None:
                    raise DepError('DOWNLOAD_FAILED',
                                   'wheel 内含非法路径: %s' % n)
                parent = os.path.dirname(dest)
                if parent:
                    os.makedirs(parent, exist_ok=True)
                with zf.open(n) as fsrc, open(dest, 'wb') as fdst:
                    shutil.copyfileobj(fsrc, fdst)
        # 解包完立刻验一次 ABI：cp311 的包在 3.12 上装得下但用不了，
        # 必须在这里拦住，否则上层会报「依赖已就绪」，插件加载时才炸。
        check_wheel_abi(tmp, pkg)
    finally:
        try:
            if os.path.isfile(whl):
                os.remove(whl)
        except OSError:
            pass


# ---------------- 单包安装：临时目录 → 原子换入 ----------------
def _install_one(manifest, root, label, emit, should_abort, index, count):
    """全部文件下到临时目录，齐了再原子换入 packages/<pkg>/。"""
    pkg = manifest['name']
    files = manifest['files']
    total_files = len(files)
    target = os.path.join(root, pkg)

    # 同包残留的旧临时目录（上次崩在半路）先清了
    try:
        for fn in os.listdir(root):
            if fn.startswith(TMP_PREFIX + pkg):
                shutil.rmtree(os.path.join(root, fn), ignore_errors=True)
    except Exception:
        pass

    tmp = tempfile.mkdtemp(prefix=TMP_PREFIX + pkg + '-', dir=root)
    try:
        is_wheel = bool(manifest.get('wheel'))
        if is_wheel:
            _unpack_wheel(files[0], tmp, pkg, label, emit, should_abort,
                          index, count)
        for i, mf in (() if is_wheel else enumerate(files, 1)):
            if should_abort is not None and should_abort():
                raise AbortInstall('安装已中止')
            # 清单路径若自带 “<包名>/” 前缀（wheel 风格），剥掉再落盘：
            # 目标是 packages/<pkg>/ 就是包的导入根目录，不能再套一层。
            rel = str(mf['rel'])
            prefix = pkg + '/'
            if rel.startswith(prefix):
                rel = rel[len(prefix):]
            if not rel:
                continue
            mf = dict(mf)
            mf['rel'] = rel
            dest = safe_join(tmp, rel)
            if dest is None:
                raise DepError('DOWNLOAD_FAILED',
                               '清单里有非法路径: %s' % mf['rel'])
            fname = mf['rel'].rsplit('/', 1)[-1]
            file_pct = int(i * 100 / total_files)

            # 车速统计：每攒够 0.3 秒刷一次
            st = {'t0': time.monotonic(), 'd0': 0, 'speed': 0.0}

            def on_progress(done, total, st=st, i=i, fname=fname,
                            label=label, pkg=pkg, index=index,
                            count=count, file_pct=file_pct):
                now = time.monotonic()
                dt = now - st['t0']
                speed = st['speed']
                if dt >= 0.3:
                    speed = max(0.0, (done - st['d0']) / dt)
                    st['t0'] = now
                    st['d0'] = done
                    st['speed'] = speed
                pct = int(done * 100 / total) if total else -1
                if emit is not None:
                    emit({'stage': 'download', 'package': pkg,
                          'label': label, 'file': fname,
                          'pct': max(0, pct), 'done': done, 'total': total,
                          'speed': fmt_speed(speed),
                          'index': index, 'count': count,
                          'text': '正在安装 %s…（%d/%d）%s %s · %s/%s · %s'
                                  % (label, index, count, fname,
                                     ('%d%%' % pct) if total
                                     else fmt_mb(done),
                                     fmt_mb(done),
                                     fmt_mb(total) if total else '?',
                                     fmt_speed(speed))})

            download_file(mf, dest, on_progress, should_abort)
            if emit is not None:
                emit({'stage': 'verify', 'package': pkg, 'label': label,
                      'file': fname, 'pct': 100,
                      'index': index, 'count': count,
                      'text': '正在安装 %s…（%d/%d）校验通过 %s（已完成 %d%%）'
                              % (label, index, count, fname, file_pct)})

        # 全部落盘 → 换入正式目录（旧版本目录直接覆盖重装）
        last_err = ''
        moved = False
        for _attempt in range(2):
            try:
                if os.path.isdir(target):
                    shutil.rmtree(target)
                os.replace(tmp, target)
                tmp = None
                moved = True
                break
            except Exception as e:
                last_err = str(e)
                time.sleep(0.4)
        if not moved:
            raise DepError('LOAD_ERROR',
                           '%s 落盘失败（文件可能被占用）: %s'
                           % (pkg, last_err))
        # 加载前验证目录存在（换入后必须还在）
        if not os.path.isdir(target):
            raise DepError('LOAD_ERROR', '%s 安装后目录不存在' % pkg)
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------- 对外总入口 ----------------
def ensure_requirements(db, root, base_url, plugin, names,
                        emit=None, should_abort=None):
    """确保 plugin 声明的依赖全部就绪（含递归依赖闭包）。

    db        PackageDB（packages.json 登记表）
    root      packages 根目录（plugins/packages）
    base_url  依赖清单目录（空串用 DEFAULT_BASE）
    plugin    当前插件名（写进各包 used_by，也用于文案）
    names     该插件 plugin.json 声明（已规范化）的包名列表

    返回 (就绪包名列表, 错误 dict{包名: [kind] 文本})。
    错误不抛出去而是收集，方便上层归到具体插件头上。
    """
    names = normalize_requires(names, plugin)
    if not names:
        return [], {}
    try:
        os.makedirs(root, exist_ok=True)
    except Exception as e:
        return [], {plugin: '[LOAD_ERROR] 依赖目录建不出来: %s' % e}

    def base_emit(ev):
        if emit is None:
            return
        if isinstance(ev, dict):
            ev.setdefault('plugin', plugin or '')
        try:
            emit(ev)
        except Exception:
            pass

    try:
        order, manifests, reasons = _plan_closure(
            names, base_url, base_emit, should_abort)
    except AbortInstall:
        return [], {plugin: '[MISSING_DEP] 安装被中止'}
    except DepError as e:
        kind = getattr(e, 'kind', 'DOWNLOAD_FAILED')
        base_emit({'stage': 'failed', 'package': '', 'label': plugin,
                   'text': '依赖准备失败 [%s] %s' % (kind, e)})
        return [], {plugin: '[%s] %s' % (kind, e)}

    ready = []
    errors = {}
    count = len(order)
    for idx, pkg in enumerate(order, 1):
        manifest = manifests[pkg]
        version = manifest['version']
        label = label_for(pkg, reasons.get(pkg, ''))
        try:
            have = db.installed_version(pkg)
            if have == version:
                # 同版本已在：不重复 Download，只登记 used_by
                db.record_use(pkg, version, plugin,
                              files=len(manifest['files']))
                ready.append(pkg)
                base_emit({'stage': 'done', 'package': pkg, 'label': label,
                           'pct': 100, 'index': idx, 'count': count,
                           'text': '%s %s 已就位（%d/%d）'
                                   % (label, version, idx, count)})
                continue
            if have:
                base_emit({'stage': 'extract', 'package': pkg,
                           'label': label, 'index': idx, 'count': count,
                           'text': '%s 将从 %s 覆盖为 %s（%d/%d）'
                                   % (label, have, version, idx, count)})
            _install_one(manifest, root, label, base_emit,
                         should_abort, idx, count)
            db.record_use(pkg, version, plugin, files=len(manifest['files']))
            ready.append(pkg)
            base_emit({'stage': 'done', 'package': pkg, 'label': label,
                       'pct': 100, 'index': idx, 'count': count,
                       'text': '已安装 %s %s（%d/%d）'
                               % (label, version, idx, count)})
        except AbortInstall:
            errors[pkg] = '[MISSING_DEP] 安装被中止'
        except DepError as e:
            kind = getattr(e, 'kind', 'DOWNLOAD_FAILED')
            errors[pkg] = '[%s] %s' % (kind, e)
            base_emit({'stage': 'failed', 'package': pkg, 'label': label,
                       'index': idx, 'count': count,
                       'text': '依赖安装失败 %s [%s] %s' % (label, kind, e)})
        except Exception as e:
            errors[pkg] = '[DOWNLOAD_FAILED] %s' % e
            base_emit({'stage': 'failed', 'package': pkg, 'label': label,
                       'index': idx, 'count': count,
                       'text': '依赖安装失败 %s %s' % (label, e)})
        if errors:
            break          # 一个包失败，后面的多半也白搭，止损
    return ready, errors
