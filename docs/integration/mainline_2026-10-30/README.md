# 主线回合与交付接入

本层对应用户授权的10个完整回合案例、规则基线和直接展示实验设计，另做训练目录迁移的必要路径修复。应用与结果见[主线报告](../../evaluation/mainline_2026-10-30/REPORT.md)，不另维护第二份进度清单。

- `before_snapshot.json`：修改前945个相关文件哈希、此前有效保护清单，以及旧训练目录到新目录的逐文件映射；映射后的初始不一致数为0。
- `authorized_source_changes.json` / `runtime_manifest.json`：有限运行文件的前后哈希与新增设计阅读模块。改变目标/设计时重查单位及依赖，不授权真实执行。
- `support_source_changes.json`：回归开始时校验、测试及文档的授权变更说明；`documentation_followup.json`追加最终链接和指南修改的哈希链，不回写测试源证据。
- `full_tests.json`：本轮实际测试范围、结果和输入哈希；不合并历次重叠样本。
- `verification.json`：当前完整性、离线案例及交付制品检查。便携检查另保存在 `.local/checks/repository_check.json`。

旧保护清单和此前集成JSON保持原字节；目录迁移只改变最终解析位置。迁移后的数据/权重仍按旧哈希校验，不能借迁移覆盖权重。新增篡改检查覆盖运行模块、训练制品、历史记录和不合法路径映射。

`scripts/verify_dynamic_upgrade.py`、`verify_interfaces.py`、`verify_question_tool.py`、`verify_branding.py`、`verify_context_choices.py` 的默认当前验收链转到本层，保留旧回执。专门针对旧版本的历史审计不表示当前源码仍逐字等于旧版。

```powershell
& '.\RUT_Science\.venv\Scripts\python.exe' -B scripts/verify_planning_mainline.py
# 需要实际重跑当前应用及完整性/评分测试时：
& '.\RUT_Science\.venv\Scripts\python.exe' -B scripts/verify_planning_mainline.py --run-tests
```

本轮没有模型请求、训练或真实实验。真人质量评分尚未采集；浏览器访问host和Computer Use本地管道不可用，视觉验收未完成。
