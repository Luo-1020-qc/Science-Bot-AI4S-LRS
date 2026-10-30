# 动态澄清接入与完整性链

用户于2026-10-29明确授权：在现有版本账本及校验上实现基于回答、未知、冲突的动态澄清，保留模板降级；接入显式选择的论文证据，使用独立任务评估追问、可检验计划和研究者理解。用户选择先以合成文献片段验证。

本轮修改 `planning/ledger.py`、`blueprint.py`、`runtime.py`，新增 `clarification.py`、`evidence.py`、`understanding.py`。随后仅在 `general/conversation.py` 补充规划回答的可重放历史摘要，防止本地证据显示进入普通聊天上下文。原启动器、DeepSeek transport/configuration、其余宿主接线、旧工具核心、RL环境、奖励、权重和封存结果不变。

- [before_snapshot.json](before_snapshot.json)：修改前保存3个模块哈希，并锁定8个历史清单/API文件；未回填或重写这些哈希。
- [authorized_source_changes.json](authorized_source_changes.json)：本次3个已有模块的before/after及授权原因。
- [runtime_manifest.json](runtime_manifest.json)：本次6个运行模块。
- [full_tests.json](full_tests.json)：最终全量应用回归412项，0失败/错误、2跳过，绑定本次runtime manifest及隐私覆盖层。
- [evaluation_display_patch.json](evaluation_display_patch.json)：在线评估后仅修复证据成功提示中的问题显示及只读浏览保留问题映射；核对反向补丁后恰好恢复评估源码，提问逻辑未改变。
- [历史隐私补丁before](history_privacy/before_snapshot.json)与[after](history_privacy/authorized_source_changes.json)：在修改会话宿主前单独保存原始哈希，未回填或改写前述3模块的before记录。
- [verification.json](verification.json)：核对当前文件、历史链、保留训练制品、测试记录和两组评估来源；不调用模型或训练。

此前 `planning_2026-10-29` 的before/after清单和66项专项记录保留为历史证据，不再用其旧测试数描述当前代码。`scripts/integrity.py`依次应用原清理、工具接入、旧规划、本次动态澄清四层；权重不在允许的源码覆盖范围内。

本次定稿使用 `scripts/finalize_dynamic_integrity.py`，然后执行全量回归及 `scripts/verify_dynamic_upgrade.py`。隐私层已绑定本次manifest，后续源码升级须追加新授权链，不修改本次before或封存哈希。一次性旧规划定稿和本机日志取证脚本已在文档精简中退役；历史清单与测试证据保留。当前核验不依赖旧本机演示日志，但保存的测试记录不能替代新机器实际重跑测试。

使用方式见[动态澄清说明](../../HARNESS_PLANNING.md)，完整正/负评估见[评估报告](../../evaluation/dynamic_clarification_2026-10-29/REPORT.md)。当前所有工作仍在本地，未提交或push。
