# 详细工具库：在线Harness与训练接入

20个已实现离线工具已进入原ToolRegistry，终端、HTTP消息和训练宿主方法共用同一工具契约与执行器。45项契约的其余25项仍按原状态处理：待实现、已有能力引用、人审或真实执行禁用，不冒充新增可调用能力。

## 从原入口使用

重启Science Bot：

```powershell
.\science-bot.cmd -Backend offline
```

聊天中输入：

```text
/tools
/tools list
/tools status
/tools call project_create {"title":"Darcy比较","objective":"仅离线模拟，检查方案与结论闭环"}
```

后续工具参数需使用实际返回的project_ref、plan_ref等64位引用。制品保存在当前会话`tool_library/objects`，不接受任意文件路径；其他会话无法直接复用这些引用。`/tools call`不调用模型，输出来自真实离线工具。

API模式下可让DeepSeek规划工具调用：

```text
/tools chat 请为Darcy方法比较建立一个合成离线示例，检查区组与响应指标，若需要修改则重新复核、对齐和冻结，随后编译核验工作流、对账、模拟、分析、结论复核和报告。不能把合成参数当作真实先导依据，信息不足时向我提问。
```

也支持“使用详细工具库：……”这一明确前缀。普通咨询、解释或提及工具名称不会自动授权该工具集合。`/tools chat`使用原GeneralProvider及本地API配置，消耗会话模型预算；未改动DeepSeek传输代码。

## 状态、预算与证据

- 新会话默认工具调用上限由12调整为40，支持多步闭环；旧会话保留原预算，不自动提额。模型请求／token上限保持原值，耗尽后应新建合理预算会话。
- 注册范围仅20个离线实现。执行仍经过参数校验、同会话制品、幂等key、预算、工作流／对账前置条件和原固定verifier。
- 原生函数Schema已提供给模型；在线tool_catalog返回45项名称／状态／用途摘要，避免重复整套Schema耗尽上下文。独立CLI仍可查询完整契约。
- 每次plan_patch产生新版本并清除旧复核／冻结的活动引用；旧复核问题通过review_resolve处理，不能直接绕过。
- job_run_mock的情景由宿主绑定，模型工具Schema不暴露该参数。默认null；操作者可在首次调用前显式使用`/tools scenario benefit`或`harm`设置夹具。状态进入模型上下文时情景被隐藏，防止预告结果。
- report_build要求工作流已核验、作业已对账并显式处理下一步。`/report`可读取详细工具报告，`/tools status`和HTTP状态可查看活动引用。
- API最终回答需引用当轮实际工具evidence_ref。模型可以提问，不得编造执行或科学结论；跨进程恢复会重新验证已保存制品哈希。

## 为下一步训练提供的入口

```python
from rut_science.science_bot.general.conversation import GeneralSession

session = GeneralSession.create(
    "path/to/training_sessions", backend="offline", limits={"tool_calls": 80}
)
result = session.execute_library_tool(
    "project_create",
    {"title": "training example", "objective": "offline tools only"},
    key="episode_001_step_000",
)
```

训练适配器可以把action映射到这里，复用同一注册表、预算、制品和证据。模型API的job_run_mock省略scenario，由宿主注入；宿主训练方法也可省略该参数或提供与宿主夹具一致的值。

v2已有23个候选action仍保持原协议和冻结副本，其中包括两个host交互动作；它们不等于20个工具名称。现有v2环境、奖励、采样记录和权重未改写。下一轮需要明确观察、mask、奖励和环境版本后再进行正式训练；本轮没有把旧PPO权重设为在线默认，也没有宣称在线LLM已获得RL提升。

## 实现与验证

新增`general/tool_library.py`负责注册、命令、API规划及状态；`Research_Tool_Library/online_worker.py`在隔离进程复用原core、catalog和G2.4数学实现，只将Store绑定到宿主会话。原离线CLI、v2训练副本和既有权重保持不变。

验证覆盖20项注册范围、Darcy／CViT各21步实际闭环、会话隔离、幂等、预算、篡改恢复、宿主情景隐藏、模型原生tool_calls和现有HTTP messages。模型规划测试使用模拟模型返回，没有发起真实DeepSeek请求；离线工具与工作流实际执行。

验收及授权源码变更见[接入记录](integration/tool_library_2026-10-28/README.md)。真实Darcy拟合、CViT/GPU训练、shell和源码编辑仍不属于本工具集合。
