# Class Daily Land · 项目结构梳理

> 面向"下一步要改哪里"的工程地图。与 `README.md`（用户视角）互补，这份是开发者视角。
> 梳理时间：2026-10-17 / 代码规模：Python 约 25.5k 行（根 22.8k + QML 桥 2.7k）+ QML 5.1k 行 + Web（遗留）5.1k 行

---

## 0. 一句话定位

Windows 桌面班级管理工具。核心是**三个自绘悬浮层**（灵动岛 / 副岛 / 下拉面板）+ **一个右侧信息窗**，
全部由 `ScheduleManager` 的课表状态驱动；设置中心已经外置成 QML + RinUI 的独立子项目；
插件系统通过"注册回调 → 每帧取 spec"的方式往上述浮层注入内容。

---

## 1. 技术栈与运行

| 项 | 值 |
|---|---|
| GUI | PySide6 6.11.2（原生 QWidget 自绘 + QML） |
| 设置界面 | QML + RinUI 0.4.4.1（Fluent Design，来自 Class Widgets 2 外壳） |
| 平台 | Windows 10/11（Win32 API 用于置顶、全屏检测、Mica） |
| 入口 | `python "Class Daily Land.py"` |
| 打包 | `pyinstaller -F -w --add-data "settings_qml;settings_qml" --collect-all RinUI` |
| 依赖声明 | **缺失**（无 requirements.txt / pyproject.toml） |
| 版本号 | 根 `config.json` → `version = 3.0`（README 写 4.3，不一致） |

---

## 2. 总体分层

```
┌──────────────────────────────────────────────────────────────────────┐
│ 入口  Class Daily Land.py                                             │
│ 单实例锁 → 建 QApplication → 同意协议 → 装服务 → 建窗口 → 装托盘 → 主循环 │
└───────────────────────────────┬──────────────────────────────────────┘
                                │
        ┌───────────────────────┴────────────────────────┐
        ▼                                                ▼
┌──────────────────┐                           ┌──────────────────────┐
│ 协调层            │                           │ 设置中心（可插拔）     │
│ controller.py    │◄──────────────────────────│ qml_bridge.py        │
│ AppController    │   apply_settings()        │  └→ settings_qml/    │
│ · 可见性统一开关   │   set_main_opacity()      │      (QML+RinUI)     │
│ · 设置按签名分级下发│                          │ 兜底 ↓               │
│ · 岛/副岛几何联动  │                           │ settings_dialog_v4   │
└────────┬─────────┘                           │  └→ v3 (控件库)      │
         │                                      └──────────────────────┘
         ▼
┌──────────────────────────────────────────────────────────────────────┐
│ UI 层（全部原生 Qt，深色自绘，不走主题模块）                             │
│  ClassBoardApp(gui)   DynamicIsland   SubIsland   PanelWindow  AppTray│
│  menu.py(值日/出勤/作业/课表/假期/周末 六个编辑对话框)                    │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ 读取状态 / 取插件 spec
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│ 服务层（纯 Python，无 Qt 窗口依赖）                                     │
│  ScheduleManager  StudentOnDuty  HomeworkManager  SettingsManager     │
│  PluginManager(+PluginAPI)  PluginMarket  PackageStore  PluginDeps    │
└───────────────────────────────┬──────────────────────────────────────┘
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│ 基础设施  paths · storage(原子写) · theme(色板/QSS) · utils ·          │
│           ui_common(对话框样式/触屏滚动) · single_instance ·           │
│           agreement · about · dev_guard · launch_updater              │
└──────────────────────────────────────────────────────────────────────┘
```

**两个要点：**

1. **`AppController` 是唯一的设置/可见性枢纽。** 设置页、托盘、右键菜单都只调它，不直接碰窗口。
2. **UI 层读写服务层对象，不持有副本。** 设置中心拿到的是主程序运行时的同一批实例（`services.py`），
   所以改完立刻生效，不需要重启。

---

## 3. 启动时序（顺序有依赖，别随意调）

```
1  acquire_single_instance_lock()        # OSError / None 两种失败路径
2  ensure_dirs()                          # settings/ plugins/ plugin-repo/
3  QApplication + setQuitOnLastWindowClosed(False)
4  install_touch_scrolling(app)           # 全局触屏滚动
5  agreement.check_agreement(CONFIG_DIR)  # 未同意直接 exit
6  SettingsManager(CONFIG_DIR)
7  theme.init(settings) → theme.apply_theme(app)
8  ScheduleManager(CONFIG_DIR)
9  AppController(settings)
10 定义 on_refresh / on_notify 两个回调（闭包引用窗口变量，调用时才解析）
11 PluginManager(PLUGINS_DIR, on_refresh, on_notify, settings)
12   └ set_schedule_status_provider(schedule.get_status)
13 ClassBoardApp / DynamicIsland / SubIsland 三窗口
14 controller.bind(window, island, sub_island)
15 island.set_geometry_callback(controller.on_island_geometry)
16 plugin_manager.set_subisland_control(...)   # 折叠/展开回调
17 window.show() / island.show() / island._pin_top()
18 controller.show_main/show_island/show_sub_island（读 settings 初值）
19 controller.set_main_opacity(...)
20 plugin_manager.set_disabled_ids(...) → load_all()   # 插件在这一步才执行
21 AppTray(...) → controller.bind(tray=tray) → tray.show()
22 app.exec()
```

**踩点提醒**：`load_all()` 必须晚于第 13 步。插件 `register()` 里可能会立刻 `notify()` 或
`request_refresh()`，那时三个窗口必须已存在。

---

## 4. 文件职责表

### 4.1 入口与基础设施

| 文件 | 职责 | 备注 |
|---|---|---|
| `Class Daily Land.py` | 唯一入口，130 行装配代码 | 文件名带空格，打包时注意引号 |
| `paths.py` | `APP_ROOT`（可写）/ `RESOURCE_ROOT`（只读，`sys._MEIPASS`） | 打包后图标丢失的根因就在这两者的区分 |
| `storage.py` | `read_json` / `write_json`（临时文件 + `os.replace`）/ `update_json`（合并） | 所有落盘都走这里 |
| `single_instance.py` | Windows 命名互斥体 | |
| `theme.py` | 双色板（LIGHT/DARK，各 30+ 键）+ 全局 QSS + 弱引用 watcher | 灵动岛不参与主题 |
| `ui_common.py` | 对话框统一 QSS、Mica、触屏滚动（`setup_touch_scroll` / `install_touch_scrolling`） | 三个设置实现都依赖它 |
| `utils.py` | 图标（含多尺寸补齐）、Windows 版本判断 | |
| `agreement.py` / `about.py` | 首启协议 / 版本号读取 | 版本取自根 `config.json` |
| `dev_guard.py` | 源码运行保护：扫描未打包主入口 | 所有更新入口共用同一拦截点 |
| `launch_updater.py` | 拉起 `Launcher.exe` / `launcher.py`（隐藏或可见），写退出标志文件 | 主程序**不含**下载逻辑 |

### 4.2 服务层

| 文件 | 核心对象 | 说明 |
|---|---|---|
| `settings_manager.py` | `SettingsManager`、`DEFAULTS` | **默认值的唯一事实来源**；含类型校验回退 |
| `schedule.py` | `ScheduleManager` | 1017 行，最复杂的服务：多课表 / 临时调课 / 假期 / 调休 / 周末作息 / 时间偏移 / 导入导出（JSON/CSV/文本多种格式解析）/ `get_status()` 状态机 |
| `StudentOnDuty.py` | `StudentOnDuty` | 按日期自动轮换，写 `name.json` + `config.json` |
| `homework.py` | `HomeworkManager` | 按科目分组 |
| `plugin_manager.py` | `PluginManager`、`PluginAPI`、`_DepsHub` | 899 行；加载 / 禁用 / 依赖安装 / 五类注入点收集 |
| `plugin_market.py` | `PluginMarket`、`parse_remote_list` | 三源索引（official/github/gitee）、后台线程、哈希校验 |
| `plugin_deps.py` | `PackageDB`、`ensure_requirements` | 888 行；清单解析 → 递归依赖 → 多镜像下载 → 逐文件 sha256 → 原子落盘 → wheel ABI 检查 |
| `package_store.py` | 包登记表 | `packages.json` 记录版本与 `used_by` |
| `builtin/`（包） | `registry.BUILTINS`、`PluginHost` 无关 | 内置功能：媒体播放 / 灾害预警。原先是 `plugins/` 里的插件，现已编进本体，用 `PluginManager.register_builtins()` 以 `PluginAPI` 注册（界面层与插件同构），数据在 `settings/builtin/<key>/` |

### 4.3 原生 UI 层

| 文件 | 规模 | 职责 |
|---|---|---|
| `dynamic_island.py` | **2093 行，最重** | 胶囊动画状态机：唤醒 / 滚动文字 / 倒计时环 / 提醒横幅 / 下拉面板编排 / 全屏与 Office 检测 / 情景测试。`paintEvent` 里全是手绘 |
| `menu.py` | 1349 行 | 9 个对话框：出勤、值日、作业、课程、课表管理、临时调课、假期、周末作息、导入预览 |
| `gui.py` | 570 行 | 右侧主窗（值日/应到实到/作业自动滚动）+ **设置中心的三层选择逻辑** `_make_settings_dialog` |
| `sub_island.py` | 340 行 | 主岛右侧副岛，可折叠、自动收起、位置跟随主岛几何 |
| `panel_window.py` | 221 行 | 独立面板窗口：高度 0 → 目标高度，带拖拽惯性 / 淡入淡出 |
| `tray_icon.py` | 93 行 | 托盘菜单与三项可见性同步 |
| `randoms.py` | 105 行 | 随机点名（带冷却） |
| `test_dialog.py` | 400 行 | 状态测试 + 情景演示（驱动真实灵动岛） |

### 4.4 设置中心（四套实现，只有两条在用）

```
活跃主路：gui._make_settings_dialog
   └→ qml_bridge.py            （薄壳，只负责定位 + 转发）
        └→ settings_qml/app/embed.py    （模态适配器 QmlSettingsDialog）
             └→ window.py               （RinUIWindow 装配 + 14 个上下文属性）
                  ├→ bridge.py          （Config / AppInfo / Folders / Plugins /
                  │                      Homework / ListStore / ScheduleInfo）
                  ├→ extra.py           （TimetableStore / StatusTester /
                  │                      MarketStore / PackageBridge / UpdaterBridge）
                  ├→ pluginpages.py     （插件设置页目录：list / hasPageFor / entry_for）
                  ├→ pluginhome.py      （**内嵌宿主**：插件原生 QWidget → 设置窗口内容区）
                  ├→ schema.py          （字段/类型/范围，QML 侧的校验来源）
                  ├→ store.py           （原子写 + 类型合并）
                  └→ paths.py           （给 QML 的绝对 file:// URL）
        └→ settings_qml/qml/Settings.qml + pages/*.qml（17 页）+ components/*.qml

            导航只有 9 个顶层项，**没有可展开的子项**（照 Win11：子页从右侧页面
            的入口行进）。分支结构：
              课表与提醒 → 课表管理 / 假期与调休 / 周末作息 / 值日生名单 / 状态测试
              插件       → 插件管理（列出已装插件，点一行载入它的设置页）
                           / 插件市场（→ 其中再进 依赖包管理）

            「作业」「周末作息」两页是主窗口右键菜单里那两个原生对话框
            （menu.HomeworkEditor / menu.WeekendScheduleDialog）的移植，
            字段与行为逐项对齐；见 §4.6。

### 4.6 作业 / 周末作息：与原生的对应关系

主窗口右键菜单里有两个原生对话框，QML 侧各有一页承接同一份数据：

| 原生（menu.py） | QML 页 | 数据 |
|---|---|---|
| `HomeworkEditor` | `pages/Homework.qml` | `settings/homework.json`（`HomeworkManager`） |
| `WeekendScheduleDialog` | `pages/Weekend.qml` | `schedule.json` 的 `weekend`（`ScheduleManager`） |

对齐的要点：

* 作业：科目 + 提交日期 + **多行**内容 → 添加；按科目分组、组标题带日期、
  每组「整组清除」、每条「修改 / 删除」。
* 周末作息：上午分界（HH:MM）+ 4 列表格（节次 / 开始 / 结束 / 课程）。
  上午那几节取自**当前课表**、只读灰底；下午节次可增删改；课程与行一一对应。
* **改完必须通知宿主**：原生每个对话框自己调 `app.update_display()` /
  `_notify_island()`；QML 侧拿不到 app 引用，走 `Services.on_data_changed`
  （embed.py 里接到 `update_display` 与 `_notify_island`）。
  少了这一环，就会出现「设置里加完作业，主窗口还写着暂无作业」——
  数据其实已经落盘，只是没人刷新，看着像功能坏了。

### 4.7 右键菜单改走设置页（可退回原生）

`gui.py:_show_menu()` 里那几项默认调 `_open_settings_page(标题)` →
`open_settings(start_page=...)` → `qml_bridge.create_dialog(start_page=...)`
→ `SettingsApp(page=...)` → `Paths.setStartPage()`，NavigationView **首次 push**
就直接落在目标页（不是"先开首页再跳"，那条路有竞态，见 §4.4 的说明）。

开关：`right_click_native_menu`（默认 `False`）。

| 右键项 | 默认行为 | 开关打开后 |
|---|---|---|
| 编辑作业 | 设置中心 → 作业 | `menu.HomeworkEditor` 原生对话框 |
| 课表管理 | 设置中心 → 课表管理 | `menu.TimetableManagerDialog` |
| 临时调课 | 设置中心 → 课表管理（临时调课区块） | `menu.TempAdjustDialog` |
| 假期与调休 | 设置中心 → 假期与调休 | `menu.HolidayDialog` |
| 周末作息 | 设置中心 → 周末作息 | `menu.WeekendScheduleDialog` |

「出勤人数」「随机点名」没有对应的设置页，两种模式下都还是原生窗口。
键写在 `settings_manager.DEFAULTS` 里（老配置加载时自动补默认值），
schema 里也有同名 `Field`，所以设置页那个开关是真的会落盘的。

**插件设置页怎么"放进"窗口**（`app/pluginhome.py`，试错记录都在模块说明里）：
插件返回的是原生 QWidget。`WindowContainer` 嵌得住但**定位不可靠**（窗口挪
160px 只跟了 8px）；渲染成图片再转发鼠标又撑不住输入框与每秒刷新的插件页。
最终做法是「无边框工具窗 + 精确喂坐标」：QML 把内容区的**场景坐标**交给
`PluginHost.placeScene()`，Python 加上窗口位置换成屏幕坐标后 `setGeometry`，
窗口位移/缩放由订阅 `xChanged/yChanged` 驱动 —— 实测逐像素吻合。

兜底路：settings_dialog_v4.py（1737 行）
   └→ settings_dialog_v3.py（2916 行，**不是死代码**，被当控件库 import）
        └→ settings_widgets.py（StaggerPlayer 等自绘控件）
   └→ market_page.py / package_page.py（461 + 304 行，延迟 import）
```

**QML 侧三个易踩的坑（代码里都有长注释）：**

1. 上下文属性必须在 `engine.load()` **之前**挂好，且必须自己持引用（否则被 GC，QML 读到 null）。
2. 上下文属性名**不能与任何 .qml 文件名相同** —— QML 本地类型优先，页面会静默拿到 undefined。
   所以桥叫 `TimetableStore` 而不是 `Timetable`。`tools/selftest.py` 有一组检查专门盯这个。
3. 动态创建的页面看不到 `Settings.qml` 里的 `id`，所以 `settingsWindow` 额外挂了一份上下文属性。

### 4.5 未接线的遗留（可删，约 5100 行 + `ui/` 5070 行）

| 文件 | 状态 |
|---|---|
| `settings_dialog.py`（902） | 未被任何文件 import；只被 `settings_rows.py` 服务 |
| `settings_rows.py`（247） | 只被上面那个 v1 用 |
| `settings_dialog_v2.py`（2209） | 未被 import |
| `web_settings.py`（1293） | 已被移出回退链；只有 `web_settings_selftest.py` 引用 |
| `web_settings_selftest.py`（481） | 自检脚本，可保留 |
| `ui/`（5070 行 JS/CSS） | Web 版界面本体，与 .NET 版共用；当前无人加载 |

### 4.6 数据与文档

| 路径 | 说明 |
|---|---|
| `README.md` | 用户向文档（部分内容已过时，见 §7） |
| `PLUGIN_API.md` | 63 KB，插件开发契约，分 17 章 |
| `icon.ico` | 程序图标 |
| `plugins/<id>/` | 已装插件（当前 2 个：`audio`、`disaster-alert`） |
| `plugins/packages/` | 第三方依赖包落盘位置（当前空） |
| `settings/` | 运行时数据（`.gitignore` 已忽略） |
| `settings_qml/data/` | **QML 独立运行的演示数据根**（`CDL_DATA_ROOT` 默认值），不是真实配置 |
| `settings_qml/tools/` | 10 个自检/探针脚本，见 §8 |
| `settings_qml/_shots/`、`_transition/` | 截图产物，可清理 |

---

## 5. 三条关键数据流

### 5.1 设置变更（最常改的链路）

```
QML 控件 / 原生控件
   → Config.set(key, value)            # schema 校验 + 范围夹取
   → settings_manager.set + save       # 落盘 settings.json
   → controller.apply_settings()
        ├ 计算两种签名（字段前缀 island_/sub_island_、三个可见性开关）
        ├ 签名没变 → 跳过重活（防止拖滑块时整窗闪）
        ├ window.apply_main_settings()  # 内部再按"内容签名"决定是否重建作业列表
        ├ island.apply_settings() / sub_island.apply_settings()
        ├ show_main / show_island / show_sub_island
        ├ set_main_opacity
        └ notify_island_dirty() + tray.sync_state()
```

> **性能设计要点**：`apply_settings` 分三级下发（island 签名 / 可见性 / main 内容签名）。
> 新增设置项只要命名带 `island_` 前缀就会自动纳入签名，不用改 `controller.py`。
> 两个换主题相关的坑写在 `settings_qml` 之外：`main_apply_settings` 里把 `theme.is_dark()` 也算进内容签名。

### 5.2 灵动岛一次刷新

```
DynamicIsland._refresh（定时）
  → schedule_manager.get_status(now, advance, offset)    # 返回 status/course/until_sec/...
  → _collect_specs()                                     # 课表 spec + 插件 spec 合并
       ├ _make_schedule_spec()                           # 主岛
       ├ plugin_manager.get_island_text()                # 文本后缀
       ├ plugin_manager.get_island_extra()               # 右侧加长片段
       ├ plugin_manager.get_island_banner()              # 紧急警报条
       └ plugin_manager.get_panel_specs()                # 下拉面板
  → 计算 _layout() → _animate_to() → paintEvent 手绘
  → _notify_geometry() → controller.on_island_geometry() → sub_island.reposition()
```

### 5.3 插件生命周期

```
PluginManager.load_all()
  → 遍历 plugins/*/ (跳过 disabled_plugins)
  → 解析 plugin.json → importlib 加载 entry → register(api)
  → api 把回调**注册成函数**，不立即求值
  → 宿主每帧/每事件调用 fn() 拿返回值（因此 fn 必须轻量，PLUGIN_API §17 有性能要求）
  → 缺依赖时 _DepsHub 后台装包，装完 refresh_dep_paths() 再重载
```

---

## 6. 数据与配置

| 文件 | 写入方 | 内容 |
|---|---|---|
| `config.json`（根） | 手工 / Launcher | `version`(3.0) / `version_url` / `exe_name` |
| `settings/settings.json` | `SettingsManager` | 30 个设置项，见 `DEFAULTS` |
| `settings/schedule.json` | `ScheduleManager` | 多课表 + 假期 + 调休 + 周末 + 偏移 |
| `settings/name.json` | `StudentOnDuty` | 值日生名单 |
| `settings/homework.json` | `HomeworkManager` | 作业列表 |
| `settings/config.json` | **两个 owner** | `current_index`/`last_date`（值日生）+ `should`/`actual`（应到实到） |
| `settings/agreement.json` | `agreement` | 协议同意状态 |
| `settings/plugin-repo/` | `PluginMarket` | 市场索引缓存（离线可用） |
| `plugins/packages/packages.json` | `PackageDB` | 依赖包登记表 + `used_by` |

**注意**：`settings/config.json` 一个文件两个写入者。两者都用 `update_json`（合并写），
所以不会互相覆盖，但语义混在一起 —— 后续要拆的话，把应到/实到挪到 `homework.json` 或独立的 `attendance.json` 更清晰。

---

## 7. 现状体检

### 该修的不一致

| 问题 | 位置 | 影响 |
|---|---|---|
| README 写 v4.3，实际 `version = 3.0` | 根 `config.json` vs `README.md` | 关于页显示 3.0 |
| README 说 `settings/config.json` 存"版本号、更新地址" | README §配置文件 | 实际存值日生状态，会误导后来者 |
| README 目录树没有 `settings_qml/`、`ui/`、`ARCHITECTURE.md` | README §目录结构 | 新人找不到设置中心在哪 |
| 版本号读取依赖"根 config.json 必须有 version 字段" | `about.py` | 缺失时显示"版本成谜" |

### 结构性隐患

1. **跨模块访问私有成员**：`Class Daily Land.py` 调 `island._pin_top()`；
   `controller.on_island_geometry` 读 `island._state`。改成公开方法（`pin_top()` / `state` 属性）成本很低。
2. **没有版本控制**：目录不是 git 仓库（无 `.git`）。改动前建议先 `git init`，否则无法回退。
3. **默认值有两份**：`settings_manager.DEFAULTS`（权威）与 `settings_qml/app/schema.py`（含范围夹取）。
   加设置项必须两处同步，否则 QML 侧 `Config.set` 会拒绝该键（`isManaged()` 返回 False）。
4. **调试靠 print**：全项目无 `logging`，启动/插件/设置失败信息都打在控制台，打包后（`-w`）看不到。

### 可清理

- `__pycache__/` 4 处（根、settings_qml/app、两个插件）
- `settings_qml/_transition/`、`_shots/`：调试截图，几十个文件
- 遗留设置实现约 5100 行 Python + `ui/` 5070 行前端，确认不要了就删

---

## 8. 自检与验证命令

```bash
# QML 设置中心四组自检（Python/schema/QML 静态与编译/上下文属性撞名）
python settings_qml/tools/selftest.py

# 插件设置页端到端（注册 → 桥列出 → 建出可内嵌的原生页）
python settings_qml/tools/plugin_e2e.py
# 内嵌是否真的落在内容区（位置逐像素对、挪窗口跟着走、页面非空白）
python settings_qml/tools/embed_probe.py

# 界面行为：导航强调条会不会跟着高亮项滑动、四种转场方向对不对
python settings_qml/tools/ui_probe.py

# 截图核对界面（不要用 offscreen：software 后端不栅格化文字）
python settings_qml/tools/shot.py "插件管理" settings_qml/_shots/out.png
CDL_SHOT_EMBEDDED=1 python settings_qml/tools/shot.py "插件管理" out.png  # 带真实插件管理器

# 作业页 / 周末作息页的**页面逻辑**（填表 → 添加 → 修改 → 整组清除；加下午节 → 保存）
python settings_qml/tools/page_probe.py

# 周末作息端到端（QML 保存 → 落盘 → 周六 get_status 真读得到课）
python settings_qml/tools/qml_e2e.py

# 周末数据链路（读 → 存 → 影响 courses_for / get_status，含非法输入被拒）
python settings_qml/tools/weekend_check.py

# 接入口装配：改作业 / 周末后，宿主 app.update_display / _notify_island 有没有被叫到
python settings_qml/tools/embed_data_probe.py

# 页面能不能滚（内容比视口高时滚轮要真的动 contentY）
python settings_qml/tools/interact_probe.py

# 页面转场 / 位移（三个视角）
python settings_qml/tools/transition_check.py
python settings_qml/tools/transition_verify.py
python settings_qml/tools/transition_shot.py

# Web 版桥的回归网（文件仍在）
python web_settings_selftest.py

# 源码运行保护单独排查
python dev_guard.py <目录>

# 前端静态/渲染测试（需 npm i jsdom）
cd ui && npm test
```

> QML 工具统一把数据根指向临时目录（`CDL_DATA_ROOT`），不碰真实 `settings/`。
> 离屏渲染用 `QT_QPA_PLATFORM=offscreen` + `QT_QUICK_BACKEND=software`。

---

## 9. 下一步：按目标找入口

| 想做的事 | 从哪下手 |
|---|---|
| **加一个设置项** | ① `settings_manager.py:DEFAULTS` ② `settings_qml/app/schema.py:FIELDS`（含范围）③ 对应 `settings_qml/qml/pages/*.qml` 加控件 ④ `controller.py:apply_settings` 签名自动覆盖（前缀 `island_` 即可） |
| **改灵动岛外观** | `dynamic_island.py`：尺寸 `_layout` / `_compact_width`，配色 `_paint_compact` / `_paint_countdown_fill`，文字 `_text_for` |
| **改课表逻辑/状态机** | `schedule.py:get_status`（415 行起的 `ScheduleManager`）；状态字典字段见 README §灵动岛状态字典 |
| **加编辑对话框** | `menu.py`（现有 9 个可当模板）+ `gui.py:_show_menu` 挂右键项 |
| **加插件注入点** | `plugin_manager.py:PluginAPI`（注册侧）+ `get_island_*`（收集侧）+ 消费侧 `dynamic_island._collect_specs` + `PLUGIN_API.md` 同步 |
| **改设置中心界面** | `settings_qml/qml/pages/`，数据走 `bridge.py` 的对应桥对象；改完跑 `tools/selftest.py` |
| **改兜底设置窗** | `settings_dialog_v4.py`（注意它 import v3 的控件库，改 v3 会同时影响） |
| **换主题色/加主题** | `theme.py:PALETTES`（LIGHT/DARK 两份要同键） |
| **做安装包** | 缺 `.spec`、`version.json`、`LICENSE`；`README` 有一行 pyinstaller 命令可作起点 |
| **清理仓库** | 删 `settings_dialog.py` / `settings_dialog_v2.py` / `settings_rows.py` / `web_settings.py` / `ui/`；清 `__pycache__` 与 `_transition` |
| **接手前必做** | `git init` + 首次提交 + 补 `requirements.txt`（`PySide6>=6.11`、`RinUI>=0.4.4`） |

---

## 10. 一页速查

```
改界面 → gui.py / dynamic_island.py / sub_island.py / panel_window.py
改设置 → settings_qml/qml/pages/ + settings_qml/app/bridge.py
改逻辑 → schedule.py / plugin_manager.py
改主题 → theme.py
加功能 → 服务层写 Python，UI 层只做展示，中间过 controller
```

**铁律**：
1. 落盘只用 `storage.py`，不要自己 `open(..., 'w')`。
2. 设置变更只走 `controller.apply_settings()`，不要各窗口自己响应。
3. 插件回调 `fn()` 必须轻量 —— 它可能在每帧被调用。
4. 新增 QML 上下文属性，名字避开所有 `.qml` 文件名，并在 `CONTEXT_PROPERTIES` 里登记。
