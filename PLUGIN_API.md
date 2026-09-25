# ClassBoard 插件 API 接口规范

> 版本：v3.0（对应主程序 v3.0+）
> 本文档是插件开发的**唯一权威接口规范**，逐条对应 `plugin_manager.py` 的实现。
> 读完本文档即可不读源码开发任意插件。

---

## 目录

1. [插件模型与加载机制](#1-插件模型与加载机制)
2. [目录结构与 plugin.json](#2-目录结构与-pluginjson)
3. [入口约定 register(api)](#3-入口约定-registerapi)
4. [生命周期](#4-生命周期)
5. [API 总览速查表](#5-api-总览速查表)
6. [生命周期注册](#6-生命周期注册)
7. [定时器](#7-定时器)
8. [主岛：胶囊文本 add_island_text](#8-主岛胶囊文本-add_island_text)
9. [主岛：加长片段 add_island_extra](#9-主岛加长片段-add_island_extra)
10. [下拉面板 add_panel](#10-下拉面板-add_panel)
11. [副岛 add_subisland 系列](#11-副岛-add_subisland-系列)
12. [设置页 add_settings_page](#12-设置页-add_settings_page)
13. [配置持久化](#13-配置持久化)
14. [课表状态](#14-课表状态)
15. [日志 / 刷新 / 通知](#15-日志--刷新--通知)
16. [spec 通用规则与性能要求](#16-spec-通用规则与性能要求)
17. [主题适配约定](#17-主题适配约定)
18. [完整示例插件](#18-完整示例插件)
19. [附录 A：课表状态字典字段表](#附录-a课表状态字典字段表)
20. [附录 B：主程序关键设置键](#附录-b主程序关键设置键)
21. [附录 C：内置插件参考](#附录-c内置插件参考)
22. [附录 D：已知限制与注意事项](#附录-d已知限制与注意事项)

---

## 1. 插件模型与加载机制

- 插件是 `plugins/<插件目录名>/` 下的一个**松散目录**，含 `plugin.json` + 入口 py 文件。
- 程序启动时 `PluginManager.load_all()` 按**目录名字典序**（`sorted(os.listdir)`）逐个加载。
- 加载方式：`importlib.util.spec_from_file_location(f"plugin_{name}", entry)` 动态执行入口文件，然后调用其 `register(api)`。
- **无沙箱、无签名、无权限控制**：插件与主程序同进程同权限，可 import 任意库、联网、起子进程。请只安装可信来源的插件。
- 单个插件的任何异常（加载失败 / register 出错 / 运行期 spec 出错）都会被捕获并记录，**不影响主程序和其他插件**。
- 加载结果记录在 `PluginManager.loaded`：`[(目录名, 是否成功, 消息), ...]`，设置窗口"插件"页可见。
- 插件设置页里"添加插件"只是**复制文件到插件目录，重启后生效**；`.cbplugin` 扩展名仅为文件过滤器约定，没有打包格式。

### 加载失败的可能原因（loaded 中的消息）

| 消息 | 含义 |
|---|---|
| `读元信息失败: ...` | plugin.json 读取/解析异常 |
| `入口不存在` | entry 指定的文件不存在 |
| `加载失败: ...` | 入口文件 exec_module 抛异常（语法错误、import 失败等） |
| `无 register` | 模块没有 `register` 函数 |
| `register 出错: ...` | register(api) 调用抛异常 |

---

## 2. 目录结构与 plugin.json

```
plugins/my_plugin/
├── plugin.json     # 必需，元信息
├── main.py         # 入口（默认），必须实现 register(api)
├── data.json       # （可选）由 api.set_config 自动生成
├── config.json     # （可选）插件自管的配置（内置插件的惯例做法）
└── ...             # 其他资源文件随意
```

`plugin.json` 字段：

| 字段 | 类型 | 必需 | 默认 | 说明 |
|---|---|---|---|---|
| `name` | str | 建议 | — | 显示名（目前主程序不消费，仅文档意义） |
| `version` | str | 建议 | — | 版本号（同上） |
| `entry` | str | 否 | `"main.py"` | 入口文件名（相对插件目录） |
| `description` | str | 建议 | — | 描述（同上） |

> 注：`clock` 插件还带了 `display_name/author_id/author_name` 扩展字段，主程序不消费，可自由扩展。

---

## 3. 入口约定 register(api)

入口文件必须定义模块级函数 `register(api)`，主程序加载时调用一次：

```python
def register(api):
    api.on_start(lambda: api.log("started"))
```

- `api` 是该插件**专属**的 `PluginAPI` 实例（绑定插件名与插件目录）。
- `register` 内应只做**注册**（钩子等），不要做耗时操作（阻塞启动）。
- 耗时初始化放到 `on_load` / `on_start` 回调里。
- 插件内部状态推荐用**模块级 dict** 保存（参考内置插件的 `_state` 模式）。

---

## 4. 生命周期

`load_all()` 的严格顺序：

```
for 每个插件目录（目录名字典序）:
    读 plugin.json → 动态加载入口 → 调 register(api)   # 注册钩子
for 每个插件:
    调用其注册的 on_load 回调        # 全部插件 register 完之后
for 每个插件:
    调用其注册的 on_start 回调       # 全部 on_load 完之后
```

退出时（托盘退出 / 主窗口退出）`stop_all()`：

```
停止所有 api.set_interval / set_timeout 创建的 QTimer
按注册顺序调用每个插件的 on_stop 回调
```

| 回调 | 时机 | 典型用途 |
|---|---|---|
| `on_load(fn)` | 全部插件 register 完成后 | 读配置、预热数据、恢复缓存 |
| `on_start(fn)` | on_load 之后 | 首次刷新、启动后台任务、注册首个 spec 数据 |
| `on_stop(fn)` | 程序退出前 | 杀子进程、关网络会话、保存状态 |

---

## 5. API 总览速查表

| 分类 | 方法 | 一句话 |
|---|---|---|
| 生命周期 | `on_load(fn)` / `on_start(fn)` / `on_stop(fn)` | 注册生命周期回调 |
| 定时器 | `set_interval(seconds, fn)` | 周期定时器，返回 QTimer |
| 定时器 | `set_timeout(seconds, fn)` | 单次定时器，返回 QTimer |
| 主岛 | `add_island_text(fn)` | 胶囊文案追加一段文字 |
| 主岛 | `add_island_extra(fn)` | 胶囊右侧加长自绘片段（可点击） |
| 面板 | `add_panel(fn)` | 点击主岛下拉的面板卡片 |
| 副岛 | `add_subisland(fn)` | 副岛内容（text/icon 或自绘） |
| 副岛 | `set_subisland_length(px)` | 全局副岛默认长度 |
| 副岛 | `set_subisland_collapsed(b)` / `collapse_subisland()` / `expand_subisland()` | 收起/展开副岛 |
| 副岛 | `on_subisland_click(fn)` | 副岛点击回调 |
| 副岛 | `subisland_show_weather(b)` | ⚠ 保留接口，当前无效果 |
| 设置 | `add_settings_page(title, factory, icon)` | 在设置窗口加一页 |
| 配置 | `get_data_dir()` | 插件数据目录 |
| 配置 | `get_config(default)` / `set_config(data)` | data.json 读写 |
| 课表 | `get_schedule_status()` | 当前课程状态字典 |
| 课表 | `is_in_class()` | 是否上课中 |
| 交互 | `log(*args)` | 打印 `[Plugin:名] ...` |
| 交互 | `request_refresh()` | 请求主岛/副岛/主窗口立即刷新 |
| 交互 | `notify(text, is_end)` | 主岛弹出提醒条 |

---

## 6. 生命周期注册

### `api.on_load(fn)`
### `api.on_start(fn)`
### `api.on_stop(fn)`

- `fn`：无参数 callable。可注册多个，按注册顺序调用。
- 异常会被捕获并通过 `api.log` 记录，不会中断其他回调。

```python
def register(api):
    api.on_load(load_cache)
    api.on_start(first_refresh)
    api.on_stop(cleanup)
```

---

## 7. 定时器

### `api.set_interval(seconds, fn, start=True) -> QTimer`

- 每 `seconds` 秒触发一次 `fn`。实际间隔 = `max(1, int(seconds*1000))` ms。
- 返回的 `QTimer` 可自行 `stop()/start()/setInterval()`。
- **退出时由主程序统一停止**，插件无需（也不应）自行 delete。
- 不要用它做高频刷新：主岛/副岛的动画帧率由主程序维护，插件只需在**数据变化后**调 `request_refresh()`。

### `api.set_timeout(seconds, fn) -> QTimer`

- 单次触发（singleShot）。

```python
def register(api):
    api.set_interval(1, tick)          # 每秒
    api.set_timeout(5, delayed_init)   # 5 秒后一次
```

> 内置插件 clock / gaokao_countdown 用 `set_interval(1, ...)` 秒级刷新；audio 用 `set_interval(1, ...)` 轮询状态。

---

## 8. 主岛：胶囊文本 add_island_text

### `api.add_island_text(fn)`

- `fn() -> str | None`：返回要**追加到主岛胶囊文案末尾**的文字；返回 `None`/空串则不追加。
- 多个插件的文本以**全角空格 `　`** 拼接，最终文案为：`{课表状态文案} · {插件文本1}　{插件文本2}`。
- **调用时机**：主岛每秒刷新时同步调用。必须**纯函数、极快**（微秒级），不得联网/读写大文件。
- 文案变化时主岛自动播放"顶掉"滚动动画（受设置"文字变化时渐显"控制）。

```python
def register(api):
    api.add_island_text(lambda: f"{count} 条待办" if count else None)
```

---

## 9. 主岛：加长片段 add_island_extra

### `api.add_island_extra(fn)`

在主岛胶囊**右侧加长一段**完全由插件自绘的区域（分割线左侧是课表内容，右侧是你）。

`fn() -> dict | None`，spec 字段：

| 字段 | 类型 | 必需 | 默认 | 说明 |
|---|---|---|---|---|
| `width` | int | 否 | 160 | 片段宽度 px，钳制 **[0, 400]** |
| `draw` | callable | **是** | — | `draw(painter, rect, t)` 自绘函数，缺了 spec 会被丢弃 |
| `on_click` | callable | 否 | — | 点击该片段时调用（无参数） |
| `priority` | int | 否 | 0 | 多插件竞争时**数值最大者独占**该片段 |

行为细节：

- **仲裁**：所有插件的 spec 取 `priority` 最大者；平级时先注册者胜（`>` 比较）。
- **调用时机**：主岛每秒重新取一次 spec；`draw` 存在时该区域以 **~60fps** 重绘（`t = time.monotonic()` 秒，可直接驱动动画）。
- **显示状态**：仅主岛 `compact`（常规胶囊）状态显示；倒计时 / 提醒 / 隐藏 / 下拉 / 测试演示时不显示、不取 spec。主岛隐藏时不重绘（省电）。
- **绘制**：`rect` 是片段在主岛上的矩形（高=胶囊高 40px）。左侧已由主程序画好 1px 半透明分割线。文字建议白色、背景透明。
- **点击**：命中区域 = 整个片段 rect。点击触发 `on_click()`（异常被捕获）。
- **宽度变化**：`width` 改变时主岛自动播放宽度动画；**下拉面板展开期间不会重排**（不会打断下拉）。
- 返回 `None` 表示当前不显示（如 audio 插件在无媒体/上课中返回 None）。

```python
def extra_spec():
    if not has_content():
        return None
    return {"width": 200, "draw": my_draw, "on_click": my_click,
            "priority": 10}

def my_draw(painter, rect, t):
    # rect: QRect，片段区域；t: float 秒
    painter.setPen(QColor('white'))
    painter.drawText(rect, Qt.AlignCenter, "hello")
```

> 参考实现：`plugins/audio/main.py` 的 `_extra_spec` / `_draw_media`（priority 10，播放/暂停切换）。

---

## 10. 下拉面板 add_panel

### `api.add_panel(fn)`

点击主岛胶囊时下拉展开一排面板卡片，插件可注册自己的卡片。

`fn() -> dict | None`，spec 字段：

| 字段 | 类型 | 必需 | 默认 | 说明 |
|---|---|---|---|---|
| `text` | str | **是** | — | 面板正文（支持 `\n` 多行，自动换行）；**空则整个 spec 被丢弃** |
| `width` | int | 否 | 180 | 期望宽度，最终钳制 `[min_width, 320]` |
| `min_width` | int | 否 | 120 | 超宽收缩时的下限 |
| `height` | int | 否 | — | 面板高度 px（**建议按内容行数提供**，缺省可能显示不全） |
| `order` | int | 否 | 100 | 同列内排序，**升序**（小的靠左） |
| `position` | str | 否 | `"left"` | `"left"` 或 `"right"`：放在课表面板左侧列还是右侧列 |

布局与行为：

- 下拉时的布局：`[left 列(按 order)] [课表面板] [right 列(按 order)]`，面板间距 4px。
- **课表面板**固定居中，宽 240（收缩下限 180）；总宽超过屏幕宽 80% 时：先缩课表面板，再按比例缩其他面板（不低于各自 `min_width`）。
- 面板**逐个错峰展开**（间隔 70ms，从高度 0 展开 + 轻微上浮 + 可选淡入），展开后**停留 3 秒自动收回**；期间滚轮可滚动（总高超屏幕 1/3 时出现底部渐变遮罩）。
- **spec 在下拉瞬间收集一次**，展开期间不刷新；想更新内容等下次下拉。
- 面板为深色卡片（`#1c1c1e` 底，13px `#e6e6e6` 文字，内边距 12px），自绘不可定制，只能提供纯文本。
- 动画时长跟随设置"动画时长"（`anim_duration`，钳制 100–500ms）。

```python
def panel_spec():
    return {
        "text": f"距高考 {days} 天\n{h:02d}:{m:02d}:{s:02d}",
        "width": 190, "height": 74,
        "order": 90, "position": "right",
    }

def register(api):
    api.add_panel(panel_spec)
    api.set_interval(1, api.request_refresh)  # 文案本身会在下次下拉时更新
```

> 参考实现：`plugins/clock/main.py`、`plugins/gaokao_countdown/main.py`。

---

## 11. 副岛 add_subisland 系列

副岛是主岛右侧的小岛（高 40px，宽 44–380px，可收成 40px 圆形）。**同一时刻只显示一个插件的内容**。

### `api.add_subisland(fn)`

`fn() -> dict | None`，spec 字段：

| 字段 | 类型 | 必需 | 默认 | 说明 |
|---|---|---|---|---|
| `text` | str | 条件 | — | 文本内容（与 `draw` 至少其一，否则 spec 被丢弃） |
| `icon` | str | 否 | — | 文本模式下的前置 emoji 图标；收起为圆形时显示它 |
| `length` | int | 否 | 见下 | 展开宽度 px，钳制 **[44, 380]**；未提供时用全局值（`set_subisland_length`），再没有则 158 |
| `draw` | callable | 条件 | — | `draw(painter, rect, t)` 完全自绘（优先于 text/icon） |
| `auto_collapse` | bool | 否 | False | True=空闲 N 秒后自动收成圆形（N 为设置项 `sub_island_auto_collapse_sec`，默认 5，0=不收） |
| `priority` | int | 否 | 0 | 多插件竞争，**数值最大者独占副岛** |

行为细节：

- **仲裁**：同 `add_island_extra`，priority 最大者胜（天气=0 占位，媒体=10 顶替）。
- **刷新**：`request_refresh()` 后副岛重新取 spec；`draw` 模式下副岛以 ~60fps 调用 `draw`。
- **自绘约定**：收起为圆形时 `draw` 仍被调用，`rect.width() <= 46` 时应只画一个图标（参考 weather/audio 的处理）。
- **文本模式**：展开时 `icon + text`；收起时只显示 `icon`（无 icon 则显示 text 首字符）。
- **自动展开**：副岛当前处于收起状态时，如果**新内容接管**（spec 身份变化，如天气→媒体）且该内容 `auto_collapse=False`，副岛会**自动展开**；同一内容持续刷新不会干扰用户手动收起。
- **点击**：左键 = 先触发所有 `on_subisland_click` 注册的回调，再**切换收起/展开**。右键菜单可关闭副岛。
- **显示时机**：仅主岛处于 compact/countdown/alert 时显示；位置自动跟随主岛右缘 +8px。

### 其他副岛控制

| 方法 | 说明 |
|---|---|
| `set_subisland_length(px)` | 设置**全局**副岛长度：之后所有未提供 `length` 的 spec 都用它（自动触发刷新） |
| `set_subisland_collapsed(b)` | 收起/展开副岛（等同用户点击） |
| `collapse_subisland()` / `expand_subisland()` | 上面方法的便捷封装 |
| `on_subisland_click(fn)` | 注册副岛左键点击回调（在折叠切换之前触发） |
| `subisland_show_weather(enabled)` | ⚠ **保留接口**：当前主程序未消费该开关，调用无实际效果，勿依赖 |

```python
def sub_spec():
    if not data:
        return None
    return {"length": 158, "draw": draw_weather,
            "auto_collapse": True, "priority": 0}

def register(api):
    api.add_subisland(sub_spec)
```

> 参考实现：`plugins/weather/main.py`（自绘动画图标）、`plugins/audio/main.py`（priority 10 + auto_collapse False 保持展开）。

---

## 12. 设置页 add_settings_page

### `api.add_settings_page(title, factory, icon="🧩")`

在设置窗口左侧导航追加一页（排在"主窗口/灵动岛/动画/插件/关于"之后）。

- `title`：导航显示名。
- `icon`：导航 emoji 图标，默认 🧩。
- `factory(api) -> QWidget`：**设置窗口每次打开时**调用一次，返回页面内容控件。工厂收到的 `api` 就是插件自己的 api。
- 页面放进可滚动区域，布局用 `QVBoxLayout`/`QFormLayout` 即可；控件改动建议**即时保存**到插件配置并 `api.request_refresh()`。
- 工厂抛异常时页面显示"插件设置加载失败"占位，不影响其他页。

**主题约定（重要）**：设置窗口统一应用浅色/深色主题，插件页**不要自设颜色类 QSS**；提示文字用 `label.setObjectName("hint")` 自动获得主题提示色。详见 [17. 主题适配约定](#17-主题适配约定)。

---

## 13. 配置持久化

### `api.get_data_dir() -> str`

- 返回插件目录绝对路径（自动创建）。可自行在里面写文件（如 audio 插件写 PowerShell 脚本）。

### `api.get_config(default=None)`

- 读插件目录下 `data.json`；不存在/解析失败返回 `default`。

### `api.set_config(data)`

- 把 `data`（须可 JSON 序列化）原子写入 `data.json`（临时文件 + `os.replace`，崩溃不损坏），写后**自动 `request_refresh()`**。

```python
def register(api):
    cfg = {**{"enabled": True}, **(api.get_config() or {})}
    api.set_config(cfg)   # 首次运行补全默认并落盘
```

> 惯例说明：四个内置插件实际都自管 `config.json`（含默认值合并逻辑），`get_config/set_config`（data.json）更适合轻量插件，二选一即可。

---

## 14. 课表状态

### `api.get_schedule_status() -> dict | None`

返回当前课程状态字典（字段见 [附录 A](#附录-a课表状态字典字段表)），已包含主程序生效的**提前提醒**与**时间偏移**。provider 异常时返回 `None`。

### `api.is_in_class() -> bool`

- `get_schedule_status().status == 'ongoing'` 的便捷封装。
- 典型用法：**上课期间自动隐藏/静音**（audio 插件上课隐藏并停轮询，下课自动恢复）。

```python
def tick():
    st = api.get_schedule_status()
    if st and st.get('status') == 'upcoming' and st.get('until_sec', 999) <= 60:
        api.notify(f"即将上课：{st['course']}")
```

---

## 15. 日志 / 刷新 / 通知

### `api.log(*args)`

- 打印 `[Plugin:<插件名>] ...` 到 stdout（打包版无控制台时仅调试可见）。

### `api.request_refresh()`

- 请求**立即**刷新主岛文案/extra、副岛内容、主窗口。数据变化后调用；它是主岛/副岛内容更新的**主要驱动方式**（除主岛自身每秒 tick）。

### `api.notify(text, is_end=False)`

- 主岛弹出**提醒条**（alert）：打断当前状态，展开为提醒宽度（设置 `island_alert_width`，默认 300px），停留 `island_alert_hold_ms`（默认 600ms）后自动收回。
- `is_end=False`：绿色文本（#30d158，适合"上课了"）；`is_end=True`：白色文本（适合"下课了"）。
- 连续 `notify` 时新提醒会正确顶替旧提醒（旧提醒的收回定时器不会误伤新提醒）。
- 全屏隐藏 / Office 前台隐藏期间的状态保护已内置，但仍建议**节制使用**，只在真正重要事件时调用。

---

## 16. spec 通用规则与性能要求

所有 `fn()`（island_text / island_extra / panel / subisland）遵守同一契约：

1. **必须快**：同步返回，微秒~毫秒级。把耗时工作放后台线程/定时器，把结果缓存到模块级变量，spec 只读缓存。
2. **返回 None = 隐藏**：随时可通过返回 None 让内容消失。
3. **每次调用返回新 dict**：不要复用并原地修改同一个 dict（主程序可能保留引用）。
4. **异常安全**：抛异常会被捕获记日志，该次内容视为无，不会崩主程序——但不要依赖这一点掩盖 bug。
5. **draw(painter, rect, t)**：
   - `painter` 已开抗锯齿；不要 `end()` 它。
   - `rect` 是**目标区域局部坐标**，在其中绘制即可。
   - `t = time.monotonic()`（秒，单调递增），用它做动画相位，不要自己 `time.time()`。
   - 背景已由主程序填充深色（#1c1c1e），内容画浅色。
6. **线程**：所有 api 方法与 spec/draw 回调都在 **GUI 线程**执行；后台线程写完数据后不要直接碰 Qt 控件，用 `set_interval` 的 tick 或 `request_refresh` 汇合（audio 插件的 daemon 线程只写 dict 的做法是正确的范例）。

---

## 17. 主题适配约定

主程序支持浅色 / 深色主题（跟随系统或设置里手动切换）。规则：

- **插件设置页**：不要自设颜色类样式（背景色、文字色等），交给宿主主题；提示文字设 `setObjectName("hint")`。
- **主岛 / 副岛 / 下拉面板**：恒为深色自绘（仿 iPhone 灵动岛），插件 `draw` 内容保持**深底浅字**风格，与系统主题无关、无需适配。
- 主程序主题对插件完全透明，插件**不需要也无法**读取当前主题。

---

## 18. 完整示例插件

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
        "width": 180, "height": 60,
        "order": 100, "position": "left",
    }


# ---------- 副岛（自绘） ----------
def sub_spec():
    if not _state["config"].get("show_on_sub"):
        return None
    return {"length": 120, "draw": draw_sub,
            "auto_collapse": True, "priority": 0}


def draw_sub(painter, rect, t):
    painter.setPen(QColor('white'))
    if rect.width() <= 46:          # 收起为圆形：只画图标
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

## 附录 A：课表状态字典字段表

`api.get_schedule_status()` 返回值（`status` 决定存在哪些字段）：

| status | 含义 | 附加字段 |
|---|---|---|
| `ongoing` | 上课中 | `course` 课程名、`period` 节次名、`start`/`end` "HH:MM"、`remain_sec` 剩余秒、`remain_min` 剩余分钟(向上取整,≥1)、`duration_sec` 课程总长秒、`index` 节次下标 |
| `upcoming` | 未上课（下一节） | `course`、`period`、`start`、`until_sec` 距上课秒、`until_min` 距上课分钟(≥1)、`advance_sec` 生效的提前量秒、`index` |
| `holiday` | 假期中 | `name` 假期名（可空串） |
| `none` | 今天无课 | — |
| `done` | 今日课程已结束 | — |

说明：

- `upcoming` 的"上课时刻"已包含**提前提醒**（`advance_minutes`）与**时间偏移**（`time_offset_seconds`）；`until_sec <= island_countdown_sec` 时主岛会进入蓝色倒计时。
- `remain_sec`/`until_sec` 为 int 秒；时间偏移会让课表显示时刻与真实时刻不同（面板显示的是偏移后的时刻）。
- 临时调课、调休补课、周末作息、跨午夜课程已由主程序处理，插件拿到的是最终生效结果。

---

## 附录 B：主程序关键设置键

插件通过行为间接感受这些设置（`settings.json`，用户在设置窗口修改）：

| 键 | 默认 | 影响 |
|---|---|---|
| `island_countdown_sec` | 60 | 上课前多少秒进入倒计时 |
| `island_alert_width` / `island_alert_hold_ms` | 300 / 600 | `notify` 提醒条宽度与停留时长 |
| `sub_island_auto_collapse_sec` | 5 | `auto_collapse=True` 的副岛内容多少秒后收圆（0=不收） |
| `sub_island_collapsed` | False | 副岛默认收成圆形 |
| `anim_fade_panel` / `anim_fade_text` | True | 面板展开淡入 / 文案滚动动画开关 |
| `anim_duration` | 320 | 面板展开时长（100–500）与文字滚动时长（×0.7，120–400） |
| `theme_mode` | system | 主题（跟随系统/浅色/深色），只影响窗口类 UI |

---

## 附录 C：内置插件参考

| 插件 | 用到的 API | 说明 |
|---|---|---|
| `clock` | add_panel, set_interval | 最简面板插件 |
| `gaokao_countdown` | add_panel, add_settings_page, set_interval | 面板+设置页 |
| `weather` | add_subisland, add_settings_page, set_interval, on_start, request_refresh | 副岛自绘动画（priority 0 占位） |
| `audio` | add_island_extra, add_subisland, add_settings_page, set_interval, on_stop, is_in_class, get_data_dir, request_refresh | 最完整参考（priority 10、上课隐藏、子进程管理、daemon 线程汇合） |

---

## 附录 D：已知限制与注意事项

1. **无热重载**：插件改动（包括新增/删除）必须重启主程序生效。
2. **同进程**：插件死循环/阻塞会卡死整个程序；耗时操作务必异步化。
3. `subisland_show_weather()` 是保留接口，当前无效果。
4. 面板只能纯文本，不可自绘；想自绘请用副岛或主岛 extra。
5. 副岛/主岛 extra 是**独占**资源（priority 仲裁），请给自家插件选合理的 priority：占位类 0，临时重要信息（如媒体）10。
6. Windows 专属：主程序大量依赖 Win32（置顶、前台检测、SMTC 等），插件跨平台需自行判断 `sys.platform`。
7. 打包（PyInstaller）后插件目录在 exe 同级 `plugins/` 下，更新器升级时**保留** `settings/` 与 `plugins/`。
