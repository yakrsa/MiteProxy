<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE TS>
<TS version="2.1" language="en_US">
<context>
    <name>ApiPanel</name>
    <message>
        <location filename="../ui/api_panel.py" line="74"/>
        <source>校验证书</source>
        <extracomment>请求 body 输入上限（超出直接拦，别等线程里炸） 请求完成（后台线程 → 主线程）；payload 是 ApiResponse</extracomment>
        <translation>Verify certificate</translation>
    </message>
    <message>
        <location filename="../ui/api_panel.py" line="76"/>
        <source>调试对象常是自签 / 内网证书，默认跳过校验；
要验证正式证书链再勾上。</source>
        <translation>Debug targets are often self-signed or internal certificates, so verification is skipped by default;
check this to verify a formal certificate chain.</translation>
    </message>
    <message>
        <location filename="../ui/api_panel.py" line="79"/>
        <location filename="../ui/api_panel.py" line="255"/>
        <source>发送</source>
        <translation>Send</translation>
    </message>
    <message>
        <location filename="../ui/api_panel.py" line="97"/>
        <source>请求 Header</source>
        <translation>Request Headers</translation>
    </message>
    <message>
        <location filename="../ui/api_panel.py" line="109"/>
        <source>添加 Header</source>
        <translation>Add header</translation>
    </message>
    <message>
        <location filename="../ui/api_panel.py" line="113"/>
        <source>删除选中行</source>
        <translation>Delete selected row</translation>
    </message>
    <message>
        <location filename="../ui/api_panel.py" line="120"/>
        <source>请求 Body（GET / HEAD 时忽略）：</source>
        <translation>Request body (ignored for GET / HEAD):</translation>
    </message>
    <message>
        <location filename="../ui/api_panel.py" line="126"/>
        <source>如 {&quot;name&quot;: &quot;张三&quot;}，或表单 a=1&amp;b=2</source>
        <translation>e.g. {&quot;name&quot;: &quot;Alice&quot;}, or form a=1&amp;b=2</translation>
    </message>
    <message>
        <location filename="../ui/api_panel.py" line="136"/>
        <source>尚未发送</source>
        <translation>Not sent yet</translation>
    </message>
    <message>
        <location filename="../ui/api_panel.py" line="188"/>
        <source>已带入请求，点击「发送」（或 Ctrl+Return）</source>
        <translation>Request loaded. Click &quot;Send&quot; (or Ctrl+Return)</translation>
    </message>
    <message>
        <location filename="../ui/api_panel.py" line="216"/>
        <source>请先填 URL</source>
        <translation>Please enter a URL first</translation>
    </message>
    <message>
        <location filename="../ui/api_panel.py" line="221"/>
        <source>请求 body 超过 50MB 上限</source>
        <translation>Request body exceeds the 50MB limit</translation>
    </message>
    <message>
        <location filename="../ui/api_panel.py" line="231"/>
        <source>发送中…</source>
        <translation>Sending…</translation>
    </message>
    <message>
        <location filename="../ui/api_panel.py" line="232"/>
        <source>请求中…</source>
        <translation>Requesting…</translation>
    </message>
    <message>
        <location filename="../ui/api_panel.py" line="271"/>
        <source>HTTP {0} {1} · {2}ms · {3} 字节 · {4} 个响应头</source>
        <translation>HTTP {0} {1} · {2}ms · {3} bytes · {4} response headers</translation>
    </message>
    <message>
        <location filename="../ui/api_panel.py" line="146"/>
        <source>响应 Header</source>
        <translation>Response headers</translation>
    </message>
</context>
<context>
    <name>BodyPane</name>
    <message>
        <location filename="../ui/detail_panel.py" line="334"/>
        <source>换行</source>
        <translation>Wrap</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="337"/>
        <source>超长行自动折行显示。单行超过 {0}KB 时会自动临时关闭（换行会让界面卡顿）。</source>
        <translation>Wrap long lines automatically. Temporarily disabled when a single line exceeds {0}KB (wrapping makes the UI laggy).</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="344"/>
        <source>图片缩放</source>
        <translation>Image zoom</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="382"/>
        <source>名称</source>
        <translation>Name</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="382"/>
        <source>值</source>
        <translation>Value</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="602"/>
        <source>已按 {0} 压缩，但解压失败，显示的是原始压缩字节</source>
        <translation>Compressed with {0}, but decompression failed; showing the raw compressed bytes</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="561"/>
        <location filename="../ui/detail_panel.py" line="997"/>
        <source>已截断：会话快照单条只保留前 {0}KB，内容不完整（重新抓包可看全）</source>
        <translation>Truncated: session snapshots keep only the first {0}KB of each body, so the content is incomplete (capture again to see all of it)</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="558"/>
        <location filename="../ui/detail_panel.py" line="990"/>
        <source>已截断：快照只保留前 {0}KB，原 {1}KB（重新抓包可看全）</source>
        <translation>Truncated: the snapshot keeps only the first {0}KB of {1}KB (capture again to see all of it)</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="682"/>
        <source>加载中 {0:.1f}/{1:.1f}MB</source>
        <translation>Loading {0:.1f}/{1:.1f}MB</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="707"/>
        <source>大内容加载中，加载完成后恢复换行</source>
        <translation>Loading large content; wrapping will be restored when loading finishes</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="779"/>
        <source>（无 body）</source>
        <translation>(no body)</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="784"/>
        <source>（空 body）</source>
        <translation>(empty body)</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="794"/>
        <source>自动 → {0}</source>
        <translation>Auto → {0}</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="812"/>
        <source>无法渲染为图片，已显示十六进制</source>
        <translation>Cannot render as image; showing hex instead</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="819"/>
        <source>已截断显示</source>
        <translation>Truncated</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="834"/>
        <source>无法按文本解码，已显示十六进制</source>
        <translation>Cannot decode as text; showing hex instead</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="842"/>
        <source>{0} 个字段（已 URL 解码）</source>
        <translation>{0} fields (URL-decoded)</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="844"/>
        <source>无法解析为表单，已显示原文</source>
        <translation>Cannot parse as form; showing raw text instead</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="356"/>
        <source>展开</source>
        <translation>Expand</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="361"/>
        <source>收起</source>
        <translation>Collapse</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="358"/>
        <source>展开全部节点（内容多时较慢）</source>
        <translation>Expand all nodes (slow for large content)</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="363"/>
        <source>收起到只剩根节点</source>
        <translation>Collapse everything except the root</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="724"/>
        <source>内容超过 {0}KB，树视图不适用（可用原文 / JSON 视图）</source>
        <translation>Larger than {0}KB: the tree view is unavailable (use Raw / JSON)</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="732"/>
        <source>无法解析为 JSON：{0}</source>
        <translation>Not valid JSON: {0}</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="739"/>
        <source>内容较大，全部展开会慢一些</source>
        <translation>Large content: expanding all may be slow</translation>
    </message>
</context>
<context>
    <name>BreakpointDialog</name>
    <message>
        <location filename="../ui/breakpoint_dialog.py" line="49"/>
        <source>断点：请求发出前</source>
        <extracomment>常用请求方法（断点里改方法用；保留自定义输入能力）</extracomment>
        <translation>Breakpoint: before request is sent</translation>
    </message>
    <message>
        <location filename="../ui/breakpoint_dialog.py" line="51"/>
        <source>断点：响应返回前</source>
        <translation>Breakpoint: before response is returned</translation>
    </message>
    <message>
        <location filename="../ui/breakpoint_dialog.py" line="59"/>
        <source>会话已挂起：改完点「继续」放行，点「中止」让请求失败。直接关闭窗口 = 原样放行。</source>
        <translation>Session held: click &quot;Release&quot; to continue, &quot;Abort&quot; to fail the request. Closing this window releases it unchanged.</translation>
    </message>
    <message>
        <location filename="../ui/breakpoint_dialog.py" line="81"/>
        <source>状态码:</source>
        <translation>Status code:</translation>
    </message>
    <message>
        <location filename="../ui/breakpoint_dialog.py" line="87"/>
        <source>原因短语（可留空）</source>
        <translation>Reason phrase (optional)</translation>
    </message>
    <message>
        <location filename="../ui/breakpoint_dialog.py" line="94"/>
        <source>Header（可增删改）</source>
        <translation>Headers (editable)</translation>
    </message>
    <message>
        <location filename="../ui/breakpoint_dialog.py" line="97"/>
        <source>名称</source>
        <translation>Name</translation>
    </message>
    <message>
        <location filename="../ui/breakpoint_dialog.py" line="97"/>
        <source>值</source>
        <translation>Value</translation>
    </message>
    <message>
        <location filename="../ui/breakpoint_dialog.py" line="110"/>
        <source>新增一行</source>
        <translation>Add row</translation>
    </message>
    <message>
        <location filename="../ui/breakpoint_dialog.py" line="112"/>
        <source>删除选中行</source>
        <translation>Delete selected row</translation>
    </message>
    <message>
        <location filename="../ui/breakpoint_dialog.py" line="120"/>
        <source>Body（可编辑）</source>
        <translation>Body (editable)</translation>
    </message>
    <message>
        <location filename="../ui/breakpoint_dialog.py" line="129"/>
        <source>中止请求</source>
        <translation>Abort request</translation>
    </message>
    <message>
        <location filename="../ui/breakpoint_dialog.py" line="132"/>
        <source>继续放行</source>
        <translation>Release</translation>
    </message>
</context>
<context>
    <name>Codec</name>
    <message>
        <location filename="../codec.py" line="41"/>
        <source>编解码</source>
        <translation>Codec</translation>
    </message>
    <message>
        <location filename="../codec.py" line="42"/>
        <source>格式 · 文本</source>
        <translation>Format · Text</translation>
    </message>
    <message>
        <location filename="../codec.py" line="43"/>
        <source>哈希</source>
        <translation>Hash</translation>
    </message>
    <message>
        <location filename="../codec.py" line="96"/>
        <source>结果不是合法 UTF-8，已按单字节显示；要看原始字节请再做一次「Hex 编码」</source>
        <extracomment>放到工具栏上的常用四项（对齐 Fiddler 里用得最多的那几个） 实时转换的输入上限，超过就让用户点按钮（见 codec_panel 的说明） 失败原因；非 None 时 text 为空 成功但需要说明（如「已按单字节显示」「压缩率」）</extracomment>
        <translation>The result is not valid UTF-8 and is shown byte by byte; run &quot;Hex encode&quot; again to see the raw bytes</translation>
    </message>
    <message>
        <location filename="../codec.py" line="111"/>
        <source>输入为空</source>
        <translation>Input is empty</translation>
    </message>
    <message>
        <location filename="../codec.py" line="131"/>
        <source>输入既不是 Hex 也不是 Base64——二进制数据请先用其中一种形态贴进来</source>
        <translation>Input is neither Hex nor Base64 — please paste binary data in one of those two forms</translation>
    </message>
    <message>
        <location filename="../codec.py" line="165"/>
        <source>不是合法的 Base64（只认 A-Z a-z 0-9 + / - _，末尾 = 补齐）</source>
        <translation>Not valid Base64 (only A-Z a-z 0-9 + / - _, with = padding at the end)</translation>
    </message>
    <message>
        <location filename="../codec.py" line="175"/>
        <source>Base64 解码失败：{0}</source>
        <translation>Base64 decoding failed: {0}</translation>
    </message>
    <message>
        <location filename="../codec.py" line="189"/>
        <source>十六进制长度应为偶数，当前 {0} 个字符</source>
        <translation>Hex length must be even; currently {0} characters</translation>
    </message>
    <message>
        <location filename="../codec.py" line="191"/>
        <source>含非十六进制字符（只认 0-9 a-f A-F）</source>
        <translation>Contains non-hex characters (only 0-9 a-f A-F are accepted)</translation>
    </message>
    <message>
        <location filename="../codec.py" line="227"/>
        <source>不是合法的 JSON 字符串：{0}</source>
        <translation>Not a valid JSON string: {0}</translation>
    </message>
    <message>
        <location filename="../codec.py" line="265"/>
        <source>UTF-8 {0}B → gzip {1}B → Base64 {2} 字符</source>
        <translation>UTF-8 {0}B → gzip {1}B → Base64 {2} chars</translation>
    </message>
    <message>
        <location filename="../codec.py" line="279"/>
        <source>（按 {0} 解析，解压后 {1}B）</source>
        <translation>(parsed as {0}; {1}B after decompression)</translation>
    </message>
    <message>
        <location filename="../codec.py" line="282"/>
        <source>Gzip 解压失败：输入应是 gzip 数据的 Base64 或 Hex</source>
        <translation>Gzip decompression failed: input should be Base64 or Hex of gzip data</translation>
    </message>
    <message>
        <location filename="../codec.py" line="291"/>
        <source>裸 deflate</source>
        <translation>raw deflate</translation>
    </message>
    <message>
        <location filename="../codec.py" line="292"/>
        <source>zlib 头</source>
        <translation>zlib header</translation>
    </message>
    <message>
        <location filename="../codec.py" line="302"/>
        <source>（按 {0} 解析，{1}，解压后 {2}B）</source>
        <translation>(parsed as {0}, {1}; {2}B after decompression)</translation>
    </message>
    <message>
        <location filename="../codec.py" line="305"/>
        <source>Deflate 解压失败：输入应是 deflate/zlib 数据的 Base64 或 Hex</source>
        <translation>Deflate decompression failed: input should be Base64 or Hex of deflate/zlib data</translation>
    </message>
    <message>
        <location filename="../codec.py" line="323"/>
        <source>（已自动去掉 Bearer 前缀）</source>
        <translation>(Bearer prefix removed automatically)</translation>
    </message>
    <message>
        <location filename="../codec.py" line="329"/>
        <source>JWT 应由 header.payload.signature 三段组成（Bearer 前缀会自动去掉）</source>
        <translation>A JWT should consist of header.payload.signature (the Bearer prefix is removed automatically)</translation>
    </message>
    <message>
        <location filename="../codec.py" line="336"/>
        <source>{0} 不是合法的 Base64URL</source>
        <translation>{0} is not valid Base64URL</translation>
    </message>
    <message>
        <location filename="../codec.py" line="354"/>
        <source>{0}（未校验签名）</source>
        <translation>{0} (signature not verified)</translation>
    </message>
    <message>
        <location filename="../codec.py" line="372"/>
        <source>已过期</source>
        <translation>Expired</translation>
    </message>
    <message>
        <location filename="../codec.py" line="374"/>
        <source>剩余 {0} 天</source>
        <translation>{0} days left</translation>
    </message>
    <message>
        <location filename="../codec.py" line="376"/>
        <source>即将过期（24 小时内）</source>
        <translation>Expiring soon (within 24 hours)</translation>
    </message>
    <message>
        <location filename="../codec.py" line="390"/>
        <source>请输入数字时间戳（秒或毫秒）</source>
        <translation>Please enter a numeric timestamp (seconds or milliseconds)</translation>
    </message>
    <message>
        <location filename="../codec.py" line="398"/>
        <source>时间戳超出可表示范围：{0}</source>
        <translation>Timestamp out of representable range: {0}</translation>
    </message>
    <message>
        <location filename="../codec.py" line="399"/>
        <source>毫秒</source>
        <translation>milliseconds</translation>
    </message>
    <message>
        <location filename="../codec.py" line="400"/>
        <source>秒</source>
        <translation>seconds</translation>
    </message>
    <message>
        <location filename="../codec.py" line="401"/>
        <source>{0}（本地）
{1}（UTC）
原始数值 {2}，按{3}解释</source>
        <translation>{0} (local)
{1} (UTC)
Raw value {2}, interpreted as {3}</translation>
    </message>
    <message>
        <location filename="../codec.py" line="431"/>
        <source>无法解析日期，试试 2026-10-14 00:17:33 或 2026-10-14T00:17:33Z</source>
        <translation>Cannot parse the date. Try 2026-10-14 00:17:33 or 2026-10-14T00:17:33Z</translation>
    </message>
    <message>
        <location filename="../codec.py" line="435"/>
        <source>{0} 看起来是时间戳而不是日期，请用「时间戳 → 日期」</source>
        <translation>{0} looks like a timestamp rather than a date. Please use &quot;Timestamp → Date&quot;</translation>
    </message>
    <message>
        <location filename="../codec.py" line="438"/>
        <source>带时区偏移</source>
        <translation>with timezone offset</translation>
    </message>
    <message>
        <location filename="../codec.py" line="438"/>
        <source>按本地时区解释</source>
        <translation>interpreted in local timezone</translation>
    </message>
    <message>
        <location filename="../codec.py" line="440"/>
        <source>{0}
{1}（毫秒）
{2}，{3}</source>
        <translation>{0}
{1} (ms)
{2}, {3}</translation>
    </message>
    <message>
        <location filename="../codec.py" line="455"/>
        <source>URL 编码</source>
        <translation>URL encode</translation>
    </message>
    <message>
        <location filename="../codec.py" line="455"/>
        <source>空格 → %20；除字母数字与 -_.~ 外全部转义（RFC 3986）</source>
        <translation>Spaces → %20; everything except alphanumerics and -_.~ is escaped (RFC 3986)</translation>
    </message>
    <message>
        <location filename="../codec.py" line="456"/>
        <source>URL 编码（表单）</source>
        <translation>URL encode (form)</translation>
    </message>
    <message>
        <location filename="../codec.py" line="456"/>
        <source>空格 → +，用于 application/x-www-form-urlencoded</source>
        <translation>Spaces → +, for application/x-www-form-urlencoded</translation>
    </message>
    <message>
        <location filename="../codec.py" line="457"/>
        <source>URL 解码</source>
        <translation>URL decode</translation>
    </message>
    <message>
        <location filename="../codec.py" line="457"/>
        <source>%XX 还原；+ 保持为加号（适用于路径与 query）</source>
        <translation>%XX restored; + stays a plus sign (for paths and query strings)</translation>
    </message>
    <message>
        <location filename="../codec.py" line="458"/>
        <source>URL 解码（表单）</source>
        <translation>URL decode (form)</translation>
    </message>
    <message>
        <location filename="../codec.py" line="458"/>
        <source>%XX 还原，且 + 视为空格（表单语义）</source>
        <translation>%XX restored and + treated as a space (form semantics)</translation>
    </message>
    <message>
        <location filename="../codec.py" line="459"/>
        <source>Base64 编码</source>
        <translation>Base64 encode</translation>
    </message>
    <message>
        <location filename="../codec.py" line="459"/>
        <source>UTF-8 字节 → Base64（标准字母表，含 + /）</source>
        <translation>UTF-8 bytes → Base64 (standard alphabet, including + /)</translation>
    </message>
    <message>
        <location filename="../codec.py" line="460"/>
        <source>Base64 解码</source>
        <translation>Base64 decode</translation>
    </message>
    <message>
        <location filename="../codec.py" line="460"/>
        <source>自动忽略换行空格；含 - _ 时按 URL-safe 字母表解</source>
        <translation>Newlines and spaces are ignored automatically; decoded with the URL-safe alphabet when - _ are present</translation>
    </message>
    <message>
        <location filename="../codec.py" line="461"/>
        <source>Hex 编码</source>
        <translation>Hex encode</translation>
    </message>
    <message>
        <location filename="../codec.py" line="461"/>
        <source>UTF-8 字节 → 小写十六进制串</source>
        <translation>UTF-8 bytes → lowercase hex string</translation>
    </message>
    <message>
        <location filename="../codec.py" line="462"/>
        <source>Hex 解码</source>
        <translation>Hex decode</translation>
    </message>
    <message>
        <location filename="../codec.py" line="462"/>
        <source>十六进制串 → 文本；容忍空格、冒号与 0x 前缀</source>
        <translation>Hex string → text; tolerates spaces, colons and the 0x prefix</translation>
    </message>
    <message>
        <location filename="../codec.py" line="463"/>
        <source>HTML 实体编码</source>
        <translation>HTML entity encode</translation>
    </message>
    <message>
        <location filename="../codec.py" line="463"/>
        <source>&amp; &lt; &gt; &quot; &apos; → &amp;amp; &amp;lt; … 可直接贴进 HTML 属性</source>
        <translation>&amp; &lt; &gt; &quot; &apos; → &amp;amp; &amp;lt; … can be pasted directly into HTML attributes</translation>
    </message>
    <message>
        <location filename="../codec.py" line="464"/>
        <source>HTML 实体解码</source>
        <translation>HTML entity decode</translation>
    </message>
    <message>
        <location filename="../codec.py" line="464"/>
        <source>&amp;amp; &amp;#x27; &amp;nbsp; 等实体还原为字符</source>
        <translation>Entities such as &amp;amp; &amp;#x27; &amp;nbsp; are restored to characters</translation>
    </message>
    <message>
        <location filename="../codec.py" line="465"/>
        <source>Unicode 转义</source>
        <translation>Unicode escape</translation>
    </message>
    <message>
        <location filename="../codec.py" line="465"/>
        <source>中文 → \u4e2d\u6587，换行 → \n（字符串字面量形态）</source>
        <translation>Chinese → \u4e2d\u6587, newline → \n (string-literal form)</translation>
    </message>
    <message>
        <location filename="../codec.py" line="466"/>
        <source>Unicode 反转义</source>
        <translation>Unicode unescape</translation>
    </message>
    <message>
        <location filename="../codec.py" line="466"/>
        <source>\u4e2d\u6587 → 中文，同时支持 \x41 \n \t</source>
        <translation>\u4e2d\u6587 → Chinese; also supports \x41 \n \t</translation>
    </message>
    <message>
        <location filename="../codec.py" line="467"/>
        <source>JSON 字符串转义</source>
        <translation>JSON string escape</translation>
    </message>
    <message>
        <location filename="../codec.py" line="467"/>
        <source>加 JSON 所需转义，不加外层引号</source>
        <translation>Adds the escapes JSON requires, without outer quotes</translation>
    </message>
    <message>
        <location filename="../codec.py" line="468"/>
        <source>JSON 字符串反转义</source>
        <translation>JSON string unescape</translation>
    </message>
    <message>
        <location filename="../codec.py" line="468"/>
        <source>去掉 JSON 转义；带不带外层引号都认</source>
        <translation>Removes JSON escapes; works with or without outer quotes</translation>
    </message>
    <message>
        <location filename="../codec.py" line="469"/>
        <source>Gzip 压缩</source>
        <translation>Gzip compress</translation>
    </message>
    <message>
        <location filename="../codec.py" line="469"/>
        <source>压缩后以 Base64 输出（mtime 固定，同输入同结果）</source>
        <translation>Outputs Base64 after compression (fixed mtime, so the same input gives the same result)</translation>
    </message>
    <message>
        <location filename="../codec.py" line="470"/>
        <source>Gzip 解压</source>
        <translation>Gzip decompress</translation>
    </message>
    <message>
        <location filename="../codec.py" line="470"/>
        <source>输入为 gzip 数据的 Base64 或 Hex，两种都试</source>
        <translation>Input is Base64 or Hex of gzip data; both are tried</translation>
    </message>
    <message>
        <location filename="../codec.py" line="471"/>
        <source>Deflate 解压</source>
        <translation>Deflate decompress</translation>
    </message>
    <message>
        <location filename="../codec.py" line="471"/>
        <source>裸 deflate / zlib 头 / gzip 三种都试</source>
        <translation>Tries raw deflate / zlib header / gzip</translation>
    </message>
    <message>
        <location filename="../codec.py" line="472"/>
        <source>JWT 解码</source>
        <translation>JWT decode</translation>
    </message>
    <message>
        <location filename="../codec.py" line="472"/>
        <source>拆 header / payload 并美化 JSON，签名不校验；带 exp 时提示是否过期</source>
        <translation>Splits header / payload and pretty-prints the JSON; the signature is not verified; expiry is reported when exp is present</translation>
    </message>
    <message>
        <location filename="../codec.py" line="473"/>
        <source>JSON 美化</source>
        <translation>JSON pretty-print</translation>
    </message>
    <message>
        <location filename="../codec.py" line="473"/>
        <source>缩进 2 空格，中文不转义</source>
        <translation>2-space indent, Chinese left unescaped</translation>
    </message>
    <message>
        <location filename="../codec.py" line="474"/>
        <source>JSON 压缩</source>
        <translation>JSON minify</translation>
    </message>
    <message>
        <location filename="../codec.py" line="474"/>
        <source>去掉所有多余空白，压成一行</source>
        <translation>Removes all extra whitespace and collapses to one line</translation>
    </message>
    <message>
        <location filename="../codec.py" line="475"/>
        <source>时间戳 → 日期</source>
        <translation>Timestamp → Date</translation>
    </message>
    <message>
        <location filename="../codec.py" line="475"/>
        <source>自动区分秒 / 毫秒，同时给出本地时间与 UTC</source>
        <translation>Auto-detects seconds / milliseconds and shows both local time and UTC</translation>
    </message>
    <message>
        <location filename="../codec.py" line="476"/>
        <source>日期 → 时间戳</source>
        <translation>Date → Timestamp</translation>
    </message>
    <message>
        <location filename="../codec.py" line="476"/>
        <source>秒与毫秒都给；无时区按本地时区解释</source>
        <translation>Gives both seconds and milliseconds; no timezone means local timezone</translation>
    </message>
    <message>
        <location filename="../codec.py" line="477"/>
        <source>转大写</source>
        <translation>Uppercase</translation>
    </message>
    <message>
        <location filename="../codec.py" line="477"/>
        <source>Unicode 大写（中文不受影响）</source>
        <translation>Unicode uppercase (Chinese unaffected)</translation>
    </message>
    <message>
        <location filename="../codec.py" line="478"/>
        <source>转小写</source>
        <translation>Lowercase</translation>
    </message>
    <message>
        <location filename="../codec.py" line="478"/>
        <source>Unicode 小写（中文不受影响）</source>
        <translation>Unicode lowercase (Chinese unaffected)</translation>
    </message>
    <message>
        <location filename="../codec.py" line="479"/>
        <source>MD5</source>
        <translation>MD5</translation>
    </message>
    <message>
        <location filename="../codec.py" line="479"/>
        <source>32 位十六进制（仅用于校验，勿当密码算法）</source>
        <translation>32 hex digits (for checksums only, not a password algorithm)</translation>
    </message>
    <message>
        <location filename="../codec.py" line="480"/>
        <source>SHA-1</source>
        <translation>SHA-1</translation>
    </message>
    <message>
        <location filename="../codec.py" line="480"/>
        <source>40 位十六进制（仅用于校验）</source>
        <translation>40 hex digits (for checksums only)</translation>
    </message>
    <message>
        <location filename="../codec.py" line="481"/>
        <source>SHA-256</source>
        <translation>SHA-256</translation>
    </message>
    <message>
        <location filename="../codec.py" line="481"/>
        <source>64 位十六进制（仅用于校验）</source>
        <translation>64 hex digits (for checksums only)</translation>
    </message>
    <message>
        <location filename="../codec.py" line="554"/>
        <source>未知转换：{0}</source>
        <extracomment>反向映射：可逆的转换互相指向对方（供 UI 的「反向」按钮用）</extracomment>
        <translation>Unknown transform: {0}</translation>
    </message>
</context>
<context>
    <name>CodecPanel</name>
    <message>
        <location filename="../ui/codec_panel.py" line="78"/>
        <source>常用:</source>
        <translation>Common:</translation>
    </message>
    <message>
        <location filename="../ui/codec_panel.py" line="89"/>
        <source>转换:</source>
        <translation>Transform:</translation>
    </message>
    <message>
        <location filename="../ui/codec_panel.py" line="108"/>
        <source>反向 ⇄</source>
        <translation>Reverse ⇄</translation>
    </message>
    <message>
        <location filename="../ui/codec_panel.py" line="109"/>
        <source>切到反向转换，并把结果填回输入（如 编码 → 解码）</source>
        <translation>Switch to the reverse transform and put the result back into the input (e.g. encode → decode)</translation>
    </message>
    <message>
        <location filename="../ui/codec_panel.py" line="119"/>
        <source>输入</source>
        <translation>Input</translation>
    </message>
    <message>
        <location filename="../ui/codec_panel.py" line="123"/>
        <source>把要转换的内容贴在这里…</source>
        <translation>Paste the content to convert here…</translation>
    </message>
    <message>
        <location filename="../ui/codec_panel.py" line="132"/>
        <source>结果</source>
        <translation>Result</translation>
    </message>
    <message>
        <location filename="../ui/codec_panel.py" line="155"/>
        <source>立即转换</source>
        <translation>Convert now</translation>
    </message>
    <message>
        <location filename="../ui/codec_panel.py" line="159"/>
        <source>结果填回输入 ↑</source>
        <translation>Result → input ↑</translation>
    </message>
    <message>
        <location filename="../ui/codec_panel.py" line="160"/>
        <source>把结果放回输入框，便于连续做多次转换</source>
        <translation>Puts the result back into the input box for chaining multiple conversions</translation>
    </message>
    <message>
        <location filename="../ui/codec_panel.py" line="164"/>
        <source>复制结果</source>
        <translation>Copy result</translation>
    </message>
    <message>
        <location filename="../ui/codec_panel.py" line="168"/>
        <source>清空</source>
        <translation>Clear</translation>
    </message>
    <message>
        <location filename="../ui/codec_panel.py" line="224"/>
        <source>已执行「{0}」</source>
        <translation>Ran &quot;{0}&quot;</translation>
    </message>
    <message>
        <location filename="../ui/codec_panel.py" line="231"/>
        <source>结果为空，无可复制内容</source>
        <translation>Result is empty; nothing to copy</translation>
    </message>
    <message>
        <location filename="../ui/codec_panel.py" line="235"/>
        <source>已复制 {0} 字符到剪贴板</source>
        <translation>Copied {0} characters to the clipboard</translation>
    </message>
    <message>
        <location filename="../ui/codec_panel.py" line="246"/>
        <source>内容超过 {0}KB，已暂停自动转换——点「立即转换」执行</source>
        <translation>Content exceeds {0}KB; auto-convert paused — click &quot;Convert now&quot; to run</translation>
    </message>
    <message>
        <location filename="../ui/codec_panel.py" line="261"/>
        <source>「{0}」没有反向转换（哈希不可逆）</source>
        <translation>&quot;{0}&quot; has no reverse transform (hashes are irreversible)</translation>
    </message>
    <message>
        <location filename="../ui/codec_panel.py" line="275"/>
        <source>结果为空</source>
        <translation>Result is empty</translation>
    </message>
    <message>
        <location filename="../ui/codec_panel.py" line="312"/>
        <source>0 字符</source>
        <translation>0 chars</translation>
    </message>
    <message>
        <location filename="../ui/codec_panel.py" line="313"/>
        <source>{0} 字符 / {1} 字节</source>
        <translation>{0} chars / {1} bytes</translation>
    </message>
</context>
<context>
    <name>CompareDialog</name>
    <message>
        <location filename="../ui/compare_dialog.py" line="116"/>
        <source>重放对比</source>
        <extracomment>报告区最大行数：diff 可能几千行，全渲染会卡</extracomment>
        <translation>Replay comparison</translation>
    </message>
    <message>
        <location filename="../ui/compare_dialog.py" line="142"/>
        <source>原响应</source>
        <translation>Original response</translation>
    </message>
    <message>
        <location filename="../ui/compare_dialog.py" line="142"/>
        <source>新响应</source>
        <translation>New response</translation>
    </message>
    <message>
        <location filename="../ui/compare_dialog.py" line="153"/>
        <source>&lt;b&gt;差异报告&lt;/b&gt;</source>
        <translation>&lt;b&gt;Diff report&lt;/b&gt;</translation>
    </message>
    <message>
        <location filename="../ui/compare_dialog.py" line="165"/>
        <source>复制差异</source>
        <translation>Copy diff</translation>
    </message>
    <message>
        <location filename="../ui/compare_dialog.py" line="167"/>
        <source>关闭</source>
        <translation>Close</translation>
    </message>
    <message>
        <location filename="../ui/compare_dialog.py" line="191"/>
        <source>（无差异）</source>
        <translation>(no differences)</translation>
    </message>
    <message>
        <location filename="../ui/compare_dialog.py" line="197"/>
        <source>无响应（{0}）</source>
        <translation>No response ({0})</translation>
    </message>
    <message>
        <location filename="../ui/compare_dialog.py" line="198"/>
        <source>未知原因</source>
        <translation>unknown reason</translation>
    </message>
    <message>
        <location filename="../ui/compare_dialog.py" line="200"/>
        <source>无响应</source>
        <translation>No response</translation>
    </message>
    <message>
        <location filename="../ui/compare_dialog.py" line="205"/>
        <source>{0}
原响应：{1}&#x3000;→&#x3000;新响应：{2}&#x3000;·&#x3000;{3}</source>
        <translation>{0}
Original: {1}&#x3000;→&#x3000;New: {2}&#x3000;·&#x3000;{3}</translation>
    </message>
    <message>
        <location filename="../ui/compare_dialog.py" line="224"/>
        <source>{0} {1}（无响应）</source>
        <translation>{0} {1} (no response)</translation>
    </message>
    <message>
        <location filename="../ui/compare_dialog.py" line="249"/>
        <source>body 一致，headers 有差异</source>
        <translation>Bodies match; headers differ</translation>
    </message>
    <message>
        <location filename="../ui/compare_dialog.py" line="250"/>
        <source>Headers 差异：
</source>
        <translation>Header differences:
</translation>
    </message>
    <message>
        <location filename="../ui/compare_dialog.py" line="252"/>
        <source>完全一致</source>
        <translation>Identical</translation>
    </message>
    <message>
        <location filename="../ui/compare_dialog.py" line="252"/>
        <source>两个响应完全一致（body 与 headers 均相同）</source>
        <translation>The two responses are identical (both body and headers match)</translation>
    </message>
    <message>
        <location filename="../ui/compare_dialog.py" line="270"/>
        <source>

Headers 差异：
</source>
        <translation>

Header differences:
</translation>
    </message>
    <message>
        <location filename="../ui/compare_dialog.py" line="272"/>
        <source>{0} 处差异（JSON 键级）</source>
        <translation>{0} differences (JSON key level)</translation>
    </message>
    <message>
        <location filename="../ui/compare_dialog.py" line="274"/>
        <source>差异过多（JSON 键级，已截断）</source>
        <translation>Too many differences (JSON key level, truncated)</translation>
    </message>
    <message>
        <location filename="../ui/compare_dialog.py" line="282"/>
        <source>二进制内容不同</source>
        <translation>Binary content differs</translation>
    </message>
    <message>
        <location filename="../ui/compare_dialog.py" line="282"/>
        <source>响应为二进制内容且无法按文本解码，仅确认两者不同。</source>
        <translation>The response is binary and cannot be decoded as text; only confirmed that the two differ.</translation>
    </message>
    <message>
        <location filename="../ui/compare_dialog.py" line="284"/>
        <source>文本有差异</source>
        <translation>Text differs</translation>
    </message>
    <message>
        <location filename="../ui/compare_dialog.py" line="284"/>
        <source>解码后一致（原始字节不同，可能是换行/编码差异）</source>
        <translation>Identical after decoding (raw bytes differ, possibly a newline/encoding difference)</translation>
    </message>
    <message>
        <location filename="../ui/compare_dialog.py" line="285"/>
        <source>（无行级差异）</source>
        <translation>(no line-level differences)</translation>
    </message>
</context>
<context>
    <name>DetailPanel</name>
    <message>
        <location filename="../ui/detail_panel.py" line="131"/>
        <source>自动 = 按 content-type 挑最合适的视图（JSON / 表单 / 图片 / 原文 / 十六进制）。
手动切换后会保持，换会话也不回弹。
解析失败会退回原文并说明原因，不会丢内容。</source>
        <extracomment>表单表格里命中的单元格底色（与 body 文本高亮同色系，视觉上是一回事） WebSocket 消息表最多渲染的行数（再多的只记在内存里，别把表格撑爆）</extracomment>
        <translation>Auto = picks the best view by content-type (JSON / form / image / raw / hex).
A manual choice sticks and does not reset when switching sessions.
On parse failure it falls back to raw text with an explanation; no content is lost.</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="155"/>
        <source>适应窗口</source>
        <extracomment>图片缩放档位：适应窗口 + 固定比例</extracomment>
        <translation>Fit window</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="156"/>
        <source>25%</source>
        <translation>25%</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="157"/>
        <source>50%</source>
        <translation>50%</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="158"/>
        <source>100%</source>
        <translation>100%</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="159"/>
        <source>200%</source>
        <translation>200%</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="171"/>
        <source>图片</source>
        <translation>Image</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="1347"/>
        <source>（空）</source>
        <translation>(empty)</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="1761"/>
        <source>请求</source>
        <translation>Request</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="1762"/>
        <source>响应</source>
        <translation>Response</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="1765"/>
        <source>耗时</source>
        <translation>Timings</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="1838"/>
        <source>尚未收到响应…</source>
        <translation>No response yet…</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="146"/>
        <source>查看</source>
        <extracomment>MessagePane 内部 tab 文案（对齐 Fiddler 的 inspector：查看 / Raw）</extracomment>
        <translation>Inspect</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="147"/>
        <source>原始</source>
        <translation>Raw</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="148"/>
        <source>完整 HTTP 报文：请求/状态行 + 全部头 + body（与 Fiddler Raw 一致）</source>
        <translation>Full HTTP message: request/status line + all headers + body (matches Fiddler Raw)</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="138"/>
        <source>JSON 树视图：点箭头展开/收起，右键可复制值、键、路径或整个节点的 JSON。
树是**解析后**的视图：重复键只保留最后一个，浮点形态可能与原文不同——
要一字不差地校对请用「原文」视图。</source>
        <translation>JSON tree: click the arrow to expand/collapse; right-click to copy the value, key, path or the whole node as JSON.
The tree is built from the **parsed** JSON: duplicate keys keep only the last one, and float formatting may differ from the raw bytes —
use the Raw view when you need byte-exact content.</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="372"/>
        <source>层级</source>
        <translation>Level</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="376"/>
        <source>按层级展开树（避免大数组一次性全展开卡顿）</source>
        <translation>Expand the tree by level (avoids freezing on large arrays when expanding all at once)</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="380"/>
        <source>全部展开</source>
        <translation>Expand all</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="381"/>
        <source>展开到第 3 层</source>
        <translation>Expand to level 3</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="382"/>
        <source>展开到第 2 层</source>
        <translation>Expand to level 2</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="383"/>
        <source>展开到第 1 层</source>
        <translation>Expand to level 1</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="384"/>
        <source>全部收起</source>
        <translation>Collapse all</translation>
    </message>
</context>
<context>
    <name>FeedbackDialog</name>
    <message>
        <location filename="../ui/feedback_dialog.py" line="30"/>
        <location filename="../ui/feedback_dialog.py" line="155"/>
        <source>意见反馈</source>
        <translation>Feedback</translation>
    </message>
    <message>
        <location filename="../ui/feedback_dialog.py" line="45"/>
        <source>遇到问题或有功能建议？描述越具体越容易定位：</source>
        <translation>Hit a problem or have a feature idea? The more specific your description, the easier it is to track down:</translation>
    </message>
    <message>
        <location filename="../ui/feedback_dialog.py" line="47"/>
        <source>你的昵称（必填，≤64 字符；会显示在 issue 标题上）</source>
        <translation>Your nickname (required, ≤64 chars; shown in the issue title)</translation>
    </message>
    <message>
        <location filename="../ui/feedback_dialog.py" line="52"/>
        <source>一句话概括（必填），如：导入 Fiddler 规则后中文乱码</source>
        <translation>One-line summary (required), e.g. Garbled Chinese after importing Fiddler rules</translation>
    </message>
    <message>
        <location filename="../ui/feedback_dialog.py" line="57"/>
        <source>详细描述（必填）：做了什么操作、期望的结果、实际的结果…</source>
        <translation>Details (required): what you did, the expected result, the actual result…</translation>
    </message>
    <message>
        <location filename="../ui/feedback_dialog.py" line="62"/>
        <source>提交后会自动附带 App 版本 / 系统信息，并以公开 issue 形式创建到 GitHub（{0}）。昵称会显示在 issue 标题上，便于我们回复与追溯。</source>
        <translation>Submitting automatically attaches the app version / system info and creates a public issue on GitHub ({0}). Your nickname appears in the issue title so we can reply and follow up.</translation>
    </message>
    <message>
        <location filename="../ui/feedback_dialog.py" line="75"/>
        <source>提交</source>
        <translation>Submit</translation>
    </message>
    <message>
        <location filename="../ui/feedback_dialog.py" line="78"/>
        <source>取消</source>
        <translation>Cancel</translation>
    </message>
    <message>
        <location filename="../ui/feedback_dialog.py" line="94"/>
        <source>开发者尚未配置反馈通道，请到 GitHub 手动提 issue：{0}</source>
        <translation>The feedback channel is not configured yet. Please file an issue on GitHub manually: {0}</translation>
    </message>
    <message>
        <location filename="../ui/feedback_dialog.py" line="104"/>
        <source>请填写昵称（必填，会显示在 issue 标题上）。</source>
        <translation>Please enter a nickname (required; shown in the issue title).</translation>
    </message>
    <message>
        <location filename="../ui/feedback_dialog.py" line="107"/>
        <source>标题和内容都需要填写。</source>
        <translation>Both the title and the body are required.</translation>
    </message>
    <message>
        <location filename="../ui/feedback_dialog.py" line="112"/>
        <source>正在提交…</source>
        <translation>Submitting…</translation>
    </message>
</context>
<context>
    <name>FilterBar</name>
    <message>
        <location filename="../ui/traffic_table.py" line="53"/>
        <source>域名:</source>
        <translation>Domain:</translation>
    </message>
    <message>
        <location filename="../ui/traffic_table.py" line="55"/>
        <source>隐藏(黑名单)</source>
        <translation>Hide (blocklist)</translation>
    </message>
    <message>
        <location filename="../ui/traffic_table.py" line="56"/>
        <source>只显示(白名单)</source>
        <translation>Show only (allowlist)</translation>
    </message>
    <message>
        <location filename="../ui/traffic_table.py" line="57"/>
        <source>黑名单：隐藏含关键词的域名；白名单：只显示含关键词的域名</source>
        <translation>Blocklist: hide domains containing the keywords; Allowlist: show only domains containing the keywords</translation>
    </message>
    <message>
        <location filename="../ui/traffic_table.py" line="61"/>
        <source>关键词，逗号分隔；留空 = 不过滤</source>
        <translation>Keywords, comma-separated; empty = no filtering</translation>
    </message>
    <message>
        <location filename="../ui/traffic_table.py" line="65"/>
        <source>隐藏 CONNECT</source>
        <translation>Hide CONNECT</translation>
    </message>
    <message>
        <location filename="../ui/traffic_table.py" line="66"/>
        <source>隐藏 Image</source>
        <translation>Hide Image</translation>
    </message>
</context>
<context>
    <name>FlowDetailDialog</name>
    <message>
        <location filename="../ui/flow_detail_dialog.py" line="38"/>
        <source>请求详情</source>
        <translation>Request details</translation>
    </message>
    <message>
        <location filename="../ui/flow_detail_dialog.py" line="55"/>
        <source>关闭</source>
        <translation>Close</translation>
    </message>
    <message>
        <location filename="../ui/flow_detail_dialog.py" line="96"/>
        <source>尚未收到响应…</source>
        <translation>No response yet…</translation>
    </message>
</context>
<context>
    <name>FlowStore</name>
    <message>
        <location filename="../ui/flow_store.py" line="39"/>
        <source>方法</source>
        <extracomment>列头的翻译文案。**必须懒执行**：翻译器是在 app/main.py 里 QApplication 创建之后才装载的，若在 import 时求值会永远拿到中文原文。 字面量写死在这里（而不是 self.tr(变量)）是为了让 pyside6-lupdate 能抽到。</extracomment>
        <translation>Method</translation>
    </message>
    <message>
        <location filename="../ui/flow_store.py" line="41"/>
        <source>服务器 IP</source>
        <translation>Server IP</translation>
    </message>
    <message>
        <location filename="../ui/flow_store.py" line="42"/>
        <source>路径</source>
        <translation>Path</translation>
    </message>
    <message>
        <location filename="../ui/flow_store.py" line="43"/>
        <source>状态</source>
        <translation>Status</translation>
    </message>
    <message>
        <location filename="../ui/flow_store.py" line="44"/>
        <source>请求体</source>
        <translation>Request body</translation>
    </message>
    <message>
        <location filename="../ui/flow_store.py" line="45"/>
        <source>响应</source>
        <translation>Response</translation>
    </message>
    <message>
        <location filename="../ui/flow_store.py" line="46"/>
        <source>耗时(ms)</source>
        <translation>Duration (ms)</translation>
    </message>
    <message>
        <location filename="../ui/flow_store.py" line="47"/>
        <source>标记</source>
        <translation>Mark</translation>
    </message>
    <message>
        <location filename="../ui/flow_store.py" line="196"/>
        <source>弱网{0}ms</source>
        <extracomment>排序专用 role。DisplayRole 里「大小」是 `4.2 KB`、「耗时」是格式化过的字符串， 直接按显示文本排会出现 `1.3 MB` 排在 `812 B` 前面的笑话——所以排序一律走这个 role 取**原始数值**（见 FlowFilterProxyModel.lessThan）。</extracomment>
        <translation>Throttle {0}ms</translation>
    </message>
    <message>
        <location filename="../ui/flow_store.py" line="270"/>
        <source>
服务器 IP: {0}</source>
        <translation>
Server IP: {0}</translation>
    </message>
    <message>
        <location filename="../ui/flow_store.py" line="272"/>
        <source>
备注: {0}</source>
        <translation>
Comment: {0}</translation>
    </message>
    <message>
        <location filename="../ui/flow_store.py" line="276"/>
        <source>
弱网延迟: {0} ms</source>
        <translation>
Throttle delay: {0} ms</translation>
    </message>
    <message>
        <location filename="../ui/flow_store.py" line="279"/>
        <source>
WebSocket：{0} 条消息</source>
        <translation>
WebSocket: {0} messages</translation>
    </message>
    <message>
        <location filename="../ui/flow_store.py" line="280"/>
        <source>（已关闭）</source>
        <translation>(closed)</translation>
    </message>
    <message>
        <location filename="../ui/flow_store.py" line="280"/>
        <source>（连接中）</source>
        <translation>(connecting)</translation>
    </message>
</context>
<context>
    <name>ImageView</name>
    <message>
        <location filename="../ui/detail_panel.py" line="208"/>
        <source>SVG 渲染不可用（缺少 QtSvg）</source>
        <translation>SVG rendering unavailable (QtSvg missing)</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="211"/>
        <source>SVG 内容无法解析</source>
        <translation>SVG content cannot be parsed</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="224"/>
        <source>无法识别为图片（内容可能已损坏或非图片格式）</source>
        <translation>Not recognized as an image (the content may be corrupted or not an image format)</translation>
    </message>
</context>
<context>
    <name>ImportPreviewDialog</name>
    <message>
        <location filename="../ui/import_dialog.py" line="85"/>
        <source>导入 Fiddler 规则 — {0}</source>
        <translation>Import Fiddler rules — {0}</translation>
    </message>
    <message>
        <location filename="../ui/import_dialog.py" line="94"/>
        <source>识别到 &lt;b&gt;{0}&lt;/b&gt; 条可导入规则，&lt;b&gt;{1}&lt;/b&gt; 条跳过。勾选要导入的规则：</source>
        <translation>Found &lt;b&gt;{0}&lt;/b&gt; importable rules, &lt;b&gt;{1}&lt;/b&gt; skipped. Check the rules to import:</translation>
    </message>
    <message>
        <location filename="../ui/import_dialog.py" line="102"/>
        <source>全选</source>
        <translation>Select all</translation>
    </message>
    <message>
        <location filename="../ui/import_dialog.py" line="103"/>
        <source>全不选</source>
        <translation>Select none</translation>
    </message>
    <message>
        <location filename="../ui/import_dialog.py" line="112"/>
        <source>名称</source>
        <translation>Name</translation>
    </message>
    <message>
        <location filename="../ui/import_dialog.py" line="112"/>
        <source>匹配</source>
        <translation>Match</translation>
    </message>
    <message>
        <location filename="../ui/import_dialog.py" line="112"/>
        <source>动作</source>
        <translation>Action</translation>
    </message>
    <message>
        <location filename="../ui/import_dialog.py" line="112"/>
        <source>来源</source>
        <translation>Source</translation>
    </message>
    <message>
        <location filename="../ui/import_dialog.py" line="149"/>
        <source>&lt;br&gt;• ……等共 {0} 条</source>
        <translation>&lt;br&gt;• … and {0} more</translation>
    </message>
    <message>
        <location filename="../ui/import_dialog.py" line="164"/>
        <source>跳过的规则及原因（{0} 条）</source>
        <translation>Skipped rules and reasons ({0})</translation>
    </message>
    <message>
        <location filename="../ui/import_dialog.py" line="167"/>
        <source>点击收起 / 展开跳过的规则及原因</source>
        <translation>Click to collapse / expand skipped rules and reasons</translation>
    </message>
    <message>
        <location filename="../ui/import_dialog.py" line="179"/>
        <source>导入所选</source>
        <translation>Import selected</translation>
    </message>
</context>
<context>
    <name>JsonComparePanel</name>
    <message>
        <location filename="../ui/json_compare_panel.py" line="39"/>
        <source>新增</source>
        <extracomment>差异表最多显示多少行（diff 本身仍会算完，只是不全部渲染）</extracomment>
        <translation>Added</translation>
    </message>
    <message>
        <location filename="../ui/json_compare_panel.py" line="40"/>
        <source>删除</source>
        <translation>Removed</translation>
    </message>
    <message>
        <location filename="../ui/json_compare_panel.py" line="41"/>
        <source>修改</source>
        <translation>Changed</translation>
    </message>
    <message>
        <location filename="../ui/json_compare_panel.py" line="84"/>
        <source>交换左右</source>
        <extracomment>类型列文字色走语义 token（新增=ok / 删除=error / 修改=warn），随主题换色</extracomment>
        <translation>Swap left/right</translation>
    </message>
    <message>
        <location filename="../ui/json_compare_panel.py" line="85"/>
        <source>把两边内容对调（比对结果方向随之反转）</source>
        <translation>Swaps the two sides (the diff direction is reversed accordingly)</translation>
    </message>
    <message>
        <location filename="../ui/json_compare_panel.py" line="91"/>
        <source>复制差异</source>
        <translation>Copy diff</translation>
    </message>
    <message>
        <location filename="../ui/json_compare_panel.py" line="96"/>
        <source>清空</source>
        <translation>Clear</translation>
    </message>
    <message>
        <location filename="../ui/json_compare_panel.py" line="103"/>
        <location filename="../ui/json_compare_panel.py" line="212"/>
        <source>原 JSON</source>
        <translation>Original JSON</translation>
    </message>
    <message>
        <location filename="../ui/json_compare_panel.py" line="103"/>
        <location filename="../ui/json_compare_panel.py" line="212"/>
        <source>新 JSON</source>
        <translation>New JSON</translation>
    </message>
    <message>
        <location filename="../ui/json_compare_panel.py" line="109"/>
        <source>把 JSON 贴进来…</source>
        <translation>Paste JSON here…</translation>
    </message>
    <message>
        <location filename="../ui/json_compare_panel.py" line="117"/>
        <source>差异</source>
        <translation>Diff</translation>
    </message>
    <message>
        <location filename="../ui/json_compare_panel.py" line="122"/>
        <source>路径</source>
        <translation>Path</translation>
    </message>
    <message>
        <location filename="../ui/json_compare_panel.py" line="122"/>
        <source>类型</source>
        <translation>Kind</translation>
    </message>
    <message>
        <location filename="../ui/json_compare_panel.py" line="122"/>
        <source>旧值</source>
        <translation>Old value</translation>
    </message>
    <message>
        <location filename="../ui/json_compare_panel.py" line="122"/>
        <source>新值</source>
        <translation>New value</translation>
    </message>
    <message>
        <location filename="../ui/json_compare_panel.py" line="137"/>
        <location filename="../ui/json_compare_panel.py" line="188"/>
        <location filename="../ui/json_compare_panel.py" line="207"/>
        <source>两边都贴上 JSON 后自动比对</source>
        <translation>Comparison runs automatically once JSON is pasted on both sides</translation>
    </message>
    <message>
        <location filename="../ui/json_compare_panel.py" line="214"/>
        <source>「{0}」还是空的</source>
        <translation>&quot;{0}&quot; is still empty</translation>
    </message>
    <message>
        <location filename="../ui/json_compare_panel.py" line="219"/>
        <source>「{0}」不合法：{1}</source>
        <translation>&quot;{0}&quot; is invalid: {1}</translation>
    </message>
    <message>
        <location filename="../ui/json_compare_panel.py" line="227"/>
        <source>左 {0} 节点 · 右 {1} 节点</source>
        <translation>Left: {0} nodes · Right: {1} nodes</translation>
    </message>
    <message>
        <location filename="../ui/json_compare_panel.py" line="231"/>
        <source>两个 JSON 完全一致</source>
        <translation>The two JSON documents are identical</translation>
    </message>
    <message>
        <location filename="../ui/json_compare_panel.py" line="232"/>
        <source>{0} · 完全一致</source>
        <translation>{0} · identical</translation>
    </message>
    <message>
        <location filename="../ui/json_compare_panel.py" line="249"/>
        <source>（差异表仅显示前 {0} 条）</source>
        <translation>(diff table shows only the first {0} rows)</translation>
    </message>
    <message>
        <location filename="../ui/json_compare_panel.py" line="253"/>
        <source>（差异过多，结构化对比已提前停止）</source>
        <translation>(too many differences; structured comparison stopped early)</translation>
    </message>
    <message>
        <location filename="../ui/json_compare_panel.py" line="255"/>
        <source>{0} · 共 {1} 处差异{2}{3}</source>
        <translation>{0} · {1} differences in total{2}{3}</translation>
    </message>
</context>
<context>
    <name>JsonPanel</name>
    <message>
        <location filename="../ui/json_panel.py" line="65"/>
        <source>2 空格</source>
        <extracomment>树视图**已构建**节点总数上限（懒加载下按展开量计）：超过就暂停填充并提示 单个节点子项填充上限：展开一个 10 万元素的数组也不至于把列表铺满</extracomment>
        <translation>2 spaces</translation>
    </message>
    <message>
        <location filename="../ui/json_panel.py" line="66"/>
        <source>4 空格</source>
        <translation>4 spaces</translation>
    </message>
    <message>
        <location filename="../ui/json_panel.py" line="67"/>
        <source>Tab</source>
        <translation>Tab</translation>
    </message>
    <message>
        <location filename="../ui/json_panel.py" line="74"/>
        <source>常用写法：
  $.data.list[0].name        取字段
  $.data.list[-1]            最后一个
  $.data.list[0:5]           切片
  $.data.list[*].id          所有元素的 id
  $..token                   所有层级里叫 token 的字段
  $.list[?(@.price &gt; 10)]    过滤（&amp;&amp; || 组合，=~ 正则）
  $[&apos;a&apos;,&apos;b&apos;]、$[0,1]         一次取多个
</source>
        <translation>Common patterns:
  $.data.list[0].name        get a field
  $.data.list[-1]            last element
  $.data.list[0:5]           slice
  $.data.list[*].id          id of every element
  $..token                   every field named token at any depth
  $.list[?(@.price &gt; 10)]    filter (&amp;&amp; || combos, =~ regex)
  $[&apos;a&apos;,&apos;b&apos;], $[0,1]         grab several at once
</translation>
    </message>
    <message>
        <location filename="../ui/json_panel.py" line="128"/>
        <source>格式化</source>
        <translation>Format</translation>
    </message>
    <message>
        <location filename="../ui/json_panel.py" line="132"/>
        <source>压缩</source>
        <translation>Minify</translation>
    </message>
    <message>
        <location filename="../ui/json_panel.py" line="136"/>
        <source>校验</source>
        <translation>Validate</translation>
    </message>
    <message>
        <location filename="../ui/json_panel.py" line="137"/>
        <source>只判断合法性与规模，不渲染内容（超大 JSON 用这个）</source>
        <translation>Only checks validity and size without rendering (use this for very large JSON)</translation>
    </message>
    <message>
        <location filename="../ui/json_panel.py" line="142"/>
        <source>缩进:</source>
        <translation>Indent:</translation>
    </message>
    <message>
        <location filename="../ui/json_panel.py" line="151"/>
        <source>视图:</source>
        <translation>View:</translation>
    </message>
    <message>
        <location filename="../ui/json_panel.py" line="153"/>
        <source>格式化文本</source>
        <translation>Formatted text</translation>
    </message>
    <message>
        <location filename="../ui/json_panel.py" line="154"/>
        <source>树形</source>
        <translation>Tree</translation>
    </message>
    <message>
        <location filename="../ui/json_panel.py" line="155"/>
        <source>JSONPath 结果</source>
        <translation>JSONPath results</translation>
    </message>
    <message>
        <location filename="../ui/json_panel.py" line="159"/>
        <source>展开全部</source>
        <translation>Expand all</translation>
    </message>
    <message>
        <location filename="../ui/json_panel.py" line="162"/>
        <source>折叠全部</source>
        <translation>Collapse all</translation>
    </message>
    <message>
        <location filename="../ui/json_panel.py" line="166"/>
        <source>换行</source>
        <translation>Wrap</translation>
    </message>
    <message>
        <location filename="../ui/json_panel.py" line="169"/>
        <source>单行超过 {0}KB 时会自动临时关闭（换行对超长单行是超线性开销）</source>
        <translation>Temporarily disabled when a single line exceeds {0}KB (wrapping a very long line is super-linear)</translation>
    </message>
    <message>
        <location filename="../ui/json_panel.py" line="176"/>
        <location filename="../ui/json_panel.py" line="268"/>
        <source>复制结果</source>
        <translation>Copy result</translation>
    </message>
    <message>
        <location filename="../ui/json_panel.py" line="179"/>
        <source>清空</source>
        <translation>Clear</translation>
    </message>
    <message>
        <location filename="../ui/json_panel.py" line="187"/>
        <source>输入</source>
        <translation>Input</translation>
    </message>
    <message>
        <location filename="../ui/json_panel.py" line="191"/>
        <source>把 JSON 贴进来，或用下面的 JSONPath 提取…</source>
        <translation>Paste JSON here, or extract with JSONPath below…</translation>
    </message>
    <message>
        <location filename="../ui/json_panel.py" line="200"/>
        <source>结果</source>
        <translation>Result</translation>
    </message>
    <message>
        <location filename="../ui/json_panel.py" line="212"/>
        <source>名称</source>
        <translation>Name</translation>
    </message>
    <message>
        <location filename="../ui/json_panel.py" line="212"/>
        <location filename="../ui/json_panel.py" line="226"/>
        <source>值</source>
        <translation>Value</translation>
    </message>
    <message>
        <location filename="../ui/json_panel.py" line="212"/>
        <source>类型</source>
        <translation>Type</translation>
    </message>
    <message>
        <location filename="../ui/json_panel.py" line="226"/>
        <source>路径</source>
        <translation>Path</translation>
    </message>
    <message>
        <location filename="../ui/json_panel.py" line="262"/>
        <source>提取</source>
        <translation>Extract</translation>
    </message>
    <message>
        <location filename="../ui/json_panel.py" line="283"/>
        <source>跳到出错位置</source>
        <translation>Jump to error</translation>
    </message>
    <message>
        <location filename="../ui/json_panel.py" line="285"/>
        <source>把光标移到出错的行列</source>
        <translation>Moves the cursor to the offending line and column</translation>
    </message>
    <message>
        <location filename="../ui/json_panel.py" line="325"/>
        <source>解析失败</source>
        <translation>Parse failed</translation>
    </message>
    <message>
        <location filename="../ui/json_panel.py" line="339"/>
        <source>✓ 合法 JSON · {0} 个节点 · 最大深度 {1}</source>
        <translation>✓ Valid JSON · {0} nodes · max depth {1}</translation>
    </message>
    <message>
        <location filename="../ui/json_panel.py" line="357"/>
        <source>已压缩为单行（复制方便，看结构请切「格式化」）</source>
        <translation>Minified to one line (easy to copy; switch to &quot;Format&quot; to inspect the structure)</translation>
    </message>
    <message>
        <location filename="../ui/json_panel.py" line="364"/>
        <source>结果过长已截断</source>
        <translation>Result too long; truncated</translation>
    </message>
    <message>
        <location filename="../ui/json_panel.py" line="370"/>
        <source>共 {0} 个节点</source>
        <translation>{0} nodes in total</translation>
    </message>
    <message>
        <location filename="../ui/json_panel.py" line="371"/>
        <source>最大深度 {0}</source>
        <translation>Max depth {0}</translation>
    </message>
    <message>
        <location filename="../ui/json_panel.py" line="381"/>
        <source>请输入 JSONPath 表达式（如 $.data.list[0]）</source>
        <translation>Enter a JSONPath expression (e.g. $.data.list[0])</translation>
    </message>
    <message>
        <location filename="../ui/json_panel.py" line="388"/>
        <source>输入不是合法 JSON，先修好上面的错误再提取</source>
        <translation>The input is not valid JSON; fix the error above before extracting</translation>
    </message>
    <message>
        <location filename="../ui/json_panel.py" line="399"/>
        <source>没有匹配到任何内容</source>
        <translation>No matches found</translation>
    </message>
    <message>
        <location filename="../ui/json_panel.py" line="401"/>
        <source>共 {0} 处匹配</source>
        <translation>{0} matches</translation>
    </message>
    <message>
        <location filename="../ui/json_panel.py" line="409"/>
        <source>结果为空，无可复制内容</source>
        <translation>Result is empty; nothing to copy</translation>
    </message>
    <message>
        <location filename="../ui/json_panel.py" line="412"/>
        <source>已复制 {0} 字符到剪贴板</source>
        <translation>Copied {0} characters to the clipboard</translation>
    </message>
    <message>
        <location filename="../ui/json_panel.py" line="417"/>
        <source>没有可复制的提取结果</source>
        <translation>No extraction result to copy</translation>
    </message>
    <message>
        <location filename="../ui/json_panel.py" line="425"/>
        <source>已复制 {0} 个匹配值（JSON 数组）到剪贴板</source>
        <translation>Copied {0} matched values (as a JSON array) to the clipboard</translation>
    </message>
    <message>
        <location filename="../ui/json_panel.py" line="437"/>
        <source>内容超过 {0}KB，已暂停自动格式化——点「格式化」执行</source>
        <translation>Content exceeds {0}KB; auto-format paused — click &quot;Format&quot; to run</translation>
    </message>
    <message>
        <location filename="../ui/json_panel.py" line="473"/>
        <source>单行最长 {0}KB 超过 {1}KB，已临时关闭换行</source>
        <translation>Longest single line {0}KB exceeds {1}KB; wrapping temporarily disabled</translation>
    </message>
    <message>
        <location filename="../ui/json_panel.py" line="484"/>
        <source> · 单行最长</source>
        <translation> · longest line</translation>
    </message>
    <message>
        <location filename="../ui/json_panel.py" line="519"/>
        <location filename="../ui/json_panel.py" line="564"/>
        <source>{0} 项</source>
        <translation>{0} items</translation>
    </message>
    <message>
        <location filename="../ui/json_panel.py" line="554"/>
        <source>树节点超过 {0}，更深处未展开（用 JSONPath 缩小范围）</source>
        <translation>Tree nodes exceed {0}; deeper levels are not expanded (narrow the scope with JSONPath)</translation>
    </message>
    <message>
        <location filename="../ui/json_panel.py" line="575"/>
        <source>…（其余 {0} 项未显示）</source>
        <translation>… ({0} more items not shown)</translation>
    </message>
    <message>
        <location filename="../ui/json_panel.py" line="666"/>
        <source>0 字符</source>
        <translation>0 chars</translation>
    </message>
    <message>
        <location filename="../ui/json_panel.py" line="667"/>
        <source>{0} 字符 / {1} 字节</source>
        <translation>{0} chars / {1} bytes</translation>
    </message>
</context>
<context>
    <name>JsonPath</name>
    <message>
        <location filename="../jsonpath.py" line="50"/>
        <source>JSONPath 语法错误（第 {0} 个字符）：{1}
{2}
{3}</source>
        <extracomment>单次提取最多返回多少条（再多只统计不展示） 递归下降时最多遍历多少节点</extracomment>
        <translation>JSONPath syntax error (char {0}): {1}
{2}
{3}</translation>
    </message>
    <message>
        <location filename="../jsonpath.py" line="150"/>
        <source>必须以 $ 开头（如 $.data.list[0]）</source>
        <extracomment>支持的聚合函数</extracomment>
        <translation>Must start with $ (e.g. $.data.list[0])</translation>
    </message>
    <message>
        <location filename="../jsonpath.py" line="152"/>
        <source>最外层请用 $ 而不是 @（@ 只在过滤器里表示当前元素）</source>
        <translation>Use $ rather than @ at the top level (@ only means the current element inside filters)</translation>
    </message>
    <message>
        <location filename="../jsonpath.py" line="165"/>
        <source>无法识别的 {0}：字段前要有 . 或 [</source>
        <translation>Unrecognized {0}: a field must be preceded by . or [</translation>
    </message>
    <message>
        <location filename="../jsonpath.py" line="179"/>
        <source>.. 后面要跟字段名或 *（如 $..id）</source>
        <translation>.. must be followed by a field name or * (e.g. $..id)</translation>
    </message>
    <message>
        <location filename="../jsonpath.py" line="187"/>
        <source>. 后面要跟字段名或 *（如 $.data）</source>
        <translation>. must be followed by a field name or * (e.g. $.data)</translation>
    </message>
    <message>
        <location filename="../jsonpath.py" line="190"/>
        <source>空的字段访问</source>
        <translation>Empty field access</translation>
    </message>
    <message>
        <location filename="../jsonpath.py" line="210"/>
        <source>[] 里是空的</source>
        <translation>[] is empty</translation>
    </message>
    <message>
        <location filename="../jsonpath.py" line="241"/>
        <source>缺少配对的 ]</source>
        <translation>Missing matching ]</translation>
    </message>
    <message>
        <location filename="../jsonpath.py" line="276"/>
        <source>无法识别的 [{0}]</source>
        <translation>Unrecognized [{0}]</translation>
    </message>
    <message>
        <location filename="../jsonpath.py" line="281"/>
        <source>暂不支持带步长的切片（如 [::2]）</source>
        <translation>Slices with a step (e.g. [::2]) are not supported yet</translation>
    </message>
    <message>
        <location filename="../jsonpath.py" line="287"/>
        <source>切片的 {0} 不是整数</source>
        <translation>Slice bound {0} is not an integer</translation>
    </message>
    <message>
        <location filename="../jsonpath.py" line="296"/>
        <source>? 后面要跟 ( 表达式 )，如 $[?(@.price &gt; 10)]</source>
        <translation>? must be followed by ( expression ), e.g. $[?(@.price &gt; 10)]</translation>
    </message>
    <message>
        <location filename="../jsonpath.py" line="319"/>
        <source>过滤器缺少配对的 )</source>
        <translation>Filter is missing a matching )</translation>
    </message>
    <message>
        <location filename="../jsonpath.py" line="324"/>
        <source>过滤器后面要跟 ]</source>
        <translation>A filter must be followed by ]</translation>
    </message>
    <message>
        <location filename="../jsonpath.py" line="327"/>
        <source>过滤器是空的，如 $[?(@.price &gt; 10)]</source>
        <translation>Filter is empty, e.g. $[?(@.price &gt; 10)]</translation>
    </message>
    <message>
        <location filename="../jsonpath.py" line="417"/>
        <source>过滤器左边要以 @ 开头：{0}</source>
        <translation>The left side of a filter must start with @: {0}</translation>
    </message>
    <message>
        <location filename="../jsonpath.py" line="434"/>
        <source>过滤器里的字段名不合法：{0}</source>
        <translation>Invalid field name in filter: {0}</translation>
    </message>
    <message>
        <location filename="../jsonpath.py" line="441"/>
        <source>过滤器里的 [ 缺少配对的 ]</source>
        <translation>Missing matching ] for [ in filter</translation>
    </message>
    <message>
        <location filename="../jsonpath.py" line="449"/>
        <source>过滤器里无法解析：{0}</source>
        <translation>Cannot parse in filter: {0}</translation>
    </message>
    <message>
        <location filename="../jsonpath.py" line="452"/>
        <source>过滤器里 @ 后面没有字段，如 @.price</source>
        <translation>No field after @ in filter, e.g. @.price</translation>
    </message>
    <message>
        <location filename="../jsonpath.py" line="558"/>
        <source>{0}() 只能比较数字（遇到 {1}：{2}）</source>
        <translation>{0}() can only compare numbers (found {1}: {2})</translation>
    </message>
    <message>
        <location filename="../jsonpath.py" line="564"/>
        <source>{0}() 没有可比较的数字（结果为空）</source>
        <translation>{0}() has no comparable numbers (empty result)</translation>
    </message>
    <message>
        <location filename="../jsonpath.py" line="625"/>
        <source>请输入 JSONPath 表达式（如 $.data.list[0]）</source>
        <translation>Enter a JSONPath expression (e.g. $.data.list[0])</translation>
    </message>
    <message>
        <location filename="../jsonpath.py" line="631"/>
        <source>表达式嵌套过深</source>
        <translation>Expression nesting too deep</translation>
    </message>
    <message>
        <location filename="../jsonpath.py" line="640"/>
        <source>数据嵌套过深，无法继续提取</source>
        <translation>Data nesting too deep; cannot continue extracting</translation>
    </message>
    <message>
        <location filename="../jsonpath.py" line="644"/>
        <source>（命中过多，仅显示前 {0} 条）</source>
        <translation>(too many hits; showing only the first {0})</translation>
    </message>
</context>
<context>
    <name>JsonTreeModel</name>
    <message>
        <location filename="../ui/json_tree.py" line="186"/>
        <source>键</source>
        <extracomment>第 1 列默认宽度。不用 Stretch——键列跟随内容会把整棵树挤变形；值列才拉伸。 搜索只保留这么多命中：再多既没有展示价值，展开祖先也会变慢 超过这么多命中就不逐个定位（只报告数量），避免 setExpanded 刷爆 自动展开的第 2 层子节点数上限（见 _default_expand） 持有取色用的控件引用——不能用 self.parent()（被 parent(index) 遮蔽）</extracomment>
        <translation>Key</translation>
    </message>
    <message>
        <location filename="../ui/json_tree.py" line="187"/>
        <source>值</source>
        <translation>Value</translation>
    </message>
    <message>
        <location filename="../ui/json_tree.py" line="189"/>
        <source>类型</source>
        <translation>Type</translation>
    </message>
    <message>
        <location filename="../ui/json_tree.py" line="192"/>
        <source>路径：{0}</source>
        <translation>Path: {0}</translation>
    </message>
    <message>
        <location filename="../ui/json_tree.py" line="194"/>
        <source>对象（{0} 个键）</source>
        <translation>Object ({0} keys)</translation>
    </message>
    <message>
        <location filename="../ui/json_tree.py" line="196"/>
        <source>数组（{0} 项）</source>
        <translation>Array ({0} items)</translation>
    </message>
    <message>
        <location filename="../ui/json_tree.py" line="200"/>
        <source>
（共 {0} 字符，双击或右键复制完整值）</source>
        <translation>
({0} chars in total; right-click to copy the full value)</translation>
    </message>
</context>
<context>
    <name>JsonTreeView</name>
    <message>
        <location filename="../ui/json_tree.py" line="381"/>
        <source>复制值</source>
        <translation>Copy value</translation>
    </message>
    <message>
        <location filename="../ui/json_tree.py" line="382"/>
        <source>复制键</source>
        <translation>Copy key</translation>
    </message>
    <message>
        <location filename="../ui/json_tree.py" line="383"/>
        <source>复制路径</source>
        <translation>Copy path</translation>
    </message>
    <message>
        <location filename="../ui/json_tree.py" line="384"/>
        <source>复制整个节点（JSON）</source>
        <translation>Copy whole node (JSON)</translation>
    </message>
    <message>
        <location filename="../ui/json_tree.py" line="385"/>
        <source>全部展开</source>
        <translation>Expand all</translation>
    </message>
    <message>
        <location filename="../ui/json_tree.py" line="386"/>
        <source>全部收起</source>
        <translation>Collapse all</translation>
    </message>
</context>
<context>
    <name>LogPanel</name>
    <message>
        <location filename="../ui/log_panel.py" line="72"/>
        <source>全部</source>
        <extracomment>磁盘日志路径：~/.miteproxy/logs/miteproxy.log（main 里据此挂 RotatingFileHandler） (已格式化文本, 级别 levelno) 各级别在文本区里的颜色（红/琥珀在深浅色主题下都看得清） 级别筛选下拉：文案 -&gt; 最低级别阈值（记录 levelno &gt;= 阈值才显示）</extracomment>
        <translation>All</translation>
    </message>
    <message>
        <location filename="../ui/log_panel.py" line="73"/>
        <source>INFO 及以上</source>
        <translation>INFO and above</translation>
    </message>
    <message>
        <location filename="../ui/log_panel.py" line="74"/>
        <source>WARNING 及以上</source>
        <translation>WARNING and above</translation>
    </message>
    <message>
        <location filename="../ui/log_panel.py" line="75"/>
        <source>ERROR 及以上</source>
        <translation>ERROR and above</translation>
    </message>
    <message>
        <location filename="../ui/log_panel.py" line="90"/>
        <source>级别:</source>
        <extracomment>内存里最多保留的行数（防止长时间运行把文本区撑爆；磁盘文件另有滚动上限）</extracomment>
        <translation>Level:</translation>
    </message>
    <message>
        <location filename="../ui/log_panel.py" line="100"/>
        <source>打开日志文件</source>
        <translation>Open log file</translation>
    </message>
    <message>
        <location filename="../ui/log_panel.py" line="101"/>
        <source>在访达中打开滚动日志文件（macOS）</source>
        <translation>Open the rolling log file in Finder (macOS)</translation>
    </message>
    <message>
        <location filename="../ui/log_panel.py" line="105"/>
        <source>清空</source>
        <translation>Clear</translation>
    </message>
    <message>
        <location filename="../ui/log_panel.py" line="106"/>
        <source>清空当前显示的日志（不影响磁盘文件）</source>
        <translation>Clears the currently displayed logs (the file on disk is unaffected)</translation>
    </message>
</context>
<context>
    <name>MainWindow</name>
    <message>
        <location filename="../ui/main_window.py" line="542"/>
        <source>文件</source>
        <translation>File</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="543"/>
        <source>保存会话…</source>
        <translation>Save session…</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="548"/>
        <source>打开会话…</source>
        <translation>Open session…</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="297"/>
        <location filename="../ui/main_window.py" line="554"/>
        <source>清除列表</source>
        <extracomment>重放并对比：等重放响应到达的超时（秒）。超时说明上游没响应， 清理 pending 并在状态栏告知，避免永远等一个不会来的 flow。 对比对话框保留个数：开太多不关也不至于无限攒着 启动时是否询问恢复上次会话快照（脚本/测试可关掉，避免模态框阻塞） 系统代理接管/还原串行化：停代理与后台接管线程竞争时保证不漏还原 更新检测：checker 惰性创建（用到才建 QNetworkAccessManager）； _update_manual 标记本次是否用户手动触发（决定无更新/失败要不要提示） 断点编辑器（非模态，多条会话可同时挂起 → 都留着引用，关掉时清）</extracomment>
        <translation>Clear list</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="559"/>
        <source>退出时自动保存会话</source>
        <translation>Auto-save session on exit</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="567"/>
        <source>退出</source>
        <translation>Quit</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="475"/>
        <location filename="../ui/main_window.py" line="572"/>
        <source>工具</source>
        <translation>Tools</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="111"/>
        <source>CA 证书位置：{path}

macOS：双击后在「钥匙串访问」中设为始终信任；
手机：点「证书服务」按钮，用手机浏览器打开显示的地址安装。</source>
        <translation>CA certificate location: {path}

macOS: double-click it and set it to &quot;Always Trust&quot; in Keychain Access;
Phone: tap the &quot;Certificate service&quot; button and open the shown address in the phone&apos;s browser to install.</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="311"/>
        <source>保存数量:</source>
        <translation>Keep:</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="314"/>
        <source>{0} 条</source>
        <translation>{0}</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="316"/>
        <source>流量列表最多保留的会话数，超出后从最旧一条开始丢弃（上限 5000）</source>
        <translation>Maximum sessions kept in the traffic list; beyond this the oldest are dropped (max 5000)</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="325"/>
        <source>高亮:</source>
        <translation>Highlight:</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="327"/>
        <source>URL 关键字</source>
        <translation>URL keyword</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="331"/>
        <source>URL 包含该关键字的请求整行黄色高亮。
实时生效：正在显示的与之后新到的流量都会高亮；清空即关闭。</source>
        <translation>Requests whose URL contains this keyword are highlighted across the whole row in yellow.
Live: both currently shown and future traffic are highlighted; clearing the box turns it off.</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="337"/>
        <source>自动滚动</source>
        <translation>Auto-scroll</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="340"/>
        <source>新会话到达时自动滚到最新一条。
你手动翻到别处时不会来抢滚动条——只有停在最新端才跟着走。</source>
        <translation>Scrolls to the newest session as new ones arrive.
It will not fight your manual scrolling — it only follows when you are already at the newest end.</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="345"/>
        <source>设为系统代理</source>
        <translation>Set as system proxy</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="348"/>
        <source>启动代理时自动把系统 HTTP/HTTPS 代理指向本应用，停止或退出时自动还原
（对齐 Fiddler「Act as System Proxy」）。
macOS 首次接管会请求一次管理员授权；不想自动改系统设置就取消勾选。</source>
        <translation>On proxy start, points the system HTTP/HTTPS proxy at this app automatically, and restores it on stop or quit
(matching Fiddler&apos;s &quot;Act as System Proxy&quot;).
macOS asks for admin authorization the first time it takes over; uncheck to avoid changing system settings.</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="356"/>
        <location filename="../ui/main_window.py" line="868"/>
        <location filename="../ui/main_window.py" line="959"/>
        <source>启动代理</source>
        <translation>Start proxy</translation>
    </message>
    <message>
        <source>端口:</source>
        <translation type="vanished">Port:</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="362"/>
        <source>顺序:</source>
        <translation>Order:</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="364"/>
        <source>到达顺序（新在底部）</source>
        <translation>Arrival order (newest at bottom)</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="365"/>
        <source>新的在顶部</source>
        <translation>Newest at top</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="366"/>
        <source>倒序 = 按到达序号降序，最新的会话排在最上面</source>
        <translation>Reverse = sort by arrival number descending, newest session on top</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="370"/>
        <source>布局:</source>
        <translation>Layout:</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="372"/>
        <source>左右布局</source>
        <translation>Side by side</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="373"/>
        <source>上下布局</source>
        <translation>Top and bottom</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="375"/>
        <source>流量列表与详情区的排布方向。左右 = Fiddler 风格（列表在左、body 在右），
上下 = 列表在上、body 在下。选择会记住，下次启动保持。</source>
        <translation>Arrangement of the traffic list and the detail area. Side by side = Fiddler style (list left, body right),
top/bottom = list above, body below. The choice is remembered and kept on next launch.</translation>
    </message>
    <message>
        <source>证书端口:</source>
        <translation type="vanished">Cert port:</translation>
    </message>
    <message>
        <source>证书下载服务的监听端口（默认 8081，被占用时自动顺延）
证书服务运行中修改会立即用新端口重启</source>
        <translation type="vanished">Listening port of the certificate download service (default 8081, auto-increments if taken)
Changing it while the service runs restarts it on the new port immediately</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="387"/>
        <source>证书服务</source>
        <translation>Certificate service</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="388"/>
        <source>启动局域网证书下载服务（手机装 CA 用）</source>
        <translation>Starts the LAN certificate download service (for installing the CA on phones)</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="391"/>
        <location filename="../ui/main_window.py" line="1283"/>
        <source>导出 CA 证书</source>
        <translation>Export CA certificate</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="462"/>
        <source>流量</source>
        <translation>Traffic</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="466"/>
        <source>Mock 规则</source>
        <translation>Mock rules</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="471"/>
        <source>网络模拟</source>
        <translation>Network simulation</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="479"/>
        <source>日志</source>
        <translation>Log</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="484"/>
        <source>统计</source>
        <translation>Stats</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="496"/>
        <location filename="../ui/main_window.py" line="2410"/>
        <source>代理未启动</source>
        <translation>Proxy not started</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="504"/>
        <source>点击开始/停止抓包（接管或还原系统代理，与工具栏「设为系统代理」联动）</source>
        <translation>Click to start/stop capturing (takes over or restores the system proxy; linked with the toolbar&apos;s &quot;Set as system proxy&quot;)</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="580"/>
        <source>编码转换…</source>
        <translation>Encoding converter…</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="585"/>
        <source>JSON 格式化 / 提取…</source>
        <translation>JSON format / extract…</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="590"/>
        <source>JSON 比对…</source>
        <translation>JSON compare…</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="596"/>
        <source>设置</source>
        <translation>Settings</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="597"/>
        <source>偏好设置…</source>
        <translation>Preferences…</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="603"/>
        <source>外观</source>
        <translation>Appearance</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="608"/>
        <source>跟随系统</source>
        <translation>Follow system</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="609"/>
        <source>浅色模式</source>
        <translation>Light mode</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="610"/>
        <source>深色模式</source>
        <translation>Dark mode</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="623"/>
        <source>语言</source>
        <translation>Language</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="640"/>
        <source>帮助</source>
        <translation>Help</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="641"/>
        <source>检查更新…</source>
        <translation>Check for updates…</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="644"/>
        <source>意见反馈…</source>
        <translation>Feedback…</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="647"/>
        <location filename="../ui/main_window.py" line="2511"/>
        <source>关于</source>
        <translation>About</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="662"/>
        <source>语言已切换</source>
        <translation>Language changed</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="663"/>
        <source>语言将在重启 MiteProxy 后生效。</source>
        <translation>The language will take effect after restarting MiteProxy.</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="853"/>
        <location filename="../ui/main_window.py" line="1097"/>
        <source>端口 {0} 被占用，代理已自动改用 {1}</source>
        <translation>Port {0} is in use; the proxy automatically switched to {1}</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="855"/>
        <source>停止代理</source>
        <translation>Stop proxy</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="897"/>
        <location filename="../ui/main_window.py" line="906"/>
        <source>无接管记录</source>
        <translation>No takeover record</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="911"/>
        <source>{0}（停止代理或退出时自动还原）</source>
        <translation>{0} (restored automatically on proxy stop or exit)</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="914"/>
        <source>系统代理接管失败：{0}（可手动设置代理 127.0.0.1:{1}）</source>
        <translation>Failed to take over the system proxy: {0} (you can set the proxy to 127.0.0.1:{1} manually)</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="923"/>
        <source>系统代理接管失败</source>
        <translation>Failed to take over the system proxy</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="924"/>
        <source>{0}

用管理员权限重试？（会弹出密码确认框，与 Charles 行为一致）</source>
        <translation>{0}

Retry with administrator privileges? (a password prompt will appear, same as Charles)</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1004"/>
        <source>代理端口已保存为 {0}（重启后生效）</source>
        <translation>Proxy port saved as {0} (takes effect after restart)</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1009"/>
        <source>端口已修改</source>
        <translation>Port changed</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1010"/>
        <source>代理端口已修改为 {0}，需要重启才能生效。

是否立即重启应用？重启后系统代理会自动切换到新端口。</source>
        <translation>The proxy port has been changed to {0} and requires a restart to take effect.

Restart the app now? The system proxy will switch to the new port automatically after the restart.</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1017"/>
        <source>新端口 {0} 将在下次启动时生效</source>
        <translation>New port {0} will take effect on next launch</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1023"/>
        <source>抓包代理开关。监听 127.0.0.1:{0}——端口在「设置 → 偏好设置 → 代理」里改。</source>
        <translation>Capture proxy toggle. Listening on 127.0.0.1:{0} — change the port in Settings → Preferences → Proxy.</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1058"/>
        <source>正在重启应用，切换到端口 {0} …</source>
        <translation>Restarting the app, switching to port {0} …</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1077"/>
        <source>正在重启代理，切换到 127.0.0.1:{0} …</source>
        <translation>Restarting the proxy, switching to 127.0.0.1:{0} …</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1102"/>
        <source>代理已重启，监听 127.0.0.1:{0}；系统代理切换中…</source>
        <translation>Proxy restarted, listening on 127.0.0.1:{0}; switching the system proxy…</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1149"/>
        <location filename="../ui/main_window.py" line="1203"/>
        <source>端口 {0} 被占用，证书服务已自动改用 {1}</source>
        <translation>Port {0} is in use; the certificate service automatically switched to {1}</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1181"/>
        <source>证书端口已保存为 {0}，下次启动证书服务时生效</source>
        <translation>Certificate port saved as {0}; takes effect the next time the service starts</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1229"/>
        <source>证书服务已启动</source>
        <translation>Certificate service started</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1232"/>
        <source>手机连上同一 Wi-Fi，用相机扫下方任一二维码（或浏览器打开地址），
在打开的网页里下载并安装证书：</source>
        <translation>Connect the phone to the same Wi-Fi, scan either QR code below with the camera (or open the address in a browser),
then download and install the certificate on the page that opens:</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1260"/>
        <source>安装证书后，手机 Wi-Fi 的代理请设为：电脑IP : {0}</source>
        <translation>After installing the certificate, set the phone&apos;s Wi-Fi proxy to: computer IP : {0}</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1264"/>
        <source>好</source>
        <translation>OK</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1283"/>
        <source>证书 (*.pem *.cer)</source>
        <translation>Certificates (*.pem *.cer)</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1288"/>
        <source>已导出</source>
        <translation>Exported</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1474"/>
        <source>（{0} 条）</source>
        <translation>({0})</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1476"/>
        <source>查看详情…</source>
        <translation>View details…</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1482"/>
        <source>重放请求 (R / Ctrl+R)</source>
        <translation>Replay request (R / Ctrl+R)</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1483"/>
        <source>编辑并重放… (E)</source>
        <translation>Edit and replay… (E)</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1484"/>
        <source>重放并对比…</source>
        <translation>Replay and compare…</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1486"/>
        <source>复制为 cURL (bash){0}  Ctrl+Shift+C</source>
        <translation>Copy as cURL (bash){0}  Ctrl+Shift+C</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1487"/>
        <source>复制为 cURL (Windows cmd){0}</source>
        <translation>Copy as cURL (Windows cmd){0}</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1488"/>
        <source>仅复制 URL{0}  Ctrl+Shift+U</source>
        <translation>Copy URL only{0}  Ctrl+Shift+U</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1490"/>
        <source>导出选中会话{0}…  Ctrl+E</source>
        <translation>Export selected sessions{0}…  Ctrl+E</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1491"/>
        <source>导出完整响应（Headers+Body）…</source>
        <translation>Export full response (Headers+Body)…</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1497"/>
        <source>在工具页中打开 body</source>
        <translation>Open body in the Tools page</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1500"/>
        <source>发送到 API 调试</source>
        <translation>Send to API debugger</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1504"/>
        <source>标记/备注…</source>
        <translation>Mark / comment…</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1507"/>
        <source>清除备注</source>
        <translation>Clear comment</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1513"/>
        <source>加入 Mock（用原响应做 Mock）</source>
        <translation>Add to Mock (mock with the original response)</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1559"/>
        <source>该请求还没有响应，无法生成 Mock</source>
        <translation>This request has no response yet, so a Mock rule cannot be generated</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1569"/>
        <source>已加入 Mock：{0}（精确匹配 URL，响应=原响应）</source>
        <translation>Added to Mock: {0} (exact URL match, response = original response)</translation>
    </message>
    <message>
        <source>该会话没有 body 可转换</source>
        <translation type="vanished">This session has no body to convert</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1652"/>
        <source>（二进制内容已按十六进制导入）</source>
        <translation>(binary content imported as hex)</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1654"/>
        <source>（已截断到前 512KB）</source>
        <translation>(truncated to the first 512KB)</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1662"/>
        <source>JSON 工具</source>
        <translation>JSON tools</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1662"/>
        <source>JSON 比对</source>
        <translation>JSON compare</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1662"/>
        <source>API 调试</source>
        <translation>API debugger</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1663"/>
        <source>编码转换</source>
        <translation>Encoding converter</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1666"/>
        <source>已把该会话的 body 送入工具页 · {0}{1}</source>
        <translation>Sent this session&apos;s body to the Tools page · {0}{1}</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1714"/>
        <source>已把该请求带入 API 调试页（改完点「发送」）</source>
        <translation>Loaded this request into the API debugger (click &quot;Send&quot; when done)</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1730"/>
        <source>标记/备注</source>
        <translation>Mark / comment</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1731"/>
        <source>给这条会话写个备注（列表「标记」列显示）：</source>
        <translation>Write a comment for this session (shown in the list&apos;s &quot;Mark&quot; column):</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1754"/>
        <source>已备注</source>
        <translation>Commented</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1754"/>
        <source>已清除备注</source>
        <translation>Comment cleared</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1766"/>
        <source>{0} 条 · </source>
        <translation>{0} · </translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1768"/>
        <source>已复制 cURL（{0}，{1}{2} 字符）: {3}…</source>
        <translation>Copied cURL ({0}, {1}{2} chars): {3}…</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1780"/>
        <source>{0} 条（首条 {1}）</source>
        <translation>{0} (first: {1})</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1781"/>
        <source>已复制 URL: {0}</source>
        <translation>Copied URL: {0}</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1786"/>
        <location filename="../ui/main_window.py" line="2090"/>
        <source>提示</source>
        <translation>Notice</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1786"/>
        <source>请先在流量列表里选中一条会话</source>
        <translation>Please select a session in the traffic list first</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1791"/>
        <location filename="../ui/main_window.py" line="1818"/>
        <source>该格式不支持多选</source>
        <translation>This format does not support multi-selection</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1792"/>
        <source>「仅响应 Body」一个文件只能装一条会话的 body。
请只选一条，或改用 HAR / 原始报文 / 完整响应。</source>
        <translation>&quot;Response body only&quot; can hold just one session&apos;s body per file.
Please select only one, or use HAR / raw messages / full response instead.</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1800"/>
        <location filename="../ui/main_window.py" line="1824"/>
        <source>暂无响应</source>
        <translation>No response yet</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1801"/>
        <source>所选会话里有还没响应的请求（请求进行中或连接已中断），无法导出。</source>
        <translation>Some selected sessions have requests that have not responded yet (in progress or the connection was interrupted); export is not possible.</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1808"/>
        <source>导出选中会话（{0} 条）</source>
        <translation>Export selected sessions ({0})</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1808"/>
        <source>导出选中会话</source>
        <translation>Export selected sessions</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1818"/>
        <source>「仅响应 Body」请只选一条会话。</source>
        <translation>&quot;Response body only&quot;: please select just one session.</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1824"/>
        <source>所选会话里有还没响应的请求，无法导出。</source>
        <translation>Some selected sessions have requests that have not responded yet; export is not possible.</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1833"/>
        <source>已导出 {0} 条 → {1}</source>
        <translation>Exported {0} → {1}</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1833"/>
        <source>已导出 → {0}</source>
        <translation>Exported → {0}</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1888"/>
        <source>退出时将自动保存会话快照</source>
        <translation>A session snapshot will be saved automatically on exit</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1888"/>
        <source>已关闭退出自动保存</source>
        <translation>Auto-save on exit turned off</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1894"/>
        <source>没有可保存的会话</source>
        <translation>No sessions to save</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1894"/>
        <source>当前列表是空的。</source>
        <translation>The current list is empty.</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1899"/>
        <source>保存会话（{0} 条）</source>
        <translation>Save session ({0})</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1899"/>
        <location filename="../ui/main_window.py" line="1928"/>
        <source>会话文件 (*{0})</source>
        <translation>Session files (*{0})</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1915"/>
        <source>

注意：有 {0} 条会话的 body 未保存（超出单包体积预算）。</source>
        <translation>

Note: the bodies of {0} sessions were not saved (exceeding the per-package size budget).</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1918"/>
        <source>

注意：有 {0} 条会话的 body 被截断。</source>
        <translation>

Note: the bodies of {0} sessions were truncated.</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1921"/>
        <source>已保存</source>
        <translation>Saved</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1922"/>
        <source>共 {0} 条会话 → {1}
文件大小 {2}{3}</source>
        <translation>{0} sessions → {1}
File size {2}{3}</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1924"/>
        <source>已保存 {0} 条会话 → {1}</source>
        <translation>Saved {0} sessions → {1}</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1928"/>
        <location filename="../ui/main_window.py" line="1939"/>
        <source>打开会话</source>
        <translation>Open session</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1940"/>
        <source>当前列表有 {0} 条会话，打开文件会先清空它们。
是否继续？</source>
        <translation>The current list has {0} sessions; opening a file will clear them first.
Continue?</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1953"/>
        <source>没有可恢复的会话</source>
        <translation>No sessions to restore</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1953"/>
        <source>{0}

文件中没有有效会话。</source>
        <translation>{0}

The file contains no valid sessions.</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1961"/>
        <source>
跳过无法解析的行：{0} 条。</source>
        <translation>
Skipped {0} unparsable lines.</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1966"/>
        <source>
有 {0} 条会话的 body 被截断（超出快照单条上限），详情面板会标注。</source>
        <translation>
{0} bodies were truncated (over the per-body snapshot limit); the detail panel marks them.</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1969"/>
        <source>
超出保存条数上限，最早的 {0} 条未载入。</source>
        <translation>
Exceeded the save limit; the oldest {0} were not loaded.</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1972"/>
        <source>已恢复</source>
        <translation>Restored</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1973"/>
        <source>共恢复 {0} 条会话。{1}</source>
        <translation>Restored {0} sessions. {1}</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1975"/>
        <source>已打开会话 {0}</source>
        <translation>Opened session {0}</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="2006"/>
        <source>恢复上次会话</source>
        <translation>Restore last session</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="2007"/>
        <source>检测到上次退出时保存的 {0} 条会话</source>
        <translation>Found {0} sessions saved on last exit</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="2009"/>
        <source>。
是否恢复到列表？</source>
        <translation>.
Restore them to the list?</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="2066"/>
        <source>已立即生效</source>
        <translation>Effective immediately</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="2066"/>
        <source>代理启动后生效</source>
        <translation>Effective after the proxy starts</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="2070"/>
        <source>弱网 {0}ms / {1}kbps</source>
        <translation>Throttle {0}ms / {1}kbps</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="2072"/>
        <source>{0} 条域名映射</source>
        <translation>{0} domain mappings</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="2074"/>
        <source>{0} 条本地目录映射</source>
        <translation>{0} local directory mappings</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="2075"/>
        <source>网络模拟已关闭</source>
        <translation>Network simulation is off</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="2077"/>
        <source>（{0} 条映射填写不完整，已跳过）</source>
        <translation>({0} mappings are incomplete and were skipped)</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="2090"/>
        <source>请先启动代理再重放</source>
        <translation>Please start the proxy before replaying</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="2126"/>
        <source>已加入重放队列: {0} {1}</source>
        <translation>Added to the replay queue: {0} {1}</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="2128"/>
        <source>（响应到达后自动打开对比）</source>
        <translation>(the comparison opens automatically when the response arrives)</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="2264"/>
        <source>该会话被当前过滤条件隐藏，已切回流量页</source>
        <translation>This session is hidden by the current filter; switched back to the Traffic tab</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="2355"/>
        <source>重放对比等待超时（{0} 条）：未收到重放响应</source>
        <translation>Replay comparison timed out ({0}): no replay response received</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="2365"/>
        <source>对比失败：原会话或重放会话已被淘汰出缓存</source>
        <translation>Comparison failed: the original or replayed session has been evicted from the cache</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="2386"/>
        <source>共 {0} 条</source>
        <translation>{0} in total</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="2386"/>
        <source> · 显示 {0} 条</source>
        <translation> · {0} shown</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="2389"/>
        <source> · 已选 {0} 条</source>
        <translation> · {0} selected</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="2391"/>
        <source> · 搜索「{0}」</source>
        <translation> · search &quot;{0}&quot;</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="2393"/>
        <source> · 已排序</source>
        <translation> · sorted</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="2395"/>
        <source> · 弱网模拟中</source>
        <translation> · throttling</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="2406"/>
        <source>代理运行中 127.0.0.1:{0}</source>
        <translation>Proxy running on 127.0.0.1:{0}</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="2414"/>
        <source>证书服务 {0}</source>
        <translation>Certificate service {0}</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="2429"/>
        <source>● 抓包中（系统代理 127.0.0.1:{0}）</source>
        <translation>● Capturing (system proxy 127.0.0.1:{0})</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="2435"/>
        <source>○ 抓包暂停（未接管系统代理）</source>
        <translation>○ Capture paused (system proxy not taken over)</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="2438"/>
        <source>○ 未抓包（代理未运行）</source>
        <translation>○ Not capturing (proxy not running)</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="2490"/>
        <location filename="../ui/main_window.py" line="2500"/>
        <source>检查更新</source>
        <translation>Check for updates</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="2491"/>
        <source>暂时无法获取版本信息：{0}</source>
        <translation>Could not retrieve version information: {0}</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="2492"/>
        <source>未知错误</source>
        <translation>unknown error</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="2501"/>
        <source>当前已是最新版本（{0}）。</source>
        <translation>You are already on the latest version ({0}).</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="2512"/>
        <source>MiteProxy {0}

基于 mitmproxy + PySide6 的抓包 / Mock 工具。
支持 HTTP/HTTPS 抓包、Mock 规则、Fiddler 规则导入。</source>
        <translation>MiteProxy {0}

A traffic capture / mock tool built on mitmproxy + PySide6.
Supports HTTP/HTTPS capture, mock rules and Fiddler rule import.</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1636"/>
        <source>该会话没有可查看的 body（响应为空或尚未捕获）</source>
        <translation>This session has no body to show (the response is empty or not captured yet)</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1493"/>
        <source>删除选中会话{0}  Del</source>
        <translation>Delete selected session{0}  Del</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="2106"/>
        <source>已加入重放队列（{0} 条）</source>
        <translation>Added to replay queue ({0} sessions)</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="2108"/>
        <source>，{0} 条入队失败</source>
        <translation>, {0} failed to queue</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="2111"/>
        <source>重放失败：没有请求进入队列</source>
        <translation>Replay failed: no request was queued</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="2145"/>
        <source>已删除 {0} 条会话</source>
        <translation>Deleted {0} sessions</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="1528"/>
        <source>仅支持单条会话：编辑与对比弹窗一次只能处理一条</source>
        <translation>Single session only: the edit and compare dialogs handle one at a time</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="395"/>
        <source>断点</source>
        <translation>Breakpoint</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="399"/>
        <source>断点调试：命中的会话会挂起，改完再放行（请求前 / 响应前在设置里配）</source>
        <translation>Breakpoints: matched sessions are held until you edit and release them (configure before-request / before-response in Settings)</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="2158"/>
        <source>断点调试{0}</source>
        <translation>Breakpoints {0}</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="2156"/>
        <source>已开启</source>
        <translation>enabled</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="2156"/>
        <source>已关闭</source>
        <translation>disabled</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="2175"/>
        <source>断点命中（{0}）：会话已挂起，改完点「继续放行」</source>
        <translation>Breakpoint hit ({0}): session held, click &quot;Release&quot; when done</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="2176"/>
        <source>请求前</source>
        <translation>before request</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="2176"/>
        <source>响应前</source>
        <translation>before response</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="302"/>
        <source>搜索</source>
        <translation>Search</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="305"/>
        <source>搜索会话（URL / Header / Body）  Ctrl+F</source>
        <translation>Search sessions (URL / headers / body)  Ctrl+F</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="574"/>
        <source>搜索会话…</source>
        <translation>Search sessions…</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="405"/>
        <source>MCP</source>
        <translation>MCP</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="408"/>
        <source>MCP 接口：把最近抓包暴露给 AI 客户端（默认关）。
监听地址与端口在「设置 → 流量列表 → MCP 接口」里改：
默认 127.0.0.1 仅本机可连；改成 0.0.0.0 或网卡 IP 后局域网内的设备也能读到完整抓包。</source>
        <translation>MCP interface: expose recent captures to AI clients (off by default).
Change the bind address and port in Settings → Traffic list → MCP:
127.0.0.1 (default) is local-only; 0.0.0.0 or a NIC IP makes the full capture readable from other devices on the LAN.</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="2298"/>
        <source>MCP 服务已启动：{0}</source>
        <translation>MCP server started: {0}</translation>
    </message>
    <message>
        <source>MCP 服务启动失败：端口 {0} 起均不可用</source>
        <translation type="vanished">MCP server failed to start: no free port from {0}</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="2312"/>
        <source>MCP 服务已停止</source>
        <translation>MCP server stopped</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="2284"/>
        <source>MCP 服务启动失败：地址 {0} 的端口 {1} 起均不可用</source>
        <translation>MCP server failed to start: no free port from {1} on {0}</translation>
    </message>
    <message>
        <location filename="../ui/main_window.py" line="2292"/>
        <source>MCP 服务已启动（局域网可见）：{0} —— 抓包含 Cookie / 鉴权头，用完记得关</source>
        <translation>MCP server started (LAN visible): {0} — captures contain cookies/tokens, remember to turn it off</translation>
    </message>
</context>
<context>
    <name>McpServer</name>
    <message>
        <location filename="../mcpserver.py" line="61"/>
        <source>返回最近的抓包记录。可按 URL、请求参数（query 或 body）、Header 关键字过滤，也支持按方法 / 状态码筛选。</source>
        <extracomment>默认只监听本机；改成 0.0.0.0 才会对局域网开放 视为&quot;对外暴露&quot;的地址（绑这些=不再只服务于本机） 端口被占用时向上顺延的尝试次数 body 预览长度（完整 body 可能几 MB，默认只给开头） 详情工具单个 body 的上限（默认给全量，超过才截断并标注） 详情里最多带多少条 WebSocket 消息 单次最多返回条数（防止一次吐几千条把客户端噎死） 工具描述文案：模块级用 NOOP 打标（import 期不能调 translate，翻译器还没装）， 运行时在 _tools() 里才真正翻译。</extracomment>
        <translation>Return recent captured sessions. Filter by URL, request params (query or body), or header keywords; method and status code filters are also supported.</translation>
    </message>
    <message>
        <location filename="../mcpserver.py" line="66"/>
        <source>URL 关键字（匹配方法、域名、IP、路径）</source>
        <translation>URL keyword (matches method, host, IP, path)</translation>
    </message>
    <message>
        <location filename="../mcpserver.py" line="67"/>
        <source>请求参数关键字（匹配 query 或请求体）</source>
        <translation>Request parameter keyword (matches query string or request body)</translation>
    </message>
    <message>
        <location filename="../mcpserver.py" line="68"/>
        <source>Header 关键字（匹配请求/响应的头名或值）</source>
        <translation>Header keyword (matches request/response header name or value)</translation>
    </message>
    <message>
        <location filename="../mcpserver.py" line="69"/>
        <source>HTTP 方法，如 GET / POST</source>
        <translation>HTTP method, e.g. GET / POST</translation>
    </message>
    <message>
        <location filename="../mcpserver.py" line="70"/>
        <source>响应状态码精确匹配，如 404</source>
        <translation>Exact response status code match, e.g. 404</translation>
    </message>
    <message>
        <location filename="../mcpserver.py" line="71"/>
        <source>是否返回完整请求/响应体，默认只给预览</source>
        <translation>Return full request/response bodies; by default only a preview is returned</translation>
    </message>
    <message>
        <location filename="../mcpserver.py" line="72"/>
        <source>最多返回条数，默认 20，上限 {0}</source>
        <translation>Max sessions to return, default 20, hard limit {0}</translation>
    </message>
    <message>
        <location filename="../mcpserver.py" line="75"/>
        <source>按 id 取单条会话的完整报文（含全量请求/响应体）。先用 get_recent_flows 缩小范围拿到 id，再用它展开细节——比一次性拉全量列表省 token。</source>
        <translation>Fetch a single session&apos;s full message by id (complete request/response bodies included). Call get_recent_flows first to narrow down and get the id, then expand details here — cheaper than pulling whole lists.</translation>
    </message>
    <message>
        <location filename="../mcpserver.py" line="81"/>
        <source>会话 id（get_recent_flows 返回的 id；给前几位前缀也行）</source>
        <translation>Session id (the id returned by get_recent_flows; a leading prefix also works)</translation>
    </message>
    <message>
        <location filename="../mcpserver.py" line="82"/>
        <source>是否返回完整 body，默认 true</source>
        <translation>Return full bodies; defaults to true</translation>
    </message>
    <message>
        <location filename="../mcpserver.py" line="84"/>
        <source>对抓包记录做整体统计：总数、错误率、平均/P95/最大耗时、上下行流量，按域名 / 状态码 / 方法聚合，慢请求 Top N，以及按时间分桶的请求分布。回答「刚才哪些请求挂了」「哪个域名最慢」这类问题用它。</source>
        <translation>Aggregate stats over captured traffic: totals, error rate, avg/P95/max duration, up/down bytes, breakdowns by host / status / method, slowest requests Top N, and a time-bucketed request histogram. Use it for questions like &quot;which requests just failed&quot; or &quot;which host is slowest&quot;.</translation>
    </message>
    <message>
        <location filename="../mcpserver.py" line="90"/>
        <source>可选 URL 关键字（只统计命中方法+URL 的会话）</source>
        <translation>Optional URL keyword (only sessions whose method + URL match)</translation>
    </message>
    <message>
        <location filename="../mcpserver.py" line="91"/>
        <source>域名 / 慢请求各取前多少条，默认 {0}，上限 {1}</source>
        <translation>How many hosts / slow requests to return; default {0}, max {1}</translation>
    </message>
    <message>
        <location filename="../mcpserver.py" line="93"/>
        <source>缺少 id 参数</source>
        <translation>Missing required argument: id</translation>
    </message>
    <message>
        <location filename="../mcpserver.py" line="94"/>
        <source>找不到 id 为 {0} 的会话（可能已被清理）</source>
        <translation>No session with id {0} (it may have been evicted)</translation>
    </message>
    <message>
        <location filename="../mcpserver.py" line="95"/>
        <source>前缀 {1} 匹配到 {0} 条会话，请给出更完整的 id</source>
        <translation>Prefix {1} matches {0} sessions; please give a more complete id</translation>
    </message>
</context>
<context>
    <name>MessagePane</name>
    <message>
        <location filename="../ui/detail_panel.py" line="1047"/>
        <location filename="../ui/detail_panel.py" line="1107"/>
        <source>（未选择会话）</source>
        <translation>(no session selected)</translation>
    </message>
</context>
<context>
    <name>NetworkPanel</name>
    <message>
        <location filename="../ui/network_panel.py" line="41"/>
        <source>延迟在响应返回给客户端前施加：档位给的固定延迟 + 按响应体大小折算的传输时间。
用来复现 loading 态、超时、骨架屏；不是逐块限速。</source>
        <translation>The delay is applied before the response is returned to the client: a fixed delay from the preset plus transfer time computed from the response body size.
Use it to reproduce loading states, timeouts and skeleton screens; it is not per-chunk rate limiting.</translation>
    </message>
    <message>
        <location filename="../ui/network_panel.py" line="47"/>
        <source>两种映射，按「目标」写法自动区分：
• Map Remote：目标写 host:port（如 127.0.0.1:8080），把请求转发到该地址——只替换 scheme + 域名 + 端口，路径与 query 原样保留；
• Map Local：目标写本地目录（如 ./static 或 ~/site），按 URL 路径取目录下的文件直接响应，文件不存在则透传上游（仅 GET/HEAD，防路径穿越）。
原域名含 * + ? [ ] ( ) { } | \ ^ $ 时按正则处理，否则按字面域名精确匹配；目标写 127.0.0.1:8080 时默认用 http，需要 https 就写 https://host:port。</source>
        <translation>The two mapping kinds are told apart by how the target is written:
• Map Remote: target is host:port (e.g. 127.0.0.1:8080) and the request is forwarded there — only scheme + domain + port are replaced; path and query are kept as-is;
• Map Local: target is a local directory (e.g. ./static or ~/site); the file under that directory matching the URL path is served directly, and if it does not exist the request passes through to upstream (GET/HEAD only, to prevent path traversal).
If the source domain contains * + ? [ ] ( ) { } | \ ^ $ it is treated as a regex, otherwise as a literal exact domain; a target of 127.0.0.1:8080 defaults to http — write https://host:port for https.</translation>
    </message>
    <message>
        <location filename="../ui/network_panel.py" line="88"/>
        <source>弱网模拟</source>
        <translation>Throttle simulation</translation>
    </message>
    <message>
        <location filename="../ui/network_panel.py" line="93"/>
        <source>档位:</source>
        <translation>Preset:</translation>
    </message>
    <message>
        <location filename="../ui/network_panel.py" line="97"/>
        <source>关闭 = 不做任何延迟</source>
        <translation>Off = no delay at all</translation>
    </message>
    <message>
        <location filename="../ui/network_panel.py" line="101"/>
        <source>自定义延迟:</source>
        <translation>Custom delay:</translation>
    </message>
    <message>
        <location filename="../ui/network_panel.py" line="106"/>
        <source>每个响应固定等待的时间（上限 30 秒）</source>
        <translation>Fixed wait time per response (max 30 seconds)</translation>
    </message>
    <message>
        <location filename="../ui/network_panel.py" line="109"/>
        <source>速率:</source>
        <translation>Rate:</translation>
    </message>
    <message>
        <location filename="../ui/network_panel.py" line="114"/>
        <source>按速率把响应体大小折算成传输时间，0 = 不限速</source>
        <translation>Converts the response body size into transfer time at this rate; 0 = unlimited</translation>
    </message>
    <message>
        <location filename="../ui/network_panel.py" line="134"/>
        <source>域名映射（Map Remote / Map Local）</source>
        <translation>Domain mapping (Map Remote / Map Local)</translation>
    </message>
    <message>
        <location filename="../ui/network_panel.py" line="140"/>
        <source>启用</source>
        <translation>Enabled</translation>
    </message>
    <message>
        <location filename="../ui/network_panel.py" line="140"/>
        <source>原域名</source>
        <translation>Original domain</translation>
    </message>
    <message>
        <location filename="../ui/network_panel.py" line="140"/>
        <source>目标 host:port / 本地目录</source>
        <translation>Target host:port / local directory</translation>
    </message>
    <message>
        <location filename="../ui/network_panel.py" line="153"/>
        <source>+ 添加一行</source>
        <translation>+ Add row</translation>
    </message>
    <message>
        <location filename="../ui/network_panel.py" line="154"/>
        <source>删除选中行</source>
        <translation>Delete selected row</translation>
    </message>
    <message>
        <location filename="../ui/network_panel.py" line="324"/>
        <source>未启用</source>
        <translation>Disabled</translation>
    </message>
    <message>
        <location filename="../ui/network_panel.py" line="328"/>
        <source>延迟 {0} ms</source>
        <translation>Delay {0} ms</translation>
    </message>
    <message>
        <location filename="../ui/network_panel.py" line="330"/>
        <source>限速 {0} kbps</source>
        <translation>Rate limit {0} kbps</translation>
    </message>
    <message>
        <location filename="../ui/network_panel.py" line="331"/>
        <source>生效中：</source>
        <translation>Active:</translation>
    </message>
    <message>
        <location filename="../ui/network_panel.py" line="366"/>
        <source>已启用 {0} 条映射</source>
        <translation>{0} mappings enabled</translation>
    </message>
    <message>
        <location filename="../ui/network_panel.py" line="368"/>
        <source>，{0} 条填写不完整（已跳过）</source>
        <translation>, {0} incomplete (skipped)</translation>
    </message>
    <message>
        <location filename="../network.py" line="29"/>
        <source>关闭</source>
        <extracomment>单次延迟上限：手滑填个 999999 不至于把连接挂死 档位：(key, 显示名, 延迟 ms, 速率 kbps)。0 表示该项不生效 显示名用 QT_TRANSLATE_NOOP 打标（翻译器在 QApplication 创建后才装载， import 期求值永远是中文）；NetworkPanel 构建 combo 时再 translate。</extracomment>
        <translation>Off</translation>
    </message>
    <message>
        <location filename="../network.py" line="30"/>
        <source>2G（50 kbps + 400ms）</source>
        <translation>2G (50 kbps + 400ms)</translation>
    </message>
    <message>
        <location filename="../network.py" line="31"/>
        <source>3G（400 kbps + 200ms）</source>
        <translation>3G (400 kbps + 200ms)</translation>
    </message>
    <message>
        <location filename="../network.py" line="32"/>
        <source>4G（4 Mbps + 80ms）</source>
        <translation>4G (4 Mbps + 80ms)</translation>
    </message>
    <message>
        <location filename="../network.py" line="33"/>
        <source>弱网（50 kbps + 2000ms）</source>
        <translation>Weak (50 kbps + 2000ms)</translation>
    </message>
    <message>
        <location filename="../network.py" line="34"/>
        <source>自定义</source>
        <translation>Custom</translation>
    </message>
</context>
<context>
    <name>ProxyService</name>
    <message>
        <location filename="../proxy.py" line="84"/>
        <source>从端口 {0} 起连续 {1} 个端口均不可用</source>
        <extracomment>端口被占用时向后顺延的最大尝试数（从请求端口起连续试 100 个）</extracomment>
        <translation>None of the {1} consecutive ports starting from {0} are available</translation>
    </message>
</context>
<context>
    <name>ReplayEditDialog</name>
    <message>
        <location filename="../ui/replay_dialog.py" line="36"/>
        <location filename="../ui/replay_dialog.py" line="90"/>
        <source>重放并对比</source>
        <translation>Replay and compare</translation>
    </message>
    <message>
        <location filename="../ui/replay_dialog.py" line="36"/>
        <source>编辑并重放</source>
        <translation>Edit and replay</translation>
    </message>
    <message>
        <location filename="../ui/replay_dialog.py" line="49"/>
        <source>方法:</source>
        <translation>Method:</translation>
    </message>
    <message>
        <location filename="../ui/replay_dialog.py" line="69"/>
        <source>添加</source>
        <translation>Add</translation>
    </message>
    <message>
        <location filename="../ui/replay_dialog.py" line="73"/>
        <source>删除选中</source>
        <translation>Delete selected</translation>
    </message>
    <message>
        <location filename="../ui/replay_dialog.py" line="90"/>
        <source>重放</source>
        <translation>Replay</translation>
    </message>
</context>
<context>
    <name>RuleEditorDialog</name>
    <message>
        <location filename="../ui/rule_editor.py" line="52"/>
        <source>精确（完整 URL 相等）</source>
        <translation>Exact (full URL equality)</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="53"/>
        <source>包含（URL 含子串）</source>
        <translation>Contains (URL contains substring)</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="54"/>
        <source>通配符（* 不含 /，** 任意）</source>
        <translation>Wildcard (* excludes /, ** matches anything)</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="55"/>
        <source>正则表达式</source>
        <translation>Regular expression</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="61"/>
        <source>任意方法</source>
        <translation>Any method</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="62"/>
        <source>GET</source>
        <translation>GET</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="63"/>
        <source>POST</source>
        <translation>POST</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="64"/>
        <source>PUT</source>
        <translation>PUT</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="65"/>
        <source>DELETE</source>
        <translation>DELETE</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="66"/>
        <source>PATCH</source>
        <translation>PATCH</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="67"/>
        <source>HEAD</source>
        <translation>HEAD</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="68"/>
        <source>OPTIONS</source>
        <translation>OPTIONS</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="80"/>
        <source>编辑 Mock 规则</source>
        <translation>Edit mock rule</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="80"/>
        <source>新增 Mock 规则</source>
        <translation>New mock rule</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="95"/>
        <source>规则名称:</source>
        <translation>Rule name:</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="110"/>
        <source>如 /api/user/list 或 https?://.*/v1/.*</source>
        <translation>e.g. /api/user/list or https?://.*/v1/.*</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="118"/>
        <source>URL 匹配:</source>
        <translation>URL match:</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="129"/>
        <source>请求方法:</source>
        <translation>Request method:</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="136"/>
        <source>从抓包请求带入的原始请求 Body（仅参考，不参与 URL 匹配）</source>
        <translation>Original request body captured from the request (reference only, not used for URL matching)</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="138"/>
        <source>请求 Body:</source>
        <translation>Request body:</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="153"/>
        <source>状态码(100-599):</source>
        <translation>Status code (100-599):</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="162"/>
        <source>毫秒（0 = 不延迟）</source>
        <translation>milliseconds (0 = no delay)</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="164"/>
        <source>模拟延迟:</source>
        <translation>Simulated delay:</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="170"/>
        <source>直接输入内容</source>
        <translation>Enter content directly</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="171"/>
        <source>返回本地文件</source>
        <translation>Return local file</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="172"/>
        <source>重定向到其他 URL</source>
        <translation>Redirect to another URL</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="178"/>
        <source>响应内容:</source>
        <translation>Response content:</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="183"/>
        <source>如 https://staging.example.com/api/user，支持 $1 替换（正则捕获组）</source>
        <translation>e.g. https://staging.example.com/api/user, supports $1 substitution (regex capture group)</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="185"/>
        <source>重定向到:</source>
        <translation>Redirect to:</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="188"/>
        <source>响应 body，如 JSON / HTML …</source>
        <translation>Response body, e.g. JSON / HTML …</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="189"/>
        <source>Body:</source>
        <translation>Body:</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="196"/>
        <source>命中时读取该文件内容返回（请求时读取，改文件即生效）</source>
        <translation>Reads this file and returns its content on match (read at request time; edits take effect immediately)</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="198"/>
        <source>浏览…</source>
        <translation>Browse…</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="202"/>
        <source>文件路径:</source>
        <translation>File path:</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="221"/>
        <source>添加 Header</source>
        <translation>Add header</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="223"/>
        <source>删除选中行</source>
        <translation>Delete selected row</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="229"/>
        <source>Headers:</source>
        <translation>Headers:</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="281"/>
        <source>规则名称不能为空</source>
        <translation>The rule name cannot be empty</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="285"/>
        <source>匹配值不能为空</source>
        <translation>The match value cannot be empty</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="290"/>
        <source>正则无效: {0}</source>
        <translation>Invalid regex: {0}</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="296"/>
        <source>延迟必须是整数毫秒</source>
        <translation>The delay must be an integer number of milliseconds</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="298"/>
        <source>延迟必须在 0~{0} 毫秒之间</source>
        <translation>The delay must be between 0 and {0} milliseconds</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="304"/>
        <source>重定向目标不能为空</source>
        <translation>The redirect target cannot be empty</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="306"/>
        <source>重定向目标必须以 http:// 或 https:// 开头</source>
        <translation>The redirect target must start with http:// or https://</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="313"/>
        <source>状态码必须是整数</source>
        <translation>The status code must be an integer</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="315"/>
        <source>状态码必须在 100~599 之间</source>
        <translation>The status code must be between 100 and 599</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="328"/>
        <source>请选择本地文件路径</source>
        <translation>Please choose a local file path</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="332"/>
        <source>文件不存在: {0}</source>
        <translation>File does not exist: {0}</translation>
    </message>
    <message>
        <location filename="../ui/rule_editor.py" line="379"/>
        <source>选择 mock 响应文件</source>
        <translation>Select a mock response file</translation>
    </message>
</context>
<context>
    <name>RulesPanel</name>
    <message>
        <location filename="../ui/rules_panel.py" line="107"/>
        <location filename="../ui/rules_panel.py" line="618"/>
        <source>新增</source>
        <translation>New</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="108"/>
        <location filename="../ui/rules_panel.py" line="604"/>
        <source>编辑</source>
        <translation>Edit</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="109"/>
        <location filename="../ui/rules_panel.py" line="114"/>
        <location filename="../ui/rules_panel.py" line="616"/>
        <source>删除</source>
        <translation>Delete</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="110"/>
        <location filename="../ui/rules_panel.py" line="886"/>
        <source>导出规则</source>
        <translation>Export rules</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="111"/>
        <location filename="../ui/rules_panel.py" line="915"/>
        <source>导入规则</source>
        <translation>Import rules</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="112"/>
        <location filename="../ui/rules_panel.py" line="194"/>
        <location filename="../ui/rules_panel.py" line="606"/>
        <location filename="../ui/rules_panel.py" line="637"/>
        <source>启用</source>
        <translation>Enable</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="113"/>
        <location filename="../ui/rules_panel.py" line="606"/>
        <location filename="../ui/rules_panel.py" line="637"/>
        <source>停用</source>
        <translation>Disable</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="115"/>
        <source>导出</source>
        <translation>Export</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="116"/>
        <location filename="../ui/rules_panel.py" line="610"/>
        <source>上移</source>
        <translation>Move up</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="117"/>
        <location filename="../ui/rules_panel.py" line="611"/>
        <source>下移</source>
        <translation>Move down</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="119"/>
        <location filename="../ui/rules_panel.py" line="619"/>
        <source>导入 Fiddler 规则</source>
        <translation>Import Fiddler rules</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="126"/>
        <source>对勾选的规则生效；取消全部勾选后自动隐藏</source>
        <translation>Applies to checked rules; hides automatically when all are unchecked</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="128"/>
        <source>只显示启用</source>
        <translation>Show enabled only</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="130"/>
        <source>勾选后列表只显示启用中的规则；停用规则仍在存储中，取消勾选即可看到。</source>
        <translation>When checked, the list shows only enabled rules; disabled rules remain in storage and reappear when unchecked.</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="133"/>
        <source>勾选规则时只导出勾选的；未勾选时导出全部。MiteProxy 原生 .json 格式，启停状态与顺序一并保存。</source>
        <translation>When rules are checked, only the checked ones are exported; otherwise all are exported. MiteProxy&apos;s native .json format preserves enabled state and order.</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="137"/>
        <source>导入 MiteProxy 导出的 .json 规则文件（追加到现有规则之后，不覆盖已有规则）。要导 Fiddler 的 .farx 请用「导入 Fiddler 规则」按钮。</source>
        <translation>Import a .json rule file exported from MiteProxy (appended after existing rules; existing rules are not overwritten). For Fiddler&apos;s .farx, use the &quot;Import Fiddler rules&quot; button.</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="141"/>
        <source>删除当前选中的规则；首列勾选了多条时删除勾选的。</source>
        <translation>Deletes the currently selected rule; when multiple rows are checked in the first column, deletes the checked ones.</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="165"/>
        <source>搜索:</source>
        <translation>Search:</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="167"/>
        <source>URL / 名称</source>
        <translation>URL / name</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="171"/>
        <source>按 URL 匹配值或规则名称实时过滤（大小写不敏感）。
与「只显示启用」同时生效；清空恢复全部。</source>
        <translation>Filters by URL match value or rule name in real time (case-insensitive).
Combined with &quot;Only enabled&quot;; clear to restore all.</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="192"/>
        <source>序号</source>
        <translation>No.</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="193"/>
        <source>名称</source>
        <translation>Name</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="195"/>
        <source>匹配</source>
        <translation>Match</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="196"/>
        <source>动作</source>
        <translation>Action</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="197"/>
        <source>来源</source>
        <translation>Source</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="198"/>
        <source>命中</source>
        <translation>Hits</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="199"/>
        <source>创建时间</source>
        <translation>Created</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="239"/>
        <source>选择</source>
        <translation>Select</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="244"/>
        <source>全选 / 取消全选当前列表（含「只显示启用」过滤后的可见行）</source>
        <translation>Select / deselect all rows currently in the list (including visible rows after the &quot;enabled only&quot; filter)</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="339"/>
        <source>勾选后可对该规则批量启用/停用/删除/导出</source>
        <translation>Once checked, this rule can be batch enabled / disabled / deleted / exported</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="360"/>
        <source>勾选 = 启用；点击可切换启用 / 停用</source>
        <translation>Checked = enabled; click to toggle enabled / disabled</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="387"/>
        <source>没有匹配「{0}」的规则</source>
        <translation>No rules match &quot;{0}&quot;</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="390"/>
        <source>没有启用中的规则</source>
        <translation>No enabled rules</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="392"/>
        <source>暂无规则</source>
        <translation>No rules yet</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="401"/>
        <source>最近命中 {0}</source>
        <translation>Last hit {0}</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="449"/>
        <source>启用({0})</source>
        <translation>Enable ({0})</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="450"/>
        <source>停用({0})</source>
        <translation>Disable ({0})</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="451"/>
        <source>删除({0})</source>
        <translation>Delete ({0})</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="452"/>
        <source>导出({0})</source>
        <translation>Export ({0})</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="614"/>
        <source>置顶</source>
        <translation>Move to top</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="636"/>
        <source>已{0}「{1}」</source>
        <translation>{0} &quot;{1}&quot;</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="686"/>
        <source>已置顶「{0}」</source>
        <translation>Moved 「{0}」 to top</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="721"/>
        <location filename="../ui/rules_panel.py" line="732"/>
        <source>提示</source>
        <translation>Notice</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="721"/>
        <source>请先选择一条规则</source>
        <translation>Please select a rule first</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="732"/>
        <source>请先勾选规则（末尾复选框）</source>
        <translation>Please check rules first (checkbox in the last column)</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="741"/>
        <source>已将 {0} 条规则{1}</source>
        <translation>{0} rules {1}</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="743"/>
        <source>已启用</source>
        <translation>enabled</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="743"/>
        <source>已停用</source>
        <translation>disabled</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="802"/>
        <source>「{0}」</source>
        <translation>&quot;{0}&quot;</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="805"/>
        <source>{0} 条规则（{1}{2}）</source>
        <translation>{0} rules ({1}{2})</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="809"/>
        <source>确认删除</source>
        <translation>Confirm deletion</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="809"/>
        <source>确定删除{0}？</source>
        <translation>Delete {0}?</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="817"/>
        <source>已删除 {0} 条规则</source>
        <translation>Deleted {0} rules</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="824"/>
        <source>选择 Fiddler 规则文件</source>
        <translation>Select Fiddler rules file</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="827"/>
        <source>Fiddler 规则 (*.farx *.js);;FARX 规则包 (*.farx);;CustomRules.js (*.js);;所有文件 (*)</source>
        <translation>Fiddler rules (*.farx *.js);;FARX rule package (*.farx);;CustomRules.js (*.js);;All files (*)</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="839"/>
        <location filename="../ui/rules_panel.py" line="925"/>
        <source>导入失败</source>
        <translation>Import failed</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="846"/>
        <location filename="../ui/rules_panel.py" line="929"/>
        <location filename="../ui/rules_panel.py" line="938"/>
        <source>无可导入规则</source>
        <translation>No rules to import</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="847"/>
        <source>没有解析出可导入的规则。

{0}</source>
        <translation>No rules could be parsed.

{0}</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="848"/>
        <source>文件为空或格式不符</source>
        <translation>The file is empty or the format is invalid</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="865"/>
        <location filename="../ui/rules_panel.py" line="945"/>
        <source>导入完成</source>
        <translation>Import complete</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="866"/>
        <location filename="../ui/rules_panel.py" line="946"/>
        <source>成功导入 {0} 条规则</source>
        <translation>Successfully imported {0} rules</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="880"/>
        <source>勾选的 {0} 条</source>
        <translation>the {0} checked</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="883"/>
        <source>全部 {0} 条</source>
        <translation>all {0}</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="888"/>
        <location filename="../ui/rules_panel.py" line="917"/>
        <source>MiteProxy 规则 (*.json);;所有文件 (*)</source>
        <translation>MiteProxy rules (*.json);;All files (*)</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="907"/>
        <source>导出完成</source>
        <translation>Export complete</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="908"/>
        <source>已导出{0}规则到
{1}</source>
        <translation>Exported {0} rules to
{1}</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="925"/>
        <source>文件读取/解析失败：{0}</source>
        <translation>Failed to read or parse the file: {0}</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="929"/>
        <source>文件里没有规则数据。</source>
        <translation>The file contains no rule data.</translation>
    </message>
    <message>
        <location filename="../ui/rules_panel.py" line="938"/>
        <source>文件里的规则格式无法识别。</source>
        <translation>The rule format in the file is not recognized.</translation>
    </message>
</context>
<context>
    <name>SearchBar</name>
    <message>
        <location filename="../ui/traffic_table.py" line="120"/>
        <source>搜索 URL / Headers / Body …</source>
        <translation>Search URL / Headers / Body …</translation>
    </message>
    <message>
        <location filename="../ui/traffic_table.py" line="133"/>
        <source>区分大小写</source>
        <translation>Case sensitive</translation>
    </message>
    <message>
        <location filename="../ui/traffic_table.py" line="145"/>
        <source>在匹配项间跳转（Enter / Shift+Enter）</source>
        <translation>Jump between matches (Enter / Shift+Enter)</translation>
    </message>
    <message>
        <location filename="../ui/traffic_table.py" line="150"/>
        <source>关闭搜索（Esc）</source>
        <translation>Close search (Esc)</translation>
    </message>
    <message>
        <location filename="../ui/traffic_table.py" line="179"/>
        <source>匹配 {0} / {1} 条</source>
        <translation>Match {0} / {1}</translation>
    </message>
</context>
<context>
    <name>SettingsDialog</name>
    <message>
        <location filename="../ui/settings_dialog.py" line="58"/>
        <source>代理</source>
        <extracomment>设置页分类（左侧列表）。文案用 QT_TRANSLATE_NOOP 打标——翻译器在 QApplication 创建后才装载，import 期求值永远是中文（NetworkPanel 同款）； 构建列表时再 self.tr()。</extracomment>
        <translation>Proxy</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="59"/>
        <location filename="../ui/settings_dialog.py" line="180"/>
        <source>流量列表</source>
        <translation>Traffic List</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="60"/>
        <source>外观</source>
        <translation>Appearance</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="61"/>
        <source>会话</source>
        <translation>Sessions</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="62"/>
        <source>更新</source>
        <translation>Updates</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="79"/>
        <source>设置</source>
        <translation>Settings</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="121"/>
        <source>监听端口</source>
        <translation>Listening Ports</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="126"/>
        <source>代理端口:</source>
        <translation>Proxy port:</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="133"/>
        <source>HTTP/HTTPS 代理监听端口（默认 8888）
被占用时自动顺延到下一个可用端口；修改后重启代理生效</source>
        <translation>HTTP/HTTPS proxy listening port (default 8888)
If occupied, the next available port is used automatically; a change takes effect after restarting the proxy</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="141"/>
        <source>证书端口:</source>
        <translation>Certificate port:</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="148"/>
        <source>证书下载服务的监听端口（默认 8081，被占用时自动顺延）
证书服务运行中修改会立即用新端口重启</source>
        <translation>Listening port of the certificate download service (default 8081, next available port if occupied)
Changing it while the service runs restarts it on the new port immediately</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="156"/>
        <source>系统代理</source>
        <translation>System Proxy</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="158"/>
        <source>启动代理时设为系统代理</source>
        <translation>Set as system proxy when starting the proxy</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="161"/>
        <source>启动代理时自动把系统 HTTP/HTTPS 代理指向本应用，停止或退出时自动还原
（对齐 Fiddler「Act as System Proxy」）。
macOS 首次接管会请求一次管理员授权；不想自动改系统设置就取消勾选。</source>
        <translation>On proxy start, points the system HTTP/HTTPS proxy at this app automatically, and restores it on stop or quit
(matching Fiddler&apos;s &quot;Act as System Proxy&quot;).
macOS asks for admin authorization the first time it takes over; uncheck to avoid changing system settings.</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="167"/>
        <source>与工具栏「设为系统代理」实时联动：代理运行中修改会立即接管或还原。</source>
        <translation>Synced live with the toolbar&apos;s &quot;Set as system proxy&quot;; changing it while the proxy runs takes over or restores immediately.</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="185"/>
        <source>保存条数:</source>
        <translation>Max sessions:</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="188"/>
        <source>{0} 条</source>
        <translation>{0}</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="190"/>
        <source>流量列表最多保留的会话数，超出后从最旧一条开始丢弃（上限 5000）</source>
        <translation>Maximum sessions kept in the traffic list; beyond this the oldest are dropped (max 5000)</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="198"/>
        <source>自动滚动到最新会话</source>
        <translation>Auto-scroll to the newest session</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="201"/>
        <source>新会话到达时自动滚到最新一条。
你手动翻到别处时不会来抢滚动条——只有停在最新端才跟着走。</source>
        <translation>Scrolls to the newest session as new ones arrive.
It will not fight your manual scrolling — it only follows when you are already at the newest end.</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="206"/>
        <source>新的会话显示在顶部</source>
        <translation>Show newest sessions on top</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="209"/>
        <source>倒序 = 按到达序号降序，最新的会话排在最上面；
取消勾选 = 到达顺序，新的在底部</source>
        <translation>Reverse = sort by arrival number descending, newest session on top;
uncheck = arrival order, newest at the bottom</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="214"/>
        <source>Body 默认自动换行</source>
        <translation>Wrap Body by default</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="217"/>
        <source>请求/响应 Body 默认按窗口宽度换行；
超长单行会被闸门临时关掉，也可在详情页随时改</source>
        <translation>Request/response bodies wrap to the window width by default;
very long single lines are temporarily unwrapped by the gate, and you can toggle it in the detail pane anytime</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="223"/>
        <source>以上各项与工具栏对应控件实时联动，改完点「确定」立即生效。</source>
        <translation>These options stay in sync with the matching toolbar controls; click &quot;OK&quot; to apply immediately.</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="325"/>
        <source>主题与语言</source>
        <translation>Theme &amp; Language</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="330"/>
        <source>主题:</source>
        <translation>Theme:</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="333"/>
        <source>跟随系统</source>
        <translation>Follow system</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="334"/>
        <source>浅色模式</source>
        <translation>Light mode</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="335"/>
        <source>深色模式</source>
        <translation>Dark mode</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="341"/>
        <source>切换后立即生效，下次启动保持</source>
        <translation>Applied immediately and kept on next launch</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="347"/>
        <source>语言:</source>
        <translation>Language:</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="353"/>
        <source>切换后重启 MiteProxy 生效</source>
        <translation>Takes effect after restarting MiteProxy</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="359"/>
        <source>主题切换立即生效；语言需要重启应用（翻译器在启动时装载）。</source>
        <translation>Theme changes apply immediately; language changes require an app restart (the translator loads at startup).</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="372"/>
        <source>会话快照</source>
        <translation>Session Snapshot</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="375"/>
        <source>退出时自动保存会话</source>
        <translation>Auto-save session on quit</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="378"/>
        <source>退出时把本次会话快照到磁盘，下次启动可一键恢复。
会话始终在内存，只有退出时才落盘，不影响抓包性能。</source>
        <translation>Snapshot this session to disk on quit for one-click restore next launch.
Sessions always live in memory and are only written on quit, so capture performance is unaffected.</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="384"/>
        <source>与「文件 → 退出时自动保存会话」是同一开关。</source>
        <translation>This is the same switch as &quot;File → Auto-save session on quit&quot;.</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="389"/>
        <source>配置目录</source>
        <translation>Config Directory</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="396"/>
        <source>打开</source>
        <translation>Open</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="397"/>
        <source>在文件管理器中打开配置目录</source>
        <translation>Open the config directory in the file manager</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="402"/>
        <source>settings.json（本机设置）、rules.json（Mock 规则）、
证书与日志都在这里；删 settings.json 可恢复全部默认设置。</source>
        <translation>settings.json (local settings), rules.json (Mock rules),
certificates and logs all live here; deleting settings.json restores all defaults.</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="416"/>
        <source>自动更新</source>
        <translation>Updates</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="419"/>
        <source>启动时检查更新</source>
        <translation>Check for updates on startup</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="422"/>
        <source>启动后静默检查新版本，只有确实有新版才弹窗；
网络不通一律静默，不影响抓包主流程。手动检查不受此项影响。</source>
        <translation>Silently check for a new version after launch; a dialog appears only when one exists.
No network = no interruption of the capture flow. Manual checks are unaffected.</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="428"/>
        <source>手动检查：菜单「帮助 → 检查更新…」。</source>
        <translation>Manual check: menu &quot;Help → Check for Updates…&quot;.</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="527"/>
        <source>无法打开配置目录</source>
        <translation>Cannot Open Config Directory</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="528"/>
        <source>请手动前往：
{0}</source>
        <translation>Please navigate manually:
{0}</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="229"/>
        <source>断点调试</source>
        <translation>Breakpoints</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="233"/>
        <source>请求发出前暂停</source>
        <translation>Pause before the request is sent</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="236"/>
        <source>挂起后可改 URL / Header / Body，再放行发往服务器</source>
        <translation>While held you can edit URL / headers / body, then release it to the server</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="238"/>
        <source>响应返回前暂停</source>
        <translation>Pause before the response is returned</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="241"/>
        <source>挂起后可改状态码 / Header / Body，再放行返回给客户端</source>
        <translation>While held you can edit status code / headers / body, then release it to the client</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="247"/>
        <source>URL 关键词:</source>
        <translation>URL keywords:</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="250"/>
        <source>逗号分隔；留空 = 拦截全部</source>
        <translation>Comma separated; empty = intercept everything</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="256"/>
        <source>总开关在工具栏的「断点」按钮上：开启后命中会话会挂起，改完点「继续放行」。</source>
        <translation>The master switch is the &quot;Breakpoint&quot; button on the toolbar: once enabled, matched sessions are held until you release them.</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="262"/>
        <source>MCP 接口</source>
        <translation>MCP interface</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="267"/>
        <source>监听地址:</source>
        <translation>Bind address:</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="274"/>
        <source>仅本机（127.0.0.1）</source>
        <translation>Local machine only (127.0.0.1)</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="275"/>
        <source>局域网：全部网卡（0.0.0.0）</source>
        <translation>LAN: all interfaces (0.0.0.0)</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="279"/>
        <source>局域网：{0}</source>
        <translation>LAN: {0}</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="281"/>
        <source>MCP 服务绑定哪个网卡。
仅本机 = 只有这台机器能调；改成局域网后，同网段设备（含手机、
另一台电脑上的 AI 客户端）都能读到完整抓包——含 Cookie / 鉴权头。
也可直接填某个网卡 IP，只允许经该网卡访问。</source>
        <translation>Which interface the MCP server binds to.
Local only = callable from this machine; switching to LAN lets any device on the same network (phone, another PC&apos;s AI client) read the full capture — cookies and auth headers included.
You may also type a specific NIC IP to allow access through that interface only.</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="291"/>
        <source>端口:</source>
        <translation>Port:</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="296"/>
        <source>被占用时会向上顺延，实际端口看启动后的状态栏提示。</source>
        <translation>If the port is taken it moves up; the status bar shows the actual port after start.</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="497"/>
        <source>警告：当前地址对局域网开放，同网段任何人都能读到完整抓包（含 Cookie / 鉴权头）。用完记得关掉工具栏的「MCP」按钮。</source>
        <translation>Warning: this address is exposed to the LAN — anyone on the same network can read the full capture (cookies and auth headers included). Turn the toolbar &quot;MCP&quot; button off when you&apos;re done.</translation>
    </message>
    <message>
        <location filename="../ui/settings_dialog.py" line="503"/>
        <source>总开关在工具栏的「MCP」按钮上，默认关。改完点「确定」立即生效（MCP 正在运行时会自动重启）。</source>
        <translation>The master switch is the &quot;MCP&quot; button on the toolbar; it is off by default. Changes apply on OK (the server restarts automatically if it is running).</translation>
    </message>
</context>
<context>
    <name>StatsPanel</name>
    <message>
        <location filename="../ui/stats_panel.py" line="41"/>
        <source>统计范围 = 当前流量列表中的会话（删除过的行不计入），不受顶部过滤栏影响；
耗时与「耗时」列同口径（含弱网延迟），尚未返回响应的会话其耗时会持续增长。
双击慢请求可跳到流量列表对应行。</source>
        <translation>Scope = the sessions currently in the traffic list (deleted rows excluded); the filter bar does not apply.
Duration uses the same definition as the &quot;Duration&quot; column (throttle delay included); sessions still awaiting a response keep growing.
Double-click a slow request to jump to its row in the traffic list.</translation>
    </message>
    <message>
        <location filename="../ui/stats_panel.py" line="49"/>
        <source>{0} – {1}  {2} 条 · 下载 {3}</source>
        <extracomment>直方图悬停提示（静态方法里没有 self.tr，走 NOOP + 运行时 translate）</extracomment>
        <translation>{0} – {1}  {2} sessions · downloaded {3}</translation>
    </message>
    <message>
        <location filename="../ui/stats_panel.py" line="233"/>
        <source>总会话</source>
        <extracomment>双击慢请求行 → 主窗口跳到流量列表对应行（传 flow id）</extracomment>
        <translation>Total</translation>
    </message>
    <message>
        <location filename="../ui/stats_panel.py" line="234"/>
        <location filename="../ui/stats_panel.py" line="264"/>
        <source>错误率</source>
        <translation>Error rate</translation>
    </message>
    <message>
        <location filename="../ui/stats_panel.py" line="235"/>
        <location filename="../ui/stats_panel.py" line="264"/>
        <source>平均耗时</source>
        <translation>Avg duration</translation>
    </message>
    <message>
        <location filename="../ui/stats_panel.py" line="236"/>
        <source>P95 耗时</source>
        <translation>P95 duration</translation>
    </message>
    <message>
        <location filename="../ui/stats_panel.py" line="237"/>
        <source>下载总量</source>
        <translation>Downloaded</translation>
    </message>
    <message>
        <location filename="../ui/stats_panel.py" line="238"/>
        <source>请求速率</source>
        <translation>Rate</translation>
    </message>
    <message>
        <location filename="../ui/stats_panel.py" line="259"/>
        <source>按域名（请求数排序）</source>
        <translation>By host (by request count)</translation>
    </message>
    <message>
        <location filename="../ui/stats_panel.py" line="263"/>
        <source>域名</source>
        <translation>Host</translation>
    </message>
    <message>
        <location filename="../ui/stats_panel.py" line="263"/>
        <source>请求数</source>
        <translation>Requests</translation>
    </message>
    <message>
        <location filename="../ui/stats_panel.py" line="263"/>
        <source>错误</source>
        <translation>Errors</translation>
    </message>
    <message>
        <location filename="../ui/stats_panel.py" line="264"/>
        <source>最大耗时</source>
        <translation>Max duration</translation>
    </message>
    <message>
        <location filename="../ui/stats_panel.py" line="265"/>
        <source>下载</source>
        <translation>Download</translation>
    </message>
    <message>
        <location filename="../ui/stats_panel.py" line="268"/>
        <source>耗时单位 ms；「下载」为该域名的响应体总量。
只显示前 {0} 个域名（按请求数降序）。</source>
        <translation>Durations in ms; &quot;Download&quot; is the host&apos;s total response body size.
Only the top {0} hosts are shown (by request count, descending).</translation>
    </message>
    <message>
        <location filename="../ui/stats_panel.py" line="275"/>
        <source>按状态码（次数排序）</source>
        <translation>By status (by count)</translation>
    </message>
    <message>
        <location filename="../ui/stats_panel.py" line="279"/>
        <source>状态码</source>
        <translation>Status code</translation>
    </message>
    <message>
        <location filename="../ui/stats_panel.py" line="279"/>
        <location filename="../ui/stats_panel.py" line="289"/>
        <source>次数</source>
        <translation>Count</translation>
    </message>
    <message>
        <location filename="../ui/stats_panel.py" line="279"/>
        <location filename="../ui/stats_panel.py" line="289"/>
        <source>占比</source>
        <translation>Share</translation>
    </message>
    <message>
        <location filename="../ui/stats_panel.py" line="285"/>
        <source>按方法（次数排序）</source>
        <translation>By method (by count)</translation>
    </message>
    <message>
        <location filename="../ui/stats_panel.py" line="289"/>
        <location filename="../ui/stats_panel.py" line="300"/>
        <source>方法</source>
        <translation>Method</translation>
    </message>
    <message>
        <location filename="../ui/stats_panel.py" line="295"/>
        <source>慢请求 Top N（双击跳到对应会话）</source>
        <translation>Slowest requests Top N (double-click to jump to the session)</translation>
    </message>
    <message>
        <location filename="../ui/stats_panel.py" line="300"/>
        <source>耗时(ms)</source>
        <translation>Duration (ms)</translation>
    </message>
    <message>
        <location filename="../ui/stats_panel.py" line="300"/>
        <source>状态</source>
        <translation>Status</translation>
    </message>
    <message>
        <location filename="../ui/stats_panel.py" line="301"/>
        <source>URL</source>
        <translation>URL</translation>
    </message>
    <message>
        <location filename="../ui/stats_panel.py" line="301"/>
        <source>大小</source>
        <translation>Size</translation>
    </message>
    <message>
        <location filename="../ui/stats_panel.py" line="309"/>
        <source>时间分布（按请求开始时间分桶）</source>
        <translation>Time distribution (bucketed by request start)</translation>
    </message>
    <message>
        <location filename="../ui/stats_panel.py" line="354"/>
        <source>WebSocket {0} · 重放 {1}</source>
        <translation>WebSocket {0} · Replay {1}</translation>
    </message>
    <message>
        <location filename="../ui/stats_panel.py" line="359"/>
        <source>{0} / {1} 条（4xx/5xx）</source>
        <translation>{0} / {1} sessions (4xx/5xx)</translation>
    </message>
    <message>
        <location filename="../ui/stats_panel.py" line="361"/>
        <source>暂无会话</source>
        <translation>No sessions yet</translation>
    </message>
    <message>
        <location filename="../ui/stats_panel.py" line="364"/>
        <source>最大 {0} ms</source>
        <translation>Max {0} ms</translation>
    </message>
    <message>
        <location filename="../ui/stats_panel.py" line="366"/>
        <source>95% 的请求快于此线</source>
        <translation>95% of requests are faster than this</translation>
    </message>
    <message>
        <location filename="../ui/stats_panel.py" line="368"/>
        <source>上传 {0}</source>
        <translation>Upload {0}</translation>
    </message>
    <message>
        <location filename="../ui/stats_panel.py" line="372"/>
        <source>{0} 条/秒</source>
        <translation>{0} sessions/s</translation>
    </message>
    <message>
        <location filename="../ui/stats_panel.py" line="373"/>
        <location filename="../ui/stats_panel.py" line="375"/>
        <source>时间跨度 {0} 秒</source>
        <translation>Span {0} s</translation>
    </message>
    <message>
        <location filename="../ui/stats_panel.py" line="379"/>
        <source>{0} 条会话尚未返回响应，其耗时与大小会持续增长。</source>
        <translation>{0} sessions have no response yet; their duration and size keep growing.</translation>
    </message>
    <message>
        <location filename="../ui/stats_panel.py" line="434"/>
        <location filename="../ui/stats_panel.py" line="485"/>
        <source>无响应</source>
        <translation>No response</translation>
    </message>
    <message>
        <location filename="../ui/stats_panel.py" line="508"/>
        <source>时间分布（按请求开始时间分桶，跨度 {0} 秒）</source>
        <translation>Time distribution (bucketed by request start, span {0} s)</translation>
    </message>
    <message>
        <location filename="../ui/stats_panel.py" line="515"/>
        <source>暂无数据（开始抓包后自动统计）</source>
        <translation>No data yet (stats appear once capturing starts)</translation>
    </message>
</context>
<context>
    <name>TimingsPane</name>
    <message>
        <location filename="../ui/detail_panel.py" line="1364"/>
        <source>连接服务器（含 DNS）</source>
        <extracomment>分段耗时 key → 展示名。模块级中文一律打 QT_TRANSLATE_NOOP 标（AST 守卫 + lupdate 抽取，运行时走 translate，见 rule_editor 同款教训）</extracomment>
        <translation>Connect (incl. DNS)</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="1365"/>
        <source>TLS 握手</source>
        <translation>TLS handshake</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="1366"/>
        <source>发送请求</source>
        <translation>Send request</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="1367"/>
        <source>等待响应（TTFB）</source>
        <translation>Waiting for response (TTFB)</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="1368"/>
        <source>接收响应</source>
        <translation>Receive response</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="1506"/>
        <source>总耗时 {0} ms</source>
        <translation>Total {0} ms</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="1509"/>
        <source>（含弱网延迟 {0} ms）</source>
        <translation>(incl. {0} ms throttled delay)</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="1578"/>
        <source>暂无计时数据</source>
        <translation>No timing data</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="1582"/>
        <source>该响应未经上游网络（mock / 本地映射 / 恢复的会话），仅统计本机处理耗时。</source>
        <translation>This response never went to the upstream network (mock / local mapping / restored session); only local processing time is counted.</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="1594"/>
        <source>响应尚未返回，「等待响应 / 接收响应」暂缺。</source>
        <translation>The response has not arrived yet; &quot;waiting&quot; and &quot;receive&quot; phases are missing.</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="1609"/>
        <source>未选择会话</source>
        <translation>No session selected</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="1464"/>
        <source>阶段</source>
        <extracomment>行内列宽（表头与数据行必须同值，否则列会错位）。 名称列保持 180：英文分段名（Waiting for response (TTFB)）比中文长， 压窄会在英文界面被截断——宁可让占比条窄一点。</extracomment>
        <translation>Phase</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="1465"/>
        <source>开始时刻</source>
        <translation>Start time</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="1466"/>
        <source>耗时</source>
        <translation>Duration</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="1474"/>
        <source>占比</source>
        <translation>Share</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="1546"/>
        <source>起点 {0}  →  终点 {1}（时段跨度 {2} ms）</source>
        <translation>Start {0}  →  end {1} (span {2} ms)</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="1551"/>
        <source>起点 {0}</source>
        <translation>Start {0}</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="1599"/>
        <source>起点到终点共 {0} ms，其中 {1} ms 不属于上述任何分段（如 TLS 完成后等待客户端真正发送请求、本机处理等间隙）。</source>
        <translation>Start to end spans {0} ms; {1} ms of it belongs to none of the phases above (e.g. waiting after the TLS handshake for the client to actually send the request, local processing).</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="1701"/>
        <source>开始：{0}</source>
        <translation>Start: {0}</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="1703"/>
        <source>结束：{0}</source>
        <translation>End: {0}</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="1707"/>
        <source>相对起点：{0} ms</source>
        <translation>From start: {0} ms</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="1520"/>
        <source>请求耗时（列表「耗时」列）: {0} ms</source>
        <translation>Request time (traffic list &quot;Duration&quot; column): {0} ms</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="1522"/>
        <source>，另含建连与 TLS {0} ms</source>
        <translation>; connection setup and TLS add {0} ms</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="1589"/>
        <source>总耗时含建连与 TLS 握手（一次连接只付一次的沉没成本）；列表「耗时」列只统计「发送请求 → 响应结束」，与 Fiddler 的会话计时口径一致。</source>
        <translation>Total includes connection setup and the TLS handshake (a one-off cost per connection); the traffic list&apos;s &quot;Duration&quot; column only counts &quot;send request → response end&quot;, matching Fiddler&apos;s session timing.</translation>
    </message>
</context>
<context>
    <name>ToolPanel</name>
    <message>
        <location filename="../ui/tool_panel.py" line="32"/>
        <source>编码转换</source>
        <translation>Encoding converter</translation>
    </message>
    <message>
        <location filename="../ui/tool_panel.py" line="34"/>
        <source>JSON 比对</source>
        <translation>JSON compare</translation>
    </message>
    <message>
        <location filename="../ui/tool_panel.py" line="35"/>
        <source>API 调试</source>
        <translation>API debugger</translation>
    </message>
</context>
<context>
    <name>UpdateChecker</name>
    <message>
        <location filename="../updater.py" line="239"/>
        <source>version.info 格式无法解析</source>
        <extracomment>仓库与版本信息文件地址（raw 直读，无需 token / 不受 API 限流） 兜底的下载地址：version.info 没给 download_url 时跳 Release 首页 当前版本。来源唯一：app.feedback.APP_VERSION（形如 &quot;v2.0.0&quot;），这里去掉 v 前缀。 单次检测的网络超时（毫秒）</extracomment>
        <translation>Could not parse version.info</translation>
    </message>
    <message>
        <location filename="../updater.py" line="247"/>
        <source>请求超时</source>
        <translation>Request timed out</translation>
    </message>
</context>
<context>
    <name>UpdateDialog</name>
    <message>
        <location filename="../ui/update_dialog.py" line="34"/>
        <source>发现新版本</source>
        <translation>New version available</translation>
    </message>
    <message>
        <location filename="../ui/update_dialog.py" line="46"/>
        <source>新版本 {0} 已发布（当前 {1}）</source>
        <translation>Version {0} is now available (current: {1})</translation>
    </message>
    <message>
        <location filename="../ui/update_dialog.py" line="56"/>
        <source>发布日期：{0}</source>
        <translation>Released: {0}</translation>
    </message>
    <message>
        <location filename="../ui/update_dialog.py" line="60"/>
        <source>本次更新内容：</source>
        <translation>What&apos;s new:</translation>
    </message>
    <message>
        <location filename="../ui/update_dialog.py" line="70"/>
        <source>（该版本未提供变更说明）</source>
        <translation>(No changelog provided for this version)</translation>
    </message>
    <message>
        <location filename="../ui/update_dialog.py" line="75"/>
        <source>前往下载</source>
        <translation>Go to download</translation>
    </message>
    <message>
        <location filename="../ui/update_dialog.py" line="79"/>
        <source>关闭</source>
        <translation>Close</translation>
    </message>
</context>
<context>
    <name>WebSocketPane</name>
    <message>
        <location filename="../ui/detail_panel.py" line="1162"/>
        <source>时间</source>
        <translation>Time</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="1162"/>
        <source>方向</source>
        <translation>Direction</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="1162"/>
        <source>类型</source>
        <translation>Type</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="1162"/>
        <source>长度</source>
        <translation>Length</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="1162"/>
        <source>内容预览</source>
        <translation>Content preview</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="1259"/>
        <source>文本</source>
        <translation>Text</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="1259"/>
        <source>二进制</source>
        <translation>Binary</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="1269"/>
        <source>→ 发送</source>
        <translation>→ sent</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="1269"/>
        <source>← 接收</source>
        <translation>← received</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="1295"/>
        <source>共 {0} 条消息（发送 {1} / 接收 {2}）</source>
        <translation>{0} messages in total (sent {1} / received {2})</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="1298"/>
        <source>已关闭：code={0} {1}</source>
        <translation>Closed: code={0} {1}</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="1304"/>
        <source>连接中…</source>
        <translation>Connecting…</translation>
    </message>
    <message>
        <location filename="../ui/detail_panel.py" line="1306"/>
        <source>（表格仅显示最近 {0} 条）</source>
        <translation>(the table shows only the most recent {0})</translation>
    </message>
</context>
<context>
    <name>_clear_local_proxy</name>
    <message>
        <source>无接管记录</source>
        <translation type="obsolete">No takeover record</translation>
    </message>
</context>
<context>
    <name>bodyview</name>
    <message>
        <location filename="../bodyview.py" line="84"/>
        <source>自动</source>
        <extracomment>原文 / 十六进制视图的输入截断（超过就截断显示，与搜索索引策略一致） 十六进制视图的渲染上限 JSON 格式化输入上限：json.loads/dumps 是线性开销（8MB 约 60ms），便宜， 所以给得宽松，覆盖 4-5MB 的常见大响应体；真正要卡住的是渲染，见下面 RENDER_TEXT_LIMIT / detail_panel 的流式追加。 首屏渲染上限：一次性塞进 QPlainTextEdit 的第一块（1MB ≈ 25ms）。超过 这个长度的文本由 detail_panel 走流式追加（首屏快显 + QTimer 分块喂入）， 切换不卡也能看全——一次性 setPlainText(5MB) 要 120ms+，且 QPlainTextEdit 为每个 block 建 layout，20 万行的首屏排版就是切换卡顿的元凶。 流式追加的块大小：块间让事件循环跑，界面保持可响应/可滚动。 流式追加的绝对上限：超过就真截断（附「已截断」提示）。QPlainTextEdit 文档内存约 3-4 倍文本膨胀，16MB 文本 ≈ 60MB+ 内存，是调试场景的天花板。 注意 JSON_PARSE_LIMIT 内仍可能撑到它：紧凑数组 `[1,1,...]` pretty 后 每个元素膨胀约 2.5 倍（8MB body → 20MB pretty）。 语法着色上限：QSyntaxHighlighter 按 block 走，2 万行约 260ms。 超过就暂停着色——丢了颜色但界面不卡，取舍很清楚。 换行闸门：单行超过这个长度就不换行。实测 100KB 单行换行 160ms、 300KB 单行换行 1.2s（超线性增长），而多行文本换行几乎免费。 换行判定只扫描前这么多字符：换行只需知道&quot;有没有超长单行&quot;，不必精读全篇。 对大文本（几 MB）全文 split(&quot;
&quot;) 会物化几十万临时字符串，是切换卡顿的 主因（setPlainText 2MB 才 ~50ms，反倒这个扫描更贵）；限定窗口后开销恒定， 256KB 覆盖多个闸门行，足以判定 JSON(多行短行)/base64(单行在开头) 两类。 视图模式 → 显示名。**NOOP 打标、禁止在这里 translate**： 本模块经 detail_panel 被 main_window 在 import 期带入（app/main.py 顶部 `from app.ui.main_window import MainWindow` 早于 main() 里的 load_language）， 模块级 translate 在翻译器装载前求值，英文模式下会永久烤成中文。 翻译一律推迟到 view_mode_items() / view_mode_label() 运行时做。</extracomment>
        <translation>Auto</translation>
    </message>
    <message>
        <location filename="../bodyview.py" line="85"/>
        <source>原文</source>
        <translation>Raw</translation>
    </message>
    <message>
        <location filename="../bodyview.py" line="88"/>
        <source>表单</source>
        <translation>Form</translation>
    </message>
    <message>
        <location filename="../bodyview.py" line="89"/>
        <source>图片</source>
        <translation>Image</translation>
    </message>
    <message>
        <location filename="../bodyview.py" line="90"/>
        <source>十六进制</source>
        <translation>Hex</translation>
    </message>
    <message>
        <location filename="../bodyview.py" line="159"/>
        <source>嵌套层级过深，超出解析器递归上限</source>
        <extracomment>认定为表单的 content-type（只认这一个，不猜） 可预览的图片类型（svg 走矢量渲染，见 app/ui/detail_panel.ImageView）</extracomment>
        <translation>Nesting too deep; exceeds the parser&apos;s recursion limit</translation>
    </message>
    <message>
        <location filename="../bodyview.py" line="165"/>
        <source>序列化失败：{0}</source>
        <translation>Serialization failed: {0}</translation>
    </message>
    <message>
        <location filename="../bodyview.py" line="243"/>
        <source>内容 {0:.1f}MB 超出格式化上限 {1}MB，已显示原文</source>
        <extracomment>渲染文本是否被截断（格式化成功但太长）</extracomment>
        <translation>Content of {0:.1f}MB exceeds the formatting limit of {1}MB; showing raw text</translation>
    </message>
    <message>
        <location filename="../bodyview.py" line="251"/>
        <source>无法按文本解码</source>
        <translation>Cannot decode as text</translation>
    </message>
    <message>
        <location filename="../bodyview.py" line="255"/>
        <source>JSON 解析失败，已显示原文：{0}</source>
        <translation>JSON parsing failed; showing raw text: {0}</translation>
    </message>
    <message>
        <location filename="../bodyview.py" line="289"/>
        <source>单行最长 {0}KB 超过 {1}KB，已临时关闭换行（换行会让界面卡顿）</source>
        <translation>Longest single line {0}KB exceeds {1}KB; wrapping temporarily disabled (wrapping makes the UI laggy)</translation>
    </message>
    <message>
        <location filename="../bodyview.py" line="358"/>
        <source>手动解压</source>
        <translation>Manually decompressed</translation>
    </message>
    <message>
        <location filename="../bodyview.py" line="358"/>
        <source>已解压</source>
        <translation>Decompressed</translation>
    </message>
    <message>
        <location filename="../bodyview.py" line="359"/>
        <source>{0} {1}：线上 {2:.1f}KB → {3:.1f}KB</source>
        <translation>{0} {1}: on the wire {2:.1f}KB → {3:.1f}KB</translation>
    </message>
    <message>
        <location filename="../bodyview.py" line="399"/>
        <source>[二进制内容 · 十六进制视图]
</source>
        <translation>[Binary content · hex view]
</translation>
    </message>
    <message>
        <location filename="../bodyview.py" line="402"/>
        <source>
…… [十六进制视图仅显示前 {0}KB，完整大小 {1}KB]</source>
        <translation>
…… [hex view shows only the first {0}KB; full size {1}KB]</translation>
    </message>
    <message>
        <location filename="../bodyview.py" line="408"/>
        <source>

…… [已截断：仅显示前 {0}KB，完整大小 {1}KB]</source>
        <translation>

…… [truncated: showing only the first {0}KB; full size {1}KB]</translation>
    </message>
    <message>
        <location filename="../bodyview.py" line="87"/>
        <source>树</source>
        <translation>Tree</translation>
    </message>
</context>
<context>
    <name>dumps_json</name>
    <message>
        <source>序列化失败：{0}</source>
        <translation type="obsolete">Serialization failed: {0}</translation>
    </message>
</context>
<context>
    <name>export</name>
    <message>
        <location filename="../export.py" line="37"/>
        <source>HAR 归档 (*.har)</source>
        <extracomment>这些格式必须有响应才有内容可导出（UI 层据此给出友好提示） NOOP 打标：同 bodyview.VIEW_MODE_ITEMS，本模块在翻译器装载前被 import， 模块级 translate 只会拿到中文。展示走 format_label() 运行时翻译。</extracomment>
        <translation>HAR archive (*.har)</translation>
    </message>
    <message>
        <location filename="../export.py" line="38"/>
        <source>原始 HTTP 报文：请求+响应 (*.txt)</source>
        <translation>Raw HTTP messages: request+response (*.txt)</translation>
    </message>
    <message>
        <location filename="../export.py" line="39"/>
        <source>完整响应：Headers+Body (*.txt)</source>
        <translation>Full response: Headers+Body (*.txt)</translation>
    </message>
    <message>
        <location filename="../export.py" line="40"/>
        <source>仅响应 Body (*.*)</source>
        <translation>Response body only (*.*)</translation>
    </message>
    <message>
        <location filename="../export.py" line="98"/>
        <source>########## 会话 {0}/{1} · {2} ##########</source>
        <extracomment>多选导出时不允许的格式（一个文件装不下多份裸 body）</extracomment>
        <translation>########## Session {0}/{1} · {2} ##########</translation>
    </message>
    <message>
        <location filename="../export.py" line="225"/>
        <source>{0} 会话 {1}/{2} · {3}</source>
        <translation>{0} sessions {1}/{2} · {3}</translation>
    </message>
    <message>
        <location filename="../export.py" line="247"/>
        <source>&lt;二进制 body：{0} 字节，未内联；请用「仅响应 Body」导出&gt;</source>
        <translation>&lt;binary body: {0} bytes, not inlined; use &quot;Response body only&quot; export&gt;</translation>
    </message>
    <message>
        <location filename="../export.py" line="300"/>
        <source>===== 请求 =====</source>
        <translation>===== Request =====</translation>
    </message>
    <message>
        <location filename="../export.py" line="301"/>
        <source>===== 响应 =====</source>
        <translation>===== Response =====</translation>
    </message>
    <message>
        <location filename="../export.py" line="581"/>
        <source>_{0}条</source>
        <translation>_{0}</translation>
    </message>
    <message>
        <location filename="../export.py" line="644"/>
        <source>「仅响应 Body」只支持导出单条会话</source>
        <translation>&quot;Response body only&quot; supports exporting a single session</translation>
    </message>
    <message>
        <location filename="../export.py" line="646"/>
        <source>未知导出格式: {0}</source>
        <translation>Unknown export format: {0}</translation>
    </message>
</context>
<context>
    <name>feedback</name>
    <message>
        <location filename="../feedback.py" line="132"/>
        <source>网络请求失败：{0}。请检查网络后重试。</source>
        <extracomment>版本号单一事实源在 app/version.py 的 __version__，这里统一加 &quot;v&quot; 前缀。</extracomment>
        <translation>Network request failed: {0}. Please check your network and try again.</translation>
    </message>
    <message>
        <location filename="../feedback.py" line="134"/>
        <source>无法连接 GitHub</source>
        <translation>Could not connect to GitHub</translation>
    </message>
    <message>
        <location filename="../feedback.py" line="136"/>
        <source>提交失败：反馈凭证无效（token 已过期或被撤销）。</source>
        <translation>Submission failed: the feedback credential is invalid (the token has expired or been revoked).</translation>
    </message>
    <message>
        <location filename="../feedback.py" line="139"/>
        <source>提交失败：GitHub 接口限流，请稍后再试。</source>
        <translation>Submission failed: GitHub API rate limit reached. Please try again later.</translation>
    </message>
    <message>
        <location filename="../feedback.py" line="140"/>
        <source>提交失败：没有创建 issue 的权限（token 权限不足）。</source>
        <translation>Submission failed: no permission to create issues (insufficient token scope).</translation>
    </message>
    <message>
        <location filename="../feedback.py" line="142"/>
        <source>提交失败：仓库不存在或 token 未授权该仓库。</source>
        <translation>Submission failed: the repository does not exist or the token is not authorized for it.</translation>
    </message>
    <message>
        <location filename="../feedback.py" line="144"/>
        <source>提交失败：内容未通过 GitHub 校验（标题或正文可能过长）。</source>
        <translation>Submission failed: the content failed GitHub validation (the title or body may be too long).</translation>
    </message>
    <message>
        <location filename="../feedback.py" line="146"/>
        <source>提交失败：GitHub 服务暂时不可用（HTTP {0}），请稍后再试。</source>
        <translation>Submission failed: GitHub is temporarily unavailable (HTTP {0}). Please try again later.</translation>
    </message>
    <message>
        <location filename="../feedback.py" line="147"/>
        <source>提交失败：HTTP {0} {1}</source>
        <translation>Submission failed: HTTP {0} {1}</translation>
    </message>
    <message>
        <location filename="../feedback.py" line="159"/>
        <source>反馈已提交，感谢！</source>
        <translation>Feedback submitted. Thank you!</translation>
    </message>
</context>
<context>
    <name>format_diff_report</name>
    <message>
        <source>两个 JSON 完全一致</source>
        <translation type="obsolete">The two JSON documents are identical</translation>
    </message>
</context>
<context>
    <name>httpclient</name>
    <message>
        <location filename="../httpclient.py" line="61"/>
        <source>URL 不能为空</source>
        <extracomment>响应体读取上限：调试工具不是下载器，500MB 兜底防把内存吃光 线上原始（压缩后）字节数；body 已解压，用于「已解压」提示</extracomment>
        <translation>The URL cannot be empty</translation>
    </message>
    <message>
        <location filename="../httpclient.py" line="64"/>
        <source>URL 必须以 http:// 或 https:// 开头</source>
        <translation>The URL must start with http:// or https://</translation>
    </message>
    <message>
        <location filename="../httpclient.py" line="67"/>
        <source>URL 缺少主机名</source>
        <translation>The URL is missing a hostname</translation>
    </message>
    <message>
        <location filename="../httpclient.py" line="97"/>
        <source>响应体超过 {0}MB 上限</source>
        <translation>Response body exceeds the {0}MB limit</translation>
    </message>
    <message>
        <location filename="../httpclient.py" line="121"/>
        <source>连接失败: {0}</source>
        <translation>Connection failed: {0}</translation>
    </message>
    <message>
        <location filename="../httpclient.py" line="123"/>
        <source>请求失败: {0}</source>
        <translation>Request failed: {0}</translation>
    </message>
</context>
<context>
    <name>import_dialog</name>
    <message>
        <location filename="../ui/import_dialog.py" line="33"/>
        <source>手动</source>
        <translation>Manual</translation>
    </message>
    <message>
        <location filename="../ui/import_dialog.py" line="39"/>
        <source>精确</source>
        <translation>Exact</translation>
    </message>
    <message>
        <location filename="../ui/import_dialog.py" line="40"/>
        <source>包含</source>
        <translation>Contains</translation>
    </message>
    <message>
        <location filename="../ui/import_dialog.py" line="41"/>
        <source>通配</source>
        <translation>Wildcard</translation>
    </message>
    <message>
        <location filename="../ui/import_dialog.py" line="42"/>
        <source>正则</source>
        <translation>Regex</translation>
    </message>
    <message>
        <location filename="../ui/import_dialog.py" line="48"/>
        <source>[{0}·{1}] {2}</source>
        <translation>[{0}·{1}] {2}</translation>
    </message>
    <message>
        <location filename="../ui/import_dialog.py" line="51"/>
        <source>[{0}] {1}</source>
        <translation>[{0}] {1}</translation>
    </message>
    <message>
        <location filename="../ui/import_dialog.py" line="58"/>
        <source>重定向→{0}</source>
        <translation>Redirect→{0}</translation>
    </message>
    <message>
        <location filename="../ui/import_dialog.py" line="60"/>
        <location filename="../ui/import_dialog.py" line="64"/>
        <source>延迟{0}ms</source>
        <translation>Delay {0}ms</translation>
    </message>
    <message>
        <location filename="../ui/import_dialog.py" line="66"/>
        <source>文件:{0}</source>
        <translation>File: {0}</translation>
    </message>
    <message>
        <location filename="../ui/import_dialog.py" line="71"/>
        <source>{0}个header</source>
        <translation>{0} headers</translation>
    </message>
</context>
<context>
    <name>jsondiff</name>
    <message>
        <location filename="../jsondiff.py" line="96"/>
        <source>…（共 {0} 字符）</source>
        <extracomment>节点数上限（两棵树合计）：超出即停，防超大 JSON 卡死界面 差异条目上限：防「整个数组全变」时报告爆炸 「只在一边存在」的哨兵：与任何 JSON 值（含 None）都不会相等 True = 因超限提前停止，entries 不完整</extracomment>
        <translation>… ({0} chars in total)</translation>
    </message>
    <message>
        <location filename="../jsondiff.py" line="202"/>
        <source>两个 JSON 完全一致</source>
        <translation>The two JSON documents are identical</translation>
    </message>
    <message>
        <location filename="../jsondiff.py" line="205"/>
        <source>共 {0} 处差异</source>
        <translation>{0} differences in total</translation>
    </message>
    <message>
        <location filename="../jsondiff.py" line="207"/>
        <source>（显示前 {0} 条）</source>
        <translation>(showing the first {0})</translation>
    </message>
    <message>
        <location filename="../jsondiff.py" line="211"/>
        <source>……（差异过多或内容过大，已停止；请改用文本 diff 查看）</source>
        <translation>…… (too many differences or content too large; stopped — please use the text diff instead)</translation>
    </message>
</context>
<context>
    <name>jsonutil</name>
    <message>
        <location filename="../jsonutil.py" line="45"/>
        <source>第 {0} 行</source>
        <extracomment>出错行太长了就只显示出错位置附近这一段（两侧各留这么多字符）</extracomment>
        <translation>line {0}</translation>
    </message>
    <message>
        <location filename="../jsonutil.py" line="46"/>
        <source>第 {0} 行第 {1} 列</source>
        <translation>line {0}, column {1}</translation>
    </message>
    <message>
        <location filename="../jsonutil.py" line="56"/>
        <source>可能原因：{0}</source>
        <translation>Possible cause: {0}</translation>
    </message>
    <message>
        <location filename="../jsonutil.py" line="79"/>
        <source>对象的 key 必须用双引号（单引号不行），或这里多了个尾逗号</source>
        <extracomment>不致命但需要提醒（如重复 key） 原文（非法时供 UI 显示，保证内容不丢） json 的原始消息 → 人话。按顺序匹配子串，先命中先用。 NOOP 打标：同 bodyview.VIEW_MODE_ITEMS，本模块在翻译器装载前被 import， 模块级 translate 只会拿到中文。翻译在 hint_for() 运行时做。</extracomment>
        <translation>Object keys must use double quotes (single quotes are not allowed), or there is a trailing comma here</translation>
    </message>
    <message>
        <location filename="../jsonutil.py" line="83"/>
        <source>两个值之间少了逗号，或者多了个尾逗号</source>
        <translation>A comma is missing between two values, or there is a trailing comma</translation>
    </message>
    <message>
        <location filename="../jsonutil.py" line="87"/>
        <source>key 后面少了冒号</source>
        <translation>A colon is missing after the key</translation>
    </message>
    <message>
        <location filename="../jsonutil.py" line="91"/>
        <source>对象或数组末尾多了个逗号（标准 JSON 不允许尾逗号）</source>
        <translation>There is a trailing comma at the end of the object or array (standard JSON does not allow trailing commas)</translation>
    </message>
    <message>
        <location filename="../jsonutil.py" line="95"/>
        <source>这里应该是一个值：常见原因是单引号字符串、写了注释、多了尾逗号，或内容为空</source>
        <translation>A value is expected here: common causes are single-quoted strings, comments, a trailing comma, or empty content</translation>
    </message>
    <message>
        <location filename="../jsonutil.py" line="99"/>
        <source>字符串的引号没有闭合；字符串里要换行得写成 \n</source>
        <translation>The string&apos;s quote is not closed; a newline inside a string must be written as \n</translation>
    </message>
    <message>
        <location filename="../jsonutil.py" line="103"/>
        <source>字符串里有未转义的控制字符（比如直接按了回车），应写成 \n / \t</source>
        <translation>The string contains an unescaped control character (e.g. a literal Enter); write it as \n / \t</translation>
    </message>
    <message>
        <location filename="../jsonutil.py" line="107"/>
        <source>转义序列不合法，\\ 才表示一个反斜杠</source>
        <translation>Invalid escape sequence; \\ represents a single backslash</translation>
    </message>
    <message>
        <location filename="../jsonutil.py" line="111"/>
        <source>\u 后面必须跟 4 位十六进制</source>
        <translation>\u must be followed by 4 hex digits</translation>
    </message>
    <message>
        <location filename="../jsonutil.py" line="115"/>
        <source>第一个 JSON 结束后还有多余内容：可能是 JSONP 包裹，或多个 JSON 拼在一起</source>
        <translation>There is extra content after the first JSON ends: it may be JSONP-wrapped, or several JSON documents concatenated</translation>
    </message>
    <message>
        <location filename="../jsonutil.py" line="119"/>
        <source>分隔符位置不对，检查逗号与冒号</source>
        <translation>A separator is in the wrong place; check the commas and colons</translation>
    </message>
    <message>
        <location filename="../jsonutil.py" line="161"/>
        <source>不合法的 JSON 常量：{0}</source>
        <translation>Invalid JSON constant: {0}</translation>
    </message>
    <message>
        <location filename="../jsonutil.py" line="175"/>
        <source>内容为空</source>
        <translation>Content is empty</translation>
    </message>
    <message>
        <location filename="../jsonutil.py" line="175"/>
        <source>先贴一段 JSON 进来</source>
        <translation>Paste some JSON first</translation>
    </message>
    <message>
        <location filename="../jsonutil.py" line="200"/>
        <source>浏览器 JSON.parse 也不认它；要表示空值就用 null</source>
        <translation>The browser&apos;s JSON.parse would not accept it either; use null for an empty value</translation>
    </message>
    <message>
        <location filename="../jsonutil.py" line="209"/>
        <source>嵌套层级过深，超出解析器递归上限</source>
        <translation>Nesting too deep; exceeds the parser&apos;s recursion limit</translation>
    </message>
    <message>
        <location filename="../jsonutil.py" line="210"/>
        <source>确认内容没被意外重复包裹；可用 JSONPath 先缩小范围</source>
        <translation>Make sure the content is not accidentally double-wrapped; you can narrow the scope with JSONPath first</translation>
    </message>
    <message>
        <location filename="../jsonutil.py" line="236"/>
        <source>存在重复 key：{0}{1}（已保留最后一次出现）</source>
        <translation>Duplicate key: {0}{1} (the last occurrence is kept)</translation>
    </message>
    <message>
        <location filename="../jsonutil.py" line="256"/>
        <source>嵌套层级过深，无法序列化</source>
        <translation>Nesting too deep; cannot serialize</translation>
    </message>
    <message>
        <location filename="../jsonutil.py" line="258"/>
        <source>序列化失败：{0}</source>
        <translation>Serialization failed: {0}</translation>
    </message>
</context>
<context>
    <name>main</name>
    <message>
        <location filename="../main.py" line="97"/>
        <source>MiteProxy 已在运行</source>
        <translation>MiteProxy is already running</translation>
    </message>
    <message>
        <location filename="../main.py" line="98"/>
        <source>检测到 MiteProxy 已有一个实例在运行，请切换到已打开的窗口。</source>
        <translation>Another instance of MiteProxy is already running. Please switch to the open window.</translation>
    </message>
</context>
<context>
    <name>network</name>
    <message>
        <source>关闭</source>
        <extracomment>单次延迟上限：手滑填个 999999 不至于把连接挂死 档位：(key, 显示名, 延迟 ms, 速率 kbps)。0 表示该项不生效 显示名用 QT_TRANSLATE_NOOP 打标（翻译器在 QApplication 创建后才装载， import 期求值永远是中文）；NetworkPanel 构建 combo 时再 translate。</extracomment>
        <translation type="obsolete">Close</translation>
    </message>
    <message>
        <location filename="../network.py" line="349"/>
        <source>未填写原域名</source>
        <extracomment>mitmproxy 的 map_remote 选项格式是 &quot;&lt;sep&gt;/regex/replacement&quot;，分隔符取首字符。 用不可见字符当分隔符，避免和正则里的 | 或 URL 里的 /、# 撞车。 哪些字符出现时认为用户写的是「正则」而不是「普通域名」。 注意**不包含 `.`**——域名本来就带点，把 `api.prod.com` 当正则会让 `.` 变 成&quot;任意字符&quot;，错误的匹配范围（apiXprodYcom 也会被改写）。 允许的普通主机名字符（IPv6 单独用 ipaddress 判） Windows 盘符路径（C: 或 C:/）</extracomment>
        <translation>Source domain not filled in</translation>
    </message>
    <message>
        <location filename="../network.py" line="351"/>
        <source>https?://{0}/* → 本地目录 {1}</source>
        <translation>https?://{0}/* → local directory {1}</translation>
    </message>
    <message>
        <location filename="../network.py" line="353"/>
        <source>目标无法识别（应形如 127.0.0.1:8080 或 /path/to/dir）</source>
        <translation>Target not recognized (should look like 127.0.0.1:8080 or /path/to/dir)</translation>
    </message>
    <message>
        <location filename="../network.py" line="356"/>
        <source>目标无法解析（应形如 127.0.0.1:8080）</source>
        <translation>Target cannot be resolved (should look like 127.0.0.1:8080)</translation>
    </message>
</context>
<context>
    <name>parse_json</name>
    <message>
        <source>嵌套层级过深，超出解析器递归上限</source>
        <translation type="obsolete">Nesting too deep; exceeds the parser&apos;s recursion limit</translation>
    </message>
</context>
<context>
    <name>restore</name>
    <message>
        <source>无接管记录</source>
        <translation type="obsolete">No takeover record</translation>
    </message>
</context>
<context>
    <name>save_session</name>
    <message>
        <source>没有可保存的会话</source>
        <extracomment>单条 WS 会话最多存多少条消息（与详情面板表格上限一致，超出只存前 N 条并标记）</extracomment>
        <translation type="obsolete">No sessions to save</translation>
    </message>
</context>
<context>
    <name>session</name>
    <message>
        <location filename="../session.py" line="312"/>
        <source>没有可保存的会话</source>
        <extracomment>单条 WS 会话最多存多少条消息（与详情面板表格上限一致，超出只存前 N 条并标记） flow.metadata 里记录「body 被截断」的键（值为 &quot;request&quot; / &quot;response&quot; / &quot;request,response&quot;）。 metadata 不落盘，只用于把截断事实从会话记录带到界面提示。 被截断 body 的**原始**大小（dict，按 &quot;request&quot;/&quot;response&quot; 分侧），用于 提示「原 256KB，快照只留前 64KB」。同样只活在 metadata 里。</extracomment>
        <translation>No sessions to save</translation>
    </message>
    <message>
        <location filename="../session.py" line="333"/>
        <source>写入失败: {0}</source>
        <translation>Write failed: {0}</translation>
    </message>
    <message>
        <location filename="../session.py" line="555"/>
        <source>文件不存在</source>
        <translation>File does not exist</translation>
    </message>
    <message>
        <location filename="../session.py" line="604"/>
        <source>读取失败: {0}</source>
        <translation>Read failed: {0}</translation>
    </message>
    <message>
        <location filename="../session.py" line="607"/>
        <source>文件不是 UTF-8 文本会话文件: {0}</source>
        <translation>The file is not a UTF-8 text session file: {0}</translation>
    </message>
</context>
<context>
    <name>sysproxy</name>
    <message>
        <location filename="../sysproxy.py" line="165"/>
        <source>无法枚举网络服务（networksetup 失败）</source>
        <extracomment>接管状态落盘位置（崩溃恢复用） Windows 独有常量（macOS/Linux 的 subprocess 没有这个属性，需 getattr 防护）</extracomment>
        <translation>Cannot enumerate network services (networksetup failed)</translation>
    </message>
    <message>
        <location filename="../sysproxy.py" line="184"/>
        <source>设置 {0} 代理失败: {1}</source>
        <translation>Failed to set the proxy for {0}: {1}</translation>
    </message>
    <message>
        <location filename="../sysproxy.py" line="191"/>
        <source>已接管 {0} 个网络服务的系统代理</source>
        <translation>Took over the system proxy for {0} network services</translation>
    </message>
    <message>
        <location filename="../sysproxy.py" line="201"/>
        <source>写注册表失败: {0}</source>
        <translation>Failed to write the registry: {0}</translation>
    </message>
    <message>
        <location filename="../sysproxy.py" line="208"/>
        <source>已接管系统代理</source>
        <translation>System proxy taken over</translation>
    </message>
    <message>
        <location filename="../sysproxy.py" line="222"/>
        <location filename="../sysproxy.py" line="285"/>
        <source>无接管记录</source>
        <translation>No takeover record</translation>
    </message>
    <message>
        <location filename="../sysproxy.py" line="229"/>
        <source>接管记录损坏，跳过还原: {0}</source>
        <translation>The takeover record is corrupted; skipping restore: {0}</translation>
    </message>
    <message>
        <location filename="../sysproxy.py" line="254"/>
        <source>已还原系统代理</source>
        <translation>System proxy restored</translation>
    </message>
    <message>
        <location filename="../sysproxy.py" line="284"/>
        <source>已还原系统代理（无接管记录，按端口 {0} 兜底关闭）</source>
        <translation>System proxy restored (no takeover record; closed by port {0} as a fallback)</translation>
    </message>
    <message>
        <location filename="../sysproxy.py" line="294"/>
        <source>兜底</source>
        <translation>fallback</translation>
    </message>
</context>
<context>
    <name>textutil</name>
    <message>
        <location filename="../textutil.py" line="86"/>
        <source>原响应</source>
        <translation>Original response</translation>
    </message>
    <message>
        <location filename="../textutil.py" line="87"/>
        <source>新响应</source>
        <translation>New response</translation>
    </message>
    <message>
        <location filename="../textutil.py" line="96"/>
        <source>……（diff 超过 {0} 行，已截断）</source>
        <translation>…… (diff exceeds {0} lines; truncated)</translation>
    </message>
</context>
<context>
    <name>unified_diff</name>
    <message>
        <source>原响应</source>
        <translation type="obsolete">Original response</translation>
    </message>
    <message>
        <source>新响应</source>
        <translation type="obsolete">New response</translation>
    </message>
</context>
</TS>
