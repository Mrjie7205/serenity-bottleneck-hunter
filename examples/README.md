# 离线历史演示

这是公库原已公开数据的工具演示。不是新研究、当前行情或当前投资建议。输入行情日期为 **2026-06-01**，报告日期为 **2026-06-02**。

在仓库根目录运行：

```bash
python scripts/run_demo.py
```

不需要密钥、不访问行情服务。生成 `reports/demo-report.html` 和独立的 `reports/demo_tracking.csv`，随后自动执行严格校验。可用 `--output /path/to/folder` 指定输出目录。主 `tracking/forward_picks.csv` 不会改变。

文件说明：

- `demo_scan.json`：从原公开 `tracking/_scan_AIAgent_v1.json` 摘取两条快照，补上原公开真值表中的公司名；来源记录在 `provenance.json`。
- `demo_spec.json`：可复制修改的最小完整报告定义。网络行情、资本开支、公司关系与估值需要在真实研究时另行验证。
- `demo-report.html`：由相同输入生成的可直接打开示例。
- `blank_tracking.csv`：只有表头的新研究跟踪模板。通过 SPEC 的 `tracking_file` 选择自己的档案，不覆盖公开历史样本。

示例图中的依赖边用于展示交互，不是商业关系声明。黄色标识展示版式，不是当前评级。历史快照采用旧版口径，不能用于证明新版复权数据正确；新版复权逻辑另有明确因子和真实跳涨的合成回归测试。

真实使用时沿用技能的主题、证据、红队和证伪流程。`demo: true` 只用于显式历史教学演示，不允许用来把虚构数字写成真实研究。
