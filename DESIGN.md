# MiteProxy 项目设计方案

| 项目 | 内容 |
|---|---|
| 产品名 | MiteProxy（类 Fiddler 抓包 + Mock 工具） |
| 交付形态 | macOS + Windows 双平台桌面客户端（PySide6 + PyInstaller 本地构建） |
| 内核 | mitmproxy（`DumpMaster` 内嵌，同进程运行） |
| 文档版本 | v1.14（2026-10-14） |
| 修订 | v1.1：交付范围扩展为 macOS + Windows 双平台（方案 A 本地构建）；新增流量过滤设计（域名过滤 / 隐藏 CONNECT / 隐藏 Image）<br>v1.2：域名过滤支持黑名单/白名单双模式（空白名单不过滤、模式切换保留关键词）<br>v1.3：新增流量搜索设计（Ctrl+F、URL/Headers/Body 范围、大小写切换、命中高亮、大 body 索引策略）<br>v1.4：Mock 支持本地文件响应（请求时读取）、模拟延迟、异常状态码预设；FARX 映射补充 x-replywithfile 与 latency<br>v1.5：①body 解码统一默认 UTF-8（弃用 mitmproxy latin-1 默认，`app/textutil.py`，文本类 mock 响应自动补 charset）；②新增请求重放（3.6：副本 + ClientPlayback，Ctrl+R / 右键菜单 / 编辑并重放对话框，REPLAY 徽标），重放从非目标移入范围<br>v1.6：①修正代理归属——仅 MainWindow 持有一个 ProxyService，入口不再自建（此前入口的裸代理会抢占端口，导致打包后 mock/捕获全失效，已加防回归测试）；②启动即自动开代理，端口占用时弹窗并复位按钮；③窗口几何持久化；④图标（icon.icns/icon.ico）与 Info.plist 落地；⑤补 macOS 冻结产物验收记录<br>v1.7：①导出加「完整响应（Headers+Body）」格式（3.2.3）；②列表支持列排序 + 多选批量复制/导出（3.2.4）；③会话保存与恢复（3.7，JSONL + 退出自动快照）；④网络模拟（3.8，弱网限速档位 + 域名映射到本地）<br>v1.8：body 结构化视图（3.2.5）——JSON 缩进 + 语法着色、WebForm 表单表格、自动/原文/JSON/表单/十六进制五模式；顺带修正 3.2 中"body 支持十六进制/文本切换"的表述（此前代码是自动判定、无手动切换控件）<br>v1.9：①列表顺序（到达顺序 / 新的在顶部）+ 自动滚动（3.2.6）；②body 视图加图片预览与换行开关，并补三道大内容闸门（深嵌套崩溃、大 JSON 因截断丢格式化、超长单行换行卡死，3.2.5）；③压缩 body 的"已解压"提示与兜底解压（3.2.7）；④WebSocket 抓包与消息列表（3.9）<br>v1.10：新增**工具页**（3.10）——编码转换（对齐 Fiddler TextWizard，27 种转换）+ JSON 格式化（对齐 json.cn，精确错误定位 + 树形浏览 + JSONPath 提取）；JSON 着色器从 detail_panel 抽出为 `app/ui/highlight.py` 供两处共用<br>v1.11：①Mock 命中计数 + 会话标记/备注（3.3.4）；②Map Local 本地目录映射 + 证书页二维码（3.8.3）；③**重放并对比**（3.6.1——副本 id 精确关联，JSON 键级 diff + 文本行级 diff 双轨，`app/jsondiff.py` 纯函数引擎）；④工具页加**JSON 比对**子页（3.10.3，复用同一 diff 引擎）；⑤JSONPath 补聚合函数 `length()`/`min()`/`max()`（3.10.2，对整个结果集生效）；⑥**WS 消息写入会话文件并可恢复**（3.9——`ws_messages` 随记录落盘，条数 2000 / 预算双闸，旧文件兼容，summary 计数按实际存储数回填）<br>v1.13：**系统代理自动接管**（3.1.1，对齐 Fiddler「Act as System Proxy」——启动代理自动把系统 HTTP/HTTPS 代理指向本应用，停止/退出/崩溃恢复全路径还原，原始配置逐项记录写回；macOS networksetup + 提权重试，Windows 注册表路径未实机回归）<br>v1.12：①Mock 规则支持**按请求方法匹配**（3.3.5，任意/GET/POST/… 下拉，比 Fiddler 免拼正则）；②Mock 支持**重定向到其他 URL**（3.3.6，规则级 Map Remote，支持 $1 替换，防指回代理自身死循环）；③JSON 树视图**懒加载**（3.10.2，展开才构建子节点，单层 5000 / 全局 5000 双上限）；④工具页新增**API 调试**子页（3.10.4，构建请求直发 + 右键从流量带入完整请求，响应复用 BodyPane 六模式渲染）；⑤**bug 排查修复 12 项**（settings 数字崩溃、流式响应丢行、非 UTF-8 会话字节篡改、代理 stop/start 竞态、规则重载行号错位、规则错误不可见、POST 空 body 无 Content-Length、WS 溢出保留最旧、窗口几何死路径、保存 tmp 残留、CA 损坏未捕获、导入信号误发）；⑥新增使用教程 TUTORIAL.md<br>v1.13b：①body 视图改 Fiddler 式**互斥按钮条**（去下拉）；②流量页**左右/上下布局可切换**（默认左右，工具栏「布局」下拉，比例换算 + splitter_state 持久化）；③Windows 打包输出改 **zip**（exe + `_internal\` 依赖目录，解压即用）<br>v1.14：**主题深浅色**（3.11，`app/ui/theme.py`）——默认跟随系统，菜单「外观」可切浅色/深色；语义色 token 收拢 + `theme.dynamic` 就地更新 + `_retheme` 监听广播；JSON 着色双配色已有 |

---

## 1. 项目概述

### 1.1 背景

本地 Web/移动端开发测试中，需要一个轻量的抓包工具，核心诉求就两个：**能抓包**（HTTP/HTTPS，含手机 App 流量）、**能 mock**（对命中规则的请求直接返回预设数据）。Fiddler 是 Windows 老牌工具但生态重、规则迁移成本高；本项目基于 mitmproxy 做一层薄壳，提供接近 Fiddler 的核心体验，并支持直接导入 Fiddler 既有规则，降低迁移成本。

### 1.2 目标

- **G1 抓包**：HTTP/HTTPS 流量捕获、列表展示、请求/响应详情查看；CA 证书一键导出，支持手机安装后抓 App 流量；支持按域名过滤（黑名单/白名单双模式）、按类型隐藏（CONNECT / Image）、按关键字搜索（URL / Header / Body）；列表可配置保存条数（100~5000）、支持列排序与多选、**顺序切换（新的在顶部）与自动滚动**（见 3.2.6）；body 支持结构化视图（JSON 缩进着色 / WebForm 表单表 / **图片预览** / 原文 / 十六进制）与换行开关，默认按 content-type 自动挑（见 3.2.5）；**压缩内容（gzip/br/zstd）自动解压并注明**（见 3.2.7）；支持复制为 cURL、导出会话（HAR / 原始报文 / 完整响应 / 响应 Body），**单条与多选批量均可**。
- **G1.1 WebSocket**：捕获 WebSocket 连接与逐条消息（方向 / 类型 / 长度 / 内容），详见 3.9。
- **G2 Mock**：可视化规则管理（增删改、启用/禁用）；支持精确、通配符、正则三种 URL 匹配；命中后直接返回自定义响应——**内联内容或本地文件**、**任意状态码**（含 4xx/5xx 异常码，预设快捷键）、**可设模拟延迟**；命中即造 response，请求不发给真实服务器。
- **G3 请求重放**：原样重发已捕获请求；或编辑 method/URL/headers/body 后重发（对齐 Fiddler Replay / Edit and Replay）；**重放并对比**——重放响应到达后自动弹出对比视图，旧响应 vs 新响应一键看差异（3.6.1）。
- **G4 规则迁移**：支持导入 Fiddler 的 `.farx` 规则包与 `CustomRules.js` 脚本规则，导入前可预览、可勾选。
- **G5 交付形态**：PyInstaller 打包为 macOS `.app` + Windows zip（onedir 目录整体压缩：`MiteProxy.exe` + `_internal\` 依赖文件夹，解压即用免安装，脚本自动产出 `MiteProxy-v<版本>-windows-x64.zip`；本地构建，脚本随项目提供）。
- **G6 会话保存与恢复**：把当前抓到的会话存成文件、下次打开继续用（对齐 Fiddler Save All Sessions / Load Sessions）；退出时自动快照，下次启动可一键恢复。恢复后仍是**活会话**，可查看、导出、重放。
- **G7 网络模拟**：弱网限速（档位 / 自定义延迟与速率）复现 loading 态与超时；域名映射把线上域名转发到本地服务，用于「线上前端 + 本地后端」联调。

### 1.3 非目标（明确不做）

以下功能刻意不做，控制范围：

- 断点调试（Breakpoints）、会话重放响应编辑（Composer 手工构造全新请求——编辑已有请求后重放已做，见 3.6）
- WebSocket **帧级**（分片帧、ping/pong 等控制帧）展示——消息级已做（见 3.9，mitmproxy 本身会先把分片重组再抛给钩子）；protobuf/msgpack 等二进制协议解码不做
- 上游代理链、脚本自动化（FiddlerScript 全量兼容）
- 多标签页、多用户/权限（过滤做域名 + 类型隐藏；搜索做 URL/Header/Body 关键字；均不做正则查询）
- Linux 打包（架构上无阻碍，本期交付 macOS + Windows）
- **第三方**会话格式的导入（HAR、Fiddler `.saz`）——自有 JSONL 会话格式的保存/恢复已做（见 3.7）；导出已做（见 3.2.3）
- 真逐块限速（弱网模拟只做"按体积折算总传输时间的一次性等待"，见 3.8.1）
- 正向代理链 / 反向代理 / pac 脚本（域名映射只做 Map Remote 的前缀改写）

### 1.4 目标用户与场景

- 本机开发者：调试本地/测试环境 API，快速 mock 边界数据（错误码、空列表、超时文案）。
- 移动端测试：手机配代理 + 装 CA 后抓 App 流量，对特定接口返回 mock 数据验证客户端表现。
- Fiddler 老用户迁移：把 AutoResponder 规则导出 `.farx`，一键导入继续用。

---

## 2. 总体架构

### 2.1 架构图

```
┌──────────────────────────── Qt 主进程 (PySide6) ────────────────────────────┐
│                                                                             │
│  ┌──────────────┐   ┌──────────────────┐   ┌───────────────────────────┐   │
│  │  MainWindow  │   │  MockRulesPanel  │   │  NetworkPanel             │   │
│  │  (流量列表/   │   │  (规则 CRUD/开关) │   │  (弱网档位/域名映射表)      │   │
│  │   详情面板)   │   └────────┬─────────┘   └────────────┬──────────────┘   │
│  └──────┬───────┘            │                          │                   │
│         │ Qt Signals         │ 读写                      │ changed 信号       │
│         ▼                    ▼                          ▼                   │
│  ┌─────────────────────────────────────┐      ┌───────────────────────┐    │
│  │        RuleStore (规则中心)          │◄─────│  FiddlerImporter      │    │
│  │  内存规则 + rules.json 持久化(加锁)   │      │  FARXParser / JSParser│    │
│  └──────────────┬──────────────────────┘      └───────────────────────┘    │
│                 │ 同一进程内直接访问                                        │
│  ┌──────────────▼──────────────────────────────────────────────────────┐   │
│  │              mitmproxy DumpMaster (asyncio 线程)                     │   │
│  │  ┌─────────────┐  ┌──────────────┐  ┌──────────────────────────┐    │   │
│  │  │ Proxy Core  │  │ MockAddon    │  │ CaptureAddon             │    │   │
│  │  │ (HTTP/HTTPS │  │ request hook │  │ response hook            │    │   │
│  │  │  解密/证书)  │  │ 命中即造 resp│  │ 推 flow 到 UI            │    │   │
│  │  └─────────────┘  └──────────────┘  └──────────────────────────┘    │   │
│  │  ┌─────────────┐  ┌──────────────┐                                  │   │
│  │  │ ThrottleAddon│ │ MapRemote     │  ← 官方内置 addon，靠 map_remote  │   │
│  │  │ response hook│ │ (官方)         │     选项驱动（3.8.2）            │   │
│  │  │ 弱网延迟     │ │ 域名前缀改写   │                                  │   │
│  │  └─────────────┘  └──────────────┘                                  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              │ 监听 127.0.0.1:8888                          │
└──────────────────────────────┼─────────────────────────────────────────────┘
                               │
              手机/浏览器设代理 → 电脑IP:8888
              CA 证书下载：电脑IP:8081（内置简易 HTTP 服务）
```

### 2.2 技术选型

| 层 | 选型 | 理由 |
|---|---|---|
| 代理内核 | mitmproxy 11.x（Python 包） | 协议栈、HTTPS 解密、证书体系全部现成；Addon API 是官方扩展点，map local 类功能官方自己就用 `request` hook 造 response 实现，路线已验证 |
| 嵌入方式 | `mitmproxy.tools.dump.DumpMaster` 编程式实例化 | 不用 `mitmdump` 子进程，免去 IPC；插件与 UI 同进程，共享 RuleStore 对象 |
| GUI | PySide6（Qt for Python） | 跨平台、原生观感、打包成熟；信号槽机制天然适合跨线程 UI 更新 |
| 打包 | PyInstaller | 社区标准方案，`--windowed` 直接产 `.app` |
| 规则存储 | JSON 文件（`~/.miteproxy/rules.json`） | 人眼可读、手改方便、git 友好；规则量级（几十条）无需数据库 |

### 2.3 模块划分

| 模块 | 文件 | 职责 |
|---|---|---|
| 入口 | `app/main.py` | 仅启动 Qt 应用、显示主窗口、调用 `window.start_proxy()`、绑定退出清理。**不持有代理实例** |
| 主窗口 | `app/ui/main_window.py` | **代理唯一持有者**：装配 MockAddon/CaptureAddon 的 `ProxyService`，提供 `start_proxy()/stop_proxy()` |
| 代理服务 | `app/proxy.py` | DumpMaster 生命周期管理（启动/停止/端口）、证书定位 |
| 捕获插件 | `addons/capture.py` | `response` hook：flow → UI；另提供 `load_flows()` 供会话恢复整体灌入 |
| Mock 插件 | `addons/mock.py` | `request` hook：规则匹配 + 造 response |
| 弱网插件 | `addons/throttle.py` | `response` hook：按配置 `await asyncio.sleep()` 施加延迟 |
| 会话模块 | `app/session.py` | 会话 JSONL 保存/恢复、退出快照（纯函数，无 Qt） |
| 网络逻辑 | `app/network.py` | 弱网档位与延迟折算、域名映射 spec 生成（纯函数，无 Qt） |
| 规则中心 | `app/rules.py` | 规则模型、匹配算法、JSON 读写、线程安全 |
| FARX 导入 | `addons/importers/farx.py` | `.farx` XML → 规则对象 |
| JS 导入 | `addons/importers/jsscript.py` | `CustomRules.js` → 规则对象（启发式） |
| UI | `app/ui/*.py` | 主窗口、流量表格、详情面板、规则页、网络模拟页、各对话框 |
| 证书服务 | `app/certserver.py` | 8081 端口证书下载页（局域网手机用） |

> **代理归属唯一（Gate 6 修正）**：早期版本入口与主窗口各建了一个 `ProxyService`，
> 入口那个**不带任何 addon** 且开机即监听端口，导致实际运行的是裸代理——
> 能连上游，却既不 mock 也不向界面推流量（源码冒烟因直接构造 MainWindow 而漏掉）。
> 现约定：代理只由 `MainWindow` 持有，入口通过 `start_proxy()` 启动，
> 并由 `tests/test_entrypoint.py` 守住这条不变量。

### 2.4 线程模型（关键设计）

mitmproxy 的 DumpMaster 跑在自己的 asyncio 事件循环里，**不能**直接在代理线程操作 Qt 控件。方案：

1. **代理线程**：普通 `threading.Thread` 内 `asyncio.run(master.run())`。
2. **代理 → UI**：CaptureAddon 在 `response` hook（asyncio 线程）中把 flow 摘要打包成纯数据 dict，通过 `pyqtSignal` 发射（Qt 跨线程用队列连接，自动 marshalling），UI 线程槽函数更新表格。
3. **UI → 代理**：Mock 匹配完全在代理线程内完成，RuleStore 的读写加 `threading.RLock`；UI 改规则只碰 RuleStore，不直接碰 master。
4. **body 传输**：大 body（如图片）只传摘要 + 截断预览（如前 64KB），完整内容按需从 flow 对象懒取——flow 对象由 CaptureAddon 以 `id -> flow` 字典持有，UI 通过 flow id 回查。
5. **UI → mitmproxy 选项**（弱网/域名映射用）：`master.options` 的变更会触发 addon 的 `configure` 钩子，**不能**从 UI 线程直接改。`ProxyService.update_options(**opts)` 经 `loop.call_soon_threadsafe` 投到事件循环线程执行；代理未运行时只记进 `_options`，下次 `start()` 前 `master.options.update(**self._options)` 一次性带上（要放在 `run()` 之前，否则第一个请求就漏了映射）。返回值告诉 UI 是「已立即生效」还是「代理启动后生效」。
6. **配置对象整体替换**：弱网配置这类会被 asyncio 线程高频读取的对象，UI 侧一律 `set_config(新建对象)` 而不是原地改字段——属性赋值是原子的，跨线程读到的永远是完整配置，不会读到半更新状态。

> 这条是整套方案最容易翻车的地方：Qt 控件只能在主线程碰，mitmproxy 回调永远在 asyncio 线程。所有跨边界的数据都走信号，不用共享控件引用。

---

## 3. 功能设计

### 3.1 代理与抓包

- **监听**：默认 `127.0.0.1:8888`（对齐 Fiddler 默认端口），界面可改端口。
  端口输入框用 `editingFinished`（回车/失焦）提交而非 `valueChanged`——后者每敲一个
  数字触发一次，运行中会连续重启代理。**运行中改端口即时生效**：先还原系统代理
  （直接重接管会把旧端口存成「原始值」，还原就错了）→ 重启代理线程 → 按新端口
  重新接管 → 证书服务静默重启；新端口被占用由 `_verify_proxy_started` 兜底弹窗。
  随附修复 `ProxyService.stop()` 的 master 未就绪竞态（线程刚启动就停止时
  shutdown 无人接收，会滞留到超时）。
- **HTTPS 解密**：mitmproxy 默认开启；CONNECT 隧道内动态签发证书。CA 在首次启动时自动生成于 `~/.mitmproxy/`。
- **抓包范围**：全部 HTTP/HTTPS；WebSocket 仅记录建立连接的首个会话（不展开帧，符合非目标）。
- **代理开关**：工具栏开始/停止按钮控制 `master.shutdown()`；停止后列表保留、可清空。

#### 3.1.1 系统代理自动接管（v1.13，`app/sysproxy.py`，对齐 Fiddler「Act as System Proxy」）

开启抓包（启动代理）即自动把本机系统 HTTP/HTTPS 代理设为 `127.0.0.1:<port>`，流量直接进列表；
关闭抓包（停止代理）、退出应用、或代理启动失败，都**自动还原**接管前的系统代理——
不抓的时候本机就是默认网络配置。

- **逐项记录、精确还原**：接管前对每个网络服务分别记录 HTTP/HTTPS 代理的原始
  enabled/server/port，还原时逐项写回——用户已有的代理配置（如 Clash 的 7890）不会丢。
- **macOS**：`networksetup`；权限不足时弹一次密码框提权重试（osascript administrator
  privileges，每次会话最多问一次）。Windows：HKCU Internet Settings 注册表
  （ProxyEnable/ProxyServer，未经实机回归）。
- **崩溃恢复**：接管状态落盘 `~/.miteproxy/sysproxy.json`，进程异常退出没还原的，
  下次启动 `recover_if_needed()` 补还原。
- **线程模型**：接管/还原在后台线程跑（networksetup 逐服务多条命令，可能数秒），
  经 `sysproxy_done` 信号回主线程；`_sysproxy_lock` 保证「接管未完成就停止」时
  仍能按完整记录还原。工具栏「设为系统代理」复选框控制是否自动（默认开），
  运行中切换即时生效。工具栏排列：列表操作（清除/保存数量）→ 抓包选项
  （自动滚动/设为系统代理）→ 代理控制（启动/端口）→ 视图（顺序/布局）→
  低频功能靠右（证书服务/导出 CA 证书）。

### 3.2 流量列表与详情

列表列：# | 方法 | 主机 | 服务器 IP | 路径 | 状态码 | 大小 | 耗时 | 标记。

- **服务器 IP**：上游服务端的实际 IP。取值顺序 `server_conn.peername`（已建连的真实对端，一定是解析后的 IP）→ `server_conn.address`（未建连时可能是原始域名，仅当形如 IP 才采用）。CONNECT 隧道请求、以及被 mock 直接短路（从未连上游）的请求取不到，显示 `-`。`Ctrl+F` 的 URL 范围把该列一并纳入匹配。
- **标记**：命中 mock 规则的请求显示 `MOCK` 徽标 + 规则名（加粗）；HTTPS 显示锁图标。
- **mock 命中整行着色**：背景 `#fff4d6`、文字 `#412402`，行内一眼可辨。**同时设底色与字色**——只换底色在深色主题下会让默认浅色文字落在浅底上，反而看不清。状态列保留绿/蓝/橙/红语义色（优先级高于行色），「标记」列仍显示规则名。只重放未命中 mock 的行（`REPLAY`）**不着色**，避免与 mock 命中混淆。
- **详情面板**：请求与响应两分栏（方法/URL/headers/body）。body 默认按 content-type 自动挑视图（JSON 格式化 / 表单表格 / 原文 / 十六进制），也可用视图按钮条手动切换（见 3.2.5）。
- **布局方向**：流量列表与详情区之间是 `QSplitter`，默认**左右**（Fiddler 风格，列表在左、body 在右），工具栏「布局」下拉可切**上下**。切换时按当前比例换算到新方向，不会把某一边挤没；方向与分隔条位置随 `settings.json` 持久化，重启保持（见 4.3）。分隔条手柄加宽到 6px，好抓。
- **body 解码策略**（`app/textutil.py`）：按 content-type 声明的 charset 解码；**未声明时默认 UTF-8**——不使用 mitmproxy `get_text()` 的 latin-1 默认（中文内容会变乱码）；解码失败走十六进制视图。mock 引擎对文本类响应自动补 `charset=utf-8`，保证往返一致。
- **保存条数**：工具栏下拉选择 `100 / 200 / 500 / 1000 / 2000 / 3000 / 5000`（上限 5000），随 `settings.json` 持久化（见 4.3），启动即恢复。超出上限后 FIFO 丢弃最旧一条，并**精确停在上限**（旧实现批量淘汰 10% 会掉到上限以下，与用户设定的数字不符）。
  - 改小上限时列表立即从最旧一端裁剪，给即时反馈；
  - `CaptureAddon` 另有一份 flow 对象缓存，`response()` 跑在 mitmproxy 的 asyncio 线程——UI 线程只改上限数值（赋值原子），实际淘汰等下一次 `response()` 内自行完成，**代理停止时**才允许 UI 直接裁，避免跨线程遍历 dict；
  - 保存条数只影响保留量，不改变抓取行为；重启应用不恢复历史（范围内不做持久化）。

#### 3.2.1 流量过滤（视图层）

**设计原则：过滤只影响显示，不影响抓取与 mock。** flow 全量进存储，UI 按过滤条件显隐——切过滤不丢数据，关掉过滤立刻看到全部。这与 Fiddler 的 Filters 行为一致。

三个过滤维度：

| 维度 | 控件 | 判定逻辑 |
|---|---|---|
| 域名过滤 | 模式单选（黑名单 / 白名单）+ 输入框（多关键词逗号分隔） | 见下方语义表 |
| 隐藏 CONNECT | 复选框 | `flow.request.method == "CONNECT"` |
| 隐藏 Image | 复选框 | 响应 `content-type` 以 `image/` 开头，**或** URL 路径以 `.png/.jpg/.jpeg/.gif/.webp/.svg/.ico/.bmp` 结尾 |

**域名过滤语义**：

| 模式 | keywords 非空 | keywords 为空 |
|---|---|---|
| 黑名单（隐藏这些域名） | host 不含任何关键词的才显示 | 全部显示 |
| 白名单（只显示这些域名） | host 含任一关键词才显示 | 全部显示（等同未启用） |

- 模式切换时**保留关键词**，不用重输；空白名单不过滤，避免清空输入框后界面全空。
- 关键词匹配按 host 子串包含（大小写不敏感），如 `example.com` 同时命中 `www.example.com` 与 `api.example.com`。

- **可扩展结构**：类型隐藏内部维护一个"隐藏类型集合"（目前 `{CONNECT, IMAGE}`），后续加 CSS/JS/Font/Video 只需往集合加项 + 加复选框，过滤管线不变。
- **实现**：`QSortFilterProxyModel` 子类，`filterAcceptsRow` 中读取 `FilterConfig`；配置变更时 `invalidateFilter()` 全表重算（5000 条规模无感）。
- **状态反馈**：状态栏常驻 `显示 X / 共 Y 条`，过滤生效时高亮，避免"流量突然没了"的困惑。
- **持久化**：过滤配置随 `settings.json` 保存（见 4.3），重启后恢复。

#### 3.2.2 流量搜索

与过滤共用同一条视图管线（同一个 `QSortFilterProxyModel`，AND 组合），交互对齐 Fiddler 的 Ctrl+F 肌肉记忆：

- **唤起**：`Ctrl+F` 在流量表格顶部弹出搜索栏；`Esc` 关闭并恢复显示。
- **输入即搜**：关键字输入 debounce 300ms 后过滤列表；`Enter` / `Shift+Enter` 在匹配项间循环跳转并选中。
- **搜索范围**（复选框，默认仅 URL）：
  - `URL`：方法 + host + 服务器 IP + path + query
  - `Headers`：请求与响应 headers（名 + 值）
  - `Body`：请求与响应 body
- **大小写**：默认不敏感，提供 `Aa` 切换按钮。
- **匹配反馈**：状态栏显示 `匹配 X / 共 Y 条`；选中会话在详情面板中**高亮所有命中文本**（headers 与 body 视图同步）。
- **大 body 策略**：body 超过 512KB 的 flow 仅索引前 512KB（与预览同源，不额外占内存），搜索此类 flow 时状态栏注明"大文件仅索引前 512KB"。
- **不做持久化**：搜索是临时动作，关闭即丢弃，不进 `settings.json`。

#### 3.2.3 复制与导出（对齐 Fiddler 的 Copy / Save 菜单）

右键选中会话即可复制或导出：

| 菜单项 | 快捷键 | 行为 |
|---|---|---|
| 重放请求 | `Ctrl+R` | 原样重发（见 3.6） |
| 编辑并重放… | — | 改 method/URL/headers/body 后重发 |
| 复制为 cURL (bash) | `Ctrl+Shift+C` | 请求转成可执行的 curl 命令，POSIX 单引号格式 |
| 复制为 cURL (Windows cmd) | — | 同一命令的 cmd 单行版（值用双引号，内层 `"` → `\"`） |
| 仅复制 URL | `Ctrl+Shift+U` | 复制 `pretty_url` |
| 导出选中会话… | `Ctrl+E` | 保存对话框，用「文件类型」下拉切四种格式 |
| 导出完整响应（Headers+Body）… | `Ctrl+Shift+E` | 跳过格式选择，直接以「完整响应」格式调起保存对话框 |

**多选批量**（见 3.2.4）：选中多条时，菜单项标注 `（N 条）`，cURL / 仅 URL / 导出都作用于全部选中项。
多选下的落盘规则：cURL 用 `# --- 第 i/N 条 · 起行 ---` 分段；HAR / 原始报文 / 完整响应在文件内逐条追加并带同样的分段横幅；
「仅响应 Body」**只能单条**（一个文件装不下多条 body，UI 直接弹提示拦住）。

导出只做常用四种：

| 格式 | 扩展名 | 内容 |
|---|---|---|
| HAR 归档 | `.har` | HAR 1.2 单条 entry；浏览器 DevTools、Charles、Fiddler 都能打开 |
| 原始 HTTP 报文 | `.txt` | 请求 + 响应两段完整报文（起行 + headers + body），对齐 Fiddler 的 Save → Raw |
| 完整响应 | `.txt` | **仅响应**：起行 + 全部 headers + 空行 + body 原始字节，对齐 Fiddler 的 Save → Response → Entire Response |
| 仅响应 Body | 按 content-type 推断 | 响应原始字节，二进制原样落盘（不重编码） |

实现要点（`app/export.py`，**纯函数、无 Qt 依赖**，便于逐字单测）：

- **cURL 跳过 `Host` 与 HTTP/2 伪头**（`:method`/`:authority`…）：前者由 curl 按 URL 现算，后者是协议内部头；其余抓到的头原样带上。非 GET 才输出 `-X`；body 一律用 `--data-binary`（`-d` 会吞换行、把 `@` 当文件）——文本内联，二进制退化为 `@payload.bin`。
- **body 解码复用 `app/textutil.py`**：声明 charset 优先 → 默认 UTF-8 → 失败改走 base64/占位，中文不乱码、二进制不损坏。
- **HAR `timings` 用 mitmproxy 三段真实时间戳拆分**：`send` = 请求上传、`wait` = 服务端处理、`receive` = 响应下载；时间戳缺失（合成流）时退化为全部计入 `wait`，并始终保证 `time == send + wait + receive`（HAR 规范要求）。
- 二进制响应在 HAR 中写 `content.encoding = "base64"`（规范做法）；mock 命中写入 entry 的 `comment`；有服务端 IP 时写 `serverIPAddress`。
- **完整响应以 bytes 拼装**：头部按 HTTP 线格式用 CRLF 分隔、末尾空行后直接拼 body **原始字节**——所以二进制响应不会被重编码或截断，文本响应也能一眼看到头。无响应的会话（请求进行中）该格式导出为空，UI 层改用提示框拦住而不是落一个空文件。
- 默认文件名由 `host + path` 生成（如 `api.example.com_v1_user.har`）；完整响应用 `.response.txt` 后缀与「原始 HTTP 报文」的 `.txt` 区分，避免同名覆盖；Body 导出优先用 URL 末段名 + content-type 扩展名，用户自己写了扩展名则尊重、不重复追加。
- **多选时文件名加 `_N条` 后缀**：单条导出不加（保持与旧版逐字一致）；批量导出时默认名形如 `api.example.com_v1_user_3条.har`，一眼能看出这不是单条。
- 单条导出路径与旧版**逐字节一致**（`as_flow_list()` 把单条包成单元素列表，`build_*` / `default_filename` / `ensure_suffix` 内部统一走列表分支）——所以补多选能力没有改动既有行为。

#### 3.2.4 列表排序与多选

**排序**：表头点击即按该列排序（对齐 Fiddler），`#` 列始终显示「抓包到达序号」——排序只改显示顺序，不改这个号，所以排序后仍能一眼看出真实先后。

- **走代理模型的排序角色，而不是显示文本**：`FlowStore` 增加 `SORT_ROLE`（`Qt.UserRole + 1`），数值列（`#` / 状态码 / 大小 / 耗时）给数值、文本列（方法 / 主机 / IP / 路径）给小写串、缺失给空串或 0；`FlowFilterProxyModel.setSortRole(SORT_ROLE)`。
  这样避免两个经典陷阱：`1.3 MB` 与 `812 B` 按字符串排会把 `812 B` 排到前面；`9.0` 与 `10.0` 会排成 `10.0 < 9.0`。
- **`lessThan()` 做类型分组**：`_rank` 把值分成 0=数值 / 1=字符串 / 2=None，先比 rank 再比值——否则混合类型会 `TypeError: '<' not supported between 'int' and 'str'`，直接崩在排序里。只有 None 沉底，空串按普通字符串处理（升序时 `-` 与状态 0 排最前，与 Fiddler 一致）。
- `setDynamicSortFilter(True)`：新会话到达时自动落到正确位置，不用手动重排。
- 表格 `setSortingEnabled(True)`，并在覆写的 `setModel()` 里清掉初始排序指示器（Qt 默认会在第 0 列挂一个隐藏的升序排序，会让「刚打开就少了一条」这种怪现象出现）。

**多选**：`QAbstractItemView.SelectionMode.ExtendedSelection`（`Ctrl`/`Shift` 点选，`Ctrl+A` 全选）。

- 加两个小访问器：`_selected_flows()` 按**列表当前可见顺序**返回选中会话（用 `selectionModel().selectedRows()` 再 `mapToSource()` 回查 `FlowStore` → `CaptureAddon.get_flow()`），`_selected_flow()` 取第一条给详情面板与重放用。
- 详情面板跟随**第一条**选中项——多选时不会因为选了一堆而空白。
- 状态栏显示 `已选 N 条`，右键菜单项同步标注 `（N 条）`，避免"我明明选了 10 条，导出的却只有 1 条"。
- 批量导出走 `_export_selected()` 的统一校验：`SINGLE_ONLY_FORMATS`（仅「仅响应 Body」）在多选时直接弹提示；`REQUIRES_RESPONSE`（完整响应 / 仅响应 Body）在所选里有未响应会话时拦住，不落空文件。

#### 3.2.5 body 结构化视图（对齐 Fiddler 的 JSON / WebForm inspector）

body 区顶部是一排互斥按钮（Fiddler inspector 风格，非下拉）：`自动 / 原文 / JSON / 表单 / 图片 / 十六进制`，默认「自动」按 content-type 挑最合适的那个：

| 模式 | 触发（自动） | 展示 |
|---|---|---|
| 自动 | —— | 按 content-type 判定后落到下面某一项，并在提示里写明「自动 → JSON」 |
| 原文 | 兜底 | 解码后的原始文本（超 512KB 截断并注明） |
| JSON | `application/json`、`text/json`、`*+json`（jsonp / hal / vnd.api / problem…） | 缩进 2 空格 + 语法着色 |
| 表单 | `application/x-www-form-urlencoded` | key / value 两列表格，URL 已解码 |
| 图片 | `image/*`（含 `svg+xml`） | 预览 + 缩放档位（适应窗口 / 25% / 50% / 100% / 200%） |
| 十六进制 | 文本解不出来时 | 偏移 / 十六进制 / ASCII 三栏 |

**一条硬规则：格式化失败一律回落原文并说明原因，绝不吞掉 body。** 抓包工具里"内容不见了"比"没格式化"严重得多。JSON 解析失败时显示原文 + `JSON 解析失败，已显示原文：<原因>`；表单解析不出字段时显示原文 + `无法解析为表单，已显示原文`。

判定细节（都是踩过的坑）：

- **声明了 JSON 但解析不了，仍然进 JSON 视图**——内容不丢（渲染层回落原文），但会挂一句原因。"服务端说自己是 JSON、实际不是"本身就是重要线索，静默当成普通文本等于把线索丢了。
- **嗅探只发生在「没声明 content-type」或「声明成 `text/*`」两种情况**，且要求真的能解析、首字符是 `{` 或 `[`。把普通文本（如 `[INFO] ...` 日志片段）塞进 JSON 视图只会显示一句吓人的"解析失败"，不如老实显示原文。`text/html` 之类即使含 `{` 也不嗅探——猜错代价太大。
- **表单只按 content-type 认，绝不猜**：表单体长得太像普通文本。并且要求 body 里**至少有一个 `=`**——`parse_qsl` 会把没有 `=` 的整串当成"key + 空值"返回，那样一句错误信息也会被显示成一行莫名其妙的字段。
- **`keep_blank_values=True`**：保留 `flag=` 这类空值字段。前端到底传没传这个字段，本身就是调试时要看的信息。
- **key 顺序保持服务端顺序**（`json.dumps` 不 `sort_keys`），便于和线上响应逐行对照；`ensure_ascii=False`，中文原样显示不变成 `\uXXXX`。
- **语法着色只改前景色、不碰背景**：搜索高亮走的是 `ExtraSelections` 的背景色，若着色也铺背景会把命中盖掉——搜到了却看不出在哪。
- 着色有亮/暗两套配色，按 `QPalette.Base` 的亮度自动选（判深浅要用 `Base` 而不是 `backgroundRole()`，后者在不同控件上语义不一致，容易判反）。
- 数字/关键字染色要**跳过字符串内部**：否则 `"13800138000"` 里的数字会被当成 JSON number 染成橙色。
- **手动切过之后模式是粘性的**（换会话不回弹），对齐 Fiddler inspector 的手感；默认仍是「自动」。
- **搜索高亮在结构化视图上照样生效**：文本视图走 `QTextDocument.find`（`ExtraSelections`），表单表格走单元格底色（命中 key 或 value 都算，清空搜索时撤销底色）。图片视图没有文本可搜，返回 0 而不是去表格里瞎找。
- 十六进制视图从 UI 里抽到 `app/bodyview.py`，可被单测（此前内联在渲染函数里）。
- **`BodyPane` 从 `MessagePane` 里拆出来**，请求 / 响应 / WebSocket 消息三处共用——一处支持了 JSON 着色，三处都有，不会出现「WS 消息忘了支持格式化」这类偏差。

##### 大内容的三道闸门（都是实测出来的，不是拍脑袋）

卡不卡先量再定。实测环境（offscreen，M4）：

| 场景 | 实测耗时 |
|---|---|
| 多行文本塞进 `QPlainTextEdit`（2MB） | ~52 ms |
| 语法着色 2 万行 JSON | ~260 ms |
| 单行 100KB + 换行 | ~164 ms |
| 单行 300KB + 换行 | **~1.2 s**（超线性） |
| `json.loads` + `dumps` 4MB | ~30 ms |

结论：**卡顿不来自解析，来自着色（按 block 线性）和超长行换行（超线性）**。于是：

1. **JSON 先完整解析、只截断渲染结果**（`JSON_PARSE_LIMIT` = 4MB，`RENDER_TEXT_LIMIT` = 2MB）。
   早期实现先按 512KB 截断再解析 → 任何大于 512KB 的 JSON 都被截成半截、解析失败，用户反而**失去格式化还看到一句"解析失败"**。解析很便宜，所以反过来做：完整解析，输出太长才截断（截断的是纯文本，视觉结构依然完整）。
2. **渲染文本超过 `HIGHLIGHT_LIMIT`（256KB）就暂停语法着色**——丢颜色，不丢流畅。
3. **单行超过 `WRAP_MAX_LINE_CHARS`（64KB）时临时关闭换行**并在提示里说明。换行对多行文本几乎免费，对超长单行是超线性开销；用户切到 JSON 视图（格式化后是多行）就又能换行了。提示文案写明"已临时关闭"而不是静默不换——否则用户会以为是 bug。

另外 `json.loads` 遇到深嵌套（如 `[[[[…]]]]`）抛的是 **`RecursionError`，它不是 `ValueError` 的子类**。漏接就是整个界面崩掉，所以 `format_json_text` 显式接住并回落原文。

##### 图片预览

- `image/*` 自动进图片视图；`svg+xml` 走 `QSvgRenderer` 矢量渲染（可任意倍率缩放），没有 QtSvg 时明确报"渲染不可用"而不是留个空白框。
- 原图存一份，按档位渲染；「适应窗口」只缩不放（小图不被拉糊），窗口 resize 时重算。
- 图片**加载失败（内容损坏 / 格式不支持）回落十六进制并说明**——同样是"不丢内容"原则。
- 提示里给出格式、像素尺寸与体积（`PNG · 800×600 · 12.3KB`）。

#### 3.2.6 列表顺序与自动滚动

工具栏两项，都持久化：

- **顺序**：`到达顺序（新在底部）` / `新的在顶部`。倒序不新增排序维度，直接复用「按 `#` 列降序」——`#` 就是到达序号，天然正确，也不用给代理模型加一套反向映射。正序则把排序指示器清回 `-1`（自然到达顺序）。
- **自动滚动**：新会话到达时滚到最新端。两个克制条件，缺一不可：
  - **只有用户本来就停在最新端时才滚**——否则会把人手动翻到的位置抢走（比不自动滚还烦）；
  - **只在按到达顺序排列时才滚**（未排序或 `#` 列）——用户按耗时排完序再被拽回底部是最招人烦的。

#### 3.2.7 压缩 body（Content-Encoding）

mitmproxy 的 `Message.content` / `get_content(strict=False)` **已经按 `content-encoding` 解压**（`raw_content` 才是线上压缩字节），所以 gzip / deflate / br / zstd 无需我们处理。缺的是"告诉用户"：

- 解压生效时提示 `已解压 gzip：线上 12.3KB → 89.1KB`——导出时到底按哪个算，全靠这句话说清楚。
- **兜底**：若 mitmproxy 解压失败（返回长度与原始长度相同），按魔数再试一次（`\x1f\x8b` → gzip、`\x28\xb5\x2f\xfd` → zstd、`\x78` → deflate），成功则提示"手动解压"。都不行就明说"已按 X 压缩，但解压失败，显示的是原始压缩字节"，而不是丢一堆乱码让人以为是编码问题。

### 3.3 Mock 规则引擎

**规则模型**（`rules.json`）：

```json
{
  "version": 1,
  "rules": [
    {
      "id": "r_7f3a9c",
      "name": "用户信息-空列表",
      "enabled": true,
      "match":  { "type": "contains", "value": "/api/user/list" },
      "action": {
        "type": "mock",
        "status": 200,
        "headers": { "Content-Type": "application/json" },
        "body_source": "inline",
        "body": "{\"total\":0,\"items\":[]}",
        "file_path": null,
        "latency_ms": 0
      }
    }
  ]
}
```

- `match.type` 取值：`exact`（全URL精确）、`contains`（子串）、`wildcard`（`*` 通配，内部转正则 `[^/]*`→按 `.*`）、`regex`（用户正则）。
- `action.type` 本期只实现 `mock`（Fiddler 重定向规则导入时转换为带 `Location` 头的 mock，见 3.4.1）。
- **匹配流程**：请求进入 `request` hook → 遍历启用中的规则（按列表顺序）→ 第一条命中即 `flow.response = Response.make(status, body_bytes, headers)` 并 `return`，mitmproxy 发现 response 已存在便不再连接上游——**请求不离开本机**。
- **优先级语义与 Fiddler 一致**：先声明先匹配，用户可在规则页拖动排序。
- 命中后给 flow 打标（`flow.marked = "MOCK:规则名"`），CaptureAddon 同步到 UI 徽标。

#### 3.3.1 本地文件响应（对齐 Fiddler `x-replywithfile`）

- `body_source = "file"` 时，命中后读取 `file_path` 的内容返回。
- **请求时读取，非规则加载时**：改文件内容即改 mock 输出，不动规则——这是本地文件 mock 的核心价值（调 JSON 不用重启任何东西）。
- Content-Type：规则 headers 显式指定优先；未指定时按扩展名推断（`.json→application/json`、`.html→text/html`、`.png→image/png`，用标准库 `mimetypes`）。
- 异常处理：文件不存在 / 无权限 / 超过 100MB → 返回 **502 + 错误说明 body**，同时规则列表该条标记红色警告；恢复正常后自动清除标记。
- 二进制文件（图片、zip 等）按字节原样返回，不做任何编解码。

#### 3.3.2 模拟延迟（对齐 Fiddler Set Latency）

- `latency_ms`：命中后先等待再返回，`0` = 无延迟；UI 输入校验为 0~60000 的整数。
- 实现为 `await asyncio.sleep()`：**事件循环非阻塞**，延迟期间其他连接的抓包与 mock 完全不受影响。
- 大文件读取同样丢线程池（`asyncio.to_thread`），防止磁盘 IO 卡死整个代理（见风险表）。

#### 3.3.3 异常状态码

- `status` 接受任意 100~599，不限于 2xx——造错误场景是 mock 的主要用途之一。
- UI 提供预设按钮：`400 / 401 / 403 / 404 / 429 / 500 / 502 / 503 / 504`，点击即填，也支持自由输入。
- 与 body/headers 自由组合，例如 `503 + Retry-After: 30 + 维护页 HTML`。

#### 3.3.4 命中计数与会话备注

**命中计数**（规则页「命中」列）：

- 每条规则一个内存计数器（`Rule.hits` + `last_hit`），命中即 `record_hit()`。
- **只存内存不落盘**：`rules.json` 是可迁移可分享的资产，掺进本机运行期计数会让 diff 变脏；
  且每次命中写盘会把热路径拖慢。重启归零可接受（计数是"刚才有没有生效"的即时反馈，
  不是长期统计）。
- **线程安全**：`MockAddon` 在 asyncio 线程调 `record_hit`，计数在锁内做；回调
  （`FlowBridge.emit_rule_hit` 信号）在锁外调，回调异常只记日志——绝不能让它
  波及代理线程。信号桥把更新递回 Qt 主线程，规则页只改命中那一格，不整表重建。

**会话备注**（列表「标记」列 + 详情面板顶部）：

- 备注写 mitmproxy 原生字段 `flow.comment`；`flow.marked` 留给 `MOCK:` / `REPLAY:` /
  `LOCAL:` / `WS` 徽标——**两个字段互不覆盖**（早期混用会让备注被徽标冲掉）。
- 「标记」列显示优先级：**用户备注 > MOCK 徽标 > WS > REPLAY**；tooltip 同时给出备注与徽标。
- 存取闭环经 `CaptureAddon.summarize()` 天然打通：备注进摘要 → 会话保存/恢复不丢失。
- 入口：右键「标记/备注…」（单选，预填旧值）/「清除备注」。

### 3.4 Fiddler 规则导入

#### 3.4.1 `.farx` 导入（主路径）

基于 Telerik 官方规则仓库真实样本解码验证的格式规范：

```
<AutoResponder RulesVersion="2" FiddlerVersion="5.0.x">
  <State Enabled="true" Fallthrough="true" UseLatency="false">
    <ResponseRule Priority="1" MaxMatchCount="1" Comment="..." Enabled="true"
                  Match='{"matches":["%%<base64:条件JSON>"], "matchCondition":1}'
                  Action='["%%<base64:动作JSON>", ...]'
                  Headers="<base64:原始响应头文本>"
                  Body="<base64:响应体字节>" />
  </State>
</AutoResponder>
```

- 条件 JSON 实例：`{"type":4,"condition":"contains","value":"example.com", ...}`
- 动作 JSON 实例（mock 类）：`{"type":22,...}`、`{"type":11,...}`（配合非空 Headers/Body）
- 动作 JSON 实例（重定向类）：`{"type":6,"condition":"regex","value":"http://localhost:4000/$2","find":"(.*example.com/)(.*)"}`

**映射规则**：

| FARX 元素 | 映射到本工具 |
|---|---|
| `Comment` | 规则 `name` |
| `Enabled` | 规则 `enabled` |
| 条件 `condition:"contains"` + `value` | `match.type = contains` |
| 动作带 `find`（正则） | `match.type = regex`（`find` 为正则体，`value` 中的 `$1/$2` 替换组在 mock 响应里做变量替换） |
| mock 类动作 + 非空 `Headers`/`Body` | `Headers` 首行抠状态码 → `action.status`；`Content-Type` 提为 header；`Body` 原样 → `action.body` |
| type 6 重定向动作 | 转换为 `action.type=mock, status=307, headers={"Location": <value>}`（语义等价，落入统一模型） |
| `$1`/`$2` 占位 | mock body/headers 中保留替换语法，由 mock 引擎在命中时用正则分组填充 |
| `oSession["x-replywithfile"]` 指向的本地文件 | `body_source=file, file_path` 原样保留（文件不存在也导入并标警告，路径可后改） |
| `State@UseLatency` / 规则级 latency 值 | `latency_ms`（无则不延迟） |

**兼容性策略**：能识别的结构完整导入；无法识别的节点（如特殊动作 `*drop`、Latency 设置）在预览中列为"跳过"并附原因，不阻断其余规则导入。

#### 3.4.2 `CustomRules.js` 导入（辅助路径）

FiddlerScript 是 JScript.NET，无法完整执行，采用**典型模式启发式解析**，逐条扫描 `OnBeforeRequest` 函数体内的语句，识别以下模式：

| JS 模式 | 产出 |
|---|---|
| `oSession.uriContains("X")`（含 if 条件） | `match.type=contains, value=X` |
| `oSession.HostnameIs("X")` | `match.type=contains, value=X`（主机名） |
| `/regex/.test(oSession.URI)` | `match.type=regex` |
| `oSession.utilCreateResponseAndBypassServer()` | 标记该条为 mock 规则 |
| `oSession.utilSetResponseBody('...')` 或 `oSession.responseBodyString = '...'` | `action.body`（处理 JS 字符串转义） |
| `oSession.responseCode = 200` | `action.status` |
| `oSession.oResponse.headers.Add("K","V")` / `oSession.oResponse["K"]="V"` | `action.headers` |
| `oSession["x-replywithfile"] = "path"` | 读取该文件内容作为 `action.body`；文件不存在则跳过并提示 |

**边界声明**：解析按"一个 if 块 = 一条候选规则"聚合；条件表达式过复杂（多重嵌套、自定义函数）无法静态识别的一律跳过。导入结果页明确展示：识别 N 条、跳过 M 条（附跳过原因），绝不静默丢弃。

#### 3.4.3 导入流程

```
用户点击「导入 Fiddler 规则」→ 选择 .farx / .js
  → 对应 Parser 解析为规则对象列表 + 跳过清单
  → 导入预览对话框（表格：规则名/匹配/动作摘要/来源/是否勾选，默认全选）
  → 用户确认 → RuleStore.merge()（id 重新生成，名称冲突自动加后缀 (2)）
  → 规则页刷新 + 结果提示「导入成功 N 条，跳过 M 条」
```

### 3.5 CA 证书管理

- 应用启动时确认 `~/.mitmproxy/mitmproxy-ca-cert.pem` 存在，不存在则触发生成。
- 工具栏「证书」入口提供两个动作：
  1. **导出到文件**：弹出保存对话框，复制 CA 证书。
  2. **手机下载**：启动 `certserver.py`（监听 `0.0.0.0:8081`），页面显示本机局域网 URL（如 `http://192.168.1.5:8081`）+ PEM/DER 两种下载链接 + 简要安装指引（iOS：设置→通用→VPN与设备管理；Android：设置→安全→加密与凭据）。停止代理时一并关闭该服务。

### 3.6 请求重放（对齐 Fiddler Replay / Edit and Replay）

- **入口**：流量表格右键菜单「重放请求 (Ctrl+R)」「编辑并重放…」。
- **实现路线**：`app/replay.py` 生成请求**副本** → `ProxyService.replay_flow()` 经
  `call_soon_threadsafe` 投递到事件循环线程 → mitmproxy 官方 `ClientPlayback` addon
  的 `start_replay()` 发送。
- **为什么必须走副本**：`start_replay` 会修改 flow（设 `is_replay`、清 response），
  直接传原会话会污染用户已捕获的数据。副本 = 深拷贝 + 新 id + 清 response/marked，
  原会话原封不动（Fiddler 语义：原会话保留，重放产生新会话）。
- **编辑并重放**：对话框预填原始请求（method/URL/headers/body 可改），确认后把编辑
  应用到副本再入队。headers 传 dict 即整体替换；body 按 UTF-8 编码发送。
- **结果可见**：副本走完整代理生命周期，响应再次触发 CaptureAddon，新会话自动出现
  在流量列表并带 `REPLAY` 徽标（`is_replay` 字段）；mock 规则对重放请求同样生效。
- **边界**：代理未运行时提示先启动；WebSocket 会话不可重放（mitmproxy 限制）。

#### 3.6.1 重放并对比（对齐 Fiddler 的 Replay and Compare）

重放的价值一半在"再发一次"，另一半在"**发出去的结果和原来比变了什么**"——改个 header
看缓存是否生效、换个参数看分页是否正确，以前要自己翻两条会话的 body 肉眼对比。

- **入口**：右键「重放并对比…」。走的是同一条编辑对话框（`ReplayEditDialog`，只是
  标题与确认按钮换成「重放并对比」）——**先改请求再对比**，覆盖"编辑后对比"的场景。
- **关联方式（关键设计）**：登记 pending 时记下**副本的 id**（`make_replay_copy` 生成，
  重放后新 flow 的 id 与之相同，见 test_replay 端到端断言），新 flow 到达
  `_on_flow_arrived` 时按 `id` 精确匹配。不用 URL + 时间戳模糊匹配——同一秒内重放
  同一 URL 多次会串台；id 是 UUID，不可能错。
- **对比窗口**（`app/ui/compare_dialog.py`，非模态，可一直开着继续抓包）：
  - 顶部一行概要：URL、原/新状态码与大小、判定结论；
  - 中部左右双栏复用 `MessagePane`（原响应 / 新响应，headers + body 全量可见）；
  - 底部差异报告 +「复制差异」按钮。
- **双轨 diff**：
  - 两边 body 都能解析成 JSON → **键级结构化 diff**（`app/jsondiff.py`，纯函数）。
    行级 diff 遇到"JSON 重排"会全行飘红，键级只标真正变化的字段（`$.user.name: "tom" → "jerry"`）；
  - 否则 → **行级文本 diff**（`difflib`，`app/textutil.unified_diff`）；
  - 二进制且解码失败 → 只报"相同/不同"，不硬渲染乱码。
  - body 一致但 headers 有差 → 判"body 一致，headers 有差异"并列出增删改的 header。
- **`app/jsondiff.py` 的四条约束**（Task #28 的「JSON 比对」页共用同一引擎）：
  1. **迭代不递归**——`[[[[…]]]]` 深嵌套会 `RecursionError`（jsonutil 踩过的坑），用显式栈；
  2. **双上限**——节点数 20 万 / 差异条目 2000，超限即停并标 `truncated`，调用方回退文本 diff；
  3. **key 顺序不算差异**——按 key 集合比较，服务端调整字段顺序不报噪音；
  4. **bool 与数字严格区分**——Python 里 `True == 1`，JSON 语义里 `true != 1`。
- **超时兜底**：pending 登记后启动 5s 轮询的定时器，超过 20s 没等到重放响应即清理并在
  状态栏提示（上游挂了 / 请求被 mock 短路等场景），不会让 pending 永久挂账。
- **已知限制**：列表按下标对齐，中间插入元素会让后续元素整体偏移（这类场景文本 diff
  更能看出版本变化）；二进制 body 只报同/不同。

### 3.7 会话保存与恢复（对齐 Fiddler 的 Save All Sessions / Load Sessions）

- **入口**：文件菜单「保存会话… `Ctrl+S`」「打开会话… `Ctrl+O`」；另有**退出自动快照**（默认开，可关）。
- **格式：JSONL，一行一条会话**（`app/session.py`，纯函数、无 Qt 依赖）：

  ```json
  {"v": 1, "summary": {...}, "request": {...}, "response": {...} | null}
  ```

  选 JSONL 而不是单个大 JSON 的三个理由：①可以**流式追加**写，不必先把整包会话摞在内存里；②写一半崩了，前面的行照样能读（坏行/半截行跳过并计数）；③方便人工 `grep`/`head` 看。
- **body 有预算**：单条上限 + 整包上限，超预算只存元数据并把该会话标记 `body_dropped`，绝不让一条大 body 拖垮整次保存。
  预算**只约束响应体**；请求体仅受单条上限约束——保住 POST payload，恢复出来的会话才能原样重放。
  显式保存：单条 512KB / 整包 512MB；退出快照收紧到单条 64KB / 整包 32MB（保证退出是秒级的）。
- **原子写**：先写 `.tmp` 再 `os.replace`，避免崩溃时留下半截文件覆盖掉上一份好数据。
- **恢复后仍是「活会话」**（关键，也是最容易漏的一点）：重建 mitmproxy 的 `Request` / `Response` / `HTTPFlow`，所以恢复出来的会话照样能看详情、导出、**重放**。为此要做三件事：
  1. **合成 `Client` / `Server` 连接对象**。`Flow.copy()`（重放必经之路）内部会调 `client_conn.get_state()`，连接为 `None` 直接 `AttributeError` 崩掉；`Server` 还必须给 `address=`（否则 `TypeError: missing 1 required keyword-only argument`）。用 `urlparse` 出来的 scheme 决定 `tls`。
  2. **还原 `marked` 与 `is_replay`**，否则恢复后 `MOCK` / `REPLAY` 徽标全丢。
  3. **还原原始时间戳**，HAR 导出的 `timings` 三段（send/wait/receive）才能拆得出来。
  4. headers 走 `Request.make` / `Response.make` 时必须编码成 `bytes`（latin-1，失败退 UTF-8）——传 `str` 会 `TypeError: Header fields must be bytes`。
- **超上限处理**：恢复的条数超过当前「保存条数」（3.2）时，保留**最新的一段**（与抓包时的淘汰方向一致），并告知用户丢了多少条。
- **退出自动快照**：`closeEvent` 里先做快照（此时列表与缓存都还是完整状态），写到 `~/.miteproxy/last-session.jsonl` 并附一份 `last-session.meta.json`（条数 + 时间）；下次启动询问是否恢复，无论用户选是选否都把快照**归档**成 `last-session.previous.jsonl`，避免每次启动都弹同一个框。列表为空时清掉旧快照，免得下次启动拿一份过期数据误导人。
- **路径经模块引用**（`app.session.AUTOSAVE_PATH`，不按值导入）：否则测试/脚本改写到临时目录后，主窗口仍会往真实目录写。

### 3.8 网络模拟（弱网限速 + 域名映射到本地）

「网络模拟」标签页，两个能力互相独立，改动**即时落盘 + 即时推给运行中的代理**。

#### 3.8.1 弱网限速

**语义（重要，避免误解）**：不是逐块限速，而是**按响应体大小折算总传输时间，在响应发回客户端前一次性等待**：

```
延迟 = 档位固定延迟 + 响应体字节数 / (rate_kbps * 1024 / 8) * 1000   （上限 30s）
```

- 这样对「复现 loading 态 / 超时 / 骨架屏」足够，且行为可预测、可单测；真逐块限速要改写传输层，收益不划算。
- 档位：`关闭 / 2G（50kbps+400ms）/ 3G（400kbps+200ms）/ 4G（4Mbps+80ms）/ 弱网（50kbps+2000ms）/ 自定义`。
- **手改数字自动切到「自定义」**：否则下次加载配置时会被档位表覆盖，用户会觉得"改了没用"。切换时同步一次控件可用状态，避免输入框停在禁用态像坏了。
- 非自定义档位**以档位表为准**（`ThrottleConfig.from_dict` 里强制覆写），免得手改 `settings.json` 造出"档位和参数对不上"的迷惑状态。
- **为什么放在 `response` 钩子而不是 `request`**：request 阶段响应还没产生，拿不到体量。实现是 `async def response` + `await asyncio.sleep(...)`——mitmproxy 的 addon 管理器会 await 协程钩子，且每条 flow 在各自任务里跑，等这一条不会卡住其他连接（用 `time.sleep` 就会卡死整个事件循环）。
- **配置对象整体替换**：UI 线程 `set_config()` 赋一个新对象，不原地改字段，避免跨线程读到半更新的状态。
- `MAX_DELAY_MS = 30_000` 兜住手滑填的 `999999`；档位 `关闭` 或延迟/速率都为 0 → `enabled=False`，钩子直接返回。

#### 3.8.2 域名映射到本地（Map Remote）

把线上域名转发到本机服务，用于「线上前端 + 本地后端」联调。

- **复用 mitmproxy 自带的 `MapRemote`**，不重复造轮子：只补 UI + spec 生成 + 热更新。`MapRemote` 的选项 `map_remote` 是 `"/flow-filter/subject/replacement"` 形式的串表，动作就是 `re.sub(subject, replacement, pretty_url)`。
- **生成的正则只替换 URL 前缀**（scheme + host + 端口），路径与 query 原样保留：

  ```
  ^https?://api\.prod\.com(?::\d+)?/     →  http://127.0.0.1:8080/
  ```

- **`.` 必须转义，所以不能把点号当"用户写了正则"的信号**。`_REGEX_HINT_CHARS` 只认 `* + ? [ ] ( ) { } | \ ^ $`；若把 `.` 也算进去，`api.prod.com` 会被当正则处理，`.` 变成"任意字符"，`apiXprodYcom` 也会被改写。普通域名整串 `re.escape()` 成字面量。
- **spec 分隔符用不可见字符 `\x1f`**：`map_remote` 的 spec 以首字符为分隔符，用 `/` 会和 URL、正则里的 `/` 撞车；用 `|` 会和正则的 `|` 撞车。分隔符意外出现在 subject/replacement 里时直接判为该规则不可用（而不是静默错位）。
- **目标写法**：`127.0.0.1:8080` 默认按 `http`（本地开发服务几乎都是 http）；要 https 就显式写 `https://dev.local:9000`。端口越界（如 `:99999`）必须 `try/except ValueError` 接住 `.port` 的抛错并判为不可解析，否则会直接抛到 UI 层。
- **热更新**：`ProxyService.update_options(map_remote=specs)` → 运行中经 `call_soon_threadsafe` 投到事件循环线程执行（options 变更会触发 addon 的 `configure` 钩子，不能从 UI 线程直接改）；代理未启动就只记进 `_options`，下次启动自动带上。`update_options` 返回 `True/False` 让状态栏如实显示「已立即生效」/「代理启动后生效」。
- **UI 反馈**：表格每行显示一句话说明（`https?://api.prod.com/* → http://127.0.0.1:8080/*`）；**填了一半但生成不出 spec** 的行标红（`#fff1f0` 底 / `#8a1f1f` 字）并计入「N 条填写不完整（已跳过）」；**整行全空不算错**（刚点「+ 添加一行」还没填就报红是噪音）；未启用行灰字。清色时用空 `QBrush()` 回到主题默认，不写死颜色，深色主题下才不会出现浅底浅字。

#### 3.8.3 本地目录映射（Map Local）

Map Remote 的目标是 `host:port`，但"把某个前缀的请求整个换成本地目录里的文件"是另一类
高频需求（前端本地 bundle、mock 静态资源）。mitmproxy 自带的 `map_local` 是**单文件**
映射，不满足"前缀 → 目录"，所以自研 `addons/maplocal.py`：

- **形态识别**（`app/network.py`）：目标列先看**路径特征**（`/`、`./`、`../`、`~`、`\`、
  Windows 盘符）判 local，再看 `host:port` 判 remote，都不像标 unknown。顺序不能反——
  `parse_target("./s")` 会把它解析成 netloc。
- **拦截范围**：只拦 `GET`/`HEAD`（POST 等写操作映射到静态文件没有意义）；查询串丢弃；
  目录请求试 `index.html`。
- **安全**：`Path.resolve() + is_relative_to()` 双保险，挡路径穿越（`..`）与符号链接逃逸；
  站点目录内部的软链照样能访问（本地开发的常见布局）。
- **失败一律透传上游**：文件不存在 / 超限（100MB）/ 读取出错都不报错——本地缺文件不该
  让页面白屏，回落线上内容才是合理默认。
- **标记**：命中的 flow 打 `LOCAL:文件名` 徽标，走 `marked` 字段，与用户备注分离；
  行着色只认 `MOCK:` 前缀，LOCAL 不染琥珀色。
- **二维码证书页**（`app/certserver.py`）：证书下载页每个局域网地址配一枚二维码
  （`segno` 纯 Python 生成内联 SVG，无额外依赖；segno 缺失时降级为纯链接不报错），
  手机扫码直达，不用手输 IP。地址候选取路由出口 IP 优先 + `getaddrinfo` 去重。

### 3.3.5 按请求方法匹配（v1.12，比 Fiddler 更好用的点）

`Match.method`（空 = 任意方法）：规则编辑器下拉选 任意 / GET / POST / PUT / DELETE /
PATCH / HEAD / OPTIONS，**不用像 Fiddler 那样自己拼正则区分方法**。匹配大小写不敏感。
同一 URL 想对不同方法返回不同响应（如 OPTIONS 预检回 200、GET 回数据）就是两条规则的事。

- 持久化：`rules.json` 的 `match.method`；旧文件无该字段 = 任意方法，行为不变。
- `find_rule(url, method)`：规则配了方法而调用方不传方法时**不命中**（"不知道方法"按不匹配处理，保守侧默认）。

### 3.3.6 重定向到其他 URL（v1.12，规则级 Map Remote）

`Action.redirect_url` 非空时走另一条路：命中后**改写请求 URL 放行到新上游**，返回真实上游响应
（不造 response）——对客户端完全透明。与「返回本地内容」的 mock 在编辑器里是三选一
（直接输入 / 本地文件 / 重定向），重定向模式下 status/headers/body 置灰不生效。

- 目标支持 `$1`/`${name}` 正则捕获组替换（与 body 同一套语义）：匹配值
  `https://a\.com/v(\d+)/(.*)` + 目标 `https://b.com/v$1/rewritten/$2` 即可做路径改写。
- **死循环保护**：目标指向本代理监听地址（127.0.0.1/localhost + 本代理端口）直接拒绝并标错
  ——那会让每一跳生成新 flow，metadata 计数管不到；另有 flow.metadata 计数兜底。
- 改写失败（目标非法/循环）返回 502 + 规则标错，不用规则配置的 body 兜底（那是误导）。

### 3.9 WebSocket 抓包（对齐 Fiddler 的 WebSocket 会话）

mitmproxy 12 把 WebSocket 连接表示成**带 `websocket` 属性的 HTTP flow**：握手是 101 响应，消息累积在 `flow.websocket.messages` 里（`from_client` / `type` / `content` / `timestamp`）。

**钩子的关键点**：mitmproxy 12 **没有 `websocket_start` 钩子**。它在调用 `response` 钩子**之前**就挂上了 `flow.websocket`，所以：

| 阶段 | 钩子 | 本工具做什么 |
|---|---|---|
| 握手 | `response`（101） | 正常产出列表行；摘要里 `is_websocket=True`、状态 101 |
| 每条消息 | `websocket_message` | **增量更新同一行**（消息数 / 体积 / 耗时），不新增行 |
| 关闭 | `websocket_end` | 补关闭码与最终耗时，`ws_closed=True` |

- **体积口径**：101 响应没有 body，所以 WS 会话的「大小」列用**消息体总和**——用响应长度的话这一列永远是 0，看不出连接到底传了多少数据。
- **耗时口径**：用 `websocket.timestamp_end - request.timestamp_start`（连接存活时长），而不是握手那几十毫秒。
- **列表展示**：「标记」列显示 `WS N`（N = 已捕获消息数），悬停提示补 `WebSocket：N 条消息（连接中/已关闭）`。
- **详情面板**：WebSocket 页签**只在当前会话是 WS 时才可见**（`QTabWidget.setTabVisible`）——普通 HTTP 会话挂个空页签只会让人以为功能坏了。页内上半是消息表（`# / 时间 / 方向 / 类型 / 长度 / 内容预览`），下半复用 `BodyPane` 展示选中消息的 payload（一样支持 JSON 着色 / 表单 / 图片 / 十六进制）。
- **增量追加而不是每次重建**：消息可能每秒几十条，重建会丢掉滚动位置与选中行；只在原本停在底部时才自动滚。表格上限 `WS_TABLE_LIMIT = 2000` 行（再多的只留在内存里并注明）。
- **URL 显示成 `ws://`**：握手请求行按 RFC 6455 是 `http://`，但给人看要显示 `ws://`（`_ws_display_url`）。
- **消息写入会话文件**（v1.11）：`ws_messages` 字段随记录落进 `.jsonl`——`messages` 逐条编（文本/base64 与 body 同一套编码）、`total` 记真实条数、`close_code`/`close_reason` 记收尾。**与 body 共用同一份剩余预算**（消息可能极大，不能让一条吵闹的连接把整包保存撑爆），另有 `WS_MESSAGE_LIMIT = 2000` 条数闸；任一闸触发即停并置 `truncated`。恢复时重建 mitmproxy 的 `WebSocketData`/`WebSocketMessage`（`type` 存 Opcode 整数值，`is_text` 由 mitmproxy 自推导），消息表、payload、关闭码原样回来；**旧文件没有该字段照常加载**。summary 里的消息计数按**实际存储数**回填，不会出现「行上显示 2100、点开却没有」。
- **已知限制**：
  1. **消息仍受保存预算约束**：吵闹的连接（>2000 条或预算耗尽）只存前一部分并在结果里注明 `truncated`——这是刻意取舍：宁可少存，不能把整个会话文件撑爆或让保存卡住。
  2. **请求行必须是 `http://` 形式**。mitmproxy 的 HTTP/1 解析会拒绝 `ws://` 的绝对 URI（`Invalid request scheme: ws` → 400）。RFC 6455 规定的正是 `http://`（wss 对应 `https://`），主流客户端都这么做；真遇到发 `ws://` 的客户端需要它自己改成 `http://`。

---

### 3.10 工具页（编码转换 + JSON + JSON 比对 + API 调试）

抓包看到一段 base64、或一大坨压缩过的 JSON 时，以前要复制到外部网站去处理。
这里把四件高频的事放进一个标签页：**编码转换**（3.10.1，对齐 Fiddler 的
TextWizard）、**JSON 格式化/提取**（3.10.2，对齐 json.cn）、**JSON 比对**
（3.10.3，复用 3.6.1 的 diff 引擎）与 **API 调试**（3.10.4，构建请求直发）。
合成一页而不是多个顶层标签页，是因为它们的用法是连着的——先 base64 解码、
解出来是 JSON 再格式化、再用 JSONPath 抠出要盯的字段、把两段 JSON 比一比、
最后照着抓到的请求改一改自己发出去。

流量列表右键「在工具页中打开 body」把选中会话的 body 直接送进来（送到哪个子页
由用户当前停在哪一页决定），省掉手动复制。

#### 3.10.1 编码转换（`app/codec.py` + `app/ui/codec_panel.py`）

27 种转换，全部**文本进、文本出**；失败不抛到 UI，返回带 `error` 的 `Result`
让界面显示红字说明。

| 分组 | 转换 |
|---|---|
| 编解码 | URL 编码 / 解码（各分「路径」与「表单」两种 `+` 语义）、Base64 编解码、Hex 编解码、HTML 实体编解码、Unicode 转义与反转义、JSON 字符串转义与反转义、Gzip 压缩（→Base64）/ 解压、Deflate 解压 |
| 格式 · 文本 | JWT 解码、JSON 美化 / 压缩、时间戳 ↔ 日期、大小写 |
| 哈希 | MD5 / SHA-1 / SHA-256 |

几条刻意的取舍：

- **URL 的 `+` 不混**：表单里 `+` 是空格、路径里 `+` 就是加号，所以编码/解码各
  给两项（`quote` vs `quote_plus`）。合成一项必然有一半场景解错。
- **Base64 输入严格校验**：`b64decode(validate=False)` 会静默丢弃非法字符，把
  任意文本都"解"成一串乱码。这里先用正则校验字符集，不合法就明确报错。
- **解码结果不是 UTF-8 时不报错**：按单字节回落并在 note 里说明
  （"解出来了但看不懂"比"报错"信息量大），用户可以再对它做一次 Hex 编码看字节。
- **二进制中间产物统一走 Base64 或 Hex**：Gzip/Deflate 的输入两种都尝试识别，
  并在 note 里说明实际按哪种解的；Deflate 还会依次尝试裸 deflate / zlib 头 /
  gzip 三种（HTTP 的 `Content-Encoding: deflate` 两种都常见）。
- **「反向」按钮**：可逆转换互相指向对方（`REVERSE`），一键切到反向并把结果填回
  输入。注册表有自洽测试：反向必须成对且两端都存在。
- **实时转换带 180ms 防抖**，输入超过 512KB 就暂停自动转换、交给「立即转换」按钮。

#### 3.10.2 JSON 格式化与提取（`app/jsonutil.py` / `app/jsonpath.py` / `app/ui/json_panel.py`）

- **错误必须能定位到人**：只丢一句 `Expecting ',' delimiter` 用户还是不知道改哪。
  `JsonError` 给**行 + 列 + 出错行原文 + `^` 指针 + 一句「可能原因」**（尾逗号、
  单引号、未闭合引号、JSONP 包裹等 8 类常见误用各有对应提示），并给「跳到出错
  位置」按钮把光标移过去。
- **失败绝不吞内容**：非法 JSON 时右侧照样显示原文，错误另起一块显示
  （与 3.2.5 同一条硬规则）。
- **严格模式**：拒绝 `NaN` / `Infinity`（Python 的 json 默认接受，但
  `JSON.parse` 不接受）——否则会出现"这里能解析、前端报错"的假象。重复 key 不报错，
  但给 note 提示（接口返回重复 key 是常见坑）。
- **视图**：格式化文本（着色）/ 树形（`QTreeWidget`，可展开折叠，数组显示项数）
  / JSONPath 结果（路径 + 值表）。树在节点 ≥ 5000 时跳过并说明——建树比渲染文本贵。
- **JSONPath**（自研，不引第三方）：`$`、`.key`、`['key']`、`[n]`、`[-1]`、
  `[a:b]`、`[*]`、`..name`、`..*`、`[?(...)]`（`== != > >= < <= =~`，`&&` `||`）、
  联合 `['a','b']` / `[0,1]`、聚合函数 `length()` / `min()` / `max()`。
  不做脚本表达式、step 切片——用得极少，做进来只会让报错更难懂。
  - 聚合函数**对整个结果集生效**（不是逐节点）：`$.l.max()` 取数组极值，
    `$.l[*].p.max()` 取所有 p 的极值——后者才是抓包调试的常用形态。
    函数必须带括号，字段恰巧叫 `max` 的写法（`$.a.max`）不受影响。
    `min()/max()` 遇到非数字明确报错（不静默跳过），空结果也报错。
  - 遍历全用**迭代**：`$..x` 遇到几千层嵌套也不能爆栈（实测 3000 层正常返回）。
  - 结果上限 2000 条，超出只显示前 2000 条并说明。
  - 递归下降按**文档顺序**返回：栈式遍历很容易把结果倒过来，看着像数据乱了。
- **大内容的三道闸门**（复用 3.2.5 的实测结论）：解析用完整输入（4MB 约 30ms，
  不是瓶颈），渲染文本 >2MB 截断、着色 >256KB 关掉、单行 >64KB 不换行。
- **`RecursionError` 单独接**：它不是 `ValueError` 的子类，漏接就是界面崩掉。

**树形视图懒加载**（v1.12）：只建根节点，容器节点挂 `(值, 路径)` 并用
`ShowIndicator` 显示展开箭头，`itemExpanded` 信号触发时才构建子节点——大 JSON
切到树视图不再一次性铺几万个节点。双上限：`TREE_CHILD_LIMIT = 5000`（单层子项，
超出加"其余 N 项未显示"占位）与 `TREE_NODE_LIMIT = 5000`（已构建总数，触顶暂停
填充并提示）。折叠再展开不重复填充。

#### 3.10.3 JSON 比对（`app/ui/json_compare_panel.py`，复用 `app/jsondiff.py`）

左右两个输入框，实时（220ms 防抖）出**键级差异表**（路径 / 类型 / 旧值 / 新值）。
与 3.6.1「重放并对比」共用同一个 diff 引擎，入口不同：那边比重放前后的响应，
这边比任意两段 JSON（线上返回 vs 本地期望、两个接口的字段对照）。

- 某一侧非法 → 状态区给出定位（行列 + `^` 指针），输入框内容不动（失败不吞内容）；
- 一边为空 → 提示补全，不报错；
- 差异表行数上限 500（diff 仍算完），超出在状态栏说明；
- 「交换左右」一键对调（比对方向随之反转），「复制差异」把文本报告写进剪贴板；
- 工具菜单「JSON 比对… `Ctrl+Shift+D`」直达；右键送 body 到本页时灌进左侧。

#### 3.10.4 API 调试（`app/httpclient.py` + `app/ui/api_panel.py`，v1.12）

构建请求 → 直发目标服务器 → 就地看响应，对齐 Postman 的最小核心。

- **纯函数层** `httpclient.send_request`：http.client 阻塞式、后台线程调用；
  任何失败收敛成 `ApiResponse(ok=False)`（异常不外抛，不打死线程）；
  默认跳过证书校验（调试自签/内网是常态）；**不跟随重定向**（调试要看 302 本身）；
  响应体 500MB 兜底；非 GET/HEAD 空 body 也发 `Content-Length: 0`（body 传 None
  时 http.client 不补这个头，严格服务器回 411）。
- **UI 层**：方法下拉 + URL + headers 表 + body，`Ctrl+Return` 发送；请求跑在
  daemon 线程，结果经 Qt 信号回主线程；`_seq` 序号防竞态（连点时按最后一把算）。
- **响应显示复用 BodyPane**：JSON 着色 / 表单 / 图片 / 十六进制全套免费拿到。
- **从流量带入**：右键「发送到 API 调试」把选中会话的完整请求（method/URL/
  headers/body）灌进表单——与「在工具页中打开 body」的差别：那个只送 body 素材，
  这个送完整请求模板。
- 注意：直连目标服务器，**不走抓包代理**，响应不进流量列表。

#### 3.10.5 着色器共用（`app/ui/highlight.py`）

`JsonHighlighter` 与两套配色原本内联在 `detail_panel.py`，抽出来给 body 视图与
JSON 工具页共用——两处各写一份迟早不一致（改了深色配色忘了另一处）。两条规则
不能破：只改前景不碰背景（否则盖掉搜索高亮的背景色）、数字/关键字染色跳过
字符串内部（否则 `"13800138000"` 里的数字会被染成数字色）。

### 3.11 主题：深浅色（v1.14，`app/ui/theme.py`）

- **档位**：`system`（默认，完全跟随系统深浅）/ `light` / `dark`；菜单「外观」
  三选一，选择随 `settings.json` 的 `theme` 字段持久化，启动即应用。
- **基础控件**底色/文字由 Qt 原生跟随系统，不做样式表全铺；需要处理的是散落
  各文件的**语义色**——统一收拢为 token（`hint/ok/error/warn/info` +
  mock 命中行、搜索命中底色、无效配置行等），每个 token 浅色、深色各一套，
  深色组保证深底对比度。
- **两种接入方式**：①`theme.dynamic(key)`——模块级 QColor 常量（如
  `MOCK_ROW_BG`）在主题切换时**就地更新**，模型 `data()` 每次重绘重新取值，
  持有方零改动；②`theme.add_listener(self._retheme)`——静态样式表（提示文字、
  状态行等）由各面板的 `_retheme` 重设，WeakMethod 持有、控件销毁自动清理，
  单个回调抛异常不影响其他监听者。
- **切换链路**：手动切档走 `QStyleHints.setColorScheme`（Qt 6.8+ 原生深浅，
  保真度最高，不支持的平台回落 Fusion + 手工调色板）；系统深浅变化由
  MainWindow 的全局 `PaletteChange` 事件过滤器捕获，`singleShot(0)` 等调色板
  落位后 `theme.notify()` 统一广播。JSON 语法着色沿用 3.10.5 的双配色 +
  `is_dark()`，切主题时 BodyPane 重渲染一次即换色。
- 测试：`test_theme.py`（12 例）——token 完整性、动态色就地更新、监听者生命周期
  与异常隔离、settings 往返与坏值回落、主窗口外观菜单接线；主题冒烟 7 项
  （启动→深→浅→跟随系统往返，动态色与状态栏存活）。

---

## 4. 数据设计

### 4.1 规则文件

路径 `~/.miteproxy/rules.json`，结构见 3.3。约定：

- 应用启动时读取，不存在则创建空文件（`{"version":1,"rules":[]}`）。
- 任何修改后原子写回（临时文件 + `os.replace`），防止崩溃写坏。
- 所有读写经过 `RuleStore` 的 `RLock`，代理线程只读不改。

### 4.2 Flow 运行时模型

- `CaptureAddon.flows: dict[str, Flow]`（`flow.id` 为键），UI 回查取完整数据。
- 推送 UI 的摘要 dict：`{id, method, scheme, host, server_ip, path, url, status, size, duration_ms, content_type, marked, is_replay, timestamp, is_connect, is_websocket, ws_messages, ws_closed}`。后三个字段供列表显示 WS 徽标与消息数（见 3.9）。
- 淘汰策略：`flows` 超「保存条数」上限（默认 5000，见 3.2）时删最旧，UI 表格同步裁剪；上限变更走 `set_max_flows()` / `set_max_rows()`。

### 4.3 应用设置

路径 `~/.miteproxy/settings.json`，保存 UI 偏好（非规则数据）：

```json
{
  "proxy_port": 8888,
  "cert_port": 8081,
  "max_flows": 5000,
  "filter": {
    "host_mode": "blacklist",
    "host_keywords": [],
    "hide_connect": false,
    "hide_image": false
  },
  "throttle": {"preset": "off", "latency_ms": 0, "rate_kbps": 0},
  "map_remote": [{"source": "api.prod.com", "target": "127.0.0.1:8080", "enabled": true}],
  "auto_save_session": true,
  "last_session_dir": "",
  "auto_scroll": true,
  "newest_first": false,
  "body_wrap": true,
  "traffic_side_by_side": true,
  "theme": "system",
  "splitter_state": null,
  "window_geometry": null
}
```

- 过滤配置（3.2.1）、保存条数（3.2）、监听端口、窗口几何均在此，启动时读取、变更即原子写回。
- `max_flows` 写入非法值（手改 JSON）时按**就近档位**收敛到 3.2 的选项列表，无法解析则回落到默认 5000——不静默丢弃用户意图。
- `throttle` 见 3.8.1：非自定义档位读取时以档位表为准；`preset` 不在档位表里就回落 `off`。
- `map_remote` 见 3.8.2：脏数据（`null` / 字符串 / 缺字段）整条忽略而不是让加载失败。
- `auto_save_session` / `last_session_dir` 见 3.7：前者是退出快照开关，后者记住会话文件对话框的上次目录。
- `auto_scroll` / `newest_first` 见 3.2.6；`body_wrap` 见 3.2.5（换行开关，超长单行会被闸门临时关掉）。三者缺失时取默认值，**旧版 settings.json 不能被判成损坏而丢掉全部设置**（已加回归用例）。
- `window_geometry` / `splitter_state` 是 **bytes**（`saveGeometry()` / `saveState()` 结果），落盘为 base64 文本，启动时恢复窗口尺寸与流量页分隔条位置；损坏时回落默认不阻断启动。
- `traffic_side_by_side`：流量页布局方向（3.2）——`true` 左右（Fiddler 风格，默认）、`false` 上下，工具栏「布局」下拉切换，切换即写回。
- `theme`：主题档位（3.11）——`system` / `light` / `dark`，坏值回落 `system`；菜单「外观」切换即写回。
- 与 `rules.json` 分离：规则是可迁移资产（可导出分享），设置是本机偏好。

### 4.4 会话文件

路径由用户选择（默认落在 `~/.miteproxy/sessions/`），扩展名 `.jsonl`，格式见 3.7。
另有三个固定文件（同目录下的 `~/.miteproxy/`）：

| 文件 | 内容 |
|---|---|
| `last-session.jsonl` | 退出自动快照（下次启动询问是否恢复） |
| `last-session.meta.json` | 快照元信息（条数 + 保存时间），启动询问框用它显示"上次退出时保存的 N 条（时间）" |
| `last-session.previous.jsonl` | 上一份快照的归档（用户选恢复或不要后归档，避免每次启动重复弹框） |

---

## 5. 目录结构

```
miteproxy/
├── app/
│   ├── __init__.py
│   ├── main.py               # 入口：装配 Qt + 代理线程
│   ├── proxy.py              # DumpMaster 生命周期（线程化封装）
│   ├── replay.py             # 请求重放：副本 + ClientPlayback 投递
│   ├── export.py             # 复制/导出：cURL、原始报文、完整响应、HAR 1.2、响应 Body
│   ├── bodyview.py           # body 视图纯逻辑：判定/JSON 格式化/表单/图片/压缩/大内容闸门（支持多选）
│   ├── session.py            # 会话保存/恢复：JSONL 流式写 + 活会话重建 + 退出快照
│   ├── bodyview.py           # body 结构化视图：JSON 格式化 / 表单解析 / 十六进制（纯函数）
│   ├── network.py            # 网络模拟纯逻辑：弱网档位/延迟折算 + 域名映射 spec 生成
│   ├── codec.py              # 编码转换纯逻辑：27 种转换（URL/Base64/Hex/HTML/Unicode/Gzip/JWT/哈希…）
│   ├── jsonutil.py           # JSON 解析 + 精确错误定位（行列/指针/可能原因）+ 规模统计
│   ├── httpclient.py         # API 调试的 HTTP 客户端（纯函数层，v1.12）
│   ├── jsondiff.py           # JSON 结构化 diff：键级差异列表（迭代/双上限/bool 严格），重放对比与 JSON 比对共用
│   ├── jsonpath.py           # JSONPath 解析与提取（自研，迭代遍历不爆栈）
│   ├── rules.py              # RuleStore：模型/匹配/持久化（含内存命中计数）
│   ├── settings.py           # settings.json（端口/保存条数/过滤/弱网/域名映射/会话）
│   ├── textutil.py           # body 解码策略（charset 优先 → 默认 UTF-8）+ difflib 行级 diff
│   ├── certserver.py         # 证书下载服务 (8081)，页面模板内嵌（多候选 IP + segno 二维码）
│   └── ui/
│       ├── main_window.py    # 主窗口：工具栏/标签页/状态栏/复制导出/会话/网络模拟/重放对比接线
│       ├── flow_store.py     # 流量表格数据模型（列/上限/着色/排序角色）
│       ├── filter_model.py   # 过滤 + 搜索 + 排序共用的代理模型
│       ├── traffic_table.py  # 流量列表 + 过滤栏 + 搜索栏（多选 + 表头排序）
│       ├── detail_panel.py   # 请求/响应详情（BodyPane 六视图 + 命中高亮 + 备注条）+ WebSocket 消息页
│       ├── highlight.py      # JSON 语法着色器与两套配色（body 视图与 JSON 工具页共用）
│       ├── rules_panel.py    # Mock 规则管理页（含命中计数列）
│       ├── network_panel.py  # 网络模拟页（弱网档位 + 域名映射表）
│       ├── codec_panel.py    # 编码转换页（常用四项 + 分组下拉 + 反向 / 回填 / 复制）
│       ├── json_panel.py     # JSON 工具页（格式化/压缩/校验 + 树形 + JSONPath 提取）
│       ├── json_compare_panel.py # JSON 比对页（左右输入 + 键级差异表，复用 jsondiff）
│       ├── tool_panel.py     # 工具页外壳：编码转换 / JSON / JSON 比对三个子页
│       ├── rule_editor.py    # 规则编辑对话框
│       ├── import_dialog.py  # 导入预览对话框
│       ├── replay_dialog.py  # 编辑并重放对话框（compare 模式复用为「重放并对比」）
│       ├── compare_dialog.py # 重放对比对话框（双 MessagePane + JSON 键级/文本行级差异报告）
│       └── signals.py        # 跨线程信号桥（asyncio→Qt）
├── addons/
│   ├── capture.py            # response / websocket_message / websocket_end → UI（含 load_flows 恢复灌入）
│   ├── mock.py               # request hook → mock（命中记数）
│   ├── throttle.py           # response hook → 弱网延迟（await asyncio.sleep）
│   ├── maplocal.py           # request hook → 本地目录映射（GET/HEAD，防穿越，失败透传）
│   └── importers/
│       ├── __init__.py
│       ├── farx.py           # FARX 解析器
│       └── jsscript.py       # CustomRules.js 解析器
├── tests/
│   ├── conftest.py
│   ├── test_rules.py         # 模型/匹配/持久化
│   ├── test_farx.py          # 官方样本回归
│   ├── test_jsscript.py
│   ├── test_mock.py          # mock 内联/文件/延迟/异常码
│   ├── test_replay.py        # 重放（含端到端）
│   ├── test_textutil.py      # UTF-8 解码策略
│   ├── test_filter_model.py  # 过滤 + 搜索
│   ├── test_export.py        # cURL/原始报文/完整响应/HAR/Body + 多选批量
│   ├── test_sort_and_batch.py# 排序角色/比较器/多选批量
│   ├── test_session.py       # 会话保存恢复（含活会话重建）
│   ├── test_network.py       # 弱网折算 + 域名映射 spec 生成 + local 形态识别
│   ├── test_network_panel.py # 网络面板 + 设置往返 + 主窗口接线
│   ├── test_bodyview.py      # body 视图：判定/格式化/图片/换行/压缩/面板接线
│   ├── test_list_and_ws.py   # 列表顺序与自动滚动 + WebSocket 捕获接线
│   ├── test_codec.py         # 编码转换 27 种 + 面板接线 + 主窗口送 body
│   ├── test_json_tools.py    # JSON 解析/错误定位 + JSONPath + JSON 页与工具页接线
│   ├── test_jsondiff.py      # JSON 结构化 diff（增删改/容器变化/bool/深嵌套/双上限）+ 行级 diff
│   ├── test_mark_and_hits.py # 命中计数（线程安全）+ 备注字段与列表/详情/会话闭环
│   ├── test_maplocal.py      # Map Local 形态识别/addon 行为/证书页二维码
│   ├── test_replay_compare.py# 重放并对比：对比对话框 + pending 关联/超时/入口
│   ├── test_flow_limit.py    # 保存条数档位与淘汰
│   ├── test_server_ip.py     # 服务器 IP 列
│   ├── test_e2e_proxy.py     # 真代理端到端
│   ├── test_entrypoint.py    # 入口装配防回归
│   └── fixtures/             # Telerik 官方 FARX 样本
├── packaging/
│   ├── miteproxy.spec  # PyInstaller 配置（含 macOS/Windows 平台分支）
│   ├── build_mac.sh            # macOS 一键构建
│   ├── build_windows.ps1       # Windows 一键构建
│   ├── icon.icns               # macOS 图标
│   └── icon.ico                # Windows 图标
├── DESIGN.md
└── requirements.txt
```

---

## 6. 实现步骤与任务拆分

> 任务编号 T1.x~T7.x，每阶段末设验收门（Gate），不过门不进入下一阶段。

### 阶段 1：环境搭建与项目骨架

| # | 任务 | 产出 | 验收 |
|---|---|---|---|
| T1.1 | venv 安装 mitmproxy、PySide6、PyInstaller；冻结 `requirements.txt` | 依赖清单 | `python -c "import mitmproxy, PySide6"` 通过 |
| T1.2 | 按第 5 节建目录；`main.py` 空窗口能跑 | 骨架 | `python app/main.py` 弹出空窗口 |
| T1.3 | `proxy.py`：DumpMaster 内嵌启动，curl 验证代理通 | 最小代理 | `curl -x 127.0.0.1:8080 http://example.com` 200 |

**Gate 1**：桌面窗口 + 后台代理同时运行，curl 抓到 example.com。

### 阶段 2：代理内核与流量捕获

| # | 任务 | 产出 | 验收 |
|---|---|---|---|
| T2.1 | 代理线程封装：Thread + asyncio.run，启动/停止/端口参数 | proxy.py 完善 | 停止后端口释放，无僵尸线程 |
| T2.2 | CaptureAddon：`response` hook 收 flow，发 Qt 信号；内存存储带上限 | capture.py | 连续 50 请求 UI 全部刷新，无跨线程崩溃 |
| T2.3 | HTTPS 解密验证 + CA 生成确认 | 证书就绪 | curl `-k -x` https 站点成功，`~/.mitmproxy/mitmproxy-ca-cert.cer` 存在 |
| T2.4 | flow id 回查 + body 截断预览 | 数据通道 | 点选任意 flow 能取到完整 headers/body |

**Gate 2**：HTTPS 网站完整抓包并在界面可见。

### 阶段 3：Mock 规则引擎

| # | 任务 | 产出 | 验收 |
|---|---|---|---|
| T3.1 | RuleStore：模型类、四种 match 编译、JSON 原子读写、RLock | rules.py | 单测：四种匹配各命中/不命中用例 |
| T3.2 | MockAddon：`request` hook 顺序匹配、造 response、阻断上游 | mock.py | curl 命中规则返回 mock；未命中正常透传 |
| T3.3 | 命中打标 → UI 徽标 | 联动 | 列表可见 MOCK 徽标与规则名 |
| T3.4 | 规则页：CRUD + 启用开关 + 排序 | rules_panel.py | 改规则后即时生效（热加载） |
| T3.5 | 本地文件响应：请求时读文件、扩展名推断 Content-Type、缺失/超大异常标记、二进制支持 | mock.py / rules_panel.py | 改文件输出即变；文件缺失返回 502 且规则标红；图片按字节原样返回 |
| T3.6 | 模拟延迟（asyncio.sleep + 输入校验）与异常状态码预设 | mock.py / rules_panel.py | curl 计时延迟生效且并发请求不受阻；预设码与自定义码均正确返回 |

**Gate 3**：浏览器/curl 走代理，命中 mock 规则的请求拿到预设响应（内联/文件/延迟/异常码均验证），其余正常上网。

### 阶段 4：Fiddler 规则导入

| # | 任务 | 产出 | 验收 |
|---|---|---|---|
| T4.1 | FARXParser：XML→属性→base64 JSON 解码→规则映射（含 307 转换、$1 替换保留） | farx.py | 用官方样本 `map-local-manual.farx`、`map-remote-localhost.farx` 导入，字段正确 |
| T4.2 | JSParser：典型模式启发式解析 + 跳过清单 | jsscript.py | 自造 3 种典型 CustomRules.js 片段全部识别；1 个复杂片段正确跳过 |
| T4.3 | 导入预览对话框：表格勾选、统计、确认导入 | import_dialog.py | 预览→勾选→导入→规则页可见 |
| T4.4 | 导入产物回归：把导入的规则跑通 mock | 端到端 | 命中导入规则的请求返回 FARX 里的 body |

**Gate 4**：一份真实 `.farx` + 一份 `CustomRules.js` 完整走通导入并生效。

### 阶段 5：Qt 桌面界面

| # | 任务 | 产出 | 验收 |
|---|---|---|---|
| T5.1 | 主窗口三栏：工具栏/流量表格/详情面板 | main_window 等 | 布局无重叠，窗口缩放正常 |
| T5.2 | 流量表格：列渲染、选中联动、MOCK/HTTPS 徽标、清除按钮 | traffic_table.py | 操作无卡顿（1 万条内） |
| T5.3 | 详情面板：请求/响应 headers + body（文本/hex） | detail_panel.py | 图片类 body 显示十六进制不卡死 |
| T5.4 | certserver.py：8081 下载页 + 局域网地址展示 + iOS/Android 指引 | 证书页 | 手机连同一 Wi-Fi，浏览器打开 URL 能装 CA |
| T5.5 | 端口设置、代理开关、状态栏（运行中/已停止/当前端口） | 收尾 | 改端口重启代理生效 |
| T5.6 | 流量过滤：域名黑/白名单模式 + 输入框 + 隐藏 CONNECT/Image 复选框 + `显示 X / 共 Y` 状态 + 配置持久化 | traffic_table / settings | 两种模式与两类隐藏均生效；重启后过滤配置恢复；关闭过滤数据不丢 |
| T5.7 | 流量搜索：Ctrl+F 搜索栏、范围复选框（URL/Headers/Body）、大小写切换、Enter 循环跳转、详情面板命中高亮 | traffic_table / detail_panel | 三种范围均能命中；组合过滤与搜索时结果正确；大 body 索引策略有提示 |
| T5.8 | 请求重放：右键菜单 + Ctrl+R 原样重放；编辑并重放对话框（method/URL/headers/body）；副本机制 + ClientPlayback 投递；REPLAY 徽标 | main_window / replay_dialog / proxy | 重放后上游收到第二次请求且原会话不动；编辑后的 body 上游收到修改版；新会话带 REPLAY 标记 |

**Gate 5**：全界面操作闭环，手机装 CA 后抓到 App HTTPS 流量。

### 阶段 6：双平台打包（方案 A：本地构建）

> PyInstaller 不能交叉打包：macOS 包必须在 Mac 构建，Windows 包必须在 Windows 构建。两个平台的构建脚本都随项目提供，用户在自己机器上执行。

| # | 任务 | 产出 | 验收 | 状态 |
|---|---|---|---|---|
| T6.1 | 编写 `packaging/miteproxy.spec`：macOS/Windows 分支（bundle、图标格式）、hidden imports、剔除无用大包 | spec 文件 | 构建无模块缺失警告 | ✅ 已完成 |
| T6.2 | `packaging/build_mac.sh`：venv → 装依赖 → pyinstaller → 产出 `.app` | macOS 构建脚本 | 双击启动，功能回归通过 | ✅ 脚本就绪 |
| T6.3 | `packaging/build_windows.ps1`：venv → 装依赖 → pyinstaller（onedir）→ `Compress-Archive` 整体压成 `dist\MiteProxy-v<版本>-windows-x64.zip`（`-Version` 可指定版本号；脚本带 UTF-8 BOM，兼容 Windows PowerShell 5.1） | Windows 构建脚本 | 用户在 Windows 上执行，解压 zip 后双击 `MiteProxy.exe` 直接使用 | ✅ 脚本就绪，待 Windows 上执行 |
| T6.4 | 图标适配（`.icns` / `.ico`）+ Info.plist 元信息 | 成品感 | Dock/任务栏显示自定义图标 | ✅ 已完成 |
| T6.5 | 冻结产物验收：启动、自动开代理、mock、FARX、HTTPS | 验收记录 | 与源码版行为一致 | ✅ macOS 已通过 |

**构建命令**（各平台在仓库根目录执行）：

```bash
# macOS
./packaging/build_mac.sh
```

```powershell
# Windows（PowerShell，若执行策略受限：powershell -ExecutionPolicy Bypass -File .\packaging\build_windows.ps1）
.\packaging\build_windows.ps1
```

**Windows 平台注意事项**（写入手册）：

- 下载 zip 解压到任意目录，进入 `MiteProxy` 文件夹双击 `MiteProxy.exe` 即可（exe 与 `_internal\` 依赖目录必须放在一起，别单独挪走 exe）；
- 首次启动监听端口时系统弹防火墙对话框 → 勾选"专用网络"允许；
- 部分杀毒软件会误报 PyInstaller 解包行为 → 需加白名单；
- 建议解包到非系统目录运行。

**Gate 6**：两平台产物脱离源码目录可运行，且 Gate 7 的功能回归与源码版一致。

> **验收记录（macOS，2026-10-13）**：`dist/MiteProxy.app`（138MB，arm64，ad-hoc 签名）
> 脱离源码目录启动 ✅；启动即自动开代理 ✅；冻结产物上实测通过——内联 mock、正则 mock（`$1` 替换）、
> 503 + `Retry-After`、FARX 导入规则（返回 `Fiddler Everywhere - Example Domain`）、HTTPS 解密后 mock。
>
> **踩坑记录（真 bug）**：首次打包验收时 mock 全部失效、流量不进界面。根因是入口与主窗口
> 各建了一个 `ProxyService`，入口那个**不带 addon** 且开机即监听，实际运行的是裸代理。
> 已修为「代理由 MainWindow 唯一持有」，并加 `tests/test_entrypoint.py` 防回归。
> 这正是 Gate 6 存在的意义——源码冒烟绕过了入口，打包验收才把它逼出来。
>
> **未覆盖**：Windows 产物（需在 Windows 机器上执行 `build_windows.ps1`）、Intel Mac 产物
> （当前 Python 为 arm64，需在 Intel 机器或用 universal2 Python 构建）。

### 阶段 7：联调测试与验收

| # | 任务 | 产出 | 验收 |
|---|---|---|---|
| T7.1 | mock 命中/未命中 curl 脚本化回归 | 测试脚本 | 全绿 |
| T7.2 | HTTPS + 手机代理全链路 | 验收记录 | App 流量可见且可 mock |
| T7.3 | 真实 FARX 样本（官方仓库 3 份）+ 复杂 JS 片段导入回归 | 导入回归 | 结果与预期映射一致 |
| T7.4 | 长跑稳定性（持续抓包 30 分钟 + 规则热改） | 稳定性记录 | 无内存泄漏迹象、无跨线程异常 |
| T7.5 | 编写 README（使用说明 + 证书安装指引） | README | 新人按文档 10 分钟跑通 |

**Gate 7**：以上全过，交付。

### 阶段 8：体验补强（v1.7 追加，Gate 7 之后的增量）

| # | 任务 | 产出 | 验收 | 状态 |
|---|---|---|---|---|
| T8.1 | 导出新增「完整响应（Headers+Body）」格式 | export.py / main_window | 报文字节级正确（CRLF + 原始 body），无响应时弹提示不落空文件 | ✅ 已完成 |
| T8.2 | 列表列排序（表头点击） | flow_store / filter_model / traffic_table | 数值列按数值排（`1.3 MB > 812 B`）、文本列按字符串排、None 沉底、类型不混比较崩溃；`#` 列恒为到达序号 | ✅ 已完成 |
| T8.3 | 多选批量复制/导出 | main_window / export.py | 多选 cURL/URL/HAR/原始报文/完整响应均正确分段；「仅响应 Body」多选时被拦住；单条导出与旧版逐字节一致 | ✅ 已完成 |
| T8.4 | 会话保存与恢复（JSONL + 活会话重建） | session.py / main_window | 保存→恢复→详情可见→**重放可用**（`Flow.copy()` 不崩）；超上限保留最新一段；坏行跳过计数 | ✅ 已完成 |
| T8.5 | 退出自动快照 + 启动询问恢复 | session.py / main_window | 退出后 `last-session.jsonl` 就绪；下次启动询问并归档，不重复弹 | ✅ 已完成 |
| T8.6 | 弱网限速（档位 + 自定义） | network.py / throttle.py / network_panel.py | 真代理上大响应耗时 ≈ 固定延迟 + 体积折算，小响应只吃固定延迟；关闭后回落基线 | ✅ 已完成 |
| T8.7 | 域名映射到本地（Map Remote） | network.py / network_panel.py | 不可解析域名经代理后被改写并返回本地上游内容；改动即时生效/落盘；删行即失效 | ✅ 已完成 |
| T8.8 | body 结构化视图（JSON 格式化 + WebForm 表单表） | bodyview.py / detail_panel.py | 自动按 content-type 挑视图；JSON 缩进着色且中文不转义；表单字段 URL 解码；解析失败回落原文并说明；搜索高亮在结构化视图上仍生效 | ✅ 已完成 |
| T8.9 | 列表顺序 + 自动滚动 | traffic_table / main_window / settings | 倒序后最新在最上、正序回到到达序号；自动滚动只在"停在最新端 + 按到达顺序排"时动；两项持久化 | ✅ 已完成 |
| T8.10 | 大内容三道闸门 | bodyview.py / detail_panel.py | 深嵌套不崩（`RecursionError`）；>512KB 的 JSON 仍被格式化（先解析后截断渲染）；超长单行不换行并说明；大文本暂停着色 | ✅ 已完成 |
| T8.11 | 换行开关 | bodyview.py / detail_panel.py | 默认开、持久化；超长单行被闸门拦下时明说；反复切换不把提示越叠越长 | ✅ 已完成 |
| T8.12 | 压缩 body 提示 + 兜底解压 | bodyview.py / detail_panel.py | gzip 响应显示解压后内容并提示"已解压 gzip：线上 x → y"；mitmproxy 解压失败时按魔数兜底 | ✅ 已完成 |
| T8.13 | 图片预览 | bodyview.py / detail_panel.py | `image/*` 自动预览并显示格式/尺寸/体积；SVG 矢量渲染；缩放档位切换；损坏图片回落十六进制 | ✅ 已完成 |
| T8.14 | WebSocket 抓包与消息列表 + 消息持久化 | capture.py / flow_store.py / detail_panel.py / session.py | 真 WS 连接：握手行出现、消息增量入表（方向/类型/长度/预览）、点消息看 payload、关闭码可见；**保存后 `ws_messages` 落盘（条数/关闭码），恢复后消息表原样回来** | ✅ 已完成 |
| T8.15 | 编码转换工具（27 种） | codec.py / codec_panel.py | URL 的 `+` 两种语义不混；Base64 非法输入明确报错（不静默解成乱码）；二进制走 Base64/Hex 双识别；反向映射成对；失败只显示红字不崩 | ✅ 已完成 |
| T8.16 | JSON 格式化 + 精确错误定位 | jsonutil.py / json_panel.py | 非法 JSON 显示行列 + 出错行 + `^` + 可能原因，且**原文不丢**；`NaN`/`Infinity` 按浏览器语义拒绝；重复 key 给提示；深嵌套不崩；大 JSON 仍格式化 | ✅ 已完成 |
| T8.17 | JSONPath 提取 | jsonpath.py / json_panel.py | `.*[]..?()` 与联合写法均正确；递归下降按文档顺序且不爆栈（3000 层）；语法错误带位置指针；命中过多有上限说明 | ✅ 已完成 |
| T8.18 | 工具页合并与送 body | tool_panel.py / main_window | 两个子页在一个标签页内；右键「在工具页中打开 body」按当前子页送达并立即处理 | ✅ 已完成 |
| T8.19 | JSON 比对子页 + JSONPath 聚合函数 | json_compare_panel.py / jsondiff.py / jsonpath.py | 左右 JSON 实时出键级差异表（增/删/改分色、行数上限、交换左右、复制差异）；非法侧给定位且内容不丢；`length()/min()/max()` 对整个结果集生效，非数字明确报错 | ✅ 已完成 |

**Gate 8**：真代理端到端冒烟——限速延迟确实体现在客户端耗时上；域名映射确实改写上游地址；
面板改动即时落盘并热更新到运行中的代理；大 JSON 真的被格式化而不是报解析失败；
gzip 内容解压后可读；图片真能预览；WS 消息真能一条条收进来，**保存后随会话文件落盘、
恢复后原样回到消息表**；**抓到的 body 送进工具页
后能格式化、能用 JSONPath 抠出字段、非法内容能定位到行**。**已通过**
（33 + 53 + 47 + 26 + 21 + 22 + 19 项断言的 offscreen 冒烟，见 8.2 节）。
v1.12 增量以单测 + 本地服务集成测试为主（803 例），另跑真代理冒烟验证
方法匹配（GET 命中/POST 透传）与重定向（上游收到改写后的请求）。

> **打包提醒**：`dist/` 下既有产物是 v1.6 之前打出来的，**不含以上任何 T8.x 功能**；
> 要用上需重新执行 `packaging/build_mac.sh`（或 Windows 上的 `build_windows.ps1`）。

---

## 7. 风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| Qt 跨线程操作控件崩溃 | 高 | 严格执行"信号传数据、主线程碰控件"；代理线程只调信号与加锁数据结构 |
| mitmproxy 版本 API 变动 | 中 | 锁定 mitmproxy 大版本；DumpMaster 用法属稳定面，`request` hook 造 response 是官方 map local 同款路线 |
| CustomRules.js 解析覆盖不足 | 中 | 产品层面明确"启发式"定位；预览页展示跳过原因，用户可手工补齐 |
| PyInstaller 漏打包 mitmproxy 的动态模块 | 中 | spec 中显式收集；打包后必须完整回归（Gate 6），不接受"源码能跑就算完" |
| PyInstaller 不可交叉打包 | 中 | 已在方案 A 内消化：两个平台各一份构建脚本，用户在对应 OS 执行 |
| Windows 防火墙/杀毒误报 | 低 | 手册写明允许专用网络 + 加白名单 |
| 大文件读取阻塞 asyncio 事件循环 | 中 | 文件读取走 `asyncio.to_thread`；超过 100MB 拒绝并返回 502 |
| macOS 首次运行安全提示（未签名） | 低 | README 说明右键打开；后续可申请开发者证书 |
| 大 body（图片/视频）拖垮 UI | 中 | 摘要 + 截断预览 + 按需回查；表格虚拟化行数 |
| `.app` 体积 ~100MB | 低 | Qt 宿命；README 说明，不优化 |
| 恢复出的会话无法重放（`Flow.copy()` 需连接对象） | 中 | 恢复时合成 `Client`/`Server`（`Server` 必须给 `address=`），并加单测守住；这是"恢复出来的只是个死记录"的典型翻车点 |
| 域名映射把 `.` 当通配（`api.prod.com` 命中 `apiXprodYcom`） | 中 | 只有出现 `* + ? [ ] ( ) { } \| \ ^ $` 才按正则处理，普通域名整串 `re.escape()`；单测直接验 `re.sub` 结果 |
| `map_remote` 选项 spec 分隔符与正则/URL 撞车 | 中 | 用不可见字符 `\x1f` 当分隔符；分隔符若出现在 subject/replacement 里直接判该规则不可用（不静默错位） |
| 弱网用 `time.sleep` 卡死事件循环 | 中 | 只用 `async def` 钩子 + `await asyncio.sleep()`（mitmproxy 会 await 协程钩子）；`MAX_DELAY_MS` 兜住手滑的大数值 |
| 排序把格式化字符串当数值比（`1.3 MB` < `812 B`） | 低 | 走代理模型的 `SORT_ROLE` 给数值列真数值；`lessThan` 做类型分组防 `int < str` 崩溃 |
| body 格式化失败导致内容"消失" | 高 | 硬规则：一律回落原文 + 说明原因，绝不吞 body；有专门回归用例 |
| 表单误判（普通文本被拆成 key/value） | 中 | 只按 content-type 认，且要求 body 至少一个 `=`；`parse_qsl` 会把无 `=` 的整串当空值 key |
| JSON 着色盖掉搜索高亮 | 中 | 着色只改前景不改背景；数字/关键字染色跳过字符串内部 |
| JSON 着色在深色主题下不可读 | 低 | 亮/暗两套配色，按 `QPalette.Base` 亮度自动选 |
| 深嵌套 JSON 触发 `RecursionError`（不是 `ValueError` 子类） | 高 | `format_json_text` 显式接住并回落原文——漏接就是整个界面崩掉 |
| 大 JSON 被 512KB 截断后解析失败 → 反而丢掉格式化 | 高 | 先完整解析、只截断**渲染结果**（解析 4MB 只要 ~30ms，瓶颈在渲染不在解析） |
| 超长单行换行把界面卡死（300KB 单行 ≈ 1.2s，超线性） | 中 | `WRAP_MAX_LINE_CHARS` 闸门：超长行临时不换行**并说明**，用户切 JSON 视图（多行）即可换行 |
| 语法着色拖慢大 body（2 万行 ≈ 260ms，按 block 线性） | 中 | 渲染文本超 `HIGHLIGHT_LIMIT` 就暂停着色——丢颜色不丢流畅 |
| 自动滚动抢走用户手动翻到的位置 | 中 | 只在"停在最新端 **且** 按到达顺序排列"时才滚；用户按别的列排序时完全不动 |
| WebSocket 消息高频到达刷爆 UI | 中 | 增量追加（不重建）、表格上限 2000 行、只在原本停在底部时才跟着滚 |
| WS 会话保存/恢复时消息丢失 | 低 | v1.11 起已入库（条数/预算双闸，超限置 `truncated`）；旧文件无该字段照常加载，summary 计数按实际存储数回填 |
| 客户端用 `ws://` 发握手被 mitmproxy 判非法 scheme | 低 | 文档写明须用 `http://`（RFC 6455 规定，主流客户端如此）；mitmproxy 层行为，不在本工具内改 |
| Base64 解码把任意文本都"解"成乱码 | 中 | 先用正则校验字符集，不合法明确报错；不用 `b64decode(validate=False)` 的宽松模式 |
| URL 编解码把 `+` 与空格搞混 | 中 | 编码/解码各给「路径」与「表单」两项，语义不合一；`unquote_plus` 没有字节版，自己按 `+ → 空格` 再 `unquote_to_bytes` |
| 编码转换失败时 UI 抛异常 | 高 | 所有转换收敛成 `Result(error=…)`；`run()` 兜底接所有异常 |
| JSON 报错无法定位（`Expecting ',' delimiter` 说了等于没说） | 高 | 给行列 + 出错行 + `^` 指针 + 8 类常见误用的"可能原因"，并提供跳转按钮 |
| `NaN`/`Infinity` 这里能解析、前端报错 | 中 | 严格模式用 `parse_constant` 拒绝，对齐 `JSON.parse` |
| JSONPath 深嵌套爆栈 | 中 | 树的遍历与递归下降全用迭代实现；实测 3000 层正常 |
| JSONPath 递归下降把结果倒过来 | 低 | 栈式遍历逆序压栈，保证按文档顺序返回（单测守着） |
| 树视图在大 JSON 上卡死 | 中 | 节点 ≥ 5000 就跳过并说明，引导用格式化文本或 JSONPath 缩小范围 |
| 状态提示被后续 `_set_status` 覆盖（换行/树跳过的说明丢了） | 低 | 渲染函数**返回**提示而不是直接写状态区，由调用方统一拼装（踩过一次） |
| 着色器两处各写一份导致配色不一致 | 低 | 抽到 `app/ui/highlight.py` 共用，body 视图与 JSON 页同一套 |

---

## 8. 测试计划

- **单元**：匹配算法（四种 type 边界：特殊正则字符、`*` 位置、空 value）、JSON 原子写、FARX 映射（官方样本）、JS 解析（典型/复杂片段）。
- **集成**：curl 脚本驱动 mock 命中/透传/307 导入规则；端口切换；规则热改即时生效。
- **端到端**：手机连代理装 CA → App 抓包 → 命中 mock；`.farx`/`.js` 导入全流程。
- **打包后回归**：`.app` 内重跑上述集成用例。

### 8.1 单元测试覆盖（截至 v1.13，`tests/` 共 820 例）

| 文件 | 覆盖点 |
|---|---|
| `test_rules.py` | 规则模型 / 四种匹配 / JSON 原子写 |
| `test_farx.py` / `test_jsscript.py` | Fiddler 规则导入（含官方样本回归） |
| `test_mock.py` | mock 内联 / 本地文件 / 延迟 / 异常码 / `$1` 替换 |
| `test_replay.py` | 重放副本机制、编辑后重放、端到端上游收到第二次请求 |
| `test_textutil.py` | body 解码策略（charset → UTF-8 → hex） |
| `test_filter_model.py` | 过滤 + 搜索（含与排序共存） |
| `test_export.py` | cURL（bash/cmd）/ 原始报文 / **完整响应** / HAR 1.2 / 响应 Body / **多选批量** |
| `test_sort_and_batch.py` | 排序角色取值、`lessThan` 类型分组、`#` 列语义、多选选中项顺序、批量导出校验 |
| `test_session.py` | JSONL 往返、坏行容忍、body 预算、**活会话重建（`Flow.copy()` 不崩）**、`marked`/`is_replay`/时间戳还原、退出快照与归档、**WS 消息持久化**（逐条编解码/预算与条数双闸/关闭码/旧文件兼容/summary 计数按实际存储数回填/截断标记透出） |
| `test_network.py` | 弱网档位表、延迟折算边界、映射 spec 生成（`.` 不转义陷阱、端口越界、非法正则、spec 分隔符） |
| `test_network_panel.py` | 面板 ↔ 配置双向一致、settings.json 往返、主窗口接线（addon 齐 / `map_remote` 选项 / 即时落盘） |
| `test_bodyview.py` | content-type 判定（`*+json` 变体 / 表单 / 图片 / 嗅探边界）、JSON 格式化与失败原因、表单 URL 解码与空值、十六进制布局、面板六模式渲染与粘性、结构化视图上的搜索高亮、**大内容三道闸门**（深嵌套 / 大 JSON 不丢格式化 / 着色暂停）、换行开关与闸门、压缩提示与兜底解压、图片预览与缩放、WS 消息表与 payload |
| `test_list_and_ws.py` | 行内更新（`dataChanged`、不新增行）、WS 徽标与悬停提示、WS 摘要体积/耗时口径、钩子接线、信号桥、列表顺序（倒序/正序）与自动滚动的克制条件、新设置字段往返与旧文件兼容 |
| `test_codec.py` | 27 种转换的正/反用例（URL 两种 `+` 语义、Base64 严格校验、Hex/Base64 双形态识别、Deflate 三种头、JWT 过期提示、时间戳秒/毫秒）、注册表自洽（反向成对、分组头不可选、hint 齐全）、面板接线（防抖/粘性/回填/上限交给按钮）、主窗口「送 body」按子页分流 |
| `test_json_tools.py` | 解析与错误定位（行/列/出错行/`^`/8 类原因提示、严格模式拒 NaN、重复 key 提示、深嵌套 RecursionError 被接住）、序列化（缩进档位/中文不转义/大结果截断）、JSONPath（下标/负号/切片/通配/递归下降顺序/过滤六比较符与 `&&`/`||`/联合/语法错误位置/命中上限与遍历上限）、JSON 页（实时格式化、视图切换、树上限跳过、错误跳到位置、着色与换行闸门复用） |
| `test_jsondiff.py` | 键级 diff（增/删/改、容器类型变化、bool vs 数字、key 顺序、列表下标对齐、根替换）、10000 层深嵌套不爆栈、双上限截断、报告渲染与截断说明、difflib 行级 diff 与超行截断 |
| `test_replay_compare.py` | 对比对话框（一致/键级 diff/headers 差异/文本 diff/二进制/无响应回落请求/复制）、`diff_headers` 多值语义、pending 登记与 id 精确关联、非重放与异 id 不触发、超时清理、对话框保留上限、入口接线（登记/取消/纯重放不登记/代理未启动） |
| `test_mark_and_hits.py` | 命中计数（线程安全 20 线程、不持久化、回调异常隔离、MockAddon 命中/未命中/禁用、信号到规则页完整链路）、comment 字段（summarize、会话往返）、列表显示优先级与 tooltip、右键备注写入/取消/清除 |
| `test_maplocal.py` | local/remote 形态识别（`looks_like_path`、`kind`、remote spec 拒 local）、`map_local_entries` 过滤、addon 行为（命中/缺失透传/查询串/index.html/charset/`..` 与编码穿越/符号链接逃逸/POST 不拦/HEAD 空 body/超大透传/热更新）、证书页多候选 IP 与二维码 SVG/降级 |
| `test_json_tools.py`（JSON 比对与函数部分） | 比对页（一致/键级差异三态行/非法侧定位且内容不丢/单侧为空/交换/复制/清空/差异表 500 行截断）、ToolPanel 三子页与送 body 分流、JSONPath 聚合函数（length 三形态、min/max 单数组与多命中、非数字报错、空结果报错、字段名与函数不冲突、递归下降后聚合） |
| `test_e2e_proxy.py` | 真代理端到端（mock 透传 / HTTPS 解密 / FARX 在线生效 / 上游 IP） |
| `test_entrypoint.py` | 入口装配防回归（代理唯一持有） |
| `test_rule_editor.py` | 规则编辑器：方法下拉（默认任意/选中保存）、重定向模式往返与校验、redirect 下 status/headers 置灰、存量规则编辑不丢字段 |
| `test_httpclient.py` | 本地最小 HTTP 服务真发真收：GET/POST 与 body、重复响应头保序、3xx 不跟随、404 照常返回、非法 URL/不可达收敛、方法名规范化 |
| `test_api_panel.py` | API 调试页：load_request 灌表、真发真收显示 HTTP 200 与 BodyPane 内容、不可达显示 ✗、空 URL 拦截、`_seq` 防陈旧结果 |
| `test_sysproxy.py` | 系统代理接管/还原：状态记录与回滚、崩溃恢复、Windows 分支、settings 开关往返、主窗口接线（启动接管/停止还原/关闭同步还原） |
| `test_bugfix_regressions.py` | v1.12 bug 修复回归：settings 坏数字回落、geometry base64 往返、流式 raw_content=None 不丢行、GBK body 保存恢复字节一致、重定向指回代理被拒 |
| `test_flow_limit.py` / `test_server_ip.py` | 保存条数精确裁剪 / 服务器 IP 列 |

### 8.2 关键冒烟（offscreen + 真代理）

新增能力都跑过 `QT_QPA_PLATFORM=offscreen` 下**真实端口、真实 socket、真实 asyncio 线程**的冒烟，
因为有些事只有跑起来才知道：延迟到底有没有加到客户端看到的耗时上、映射到底有没有改写上游地址。

| 冒烟 | 断言要点 |
|---|---|
| 完整响应导出 | 落盘 240 字节响应文件（含 `X-Trace-Id` / `Set-Cookie` / 中文 JSON body），线格式为 CRLF；无响应分支走提示而非空文件 |
| 多选批量 | 剪贴板/文件内逐条分段正确；「仅响应 Body」多选被拦住 |
| 会话保存恢复 | 保存 → 恢复 → 详情可见 → **重放成功**；超上限丢最旧 |
| 弱网限速 | 基线 < 0.8s；`custom 300ms + 32kbps` 下 4096B 响应 ≈1.3s、17B 响应 ≈0.3s；关闭后回落基线 |
| 域名映射 | 不可解析域名 `mapped.invalid` 经代理后返回本地上游内容（`X-Upstream` 头为证）；未映射地址仍失败；删行即失效；重启窗口回灌 |
| body 视图 | 真请求 → 列表 → 选中 → 详情面板自动挑视图：JSON 缩进且中文不转义、key 顺序不变、着色开启；`text/plain` 里的 JSON 被嗅探；HTML/二进制不被误判；WebForm 请求解码成 `[("name","张三"),("city","北京"),("flag","")]`；手动切换粘性；JSON 解析失败时内容不丢 |
| 大内容 / 压缩 / 图片 / 顺序 / WebSocket（53 项） | 800KB JSON 仍被格式化且不误报解析失败（重渲染 93ms）；gzip 响应显示解压后中文并提示"已解压 gzip"；PNG 自动进图片视图并给出 `PNG · 8×8`；300KB 单行换行被闸门拦下且内容完整；倒序后最新在顶部、正序回到到达序号、顺序落盘；**真 WS 服务端 + 真代理**：握手 101、3 发 3 收回声全部入表、关闭码 1000、消息数与体积口径正确、点消息看 payload、`ws://` 显示、含 WS 的会话能存能恢复 |
| 工具页（47 项） | 真请求 → 列表 → 右键「在工具页中打开 body」→ JSON 子页直接格式化并给出节点数/深度；`Ctrl+Shift+T`/`Ctrl+Shift+J` 直达对应子页；非法 JSON 显示行列 + `^` 指针且「跳到出错位置」真的把光标移过去；JSONPath 提取 `.data.list[*]`、`$..name`、过滤表达式均正确，语法错误与零命中各有明确提示；编码转换 27 种抽查（URL 的 `+` 两种语义、Base64 双向、Gzip→Base64、JWT、时间戳）；大 JSON 走「立即转换」按钮而非实时路径 |
| Map Local + 二维码（26 项） | 真代理 + 真上游：未配置走上游；面板加 local 规则（无"填写不完整"误报）→ 本地命中（body/content-type/index.html/charset）、缺失回落上游、`..` 与编码穿越不泄密、列表 `LOCAL:` 标记、删行失效、重启回灌；证书下载页多 IP 各带一枚内联 SVG 二维码 |
| 重放并对比（21 项） | 真代理 + 真上游（按命中次数返回 `{"v":1}`/`{"v":2}`）：抓包 → 选中 → 「重放并对比」→ pending 登记 → **对比框自动弹出**且报 `~ $.v: 1 → 2`；新行进列表带 REPLAY 徽标、id 与副本一致；原会话未被动过；剪贴板与报告一致；超时 pending 被清并提示；全程无 critical 弹窗 |
| JSON 比对页 + JSONPath 函数（22 项） | 真请求 → 右键送 body 到比对页左侧 → 右侧贴修改版 → 差异表 3 行（改/增/删路径正确）→ 交换左右 → JSONPath `max()/min()/length()` 四个表达式全部正确 → 复制差异进剪贴板；菜单「JSON 比对…`Ctrl+Shift+D`」切页生效 |
| WS 消息持久化（19 项） | 真 WS 服务端 + 真代理 + 真 MainWindow：握手 101、文本/二进制/关闭 3 帧入表、`WS 3` 徽标、详情页 3 行消息 → 保存后 `ws_messages` 落盘（3 条 + 关闭码 1000）→ 清空 → 恢复 → 消息表仍是 3 行且二进制 payload 原样；全程无 critical 弹窗 |


---

## 9. 里程碑

| 里程碑 | 内容 | 对应 Gate |
|---|---|---|
| M1 | 代理能跑、流量可见 | Gate 2 |
| M2 | Mock 引擎可用（本机） | Gate 3 |
| M3 | Fiddler 规则可导入 | Gate 4 |
| M4 | 完整桌面体验（含手机抓包） | Gate 5 |
| M5 | 交付双平台客户端（.app + .exe） | Gate 6~7 |
| M6 | 体验补强：完整响应导出、排序 / 多选批量、会话保存恢复、弱网 + 域名映射 | Gate 8 |

- 系统代理自动接管在 Windows 上走注册表路径，**未在 Windows 实机回归**（v1.13 在 macOS 真机验证接管→还原往返精确无损）。
