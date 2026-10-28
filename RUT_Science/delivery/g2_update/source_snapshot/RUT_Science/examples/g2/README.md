# G2 合成示例

本目录提供独立两组、配对测量及预测比较三个合成场景，不是实际科研结论。

在 `LangGraph_RL_Agent` 根目录：

```powershell
.\science-bot.cmd -Backend offline -Workspace 'RUT_Science\examples\g2'
```

在终端内输入以下任意设计，检查后确认：

```text
/design independent_design.json
/confirm
/report
```

另两个设计文件是 `paired_design.json` 和 `prediction_design.json`，每项单独生成并确认。默认工具预算12次；建议每个预测演示使用新会话。

API模式可以使用自然语言：

```text
请为 prediction.csv 设计预测比较，比较均值基线与OLS。response=y，unit=id，features=[x1,x2]。数据为合成 synthetic。sampling_note=全部现有合成样本，仅作探索性演示；未进行事先功效计算。alpha=0.05，seed=42。
```

数据由固定种子20261022生成；分析划分种子默认为42。生成脚本只补齐不存在的示例文件，不覆盖已有修改。列名、来源、单位和样本依据须按实际任务修改，不能把示例声明直接套用到真实数据。

完整约束见[使用说明](../../docs/Science_Bot_G2_表格与实验设计_zh.md)。
