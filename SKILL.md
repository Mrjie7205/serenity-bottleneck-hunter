---
name: serenity-bottleneck-hunter
description: 给定一个投资主题/趋势,复用交易者 Serenity(@aleabitoreddit)的"供应链瓶颈逆向映射"方法论,独立挖出被市场忽视的上游瓶颈股(而非分析他已喊过的标的)。当用户给出一个主题(如"AI 数据中心电力""人形机器人""HBM 内存")并想要候选标的+论证时使用。仅供研究教育,非投资建议。
---

# Serenity Bottleneck Hunter

把一个**投资主题**转成一份**被忽视的上游瓶颈候选股名单 + 论证 + 目标价/时间框架**。核心不是抄 Serenity 的票,而是**复用他的逻辑去选新股**。

> 📓 每条纪律是怎么用一次真实翻车换来的,见 `reference/lessons.md`。本文件只讲"做什么";完整事故复盘在那边,用 `〔… → lessons.md#锚点〕` 指过去。

## 何时用
- 用户给出一个主题/趋势,想要"沿这个方向能买什么"。
- 用户给一个上游环节/材料,想找对应的瓶颈公司。
- ❌ 不要用于:已知标的的纯财务分析、抄作业式"他买了啥"。

## 核心理念
> 逆向拆解供应链,在机构与分析师发现之前,埋伏那个**无人察觉的上游瓶颈**,用催化剂兑现。
> alpha 来自"**早于机构发现主题**",不是抄到最低点。

---

## v0.2 工具入口

- 首次安装后可执行 `python scripts/run_demo.py`：不联网的历史演示，输出与正式跟踪表分开；说明见 [examples/README.md](examples/README.md)。演示不替代真实研究。
- 实际 A 股／美股／港股取价与估值设置见 [reference/DATA_SOURCES.md](reference/DATA_SOURCES.md)。保留来源、行情日期及质量提醒；不得按跳空幅度自行猜除权。
- 报告 SPEC 中相对路径从本技能根目录解析；可用 `tracking_file` 选择自己的 CSV。现有默认路径兼容保留。`shell_from` 缺省时使用内置模板，无需私库或驾驶舱。
- 发布前可用 `python scripts/verify_report.py <报告> --scan <输入> --tracking <跟踪表> --strict` 完整对账。严格模式的输入缺失和数字错配必须先解决。

## 可选驾驶舱

只有用户需要管理、跟踪或复盘已有研究时，才使用 [cockpit/README.md](cockpit/README.md) 的本地驾驶舱。核心研究流程不依赖它。

默认 `python cockpit/run.py` 读取只读历史演示，不抓取行情。用户自己的研究须明确指定目录；报告 SPEC 的 `out` 与 `tracking_file` 应指向该目录。取价、告警核对和定时任务分别由用户手动触发或显式启用。驾驶舱的“猎手／覆盖”是显示范围，不是龙头视角。

## 工作流(7 步)

**Step 1 · 确认资本开支确定性**
这个主题的钱为什么"一定"会花?规模、周期多长?需求确定性 > 个股故事性。先归类:**Bottleneck(瓶颈)/ Disruption(颠覆)/ Evolution(演进)**?(本 skill 主攻 Bottleneck)
- **标明需求来源**:政府/国防(节奏慢、看订单与预算周期)还是商业(超大规模厂商 capex、节奏快)?二者估值锚与择时节奏不同,Step 6/7 据此调整。

**Step 2 · 逆向拆链 + 广扫纪律(5 层产业链 + 跨主题 root + 可选第 6 层独有 IP)**
列出 **5 层** 从下游到上游:**下游对照 → 中游系统 → 中游器件 → 上游设备 → 上游材料/代工**。**跳过人人都盯的下游龙头**。

- **必做"广扫供应商"**:除最上游材料层外,单独再搜一轮该主题的子系统/器件/卖铲子供应商,否则漏 ④ 原型标的。〔教训:商业航天漏 Redwire → lessons.md#redwire〕
- **广扫颗粒度**:覆盖 5 层,每层至少 2-3 个标的。**广扫不到位 ≠ 板块没机会** —— 停手前先问"是真没机会,还是没扫够"。〔教训:800VDC 6 只→15 只才挖出 STM → lessons.md#breadth-stm〕

- **跨主题 root 节点**:**ARM / CDNS / SNPS 放在 chain-viz 上方独立的"跨主题 root"小卡片,显示一次,不画进每个主题的产业链层**(三家是所有芯片设计驱动主题共用的根)。〔教训:7 份报告 IP/EDA 层 100% 重复 → lessons.md#ip-eda-root〕
  ```
  <div class="cross-theme-root">
    <span class="label">跨主题 root(芯片设计驱动主题共用)</span>
    ARM ⭐⭐ + CDNS ⭐⭐ + SNPS ⭐⭐
  </div>
  ```
  其 ⭐⭐ 状态来自 `tracking/cross_theme_index_snapshot.csv`,不每个主题重画。
- **可选第 6 层 · 主题独有 IP/EDA 玩家**(仅当主题真有独立玩家才画):
  - **自动驾驶 L4** → 真有独立 IP:**MBLY**(Mobileye 授权给 BMW/Audi/Geely)— 必须画
  - **个人 AI PC** → ARM 在 PC 是**真单源**(Apple M + Qualcomm Snapdragon X + AMD AI300)— 保留画在产业链顶层 + 标本主题真单源
  - **AI Agent / 物理 AI / AMR** → 无独立 IP 玩家 → 不画第 6 层,root section 提一次即可
  - **MLCC / 800VDC / 商业航天** → 不依赖芯片设计,完全跳过 IP/EDA
  - **凑数禁令**:没有真独立玩家的主题不强制画第 6 层 —— IP/EDA 是 optional 不是 mandatory。

- **A 穷尽性 · 已知玩家全集**:每个主题开扫前**先列已知玩家全集**(全球+全市场,涵盖上市/私有/被并购),逐一显式标记 `covered` / `private`(跳过+原因)/ `acquired`(标合并实体)/ `delisted` / `untracked`(EODHD/yfinance 无数据)。**不允许"默认遗漏"**,不允许"我扫了 5 家就够了"。写在报告底部"已知玩家全集 audit"块。〔示例:L4 LiDAR 全集枚举 → lessons.md#player-census〕
- **A+ ETF audit(强制工具化兜底)**:**A 项"凭记忆列全集"不够,会漏主仓玩家。** 每个新主题开 forward_picks 扫描前,**必跑** `python scripts/theme_etf_coverage.py --etfs <ETF1>,<ETF2>,... --theme "<主题名>"` → 拉主题 ETF top 25 持仓、与 forward_picks diff、输出 `tracking/_etf_audit_<theme>.json`。对每只 new candidate 人工判定产业链层 + 原型 + 是否纳入;**top 25 持仓 100% 必 audit**(主仓占权重 >70%,小权重 me-too 可跳)。〔教训:Dogfood #10 漏 PANW/CRWD 等 34 只、covered 率 50% → lessons.md#etf-audit〕
  - **主题 ETF 映射**:
    - AI Agent / SaaS / Software → `IGV` + `WCLD` + `AIQ`
    - 网络安全 → `CIBR` + `BUG` + `HACK`
    - 半导体 → `SOXX` + `SMH` + `PSI`
    - AI 算力/GPU → `AIQ` + `BOTZ`
    - 网络/算力基础设施 → `WCLD` + `CLOU` + `SKYY`
    - 物理 AI 机器人 → `BOTZ` + `ROBO` + `IRBO`
    - 自动驾驶 → `DRIV` + `IDRV`
    - 电网/能源 → `GRID` + `XLU` + `URNM`
    - 清洁能源/电气化 → `ICLN` + `LIT` + `KARS`
    - 国防/航天 → `ITA` + `XAR` + `UFO`
    - 5G / 通信 → `FIVG` + `NXTG`
    - 数据中心 / 算力 → `DTCR` + `CLOU` + `SRVR`
  - **报告 audit section 必列**:① ETF 清单 ② ETF top 持仓全集数 ③ covered/private/跳过原因逐一分类 ④ ETF coverage %。**< 80% 必须诚实标"穷尽性纪律未达标"**。
  - 注:A 股无 stockanalysis ETF 持仓数据 → 改用申万行业指数成分 + 人工列已知玩家全集。
- **A++ ticker 双向验证(强制)**:**广扫前用 EODHD search 反查"代码 → 公司名"双向验证**——A 项穷尽 + A+ ETF audit 都不防"错标"(标对公司名但 ticker 指向另一家)。每只候选必验:
  ```bash
  curl "https://eodhd.com/api/search/<COMPANY_NAME>?api_token=$KEY&fmt=json"
  curl "https://eodhd.com/api/search/<TICKER>?api_token=$KEY&fmt=json"
  ```
  → 两次返回的 `Name` 必须一致。**禁止凭记忆写 ticker**,哪怕"我很确定"也必须 search。**A 股尤其踩坑**:6(沪市)/ 0(深市)/ 3(创业板)/ 688(科创板)/ 002(中小板)代码段交叉,同 5 位数字可能是不同公司。工具:`scripts/ticker_truth.py`(ground-truth 库)+ `scripts/verify_tickers.py`(git pre-commit hook 自动拦截)。**验证通过才写入 _scan_*.py。** 〔教训:绿的谐波/信质电机/ASEKY/EHGO 共 4 个真错位 → lessons.md#ticker-verify〕
- **公司状态检查(写判定前必查)**:每只候选(含链路图非候选节点)搜一次当前状态——收购/被收购/私有化/**IPO 上市**/退市/破产重组(搜 `<公司名> acquisition/IPO/merger`)。收购中的标的 🔴 剔除(被收购反向验证选股方向、记进报告当佐证)。**"私有/不可投"是状态性断言,LLM 的"某某私有"先验是训练快照、极易过期,必须当场搜证**,状态写进 company_desc 带日期的 status 字段。〔教训:SkyWater 被 IonQ 收购 + SpaceX IPO 当天报告还标"私有" → lessons.md#company-status〕
- **私有公司诚实跳过**:每个主题都有"真单源但私有/子部门"的标的。**禁止为凑标的硬塞不纯/不可投的公司**;在报告里显式列"已识别但跳过的瓶颈 + 原因"(本身就是高密度信号)。例:物理 AI 六维力传感器(坤维/字节灵犀/宇立全私)、鼎智科技(北交所 EODHD 不支持)→ 跳过。坦诚标"无干净纯 play"比硬凑更有价值。
- **主题边界声明**:跑大类主题(物理 AI / AI 算力 / 能源转型)时,**报告顶部必须界定本期边界** —— 大类下常有 3+ 个供应链差异显著的子领域,显式说"本期聚焦 X,其他子领域作为独立专题分批跑"。命名:`<大类>_<子领域>_完整分析报告.html`。〔教训:物理 AI v1 默认=人形 → lessons.md#theme-scope〕

**Step 3 · 对每层套「9 大瓶颈原型」**(详见 `reference/supply-chain-and-archetypes.md` Part D):
①上游材料/衬底垄断 ②单一来源卡脖子 ③产能售罄/已锁定=去风险 ④进每个设计的BOM/普适 ⑤估值对标套利 ⑥测试/设备瓶颈 ⑦冷门/前机构 ⑧巨头依赖护城河 ⑨宏观二阶/错杀。
命中原型越多的环节,越是猎区。

**Step 4 · 产出候选(偏上游、冷门、小市值)**
每个环节挑 1-3 家最纯正的公司。优先:小市值、卖方覆盖少、散户没听过(原型⑦)。用 EODHD search 校验代码与上市地(含海外,见 A++ 纪律)。
- **别只押"最上游材料咽喉(①②)"**:也纳入"普适器件/卖铲子(④)"——两档都列,避免选股偏科。
- **最纯的瓶颈常在海外/OTC**(如 5N Plus 在 TSX、Umicore 在布鲁塞尔)→ 主动去海外交易所找,注明流动性/准入限制。
- **若瓶颈落在私有公司或大公司的一个部门** → 必须给"暴露路径":买含该业务的母公司(说明稀释/纯度),或如实标"无干净纯 play、跳过"。不硬凑不纯标的充数。
- **跨主题节点检查(强制)**:产出候选后立即跑 `python tracking/cross_theme_scan.py`,与历史 `forward_picks.csv` 对照:
  - 同 symbol 跨 ≥2 主题 = **⭐**;≥3 = **⭐⭐**(罕见,真"非线性定价权")。
  - **档位过滤防巨头摊薄误标**:中游系统/下游对照/反面参照不计入;中游卖铲子必须有 ④ 普适才计入。
  - ⭐ 节点在 Step 5"前机构"闸门**自动加分**(多个 capex cycle 同时驱动 = 产能压力叠加、即使有机构覆盖仍可能 mispriced)。
  - **eodhd_symbol 规范**:美股一律带 `.US` 后缀,否则脚本无法匹配同一只。〔首测案例 AEHR 跨双主题 → lessons.md#cross-theme-aehr〕

**Step 5 · 三道闸门逐一检验**
- 🔒 真瓶颈:产能受限/有定价权/短期无法绕过("别人能 1-2 年内绕过吗?")
- 👁️ 前机构:卖方研报少、机构持仓低、市值小;⭐ 跨主题节点自动加分
- 💰 便宜+已去风险:估值压抑 + 产能/订单锁定或现金充足

**Step 6 · 入场时机**(见下方两套模式,别搞错)

**Step 7 · 出报告**(单文件 HTML,用下方输出模板 + `reference/report_template.html`,含目标价+时间框架+**反向研究**+**证伪条件**+风险+免责)→ **交付前必过 `scripts/verify_report.py` 契约校验**(见下方"交付契约")

---

## 入场时机:两套模式(经价格回测校准,勿混用)

| 模式 | 适用 | 触发 |
|---|---|---|
| **A 主题瓶颈长线**(本 skill 默认) | 主题里的上游瓶颈股 | **主题刚点燃 + 早期上行/突破 + 仍前机构就进,主动放弃抄底。等回调=踏空。** |
| **B 波段超跌反弹** | 成熟大票的非实质性错杀 | 买恐慌回调(增发/稀释类实质利空则回避) |

回测依据(11 只光子学标的):首 call 多在前 6 月区间 86%-237% 高位入场,之后 2-6 个月中位 ~+277%。→ **早于主题、容忍不抄底**才是 alpha 来源(注:此为逻辑自洽校准,非业绩,见"验证状态")。

**判定二轴(2026-06-21 核心修正):水位 ≠ 判定。** 高水位(rng 高、贴顶)**不再自动 = 🟡**——单看水位是「均值回归」伪装成「动量」,会系统性把热门板块的真龙头判成"别追"、错过最大涨幅(闪迪式 melt-up)。判定必须叠加**第二轴:这波涨基本面跟不跟得上**——`price.py` 的 `valuation()` 出 forward P/E / PEG / 盈利&营收增速,扫描算 RS-rank(同主题内 3 月动量排名),Step 1 出周期 runway(早/中/晚)。`render_report` 标尺自动显示第二轴 + 给 hint:

| | 基本面跟得上(forward P/E 压缩 / PEG≤2 / 盈利增速≥涨幅 / RS 领头 / 周期早) | 跟不上(纯重估 / forward P/E 扩张 / 周期晚 / RS 落后) |
|---|---|---|
| **高水位(贴顶)** | 🟢 **贵但对**——动量龙头,Mode A 持有/可加,**别 fade** | 🔴 **真贴顶**——再涨是博傻,回避 |
| **低水位** | 🟢 经典埋伏(Mode A 早 / Mode B 超跌) | 🔴 落后有原因,排除 |

**A股 forward/PEG 常缺**(yfinance 估计覆盖薄)→ 退化用"盈利/营收增速 vs 涨幅"+ RS;标尺显示"—"即数据缺、不强判。**limit**:顶 vs 续涨本质难判,二轴只 tilt 概率、不根治,新规则对不对靠 L1 向前跟踪校准。〔教训:水位标尺均值回归伪装动量、系统性反龙头 → lessons.md#water-level-2axis〕

**价格纪律(硬规则)**:
- **强制用 `scripts/price.py` 拉真实价格**(provider 自动回退:**EODHD(`EODHD_API_KEY`)→ yfinance**),输出 6 月区间位置、距高点、近 1/3 月动量、stage 标签。**严禁 WebSearch 抓价格、严禁凭印象猜 early/extended**——猜测 = 流程错误。海外股若 yfinance 拿不到,让用户提供 EODHD key 或换可解析代码重跑,不降级为定性。
- **批量拉价必须走 price.py 接口**:`python -c "from scripts.price import analyze; print(analyze('6324.T'))"` 或脚本里 `from scripts.price import fetch_history`。**禁止 inline `Invoke-RestMethod` 调 EODHD**(绕过 yfinance fallback)。〔教训:物理 AI v1 漏 4 只日股 → lessons.md#price-interface〕
- **报告所有数字 100% 来自 price.py 输出,禁止手填/猜数**:批量 scan 脚本输出必含全 9 字段(`last / range_pos_6mo_pct / pct_off_6mo_high / ret_1m_pct / ret_3m_pct / above_sma50 / stage` + high/low_6mo)+ 保留完整 log;写入 forward_picks 前逐字段 verify。〔教训:手填 9 个 off% 全错(HSAI -89% 真 -35.6%)→ lessons.md#hand-filled〕

---

## 输出模板(HTML)

> **交付物 = 一个自包含 HTML 文件**(单文件、样式内联,仅 Google Fonts 可外链),写到 `reports/<主题>_分析报告.html`。骨架与配色复用 `reference/report_template.html`。生成后 `Start-Process <file>.html`(Win)/ `open`(mac)打开。
>
> **生成方式(硬规则)**:报告**必须用 `scripts/render_report.py` 渲染**——agent 只写一个薄「主题 SPEC」(纯数据:候选 / §A§B / 产业链节点+依赖边 / 文字;示例 `examples/demo_spec.json`),引擎负责:默认读取公库自带 `reference/report_template.html`（也可显式选择合格报告外壳）(CSS + reveal/术语/chain-draw 脚本)、拉 scan 价(零手填)、渲染**真 chain-viz**(`.cnode`+`.edge-list` 喂 `layoutChain` 自动绘制判瓶颈)、水位标尺三价、§A 红队 + §B 证伪、写 forward_picks。**严禁绕过引擎手搓 HTML / 画静态简版 chain-viz**——引擎是唯一路,产出后必须用 `verify_report.py` 校验；结构通过不代表投资论点通过。因预算/复杂度砍任何既定标准,**当场说明、不把缩水版当完整品交**。〔教训:契约≠保真,把"过自己造的闸"当"做好了" → lessons.md#chain-viz-fidelity〕
>
> **report_template.html 已内置的模板特征(生成时必用)**:① **本次行动点**——头条位最多 2 张行动卡(设什么警报 / 什么条件做什么),无视排序置顶,读者 10 秒拿到本次唯一要做的事;② **水位标尺**——动量用 贴顶/高位/中位/低位/贴底 + 距高点% + 1m/3m 的人话化标尺,且**标尺两端标 6 个月最低/最高价、游标上方标现价**(6 月低/高/现价三价,币种按交易所后缀);③ **产业链双规则瓶颈判定**——漏斗型(入度≥2 出度≤1,金边)+ 枢纽型(入度≥2 出度≥2,多对多最难绕开,酒红边);④ **判定史**——同标的历史判定(旧价→今价 ±%、对错复盘),体现框架连续性与诚实度;⑤ **§A 红队 + §B 证伪**——每候选折叠红队、🟢 带证伪(本次 Tier-1 新增,见上)。

### 交付契约(`scripts/verify_report.py`,交付前必过)

报告写完、宣布完成**之前**必跑一次,把"漏交付/漏状态/漏入库"挡在交付前:

```
EODHD_API_KEY=… python scripts/verify_report.py reports/<主题>_分析报告.html
```

它查**契约**(不查思路):区块齐全(chain-viz / leaderboard / 行动点 / 三道闸 / 免责)· 每候选有 §A、🟢 有 §B · 标尺三价齐 · ticker 过 ground-truth · **现价/6月低/高 逐字段对账 scan JSON**(防手填/过期)· 状态断言带日期(过期 30 天提醒)· 每判定入轨 `forward_picks` 且 🟢 的 `invalidation` 非空 · 无占位符残留 · `<details>` 开合平衡。**有【拦】先修再交付,只剩【警】方可交付。**

**报告必含区块(对应 7 步,所有项 hard rule 不允许跳过):**
1. **页眉 + 一句话结论**:主题 | 资本开支确定性 | 类别 | 数据截止日 | 价格源 | 免责。
2. **30 秒看懂这个主题**(150-220 字大白话,hero 之后、Step 1 之前,class `.thirty-sec`)。
3. **Step1 资本开支确定性**:为什么钱一定花 + 需求来源。
4. **核心发现 callout**:最该被先看到的那句(瓶颈在哪层、有没有干净纯 play)。
5. **⚠ Step2 逆向拆链(网状视图)— 强制必含**:每个子主题供应链都不同,**禁止以"前面画过类似的"为由跳过**。`.chain-viz` 容器 + 5 层 `.chain-layer`(+ 可选第 6 层独有 IP),跨主题 root 卡片在上方。每层 `.cnode[data-id=...]`(data-id = forward_picks 一致的 eodhd_symbol,美股带 `.US`);供货关系写 `.edge-list`(`data-from/to/weight` 三档),JS 画 SVG + 判瓶颈点。跨主题节点加 `<span class="star-inline">⭐</span>`。〔教训:L4/AMR 漏此区块 → lessons.md#chain-viz-required〕
6. **候选 leaderboard**(与 forward_picks 入库解耦):
   - **leaderboard 显示 top 15-20**(按决策相关性:🟢 优先、⭐ 节点优先、stage 健康优先;超出折叠成"其他 N 只 → forward_picks.csv")。
   - **forward_picks 入库无上限**:广扫到的 🟢🟡🔴 全入库,不允许"为视觉舒服而漏入库"。
   - **上游咽喉(①②③)** 与 **中游卖铲子(④⑧)** 分两档,按 stage 排序(early/basing-momentum 在前)。每只必含字段:
     - 代码+现价 · 档位/是什么 · 瓶颈逻辑(命中原型#) · 估值/增长 + **稀释红旗**(亏损+ATM/增发+现金跑道短=标红) · **动量条**(6 月区间位置 + 1m/3m,颜色=stage) · **三档判定 🟢/🟡/🔴** · **目标价/时间框架** · **`.why` 块**(20-40 字人话) · 风险。
     - **🟢/🟡 必含「反向研究」块**(见下 Tier-1 §A) · **🟢 必含「证伪条件」块**(见下 Tier-1 §B) · **🟡 必含重估触发条件**。
7. **Step5 三道闸门**:🔒真瓶颈 / 👁️前机构 / 💰便宜去风险,逐关诚实打分(过/半过/不过)。
8. **跨主题信号区块**:当前主题命中的 ⭐ 节点(来自 `cross_theme_index_snapshot.csv`)。
9. **已知玩家全集 audit 块**:列全球+全市场已知玩家,显式标 covered/private/acquired/delisted/untracked。
10. **落地结论 + 数据备注 + 免责页脚**。
11. **底部 glossary 折叠速查表**(JS 自动从 `<abbr>` 抽取)。

### Tier-1 §A · 反向研究 / 红队(🟢🟡 候选强制,缺失或敷衍 = 报告不合格)
每个 🟢/🟡 候选必带一段红队,**不许写"风险:估值高"这种套话**。四问 + 一句最大杀点:
```
反向研究 · 杀死这个候选的最短路径
① 为什么可能不是真瓶颈?   → 谁能绕过 / 替代方案进度
② 瓶颈为什么可能不变现?   → 收入纯度 X% / 下游议价能力 / 毛利能否扩
③ 市场是否已定价?         → 【强制引用 price.py 的 off-high / 1m / 3m 数字对账,不许空谈】
④ 有没有更优替代?         → 必须点名一个对比标的 XXX.XX(且过 price.py / ticker 验证)
最大杀点(一句):________ （必须区别于"估值高/竞争加剧"的通用风险）
```
**牙齿**:③ 必须引用我们已拉到的 9 字段数字(off/1m/3m 就在 scan JSON 里,逼对账);④ 必须点名一个真实存在、可验证的对比 ticker。

### Tier-1 §B · 证伪条件(🟢 候选强制)
每个 🟢 必带 2-4 条**具体可检验**的"什么会证明我错了",**至少一条是价格/stage 机器可读**(供 score_tracker 自动监控):
```
证伪条件(满足任一即承认判断错):
· 价格/stage:跌破 ¥X(entry)且 1m 转负        ← 机器可检,写进 forward_picks 的 invalidation 列
· 基本面:下季度订单/backlog 未随主题增长
· 估值:涨到 PS > 行业 +1σ 但毛利未扩
```
**牙齿 + 闭环接口**:至少一条要能落成机器规则(stop 价 / stage 失效),写进 `forward_picks.csv` 的 `invalidation` 列;`score_tracker` 重拉价时自动检查"证伪触发没有"。**没有证伪条件的 🟢 = 故事不是投资假设。**

- **目标价/时间框架**:给情景区间 + 时间框。⚠️ **基准率随主题而变,切勿套用光子学数字**:高 beta 快速点燃(光子学 2-6 月 +150~1000%)vs 慢周期政府驱动(航天/电网 1-3 年 +30~150%)完全不同。按当前主题 beta 与催化剂节奏设定,显式标"情景非承诺、有幸存者偏差"。
- **三档判定**:每只必标 🟢/🟡/🔴(详见 methodology.md §7)。
  - 🟡 **必填重估触发条件**(价格点/财报指标/公司动作/政策事件)。
  - 🔴 **极度克制**:只用于商业模式作假/欺诈/业务死亡/个人原则。**严禁"历史事件式硬排除"**——"曾经重组/增发过"是过期信息,"1m 涨太多"是 stage 问题(降 🟡 等回调)。例:`$WOLF` 重组后是 NewCo,业务逻辑可独立评估 → 🟡 观望 + trigger,不永久排除。
- **可读性纪律**:语义化三档配色(🟢green/🟡amber/🔴red)、动量条让"谁已抛物线"一眼可见、清爽留白。
- **术语友好度**:① 顶部"30 秒看懂"块;② 每个 🟢/🟡 候选加 `.why` 一行(20-40 字人话);③ 专业缩写首次出现用 `<abbr title="中文解释">缩写</abbr>`,来源 `reference/glossary.md`(120+ 条),新术语先 append 再用;④ 底部 `<details class="glossary-section">` 折叠速查表,JS 自动从 `<abbr>` 抽取。

**页脚必带**:⚠️ 仅供研究教育,非投资建议;估值为网页研究近似值需复核;微盘/诉讼/海外标的风险极高。

---

## 数据来源与边界

- **价格/动量(择时)**:统一走 `scripts/price.py`,自动回退 **① EODHD(`EODHD_API_KEY`)→ ② yfinance → ③ 都失败=报错退出**。Key 从环境变量读、不硬编码。**WebSearch 仅用于公司基本面/定性研究,不用于抓价格**。
- **EODHD 取不到**:fundamentals(估值/增长/毛利率/市值)、screener、财报日历 → 用网页研究逐只补。
- **瓶颈/单源/产能/客户**等定性判断:靠财报+行业资料+新闻研究。

## 参考文件
- `reference/lessons.md` —— **翻车档案 / 纪律的由来**(每条纪律对应一次真实事故,SKILL.md 用 `〔… → lessons.md#锚点〕` 指向)
- `reference/methodology.md` —— 完整方法论(理念、筛选清单、两套择时、回避清单、风险)
- `reference/supply-chain-and-archetypes.md` —— 元框架、产业链速查表、**Part D 9 大瓶颈原型库**、EODHD 数据映射
- `reference/report_template.html` —— **HTML 报告骨架 + 配色模板**
- `scripts/render_report.py` —— **报告统一渲染引擎**(克隆合格报告外壳 + 数据驱动渲染真 chain-viz / 标尺三价 / §A§B / forward_picks;agent 只写薄主题 SPEC,示例 `examples/demo_spec.json`)
- `scripts/verify_report.py` —— **交付契约 linter**(报告生成后必跑;查区块齐全 / §A§B / 标尺三价 / 价格对账 scan / 入轨 forward_picks / 真 chain-viz / 揭示类脚本 / 占位符,有【拦】先修再交付)
- `reference/example_commercial_space.md` —— worked example(商业航天),示范分析内容与颗粒度
- `reference/glossary.md` —— **术语库**(120+ 条,LLM 自动 enrich);报告 `<abbr>` 注释来源
- `reference/company_desc.md` —— **公司业务描述库**:只存 business(主营/产业链位置/技术/客户),**严禁含 price/stage/估值等动态数据**。格式 `- **SYM.EX** [YYYY-MM-DD] = 业务描述`,每条带 last_updated 时间戳。
  - **拆分**:🟢 business(本文件 + `.cnode[data-desc=]`,带时间戳)/ 🔴 status(`.cnode[data-status=]`,price/stage,每次重写带 `[YYYY-MM-DD]`)。
  - **90 天 freshness**:用 data-desc 前查 last_updated,≤90 天直接复用,>90 天重新评估战略漂移(有变更新+bump,无变只 bump)。工具 `tracking/check_desc_freshness.py`。〔三次迭代史 → lessons.md#company-desc-evolution〕
- `reference/ticker_truth.csv` + `reference/TICKER_HYGIENE.md` —— ticker ground-truth 库 + L1/L2/L3 防御文档
- `tracking/forward_picks.csv` —— 向前(样本外)跟踪表(带 `invalidation` 证伪列)
- `tracking/score_tracker.py` + `tracking/theme_benchmark.csv` —— **Alpha 打分**(🟢-vs-🔴 内部对照为主、vs 主题 ETF/大盘为辅)
- `tracking/cross_theme_scan.py` + `tracking/cross_theme_index_snapshot.csv` —— 跨主题节点扫描(Step 4 末尾强制跑)+ 快照

## 验证状态(诚实说明)
- **逻辑自洽性(已做,非业绩回测)**:套到 Serenity 研究过的"AI 光子学"能重建其名单(AXTI/SIVE/LITE/TSEM/SOI/IQE/AEHR…);套到他没碰过的"AI 电力散热"能独立挖出 $CLF(GOES 电工钢独家)、$CC(浸没冷却液单源);"商业航天"挖出 $VNP/5N+($MTRN)。→ "拆链 + 原型"逻辑能指向真实瓶颈公司。
- **⚠️ 这不是业绩回测**:此前"光子学首 call 后 +X%"存在**选股循环论证(用已知赢家倒推)、幸存者偏差、峰值未来函数**,不能当收益预期。
- **唯一可信的是向前(样本外)验证 + Alpha**:对当下产出的候选,记录"建议日 + 当时价 + 事先定死的进出场/证伪规则",日后用 `score_tracker` 重拉价。**关键纪律**:量 **Alpha = 标的收益 − 主题 ETF 同期收益**(牛市里随便选上游小票也涨,raw return 看不出选股有没有 alpha);**最硬的检验是 🟢 篮子 vs 🔴 篮子内部对照**(同主题 beta 对消,差额 = 纯选股能力)。结论出来前,输出只当**研究线索**,不是业绩。**每次出新候选都追加进 forward_picks.csv。**
