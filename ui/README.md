# ui/ —— 两个项目共用的设置中心（阶段 P1）

一套 HTML/CSS/JS，两个宿主渲染同一份：

| 项目 | 外壳（原生，不动） | 渲染层（共用这份） |
|---|---|---|
| `ClassDailyLand-Net`（.NET 10 / WPF） | 窗口 / 托盘 / 热键 / Mica / 插件宿主 | 入口 `index.html` + **WebView2** |
| `ClassDailyLand-Py`（Python / PySide6） | 同上 | 入口 `index-qt.html` + **QWebEngineView** |

灵动岛、副岛、右侧班级日常主窗、下拉面板**有意保持原生**，本目录不碰它们。

## 先看效果

**双击 `index.html` 即可**（`file://` 下也能跑，检测不到宿主会自动降级成内置 mock 数据）。

能试的几件事：

1. 左侧八个页面逐个点 —— 切页带淡入，选中项有强调色指示条
2. 外观 → 颜色模式 → **深色 / 浅色** —— 整套 WinUI 3 色板实时切换
3. 通用 → 拖「窗口宽度 / 窗口透明度」—— 数值实时跟随
4. 插件 → 点「同步索引」—— 按钮转圈、运行日志滚动、底部弹出提示条
5. 顶部搜索框输入「灵动」—— 导航即时过滤
6. 高级 → 恢复全部默认 —— 弹确认框，确认后设置回到初始值

## 界面实拍

用 Edge 无头模式实拍（1360×900，无后期处理）：

- [通用 · 页内标题栏](docs/screenshots/settings-general-light.png)（`?page=general`，见得到标题栏与窗口按钮）
- [通用 · 原生标题栏模式](docs/screenshots/settings-general-native-chrome.png)（`?chrome=native`，两个宿主实际用的就是这种）
- [外观 · 浅色](docs/screenshots/settings-appearance-light.png)（主题预览磁贴 + 下划线选项卡）
- [外观 · 深色](docs/screenshots/settings-appearance-dark.png)
- [灵动岛 · 浅色](docs/screenshots/settings-island-light.png)（两张可展开卡片：主岛 / 副岛）
- [课表与提醒 · 浅色](docs/screenshots/settings-schedule-light.png)
- [课表与提醒 · 深色](docs/screenshots/settings-schedule-dark.png)
- [作业 · 浅色](docs/screenshots/settings-homework-light.png)（编辑器是**内嵌**的，不是弹窗）
- [插件 · 浅色](docs/screenshots/settings-plugins-light.png)
- [插件 · 深色](docs/screenshots/settings-plugins-dark.png)
- [高级 · 浅色](docs/screenshots/settings-advanced-light.png)
- [关于 · 浅色](docs/screenshots/settings-about-light.png)

二级对话框（页内浮层，`?dialog=<id>` 深链接拍的）：

- [假期与调休](docs/screenshots/dialog-holidays.png)
- [周末作息](docs/screenshots/dialog-weekend.png)
- [值日生名单](docs/screenshots/dialog-duty.png)
- [编辑作业](docs/screenshots/dialog-homework.png)

## 目录

```
ui/
├── index.html            .NET 宿主入口
├── index-qt.html         Python 宿主入口（多引一行 qwebchannel.js）
├── host.js               宿主桥：唯一分辨 WebView2 / Qt 的文件（含浏览器 mock）
├── lib/
│   ├── icons.js          内联 SVG 图标（42 个；不用图标字体，避免缺字掉方块）
│   ├── controls.js       Fluent / RinUI 构件构造器：
│   │                     ── 输入：ToggleSwitch / Slider / NumberBox / ComboBox /
│   │                        Segmented / SelectorBar / TextBox
│   │                     ── 反馈：InfoBar / Badge / InfoBadge / ProgressBar / ProgressRing
│   │                     ── 行与卡片：group / SettingCard / SettingItem / ClipRow /
│   │                        LinkRow / SettingExpander / ContentDialog
│   └── editors.js        二级对话框外壳 + 编辑控件：文本框 / 日期 / 多行 / 下拉 /
│                         可选中列表 / 卡片（对应原生 ScheduleDialogParts）
├── pages/
│   ├── settings.js       设置中心本体：外壳（标题栏 / 分组导航 / 内容区）+ 八个页面
│   ├── dialogs.js        二级对话框（假期与调休 / 周末作息 / 值日生名单 / 作业编辑器）
│   └── market.js         插件页：插件市场 + 第三方包 + 本地插件 + 运行日志
├── styles/
│   ├── tokens.css        设计令牌（浅/深两套，变量名对齐 WinUI 3 资源键）
│   ├── components.css    控件与行/卡片构件
│   ├── settings.css      版式：NavigationView 外壳、英雄区、分区、瀑布流
│   └── dialogs.css       浮层对话框与其中的编辑控件
├── docs/screenshots/     界面实拍（Edge 无头模式，无后期处理）
└── tests/                三项自动化校验（见下）
```

合计约 4,600 行（不含测试），**零运行时依赖、零构建**：两个 `<link>` + 七个 `<script>`。

## 设计令牌与 WinUI 3 的对应

`styles/tokens.css` 里的变量名刻意跟 WinUI 3 的 XAML 资源键对齐，方便对照排查：

| 本项目变量 | WinUI 3 资源键 | 用途 |
|---|---|---|
| `--card-background-fill-color-default` | `CardBackgroundFillColorDefault` | 设置卡片底 |
| `--card-stroke-color-default` | `CardStrokeColorDefault` | 卡片描边 |
| `--divider-stroke-color-default` | `DividerStrokeColorDefault` | 行分隔线 |
| `--text-fill-color-primary/secondary/tertiary` | `TextFillColor*` | 三级文字 |
| `--control-fill-color-*` / `--control-stroke-color-*` | `ControlFillColor*` / `ControlStrokeColor*` | 控件底与描边 |
| `--control-alt-secondary/tertiary-fill-color` | `ControlAltSecondaryColor` / `ControlAltTertiaryColor` | 行悬停与选中底 |
| `--accent-fill-color-default` | `AccentFillColorDefault` | 强调色（浅 `#005FB8` / 深 `#60CDFF`） |
| `--system-fill-color-*` / `-*-bg` | `SystemFillColorSuccess/Caution/Critical` + 浅底 | 语义色与 InfoBar 底 |
| `--control-corner-radius` | `ControlCornerRadius` | 控件圆角 5px（RinUI `buttonRadius`） |
| `--small-corner-radius` | — | 小件圆角 3px（RinUI `smallRadius`） |
| `--window-corner-radius` | — | 窗口 / 对话框圆角 7px（RinUI `windowRadius`） |
| `--card-corner-radius` | — | 卡片圆角 8px |
| `--nav-item-height` / `--nav-indicator-*` | — | 导航项 40px、选中竖条 3×17 |
| `--setting-row-height` / `--setting-item-min-height` | — | 行高 64px（ClipItem）/ 50px（SettingItem） |

字体用 `Segoe UI Variable Display / Text`，回落 `Microsoft YaHei UI`。
**要换皮、要接系统强调色，只改这一个文件。**

> 颜色这一层本来就是同一套：RinUI 的 `controlFillColor #FFFFFFB2`、`cardColor #FFFFFFB2`、
> `textColor #1b1b1b`、`dividerBorderColor #00000014`、`backgroundColor #F3F3F3`
> 与 WinUI 3 的资源**逐字节一致**。唯一的取舍是强调色 —— 本项目沿用 Windows 原生蓝
> （应用是 Windows 桌面工具，跟系统一致），RinUI 默认是 `#605ed2`，
> 想换成 CW2 那个紫只改 `--accent-fill-color-default` 三行。

## 构图（照 Class Widgets 2 重写的部分）

上一版是「一个卡片里堆很多行」的 Win11 设置观感。这一版把**构图**换成
[Class Widgets 2](https://github.com/RinLit-233-shiroko/Class-Widgets-2) 的写法
（它建在 [RinUI](https://github.com/RinLit-233-shiroko/Rin-UI) 之上），
几何、字体阶梯、动效时长全部按两份源码的真实数值取值，不是照着截图估的：

```
.app-shell
  ├ .app-titlebar                        48px 窗口镶边（无边框时才画按钮）
  └ .app-body
      ├ .nav-pane                        280px：搜索 + 分组导航（父项可展开子项）
      └ .content-pane                    圆角内容卡（layerColor + 1px 描边）
          └ .content-inner               max-width 1000、两侧 42px
              ├ .hero                    英雄区：主题色薄雾 + 大标题，底部渐隐
              └ .group × N               分区：BodyStrong 标题 + 若干卡片
                  ├ .card > .scard       一张卡一项设置（图标 22 + 标题 + 说明 + 控件）
                  ├ .exp                 SettingExpander：标题栏带实时控件，展开体放密集行
                  │   └ .sitem × N       卡内密集行（≥50 高、分隔线、可选箭头）
                  └ .crow                ClipItem：64 高的行，顶部 1px 分隔线、悬停有底色
```

- **导航分组**：`课表与提醒` 自己仍是设置页，同时展开出 5 个子项（课表管理 / 周末作息 /
  假期与调休 / 值日生名单 / 状态测试）—— 子项**不是页面**，是二级对话框入口。
  与 CW2 的「Notification & Time」那种「有子项、也有正文」的分组同构。
  子项另有 `.nav-sub-item` 类名，`?page=` 与 .NET/Qt 的按页直达不受影响。
- **字体阶梯**：照 RinUI `Typography` 的 8 档（Display 68/92 · TitleLarge 40/52 ·
  Title 28/36 · Subtitle 20/28 · BodyLarge 18/24 · Body 14/20 · **BodyStrong 14/20 DemiBold** ·
  Caption 12/16）。分区标题用 BodyStrong、行标题用 Body、说明用 Caption —— 与 CW2 一致。
- **行高与内边距**：ClipItem 64 高 / 左 22 右 16 / gap 14；SettingCard padding 18×16、
  gap 16、图标 22；SettingItem ≥50 高、gap 16；导航项 40 高、图标 19、左缩进 11、
  子项额外缩进 34。
- **圆角**：控件 5（RinUI `buttonRadius`）、小件 3（`smallRadius`）、
  窗口与对话框 7（`windowRadius`）、卡片 8。
- **标题栏**：48px 高（`windowTitleBarHeight`），窗口按钮 48×40（RinUI `CtrlBtn`
  实测值，不是 `windowButtonWidth` 那个 46），关闭键悬停变 `#c42b1c`（`captionCloseColor`）。
- **高度层级阴影**：RinUI 每档只有一段、无 spread —— cardRest `0 2px 4px @0.04`、
  tooltip `0 4px 8px @0.14`、flyout `0 8px 24px @0.14`、dialog `0 32px 64px @0.19`
  （深色 `@0.37`）；卡片与按钮顶部有一道**内高光**（`--hairline-highlight`），
  是控件「有厚度」的关键。
- **动效**：时长取 RinUI `themes/utils.qml`，曲线取它实际用的 Qt Easing
  （颜色 → OutQuart，几何 → OutQuint）。状态色 187ms、开关与指示器 250ms、
  **可展开卡片 333ms**（`animationSpeedExpander`）、页面推进与对话框缩放 667ms、
  不确定进度条 1550ms。展开动画用 `grid-template-rows: 0fr → 1fr`，不需要固定高度。
- **深浅色切换是交叉淡入**：切主题的瞬间给 `<html>` 挂 `data-theme-anim`，
  所有颜色类属性一起按 187ms OutQuart 过渡，240ms 后摘掉（启动首帧不做过场）。
  宿主侧配套：.NET 的设置窗口**显式设过一次 `ThemeMode`** —— 离屏探针实测，
  显式设过的窗口完全不受 `Application.ThemeMode` 切换影响，页面刷新与重载都不会发生。

## 页面与字段来源（全部照真实实现，没有编造）

| 页面 | 来源 | 字段 |
|---|---|---|
| 通用 | `SettingsWindow.xaml.cs` / `settings_dialog_v4.py` | 主窗口 4 项、作业滚动 4 项、启动与更新 2 项 |
| 外观 | 同上 | 颜色模式（跟随系统/浅色/深色）、淡入淡出 4 项、云母材质（非 Win11 自动禁用并说明） |
| 灵动岛 | 同上 | 主岛 6 项、副岛 3 项 |
| 课表与提醒 | `SettingsWindow.Pages.cs:RenderScheduleHubPage` | 上课提醒 3 项 + 5 个二级入口（课表管理/周末作息/假期与调休/值日生名单/状态测试，图标底色沿用源项目的 tint） |
| 作业 | `RenderHomeworkPage` | 该页最终内嵌编辑器（即时保存、无确认按钮），本轮给出入口并标注待接入 |
| 插件 | `SettingsWindow.Market.cs` | 插件中心（市场 + 第三方包管理 + 运行日志）、已安装插件（含启用开关、加载失败原因、需重启提示） |
| 高级 | `RenderAdvancedPage` | 本地插件 2 项、日常维护 2 项（恢复默认走危险色）、配置文件路径 |
| 关于 | `RenderAboutPage` | 图标 + 名称 + 版本、简介/作者/反馈/系统/窗口材质、源码运行保护提示、检查更新 |

设置键名沿用 `AppSettings` 的 snake_case，宿主直接透传即可。

## 宿主需要实现的 RPC

| 方法 | 参数 | 返回 |
|---|---|---|
| `app.getVersion` | — | `{version, platform, host, system, configPath, pluginsPath}` |
| `settings.getAll` | — | 全部设置（snake_case 键） |
| `settings.patch` | `{键: 值, …}` | `{ok:true}` |
| `settings.reset` | — | `{ok:true}` |
| `plugins.list` | — | `{plugins:[{id,name,version,desc,requires,enabled,loaded,failure}]}` |
| `plugins.setEnabled` | `{id, enabled}` | `{ok:true, restartRequired:true}` |
| `market.status` | — | 见下「插件市场用到的 RPC」 |
| `market.sync` | — | 同上 |
| `packages.status` | — | 同上 |
| `packages.sync` | `{name?}` | 同上（带 `name` 是「装这个包」，不带才是刷新目录） |
| `dialog.open` | `{id}` | `{opened:true}`；未接入时回 `{opened:false, reason:"…"}`，界面会如实弹说明 |
| `app.openFolder` | `{id: config\|plugins\|homework\|marketUrl}` | `{ok:true, path}` |
| `update.check` | — | `{current, latest, hasUpdate, message?}`（`message` 优先于「已是最新版本」显示） |
| 事件 `market.syncProgress` | — | `{stage, message}`（宿主可推） |

> `sourceLabel` 可选：Python 版的索引还在旧仓库上，不能照抄 .NET 那句来源文案 ——
> 宿主给了就用它的，没给才用页面里的默认文字。

### 插件市场用到的 RPC

插件页（`pages/market.js`）的布局照 Python 版 `market_page.py` / `package_page.py` 来：
一个条目一张卡片，带状态徽章、版本变化、作者、说明、⚠ 原因、进度条、临时提示，
按钮按状态显隐。

**★ 但更新逻辑不进这一层** —— 两端本来就不一样：

| | .NET | Python |
|---|---|---|
| 索引来源 | 固定 by-net 仓库的 plugin 分支（raw → jsDelivr → github） | `market_source` 可选 **官方服务器 / GitHub / Gitee** |
| 安装 / 卸载 | `await` 完再回结果 | **丢给工作线程**，RPC 只回 `pending`，结果走事件 |
| 依赖包源 | `packages_source`（有多个源） | 同上 |

所以「索引来源」这个下拉是**宿主驱动**的：`sourceOptions` 给了才画、给几个画几个，
没给（.NET 返回空数组）整行都不出现。页面只显示宿主说的，不替任何一端做决定。

| 方法 | 参数 | 返回 |
|---|---|---|
| `market.status` | — | `{count, source, sourceLabel, sourceOptions:[{value,label}], lastSync, busy, entries:[MarketEntry]}` |
| `market.sync` | — | 同上 + `{log:[…]}`（索引同步完会顺带重扫本地状态） |
| `market.rescan` | — | 同上（不联网，只重扫本地插件目录） |
| `market.install` | `{id}` | `{ok, message, restartRequired}`；**异步宿主**回 `{ok, pending:true, message}` |
| `market.uninstall` | `{id}` | 同上 |
| `market.setEnabled` | `{id, enabled}` | `{ok, message, restartRequired}` |
| `market.updateAll` | — | `{items:[{id,name,success,message}], restartRequired, log:[…], entries:[…]}` |
| `market.setSource` | `{source}` | `{ok, source, sourceLabel}`（不支持切换的宿主原样回当前值） |
| `packages.status` | — | `{source, sourceLabel, sourceOptions, entries:[Package]}` |
| `packages.sync` | `{name?}` | 同上 |
| `packages.install` | `{name, manual?}` | `{ok, message}`；异步宿主回 `pending` |
| `packages.uninstall` | `{name}` | 同上 |
| `packages.setSource` | `{source}` | `{ok, source, sourceLabel}` |

`MarketEntry`：`{id, name, version, description, author, format, file, installed,
installedVersion, disabled, updateAvailable, status, problem, loadError}`
—— `status` 取值见下，`problem`（索引记录不合法）与 `loadError`（插件加载失败）
统一渲染成卡片上的「⚠ 原因」。

`Package`：`{name, version, installed, installedVersion, manual, usedBy:[…], status, statusLabel}`

状态与按钮显隐（照 Python 版，两端一致）：

| status | 徽章 | 显示哪些按钮 |
|---|---|---|
| `not_installed` | 未安装 | 装上 |
| `installed` | 已安装 | 禁用 / 卸掉 |
| `update` | 可更新 | 更新 / 禁用 / 卸掉 |
| `disabled` | 已禁用 | 启用 / 卸掉 |
| `failed` | 加载失败 | 禁用 / 卸掉 |
| `invalid` | 装不了 | 都不显示（但记录照样列出来，不静默丢掉） |

**★ 异步操作要如实回 `pending`。** 页面看到 `pending` 就**不会**下结论说「✓ 完成」，
只挂一句「正在安装…」，真正的结果由下面的事件带回来 —— 假装成功是错的。

宿主推给页面的事件（`host.on` 订阅）：

| 事件 | 载荷 | 用途 |
|---|---|---|
| `market.log` / `packages.log` | `{text}` | 运行日志（页面加时间戳后追加） |
| `market.progress` | `{id, percent}`（`-1` = 收起进度条） | 插件卡片进度条 |
| `packages.progress` | `{name, percent}` | 依赖包卡片进度条 |
| `market.done` | `{id, ok, message, restartRequired}` | 卡片上的临时提示；失败原因常驻 |
| `packages.done` | `{name, ok, message}` | 同上 |
| `market.dep` | `{id, stage, text, percent}` | 依赖下载进度（带文案） |
| `market.busy` / `packages.busy` | `{busy}` | 忙闲：按钮置灰 + 转圈 |
| `market.changed` | `{id, success, restartRequired}` | 兼容早先「安装完通知一声」的写法 |

### 无边框窗口用到的 RPC

设置窗口现在**无边框**：系统标题栏没了，`SettingsWebWindow` 用
`WindowStyle=None` + `ResizeMode=CanResize`（保留 WS_THICKFRAME，系统调整边框照旧有效），
Python 侧用 `Qt.FramelessWindowHint`。标题栏、三个窗口按钮都画在页面上
（`.app-titlebar`），画不画由宿主 `app.getVersion` 返回的 `window` 决定：

```json
"window": { "frame": "none", "resize": "native", "controls": ["minimize", "maximize", "close"] }
```

- `frame: "none"` → 页面给 body 打 `data-frameless`，标题栏当窗口镶边用；
- `resize`：`native` = 窗口自带调整边框（.NET），`js` = 由页面算边再报回来（Qt）；
- `controls`：要哪几个按钮。空数组就一个都不画（宿主保留原生标题栏时）。

| 方法 | 参数 | 返回 |
|---|---|---|
| `window.minimize` | — | `{ok}` |
| `window.toggleMaximize` | — | `{ok, maximized}`（页面据此换「最大化 / 还原」图标） |
| `window.close` | — | `{ok}`（宿主**先回包再关窗**，别把正在跑的调用栈拆掉） |
| `window.startMove` | — | `{ok}` → Qt 的 `QWindow.startSystemMove()` |
| `window.startResize` | `{edge: "left\|right\|top\|bottom"}`（可组合，如 `left-top`） | `{ok}` → `QWindow.startSystemResize(edges)` |

拖动有两条路，互不干扰：**WebView2 认 CSS 的 `app-region: drag`**（宿主开了
`IsNonClientRegionSupportEnabled`），那条路上页面收不到 `pointerdown`，也就不会去调
`window.startMove`；**QtWebEngine 不认**，于是 `pointerdown` 走到页面 → 调 RPC →
`startSystemMove()`。`.NET` 那条路是系统在拖，最顺。

### 二级对话框用到的 RPC

这六个对话框**在页面内以浮层打开**（不另开窗口），数据全靠下面这些方法。
字段名一律驼峰；Python 侧本地的 `as_weekday` / `morning_split` 要在桥里转成
`asWeekday` / `morningSplit` 再出境 —— 同一份 HTML 要能吃下两边。

| 方法 | 参数 | 返回 |
|---|---|---|
| `schedule.holidays.get` | — | `{holidays:[{start,end,name}], makeupDays:[{date,asWeekday}]}` |
| `schedule.holidays.add` | `{start, end, name}` | `{ok:true}`（即时写入） |
| `schedule.holidays.remove` | `{index}` | `{ok:true}` |
| `schedule.makeup.add` | `{date, asWeekday}` | `{ok:true}`（`asWeekday` 夹到 0..6） |
| `schedule.makeup.remove` | `{index}` | `{ok:true}` |
| `schedule.weekend.get` | — | `{morningSplit, afternoonPeriods:[{name,start,end}], courses:[…]}` |
| `schedule.weekend.set` | `{morningSplit, afternoonPeriods, courses}` | `{ok:true}`（`morningSplit` 留空回落 `12:00`） |
| `duty.get` | — | `{list:[名字], current, index}` |
| `duty.add` | `{name}` | `{ok:true}`（空名字报错「姓名不能为空」） |
| `duty.addMany` | `{names:[…]}` | `{ok:true, added}`（自动去空白项） |
| `duty.remove` | `{index}` | `{ok:true}` |
| `homework.get` | — | `{items:[{index,subject,content,date}], groups:[{subject,date,entries:[{index,content}]}], count}` |
| `homework.add` | `{subject, content, date}` | `{ok:true}` |
| `homework.update` | `{index, subject, content, date}` | `{ok:true}` |
| `homework.remove` | `{index}` | `{ok:true}` |
| `homework.clearSubject` | `{subject}` | `{ok:true, removed}`（整组清除，空白科目算「未分类」） |
| `homework.save` | — | `{ok:true}` |

> `homework.get` 的 `groups` 由宿主的分组逻辑给（**按科目**，`date` 取该科目第一个非空值），
> 但**空白科目要归一成「未分类」** —— 两端的服务实现细节不同，桥里对齐一下，
> 否则同一个科目在两端会显示成不同的组名，`clearSubject` 也就对不上了。

失败一律回 `{id, error:"原因"}`，页面会把它变成 `Promise` 的 reject。

### 页面 → 宿主的单向通知（没有回包）

`host.notify(event, payload)`，宿主收到的是 `{event, payload}`（注意：**没有 `id`**，
不能当成 RPC 去回包）。宿主侧要按「有没有 `event` 字段」先分流，再走 RPC 分支。

| 事件 | 何时发 | 载荷 |
|---|---|---|
| `ui.ready` | 外壳挂好、首屏画完 | `{page, bootError}`（`bootError` 为 null 表示数据都读到了） |
| `ui.error` | 页面脚本抛错 / Promise 未处理 / 启动时 RPC 失败 | `{phase, message, file?, line?}` |

宿主拿这两个事件做两件事：撤掉「正在加载」占位、停掉启动超时计时；以及把失败原因
写进兜底面板与诊断日志（详见下面的「白屏」那条坑）。

## 宿主接入（已落地）

两个项目都已接上本目录，且本目录是**唯一权威源码** —— 改这里，再同步到两端的 `ui/`，别两端各改。

### .NET（WPF + WebView2）

| 文件 | 作用 |
|---|---|
| `src/ClassDailyLand.App/Views/SettingsWebWindow.xaml(.cs)` | 外壳：WebView2 容器、虚拟主机映射、RPC 收发、启动看门狗、失败兜底面板 |
| `src/ClassDailyLand.App/Services/WebUiBridge.cs` | 桥：把 13 个 RPC 方法落到既有服务上 |
| `src/ClassDailyLand.App/ClassDailyLand.App.csproj` | 引 `Microsoft.Web.WebView2`；把本目录拷进输出的 `ui\` |
| `src/ClassDailyLand.App/App.xaml.cs` | `ShowSettings()` 优先开 Web 版，不满足条件回退原生 `SettingsWindow` |

界面用 `SetVirtualHostNameToFolderMapping` 映射成 `https://cdl.ui/`，绕开 `file://` 的权限与 CORS。
找不到 `ui/`、机器上没装 WebView2 运行时、或 Web 版自己起不来 → 回退原生设置窗口
（见 `SettingsWebWindow.IsAvailable()` 与兜底面板上的「改用原生设置窗口」）。

Web 版失败时：窗口里给出原因（内核缺失 / 导航失败 / 启动超时 / 渲染进程崩溃），
并把诊断信息追加到 `<配置目录>/webui-error.log`（运行时版本、界面目录、页面报错都在里面）。

### Python（PySide6 + QWebEngineView）

| 文件 | 作用 |
|---|---|
| `web_settings.py` | 外壳 + 桥：`WebSettingsDialog` 与 `_Bridge`，RPC 清单与 C# 侧逐条一致 |
| `gui.py` | `open_settings()` 走 `_make_settings_dialog()`：优先 Web 版，缺 QtWebEngine 时回退 `settings_dialog_v4` |
| `web_settings_selftest.py` | 无需界面 / 联网的自检：`python web_settings_selftest.py`（32 项） |

Python 侧直接以 `file://` 载入 `index-qt.html`（经典脚本，不会有 module 的 CORS 问题）。

### 宿主可以往 URL 上带的参数

| 参数 | 作用 |
|---|---|
| `chrome=native` | 隐藏页内标题栏，改用宿主的系统标题栏（两个宿主都带这个） |
| `page=island` | 直接落到某一页（托盘 / 右键菜单做「按页直达」用） |
| `theme=dark` | 只影响本次显示的主题，不回写设置 |
| `dialog=holidays` | 启动后直接把某个二级对话框打开（文档截图 / 自测用），见 `window.CDLDialogs` |

### 桥的实现要点（这几个坑两边都踩过）

- **启动必须「先挂外壳、后拉数据」。** 反过来做（先 `await` 几次 RPC 再挂外壳）会有一个
  致命后果：只要任一 RPC 失败 / 超时 / 宿主抛异常，`body` 就是空的 —— 而 `body` 的底色是
  `--solid-background-fill-color-base`（浅色下 `#F3F3F3`），用户看到的就是**一片白**，
  还完全不知道发生了什么。.NET 端报过的白屏正是这么来的。
  所以 `boot()` 里 `mountShell()` 在前，两个 `host.invoke` 在 `try/catch` 里在后，
  失败就在页面顶部挂一条 `win-infobar.is-error` 说明原因（`render.test.mjs` 的 [9] 是这条的回归用例）。
- **弹窗类 RPC 必须「先回包、再弹窗」。** `Window.ShowDialog` / `QDialog.exec()` 会阻塞消息循环，
  若在返回前就弹，页面侧会一直等到超时。两边都把动作推迟到回包之后 —— C# 用
  `Dispatcher.InvokeAsync(…, DispatcherPriority.Background)`，Python 用 `QTimer.singleShot`。
- **「提前提醒 / 时间偏移」不在 `AppSettings` 里**，它们挂在课表服务上
  （`IScheduleService.AdvanceMinutes` / `schedule_manager.data`）。所以 `settings.getAll`
  要把这两项合并进去、`settings.patch` 要单独分流，否则页面上改这两项会**静默失效**。
- **`settings.patch` 逐字段校验类型**，类型不符就跳过该项，不让一个坏值带崩整份配置。
- 失败一律回 `{id, error:"原因"}`，页面侧表现为 `Promise` 的 reject。
- **页面发的是「字符串」，C# 侧必须用 `TryGetWebMessageAsString()` 取。** 页面统一用
  `postMessage(JSON.stringify(x))`，发出去的是**字符串**；这种消息的 `WebMessageAsJson`
  会**再多包一层引号**（`postMessage('example')` → `"example"`，见 WebView2 官方文档）。
  拿它去 `JsonDocument.Parse`，根节点是 `String` 而不是 `Object`，调 `TryGetProperty` 直接抛
  `InvalidOperationException` —— 一条消息都解析不了，页面永远等不到回包、宿主永远等不到
  `ui.ready`，表现就是**白屏**（Python 走 QWebChannel 传的就是字符串，不过这一层，所以只有
  .NET 端中招）。`.NET` 侧 `ReadMessage()` 的兜底逻辑见 `SettingsWebWindow.UnwrapJsonString`。
- **诊断要能区分「页面没跑起来」和「跑起来了但消息没收懂」。** 两者的现象一模一样（都是白），
  但成因差得远。宿主记一条「收到页面消息 N 条 / 解析失败 M 条」是最省事的判据 ——
  N>0 而 `ui.ready` 没到，就一定是本侧的解析出了问题。
- 宿主显示兜底面板时，.NET 侧**必须把 WebView2 整个从可视化树里摘掉**
  （`RootGrid.Children.Remove(Web)` 并 `Dispose()`）——它是 HWND，绘制表面永远盖在 WPF 内容之上；
  而且只设 `Visibility = Collapsed` 并不保险：子窗口有可能在内核初始化**失败之后**才被创建出来，
  照样能盖住提示面板。

### 宿主别在「设置变了」的时候重做重活

设置服务一般只会告诉你「有东西变了」，不会说是哪个字段。最省事的写法就是收到事件就把
所有东西重新应用一遍 —— 于是拖动滑块时（约 150ms 一次）每一拍都全量重做。
.NET 端最终查出来「整个界面跟刷新了一样」的真凶是**主题几乎每拍都在重新应用**，
另外两处是次要成因：

- **★ 主题只在 `theme_mode` 真的变了的时候才应用。** .NET 侧的 `ThemeBridge.Apply` 写的是
  `Application.ThemeMode`，而它**不是依赖属性**（`typeof(Application)` 上没有
  `ThemeModeProperty` 字段），所以**写进去的值和原来一模一样也会被完整执行**。
  离屏 WPF 探针实测：反复写同一个值 20 次，窗口内容的 `Unloaded` / `Loaded` 各触发 20 次
  —— 视觉树被整个拆掉重建，单次约 53ms。对 WebView2 宿主就等于 `HwndHost` 被销毁重建，
  **页面真的重新加载一遍**，用户看到的就是「跟刷新了一样」。
  `App.xaml.cs` 现在留一份 `appliedThemeMode`，值没变就跳过。
  Python 侧的 `web_settings._apply_settings` 本来就只在补丁真的带上 `theme_mode` 时才重刷主题，
  所以这个问题只有 .NET 端有。
- `SettingsWebWindow` 每次都重写 `Profile.PreferredColorScheme` 与 `Web.DefaultBackgroundColor`。
  这两个是「写一次就让 WebView2 重画整块绘制表面」的 API，**值一样也一样**。
  现在用 `_appliedDark` 记住上次推过的值（原生 `SettingsWindow` 里的 `_lastAppliedDark`
  一直是这么做的）。
- `AppController.ApplySettings` 每次都 `RefreshContent()`（作业列表是「先 Clear 再逐行 Add」）、
  `NotifyIslandDirty()`（灵动岛 `AnimateTop` + `Tick`）、`RefreshTray()`（重建托盘菜单）。
  现在按变化量分级：岛相关字段一组签名、三个显示开关一组签名；主窗内容只在字体 /
  滚动参数 / 深浅色真的变了时才重建，宽度也没变就连几何都不重算。

**一句话判据：在 `Changed` 里做任何「重建 / 重绘 / 重设」之前，先问一句「这一项真的变了吗」。**

### `[hidden]` 会被自己写的 `display` 盖掉

`components.css` 开头有一条 `[hidden] { display: none !important; }`，**别删**。
`.win-btn`（`inline-flex`）、`.market-banner`（`flex`）这些构件都显式声明了 `display`，
而**作者样式会盖掉浏览器默认的 `[hidden] { display: none }`** —— 于是「给元素设了
`hidden` 却依然显示」。插件市场的按钮显隐全靠 `.hidden`（未安装只露「装上」、
已安装只露「禁用 / 卸掉」），漏了这条就会五个按钮全冒出来。

最容易踩的地方是：**`render.test.mjs` 查的是 `.hidden` 属性、不是计算样式**，
所以这个 bug 测试抓不到 —— 只能靠这条 CSS 兜住（本轮重写就漏过一次，是看截图才发现的）。

### 滑块为什么是四个 DOM 元素而不是 `input[type=range]` 自己画

`Slider` 的外观是「4px 圆角轨道 + 从左边缘画到圆点左边缘的强调色填充段 + 浅色外圆里套一个
强调色内点」。这个双层圆点用 `::-webkit-slider-thumb` 根本做不出来（伪元素只有一个盒子）；
而且 Chromium 对伪元素上的 `transform` + `transition` 处理得不好，会逐帧重新栅格化 ——
拖动时看过去一直在抖。

所以 `lib/controls.js` 里的 `slider()` 把真正的 `<input type=range>` 退成**纯交互层**
（`opacity: 0`，绝对定位铺满 `.win-slider-field`，继续负责拖动 / 点击跳转 / 方向键 / 无障碍语义），
外观全部交给 `.win-slider-rail` 里的四个元素画。位置只由一个 `--pct`（**0..1 的纯数字**）驱动，
填充段宽度和圆点位置共用同一个 CSS 表达式 `calc((100% - 22px) * var(--pct))` ——
JS 不需要知道控件有多宽，两个盒子都是绝对定位，拖动时不会牵动任何布局。

几何照 RinUI 的 `Slider`：轨道 4px 圆角 99（未填充 `--control-strong-fill-color-default`）、
把手 22×22 的浅色外圆（`handleSize 20` + 2）、内点 10×10 强调色
（`Math.round(20 * 0.55) & ~1`，RinUI 原式）。回归用例见 `render.test.mjs` 第 [3] 节 ——
其中一条专门断言 `components.css` 里**不能**再出现 `::-webkit-slider-thumb`。


> **这张对照图已删除。** 它量的是旧肤色（外圆 20 / 内点 12），本轮把手尺寸
> 改成 RinUI 的 22 / 10 之后对照就失效了；留着一张与代码不符的图比没有更误导。

## 测试（不需要浏览器）

```bash
npm test                       # 一把跑完下面三项
node tests/static-check.mjs    # 语法 + 图标名 + 设置键 + class 名 四处交叉校验
node tests/bridge.test.js      # 两只宿主的桥接协议（含错误回包、事件推送、Qt 握手、通知通道）
node tests/render.test.mjs     # jsdom 真渲染：八个页面点一遍 + 导航分组与子项 + 可展开卡片 +
                               #              主题磁贴 + 主题三档 + 控件回写 + 搜索 +
                               #              二级对话框（假期/周末/值日生/作业）+ 插件市场 +
                               #              无边框标题栏 + 启动失败不白屏
```

`render.test.mjs` 需要 `jsdom`（仅测试用，装在 `devDependencies`；产品代码保持零依赖）。

宿主那两端的桥各有自己的自检：Python 是 `python web_settings_selftest.py`（32 项），
.NET 侧由 `dotnet test` 的 211 个用例覆盖既有服务（桥本身很薄，逻辑都在服务里）。

## 还没做

- **课表管理 / 课表编辑器**、**状态测试** 这两个二级对话框还没搬（另外四个已搬完，
  见上面「二级对话框用到的 RPC」）。规格已从原实现逐条对好（含课表网格的列结构、
  保存校验文案、导入预览子对话框、状态试算的参数与结果映射），下一轮直接写。
- 主窗口（右侧班级日常）、下拉面板、灵动岛（P3 / P4）**有意保持原生**，尚未 Web 化
- 插件 API 尚未提供 HTML 界面扩展点（P5）

## 二级对话框是怎么组织的

六个对话框本来都是两端各自的独立窗口，现在都在设置窗口内部以浮层打开 ——
**两个宿主都不用多写一行「开窗」代码**，视觉也天然一致。

- 外壳在 `lib/editors.js` 的 `open()`：遮罩 + 面板 + 固定底栏，内容区自己滚；
  `tell()` / `ask()` 是「一句提示」「确认框」的 Promise 版本，会叠在上层。
  ESC 只关最上面那层（靠一个模块级的栈，不是每个对话框各挂一个监听）。
- 挂载点 `#modal-root` 是**懒建**的：设置页 boot 时会 `document.body.replaceChildren(shell)`，
  早写在 HTML 里的占位节点会被一起换掉。
- 作业编辑器有**两种用法**（与原生一致）：独立的「编辑作业」对话框带取消/确认；
  **内嵌**进设置中心的「作业」页时不带按钮、改动即时生效 —— 本体只有一份。
- `settings.js` 的 `openDialog(id, title)` 先查 `window.CDLDialogs` 注册表，
  没有再回落到宿主的原生对话框（`dialog.open`）；两边都没有就如实弹一句说明，
  不静默失败 —— 点了一下什么都没发生是最糟的。
