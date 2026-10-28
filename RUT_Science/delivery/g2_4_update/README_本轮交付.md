# G2.4 本轮交付

日期：2026-10-27。已交付 **DOE结构化协议、统一验收/评分、设计步骤与验收条件、待专家校准任务库及审阅管道**。原 `science-bot.cmd` 和研究入口保持，不新增ZIP。

实现与完整使用说明：[G2.4研究](../../research/strategy_learning/studies/g2_4/README_本轮交付.md)。技术入口：[DOE说明](../../docs/Science_Bot_G2_4_DOE协议与统一验收_zh.md)。

| 内容 | 本轮完成 |
|---|---|
| 闭合协议 | 请求哈希、来源、因素、单位、区组、随机化、模型、主要对比、功效、预算 |
| 有界DOE编译 | 两处理CRD、两处理RCBD、可带完整区组的2×2全因子 |
| 独立验收 | 矩阵秩和可估计性、单位去重、随机化计划、模型匹配、条件名义功效、来源与成本 |
| 实验步骤 | 证据→设计检查→预注册→外部审阅→收集→分析→报告，保存依赖和验收条件；执行未启用 |
| 统一语义 | 训练反馈、开发选择及后续最终评分调用相同函数；停止只接受当前公开证据 |
| 任务与审阅 | 84训练、42开发、42封存；42条训练案例待审；真人专家标签0 |
| 验证 | G2.4 49项测试；开发42/42符合合成参考预期；最终记录未用于评分 |
| 保护 | 原核心源码、数据、模型、配置、入口、论文和G2.2/G2.3制品保持哈希一致 |

统一研究复测覆盖G2.2的39项、G2.3的37项和G2.4的49项，共125项。最终总验收见 [verification.json](verification.json)，每轮原始日志位于各study的 `evidence/current_tests.log`。

本轮没有训练新策略、接入真实工具、调用模型API、运行真实CViT或启动GPU。开发诊断只验证脚本预期；不能解释为100%的专家认可度、独立泛化或学习策略提升。功效依据指定sigma和模型假设，真实独立性与模型适用性需要外部审阅。

使用现有解释器，在项目根目录执行：

```powershell
& '.\RUT_Science\.venv\Scripts\python.exe' -B 'RUT_Science/scripts/science_bot_research.py' test
& '.\RUT_Science\.venv\Scripts\python.exe' -B 'RUT_Science/scripts/science_bot_research.py' verify
& '.\RUT_Science\.venv\Scripts\python.exe' -B 'RUT_Science/scripts/science_bot_research.py' demo --study g2_4
& '.\RUT_Science\.venv\Scripts\python.exe' -B 'RUT_Science/delivery/g2_4_update/verify_delivery.py'
```

下一步：先取得独立专家审阅、校准有争议规则，再以新版本进行BC和状态聚合；PPO放在可靠基线之后。
