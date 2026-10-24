# Class Daily Land（班级日常）

> 一个面向教室大屏 / 班级一体机的 Windows 桌面班级日常管理工具：主面板、灵动岛、副岛、课表提醒、值日与作业管理，以及可扩展的插件生态。

当前版本：**4.3** · 运行平台：**Windows 10 / 11** · UI 框架：**PySide6（Qt 6）**

---

## 项目简介

Class Daily Land 将班级里每天都要用到的信息集中到桌面：

- 右侧常驻的**班级主面板**显示值日生、出勤人数和作业，并支持自动滚动；
- 屏幕顶部中央的**灵动岛**根据课表自动切换“下节课 / 上课中 / 倒计时 / 假期”等状态；
- **副岛**用于展示插件提供的天气、媒体、倒计时等轻量信息；
- 设置中心可以管理课表、假期调休、周末作息、作业、值日名单、主题和插件。

项目采用“核心程序 + 插件”的结构：核心负责课表、UI 和系统集成，插件通过 `PluginAPI` 向灵动岛、下拉面板、副岛和设置页注入功能。插件可以从插件市场安装，也可以以 `.cblplugin` 压缩包离线分发。

软件只把数据保存在本地，不依赖账号或云服务。

---

## 功能特性

### 主面板

- 无边框、置顶、停靠屏幕右侧，宽度和字体大小可调。
- 显示今日值日生、应到 / 实到人数、按科目分组的作业。
- 作业内容超出窗口时自动上下滚动；支持调节滚动间隔、步长和到底停留时间。
- 手指 / 鼠标拖动后可暂时接管自动滚动。
- 窗口透明度、渐显动画、字号、宽度比例均可在设置中调整。
- 右键菜单可快速修改值日生、出勤人数、作业、课表、假期和设置。

### 灵动岛

- 常驻屏幕顶部中央，胶囊形态，无边框且不抢占焦点。
- 根据课表状态显示：
  - 下节课名称与距上课时间；
  - 当前课程与剩余时间；
  - 今日无课 / 今日课程已结束；
  - 假期状态与假期名称。
- 上课前进入蓝色倒计时进度条，倒计时时长可设置。
- 上课时弹出“上课了！”提醒；放假前最后一个上学日最后一节课结束后弹出“放假啦”提醒。
- 文字溢出时使用跑马灯滚动，课程剩余分钟变化时使用滚动切换动画。
- 点击胶囊可下拉面板，展示今日课表和插件提供的面板；3 秒后自动收回，也支持触屏拖动滚动和滚轮切换。
- 全屏应用时自动隐藏；WPS / Microsoft Office 前台时退出上课倒计时，避免遮挡演示或办公界面。
- 插件可注册“紧急警报条”（如地震预警）。警报条会独占显示、顶掉课表和倒计时，并在此期间隐藏副岛。

### 副岛

- 位于主岛右侧，与主岛组合成类似“灵动岛 + 实时活动”的布局。
- 内容由插件通过 `add_subisland` 提供，支持文本、Emoji 图标或自定义绘制。
- 可展开 / 收起，也可设置为默认收成圆形。
- 无内容时自动收起，超时时间可配置。
- 点击副岛会触发插件注册的点击回调，并切换展开状态。

### 课表与提醒

- 支持多张课表：新建、复制、重命名、删除、切换和恢复默认。
- 课表编辑器支持自定义节次名称、开始 / 结束时间，以及周一至周日的课程。
- 支持 JSON 单表 / 多表导入导出，以及 CSV 导入导出（兼容 Excel、UTF-8 BOM、GBK）。
- 完整备份会包含全部课表、假期、调休、周末作息、提前提醒和时间偏移。
- 支持假期区间与调休日（把某天按指定星期上课）。
- 支持单独的周末作息：上午沿用工作日节次，下午单独配置节次和课程。
- 支持临时调课：只为今天替换课程。
- 支持“提前提醒”（整体提前进入上课状态，下课时间不变）和“时间偏移”（整体提前或延后）。
- 状态测试页可以在不等待真实时间的情况下演示完整的一节课状态变化。

### 班级事务

- **值日生**：按名单轮换，每个自然日自动切到下一位，也可手动上一位 / 下一位。
- **出勤**：记录应到、实到人数。
- **作业**：按科目分组，支持日期、增删改和批量管理。
- **随机点名**：读取 `name.json` 或任意 JSON 名单，最近点过的人不会立即重复（冷却 10 人）。

### 设置中心

- Windows 11 风格设置窗口：左侧导航、二级页面下钻、返回动画和设置搜索。
- 页面包括：通用、外观、灵动岛、课表与提醒、作业、插件、高级、关于。
- 课表管理、周末作息、假期调休、值日名单、状态测试、作业编辑器均内嵌在设置窗口中。
- 修改设置后立即保存并应用，不需要“确定”按钮。
- 支持浅色 / 深色 / 跟随系统三种主题。
- Windows 11 支持云母（Mica）材质、圆角和深色标题栏；Windows 10 使用自绘窗框。

### 插件生态

- 插件是普通 Python 模块，通过 `register(api)` 注册能力。
- 可向主岛文本、主岛右侧片段、紧急警报条、下拉面板、副岛和设置中心扩展内容。
- 支持插件设置页及三级子页面，图标可使用内置矢量图标、Emoji 或自定义图片。
- 插件市场支持官方服务器、GitHub、Gitee 三种索引来源。
- 安装时校验 SHA-256；支持版本比较、单独更新、批量更新、启用 / 禁用和卸载。
- 下载支持镜像回退、失败重试和本地索引缓存。
- 插件可以声明第三方依赖，宿主会自动下载并解包到 `plugins/packages/`，再补加载插件。

### 系统集成

- 系统托盘常驻菜单：显示 / 隐藏主面板、灵动岛、副岛，假期与周末作息，设置，安装插件，退出。
- 单实例互斥锁，避免重复启动多个程序。
- 全局触屏惯性滚动适配。
- 独立更新器：启动时静默检查更新，也可以在“关于”中手动检查。
- 源码运行保护：检测到未打包的主入口源码时跳过自动更新，避免发布版覆盖本地代码。

---

## 技术栈

| 项目 | 说明 |
| --- | --- |
| 语言 | Python 3.10+（当前开发环境为 Python 3.13.5） |
| GUI | PySide6 / Qt 6 |
| 平台 | Windows 10 / 11；部分功能依赖 Win32 API |
| Win32 集成 | `ctypes` 调用 DWM、SetWindowPos、前台窗口检测、单实例互斥体等 |
| 数据存储 | 本地 JSON 文件；写入采用临时文件 + `os.replace` 原子替换 |
| 更新 | 外部 `Launcher.exe` / `Launcher_hide.exe`，通过 `config.json` 的版本地址检查 |
| 插件 | 进程内 Python 模块，ZIP 包分发（`.cblplugin` / `.cbplugin`） |

运行时唯一需要手动安装的第三方 Python 依赖是 **PySide6**。其余能力使用 Python 标准库和 Windows 系统 API 实现。

---

## 快速开始

### 环境要求

- Windows 10 或 Windows 11
- Python 3.10 及以上
- 可联网（仅更新、插件市场和插件依赖安装需要）

### 从源码运行

```powershell
cd "E:\11111\Code\Python\Class Daily Land\app\app"

python -m pip install PySide6

python "Class Daily Land.py"
```

首次启动会弹出用户协议；同意后会在程序目录下自动创建 `settings/` 和 `plugins/`。

> 入口文件名包含空格，PowerShell / CMD 中请保留引号。
>
> 程序按“源码目录”定位资源与数据，直接运行 `Class Daily Land.py` 即可，不要求把 `app\app` 加入 `PYTHONPATH`。

### 使用打包版

打包版通常以 `Launcher.exe` 启动，目录结构类似：

```text
app/
├─ Launcher.exe
├─ Launcher_hide.exe
└─ app/
   ├─ Class Daily Land.exe
   ├─ _internal/          # PySide6、Python 运行时和资源
   └─ settings/           # 用户数据
```

`Launcher_hide.exe` 用于启动时静默检查更新，`Launcher.exe` 用于显示更新窗口。

### 第一次使用建议

1. 打开设置 → **课表与提醒**，确认节次时间和课程。
2. 在 **值日生名单** 中录入学生姓名。
3. 在 **作业** 页面录入当天作业。
4. 根据班级情况设置 **假期与调休**、**周末作息**。
5. 在 **灵动岛** 页面调整倒计时时长、提醒条宽度和副岛行为。
6. 需要扩展功能时，进入 **插件 → 插件市场** 安装插件。

首次运行会生成示例数据：默认 8 节课、周一至周五示例课表、应到 40 人，以及 `001` ~ `005` 五位值日生。可以直接修改或导入自己的课表。

---

## 项目结构

```text
app/app/
├─ Class Daily Land.py       # 唯一入口：单实例、初始化、组装各组件、托盘与事件循环
├─ config.json               # 版本元数据（version / version_url / exe_name）
├─ icon.ico                  # 窗口、托盘和应用图标
├─ README.md
│
├─ Core/                     # 核心逻辑
│  ├─ __init__.py
│  ├─ schedule.py            # 课表数据、状态计算、导入导出、假期 / 调休 / 周末作息
│  ├─ StudentOnDuty.py       # 值日生轮换
│  ├─ homework.py            # 作业数据管理
│  ├─ randoms.py             # 随机点名
│  ├─ controller.py          # 组件绑定、可见性、透明度、几何联动与全局刷新
│  ├─ storage.py             # JSON 原子读写
│  ├─ paths.py               # 数据目录、资源目录、图标和插件路径
│  ├─ single_instance.py     # Windows 单实例互斥锁
│  └─ dev_guard.py           # 源码运行检测，防止更新覆盖源码
│
├─ UI/                       # 界面
│  ├─ __init__.py
│  ├─ gui.py                 # 班级主面板
│  ├─ dynamic_island.py      # 灵动岛：状态机、倒计时、提醒、下拉面板、前台检测
│  ├─ sub_island.py          # 副岛：插件内容展示与展开 / 收起
│  ├─ panel_window.py        # 灵动岛下拉面板窗口与惯性滚动
│  ├─ menu.py                # 课表、值日、作业、出勤、假期、周末作息等编辑器
│  ├─ test_dialog.py         # 手动状态测试 / 灵动岛预览（不是自动化测试）
│  ├─ theme.py               # 浅色 / 深色 / 跟随系统主题
│  ├─ ui_common.py           # DWM / 云母、圆角、触屏滚动、对话框样式
│  ├─ agreement.py           # 首次启动用户协议
│  ├─ tray_icon.py           # 系统托盘菜单
│  └─ Settings/              # 设置中心及其依赖
│     ├─ __init__.py
│     ├─ settings_dialog_v4.py  # 当前设置中心（主流程使用）
│     ├─ settings_dialog_v3.py  # 上一代设置窗口 + v4 复用的 Fluent 控件
│     ├─ settings_manager.py    # 设置默认值、类型校验与读写
│     ├─ settings_widgets.py    # 开关、分段控件、导航、卡片、动画等通用控件
│     ├─ settings_rows.py       # 设置行模型与行控件（历史实现仍可参考）
│     ├─ settings_dialog_v2.py  # 历史版本设置窗口
│     └─ settings_dialog.py     # 最早版本设置窗口
│
├─ Plugins/                  # 插件生态
│  ├─ __init__.py
│  ├─ plugin_manager.py      # 插件发现、加载、API、生命周期、依赖安装
│  ├─ plugin_market.py       # 插件市场：索引、下载、校验、安装、更新、卸载
│  ├─ market_page.py         # 插件市场 UI
│  ├─ package_store.py       # 第三方依赖包仓库逻辑
│  ├─ package_page.py        # 第三方包管理 UI
│  └─ plugin_deps.py         # 依赖清单解析、下载、校验、解包与登记
│
├─ Utils/                    # 工具与更新
│  ├─ __init__.py
│  ├─ utils.py               # 应用图标、系统版本判断等工具
│  ├─ about.py               # 版本读取与关于信息
│  └─ launch_updater.py      # 调用外部更新器与退出信号
│
├─ settings/                 # 运行时生成：用户数据
├─ plugins/                  # 运行时生成：插件与第三方依赖
└─ temp/                     # 运行时生成：安装包临时下载目录
```

> Windows 文件系统不区分大小写，`Plugins/`（代码包）与 `plugins/`（数据目录）会合并成同一个目录。插件管理器已跳过 `packages/`、`__pycache__/` 等非插件目录；在大小写敏感的系统上两者仍是独立目录。

### 核心模块职责

| 模块 | 职责 |
| --- | --- |
| `Class Daily Land.py` | 获取单实例锁、创建 `QApplication`、初始化设置 / 主题 / 课表 / 插件 / 托盘，进入事件循环 |
| `UI/gui.py` | 主面板布局、作业列表、自动滚动、右键菜单、设置入口、启动更新检查 |
| `UI/dynamic_island.py` | 灵动岛全部状态与绘制；每秒刷新课表状态，400ms 检测前台窗口 |
| `UI/sub_island.py` | 副岛内容协议与绘制，跟随主岛几何位置 |
| `Core/controller.py` | 各窗口之间的“总线”：可见性、透明度、刷新、几何联动 |
| `Core/schedule.py` | 课程状态机与课表数据模型，是灵动岛和提醒功能的数据源 |
| `UI/menu.py` | 所有日常编辑窗口，同时被设置中心以 `embedded=True` 复用 |
| `UI/Settings/settings_dialog_v4.py` | 设置中心页面、搜索、二级导航、内嵌编辑器、插件设置页 |
| `Plugins/plugin_manager.py` | 插件加载、回调注册、`PluginAPI`、依赖补装 |
| `Plugins/plugin_market.py` | 市场索引同步、镜像下载、SHA-256 校验、安装 / 更新 / 卸载 |
| `Core/paths.py` | 区分“只读资源目录”和“可写数据目录”，兼容 PyInstaller `_MEIPASS` |

> `UI/Settings/settings_dialog_v4.py` 复用了同目录下 `settings_dialog_v3.py` 的整套 Fluent 控件；`settings_dialog.py` 与 `settings_dialog_v2.py` 属于历史版本，当前主流程未引用。保留它们是为了方便回退和参考。

---

## 架构与启动流程

```text
Class Daily Land.py
│
├─ single_instance        Windows 互斥体，保证只运行一个实例
├─ SettingsManager        settings/settings.json
├─ theme                  浅色 / 深色 / 跟随系统
├─ ScheduleManager        settings/schedule.json
├─ AppController          组件之间的信号与联动
├─ PluginManager          plugins/ 下的插件
│
├─ ClassBoardApp          主面板
├─ DynamicIsland          顶部灵动岛
├─ SubIsland              主岛右侧副岛
└─ AppTray                系统托盘
        │
        └─ plugins/*        通过 PluginAPI 注入内容
```

启动顺序：

1. 获取单实例锁；已有实例时直接退出。
2. 创建 `settings/`、`plugins/`、`plugins/packages/` 等目录。
3. 启用高 DPI 缩放和全局触屏滚动。
4. 检查用户协议。
5. 加载设置、主题、课表和控制器。
6. 创建插件管理器，先安装 `plugins/*.cblplugin` 压缩包，再加载插件目录。
7. 创建主面板、灵动岛、副岛和托盘，绑定彼此引用。
8. 根据设置恢复各窗口的显示状态和透明度。
9. 启动 1 秒课表刷新、1 秒置顶校正、400ms 前台窗口检测和 500ms 退出信号轮询。
10. 进入 Qt 事件循环；关闭最后一个窗口不会退出程序，需从托盘或菜单退出。

数据写入使用 `storage.write_json()`：先写同目录临时文件，再用 `os.replace()` 替换目标文件，降低程序崩溃或断电导致 JSON 损坏的概率。

---

## 数据与配置

### 目录位置

源码运行时，数据目录是 `app/app/settings/`；打包后是 exe 所在目录下的 `settings/`。

| 路径 | 内容 |
| --- | --- |
| `settings/settings.json` | 全部应用设置（主题、窗口、灵动岛、动画、插件市场来源等） |
| `settings/schedule.json` | 多张课表、当前课表、假期、调休、周末作息、临时调课、提前分钟、时间偏移 |
| `settings/homework.json` | 作业列表 |
| `settings/name.json` | 值日生 / 随机点名名单 |
| `settings/config.json` | 主面板出勤人数、当前值日索引、上次轮换日期 |
| `settings/agreement.json` | 用户协议是否已同意 |
| `settings/plugin-repo/` | 插件市场索引缓存（`_remote_list.json`、`_github_list.json`、`_gitee_list.json`） |
| `plugins/<插件>/` | 插件文件；插件的 `data.json` 也保存在这里 |
| `plugins/packages/` | 插件第三方依赖包，登记表为 `packages.json` |
| `plugins/*.cblplugin` | 待安装 / 已分发的插件压缩包，启动时自动解压安装 |
| `config.json`（程序根目录） | **版本元数据，不是用户配置**；包含 `version`、`version_url`、`exe_name` |

> 注意区分两个 `config.json`：
> - 程序根目录的 `config.json` 记录版本号和更新地址；
> - `settings/config.json` 记录出勤人数和值日轮换状态。

### 常用设置项

| 设置键 | 默认值 | 说明 |
| --- | --- | --- |
| `theme_mode` | `system` | `system` / `light` / `dark` |
| `main_width_ratio` | `0.25` | 主面板宽度占屏幕比例 |
| `main_font_size` | `14` | 主面板正文字号 |
| `main_auto_scroll` | `true` | 作业自动滚动 |
| `main_opacity` | `1.0` | 主面板透明度 |
| `show_main_window` | `true` | 显示主面板 |
| `show_island` | `true` | 显示灵动岛 |
| `show_sub_island` | `true` | 显示副岛 |
| `island_top_margin` | `6` | 灵动岛距屏幕顶部距离（px） |
| `island_countdown_sec` | `60` | 上课前倒计时时长（秒） |
| `island_hide_on_fullscreen` | `true` | 全屏时隐藏灵动岛 |
| `sub_island_auto_collapse_sec` | `5` | 副岛无内容时自动收起时间；`0` 表示不收起 |
| `anim_duration` | `320` | 通用动画时长（ms） |
| `check_update_on_start` | `true` | 启动时静默检查更新 |
| `block_update_on_source` | `true` | 源码运行时阻止自动更新 |
| `market_source` | `official` | 插件市场索引来源：`official` / `github` / `gitee` |
| `packages_source` | `gitee` | 插件依赖下载源：`gitee` / `github` |
| `disabled_plugins` | `[]` | 被禁用的插件目录名列表 |

`advance_minutes`、`time_offset_seconds` 属于课表数据，保存在 `settings/schedule.json`，由设置页的“课表与提醒”页面修改。

### 备份与迁移

- 日常备份：复制整个 `settings/` 目录即可保留设置、课表、作业和名单。
- 课表备份：在“课表管理”中选择“导出完整备份”，会包含全部课表和假期 / 周末设置。
- 迁移插件：复制 `plugins/` 目录，或重新安装 `.cblplugin` 包。
- 升级程序时保留 `settings/` 和 `plugins/`，用户数据不会被覆盖。

---

## 灵动岛状态说明

| 状态 | 触发条件 | 表现 |
| --- | --- | --- |
| `hidden` | 启动、全屏应用、手动隐藏 | 收起到屏幕上边缘外 |
| `mini` | 从隐藏状态唤醒 | 先显示小胶囊，再展开 |
| `compact` | 正常显示课表状态或插件文本 | 240 × 40 胶囊，显示课程 / 假期 / 插件信息 |
| `countdown` | 距上课时间进入倒计时范围 | 宽度扩展，蓝色进度条随剩余时间收缩 |
| `alert` | 上课、放假、插件提醒 | 短暂显示提醒文字 |
| `banner` | 插件注册紧急警报条 | 独占长条，覆盖课表与倒计时，副岛隐藏 |

前台窗口检测逻辑：

- 当前台窗口全屏时，默认隐藏灵动岛（可在设置中关闭）。
- WPS / Microsoft Office 前台时，不进入上课倒计时，避免演示或办公时被遮挡。
- 紧急警报条激活期间，即使全屏或 Office 前台也会强制显示；若被移出屏幕会自动拉回。

---

## 插件系统

### 插件包格式

插件包是一个 ZIP 文件，后缀为 `.cblplugin` 或 `.cbplugin`。`plugin.json` 可以位于压缩包根目录，也可以位于唯一的顶层子目录中：

```text
my-plugin/
├─ plugin.json
└─ main.py
```

把目录压缩为 ZIP，再将后缀改为 `.cblplugin`，放入 `plugins/` 后重启程序即可自动安装。也可以在“设置 → 高级 → 安装本地插件”或托盘菜单中选择插件文件。

### `plugin.json`

```json
{
  "id": "class.demo.hello",
  "name": "hello",
  "version": "1.0.0",
  "entry": "main.py",
  "description": "在灵动岛上显示一句话",
  "author": "your-name",
  "requires": []
}
```

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `id` | 推荐 | 插件唯一标识，允许字母、数字、点、下划线、短横线；带命名空间时建议使用 `class.<作者>.<名字>` |
| `name` | 推荐 | 插件名；未提供 `id` 时也作为目录名候选 |
| `version` | 市场安装必填 | 语义化版本，如 `1.0.0` |
| `entry` | 否 | 入口文件，默认 `main.py`；也支持模块名 |
| `description` | 否 | 插件说明 |
| `author` | 否 | 作者信息 |
| `requires` | 否 | 依赖包名列表，由宿主依赖管理器安装 |

插件目录名会优先沿用已有安装目录，其次使用包内 `id` / `name`，最后才使用压缩包文件名。

### 入口示例

```python
from PySide6.QtWidgets import QLabel


def register(api):
    # 注册灵动岛文本：每次刷新时调用
    api.add_island_text(lambda: "你好，班级日常")

    # 注册一个插件设置页
    def build_page(_api):
        return QLabel("这是插件自己的设置页面")

    api.add_settings_page("示例插件", factory=build_page, icon="plugin")

    # 生命周期回调
    api.on_start(lambda: api.log("示例插件已启动"))
    api.on_stop(lambda: api.log("示例插件已停止"))
```

`register(api)` 在插件加载时调用，应只做注册，不要执行耗时任务。需要启动逻辑时使用 `api.on_start()`。

### `PluginAPI` 能力

| 分类 | 方法 | 说明 |
| --- | --- | --- |
| 生命周期 | `on_load(fn)` | 所有插件加载完成后调用 |
|  | `on_start(fn)` | 程序启动完成后调用 |
|  | `on_stop(fn)` | 程序退出时调用 |
| 主岛 | `add_island_text(fn)` | 返回一段文本，追加到主岛课程信息后 |
|  | `add_island_extra(fn)` | 返回主岛右侧加长片段：`{width, draw, on_click?, priority?}` |
|  | `add_island_banner(fn)` | 返回紧急警报条：`{text, ratio, color?, min_width?, priority?, on_click?}` |
| 下拉面板 | `add_panel(fn)` | 返回面板描述：`{text, width?, height?, min_width?, order?, position?}` |
| 副岛 | `add_subisland(fn)` | 返回副岛内容：`{text?, icon?, draw?, length?, priority?, auto_collapse?}` |
|  | `on_subisland_click(fn)` | 副岛被点击时调用 |
|  | `set_subisland_length(px)` | 设置副岛展开宽度 |
|  | `collapse_subisland()` / `expand_subisland()` | 控制副岛展开状态 |
| 设置页 | `add_settings_page(title, factory, icon, ...)` | 注册设置页，支持 `children` 三级子页 |
| 定时器 | `set_interval(seconds, fn)` | 注册重复定时器 |
|  | `set_timeout(seconds, fn)` | 注册单次定时器 |
| 配置 | `get_config(default)` / `set_config(data)` | 读写插件目录下的 `data.json` |
|  | `get_data_dir()` | 获取插件数据目录 |
| 课表 | `get_schedule_status()` / `is_in_class()` | 获取当前课表状态 |
| 交互 | `notify(text, is_end=False, force=False)` | 弹出主岛提醒；`force=True` 用于紧急预警 |
|  | `request_refresh()` | 请求宿主刷新灵动岛和副岛 |
|  | `log(*args)` | 输出带插件名前缀的日志 |

紧急警报条还支持 `extra.text` / `extra_text`（第二层避险要诀）、`extra_hold_sec`（第一层保持时间）和 `confirm_timeout_sec`（待确认超时）等可选字段。

所有插件的回调都在宿主主进程内执行。单个回调抛出异常时会被捕获并记录，不会导致主程序崩溃，但插件仍然拥有与主程序相同的文件与网络权限。

### 第三方依赖

插件可以在 `plugin.json` 中声明：

```json
{
  "requires": ["pillow", "requests"]
}
```

宿主会从 Gitee / GitHub 的依赖清单目录下载对应的包，校验 SHA-256 后解包到 `plugins/packages/`，并把包目录加入 `sys.path`。这套机制面向项目自己的依赖清单，不是直接执行 `pip install`。

依赖安装完成前后，插件可能显示 `MISSING_DEP` 状态；安装完成后宿主会自动补加载插件。

### 插件市场

默认索引来源：

- 官方聚合服务器：`https://plugins.class-daily-land.de5.net/list.json`
- GitHub：`LCHXXXX-1/Class-Daily-Land` 的 `plugins` 分支
- Gitee：`lchxxxx/class-daily-land` 的 `plugins` 分支

市场功能包括：

- SemVer 版本比较与“可更新”状态判断；
- 下载 `sha256` 校验；
- GitHub 直链自动转换为 jsDelivr 镜像候选；
- 下载失败自动切换镜像；
- 批量更新、启用 / 禁用、卸载；
- 网络失败时回退到上次成功同步的本地缓存；
- 索引条目有问题时仍显示插件，但标注原因并禁用安装。

插件启用 / 禁用、卸载通常需要重启程序才能完全生效，因为 Python 模块无法安全热卸载。

---

## 更新机制

程序本身不直接覆盖文件，而是调用同目录或上级目录中的更新器：

- `Launcher.exe`：显示更新界面，用于用户主动检查更新；
- `Launcher_hide.exe`：启动后静默检查更新；
- `launcher.py`：没有 exe 时的源码兜底。

搜索顺序包括：程序目录的上级目录、程序目录、`_internal/`、PyInstaller 的 `_MEIPASS`。

版本信息来自程序根目录的 `config.json`：

```json
{
  "version": "4.3",
  "version_url": "https://gitee.com/lchxxxx/class-daily-land/raw/update/version.json",
  "exe_name": "Class Daily Land.exe"
}
```

启动时，主面板会在约 2 秒后调用 `launch_hidden()` 静默检查更新；用户也可以在“设置 → 关于 → 检查更新”中手动触发。

### 源码运行保护

`dev_guard.py` 会在限定深度内扫描程序目录，识别未打包的主入口 Python 文件。命中时：

- 启动自动更新会被跳过，并提示先备份；
- 手动检查更新会弹出确认框，只有用户明确选择“仍然更新（已备份）”才会继续；
- 该行为由 `settings.json` 的 `block_update_on_source` 控制，默认开启。

### 优雅退出

更新器需要在覆盖文件前让主程序退出。主程序每 500ms 轮询：

```text
%TEMP%\ClassDailyLandLauncher\quit.flag
```

更新器写入该标志后，主程序退出 Qt 事件循环，更新器再执行替换。

---

## 开发指南

### 运行与调试

```powershell
cd "E:\11111\Code\Python\Class Daily Land\app\app"
python "Class Daily Land.py"
```

- 程序使用包结构绝对导入（如 `from Core.paths import ...`）；新增核心模块放 `Core/`，界面放 `UI/`，插件生态放 `Plugins/`，工具放 `Utils/`。
- 数据目录在源码模式下就是 `app/app/settings`，调试时可以直接打开“设置 → 高级 → 打开配置文件夹”。
- 修改课表或作业后，可通过右键菜单和设置页观察灵动岛刷新。
- `UI/test_dialog.py` 提供手动状态测试和灵动岛预览，不是 pytest 测试套件；本目录目前没有自动化测试和 CI 配置。

### 新增设置项

1. 在 `UI/Settings/settings_manager.py` 的 `DEFAULTS` 中加入默认值和类型。
2. 在 `UI/Settings/settings_dialog_v4.py` 对应页面添加 `SettingRow`，或使用 `_add_rows()`。
3. 如果设置需要立即生效，在 `AppController.apply_settings()` 或对应组件的 `apply_settings()` 中读取并应用。
4. 新键会自动获得类型校验；类型不匹配的旧值会回退到默认值。

### 新增业务数据

- 统一使用 `Core.storage.read_json()` / `write_json()` / `update_json()`，不要直接覆盖写 JSON。
- 数据文件放在 `settings/` 下，插件私有数据放在插件目录的 `data.json`。
- 涉及界面刷新时，调用 `controller.notify_island_dirty()` 或 `request_refresh()`。

### 新增插件能力

- 在 `PluginAPI` 中增加注册方法，并在 `PluginManager` 中维护回调列表。
- 在灵动岛 / 副岛 / 设置中心读取回调结果时，务必捕获插件异常，避免单个插件影响主程序。
- 涉及跨线程操作时，通过 Qt 信号回到主线程，不要在下载线程里直接创建控件。

### 打包约定

本目录没有包含 PyInstaller 配置，打包时需要注意：

- 采用 **onedir** 方式时，`icon.ico` 等只读资源通常进入 `_internal/`；`Core.paths._find_icon()` 会先查 exe 同级目录，再查 `sys._MEIPASS`。打包时必须把图标作为数据文件带上，例如：
  ```powershell
  pyinstaller -w -D -i icon.ico --add-data "icon.ico;." --collect-all PySide6 "Class Daily Land.py"
  ```
- `settings/` 和 `plugins/` 必须位于 exe 旁边，保证可写；
- `config.json` 需要能被 `about.py` 和更新器读取，可放在 exe 旁边或 `_internal/`；
- 更新器 `Launcher.exe` / `Launcher_hide.exe` 位于客户端程序目录的上级或同级目录。

---

## 已知限制与注意事项

- **Windows 优先**：云母材质、圆角、前台窗口检测、单实例互斥、任务栏行为等依赖 Win32 API；非 Windows 平台未做完整适配。
- **插件信任**：插件是进程内 Python 代码，拥有与主程序相同的权限。只安装可信来源的插件。
- **重启生效**：插件启用 / 禁用、卸载和部分更新需要重启；Python 模块不支持安全热卸载。
- **单实例**：重复启动会直接退出，不会激活已有窗口；请从托盘菜单打开界面。
- **更新器外部依赖**：源码目录中如果没有 `Launcher.exe` / `launcher.py`，更新功能不可用；这不会影响课表、作业等核心功能。
- **网络能力**：插件市场、依赖下载和自动更新依赖网络；国内网络下 GitHub 源可能不稳定，可切换 Gitee 或使用镜像。
- **设置版本**：`UI/Settings/settings_dialog_v4.py` 是当前入口；v3 的控件库仍被 v4 使用，v1 / v2 为历史实现。
- **测试方式**：本目录以手动 UI 测试为主，没有自动化测试；修改核心逻辑后建议运行“状态测试”并检查真实课表状态。
- **许可**：本目录未包含 `LICENSE` 文件。使用、分发或二次开发前，请先联系作者确认授权方式。

---

## 相关目录与反馈

本目录只包含桌面客户端源码。仓库上一级还包含 `Launcher`、`installer`、`Server`、`Web`、`Plugins`、`DeveloperTool`、`uninstall` 等子项目，具体职责以各自目录为准。

- 作者：LCHXXXX、hexwisp72
- 反馈邮箱：2352240265@qq.com
- 项目名称：Class Daily Land / 班级日常
- 当前版本：4.3

如果这个项目对你有帮助，欢迎从插件市场安装或开发插件，也欢迎反馈使用中遇到的问题。
