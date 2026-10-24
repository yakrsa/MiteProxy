"""FIX 协议字段字典（FIX 4.0–4.4 常用子集，纯数据，无 Qt 依赖）。

三条约定：

1. **只收高频字段**：标准头尾 + 报单 / 成交回报 / 行情 / 报价的常见 tag。
   未收录的 tag 在界面上照常显示（标「未收录」），不挡用户看数据。
2. **中文注释是给人扫一眼的**，不是规范翻译；enum 释义只列常见值。
3. **本文件是数据、不是界面文案**——与 rules.py 的默认规则名同性质，
   所以整个文件在 test_i18n 的覆盖度守卫里豁免（见该测试 _EXEMPT_FILES）。

类型标注（第三列）会影响注释列的提示，例如：
- `UTCTimestamp` / `UTCDateOnly` / `LocalMktDate`：界面顺带给出人话时间；
- `NumInGroup`：重复组引导字段，界面按 GROUPS 展开成树。
"""

from __future__ import annotations

#: 消息类型（tag 35）枚举。应用层消息按 4.4 常见集合收录
MSG_TYPES: dict[str, str] = {
    # 会话层（admin）
    "0": "Heartbeat 心跳",
    "1": "TestRequest 测试请求",
    "2": "ResendRequest 重传请求",
    "3": "Reject 拒绝",
    "4": "SequenceReset 序号重置",
    "5": "Logout 登出",
    "A": "Logon 登录",
    "n": "XMLMessage XML 报文",
    # 应用层（application）
    "6": "IOI 意向报价",
    "7": "Advertisement 广告",
    "8": "ExecutionReport 成交回报",
    "9": "OrderCancelReject 撤单拒绝",
    "B": "News 新闻",
    "C": "Email 邮件",
    "D": "NewOrderSingle 新单",
    "E": "NewOrderList 订单列表",
    "N": "ListStatus 订单列表状态",
    "F": "OrderCancelRequest 撤单请求",
    "G": "OrderCancelReplaceRequest 改单请求",
    "H": "OrderStatusRequest 订单状态查询",
    "J": "AllocationInstruction 分配指令",
    "R": "QuoteRequest 报价请求",
    "S": "Quote 报价",
    "Z": "QuoteCancel 报价取消",
    "a": "QuoteStatusRequest 报价状态查询",
    "b": "MassQuoteAcknowledgement 批量报价确认",
    "i": "MassQuote 批量报价",
    "V": "MarketDataRequest 行情请求",
    "W": "MarketDataSnapshotFullRefresh 全量行情快照",
    "X": "MarketDataIncrementalRefresh 增量行情",
    "Y": "MarketDataRequestReject 行情请求拒绝",
    "c": "SecurityDefinitionRequest 证券定义请求",
    "d": "SecurityDefinition 证券定义",
    "e": "SecurityStatusRequest 证券状态请求",
    "f": "SecurityStatus 证券状态",
    "g": "TradingSessionStatusRequest 交易时段状态请求",
    "h": "TradingSessionStatus 交易时段状态",
    "o": "RegistrationInstructions 登记指令",
    "p": "RegistrationInstructionsResponse 登记指令响应",
    "q": "OrderMassCancelRequest 批量撤单请求",
    "r": "OrderMassCancelReport 批量撤单报告",
    "s": "NewOrderCross 交叉新单",
}

#: tag → (英文名, 中文名, 类型, {值: 释义})
FIELDS: dict[int, tuple[str, str, str, dict[str, str]]] = {
    # ------------------------------------------------------------ 标准头 / 尾
    8: ("BeginString", "开始字符串", "String", {}),
    9: ("BodyLength", "消息体长度", "Length", {}),
    10: ("CheckSum", "校验和", "String", {}),
    34: ("MsgSeqNum", "消息序号", "SeqNum", {}),
    35: ("MsgType", "消息类型", "char", MSG_TYPES),
    43: ("PossDupFlag", "可能重复标志", "Boolean", {"Y": "是", "N": "否"}),
    49: ("SenderCompID", "发送方标识", "String", {}),
    50: ("SenderSubID", "发送子方标识", "String", {}),
    52: ("SendingTime", "发送时间", "UTCTimestamp", {}),
    56: ("TargetCompID", "接收方标识", "String", {}),
    57: ("TargetSubID", "接收子方标识", "String", {}),
    89: ("Signature", "签名", "data", {}),
    93: ("SignatureLength", "签名长度", "Length", {}),
    95: ("RawDataLength", "原始数据长度", "Length", {}),
    96: ("RawData", "原始数据", "data", {}),
    97: ("PossResend", "可能重发", "Boolean", {"Y": "是", "N": "否"}),
    98: ("EncryptMethod", "加密方法", "int", {
        "0": "无", "1": "PKCS", "2": "DES", "3": "PKCS/DES",
        "4": "PGP", "5": "PGP/DES", "6": "PEM/DES",
    }),
    115: ("OnBehalfOfCompID", "代理发送方", "String", {}),
    116: ("OnBehalfOfSubID", "代理发送子方", "String", {}),
    122: ("OrigSendingTime", "原始发送时间", "UTCTimestamp", {}),
    123: ("GapFillFlag", "缺口填充标志", "Boolean", {"Y": "是", "N": "否"}),
    128: ("DeliverToCompID", "送达方标识", "String", {}),
    129: ("DeliverToSubID", "送达子方标识", "String", {}),
    142: ("SenderLocationID", "发送方地点", "String", {}),
    144: ("OnBehalfOfLocationID", "代理地点", "String", {}),
    145: ("DeliverToLocationID", "送达地点", "String", {}),
    211: ("XmlDataLen", "XML 数据长度", "Length", {}),
    212: ("XmlData", "XML 数据", "data", {}),
    369: ("LastMsgSeqNumProcessed", "已处理到的序号", "SeqNum", {}),
    371: ("RefTagID", "引用 tag", "int", {}),
    372: ("RefMsgType", "引用消息类型", "String", MSG_TYPES),
    373: ("SessionRejectReason", "会话拒绝原因", "int", {
        "0": "Invalid tag number 非法 tag", "1": "Required tag missing 缺少必填 tag",
        "2": "Tag not defined for this message type 该报文不允许此 tag",
        "3": "Undefined tag 未定义 tag", "4": "Tag specified without a value 有 tag 无值",
        "5": "Value is incorrect 值不正确", "6": "Incorrect data format 数据格式错误",
        "10": "SendingTime accuracy problem 发送时间精度问题",
        "11": "Invalid MsgType 非法消息类型",
    }),
    348: ("EncodedIssuer", "编码后的发行人", "data", {}),
    349: ("EncodedIssuerLen", "编码后的发行人长度", "Length", {}),
    350: ("EncodedSecurityDesc", "编码后的证券描述", "data", {}),
    351: ("EncodedSecurityDescLen", "编码后的证券描述长度", "Length", {}),
    352: ("EncodedListExecInst", "编码后的执行指令列表", "data", {}),
    353: ("EncodedListExecInstLen", "编码后的执行指令列表长度", "Length", {}),
    354: ("EncodedText", "编码后的文本", "data", {}),
    355: ("EncodedTextLen", "编码后的文本长度", "Length", {}),
    # ------------------------------------------------------------ 报单 / 成交
    1: ("Account", "账户", "String", {}),
    6: ("AvgPx", "成交均价", "Price", {}),
    11: ("ClOrdID", "客户订单号", "String", {}),
    12: ("Commission", "佣金", "Amt", {}),
    13: ("CommType", "佣金类型", "char", {
        "1": "每单位", "2": "百分比", "3": "绝对金额",
    }),
    14: ("CumQty", "累计成交量", "Qty", {}),
    15: ("Currency", "币种", "Currency", {}),
    17: ("ExecID", "成交编号", "String", {}),
    18: ("ExecInst", "执行指令", "MultipleCharValue", {
        "1": "Not held 不持有", "2": "Work 逐步执行", "3": "Go along 跟随",
        "4": "Over the day 全天", "5": "Held 持有",
        "6": "Participate don't initiate 参与不主动",
    }),
    19: ("ExecRefID", "执行引用号", "String", {}),
    20: ("ExecTransType", "执行交易类型", "char", {
        "0": "New 新", "1": "Cancel 撤销", "2": "Correct 更正", "3": "Status 状态",
    }),
    21: ("HandlInst", "处理指令", "char", {
        "1": "Automated execution 自动执行", "2": "Manual 手动",
        "3": "Auto-best-ex 自动择优",
    }),
    22: ("IDSource", "代码来源", "String", {
        "1": "CUSIP", "2": "SEDOL", "3": "QUIK", "4": "ISIN", "5": "RIC",
        "6": "ISO 币种代码", "7": "ISO 国家代码", "8": "交易所代码", "9": "SICOVAM",
    }),
    29: ("LastCapacity", "最后成交能力", "char", {
        "1": "Agent 代理", "2": "Principal 自营", "3": "Riskless principal 无风险自营",
    }),
    30: ("LastMkt", "最后成交市场", "Exchange", {}),
    31: ("LastPx", "最后成交价", "Price", {}),
    32: ("LastQty", "最后成交量", "Qty", {}),
    37: ("OrderID", "订单编号", "String", {}),
    38: ("OrderQty", "订单数量", "Qty", {}),
    39: ("OrdStatus", "订单状态", "char", {
        "0": "New 新订单", "1": "Partially filled 部分成交", "2": "Filled 全部成交",
        "3": "Done for day 当日结束", "4": "Canceled 已撤销", "5": "Replaced 已改单",
        "6": "Pending Cancel 撤销中", "7": "Stopped 已停止", "8": "Rejected 已拒绝",
        "9": "Suspended 已暂停", "A": "Pending New 新单待确认",
        "B": "Calculated 已计算", "C": "Accepted 已接受",
        "D": "Pending Replace 改单待确认",
    }),
    40: ("OrdType", "订单类型", "char", {
        "1": "Market 市价", "2": "Limit 限价", "3": "Stop 止损",
        "4": "Stop limit 止损限价", "5": "Market on close 收盘市价",
        "P": "Pegged 挂钩",
    }),
    41: ("OrigClOrdID", "原客户订单号", "String", {}),
    44: ("Price", "价格", "Price", {}),
    45: ("RefSeqNum", "引用序号", "SeqNum", {}),
    47: ("RelatdSym", "关联证券", "String", {}),
    48: ("SecurityID", "证券代码", "String", {}),
    54: ("Side", "买卖方向", "char", {
        "1": "Buy 买入", "2": "Sell 卖出", "3": "Buy minus 买入（扣息）",
        "4": "Sell plus 卖出（加息）", "5": "Sell short 卖空",
        "6": "Sell short exempt 豁免卖空", "8": "Cross 交叉",
    }),
    55: ("Symbol", "证券代码", "String", {}),
    58: ("Text", "文本", "String", {}),
    59: ("TimeInForce", "时效", "char", {
        "0": "Day 当日有效", "1": "GTC 撤销前有效", "2": "At the opening 开盘时段",
        "3": "IOC 立即成交否则取消", "4": "FOK 全部成交否则取消",
        "6": "At the close 收盘时段",
    }),
    60: ("TransactTime", "交易时间", "UTCTimestamp", {}),
    61: ("Urgency", "紧急程度", "char", {"0": "Normal 普通", "1": "Flash 快速"}),
    63: ("SettlmntTyp", "结算类型", "char", {
        "0": "Regular 常规", "1": "Cash 现金", "2": "Next day 次日",
        "3": "T+2", "6": "Future 期货", "9": "T+5",
    }),
    64: ("FutSettDate", "期货结算日", "LocalMktDate", {}),
    65: ("SymbolSfx", "代码后缀", "String", {}),
    66: ("ListID", "订单列表编号", "String", {}),
    68: ("TotNoOrders", "列表订单总数", "int", {}),
    70: ("AllocID", "分配编号", "String", {}),
    73: ("NoOrders", "列表内订单数", "NumInGroup", {}),
    74: ("AvgPrxPrecision", "均价精度", "int", {}),
    75: ("TradeDate", "交易日期", "LocalMktDate", {}),
    76: ("ExecBroker", "执行券商", "String", {}),
    77: ("OpenClose", "开平标志", "char", {"O": "Open 开仓", "C": "Close 平仓"}),
    78: ("NoAllocs", "分配明细数", "NumInGroup", {}),
    79: ("AllocAccount", "分配账户", "String", {}),
    80: ("AllocQty", "分配数量", "Qty", {}),
    81: ("ProcessCode", "处理代码", "char", {
        "0": "Regular 常规", "1": "Soft dollar 软美元", "2": "No commission 无佣金",
        "3": "Commission sharing 佣金分成", "4": "Transfer 转嫁",
    }),
    84: ("CxlQty", "已撤数量", "Qty", {}),
    87: ("AllocStatus", "分配状态", "int", {
        "0": "Accepted 已接受", "1": "Block level reject 整笔拒绝",
        "2": "Account level reject 账户级拒绝", "3": "Received 已收到",
    }),
    88: ("AllocRejCode", "分配拒绝原因", "int", {
        "0": "Unknown account 未知账户", "1": "Incorrect quantity 数量不符",
        "2": "Incorrect average price 均价不符",
        "3": "Incorrect commission 佣金不符", "6": "Account not found 账户不存在",
    }),
    99: ("StopPx", "触发价", "Price", {}),
    100: ("ExDestination", "交易所目的地", "Exchange", {}),
    103: ("OrdRejReason", "订单拒绝原因", "int", {
        "0": "Broker/Exchange option 券商/交易所选项",
        "1": "Unknown symbol 未知代码",
        "2": "Exchange closed 交易所闭市",
        "3": "Order exceeds limit 超出限额",
        "4": "Too late to enter 下单过晚",
        "5": "Unknown order 未知订单",
        "6": "Duplicate order 重复订单",
        "7": "Duplicate of verbally communicated order 与电话委托重复",
        "8": "Stale order 过期订单",
    }),
    106: ("Issuer", "发行人", "String", {}),
    107: ("SecurityDesc", "证券描述", "String", {}),
    109: ("ClientID", "客户编号", "String", {}),
    110: ("MinQty", "最小数量", "Qty", {}),
    111: ("MaxFloor", "最大揭示量", "Qty", {}),
    112: ("TestReqID", "测试请求编号", "String", {}),
    118: ("NetMoney", "净金额", "Amt", {}),
    119: ("SettlCurrAmt", "结算金额", "Amt", {}),
    120: ("SettlCurrency", "结算币种（旧版）", "Currency", {}),
    121: ("ForexReq", "需要换汇", "Boolean", {"Y": "是", "N": "否"}),
    143: ("TargetLocationID", "目标地点", "String", {}),
    148: ("Headline", "标题", "String", {}),
    149: ("URLLink", "链接", "String", {}),
    153: ("AllocAvgPx", "分配均价", "Price", {}),
    161: ("AllocText", "分配文本", "String", {}),
    168: ("EffectiveTime", "生效时间", "UTCTimestamp", {}),
    117: ("QuoteID", "报价编号", "String", {}),
    124: ("NoExecs", "成交笔数", "NumInGroup", {}),
    131: ("QuoteReqID", "报价请求编号", "String", {}),
    140: ("PrevClosePx", "前收盘价", "Price", {}),
    146: ("NoRelatedSym", "关联代码数", "NumInGroup", {}),
    150: ("ExecType", "执行类型", "char", {
        "0": "New 新订单", "1": "Partial fill 部分成交", "2": "Fill 全部成交",
        "3": "Done for day 当日结束", "4": "Canceled 已撤销", "5": "Replace 已改单",
        "6": "Pending Cancel 撤销中", "7": "Stopped 已停止", "8": "Rejected 已拒绝",
        "9": "Suspended 已暂停", "A": "Pending New 新单待确认",
        "B": "Calculated 已计算", "C": "Expired 已过期", "D": "Restated 重述",
        "E": "Pending Replace 改单待确认", "F": "Trade 成交（部分）",
    }),
    151: ("LeavesQty", "剩余数量", "Qty", {}),
    152: ("CashOrderQty", "现金订单数量", "Qty", {}),
    156: ("SettlCurrency", "结算币种", "Currency", {}),
    157: ("NumDaysInterest", "计息天数", "int", {}),
    158: ("AccruedInterestRate", "应计利率", "Percentage", {}),
    159: ("AccruedInterestAmt", "应计利息", "Amt", {}),
    160: ("SettlInstMode", "结算指令模式", "char", {
        "0": "Default 默认", "1": "Standing 长期结算指令",
    }),
    167: ("SecurityType", "证券类型", "String", {
        "CS": "Common Stock 普通股", "FUT": "Future 期货", "OPT": "Option 期权",
        "IND": "Index 指数", "FX": "Forex 外汇", "MF": "Mutual Fund 基金",
    }),
    200: ("MaturityMonthYear", "到期年月", "String", {}),
    201: ("PutOrCall", "期权方向", "int", {"0": "Put 看跌", "1": "Call 看涨"}),
    202: ("StrikePrice", "行权价", "Price", {}),
    203: ("CoveredOrUncovered", "备兑标志", "int", {
        "0": "Covered 备兑", "1": "Uncovered 非备兑",
    }),
    206: ("OptAttribute", "期权属性", "char", {}),
    207: ("SecurityExchange", "交易所", "Exchange", {}),
    210: ("MaxShow", "最大揭示数量", "Qty", {}),
    231: ("ContractMultiplier", "合约乘数", "float", {}),
    # ------------------------------------------------------------ 行情
    262: ("MDReqID", "行情请求编号", "String", {}),
    263: ("SubscriptionRequestType", "订阅类型", "char", {
        "0": "Snapshot 快照", "1": "Snapshot + Updates 快照+更新",
        "2": "Disable 取消订阅",
    }),
    264: ("MarketDepth", "市场深度", "int", {}),
    265: ("MDUpdateType", "行情更新类型", "int", {
        "0": "Full refresh 全量刷新", "1": "Incremental 增量",
    }),
    266: ("AggregatedBook", "合并盘口", "Boolean", {"Y": "是", "N": "否"}),
    267: ("NoMDEntryTypes", "行情条目类型数", "NumInGroup", {}),
    268: ("NoMDEntries", "行情条目数", "NumInGroup", {}),
    269: ("MDEntryType", "行情条目类型", "char", {
        "0": "Bid 买入", "1": "Offer 卖出", "2": "Trade 成交",
        "4": "Opening Price 开盘价", "5": "Closing Price 收盘价",
        "6": "Settlement Price 结算价", "7": "Session High 最高价",
        "8": "Session Low 最低价", "9": "VWAP 成交量加权均价",
    }),
    270: ("MDEntryPx", "行情价格", "Price", {}),
    271: ("MDEntrySize", "行情数量", "Qty", {}),
    272: ("MDEntryDate", "行情日期", "UTCDateOnly", {}),
    273: ("MDEntryTime", "行情时间", "UTCTimeOnly", {}),
    278: ("MDEntryID", "行情条目编号", "String", {}),
    279: ("MDEntryAction", "行情动作", "char", {
        "0": "New 新增", "1": "Change 变更", "2": "Delete 删除",
    }),
    # ------------------------------------------------------------ 组合 / 标的 / 参与方
    311: ("UnderlyingSymbol", "标的代码", "String", {}),
    336: ("TradingSessionID", "交易时段", "String", {}),
    386: ("NoTradingSessions", "交易时段数", "NumInGroup", {}),
    447: ("PartyIDSource", "参与方来源", "char", {
        "B": "BIC", "C": "市场参与方标识", "D": "CSD 参与方",
        "E": "ISO 国家代码", "F": "结算实体地点",
    }),
    448: ("PartyID", "参与方标识", "String", {}),
    452: ("PartyRole", "参与方角色", "int", {
        "1": "Executing Firm 执行机构", "3": "Client ID 客户",
        "7": "Entering Firm 录入机构", "8": "Entering Trader 录入交易员",
        "9": "Executing Trader 执行交易员",
    }),
    453: ("NoPartyIDs", "参与方数", "NumInGroup", {}),
    555: ("NoLegs", "组合腿数", "NumInGroup", {}),
    600: ("LegSymbol", "腿代码", "String", {}),
    625: ("TradingSessionSubID", "交易子时段", "String", {}),
    711: ("NoUnderlyings", "标的数", "NumInGroup", {}),
}

#: 重复组：引导 tag（NumInGroup 字段）→ (英文名, 中文名, 成员 tag 元组)。
#: 成员只列常见字段——实例切分采用「成员 tag 在实例内不重复」的启发式，
#: 未收录成员的字段会结束该实例并平铺展示（界面上会注明）。
GROUPS: dict[int, tuple[str, str, tuple[int, ...]]] = {
    78: ("NoAllocs", "分配明细", (79, 80)),
    146: ("NoRelatedSym", "关联代码", (
        55, 65, 48, 22, 107, 167, 207, 38, 40, 44, 54, 59, 15, 58, 210,
        336, 625, 311,
    )),
    453: ("NoPartyIDs", "参与方", (448, 447, 452)),
    267: ("NoMDEntryTypes", "行情条目类型", (269,)),
    268: ("NoMDEntries", "行情条目", (
        279, 269, 278, 55, 270, 271, 272, 273, 336, 625,
    )),
    386: ("NoTradingSessions", "交易时段", (336, 625)),
    555: ("NoLegs", "组合腿", (600,)),
    711: ("NoUnderlyings", "标的", (311,)),
}

#: DataLength 配对：长度 tag → 数据 tag。数据字段的值按长度原样读取
#: （可能含 SOH，不能按分隔符切），这是 FIX 解析最容易踩的坑。
DATA_LENGTH_PAIRS: dict[int, int] = {
    93: 89,      # SignatureLength → Signature
    95: 96,      # RawDataLength → RawData
    211: 212,    # XmlDataLen → XmlData
    349: 348,    # EncodedIssuerLen → EncodedIssuer
    351: 350,    # EncodedSecurityDescLen → EncodedSecurityDesc
    353: 352,    # EncodedListExecInstLen → EncodedListExecInst
    355: 354,    # EncodedTextLen → EncodedText
}


def lookup(tag: int) -> tuple[str, str, str, dict[str, str]] | None:
    """字典查询；未收录返回 None（界面显示「未收录」但仍展示 tag/值）。"""
    return FIELDS.get(tag)


def group_of(tag: int) -> tuple[str, str, tuple[int, ...]] | None:
    """该 tag 是否是已收录的重复组引导字段。"""
    return GROUPS.get(tag)


def data_partner(tag: int) -> int | None:
    """该 tag 是否是某个数据字段的长度字段；是则返回配对的数据 tag。"""
    return DATA_LENGTH_PAIRS.get(tag)
