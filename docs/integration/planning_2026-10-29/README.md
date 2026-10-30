# 持续研究规划的接入与完整性

用户于2026-10-29明确授权升级Harness架构，同时保持DeepSeek API接口和既有工作。授权修改四个宿主文件：general/graph.py、general/router.py、general/conversation.py、science_bot/terminal.py；新增planning下五个模块。provider.py与configuration.py要求哈希不变。

`before_snapshot.json`保存改前有效哈希及旧清单哈希。新的授权清单链接到前一轮工具接入或清理基线的有效哈希，不重写旧历史。新运行时清单只接受明确文件集合，旧工具运行时中的宿主文件按授权链验证。

`scripts/integrity.py`与`verify_cleanup.py`改用链式有效哈希；已有数学工具、研究副本和旧权重仍按原哈希检查。`scripts/test_integrity.py`包含错误前驱、越权路径、旧历史、provider与权重篡改测试。

功能说明见[持续科研规划](../../HARNESS_PLANNING.md)。本轮检查结果写入本目录的verification.json；示例对话是合成程序场景，不能冒充人类专家审批或真实实验效果。
