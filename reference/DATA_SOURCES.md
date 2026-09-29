# 数据来源与 A 股使用说明（v0.2）

行情、估值和产业链证据是三条独立链路。取得价格不代表已经证明公司身份或投资论点。

## 行情

| 市场 | 默认顺序 | 输出来源标识 |
| --- | --- | --- |
| A 股（沪深京） | AKShare 前复权；沪深再尝试 Yahoo；最后可用 EODHD 显式复权字段 | `akshare-qfq` / `yfinance-qfq` / `eodhd-adj` |
| 美股、港股及其他支持市场 | 有密钥时 EODHD，再尝试 Yahoo | `eodhd-adj` / `yfinance-adj` |

传入规范代码，例如 `NVDA.US`、`0700.HK`、`300579.SHE`、`600000.SHG`。转换仅发生在供应商接口：Yahoo 美股去掉 `.US`，沪深转换为 `.SS` / `.SZ`；港股保持原后缀。北交所不假定 Yahoo 可用。

EODHD 的原始 OHLC 与 `adjusted_close` 口径不同。工具使用其明确返回的 `adjusted_close / close` 因子统一 OHLC；字段缺失时拒绝混合原始与复权序列。依据：[EODHD 接口说明](https://eodhd.com/financial-apis/api-for-historical-data-and-volumes)。

AKShare 明确请求 `adjust="qfq"`；Yahoo 明确请求 `auto_adjust=True, repair=False`。工具不凭单日跳空自行推断拆股、除权或修正历史价格。依据：[AKShare 日线文档](https://akshare.akfamily.xyz/data/stock/stock.html)、[yfinance 历史数据实现](https://github.com/ranaroussi/yfinance/blob/main/yfinance/scrapers/history.py)。

复权因子由供应商提供，并非本项目独立验证过的公司行动。A 股回退到 EODHD 时会保留质量提醒。非有限值、非正价格和非法 OHLC 被排除；冲突的同日记录拒绝使用。少于 126 个交易日会提示区间样本不足。真实涨跌不因为幅度大而被改写。

供应商可能限流、停机、覆盖不全，网络代理或证书配置也可能导致失败。不能保证所有 A 股随时可取；失败时保留缺失，不通过关闭证书验证或手填价格补齐。观察 `last_date` 与 `quality_warnings`，不要把程序运行日当成行情日。

## 估值

原有 `valuation()` 入口保留：A 股优先 AKShare 的 PE、盈利预测与财务摘要，缺字段再尝试 Yahoo；其他市场使用 Yahoo。预测 PE 取 **下一日历年**对应 EPS 列，找不到该列就保留缺失，不继续使用写死的 2026 年预测。

市盈率、盈利预测、增长率可能采用不同口径，也可能缺失或过期；查看 `src` 并与公司披露交叉核验。价格成功不等于估值成功，更不等于通过研究闸门。

## 安装与密钥

离线演示和回归测试只需要 Python 3.10+ 与 Git（部分测试使用临时 Git 仓库）。联网工具另装依赖：

```bash
python -m venv .venv
# 激活自己的项目虚拟环境后：
python -m pip install -r requirements.txt
# A 股行情和估值：
python -m pip install -r requirements-ashare.txt
```

`requirements-lock.txt` 记录经过本轮安装验证的基础依赖版本；它不包含可选 AKShare。Windows 可直接用 `.venv\Scripts\python.exe`，macOS/Linux 可用 `.venv/bin/python`，无需改变全局 Python。

EODHD 密钥由用户自行提供。可设置 `EODHD_API_KEY` 环境变量；安装基础依赖后，价格工具也会读取本仓库 `.env`。证券搜索工具等旧入口使用环境变量。不要上传自己的 `.env`。

完整主题取价和评分会产生网络调用，可能消耗供应商额度；离线演示不会调用这些服务。

## 历史数据与升级

公库已有 `tracking/forward_picks.csv`、`scorecard.md` 和 scan 文件作为原公开历史档案保留，不自动扩充私库研究。读取它们时保留记录日与快照日，不能表述为当前推荐或最新绩效。

新研究可从 `examples/blank_tracking.csv` 开始，并在报告 SPEC 中设置 `tracking_file`。评分仍使用原有公式与种子排除规则；旧版原始价格缓存不与 v0.2 复权数据混用，新缓存仅在同一天、同一来源策略内复用。运行评分会重新抓取失效缓存，既有历史评分文件不会在升级时自动重算。
