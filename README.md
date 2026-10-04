# Class Daily Land

> 一个轻量级的班级日常管理工具

Class Daily Land 是一个基于 **PySide6** 的 Windows 桌面应用，面向班级日常管理场景。提供值日生轮换、出勤记录、作业展示、课表与上课提醒，并内置模仿 iOS 灵动岛的桌面悬浮组件，可显示下节课倒计时、上课/下课提醒。v4.3 起内置了全新的 **Fluent 风格设置中心**、**浅色 / 深色自动主题**、**插件市场** 与 **插件第三方依赖自动安装**，插件扩展能力大幅增强。

- **当前版本**：v4.3
- **作者**：LCHXXXX、hexwisp72
- **反馈邮箱**：2352240265@qq.com

---

## 目录

- [功能特性](#功能特性)
- [环境要求](#环境要求)
- [安装与运行](#安装与运行)
- [目录结构](#目录结构)
- [配置文件说明](#配置文件说明)
- [插件开发](#插件开发)
- [插件市场与依赖包](#插件市场与依赖包)
- [开发说明](#开发说明)
- [常见问题](#常见问题)
- [贡献指南](#贡献指南)
- [许可证](#许可证)

---

## 功能特性

- **班级日常窗口**
  显示当前值日生、应到/实到人数、各科作业列表；作业内容支持自动滚动，窗口宽度、字号、透明度均可调。

- **灵动岛（Dynamic Island）**
  顶部居中悬浮胶囊，展示下节课倒计时、上课中剩余时间、假期/无课状态。上课前自动进入蓝色进度条倒计时，支持点击下拉面板查看课程表与插件内容。全屏应用或 WPS/Office 前台时自动隐藏或退出倒计时。

- **副岛（Sub Island）**
  主岛右侧的扩展区域，内容由插件提供，可展开/收起、可设定长度，支持自动收起。

- **课表管理**
  支持多套课表切换、新建/复制/重命名/删除；可设置临时调课、假期区间、调休上课日、周末作息；支持整体时间偏移与提前提醒分钟数；支持课表导出为文本/CSV 与从文件导入。

- **主题与外观（v4.3）**
  三档主题：跟随系统 / 浅色 / 深色。`theme.py` 提供统一色板与 QSS 生成，界面所有颜色实时取自色板，切换主题无需重启；Windows 11 下可开启设置窗口的云母（Mica）材质。

- **Fluent 风格设置中心（v4.3）**
  左侧导航栏 + 搜索框 + 分层子页的结构，页面包括：通用、外观、灵动岛、课表与提醒、作业、插件、高级、关于；课表与插件下可进二级页（课表编辑器、插件市场、依赖包）。开关、分段控件、卡片、徽章等均为自绘控件，带平滑动画。

- **插件系统**
  动态加载 `plugins/` 目录下的插件，插件可注册灵动岛文本、主岛加长片段、灵动岛横幅、下拉面板、副岛内容、设置页，并可使用定时器、读写自身配置、获取课表状态、发送通知。插件声明的第三方依赖可由宿主从服务器自动下载安装（见 [插件市场与依赖包](#插件市场与依赖包)）。

- **随机点名器**
  从 JSON 名单文件中随机抽取姓名，支持冷却避免重复。

- **系统托盘**
  快速切换主窗口、灵动岛、副岛的显示状态，打开设置、添加插件、退出程序。

- **自动更新**
  主程序不处理更新逻辑，通过 `launch_updater.py` 启动独立的 `Launcher.exe`（或源码 `launcher.py`）完成版本检查、下载与解压。

- **其他**
  首次启动需同意用户协议；单实例运行，避免重复打开；所有数据保存在本地，不上传服务器。

---

## 环境要求

- **操作系统**：Windows 10 / 11
  灵动岛的置顶、全屏检测、Office 前台检测、云母材质依赖 Win32 API，其他平台部分功能受限。
- **Python**：3.8 及以上
- **依赖库**：PySide6

```bash
pip install PySide6
```

---

## 安装与运行

### 从源码运行

```bash
git clone https://gitee.com/lchxxxx/class-daily-land.git
cd class-daily-land
pip install PySide6
python "Class Daily Land.py"
```

> GitHub 上的 `LCHXXXX-1/Class-Daily-Land` 为同步镜像（源码在 `master` 分支）。

> **源码运行保护**：在源码目录里直接 `python "Class Daily Land.py"` 启动时，程序会扫描程序目录及其一层子目录，检查是否存在未打包的主入口源码（`Class Daily Land.py` / `main.py` / `app.py`，或含 `if __name__ == "__main__":` 且顶层 import 了 `paths` / `theme` / `gui` / `controller` 的 py）。一旦命中，**不会拉起更新器**，而是弹出提示要求先手动备份（复制整个程序目录或先 `git commit`）；主动点“检查更新”时同样会拦截，可手动选择“仍然更新（已备份）”强制执行。打包版不受影响（主入口源码被 PyInstaller 收进 `_internal/`，扫描会跳过）。可在“通用 → 启动与更新”中关闭“源码运行保护更新”开关。

### 打包为可执行文件

```bash
pyinstaller -F -w -i icon.ico "Class Daily Land.py"
```

打包后请确保 `_internal/version.json` 或根目录下的 `version.json` 存在，以便“关于”页面正确显示版本号；“关于”页的版本号实际读取 `settings/config.json` 中的 `version` 字段。

### 快捷键

- `F1`：退出程序（在主窗口激活时生效）

---

## 目录结构

```
class-daily-land/
├── Class Daily Land.py    # 主入口，初始化应用与各组件
├── controller.py          # 应用协调器，集中处理设置应用与可见性联动
├── dynamic_island.py      # 灵动岛窗口与逻辑
├── sub_island.py          # 副岛窗口
├── gui.py                 # 主窗口
├── menu.py                # 值日生、出勤、作业、课表、假期等编辑对话框
├── schedule.py            # 课表管理核心
├── settings_manager.py    # 设置读写与默认值
├── settings_dialog.py     # 设置界面（基础版，前代实现）
├── settings_dialog_v2.py  # 设置界面（动画版，前代实现）
├── settings_dialog_v3.py  # 设置界面（Fluent 版，前代实现）
├── settings_dialog_v4.py  # 设置界面（当前使用的分层版）
├── settings_widgets.py    # 自绘控件库（开关/分段/卡片/徽章/导航等）
├── settings_rows.py       # 设置行与行控件（滑块/下拉/输入/开关）
├── theme.py               # 主题色板与 QSS 生成
├── plugin_manager.py      # 插件加载与 PluginAPI
├── plugin_market.py       # 插件市场：索引同步、下载校验与安装
├── market_page.py         # 插件市场页面
├── plugin_deps.py         # 插件第三方依赖：下载、校验、落盘、卸载
├── package_store.py       # 第三方依赖包管理（远端列出与安装/卸载）
├── package_page.py        # 依赖包管理页面
├── panel_window.py        # 灵动岛下拉面板窗口
├── randoms.py             # 随机点名器
├── tray_icon.py           # 系统托盘
├── agreement.py           # 用户协议对话框
├── about.py               # 关于对话框
├── launch_updater.py      # 主程序 → Launcher 的启动桥（含源码运行保护拦截点）
├── dev_guard.py           # 源码运行保护：识别未打包的主入口 py
├── single_instance.py     # 单实例互斥锁
├── storage.py             # JSON 原子读写
├── paths.py               # 统一路径管理
├── utils.py               # 图标等工具
├── ui_common.py           # 对话框公共样式与任务栏修复
├── StudentOnDuty.py       # 值日生管理
├── homework.py            # 作业管理
├── test_dialog.py         # 状态测试与情景演示
├── PLUGIN_API.md          # 插件接口文档
├── icon.ico               # 程序图标
├── plugins/               # 插件目录（运行时加载）
└── settings/              # 配置目录（运行时生成，不提交）
```

---

## 配置文件说明

程序根目录下的 `settings/` 文件夹保存所有本地数据：

| 文件 | 说明 |
|------|------|
| `settings.json` | 应用设置（主题、窗口、灵动岛、动画、市场源等） |
| `schedule.json` | 课表数据（多课表、临时调课、假期、调休、周末作息） |
| `homework.json` | 作业列表 |
| `name.json` | 值日生名单 |
| `config.json` | 版本号、更新地址、程序文件名 |
| `agreement.json` | 用户协议同意状态 |

所有读写均通过 `storage.py` 的 `read_json` / `write_json` 完成，采用临时文件 + `os.replace` 的原子写入方式，降低数据损坏风险。

### 默认设置项

| 键 | 默认值 | 说明 |
|----|--------|------|
| `theme_mode` | `system` | 主题：跟随系统 / 浅色 / 深色 |
| `settings_mica` | `True` | Windows 11 云母材质（Win10 自动忽略） |
| `main_width_ratio` | `0.25` | 主窗口宽度占屏幕比例 |
| `main_font_size` | `14` | 主窗口字号 |
| `main_auto_scroll` | `True` | 作业自动滚动 |
| `main_scroll_interval` | `50` | 滚动间隔（毫秒） |
| `main_scroll_step` | `1` | 每步滚动像素 |
| `main_scroll_pause` | `60` | 到底暂停次数 |
| `main_opacity` | `1.0` | 主窗口透明度 |
| `show_main_window` | `True` | 显示主窗口 |
| `island_top_margin` | `6` | 灵动岛距顶部距离 |
| `island_hide_on_fullscreen` | `True` | 全屏时隐藏灵动岛 |
| `island_show_wakeup_anim` | `True` | 灵动岛唤醒动画 |
| `island_alert_width` | `300` | 提醒宽度 |
| `island_alert_hold_ms` | `600` | 提醒停留时间 |
| `island_countdown_sec` | `60` | 倒计时时长 |
| `show_island` | `True` | 显示灵动岛 |
| `show_sub_island` | `True` | 显示副岛 |
| `sub_island_collapsed` | `False` | 副岛默认收起 |
| `sub_island_auto_collapse_sec` | `5` | 副岛自动收起秒数 |
| `anim_fade_window` | `True` | 窗口渐显 |
| `anim_fade_panel` | `True` | 面板渐显 |
| `anim_fade_text` | `True` | 文字变化渐显 |
| `anim_duration` | `320` | 动画时长（毫秒） |
| `check_update_on_start` | `True` | 启动时检查更新 |
| `block_update_on_source` | `True` | 源码运行保护：检测到未打包主入口时不拉起更新器（仍需手动确认） |
| `disabled_plugins` | `[]` | 被禁用的插件目录名列表 |
| `market_source` | `official` | 插件市场索引源：official / github / gitee |
| `packages_source` | `gitee` | 第三方依赖包下载源：gitee / github |
| `packages_base_url` | `""` | 自定义依赖清单服务器（空串=按 `packages_source` 取内置地址） |

---

## 插件开发

### 插件目录结构

```
plugins/
└── myplugin/
    ├── plugin.json
    └── main.py
```

`plugin.json` 示例：

```json
{
  "name": "MyPlugin",
  "entry": "main.py",
  "requires": ["requests"]
}
```

`requires` 为可选字段，列出插件需要的第三方包名（小写、不写版本）。宿主检测到缺失时会自动从依赖服务器拉取安装清单并装到 `plugins/packages/<包名>/`，装好后插件里直接 `import requests` 即可。详见 [插件市场与依赖包](#插件市场与依赖包)。

`main.py` 示例：

```python
def register(api):
    # 在灵动岛主文本后追加内容
    api.add_island_text(lambda: "🌤 26℃")

    # 每 60 秒发送一次通知
    api.set_interval(60, lambda: api.notify("喝水提醒"))

    # 注册一个设置页
    def build_settings_page(api):
        from PySide6.QtWidgets import QLabel
        return QLabel("这里是我的插件设置")

    api.add_settings_page("我的插件", build_settings_page, icon="🔧")
```

### PluginAPI 主要接口

| 方法 | 说明 |
|------|------|
| `on_load(fn)` / `on_start(fn)` / `on_stop(fn)` | 生命周期回调 |
| `add_island_text(fn)` | 注册函数，返回字符串追加到主岛文本 |
| `add_island_extra(fn)` | 注册主岛右侧加长片段，返回 `{width, draw, on_click?, priority?}` |
| `add_island_banner(fn)` | 注册主岛横幅片段 |
| `add_panel(fn)` | 注册下拉面板，返回 `{text, width, min_width, height, position, order}` |
| `add_subisland(fn)` | 注册副岛内容，返回 `{text/icon 或 draw, length, priority, auto_collapse}` |
| `set_subisland_length(n)` / `set_subisland_collapsed(bool)` | 副岛长度与折叠状态 |
| `collapse_subisland()` / `expand_subisland()` | 手动折叠 / 展开副岛 |
| `on_subisland_click(fn)` | 副岛点击回调 |
| `subisland_show_weather(bool)` | 副岛是否展示天气位 |
| `add_settings_page(title, factory, icon)` | 注册插件设置页 |
| `set_interval(seconds, fn)` | 创建循环定时器 |
| `set_timeout(seconds, fn)` | 创建单次定时器 |
| `get_data_dir()` | 获取插件数据目录 |
| `get_config(default)` / `set_config(data)` | 读写插件自己的 `data.json` |
| `get_schedule_status()` | 获取当前课表状态字典 |
| `is_in_class()` | 是否正在上课 |
| `notify(text, is_end=False)` | 让灵动岛弹出提醒 |
| `request_refresh()` | 请求刷新灵动岛与面板 |
| `log(*args)` | 输出插件日志 |

插件加载失败不会影响主程序，错误信息会打印到控制台。

### 灵动岛状态字典

`get_schedule_status()` 返回的字典大致包含：

| 字段 | 说明 |
|------|------|
| `status` | `upcoming` / `ongoing` / `done` / `none` / `holiday` |
| `course` | 课程名 |
| `period` | 节次名 |
| `start` / `end` | 课表时间 |
| `until_sec` / `until_min` | 距上课时间 |
| `remain_sec` / `remain_min` | 距下课时间 |
| `duration_sec` | 本节课总时长 |
| `advance_sec` | 提前提醒秒数 |
| `index` | 当前节次索引 |
| `name` | 假期名称（仅 `holiday` 状态） |

---

## 插件市场与依赖包

### 插件市场

插件可在应用内直接搜索、下载、启用与卸载，不必手动拷贝文件夹。市场核心在 `plugin_market.py`，索引来源三选一（设置 → 高级）：

| 来源 | 说明 |
|------|------|
| `official` | 官方服务器 `https://plugins.class-daily-land.de5.net/list.json`（默认） |
| `github` | GitHub 仓库 `plugins` 分支根目录的 `list.json`（raw 直链 + jsDelivr 镜像） |
| `gitee` | Gitee 仓库 `plugins` 分支根目录的 `list.json`（raw 直链） |

各来源的条目会解析成同一套内部字段，下载、校验、安装逻辑完全共用。索引同步成功后会落盘到缓存目录，离线时仍可打开已缓存列表。下载完成会校验哈希，再解压到 `plugins/<插件目录>/`，然后在“设置 → 插件”中启用。

### 第三方依赖包

插件在 `plugin.json` 里用 `requires` 声明依赖（如 `requests`），宿主从 `{依赖服务器}/<包名>.json` 拉安装清单，清单给出固定版本、依赖链、逐文件的 sha256、多个下载镜像与文件列表。安装流程：

1. 解析清单与递归依赖（去重、防环）；
2. 多镜像逐个尝试下载；
3. 逐文件 sha256 校验；
4. 原子落盘到 `plugins/packages/<包名>/`（该目录已在 `sys.path` 中）。

登记表 `plugins/packages/packages.json` 记录每个包的固定版本与 `used_by`（哪些插件在用）；插件卸载时把自己从 `used_by` 摘掉，没有人再用的包才会真正删除。进度通过回调实时回传到底层的依赖包管理页面。

即使没有插件声明，也可以在“设置 → 高级 → 依赖包”中手动浏览远端可用包、查看“被哪些插件使用”，自行安装或卸载。

---

## 开发说明

- **主程序不处理更新**：所有版本比较、下载、解压均由独立的 Launcher 完成。`launch_updater.py` 只负责以隐藏或可见方式启动 `Launcher.exe`（或回退到 `launcher.py`）。
- **主题机制**：`theme.init(settings)` 在启动时初始化，`theme.apply_theme(app)` 应用到全局；窗口可通过 `theme.dialog_qss()` 拿自己的 QSS，代码里用 `theme.color("...")` 取色，主题变更用 `theme.theme_changed_connect(cb)` 订阅（内部使用弱引用）。灵动岛 / 副岛 / 下拉面板为深色自绘组件，不走主题模块。
- **灵动岛的平台限制**：置顶、全屏检测、Office 前台检测使用 `ctypes` 调用 Win32 API，仅在 Windows 下完整可用；其他平台会跳过相关逻辑。
- **单实例**：通过 Windows 命名互斥体 `ClassDailyLand_SingleInstance_Mutex` 实现，避免重复启动。
- **用户协议**：首次启动弹出协议对话框，同意后写入 `agreement.json`。
- **配置即时保存**：设置对话框中的大部分修改会立即写入 `settings.json` 并应用到各组件。
- **后台任务**：市场索引同步与依赖下载全部在 worker 线程执行，通过 Qt 信号回传 UI，主线程不做阻塞网络请求。
- **数据本地化**：值日、作业、课表、设置等全部保存在 `settings/` 目录，不上传服务器。
- **源码运行保护**：`dev_guard.scan_source_entry()` 扫描程序目录与一层子目录（跳过 `settings/`、`plugins/`、`__pycache__/`、`_internal/` 等），命中主入口 py 后由 `launch_updater.py` 统一拦下——所有更新入口（启动静默检查、主窗口/托盘、关于页“检查更新”）都走这一个拦截点，不会有旁路。手动执行 `python dev_guard.py <目录>` 可单独打印扫描结果，便于调试。

### 仓库分支

| 分支 | 用途 |
|------|------|
| `master` | 主源码（本文档对应的目录结构） |
| `plugins` | 插件发布成品 |
| `developer` | 开发工具 |
| `update` | 更新服务器（`version.json` 所在） |

---

## 常见问题

**Q：灵动岛不显示怎么办？**
A：检查设置中“显示灵动岛”是否开启；如果当前有全屏应用或 WPS/Office 在前台，灵动岛会自动隐藏，切换回桌面即可恢复。

**Q：怎么把界面换成深色？**
A：设置 → 外观，主题选择“深色”或“跟随系统”；Windows 11 下可同时开启云母材质。切换是实时的，不需要重启。

**Q：如何添加插件？**
A：三种方式：把插件文件夹放进 `plugins/` 目录；在“设置 → 插件”中点击“添加插件”选择 `.cbplugin` 文件；或者在“设置 → 插件 → 插件市场”里直接搜索安装。

**Q：插件提示缺少第三方库怎么办？**
A：在插件的 `plugin.json` 中加 `requires` 声明，重启程序后会自动下载安装；也可以手动打开“设置 → 高级 → 依赖包”自行安装。

**Q：数据会上传到服务器吗？**
A：不会。所有数据仅保存在本地 `settings/` 文件夹中，插件市场与依赖包只在安装时访问网络。

**Q：如何恢复默认课表？**
A：在“课表与提醒”中打开课表管理器，点击“恢复默认课表（清除全部自定义）”。

**Q：更新检查失败？**
A：请确认程序目录下存在 `Launcher.exe` 或 `launcher.py`。主程序本身不包含下载逻辑。

**Q：我从源码运行，点了“检查更新”却没反应？**
A：这是源码运行保护在起作用——程序目录下检测到未打包的主入口源码，会先弹窗提示你手动备份（复制整个程序目录或先 `git commit`），确认后才会拉起更新器。确实要强制更新：在弹窗里点“仍然更新（已备份）”，或在设置 → 通用 → 启动与更新关掉“源码运行保护更新”开关。

**Q：为什么只能打开一个程序实例？**
A：Class Daily Land 使用单实例锁，避免多个实例同时读写配置文件造成冲突。若需重新启动，请先退出已有实例。

---

## 贡献指南

欢迎提交 Issue 和 Pull Request。

- 提交前请确保代码在 Windows + PySide6 环境下可正常运行。
- 新增功能请尽量保持模块化，并补充必要的注释。
- 插件相关改动请同步更新本文档的“插件开发”与“插件市场与依赖包”章节。
- 请勿提交包含个人隐私、真实班级数据或第三方版权内容的文件。

---

## 许可证

本项目采用 **MIT 许可证**。
如果仓库中尚未包含 `LICENSE` 文件，请作者补充；使用前请以实际许可证文件为准。

---

*Class Daily Land 仅用于个人学习与班级管理，请勿用于任何非法或违反道德的活动。*
*本项目部分内容使用了 AI 工具辅助完成*
