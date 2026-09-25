# ClassBoard

> 一个轻量级的班级日常管理工具

ClassBoard 是一个基于 **PySide6** 的 Windows 桌面应用，面向班级日常管理场景。提供值日生轮换、出勤记录、作业展示、课表提醒等功能，并内置模仿 iOS 灵动岛的桌面悬浮组件，可显示下节课倒计时、上课/下课提醒。同时支持插件扩展。

- **当前版本**：v4.0
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
- [开发说明](#开发说明)
- [常见问题](#常见问题)
- [许可证](#许可证)

---

## 功能特性

- **班级日常窗口**  
  显示当前值日生、应到/实到人数、各科作业列表；作业内容支持自动滚动，窗口宽度、字号、透明度均可调。

- **灵动岛（Dynamic Island）**  
  顶部居中悬浮胶囊，展示下节课倒计时、上课中剩余时间、假期/无课状态。上课前自动进入蓝色进度条倒计时，支持点击下拉面板查看课程表与插件内容。全屏应用或 WPS/Office 前台时自动隐藏或退出倒计时。

- **副岛（Sub Island）**  
  主岛右侧的扩展区域，内容由插件提供，可展开/收起，支持自动收起。

- **课表管理**  
  支持多套课表切换、新建/复制/重命名/删除；可设置临时调课、假期区间、调休上课日、周末作息；支持整体时间偏移与提前提醒分钟数。

- **插件系统**  
  动态加载 `plugins/` 目录下的插件，插件可注册灵动岛文本、主岛加长片段、下拉面板、副岛内容、设置页，并可使用定时器、读写自身配置、获取课表状态、发送通知。

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
  灵动岛的置顶、全屏检测、Office 前台检测依赖 Win32 API，其他平台部分功能受限。
- **Python**：3.8 及以上
- **依赖库**：PySide6

```bash
pip install PySide6
```

---

## 安装与运行

### 从源码运行

```bash
git clone https://gitee.com/lchxxxx/board.git
cd board
pip install PySide6
python ClassBoard.py
```

### 打包为可执行文件

```bash
pyinstaller -F -w -i icon.ico ClassBoard.py
```

打包后请确保 `_internal/version.json` 或根目录下的 `version.json` 存在，以便“关于”页面正确显示版本号。

### 快捷键

- `F1`：退出程序（在主窗口激活时生效）

---

## 目录结构

```
board/
├── ClassBoard.py          # 主入口，初始化应用与各组件
├── controller.py          # 应用协调器，集中处理设置应用与可见性联动
├── dynamic_island.py      # 灵动岛窗口与逻辑
├── sub_island.py          # 副岛窗口
├── gui.py                 # 主窗口 ClassBoardApp
├── menu.py                # 值日生、出勤、作业、课表、假期等编辑对话框
├── schedule.py            # 课表管理核心
├── settings_manager.py    # 设置读写
├── settings_dialog.py     # 设置界面
├── plugin_manager.py      # 插件加载与 PluginAPI
├── panel_window.py        # 灵动岛下拉面板窗口
├── randoms.py             # 随机点名器
├── tray_icon.py           # 系统托盘
├── agreement.py           # 用户协议对话框
├── about.py               # 关于对话框
├── launch_updater.py      # 主程序 → Launcher 的启动桥
├── single_instance.py     # 单实例互斥锁
├── storage.py             # JSON 原子读写
├── paths.py               # 统一路径管理
├── utils.py               # 图标等工具
├── ui_common.py           # 对话框公共样式与任务栏修复
├── StudentOnDuty.py       # 值日生管理
├── homework.py            # 作业管理
├── test_dialog.py         # 状态测试与情景演示
├── version.json           # 版本号
├── icon.ico               # 程序图标
├── plugins/               # 插件目录（运行时加载）
└── settings/              # 配置目录（运行时生成，不提交）
```

---

## 配置文件说明

程序根目录下的 `settings/` 文件夹保存所有本地数据：

| 文件 | 说明 |
|------|------|
| `settings.json` | 应用设置（窗口、灵动岛、动画、更新等） |
| `schedule.json` | 课表数据（多课表、临时调课、假期、调休、周末作息） |
| `homework.json` | 作业列表 |
| `name.json` | 值日生名单 |
| `config.json` | 出勤人数、当前值日生索引、上次轮换日期 |
| `agreement.json` | 用户协议同意状态 |

所有读写均通过 `storage.py` 的 `read_json` / `write_json` 完成，采用临时文件 + `os.replace` 的原子写入方式，降低数据损坏风险。

### 默认设置项

| 键 | 默认值 | 说明 |
|----|--------|------|
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
  "entry": "main.py"
}
```

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
| `add_panel(fn)` | 注册下拉面板，返回 `{text, width, min_width, height, position, order}` |
| `add_subisland(fn)` | 注册副岛内容，返回 `{text/icon 或 draw, length, priority, auto_collapse}` |
| `add_settings_page(title, factory, icon)` | 注册插件设置页 |
| `set_interval(seconds, fn)` | 创建循环定时器 |
| `set_timeout(seconds, fn)` | 创建单次定时器 |
| `get_schedule_status()` | 获取当前课表状态字典 |
| `is_in_class()` | 是否正在上课 |
| `notify(text, is_end=False)` | 让灵动岛弹出提醒 |
| `get_config(default)` / `set_config(data)` | 读写插件自己的 `data.json` |
| `get_data_dir()` | 获取插件数据目录 |
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

## 开发说明

- **主程序不处理更新**：所有版本比较、下载、解压均由独立的 Launcher 完成。`launch_updater.py` 只负责以隐藏或可见方式启动 `Launcher.exe`（或回退到 `launcher.py`）。
- **灵动岛的平台限制**：置顶、全屏检测、Office 前台检测使用 `ctypes` 调用 Win32 API，仅在 Windows 下完整可用；其他平台会跳过相关逻辑。
- **单实例**：通过 Windows 命名互斥体 `ClassBoard_SingleInstance_Mutex` 实现，避免重复启动。
- **用户协议**：首次启动弹出协议对话框，同意后写入 `agreement.json`。
- **配置即时保存**：设置对话框中的大部分修改会立即写入 `settings.json` 并应用到各组件。
- **数据本地化**：值日、作业、课表、设置等全部保存在 `settings/` 目录，不上传服务器。

---

## 常见问题

**Q：灵动岛不显示怎么办？**  
A：检查设置中“显示灵动岛”是否开启；如果当前有全屏应用或 WPS/Office 在前台，灵动岛会自动隐藏，切换回桌面即可恢复。

**Q：如何添加插件？**  
A：将插件文件夹放入 `plugins/` 目录，或在“设置 → 插件”中点击“添加插件”选择 `.cbplugin` 文件，重启后生效。

**Q：数据会上传到服务器吗？**  
A：不会。所有数据仅保存在本地 `settings/` 文件夹中。

**Q：如何恢复默认课表？**  
A：在“课表管理”对话框中点击“恢复默认课表（清除全部自定义）”。

**Q：更新检查失败？**  
A：请确认程序目录下存在 `Launcher.exe` 或 `launcher.py`。主程序本身不包含下载逻辑。

**Q：为什么只能打开一个程序实例？**  
A：ClassBoard 使用单实例锁，避免多个实例同时读写配置文件造成冲突。若需重新启动，请先退出已有实例。

---

## 贡献指南

欢迎提交 Issue 和 Pull Request。

- 提交前请确保代码在 Windows + PySide6 环境下可正常运行。
- 新增功能请尽量保持模块化，并补充必要的注释。
- 插件相关改动请同步更新本文档的“插件开发”章节。
- 请勿提交包含个人隐私、真实班级数据或第三方版权内容的文件。

---

## 许可证

本项目采用 **MIT 许可证**。  
如果仓库中尚未包含 `LICENSE` 文件，请作者补充；使用前请以实际许可证文件为准。

---

*ClassBoard 仅用于个人学习与班级管理，请勿用于任何非法或违反道德的活动。*