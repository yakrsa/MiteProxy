<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE TS>
<TS version="2.1" language="en_US">
<context>
    <name>FlowStore</name>
    <message>
        <location filename="../ui/flow_store.py" line="39" />
        <source>方法</source>
        <extracomment>列头的翻译文案。**必须懒执行**：翻译器是在 app/main.py 里 QApplication 创建之后才装载的，若在 import 时求值会永远拿到中文原文。 字面量写死在这里（而不是 self.tr(变量)）是为了让 pyside6-lupdate 能抽到。</extracomment>
        <translation>Method</translation>
    </message>
    <message>
        <location filename="../ui/flow_store.py" line="41" />
        <source>服务器 IP</source>
        <translation>Server IP</translation>
    </message>
    <message>
        <location filename="../ui/flow_store.py" line="42" />
        <source>路径</source>
        <translation>Path</translation>
    </message>
    <message>
        <location filename="../ui/flow_store.py" line="43" />
        <source>状态</source>
        <translation>Status</translation>
    </message>
    <message>
        <location filename="../ui/flow_store.py" line="44" />
        <source>请求体</source>
        <translation>Request body</translation>
    </message>
    <message>
        <location filename="../ui/flow_store.py" line="45" />
        <source>响应</source>
        <translation>Response</translation>
    </message>
    <message>
        <location filename="../ui/flow_store.py" line="46" />
        <source>耗时(ms)</source>
        <translation>Duration (ms)</translation>
    </message>
    <message>
        <location filename="../ui/flow_store.py" line="47" />
        <source>标记</source>
        <translation>Mark</translation>
    </message>
</context>
<context>
    <name>MainWindow</name>
    <message>
        <location filename="../ui/main_window.py" line="531" />
        <source>文件</source>
        <extracomment>重放并对比：等重放响应到达的超时（秒）。超时说明上游没响应， 清理 pending 并在状态栏告知，避免永远等一个不会来的 flow。 对比对话框保留个数：开太多不关也不至于无限攒着 启动时是否询问恢复上次会话快照（脚本/测试可关掉，避免模态框阻塞） 系统代理接管/还原串行化：停代理与后台接管线程竞争时保证不漏还原 更新检测：checker 惰性创建（用到才建 QNetworkAccessManager）； _update_manual 标记本次是否用户手动触发（决定无更新/失败要不要提示）</extracomment>
        <translation>File</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="532" />
        <source>保存会话…</source>
        <translation>Save session…</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="537" />
        <source>打开会话…</source>
        <translation>Open session…</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="543" />
        <source>清除列表</source>
        <translation>Clear list</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="548" />
        <source>退出时自动保存会话</source>
        <translation>Auto-save session on exit</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="556" />
        <source>退出</source>
        <translation>Quit</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="561" />
        <source>工具</source>
        <translation>Tools</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="562" />
        <source>编码转换…</source>
        <translation>Encoding converter…</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="567" />
        <source>JSON 格式化 / 提取…</source>
        <translation>JSON format / extract…</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="572" />
        <source>JSON 比对…</source>
        <translation>JSON compare…</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="578" />
        <source>外观</source>
        <translation>Appearance</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="583" />
        <source>跟随系统</source>
        <translation>Follow system</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="584" />
        <source>浅色模式</source>
        <translation>Light mode</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="585" />
        <source>深色模式</source>
        <translation>Dark mode</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="598" />
        <source>语言</source>
        <translation>Language</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="615" />
        <source>帮助</source>
        <translation>Help</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="616" />
        <source>检查更新…</source>
        <translation>Check for updates…</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="619" />
        <source>意见反馈…</source>
        <translation>Feedback…</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="622" />
        <source>关于</source>
        <translation>About</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="637" />
        <source>语言已切换</source>
        <translation>Language changed</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="638" />
        <source>语言将在重启 MiteProxy 后生效。</source>
        <translation>The language will take effect after restarting MiteProxy.</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="2086" />
        <location filename="../ui/main_window.py" line="2096" />
        <source>检查更新</source>
        <translation>Check for updates</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="2087" />
        <source>暂时无法获取版本信息：{0}</source>
        <translation>Could not retrieve version information: {0}</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="2088" />
        <source>未知错误</source>
        <translation>unknown error</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="2097" />
        <source>当前已是最新版本（{0}）。</source>
        <translation>You are already on the latest version ({0}).</translation>
    </message>
</context>
<context>
    <name>RuleEditorDialog</name>
    <message>
        <location filename="../ui/rule_editor.py" line="92" />
        <source>规则名称:</source>
        <translation>Rule name:</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="105" />
        <source>如 /api/user/list 或 https?://.*/v1/.*</source>
        <translation>e.g. /api/user/list or https?://.*/v1/.*</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="113" />
        <source>URL 匹配:</source>
        <translation>URL match:</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="119" />
        <source>请求方法:</source>
        <translation>Request method:</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="126" />
        <source>从抓包请求带入的原始请求 Body（仅参考，不参与 URL 匹配）</source>
        <translation>Original request body captured from the request (reference only, not used for URL matching)</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="128" />
        <source>请求 Body:</source>
        <translation>Request body:</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="143" />
        <source>状态码(100-599):</source>
        <translation>Status code (100-599):</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="152" />
        <source>毫秒（0 = 不延迟）</source>
        <translation>milliseconds (0 = no delay)</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="154" />
        <source>模拟延迟:</source>
        <translation>Simulated delay:</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="160" />
        <source>直接输入内容</source>
        <translation>Enter content directly</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="161" />
        <source>返回本地文件</source>
        <translation>Return local file</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="162" />
        <source>重定向到其他 URL</source>
        <translation>Redirect to another URL</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="168" />
        <source>响应内容:</source>
        <translation>Response content:</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="173" />
        <source>如 https://staging.example.com/api/user，支持 $1 替换（正则捕获组）</source>
        <translation>e.g. https://staging.example.com/api/user, supports $1 substitution (regex capture group)</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="175" />
        <source>重定向到:</source>
        <translation>Redirect to:</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="178" />
        <source>响应 body，如 JSON / HTML …</source>
        <translation>Response body, e.g. JSON / HTML …</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="179" />
        <source>Body:</source>
        <translation>Body:</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="186" />
        <source>命中时读取该文件内容返回（请求时读取，改文件即生效）</source>
        <translation>Reads this file and returns its content on match (read at request time; edits take effect immediately)</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="188" />
        <source>浏览…</source>
        <translation>Browse…</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="192" />
        <source>文件路径:</source>
        <translation>File path:</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="211" />
        <source>添加 Header</source>
        <translation>Add header</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="213" />
        <source>删除选中行</source>
        <translation>Delete selected row</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="219" />
        <source>Headers:</source>
        <translation>Headers:</translation>
    </message>
</context>
<context>
    <name>RulesPanel</name>
    <message>
        <location filename="../ui/rules_panel.py" line="106" />
        <location filename="../ui/rules_panel.py" line="554" />
        <source>新增</source>
        <translation>New</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="107" />
        <location filename="../ui/rules_panel.py" line="540" />
        <source>编辑</source>
        <translation>Edit</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="108" />
        <location filename="../ui/rules_panel.py" line="113" />
        <location filename="../ui/rules_panel.py" line="552" />
        <source>删除</source>
        <translation>Delete</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="109" />
        <location filename="../ui/rules_panel.py" line="808" />
        <source>导出规则</source>
        <translation>Export rules</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="110" />
        <location filename="../ui/rules_panel.py" line="837" />
        <source>导入规则</source>
        <translation>Import rules</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="111" />
        <location filename="../ui/rules_panel.py" line="171" />
        <location filename="../ui/rules_panel.py" line="542" />
        <source>启用</source>
        <translation>Enable</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="112" />
        <location filename="../ui/rules_panel.py" line="542" />
        <source>停用</source>
        <translation>Disable</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="114" />
        <source>导出</source>
        <translation>Export</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="115" />
        <location filename="../ui/rules_panel.py" line="546" />
        <source>上移</source>
        <translation>Move up</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="116" />
        <location filename="../ui/rules_panel.py" line="547" />
        <source>下移</source>
        <translation>Move down</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="118" />
        <location filename="../ui/rules_panel.py" line="555" />
        <source>导入 Fiddler 规则</source>
        <translation>Import Fiddler rules</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="125" />
        <source>对勾选的规则生效；取消全部勾选后自动隐藏</source>
        <translation>Applies to checked rules; hides automatically when all are unchecked</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="127" />
        <source>只显示启用</source>
        <translation>Show enabled only</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="169" />
        <source>序号</source>
        <translation>No.</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="170" />
        <source>名称</source>
        <translation>Name</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="172" />
        <source>匹配</source>
        <translation>Match</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="173" />
        <source>动作</source>
        <translation>Action</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="174" />
        <source>来源</source>
        <translation>Source</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="175" />
        <source>命中</source>
        <translation>Hits</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="176" />
        <source>创建时间</source>
        <translation>Created</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="385" />
        <source>启用({0})</source>
        <translation>Enable ({0})</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="386" />
        <source>停用({0})</source>
        <translation>Disable ({0})</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="387" />
        <source>删除({0})</source>
        <translation>Delete ({0})</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="388" />
        <source>导出({0})</source>
        <translation>Export ({0})</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="550" />
        <source>置顶</source>
        <translation>Move to top</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="611" />
        <source>已置顶「{0}」</source>
        <translation>Moved 「{0}」 to top</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="646" />
        <location filename="../ui/rules_panel.py" line="657" />
        <source>提示</source>
        <translation>Notice</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="646" />
        <source>请先选择一条规则</source>
        <translation>Please select a rule first</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="657" />
        <source>请先勾选规则（末尾复选框）</source>
        <translation>Please check rules first (checkbox in the last column)</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="666" />
        <source>已将 {0} 条规则{1}</source>
        <translation>{0} rules {1}</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="668" />
        <source>已启用</source>
        <translation>enabled</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="668" />
        <source>已停用</source>
        <translation>disabled</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="731" />
        <source>确认删除</source>
        <translation>Confirm deletion</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="731" />
        <source>确定删除{0}？</source>
        <translation>Delete {0}?</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="746" />
        <source>选择 Fiddler 规则文件</source>
        <translation>Select Fiddler rules file</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="749" />
        <source>Fiddler 规则 (*.farx *.js);;FARX 规则包 (*.farx);;CustomRules.js (*.js);;所有文件 (*)</source>
        <translation>Fiddler rules (*.farx *.js);;FARX rule package (*.farx);;CustomRules.js (*.js);;All files (*)</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="761" />
        <location filename="../ui/rules_panel.py" line="847" />
        <source>导入失败</source>
        <translation>Import failed</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="768" />
        <location filename="../ui/rules_panel.py" line="851" />
        <location filename="../ui/rules_panel.py" line="860" />
        <source>无可导入规则</source>
        <translation>No rules to import</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="769" />
        <source>没有解析出可导入的规则。

{0}</source>
        <translation>No rules could be parsed.

{0}</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="770" />
        <source>文件为空或格式不符</source>
        <translation>The file is empty or the format is invalid</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="787" />
        <location filename="../ui/rules_panel.py" line="867" />
        <source>导入完成</source>
        <translation>Import complete</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="788" />
        <location filename="../ui/rules_panel.py" line="868" />
        <source>成功导入 {0} 条规则</source>
        <translation>Successfully imported {0} rules</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="810" />
        <location filename="../ui/rules_panel.py" line="839" />
        <source>MiteProxy 规则 (*.json);;所有文件 (*)</source>
        <translation>MiteProxy rules (*.json);;All files (*)</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="829" />
        <source>导出完成</source>
        <translation>Export complete</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="830" />
        <source>已导出{0}规则到
{1}</source>
        <translation>Exported {0} rules to
{1}</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="847" />
        <source>文件读取/解析失败：{0}</source>
        <translation>Failed to read or parse the file: {0}</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="851" />
        <source>文件里没有规则数据。</source>
        <translation>The file contains no rule data.</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="860" />
        <source>文件里的规则格式无法识别。</source>
        <translation>The rule format in the file is not recognized.</translation>
    </message>
</context>
<context>
    <name>UpdateDialog</name>
    <message>
        <location filename="../ui/update_dialog.py" line="30" />
        <source>发现新版本</source>
        <translation>New version available</translation>
    </message>
    <message>
        <location filename="../ui/update_dialog.py" line="42" />
        <source>新版本 {0} 已发布（当前 {1}）</source>
        <translation>Version {0} is now available (current: {1})</translation>
    </message>
    <message>
        <location filename="../ui/update_dialog.py" line="52" />
        <source>发布日期：{0}</source>
        <translation>Released: {0}</translation>
    </message>
    <message>
        <location filename="../ui/update_dialog.py" line="56" />
        <source>本次更新内容：</source>
        <translation>What's new:</translation>
    </message>
    <message>
        <location filename="../ui/update_dialog.py" line="66" />
        <source>（该版本未提供变更说明）</source>
        <translation>(No changelog provided for this version)</translation>
    </message>
    <message>
        <location filename="../ui/update_dialog.py" line="71" />
        <source>前往下载</source>
        <translation>Go to download</translation>
    </message>
    <message>
        <location filename="../ui/update_dialog.py" line="75" />
        <source>关闭</source>
        <translation>Close</translation>
    </message>
</context>
<context>
    <name>main</name>
    <message>
        <location filename="../main.py" line="97" />
        <source>MiteProxy 已在运行</source>
        <translation>MiteProxy is already running</translation>
    </message>
    <message>
        <location filename="../main.py" line="98" />
        <source>检测到 MiteProxy 已有一个实例在运行，请切换到已打开的窗口。</source>
        <translation>Another instance of MiteProxy is already running. Please switch to the open window.</translation>
    </message>
</context>
</TS>
