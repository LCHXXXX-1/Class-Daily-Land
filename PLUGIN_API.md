[Uploading PLUGIN_API.md…]()
# ClassBoard 插件 API 接口规范

> **版本：v4.0**（对应主程序 v3.0+ 的插件系统；上一版为 v3.0）
> 本文档是插件开发的**唯一权威接口规范**，逐条与 `plugin_manager.py`、`dynamic_island.py`、
> `sub_island.py`、`panel_window.py` 的真实实现核对过。读完本文档即可**不读源码**开发任意插件。
>
> 约定：`api` 指插件自己的 `PluginAPI` 实例；所有 `fn` 指插件提供的**无参数** callable。

---

## 版本与变更记录

### v4.0 相对 v3.0 的新增（本版重点）

| 变更 | 类型 | 说明 |
|---|---|---|
| **`add_island_banner(fn)`** | 🆕 新接口 | **紧急警报条**：独占主岛、隐藏副岛（融合成一条）、顶掉课程显示与上课前倒计时、全屏/PPT 也不会被隐藏；支持**两层结构**（向下拓展一排）、**点击确认**交互、~30fps 实时 ratio |
| `notify(text, is_end, force)` | ➕ 参数 | 新增 `force`：紧急预警即使灵动岛被上课/全屏隐藏，也会**强制拉回屏幕**并保持 |
| `add_island_extra` 显示状态 | ✏️ 行为变更 | 除 `compact` 外，**`countdown`（上课前蓝条倒计时）期间也会显示**——紧急信息不因"马上要上课"而消失 |
| 主岛警报条 ←→ 演练优先级 | ✏️ 行为变更 | 警报条**优先于**主程序自身的测试/情景演练（演练被拒绝或被中止） |
| 附录 D | ✏️ 更新 | priority 建议值补充（警报条 ≥100）；`add_island_banner` 的兼容性写法 |
| 第 0 / 20 / 21 章 | 🆕 新章节 | 快速开始、常见问题排查（FAQ）、调试技巧 |

### API 数量总览

| 分类 | 数量 | 方法 |
|---|---|---|
| 生命周期 | 3 | `on_load` / `on_start` / `on_stop` |
| 定时器 | 2 | `set_interval` / `set_timeout` |
| 主岛 | 3 | `add_island_text` / `add_island_extra` / **`add_island_banner`** |
| 下拉面板 | 1 | `add_panel` |
| 副岛 | 6 | `add_subisland` / `set_subisland_length` / `set_subisland_collapsed` / `collapse_subisland` / `expand_subisland` / `on_subisland_click`（+ 保留接口 `subisland_show_weather`） |
| 设置页 | 1 | `add_settings_page` |
| 配置 | 3 | `get_data_dir` / `get_config` / `set_config` |
| 课表 | 2 | `get_schedule_status` / `is_in_class` |
| 交互 | 3 | `log` / `request_refresh` / `notify` |
| **合计** | **24** | （含 1 个保留接口） |

---

## 目录

0. [快速开始（5 分钟）](#0-快速开始5-分钟)
1. [插件模型与加载机制](#1-插件模型与加载机制)
2. [目录结构与 plugin.json](#2-目录结构与-pluginjson)
3. [入口约定 register(api)](#3-入口约定-registerapi)
4. [生命周期](#4-生命周期)
5. [API 总览速查表](#5-api-总览速查表)
6. [生命周期注册](#6-生命周期注册)
7. [定时器](#7-定时器)
8. [主岛：胶囊文本 add_island_text](#8-主岛胶囊文本-add_island_text)
9. [主岛：加长片段 add_island_extra](#9-主岛加长片段-add_island_extra)
10. [主岛：紧急警报条 add_island_banner](#10-主岛紧急警报条-add_island_banner)
11. [下拉面板 add_panel](#11-下拉面板-add_panel)
12. [副岛 add_subisland 系列](#12-副岛-add_subisland-系列)
13. [设置页 add_settings_page](#13-设置页-add_settings_page)
14. [配置持久化](#14-配置持久化)
15. [课表状态](#15-课表状态)
16. [日志 / 刷新 / 通知](#16-日志--刷新--通知)
17. [spec 通用规则与性能要求](#17-spec-通用规则与性能要求)
18. [主题适配约定](#18-主题适配约定)
19. [完整示例插件](#19-完整示例插件)
20. [常见问题与排查（FAQ）](#20-常见问题与排查faq)
21. [调试技巧](#21-调试技巧)
22. [附录 A：课表状态字典字段表](#附录-a课表状态字典字段表)
23. [附录 B：主程序关键设置键](#附录-b主程序关键设置键)
24. [附录 C：内置插件参考](#附录-c内置插件参考)
25. [附录 D：已知限制与注意事项](#附录-d已知限制与注意事项)

---

## 0. 快速开始（5 分钟）

### 0.1 最小可用插件

```
plugins/my_plugin/
├── plugin.json
└── main.py
```

`plugin.json`：

```json
{
  "name": "我的插件",
  "version": "1.0.0",
  "entry": "main.py",
  "description": "一句话说明"
}
```

`main.py`：

```python
_state = {"api": None}

def island_text():
    return "你好"                      # 追加到主岛胶囊文案末尾

def register(api):
    _state["api"] = api
    api.add_island_text(island_text)
    api.log("已注册")
```

重启主程序（或把目录/`.cbplugin` 包放进插件目录后重启），主岛右下角就会出现「… · 你好」。

### 0.2 接下来看哪几节

| 想做的事 | 看 |
|---|---|
| 显示一段文字（不占额外空间） | [8. add_island_text](#8-主岛胶囊文本-add_island_text) |
| 在胶囊右侧画图标/文字（可点击、可动画） | [9. add_island_extra](#9-主岛加长片段-add_island_extra) |
| 地震/火灾这类**必须立刻打断用户**的 | [10. add_island_banner](#10-主岛紧急警报条-add_island_banner) |
| 点开主岛后展开的卡片（多行文本） | [11. add_panel](#11-下拉面板-add_panel) |
| 主岛右边那个小岛（天气/媒体） | [12. add_subisland](#12-副岛-add_subisland-系列) |
| 给插件一个设置页 | [13. add_settings_page](#13-设置页-add_settings_page) |
| 存档配置 | [14. 配置持久化](#14-配置持久化) |
| 上课时静音 / 下课时恢复 | [15. 课表状态](#15-课表状态) |

### 0.3 三条铁律（先记住，能省很多调试时间）

1. **`fn()` 必须极快**：它在 GUI 线程被调用（最频繁的 `add_island_banner` 是 ~30fps）。
   联网/读文件/大计算一律放到定时器或后台线程里，把结果缓存进模块级 dict，`fn()` 只读缓存。
2. **返回 `None` 就是"不显示"**：这是你控制显隐的唯一方式，主程序不会替你清理。
3. **不要自己造 Qt 窗口**：所有显示位都由主程序管理。插件不要 `QWidget().show()`。
   （唯一例外是设置页 `add_settings_page` 的工厂返回的 QWidget，它由设置窗口托管。）

---

## 1. 插件模型与加载机制

- 插件是 `plugins/<插件目录名>/` 下的一个**松散目录**，含 `plugin.json` + 入口 py 文件。
- 程序启动时 `PluginManager.load_all()` 按**目录名字典序**（`sorted(os.listdir)`）逐个加载。
- 加载方式：

  ```python
  spec = importlib.util.spec_from_file_location(f"plugin_{name}", entry_path)
  module = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(module)        # 执行入口文件
  module.register(PluginAPI(manager, name, plugin_dir))
  ```

- **插件目录不在 `sys.path` 上**：所以入口文件里**不能**直接 `import sources`。
  同目录模块必须按文件路径加载（内置插件的标准做法）：

  ```python
  import os, sys, importlib.util

  _PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))

  def _load_sibling(name):
      """加载同目录模块（插件目录不在 sys.path 上，不能直接 import）"""
      path = os.path.abspath(os.path.join(_PLUGIN_DIR, name + ".py"))
      mod = sys.modules.get(name)
      if mod is not None and getattr(mod, "__file__", None) \
              and os.path.abspath(mod.__file__) == path:
          return mod                      # 已从同一文件加载过 -> 复用（保证 id 稳定）
      uniq = "my_plugin_" + name          # 带插件前缀，避免和其他插件同名模块冲突
      if uniq in sys.modules:
          return sys.modules[uniq]
      spec = importlib.util.spec_from_file_location(uniq, path)
      m = importlib.util.module_from_spec(spec)
      sys.modules[uniq] = m
      spec.loader.exec_module(m)
      return m

  helpers = _load_sibling("helpers")
  ```

  > 为什么要 `uniq` 前缀：不同插件可能都有自己的 `sources.py`，
  > 用同一个模块名会互相覆盖（`sys.modules` 是全局的）。

- **无沙箱、无签名、无权限控制**：插件与主程序**同进程同权限**，可 import 任意库、联网、起子进程。
  请只安装可信来源的插件。
- 单个插件的任何异常（加载失败 / register 出错 / 运行期 spec 出错）都会被捕获并记录，
  **不影响主程序和其他插件**。
- 加载结果记录在 `PluginManager.loaded`：`[(目录名, 是否成功, 消息), ...]`，设置窗口「插件」页可见。

### 1.1 `.cbplugin` 包安装（v4.0 现状）

- `plugins/*.cbplugin` 是 **ZIP 压缩包**（扩展名只是约定），启动时自动解压安装成插件目录：
  - 包内 `plugin.json` 可在**根目录**或**唯一的一层顶层目录**里（推荐后者，如 `disaster_alert/`）；
  - 安装后写入标记文件 `.cbplugin.json`（记录包的 size/mtime），**包未变化就不重复解压**；
  - 含**防路径穿越**校验（拒绝 `../` 之类的条目）；
  - 同名目录**不会**被直接覆盖（幂等安装）。
- 设置窗口「＋ 添加插件…」的流程是：把选中的文件**复制到插件目录**，提示"重启后生效"。
  所以：**把 `.cbplugin` 放进插件目录后重启即可自动安装**。
- 卸载：删除插件目录，并**同时删除插件目录里的 `.cbplugin` 文件**，否则下次启动会重新安装。

### 1.2 加载失败的可能原因（`loaded` 中的消息）

| 消息 | 含义 | 排查方向 |
|---|---|---|
| `读元信息失败: ...` | `plugin.json` 读取/解析异常 | JSON 语法、编码（必须 UTF-8） |
| `入口不存在` | `entry` 指定的文件不存在 | `entry` 拼写、文件名大小写 |
| `加载失败: ...` | 入口文件 `exec_module` 抛异常 | **最常见的坑**：`import 同目录模块`、语法错误、第三方库缺失 |
| `无 register` | 模块没有 `register` 函数 | 必须定义模块级 `def register(api)` |
| `register 出错: ...` | `register(api)` 调用抛异常 | `register` 里不能做耗时/可能失败的事（挪到 `on_load`） |
| `register 出错: ...`（continued） | | 调用了当前宿主不支持的 api 方法 → 用 `hasattr` 探测 |

---

## 2. 目录结构与 plugin.json

```
plugins/my_plugin/
├── plugin.json     # 必需，元信息
├── main.py         # 入口（默认），必须实现 register(api)
├── helpers.py      # （可选）同目录模块，需按路径加载，见 §1
├── data.json       # （可选）由 api.set_config 自动生成/维护
├── config.json     # （可选）插件自管的配置（内置插件惯例）
├── cache.json      # （可选）缓存（如断网时用的上次数据）
└── ...             # 其他资源文件随意（图片、脚本、数据表）
```

`plugin.json` 字段：

| 字段 | 类型 | 必需 | 默认 | 说明 |
|---|---|---|---|---|
| `name` | str | 建议 | — | 显示名。**当前主程序不消费**，仅文档/自用意义 |
| `version` | str | 建议 | — | 版本号。同上 |
| `entry` | str | 否 | `"main.py"` | 入口文件名（相对插件目录）。**唯一被主程序消费的字段** |
| `description` | str | 建议 | — | 描述。同上 |

> 注：`clock` 插件还带了 `display_name / author_id / author_name` 等扩展字段，
> 主程序**不消费**，你可以自由扩展（方便自己或第三方工具读取）。

**打包建议**：把插件目录整体压成 ZIP 并把扩展名改成 `.cbplugin`，让 `plugin.json` 位于
ZIP 内的**一层目录**下（例：`disaster_alert/plugin.json`）。
**打包时不要把 `config.json` / `cache.json` / `__pycache__` 打进去**，
否则用户安装后会被别人的配置覆盖。

---

## 3. 入口约定 register(api)

入口文件必须定义模块级函数 `register(api)`，主程序加载时调用**一次**：

```python
def register(api):
    api.on_start(lambda: api.log("started"))
```

- `api` 是该插件**专属**的 `PluginAPI` 实例（已绑定插件名与插件目录）。
- `register` 内应只做**注册**，不要做耗时操作（会阻塞程序启动）。
  耗时初始化放到 `on_load` / `on_start` 回调里。
- 插件内部状态推荐用**模块级 dict** 保存（内置插件统一用 `_state` 模式）：

  ```python
  _state = {
      "api": None,
      "config": {},
      "data": None,      # 后台线程写、spec 只读
  }
  ```

### 3.1 推荐骨架（可直接复制）

```python
"""我的插件：一句话说明。"""
import os

from PySide6.QtWidgets import QWidget, QFormLayout, QCheckBox

_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))

_DEFAULTS = {"enabled": True}

_state = {"api": None, "config": dict(_DEFAULTS)}


# ---------------- 显示位 ----------------
def island_text():
    if not _state["config"].get("enabled"):
        return None                       # None = 不显示
    return "示例"


# ---------------- 设置页 ----------------
def build_settings(api):
    w = QWidget()
    form = QFormLayout(w)
    cb = QCheckBox("启用")
    cb.setChecked(bool(_state["config"]["enabled"]))

    def save(*_):
        _state["config"]["enabled"] = bool(cb.isChecked())
        api.set_config(_state["config"])   # 落盘 + 自动刷新
        api.request_refresh()

    cb.toggled.connect(save)
    form.addRow("", cb)
    return w


# ---------------- 生命周期 ----------------
def on_load():
    _state["config"] = {**_DEFAULTS, **(_state["api"].get_config() or {})}


def on_stop():
    pass


# ---------------- 入口 ----------------
def register(api):
    _state["api"] = api

    api.add_island_text(island_text)
    api.add_settings_page("我的插件", build_settings, icon="🧩")

    api.on_load(on_load)
    api.on_stop(on_stop)
    api.set_interval(1, lambda: api.request_refresh())

    api.log("已注册")
```

---

## 4. 生命周期

`load_all()` 的**严格顺序**：

```
阶段 1（逐个插件，目录名字典序）:
    读 plugin.json → 动态加载入口文件 → 调用 register(api)        # 只注册钩子
阶段 2（全部插件 register 完成后）:
    依次调用每个插件的 on_load 回调
阶段 3（全部 on_load 完成后）:
    依次调用每个插件的 on_start 回调
```

退出时（托盘退出 / 主窗口退出）调用 `stop_all()`：

```
1) 停止所有由 api.set_interval / api.set_timeout 创建的 QTimer
2) 按注册顺序调用每个插件的 on_stop 回调
```

| 回调 | 时机 | 典型用途 | 不要做什么 |
|---|---|---|---|
| `on_load(fn)` | 全部插件 register 完成后 | 读配置、恢复缓存、预热内存数据 | 不要依赖其他插件的状态 |
| `on_start(fn)` | `on_load` 之后 | 首次刷新、发起首个网络请求、注册首个 spec 数据 | 不要阻塞（同步网络请求会卡界面） |
| `on_stop(fn)` | 程序退出前 | 杀子进程、关闭会话、落盘未保存状态 | 不要弹窗、不要等待超过 1 秒 |

**多回调**：同一个阶段的回调按**注册顺序**依次调用；任一回调抛异常都会被捕获记录，
**不会中断**同阶段的其他回调。

```python
def register(api):
    api.on_load(load_cache)
    api.on_start(first_refresh)
    api.on_stop(cleanup)
```

---

## 5. API 总览速查表

| 分类 | 方法 | 返回值 | 调用频率 | 一句话 |
|---|---|---|---|---|
| 生命周期 | `on_load(fn)` / `on_start(fn)` / `on_stop(fn)` | — | 各 1 次 | 注册生命周期回调 |
| 定时器 | `set_interval(seconds, fn, start=True)` | `QTimer` | 自定（最小 1s） | 周期定时器 |
| 定时器 | `set_timeout(seconds, fn)` | `QTimer` | 1 次 | 单次定时器 |
| 主岛 | `add_island_text(fn)` | — | 1 次/秒 | 胶囊文案追加一段文字 |
| 主岛 | `add_island_extra(fn)` | — | spec 1 次/秒；draw ~60fps | 胶囊右侧加长自绘片段 |
| 主岛 | **`add_island_banner(fn)`** | — | spec **~30fps** | **紧急警报条**（独占+融合副岛+顶掉课程） |
| 面板 | `add_panel(fn)` | — | 下拉瞬间 1 次 | 下拉面板卡片（纯文本） |
| 副岛 | `add_subisland(fn)` | — | 刷新时；draw ~60fps | 副岛内容 |
| 副岛 | `set_subisland_length(px)` | — | 需要时 | 全局副岛默认长度 |
| 副岛 | `set_subisland_collapsed(b)` | — | 需要时 | 收起/展开副岛 |
| 副岛 | `collapse_subisland()` / `expand_subisland()` | — | 需要时 | 上者的便捷封装 |
| 副岛 | `on_subisland_click(fn)` | — | 每次点击 | 副岛点击回调 |
| 副岛 | `subisland_show_weather(b)` | — | — | ⚠ 保留接口，**当前无效果** |
| 设置 | `add_settings_page(title, factory, icon)` | — | 每次打开设置窗口 | 加一页设置 |
| 配置 | `get_data_dir()` | str | 需要时 | 插件数据目录（绝对路径） |
| 配置 | `get_config(default=None)` | dict/any | 需要时 | 读 `data.json` |
| 配置 | `set_config(data)` | — | 需要时 | 原子写 `data.json` 并自动刷新 |
| 课表 | `get_schedule_status()` | dict/None | 需要时（建议 1 次/秒） | 当前课程状态 |
| 课表 | `is_in_class()` | bool | 同上 | 是否上课中 |
| 交互 | `log(*args)` | — | 需要时 | 打印 `[Plugin:名] ...` |
| 交互 | `request_refresh()` | — | 数据变化后 | 请求立即刷新各显示位 |
| 交互 | `notify(text, is_end=False, force=False)` | — | 少量 | 主岛弹出提醒条 |

> **频率栏是本表最该注意的一列**：`fn()` 被调用的频率决定了它的性能预算。
> 30fps 的 `add_island_banner` 意味着单次耗时必须控制在**微秒级**。

---

## 6. 生命周期注册

### `api.on_load(fn)`

| 项 | 说明 |
|---|---|
| 参数 | `fn`：无参数 callable |
| 返回值 | 无 |
| 调用时机 | 全部插件 `register` 完成后，仅 1 次 |
| 可注册个数 | 多个（按注册顺序调用） |
| 异常 | 被捕获并 `api.log` 记录，不中断其他回调 |

### `api.on_start(fn)`

同上；`on_load` 全部执行完之后调用。适合"首次拉数据"。

### `api.on_stop(fn)`

同上；程序退出前调用。**这是你唯一可靠的清理时机**——
定时器已由主程序停止，但你的子进程/线程/临时文件需要自己处理。

```python
def register(api):
    api.on_load(load_cache)        # 读缓存
    api.on_start(first_refresh)    # 首次刷新
    api.on_stop(cleanup)           # 收尾
```

---

## 7. 定时器

### `api.set_interval(seconds, fn, start=True) -> QTimer`

| 项 | 说明 |
|---|---|
| 参数 `seconds` | 秒（float/int）。**实际间隔 = `max(1, int(seconds*1000))` ms，即最小 1 秒** |
| 参数 `fn` | 无参数 callable，每次触发调用 |
| 参数 `start` | 默认 `True`（立即开始计时）；`False` 则返回未启动的 timer |
| 返回值 | `QTimer`，你可以自行 `stop()/start()/setInterval()` |
| 生命周期 | **退出时由主程序统一停止**，不需要（也不应该）`deleteLater()` |
| 异常 | 未单独捕获——`fn` 里请自己 try/except，否则会打断本次刷新 |

典型间隔建议：

| 用途 | 间隔 |
|---|---|
| 秒级 UI 刷新（时钟、倒计时展示） | 1 秒 |
| 状态轮询（媒体、天气） | 1–5 秒 |
| 网络轮询（预警、更新检查） | 5–60 秒（别太密，尊重数据源） |
| 高频动画 | ⚠ 不要用定时器做动画，见下 |

### `api.set_timeout(seconds, fn) -> QTimer`

单次触发（`singleShot`）。常用于"失败后 3 秒重试""5 秒后收起提示"。

```python
def register(api):
    api.set_interval(1, tick)              # 每秒
    api.set_timeout(5, delayed_init)       # 5 秒后一次
    timer = api.set_interval(2, poll, start=False)   # 需要时再 start()
```

### 7.1 动画不要自己开定时器

主程序已经为需要动画的显示位维护了帧循环：

| 显示位 | 帧率 | 你怎么做动画 |
|---|---|---|
| `add_island_extra` 的 `draw` | ~60fps（有 draw 时自动开启） | 用 `t`（`time.monotonic()` 秒）算相位 |
| `add_island_banner` 的 spec | ~30fps（仅一层时）/ 250fps 级降频（只显示静态第二层时 ~4fps） | 在 `fn()` 里**实时计算** `ratio` 等 |
| `add_subisland` 的 `draw` | ~60fps | 同 extra |

用 `t` 驱动动画是**唯一正确**的做法；用 `set_interval` 每 16ms 重算一次数据属于浪费。

---

## 8. 主岛：胶囊文本 `add_island_text`

### `api.add_island_text(fn)`

- `fn() -> str | None`
  - 返回要**追加到主岛胶囊文案末尾**的文字；
  - 返回 `None` 或空串 → 不追加（不是"隐藏主岛"）。

**最终文案拼接规则**：

```
{课表状态文案} · {插件文本1}　{插件文本2}　...
```

- 多个插件的文本用**全角空格 `　`** 拼接；
- 课表文案与插件文本之间是 ` · `。

| 项 | 说明 |
|---|---|
| 调用时机 | 主岛每秒刷新时同步调用（隐藏状态下不调用） |
| 频率 | 1 次/秒 |
| 性能要求 | **纯函数、极快**（微秒级）；不得联网、读大文件、做计算 |
| 超长处理 | 文案超出可用宽度时，主岛自动**跑马灯滚动**（约 32px/s，每轮回起点先停 0.9 秒） |
| 变化动画 | 文案变化时自动播放"顶掉"滚动（受设置"文字变化时渐显"控制） |

```python
def island_text():
    n = len(_state["todos"])
    return f"{n} 条待办" if n else None

def register(api):
    api.add_island_text(island_text)
```

> 如果只是想让主岛多显示"一点点"信息，用这个；
> 想画图标/要点击/要独立配色，用下一节的 `add_island_extra`。

---

## 9. 主岛：加长片段 `add_island_extra`

### `api.add_island_extra(fn)`

在主岛胶囊**右侧加长一段**完全由插件自绘的区域
（分割线左侧是课表内容，右侧是你的片段）。同一时刻**只有一个插件**能占用它。

`fn() -> dict | None`，spec 字段：

| 字段 | 类型 | 必需 | 默认 | 说明 |
|---|---|---|---|---|
| `width` | int | 否 | 160 | 片段宽度 px，**钳制 [0, 400]** |
| `draw` | callable | **是** | — | `draw(painter, rect, t)` 自绘函数；**缺了它整个 spec 被丢弃** |
| `on_click` | callable | 否 | — | 点击该片段时调用（无参数） |
| `priority` | int | 否 | 0 | 多插件竞争时**数值最大者独占** |

### 行为细节

1. **仲裁**：所有插件的 spec 取 `priority` 最大者；**平级时先注册者胜**（用 `>` 比较）。
2. **调用时机**：主岛每秒重新取一次 spec；`draw` 存在时该区域以 **~60fps** 重绘。
3. **显示状态（v4.0 起）**：主岛 `compact`（常规胶囊）**与 `countdown`（上课前蓝条倒计时）**
   状态**都显示**；`alert`（提醒条）/ 隐藏 / 下拉面板展开 / 测试演示期间**不显示、不取 spec**。
   主岛隐藏时不重绘（省电）。
   > v3.0 只在 `compact` 显示；改成"蓝条期间也显示"是为了让紧急信息不因"马上要上课"而消失。
4. **绘制**：`rect` 是片段在主岛上的矩形（高 = 胶囊高 40px）。
   左侧已由主程序画好 **1px 半透明分割线**。文字建议白色、背景透明。
5. **点击**：命中区域 = 整个片段 `rect`。点击触发 `on_click()`（异常被捕获）。
6. **宽度变化**：`width` 改变时主岛自动播放宽度动画；
   **下拉面板展开期间不会重排**（不会打断下拉）。
7. **跑马灯**：`draw` 里如果绘制长文本，请自己用 `t` 实现滚动——
   主程序只对**胶囊文案**做跑马灯，不会帮你滚动片段内容。
   （参考 `disaster_alert/draw.py` 的 `_draw_marquee`：超宽时首尾相接循环）
8. 返回 `None` 表示当前不显示（如 audio 插件在无媒体/上课中返回 None）。

```python
def extra_spec():
    if not has_content():
        return None
    return {"width": 200, "draw": my_draw, "on_click": my_click,
            "priority": 10}

def my_draw(painter, rect, t):
    # rect: QRect，片段区域；t: float 秒（单调递增）
    painter.setPen(QColor('white'))
    painter.drawText(rect, Qt.AlignCenter, "hello")
```

**宽度怎么给**：给"内容自然宽度"而不是固定值，视觉最自然——
用 `QFontMetricsF(font).horizontalAdvance(text)` 量出文字宽 + 内边距，再 clamp。
参考 `disaster_alert/main.py` 的 `_extra_width()`。

> 参考实现：`plugins/audio/main.py` 的 `_extra_spec` / `_draw_media`
> （priority 10，播放/暂停切换）；`plugins/disaster_alert/`（宽度自适应 + 跑马灯）。
>
> **紧急事件（地震等）请改用第 10 章的 `add_island_banner`**：它会顶掉课程显示、
> 隐藏副岛并把主岛变成一条独占的长条。

---

## 10. 主岛：紧急警报条 `add_island_banner`

> 🆕 v4.0 新增。这是**最强的一档显示位**，为"争分夺秒、必须打断用户"的事件设计。

### `api.add_island_banner(fn)`

返回非 `None` 期间，主岛会变成一条**独占的长条**：

| 能力 | 说明 |
|---|---|
| **顶掉课程一切显示** | 课程文本、上课前蓝条倒计时、提醒条（alert）全部让位 |
| **副岛自动隐藏（融合）** | 主岛与副岛在视觉上合成一条，不再并排两个窗口 |
| **不会被隐藏** | 上课 / PPT 全屏 / WPS-Office 前台导致灵动岛被收起时，**自动拉回屏幕顶部并保持** |
| **优先于宿主演练** | 警报条期间 `start_test_countdown()`/`start_scenario_test()` 返回 `False`；进行中的演练会被中止 |
| **点击交互** | 无第二层时命中 `on_click()`；有第二层（`extra`）时按"先点岛 → 再点确认"两步，最终命中 `on_confirm()` |

### 10.1 spec 字段全表

| 字段 | 类型 | 必需 | 默认 | 说明 |
|---|---|---|---|---|
| `text` | str | **是** | — | 长条文字；空字符串视为不显示 |
| `ratio` | float | 否 | 1.0 | 0~1，底部进度填充比例（倒计时 = 剩余/总时长） |
| `color` | str | 否 | `#ff453a` | 进度条颜色，`#RRGGBB` |
| `min_width` | int | 否 | — | 最小宽度 px；实际宽度 = 文本自适应宽，**钳制 [420, 700]** |
| `extra` | dict | 否 | — | **第二层**：`{"text": "避险要诀…"}`；有它才会展开两层 |
| `extra_text` | str | 否 | — | 等价于 `extra={"text": ...}`（简写） |
| `extra_hold_sec` | float | 否 | 60 | 第一层保持秒数；到点后第一层消失、窗口回收到单层，只留第二层（最小 3） |
| `require_confirm` | bool | 否 | True | 第二层是否"点两次"才收起 |
| `confirm_timeout_sec` | float | 否 | 5 | 待确认状态多少秒没操作就退回"只显示第二层"；**0 = 不超时** |
| `on_click` | callable | 否 | — | **无第二层时**点击调用 |
| `on_confirm` | callable | 否 | — | **有第二层时**用户确认后调用（宿主随后自动退出警报条） |
| `priority` | int | 否 | 0 | 多插件竞争时数值最大者独占（**建议紧急事件 ≥100**） |

### 10.2 尺寸与视觉

| 项 | 值 |
|---|---|
| 单层高度 | 40px（与常规胶囊一致） |
| 两层高度 | 40 + **32** = 72px（第二层左端画一个红色圆形「!」徽标，层间有 1px 分隔线） |
| 圆角 | 单层 = 高/2（胶囊）；两层 = **20px**（避免过度圆润） |
| 宽度 | 取**两行文字的较大**自适应宽（15px 加粗用于第一层，13px 加粗用于第二层）+ 内边距，再 `max(min_width)`，最终 clamp **[420, 700]** |
| 文本溢出 | 任一行放不下时，**该行自动跑马灯滚动** |
| 淡入 | 进入时 140ms 透明度淡入 |

### 10.3 两层结构与阶段机

```
进入 ──► [dual] 两层（倒计时条 + 第二层）   持续 extra_hold_sec 秒
            │  到点 → 第一层消失（窗口动画回收到 40px）
            ▼
        [extra] 只显示第二层，仍顶掉课程显示
            │  用户点击
            ▼
        [confirm] 第二层整条高亮，文案变为「点击确认，恢复上课显示」
            │  用户再点一次 → on_confirm() 被调用 → 宿主退出警报条、恢复课程
            │  或  confirm_timeout_sec 秒没动作 → 自动退回 [extra]（防误触）
            ▼
        退出（fn() 返回 None 时也会退出）
```

- **两层阶段点击不响应**（事件尚未过去，避免误触）。
- `require_confirm=False` 时，第二层**一次点击即收起**（走 `on_confirm`）。
- **无第二层**（只给 `text`）时，点击走 `on_click`，其余交互不存在。
- 重绘频率按阶段自动调整：`dual` **33ms(~30fps)** / `confirm` **60ms** /
  `extra` **250ms(~4fps，静态要诀省电)**。

### 10.4 `fn()` 的超高频约束（本接口最特殊的一点）

主程序在警报条激活期间**以 ~30fps 反复调用 `fn()`**。因此：

- **好处**：`ratio` 可以（也**应当**）**实时计算**，进度条会平滑收缩而不是每秒跳一格：

  ```python
  remain = arrive_ts - time.time()          # 用到达时刻现算
  ratio = max(0.0, min(1.0, remain / total))
  ```

- **要求**：`fn()` 必须**极快**——只读内存、不发网络请求、不做重活、不写文件。
  所有网络/计算都放在 `set_interval` 的 tick 里，把结果存进模块级 dict。

### 10.5 必须自己限制占用时长（重要）

警报条会顶掉课程等常驻内容，**不要让它无限期占屏**。
宿主**不会**替你自动释放——必须由 `fn()` 自己返回 `None`
（否则宿主下一帧取到 spec 又会重新进入警报条，形成"永远占屏"）。

推荐分档策略（`disaster_alert` 的做法）：

| 严重程度 | 策略 |
|---|---|
| **严重事件**（达到你的阈值） | 保留到用户确认（配 `extra` + `on_confirm` + `confirm_timeout_sec`） |
| **一般事件** | 只占用几秒（例：5 秒）后 `fn()` 返回 `None`，信息转由 `add_island_extra` 继续展示 |

```python
def banner_spec():
    focus = current_event()
    if not focus:
        return None
    key = (focus["uid"], focus["revision"])
    if _state["since_key"] != key:            # 同一事件不重置计时
        _state["since_key"] = key
        _state["since"] = time.monotonic()
    if not is_severe(focus):
        if time.monotonic() - _state["since"] >= 5:
            return None                        # 一般事件：5 秒后交还课程显示
    ...
```

### 10.6 与 `add_island_extra` 的分工

两者**可以同时注册**，由你决定何时让警报条接管：

```python
def register(api):
    if hasattr(api, "add_island_banner"):     # 兼容性探测，见下
        api.add_island_banner(banner_spec)
    api.add_island_extra(extra_spec)          # 让位逻辑见下
    api.add_subisland(sub_spec)
```

⚠ **关键坑**：如果你在 `extra_spec()` 里用"配置判断"来决定让位（例如"有地震就返回 None"），
那么当警报条因为**占用到期 / 用户确认 / 被关掉**而不再显示时，
片段还在让位 → **屏幕上什么都没有**。正确做法是**以"警报条当前是否真的有内容"为准**：

```python
def _banner_taking_over():
    return banner_spec() is not None          # 而不是"看配置"

def extra_spec():
    if _banner_taking_over():
        return None
    ...
```

（`banner_spec()` 内部不要再调用 `_banner_taking_over()`，避免递归。）

### 10.7 兼容性

旧版主程序没有这个方法。请**先探测再注册**：

```python
if hasattr(api, "add_island_banner"):
    api.add_island_banner(banner_spec)        # 有则用融合警报条
api.add_island_extra(extra_spec)              # 无论如何都注册片段作为回退
api.add_subisland(sub_spec)
```

### 10.8 完整示例

```python
def register(api):
    if hasattr(api, "add_island_banner"):
        api.add_island_banner(banner_spec)

def banner_spec() -> dict | None:
    ev = current_quake()
    if not ev or already_confirmed(ev):       # 用户点过"确认"就不再来打扰
        return None
    total = ev["countdown_sec"]
    remain = max(0.0, ev["arrive_ts"] - time.time())
    spec = {
        "text": f"{ev['place']} · M{ev['mag']:.1f} · 预估烈度{ev['inten']:.1f} · "
                f"横波还有 {int(remain)} 秒 · 距震中 {ev['dist']:.0f}km",
        "ratio": remain / total if total else 0.0,   # 实时算 → 红条平滑收缩
        "color": "#ff453a",
        "min_width": 460,
        "priority": 100,
    }
    if ev["inten"] > 5:                       # 大震：向下多展开一排避险要诀
        spec.update({
            "extra": {"text": "伏地 · 遮挡 · 手抓牢 ｜ 勿乘电梯、勿跳楼"},
            "extra_hold_sec": 60,             # 60 秒后第一层消失，只留要诀
            "require_confirm": True,          # 点岛 → 再点确认，才恢复上课显示
            "confirm_timeout_sec": 5,         # 只点一次不管它，5 秒后退回要诀
            "on_confirm": lambda: mark_confirmed(ev),
        })
    else:                                     # 小震：只闪一下，走 on_click
        spec["on_click"] = replay_alert
    return spec
```

> 参考实现：`plugins/disaster_alert/main.py` 的 `banner_spec()` / `_safety_tips()` /
> `_on_banner_confirm()` / `_banner_taking_over()`——含大震/小震分档、避险要诀、
> 确认后不再弹、事件升报重新弹出等完整逻辑。

---

## 11. 下拉面板 `add_panel`

### `api.add_panel(fn)`

点击主岛胶囊时下拉展开一排面板卡片，插件可注册自己的卡片。

`fn() -> dict | None`，spec 字段：

| 字段 | 类型 | 必需 | 默认 | 说明 |
|---|---|---|---|---|
| `text` | str | **是** | — | 面板正文（支持 `\n` 多行，超出宽度自动换行）；**空则整个 spec 被丢弃** |
| `width` | int | 否 | 180 | 期望宽度，最终钳制 `[min_width, 320]` |
| `min_width` | int | 否 | 120 | 超宽收缩时的下限 |
| `height` | int | 否 | — | 面板高度 px。**建议按内容行数算**：`20 + 行数*22 + 14`（缺省可能显示不全） |
| `order` | int | 否 | 100 | 同一列内排序，**升序**（小的靠左） |
| `position` | str | 否 | `"left"` | `"left"` 或 `"right"`：放在课表面板左侧列还是右侧列 |

### 布局与行为

1. 下拉布局：`[left 列（按 order 升序）] [课表面板] [right 列（按 order 升序）]`，面板间距 **4px**。
2. **课表面板**固定居中，宽 240（收缩下限 180）。
   总宽超过 **屏幕宽 80%** 时：先缩课表面板，再按比例缩其他面板（不低于各自 `min_width`）。
3. 面板**逐个错峰展开**（间隔 70ms，从高度 0 展开 + 轻微上浮 + 可选淡入），
   展开后**停留 3 秒自动收回**；期间滚轮可滚动
   （总高超过屏幕 1/3 时出现底部渐变遮罩）。
4. **spec 在下拉瞬间收集一次**，展开期间不再刷新；想更新内容等下次下拉。
5. 面板固定为**深色卡片**（`#1c1c1e` 底、13px `#e6e6e6` 文字、内边距 12px），
   不可自绘、不可换色，**只能提供纯文本**。
6. 展开/收起动画时长跟随设置「动画时长」（`anim_duration`，钳制 100–500ms）。

```python
def panel_spec():
    return {
        "text": f"距高考 {days} 天\n{h:02d}:{m:02d}:{s:02d}",
        "width": 190,
        "height": 20 + 2 * 22 + 14,      # 两行
        "order": 90,
        "position": "right",
    }

def register(api):
    api.add_panel(panel_spec)
    api.set_interval(1, api.request_refresh)   # 文案在下一次下拉时更新
```

> 参考实现：`plugins/clock/main.py`（实时时钟）、
> `plugins/gaokao_countdown/main.py`（多行 + 设置页）、
> `plugins/disaster_alert/main.py` 的 `_panel_lines()`（行数动态、含状态诊断）。

---

## 12. 副岛 `add_subisland` 系列

副岛是主岛右侧的小岛（**高 40px，宽 44–380px**，可收成 40px 圆形）。
**同一时刻只显示一个插件的内容**。

### `api.add_subisland(fn)`

`fn() -> dict | None`，spec 字段：

| 字段 | 类型 | 必需 | 默认 | 说明 |
|---|---|---|---|---|
| `text` | str | 条件 | — | 文本内容（与 `draw` **至少其一**，否则 spec 被丢弃） |
| `icon` | str | 否 | — | 文本模式的前置 emoji；收起为圆形时显示它 |
| `length` | int | 否 | 见下 | 展开宽度 px，**钳制 [44, 380]**；未提供时用全局值（`set_subisland_length`），再没有则 158 |
| `draw` | callable | 条件 | — | `draw(painter, rect, t)` 完全自绘（**优先于** text/icon） |
| `auto_collapse` | bool | 否 | False | True = 空闲 N 秒后自动收成圆形（N = 设置项 `sub_island_auto_collapse_sec`，默认 5，0=不收） |
| `priority` | int | 否 | 0 | 多插件竞争，**数值最大者独占副岛** |

### 行为细节

1. **仲裁**：同 `add_island_extra`，priority 最大者胜
   （内置约定：天气 = 0 占位，媒体 = 10 顶替）。
2. **刷新**：`request_refresh()` 后重新取 spec；`draw` 模式下以 ~60fps 调用 `draw`。
3. **自绘约定**：收起为圆形时 `draw` **仍会被调用**，
   `rect.width() <= 46` 时应只画一个图标。
4. **文本模式**：展开时 `icon + text`；收起时只显示 `icon`（无 icon 则显示 text 首字符）。
5. **自动展开**：副岛当前处于**收起状态**时，如果**新内容接管**
   （spec 身份变化，如天气→媒体）且该内容 `auto_collapse=False`，副岛会**自动展开**；
   同一内容持续刷新**不会**干扰用户手动收起。
   > 身份判定用的是 `(id(draw), text, auto_collapse)`：
   > 所以 `draw` 必须是**模块级稳定函数**，不要每次 `fn()` 都 `lambda` 新建，
   > 否则 `id()` 每次都变，会被误判成"新内容"而反复自动展开。
6. **点击**：左键 = 先触发所有 `on_subisland_click` 回调，再**切换收起/展开**。
   右键菜单可关闭副岛。
7. **显示时机**：仅主岛处于 `compact` / `countdown` / `alert` 时显示；
   位置自动跟随主岛右缘 +8px。**警报条激活时副岛隐藏**（融合成一条）。

### 其他副岛控制

| 方法 | 参数 | 说明 |
|---|---|---|
| `set_subisland_length(px)` | int | 设置**全局**副岛长度：之后所有未提供 `length` 的 spec 都用它（自动触发刷新） |
| `set_subisland_collapsed(b)` | bool | 收起/展开副岛（等同用户点击） |
| `collapse_subisland()` | — | `set_subisland_collapsed(True)` 的封装 |
| `expand_subisland()` | — | `set_subisland_collapsed(False)` 的封装 |
| `on_subisland_click(fn)` | callable | 注册副岛左键点击回调（**在折叠切换之前**触发） |
| `subisland_show_weather(enabled)` | bool | ⚠ **保留接口**：主程序未消费该开关，调用**无实际效果**，勿依赖 |

```python
def sub_spec():
    if not data:
        return None
    return {"length": 158, "draw": draw_weather,
            "auto_collapse": True, "priority": 0}

def register(api):
    api.add_subisland(sub_spec)
```

> 参考实现：`plugins/weather/main.py`（自绘动画图标 + auto_collapse）、
> `plugins/audio/main.py`（priority 10 + `auto_collapse: False` 保持展开 +
> 上课自动隐藏）、`plugins/disaster_alert/main.py`（有预警时占用、无预警让位）。

---

## 13. 设置页 `add_settings_page`

### `api.add_settings_page(title, factory, icon="🧩")`

在设置窗口左侧导航追加一页（排在"主窗口 / 灵动岛 / 动画 / 插件 / 关于"之后）。

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `title` | str | — | 导航显示名 |
| `factory` | callable | — | `factory(api) -> QWidget`：**设置窗口每次打开时**调用一次，返回页面内容控件 |
| `icon` | str | `"🧩"` | 导航 emoji 图标 |

行为与约定：

1. 工厂收到的 `api` 就是插件自己的 api（可以直接在里面调 `set_config`）。
2. 页面放进**可滚动区域**，用 `QVBoxLayout` / `QFormLayout` / `QHBoxLayout` 即可。
3. 控件改动建议**即时保存**到插件配置并 `api.request_refresh()`（内置插件都是即时保存）。
4. 工厂抛异常时该页显示"插件设置加载失败"占位，**不影响其他页**。
5. **主题约定（重要）**：设置窗口统一应用浅色/深色主题，
   插件页**不要自设颜色类 QSS**（背景色/文字色），交给宿主；
   提示文字用 `label.setObjectName("hint")` 自动获得主题提示色。详见 [18. 主题适配约定](#18-主题适配约定)。

**可用的控件**（PySide6 标准件都能用，主题已覆盖）：`QCheckBox`、`QComboBox`、
`QSpinBox`/`QDoubleSpinBox`、`QLineEdit`、`QPushButton`、`QSlider`、`QListWidget`、
`QFormLayout` 自动生成的 label 也会跟随主题。

```python
def build_settings(api):
    w = QWidget()
    root = QVBoxLayout(w)
    form = QFormLayout()
    interval = QSpinBox()
    interval.setRange(1, 60)
    interval.setSuffix(" 秒")
    interval.setValue(int(_state["config"]["interval"]))
    interval.valueChanged.connect(lambda v: _save(api, "interval", int(v)))
    form.addRow("刷新间隔", interval)
    root.addLayout(form)
    hint = QLabel("提示文字会自动使用主题的提示色")
    hint.setObjectName("hint")            # ← 关键
    hint.setWordWrap(True)
    root.addWidget(hint)
    root.addStretch()
    return w

def register(api):
    api.add_settings_page("我的插件", build_settings, icon="🧩")
```

> 参考实现：`plugins/disaster_alert/main.py` 的 `build_settings()`（约 400 行，含三级联动下拉、
> 颜色选择器、实时预览、状态刷新定时器）——是"复杂设置页"的完整范例。

---

## 14. 配置持久化

两种方案，**二选一**即可：

| 方案 | 文件 | 谁维护 | 适合 |
|---|---|---|---|
| `get_config` / `set_config` | `<插件目录>/data.json` | 主程序（原子写 + 自动刷新） | 轻量插件、配置项少 |
| 自管 JSON | 例：`<插件目录>/config.json` | 插件自己 | 需要默认值合并/迁移、复杂配置 |

### `api.get_data_dir() -> str`

返回插件目录的**绝对路径**（不存在会自动创建）。
可自行在里面写文件（如 audio 插件在此写 PowerShell 脚本、disaster_alert 写城市数据缓存）。

### `api.get_config(default=None)`

- 读插件目录下 `data.json`；
- 文件不存在 / 解析失败 → 返回 `default`；
- 返回的是普通 dict/list，可直接改（改完记得 `set_config` 落盘）。

### `api.set_config(data)`

- 把 `data`（必须可 JSON 序列化）**原子写入** `data.json`：
  先写临时文件再 `os.replace`，**崩溃/断电不会损坏**；
- 写完后**自动 `request_refresh()`**（所以不必再手动调一次）。

```python
def register(api):
    cfg = {**{"enabled": True, "interval": 5}, **(api.get_config() or {})}
    api.set_config(cfg)          # 首次运行补全默认并落盘

    def tick():
        cfg["count"] += 1
        api.set_config(cfg)      # 自动刷新
```

**自管配置的惯例**（内置插件做法）：

```python
_DEFAULTS = {"enabled": True, "interval": 5}

def _load_config():
    cfg = dict(_DEFAULTS)
    saved = read_json_or({}, _CONFIG_PATH)
    for k, v in saved.items():
        if k in cfg:                 # 只接受已知键 -> 天然支持旧配置升级
            cfg[k] = v
    return cfg
```

> **旧配置升级技巧**：`if k in cfg` 这一层过滤，使得**新增配置项会自动补默认值**，
> 用户不需要重新保存一遍设置。反过来说，**删掉的配置项会被自动忽略**。

---

## 15. 课表状态

### `api.get_schedule_status() -> dict | None`

返回当前课程状态字典（字段见 [附录 A](#附录-a课表状态字典字段表)），
**已包含主程序生效的「提前提醒」与「时间偏移」**。provider 异常时返回 `None`。

- 调用开销很小（读缓存），但建议**每秒最多一次**（放在 `set_interval(1, ...)` 里）。
- `status` 字段决定存在哪些附加字段，取值：`ongoing` / `upcoming` / `holiday` / `none` / `done`。

### `api.is_in_class() -> bool`

`get_schedule_status().status == 'ongoing'` 的便捷封装。

**典型用法：上课免打扰**（audio 插件上课隐藏并停轮询，下课自动恢复）：

```python
def tick():
    if api.is_in_class() and cfg["mute_in_class"]:
        return                        # 上课期间直接不更新显示位
    ...
```

```python
def tick():
    st = api.get_schedule_status()
    if st and st.get("status") == "upcoming" and st.get("until_sec", 999) <= 60:
        api.notify(f"即将上课：{st['course']}")
```

> 更复杂的"只在课间/自习显示"判定（如 disaster_alert 的
> `normal_only_free_time`）需要看 `status` 与 `course` 里的"自习"关键字。

---

## 16. 日志 / 刷新 / 通知

### `api.log(*args)`

- 打印 `[Plugin:<插件名>] ...` 到 stdout（打包版无控制台时仅调试可见）。
- 参数与 `print` 相同，任意个数。

### `api.request_refresh()`

- 请求**立即**刷新：主岛文案 / extra / **警报条**、副岛内容、主窗口。
- 数据变化后调用；这是主岛/副岛内容更新的**主要驱动方式**
  （除主岛自身的每秒 tick 与警报条的 30fps 拉取）。

### `api.notify(text, is_end=False, force=False)`

主岛弹出**提醒条**（alert 状态）：打断当前状态，展开为提醒宽度
（设置 `island_alert_width`，默认 300px），停留 `island_alert_hold_ms`
（默认 600ms）后自动收回。

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `text` | str | — | 提醒文字（单行，过长会跑马灯） |
| `is_end` | bool | False | `False` = **绿色**文本（#30d158，适合"上课了"）；`True` = **白色**文本（适合"下课了"） |
| `force` | bool | False | 🆕 **紧急预警专用**：即使灵动岛因**上课 / PPT 全屏 / Office 前台**被隐藏，也会**立即把岛拉回屏幕**并弹出提醒，并在设置 `island_force_hold_sec`（默认 60 秒）内保持不被再次隐藏 |

注意事项：

- **`force=True` 只用于真正紧急、必须打断用户的事件**（地震等），不要滥用。
- 连续 `notify` 时新提醒会正确**顶替**旧提醒（旧提醒的收回定时器不会误伤新提醒）。
- 如果灵动岛被用户**关闭**（`island_enabled=False`），`notify` 静默失效——
  所以**不能只依赖 `notify` 传达关键信息**，重要内容请同时用显示位呈现。
- 提醒条是**短时**的（默认 0.6 秒），不适合承载长信息。
- 兼容旧宿主：老版本 `notify` 没有 `force` 参数，调用会抛 `TypeError`，建议这样写：

  ```python
  def _notify(text, force=False):
      api = _state["api"]
      try:
          api.notify(text, force=force)          # 新宿主
      except TypeError:
          api.notify(text)                       # 老宿主回退（保证提醒不丢）
      except Exception as e:
          api.log("notify 失败:", e)
  ```

---

## 17. spec 通用规则与性能要求

所有 `fn()`（`island_text` / `island_extra` / `island_banner` / `panel` / `subisland`）
遵守同一契约：

1. **必须快**：同步返回，微秒~毫秒级。
   把耗时工作放后台线程或 `set_interval`，把结果缓存到模块级变量，**spec 只读缓存**。
2. **返回 `None` = 隐藏**：这是唯一的显隐控制方式，随时可用。
3. **每次返回新 dict**：不要复用并原地修改同一个 dict（主程序可能保留引用）。
4. **异常安全**：抛异常会被捕获并记日志，该次内容视为"无"，不会崩主程序
   ——但**不要依赖这一点掩盖 bug**。
5. **`draw(painter, rect, t)` 约定**：
   - `painter` 已开抗锯齿；**不要 `end()` 它**；建议用 `save()/restore()` 配对。
   - `rect` 是**目标区域的局部坐标**（`QRect` 或 `QRectF`），在其中绘制即可。
   - `t = time.monotonic()`（秒，单调递增）。**用 `t` 做动画相位，不要自己调 `time.time()`**。
   - 背景已由主程序填充深色（`#1c1c1e`），内容画浅色。
   - 需要测量文字宽度用 `QFontMetricsF(font).horizontalAdvance(text)`。
6. **线程**：所有 api 方法与 spec/draw 回调都在 **GUI 线程**执行。
   后台线程写完数据后**不要直接碰 Qt 控件**，用 `set_interval` 的 tick 或
   `request_refresh` 汇合。
   > 正确范例：audio 插件的 daemon 线程只写模块级 dict，tick 里读 dict 再更新显示。

### 性能预算速查

| 回调 | 频率 | 预算 |
|---|---|---|
| `add_island_banner` 的 `fn()` | **~30fps** | 微秒级（只读内存） |
| `add_island_extra` / `add_subisland` 的 `draw` | ~60fps | 尽量 < 2ms（复杂绘制要预计算） |
| `add_island_text` / `add_island_extra`(spec) / `add_subisland`(spec) | 1 次/秒 | 毫秒级 |
| `add_panel` 的 `fn()` | 下拉瞬间 | 毫秒级（可以稍微重一点，但别卡住 UI） |
| `set_interval` 的 `fn` | 自定 | 不要阻塞超过间隔 |

---

## 18. 主题适配约定

主程序支持**浅色 / 深色主题**（跟随系统，或设置里手动切换，v3.0 起支持）。规则：

1. **插件设置页**：不要自设颜色类样式（背景色、文字色、边框色等），交给宿主主题；
   提示文字设 `setObjectName("hint")`；标题类文字可设 `setObjectName("sectionTitle")`。
2. **主岛 / 副岛 / 下拉面板**：恒为**深色自绘**（仿 iPhone 灵动岛），
   与系统主题无关；插件 `draw` 内容保持**深底浅字**风格，**无需适配**。
3. 主程序主题对插件**完全透明**：插件不需要（也无法）读取当前主题。
4. **警报条**同理为深色自绘：`color` 字段影响的是进度条颜色，文字始终白色。

---

## 19. 完整示例插件

`plugins/hello/plugin.json`：

```json
{
  "name": "示例插件",
  "version": "1.0.0",
  "entry": "main.py",
  "description": "演示主要 API 的用法"
}
```

`plugins/hello/main.py`：

```python
"""示例插件：演示文本、面板、副岛、设置页、定时器、配置、课表状态。"""
from PySide6.QtGui import QColor
from PySide6.QtCore import Qt, QRectF
from PySide6.QtWidgets import QWidget, QFormLayout, QCheckBox

DEFAULTS = {"enabled": True, "show_on_sub": True}
_state = {"config": dict(DEFAULTS), "count": 0, "api": None}


# ---------- 主岛胶囊文本 ----------
def island_text():
    if not _state["config"].get("enabled"):
        return None
    return f"计数 {_state['count']}"


# ---------- 下拉面板 ----------
def panel_spec():
    return {
        "text": f"示例插件运行中\n已计数：{_state['count']}",
        "width": 180,
        "height": 20 + 2 * 22 + 14,        # 两行 -> 按行数算高度
        "order": 100,
        "position": "left",
    }


# ---------- 副岛（自绘） ----------
def sub_spec():
    if not _state["config"].get("show_on_sub"):
        return None
    return {"length": 120, "draw": draw_sub,
            "auto_collapse": True, "priority": 0}


def draw_sub(painter, rect, t):
    painter.setPen(QColor('white'))
    if rect.width() <= 46:                 # 收起为圆形：只画图标
        painter.drawText(rect, Qt.AlignCenter, "🔔")
        return
    painter.drawText(QRectF(rect), Qt.AlignCenter,
                     f"示例 {_state['count']}")


# ---------- 设置页 ----------
def build_settings(api):
    w = QWidget()
    form = QFormLayout(w)
    cb = QCheckBox("显示在副岛")
    cb.setChecked(bool(_state["config"].get("show_on_sub")))

    def save(*_):
        _state["config"]["show_on_sub"] = bool(cb.isChecked())
        api.set_config(_state["config"])   # 写盘 + 自动刷新

    cb.toggled.connect(save)
    form.addRow("", cb)
    return w


# ---------- 定时任务 ----------
def tick():
    _state["count"] += 1
    api = _state["api"]
    st = api.get_schedule_status()
    if st and st.get("status") == "upcoming" and st.get("until_sec") == 60:
        api.notify(f"1 分钟后上 {st.get('course', '')}")
    api.request_refresh()


# ---------- 入口 ----------
def register(api):
    _state["api"] = api
    _state["config"] = {**DEFAULTS, **(api.get_config() or {})}
    api.set_config(_state["config"])

    api.add_island_text(island_text)
    api.add_panel(panel_spec)
    api.add_subisland(sub_spec)
    api.add_settings_page("示例", build_settings, icon="🔔")
    api.set_interval(5, tick)
    api.on_load(lambda: api.log("配置已加载", _state["config"]))
    api.on_stop(lambda: api.log("bye"))
```

---

## 20. 常见问题与排查（FAQ）

### Q1：插件加载失败，`loaded` 里写 `加载失败: ModuleNotFoundError: No module named 'sources'`

**最常见的原因**：你在 `main.py` 里直接 `import sources`，但**插件目录不在 `sys.path`**。
解法见 [§1 的 `_load_sibling`](#1-插件模型与加载机制)。

### Q2：插件的显示位一直不显示

按顺序排查：

1. `fn()` 返回的是不是 `None`？加一行 `api.log(repr(spec))` 看。
2. **priority 被顶掉**：同一显示位只有一个插件能占。日志里看不出竞争，
   把 priority 临时调大（如 999）验证。
3. `add_island_extra` 返回的 spec 里**缺 `draw`** → 整个 spec 被丢弃。
4. `add_subisland` 的 spec 里 `text` 与 `draw` **都没有** → 被丢弃。
5. `add_panel` 的 `text` 为空 → 被丢弃。
6. 主岛处于 `hidden` / 下拉展开 / 测试演示中 → 这些状态不取 spec。
7. `add_island_banner`：优先检查 `hasattr(api, "add_island_banner")` 是否为真（宿主版本）。

### Q3：改了配置但界面没变

- `set_config()` 会自动刷新；如果你是自己写 `config.json`（不走 `set_config`），
  **必须手动 `api.request_refresh()`**。
- 面板（`add_panel`）只在下拉瞬间收集 spec，**展开期间不会刷新**——收起来再点开。

### Q4：副岛反复自动展开 / 收起

`draw` 用了 `lambda` 或局部函数，导致每次 `fn()` 返回的 `draw` 对象 `id()` 都不同，
副岛把每次都当成"新内容接管"。**改成模块级稳定函数**：

```python
def draw_sub(painter, rect, t):     # ✅ 模块级
    ...

def sub_spec():
    return {"draw": draw_sub, ...}  # 一直用同一个对象

# ❌ 反例
def sub_spec():
    return {"draw": lambda p, r, t: ...,}
```

### Q5：警报条一直占着屏幕不消失

宿主**不会**替你释放。`fn()` 必须自己返回 `None`。见
[§10.5 必须自己限制占用时长](#105-必须自己限制占用时长重要)。

### Q6：点击确认后警报条立刻又弹出来

`on_confirm` 里没有让 `fn()` 对该事件返回 `None`。
正确做法是记录 `(uid, revision)`，遇到"同一事件且未升级"就返回 `None`
（升级后应允许再次弹出）。

### Q7：老宿主上调用新接口报错

一律先探测：

```python
if hasattr(api, "add_island_banner"):
    api.add_island_banner(banner_spec)
```

`notify(force=True)` 用 `try/except TypeError` 回退（见 §16）。

### Q8：`set_interval(0.5, fn)` 还是 1 秒一次

这是设计如此：实际间隔 = `max(1, int(seconds*1000))` ms，**最小 1 秒**。
需要更高频用 `draw` 的 `t` 或 `add_island_banner` 的 `fn()`。

### Q9：后台线程里能直接更新 Qt 控件吗？

**不能**。所有 api 与 spec/draw 都在 GUI 线程执行。
后台线程只写模块级 dict，在 tick 里读 dict 更新显示或 `request_refresh()`。

### Q10：想让插件在"上课期间"完全静默

```python
def fn():
    if api.is_in_class() and _state["config"]["silent_in_class"]:
        return None          # 显示位直接不显示
    ...
```

注意 `is_in_class()` 调用开销很小，但**别在 30fps 的 `fn()` 里每秒算几十次**——
推荐在 `set_interval(1, ...)` 里把结果缓存进 `_state["in_class"]`。

---

## 21. 调试技巧

### 21.1 打日志

```python
api.log("spec =", spec)        # 输出 [Plugin:我的插件] spec = {...}
```

### 21.2 看加载结果

设置窗口 →「插件」页会列出每个插件的 `loaded` 状态与错误信息
（`[(目录名, 是否成功, 消息), ...]`）。这是排查"插件没生效"的第一站。

### 21.3 强制演示 / 演练

若你的功能依赖课表状态或地震等外部事件，**做一个"演练/演示"入口**是最高效的调试手段：
在设置页放一个按钮，直接构造一次模拟事件走真实链路。
（`disaster_alert` 的「开始演练」就是范例：可选震中城市 + 震级，倒计时走真实算法。）

### 21.4 离屏自测（推荐）

不必启动主程序即可验证纯逻辑与渲染：

```python
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"      # 无窗口渲染
from PySide6.QtWidgets import QApplication       # 必须用 QApplication
app = QApplication([])
from PySide6.QtGui import QImage

# 验证 spec
assert my_banner_spec()["text"]

# 验证 draw 不崩
img = QImage(300, 40, QImage.Format_ARGB32)
img.fill(0)
# 直接调你的 draw：draw(painter, rect, t)
```

> ⚠ `QGuiApplication` **不含控件模块**，用它构建 `QWidget` 会**静默崩溃**（退出码 127）。
> 一定要用 `QApplication`。

### 21.5 打印实测频率

如果怀疑自己的 `fn()` 太重，加个计数器验证：

```python
_state["calls"] = _state.get("calls", 0) + 1
if _state["calls"] % 30 == 0:
    api.log("fn 已调用", _state["calls"], "次")
```

---

## 附录 A：课表状态字典字段表

`api.get_schedule_status()` 返回值（`status` 决定存在哪些字段）：

| status | 含义 | 附加字段 |
|---|---|---|
| `ongoing` | 上课中 | `course` 课程名、`period` 节次名、`start`/`end` "HH:MM"、`remain_sec` 剩余秒、`remain_min` 剩余分钟（向上取整，≥1）、`duration_sec` 课程总长秒、`index` 节次下标 |
| `upcoming` | 未上课（下一节） | `course`、`period`、`start`、`until_sec` 距上课秒、`until_min` 距上课分钟（≥1）、`advance_sec` 生效的提前量秒、`index` |
| `holiday` | 假期中 | `name` 假期名（可空串） |
| `none` | 今天无课 | — |
| `done` | 今日课程已结束 | — |

说明：

- `upcoming` 的"上课时刻"已包含**提前提醒**（`advance_minutes`）与
  **时间偏移**（`time_offset_seconds`）；
  `until_sec <= island_countdown_sec`（默认 60）时主岛会进入**蓝色倒计时**状态。
- `remain_sec` / `until_sec` 为 int 秒；时间偏移会让课表显示时刻与真实时刻不同
  （面板显示的是偏移后的时刻）。
- 临时调课、调休补课、周末作息、跨午夜课程**已由主程序处理**，插件拿到的是最终生效结果。

---

## 附录 B：主程序关键设置键

插件可读取（通过主程序行为间接感知）的设置项，及其对插件显示的影响：

| 键 | 默认 | 影响 |
|---|---|---|
| `island_countdown_sec` | 60 | 上课前多少秒进入主岛蓝条倒计时 |
| `island_alert_width` | 300 | `api.notify` 提醒条宽度 |
| `island_alert_hold_ms` | 600 | 提醒条停留时长 |
| `island_force_hold_sec` | 60 | `notify(force=True)` 强制显示保持秒数 |
| `island_top_margin` | 6 | 灵动岛距屏幕顶部 |
| `island_hide_on_fullscreen` | 开 | 全屏时自动收起（**警报条期间不生效**） |
| `anim_duration` | — | 面板/胶囊动画时长基准（钳制 100–500ms） |
| `anim_fade_panel` | 开 | 下拉面板是否淡入 |
| `anim_fade_text` | 开 | 主岛文案变化是否滚动切换 |
| `sub_island_auto_collapse_sec` | 5 | 副岛 `auto_collapse` 的收圆延时（0=不收） |
| `sub_island_collapsed` | 关 | 副岛是否默认收起 |
| `show_island` / `show_sub_island` / `show_main_window` | 开 | 各组件是否显示 |
| `theme_mode` | 跟随系统 | 浅色/深色主题（**插件设置页自动跟随**） |

---

## 附录 C：内置插件参考

| 插件 | 用到的 API | 可参考什么 |
|---|---|---|
| `clock` | `add_panel`、`set_interval` | 最简面板插件 |
| `gaokao_countdown` | `add_panel`、`add_settings_page`、`set_interval` | 面板 + 设置页 |
| `weather` | `add_subisland`、`add_settings_page`、`set_interval`、`on_start`、`request_refresh` | 副岛自绘动画（priority 0 占位）、`QNetworkAccessManager` 异步请求 |
| `audio` | `add_island_extra`、`add_subisland`、`add_settings_page`、`set_interval`、`on_stop`、`is_in_class`、`get_data_dir`、`request_refresh` | 最完整参考：priority 10、上课自动隐藏、子进程管理、daemon 线程只写 dict |
| **`disaster_alert`** | **`add_island_banner`（全套）**、`add_island_extra`、`add_subisland`、`add_panel`、`add_settings_page`、`on_load/on_start/on_stop`、`set_interval`、`get_data_dir`、`notify(force)`、`is_in_class`、`request_refresh` | **v4.0 新增能力的最佳范例**：警报条两层 + 点击确认 + 大震/小震分档、跑马灯自绘、三级联动下拉、颜色选择器、可配置配色与阈值、演练模式、城市数据模块（`_load_sibling` 加载同目录模块） |

---

## 附录 D：已知限制与注意事项

1. **无热重载**：插件改动（新增/删除/改代码）必须**重启主程序**生效。
2. **同进程**：插件死循环/阻塞会卡死整个程序；耗时操作务必异步化
   （后台线程 + 主线程 tick 汇合）。
3. `subisland_show_weather()` 是**保留接口**，当前无效果。
4. **下拉面板只能纯文本**，不可自绘、不可换色；想自绘请用副岛或主岛 extra / 警报条。
5. **独占资源与 priority 建议**：
   | 显示位 | 独占 | 建议 priority |
   |---|---|---|
   | 主岛 extra | ✅ | 占位类 0，临时重要信息（媒体等）10 |
   | 主岛**警报条** | ✅ | **紧急事件 ≥100** |
   | 副岛 | ✅ | 占位类 0，临时重要信息 10 |
   | 下拉面板 | ❌（按列排布） | 只用 `order` 排序 |
   > 同一个插件想"分段占用"时，记得用 [§10.6](#106-与-add_island_extra-的分工) 的写法，
   > 以"当前是否真的有内容"决定让位，避免"两边都不显示"。
6. **Windows 专属**：主程序大量依赖 Win32（置顶、前台检测、SMTC 等），
   插件跨平台需自行判断 `sys.platform`。
7. **打包（PyInstaller）**：插件目录在 exe 同级 `plugins/` 下；
   更新器升级时**保留** `settings/` 与 `plugins/`。
8. **`add_island_banner` 是 v4.0 接口**：请先用 `hasattr(api, "add_island_banner")` 探测，
   老版宿主上回退到 `add_island_extra` + `add_subisland`，
   否则会出现"什么都不显示"。
9. **`notify(force=True)` 是 v4.0 参数**：调用时用 `try/except TypeError` 回退（见 §16）。
10. **时区**：灵动岛与课表的时刻均为**北京时间（UTC+8，固定偏移，无夏令时）**；
    插件若自行取时间，注意 `time.time()` 是 UTC 时间戳，`datetime.now()` 才是本地时间。

---

*文档版本 v4.0 · 与主程序 v3.0+ 的插件系统实现逐条核对 · 共 24 个 API（含 1 个保留接口）*
