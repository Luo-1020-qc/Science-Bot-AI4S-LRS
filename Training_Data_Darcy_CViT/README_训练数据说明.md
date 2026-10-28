# Harness训练数据入口

当前仅维护 **v2 / tool_harness_rl_v2**。弃用的v1及根目录重复兼容树已经删除；不会删除或改写仍在使用的模型权重。

## 阅读顺序

1. [专家交接文档](RL训练数据_专家交接文档.md)：任务、标注、DOE审阅、导入和预检。
2. [v2数据协议](v2/README_可训练数据集.md)：环境、动作、奖励及PPO边界。
3. [Darcy完整示例](v2/examples/darcy_full_example.json)／[CViT完整示例](v2/examples/cvit_full_example.json)。
4. [可运行示例批次](v2/sample_batch_001/README.md)与[tasks展开注释](v2/sample_batch_001/tasks_展开注释.jsonc)。
5. [版本入口配置](current_dataset.json)与[当前验收](v2/delivery_verification.json)。

基础v2包含12个任务、134个参考决策、86条脚本BC参考标签、31条待审决策。独立示例批次另含3个合成任务、30个参考决策和96步PPO采样。真人专家标签仍为0，没有独立盲测或泛化提升证据。

参考轨迹用于示范和BC，行为概率及value保持null；PPO必须通过当前策略重新交互采样。本地已保存64步基础链路检查和96步示例检查的更新前后参数，默认在线策略未改变。

在项目根目录运行：

```powershell
& '.\RUT_Science\.venv\Scripts\python.exe' -B 'Training_Data_Darcy_CViT/validate_current.py' --tests
& '.\RUT_Science\.venv\Scripts\python.exe' -B 'Training_Data_Darcy_CViT/v2/sample_batch_001/verify_sample.py'
```

专家扩展与正式训练须遵守交接文档中的来源分区、审阅和预检要求。新增设计家族与任意参数生成需要工程侧先扩展环境。
