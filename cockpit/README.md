# Serenity Cockpit · 可选本地驾驶舱

本模块随 **v0.2.0 同号更新版（cockpit-r2）** 提供。核心技能可继续独立使用，不需要安装或运行驾驶舱。本次不包含龙头视角。

驾驶舱用于管理和复盘研究成果：主题地图、机会列表、报告阅读、标的筛选、K 线判定标注、价格快照、触发条件核对、计分卡、阶段看板和跨主题矩阵。它不代替基本面研究，也不把历史演示转成当前推荐。

## 同号替换说明

此版本按维护者要求替换先前的 v0.2.0，旧下载不会自动更新。请重新下载附件并核对新的 SHA256SUMS.txt；manifest.json 中应有 `revision: cockpit-r2`。使用 Git 的用户可更新 main；如果固定使用旧 tag，可明确执行 `git fetch --force origin tag v0.2.0` 更新该本地标签。此前核心版源码仍可通过提交 `58ae022` 查看。

## 用发布包体验

推荐 Python 3.12。解压完整 ZIP / `.skill` 后，在技能根目录执行：

```bash
python -m venv .venv
# 在自己的项目环境中安装；不会改变系统 Python。
.venv/bin/python -m pip install -r cockpit/requirements.txt
.venv/bin/python cockpit/run.py
```

Windows PowerShell 对应命令：

```powershell
py -3.12 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r cockpit\requirements.txt
& .\.venv\Scripts\python.exe cockpit\run.py
```

打开 `http://127.0.0.1:8000`。按 `Ctrl+C` 停止服务；端口已占用时可追加 `--port 8001`，不会结束其他程序。

请下载 Release 附件中的 `serenity-bottleneck-hunter-v0.2.0.zip` 或 `.skill`；GitHub 自动生成的 Source code 压缩包属于源码版本。发布包已包含前端构建产物，日常运行无需 Node.js。`--check` 仅检查配置与前端文件，然后退出。

## 默认演示的边界

首次启动使用 `cockpit/demo/`：两条原已公开的历史快照、一个演示报告及示范分类。数据截至 **2026-06-01**，页面始终显示演示标记。

- 不调用行情服务，不启用定时任务，不写入演示目录。
- 演示没有逐日日线或同期基准，所以 K 线页明确提示缺少历史序列，计分卡不展示收益率或 α。
- “猎手／覆盖”切换的是显示范围，和龙头视角无关。
- 字体可能访问 Google Fonts；字体不可用时使用系统回退。这里的离线指研究数据与行情请求，不要求外部数据接口。

## 接入个人研究

先创建一个新的空目录（已有内容会被保护，不会覆盖）：

```bash
python cockpit/run.py --init local-data
python cockpit/run.py --data-dir local-data
```

使用项目虚拟环境时，将以上 `python` 替换为相应 `.venv` 中的 Python。目录结构：

```text
local-data/
  tracking/forward_picks.csv              # 自己的带日期研究记录
  tracking/theme_taxonomy.csv             # 主题分类，可留空，仍能使用跟踪表和报告库
  tracking/cross_theme_index_snapshot.csv # 按自己的记录生成的星级
  reports/*.html                         # 自己的报告
  reports/catalog.json                   # 可选：报告日期、主题、市场
  reference/ticker_truth.csv              # 可选：自己的真值表；缺省读取公库已有真值库
  .env                                   # 可选：自己的 EODHD 密钥
  .cockpit/                              # 本机运行时产生的价格、告警、处理状态
```

报告生成 SPEC 的 `out` 指向个人目录下的 `reports/`，`tracking_file` 指向个人目录下的跟踪 CSV。示例输入格式见根目录 `examples/demo_spec.json`。不要把演示的 `demo:true` 当成真实研究的标签。

也可通过 `SERENITY_DATA_DIR` 环境变量指定个人目录。路径必须明确提供且包含 `tracking/forward_picks.csv`；不会自动搜索任何相邻私库。页面会显示“个人研究”。尚未分类的记录可在“覆盖”镜头查看；补齐主题分类后，按原有规则进入对应地图和“猎手”范围。

新增研究后，按同样规则为个人目录重建跨主题星级（不联网，也不改写研究记录）：

```bash
python tracking/cross_theme_scan.py --input local-data/tracking/forward_picks.csv --output local-data/tracking/cross_theme_index_snapshot.csv
```

选择个人目录后，“同步股价”、K 线查询和手动告警核对才会联网，可能消耗数据服务额度；使用公库根目录的价格工具及同样的数据质量提示。A 股可选依赖见 `reference/DATA_SOURCES.md`。新增记录后旧收益快照会提示刷新，不按 CSV 行号错配。

定时任务默认关闭。需要时在个人环境中明确设置 `SERENITY_SCHEDULER=1`，启用每日本地时间 16:30 的告警检查；同时设置 `SNAPSHOT_AUTO=1` 才启用 16:40 全量价格快照。本机服务需保持运行。

## 数据与运行边界

代码、演示和个人记录分别保存。发布包只收录明确列出的程序与演示文件；`.env`、`local-data/`、`.cockpit/`、依赖和运行日志不进入包。原私库研究资产不随本模块发布。

服务仅监听 `127.0.0.1`。本版没有公网登录、远程协作或云端部署流程。修改操作和取价接口由本机驾驶舱调用；自行使用 API 时需带 `X-Serenity-Request: cockpit` 请求头。

## 从源码开发

源码仓库不提交前端构建目录。需要 Node.js 22.12+（建议 24）：

```bash
python -m pip install -r cockpit/requirements-test.txt
npm --prefix cockpit/web ci
npm --prefix cockpit/web run test
npm --prefix cockpit/web run build
python -m unittest discover -s cockpit/tests -v
python cockpit/run.py --check
python cockpit/run.py
```

开发前端可运行 `npm --prefix cockpit/web run dev`，它把 `/api` 代理到本机 8000 端口。正式发布包使用 Python 服务同时提供前端与 API，无需启动两个服务。

重新制作完整发布包：`python scripts/build_release.py --smoke --cockpit-smoke`。包内含完整源代码、预构建页面和依赖清单，不包含 Python 或 Node 运行时。
