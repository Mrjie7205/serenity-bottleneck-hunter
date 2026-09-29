# Serenity Bottleneck Hunter — a Codex & Claude Skill

[![GitHub stars](https://img.shields.io/github/stars/Mrjie7205/serenity-bottleneck-hunter?style=flat&logo=github)](https://github.com/Mrjie7205/serenity-bottleneck-hunter/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/Mrjie7205/serenity-bottleneck-hunter?style=flat&logo=github)](https://github.com/Mrjie7205/serenity-bottleneck-hunter/network/members)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Codex Skill](https://img.shields.io/badge/OpenAI_Codex-Skill-10a37f)](SKILL.md)
[![Claude Skill](https://img.shields.io/badge/Claude-Skill-d97757)](SKILL.md)

> Given an investment **theme**, this skill reverse-maps the supply chain to surface **overlooked upstream "bottleneck" stocks** — distilled from the *publicly shared* methodology of X/Twitter trader **Serenity (@aleabitoreddit)**.
>
> 给定一个投资主题,复用 X 博主 **Serenity** 公开分享的"供应链瓶颈逆向映射"方法,独立挖出被市场忽视的**上游瓶颈股**(而非抄他已喊过的票)。

## v0.2 · 核心工具、可复现示例与 A 股说明

保留原有七步研究方法、九大原型和判定阈值。本版修复独立目录运行、供应商代码转换、行情复权、报告元数据及提交校验；不包含驾驶舱或龙头视角扩展。

**先验证能跑通（Python 3.10+，不需要密钥或联网）：**

```bash
python scripts/run_demo.py
```

打开生成的 `reports/demo-report.html`。示例使用公库原已公开的 2026-06-01 历史快照，自动执行严格数字对账，并写到独立演示跟踪文件；它不改动正式历史表，也不代表当前投资判断。

- [查看演示 HTML（下载后用浏览器打开）](examples/demo-report.html) · [示例输入和复现说明](examples/README.md)
- [A 股／港股／美股的数据来源与安装](reference/DATA_SOURCES.md) · [完整更新日志](CHANGELOG.md)
- [下载 ZIP / .skill 发布包](https://github.com/Mrjie7205/serenity-bottleneck-hunter/releases/tag/v0.2.0)（解压后入口仍为 `SKILL.md`）

已有用户保留自己的研究 CSV、`.env` 和自定义报告。公开历史样本目前为 418 条，最新记录到 2026-06-12；旧 scorecard 和 scan 均为带日期的档案，不自动代表当前结果。真实取价、估值和评分另需安装依赖，并可能消耗数据服务额度。

## ⚡ 30 秒装上 / Quick start

### OpenAI Codex

macOS / Linux:

```bash
git clone https://github.com/Mrjie7205/serenity-bottleneck-hunter.git \
  ~/.codex/skills/serenity-bottleneck-hunter
```

Windows PowerShell:

```powershell
git clone https://github.com/Mrjie7205/serenity-bottleneck-hunter.git `
  "$HOME\.codex\skills\serenity-bottleneck-hunter"
```

安装后重新启动 Codex 或开启新会话，然后显式调用:

```text
使用 $serenity-bottleneck-hunter 分析「AI 数据中心电力」主题，给出候选标的和论证。
```

也可以自然语言触发:

```text
用 Serenity 瓶颈猎手方法分析「人形机器人」产业链，寻找被忽视的上游瓶颈股。
```

Codex 会从 `~/.codex/skills/serenity-bottleneck-hunter/SKILL.md` 读取工作流；仓库中的 `scripts/`、`reference/` 和 `tracking/` 会作为配套资源使用。

### Claude Code

```bash
# 克隆到个人 skills 目录,立即生效
git clone https://github.com/Mrjie7205/serenity-bottleneck-hunter.git ~/.claude/skills/serenity-bottleneck-hunter
```

然后在 Claude Code 里直接说:

```
用 Serenity 瓶颈猎手方法,分析「AI 数据中心电力」这个主题,给出候选标的
```

**claude.ai / Claude Desktop**:把仓库打包上传为 skill,或直接把 `SKILL.md` 拖进对话让 Claude 照着执行。

**价格数据(可选，先安装 `requirements.txt`；A 股另装 `requirements-ashare.txt`)**:`export EODHD_API_KEY=你的key`([EODHD](https://eodhd.com) 全球覆盖最广,海外股推荐);没有 key 时自动回退 yfinance(美股 OK)。**禁止用 WebSearch 猜价格** — 这是 skill 的硬纪律。

## 📊 输出长什么样 / Report anatomy

每个主题产出一份**自包含单文件 HTML 报告**(零依赖,浏览器直接打开,模板见 `reference/report_template.html`),从上到下:

| 区块 | 内容 |
|---|---|
| **一句话结论** | 开门见山:这个主题值不值得做、最佳切入点是什么 |
| **Step 1 · 资本开支确定性** | 3-4 个关键数字:谁在花钱、花多少、确定性来源 |
| **30 秒看懂** | 给非从业者的主题速览(术语友好度纪律) |
| **Step 2 · 产业链网状图** | 5 层逆向拆链,SVG 自动绘制依赖边,瓶颈节点**双规则自动判定**:漏斗型(入度≥2 出度≤1,金边)+ 枢纽型(入度≥2 出度≥2,多对多最难绕开,酒红边) |
| **⚑ 本次行动点** | 头条位:最多 2 张行动卡(设什么警报 / 什么条件做什么)无视排序置顶——读者 10 秒拿到本次唯一要做的事 |
| **Step 4-6 · 候选 leaderboard** | 核心区,每候选一行:🟢候选 / 🟡观望 / 🔴排除 + **水位标尺**(贴顶/高位/中位/低位/贴底 + 距高点% + 近1月/3月,人话化动量;**标尺两端标 6月低/高价、游标标现价**——定性+定量同在一根尺)+ **第二轴(估值×基本面)**(forward P/E 轨迹 / PEG / 盈利增速 / 板块内 RS → 把高水位分流成「贵但对=盈利撑住的龙头」vs「真贴顶=纯重估」,修正"水位单轴=均值回归伪装成动量"的偏差)+ trigger 分层(⚙ 可自动盯 / 👁 需人工)+ 行内三道闸小标 + **判定史**(同标的历史判定:旧价→今价±%、对错复盘);原型/基本面/情景/风险折叠进"详情",按 stage 从 early→extended 排序 |
| **⭐ 跨主题信号** | 本主题候选与其他已扫主题的交集 — 被多个 capex 周期同时锁定的 root 节点(⑤原型) |
| **Step 5 · 三道闸门** | 穷尽性 A / ETF audit A+ / ticker 验证 A++ 的逐项通过情况(过/半过/不过) |
| **Step 7 · 落地结论** | 仓位思路 + 触发器清单(什么条件下重估哪只) |
| **底部** | 数据备注(价格快照日期/来源)· 术语速查表(自动从正文抽取,默认折叠)· 引用链接 · 免责声明 |

报告中的每个 🟢🟡🔴 判定同步写入 `tracking/forward_picks.csv`(带日期锁定),供日后向前验证。

每份报告**交付前过 `scripts/verify_report.py` 契约校验**(区块齐全 / 每候选 §A、🟢 带 §B / 标尺三价齐 / 价格逐字段对账 scan / 入轨 forward_picks / 状态断言带日期 / 无占位符残留 / 折叠开合平衡),有【拦】先修再交付——把"分析做了但漏交付块、漏刷状态、漏入库"挡在交付前。

## What it does / 做什么

Theme → reverse supply-chain map → apply **9 "bottleneck archetypes"** → output a short list of overlooked upstream candidates with: thesis, archetype, valuation, entry-timing (Mode-A "buy early momentum, not the dip"), target/timeframe, and risks. The edge is being **early to the theme**, not chasing crowded names.

主题 → 逆向拆解供应链 → 套用 **9 大瓶颈原型** → 产出被忽视的上游候选 + 论点/估值/入场时机/目标价/风险。核心是**早于机构发现主题**,不追拥挤标的。

## 🛡️ 工程化纪律 / Engineering discipline

这个 skill 的差异点不只是方法论,是**把 LLM 的已知失败模式工程化拦截**。每条纪律都来自一次真实翻车,完整复盘档案在 [`reference/lessons.md`](reference/lessons.md)(SKILL.md 只留祈使句 + 锚点指针,保持执行路径干净)。分两条战线 —— **让数据可信** + **让判断可问责**:

**① 让数据可信(input trust)**

| 防线 | 防什么 | 工具 |
|---|---|---|
| **A 穷尽性** | 凭记忆列候选会漏(漏过 PANW/CRWD 级主仓) | 已知玩家全集 audit,显式标 covered/private/acquired |
| **A+ ETF audit** | LLM 的"知名度偏见" | `scripts/theme_etf_coverage.py` 拉主题 ETF 持仓做兜底 |
| **A++ ticker 双向验证** | LLM hallucination 错位(把 603297 永新光学当成绿的谐波,价格/判定全反) | `scripts/ticker_truth.py` ground-truth 库 + `verify_tickers.py` git pre-commit hook 自动拦截(累计抓出 4 个真错位)|
| **价格纪律** | 用 WebSearch/记忆猜价格 | `scripts/price.py` 强制 EODHD→yfinance,9 字段全留档,严禁手填 |
| **公司状态检查** | LLM 过期先验:私有→已 IPO(SpaceX 上市**当天**报告仍标"私有")/ 上市→被收购(SkyWater 被 IonQ 买走) | 判定前强制搜一次 acquisition/IPO 状态;状态断言必须带日期 |

**② 让判断可问责(judgment accountability)** — 把 skill 从"找理由买"逼成"先想怎么会亏"

| 防线 | 防什么 | 工具 |
|---|---|---|
| **§A 反向研究/红队** | "故事越讲越顺"(主题投资头号死法)| 每个候选强制四问 + 最大杀点;"是否已定价"必须引用 price.py 真实数字对账 |
| **§B 证伪条件** | 🟢 只有多头故事、没有"什么证明我错了" | 每个 🟢 必带可检验证伪,≥1 条机器可读 → 写入 `forward_picks.csv` 的 `invalidation` 列 |
| **Alpha 反馈闭环** | 事后吹回测 / 牛市里随便选都涨 | `score_tracker.py` 量 **Alpha = 标的 − 主题 ETF**(非 raw return);最硬的是 **🟢 篮子 vs 🔴 篮子内部对照**(主题 beta 对消)|
| **防循环论证** | 把回填的已知赢家算进"向前业绩"(曾把均α 灌水到 +90%,真实值为负) | 标 `历史种子` 的回填行强制从一切统计中剔除 |
| **二轴判定(水位 × 估值)** | 热门板块里"水位单轴"会把刚突破的真龙头误杀成 🟡(均值回归伪装成动量) | 高水位不自动 🟡——按 forward P/E 轨迹/PEG/盈利增速/RS 分流「贵但对」vs「真贴顶」;估值多源(A股 `akshare` + 美股 `yfinance`)+ sanity 层拦异常值。曾踩:yfinance 错 forward 把华正误判 🔴,接 akshare 纠为 🟡 |

## Use / 用法

- **Codex Skill**: clone this repository into `~/.codex/skills/serenity-bottleneck-hunter`, start a new session, then invoke `$serenity-bottleneck-hunter`.
- **Claude Skill**: clone it into `~/.claude/skills/serenity-bottleneck-hunter`, then ask Claude to analyze an investment theme.
- **Manual use**: point a compatible agent at `SKILL.md`.
- 进阶:跨主题取交集找"被多个 capex 周期同时锁定"的标的(Serenity ⑤原型),见 `tracking/cross_theme_scan.py`。

## Structure / 结构

```
SKILL.md                         # 主流程:主题→挖股 7 步 + 两套择时 + 输出模板(§A 红队/§B 证伪)
reference/
  lessons.md                     # 翻车档案:每条纪律对应一次真实事故(SKILL.md 用锚点指过来)
  methodology.md                 # 方法论(理念/筛选清单/两套择时/回避清单/风险)
  supply-chain-and-archetypes.md # 元框架 + 产业链速查表 + 9 大瓶颈原型库
  example_commercial_space.md    # 完整 worked example(商业航天)
  company_desc.md                # 公司业务描述库(带时间戳,90 天 freshness)
  ticker_truth.csv               # ticker ground-truth 库(L1,防 hallucination 错位)
  TICKER_HYGIENE.md              # L1+L2+L3 三层防御使用文档
scripts/
  price.py                       # 价格/动量(EODHD → yfinance 回退,严禁猜价)
  theme_etf_coverage.py          # ETF 持仓穷尽性 audit(A+ 防漏)
  ticker_truth.py                # ticker 验证/解析 API(L2)
  verify_tickers.py              # git pre-commit hook 扫描器(L3)
  render_report.py               # 报告统一渲染引擎(克隆合格报告外壳 + 数据驱动真 chain-viz/标尺/§A§B;agent 只写薄主题 SPEC,报告没法手搓/降级)
  verify_report.py               # 交付契约 linter(报告交付前必跑:区块/§A§B/标尺三价/价格对账/入轨/真 chain-viz/揭示类脚本)
tracking/
  forward_picks.csv              # 向前(样本外)验证:带日期锁定的候选记录 + invalidation 证伪列
  theme_benchmark.csv            # 主题 → 基准 ETF 映射(算 Alpha 用)
  score_tracker.py               # Alpha 打分(🟢-vs-🔴 内部对照 + vs 主题 ETF + 证伪触发检查)
  scorecard.md                   # 最近一次打分结果(诚实标注样本不足)
  cross_theme_scan.py            # 跨主题节点矩阵(⭐ 跨 capex cycle 信号)
```

## Data / 数据

- **Price & timing**: `scripts/price.py` 按市场选择来源并统一到供应商提供的复权口径，见[数据来源说明](reference/DATA_SOURCES.md)。A 股先尝试 AKShare 前复权，再尝试 Yahoo 和 EODHD；其他市场使用 EODHD→Yahoo。所有返回均标明来源，覆盖和网络可用性不作保证。**WebSearch 一律不用于抓价格——猜测视为流程错误**。
- **Valuation(二轴的第二轴)**: `scripts/price.py` 的 `valuation()` 多源 —— **A股 → akshare**(百度 PE-TTM + 东财券商一致预期算 forward + 东财财务增速)· **美股 → yfinance** · 缺字段互兜底 · 带 `src` 可交叉验证。估值是全 skill 最弱的数据(单源不可信),故 A股改用中国源 + sanity 层拦小基数算爆的异常值(如 +610% 增速、749x trailing)。
- **Fundamentals & bottleneck judgment**: web research per candidate — the skill's real edge is qualitative (is it a true single-source chokepoint?), which no data feed provides.

## Validation honesty / 验证说明

The only credible test is **forward / out-of-sample**: see `tracking/forward_picks.csv` (dated, rules-locked picks) + `tracking/score_tracker.py` (re-pulls prices later and scores them). Any in-sample "backtest" suffers look-ahead & survivorship bias and is **not** a performance claim.

**打分纪律(score_tracker)**:

- 量 **Alpha = 标的收益 − 同期主题 ETF**(`theme_benchmark.csv` 映射),不量 raw return —— 牛市里随便选个上游小票也涨,raw return 看不出选股有没有 alpha。
- 最硬的检验是 **🟢 候选篮子 vs 🔴 排除篮子内部对照**:两篮共享同一主题 beta,差额 = 纯选股能力,不依赖任何外部基准。
- ⚠️ `forward_picks.csv` 里含 **`历史种子`** / record_date ≤ 2026-02-01 的行是回填参照锚点(Serenity 原始 call,2026-01-02 价),**做任何业绩统计必须剔除**——混入即循环论证(我们踩过:含种子时 🟢 均 α 灌水到 +90%,剔除后真实样本为负且观察期未满)。真实向前基线自 **2026-05-26** 起算。
- **样本期太短 + N<30 → 当前只装仪表、不下结论。** 可信度由时间长出来,不由功能加出来。

## ⚠️ Disclaimer / 免责声明

- **Not financial advice — educational / research use only.** / **非投资建议,仅供研究教育。**
- This project distills a **methodology** from Serenity's public posts. It does **not** redistribute his content and is **not affiliated with, sponsored by, or endorsed by** him. / 本项目只提炼其**公开方法论**,不转载其原始内容,与本人**无任何关联或背书**。
- Any "validation" inside is **logic-consistency + forward tracking**, NOT an audited performance record. Markets are risky; do your own research. / 文中"验证"为逻辑自洽 + 向前跟踪,**非经审计的业绩**。投资有风险,务必独立判断。

## License / 协议

MIT (see `LICENSE`). Methodology credit: **Serenity (@aleabitoreddit)** — this is an independent, fan-made distillation of publicly shared ideas.

## 开发与验收

```bash
python -m unittest discover -s tests -v
python scripts/run_demo.py
python scripts/build_release.py --smoke
```

这些检查使用离线输入。GitHub Actions 在 Windows / Linux 验证核心测试，并检查发布包在新目录解压后可运行。价格源实际可用性需另行抽样，离线通过不等于全市场实时数据通过。

可选提交钩子：`python scripts/install_pre_commit.py`。它只安装当前仓库的校验入口；已有钩子或自定义 hooksPath 会保留，并提示手动接入。
