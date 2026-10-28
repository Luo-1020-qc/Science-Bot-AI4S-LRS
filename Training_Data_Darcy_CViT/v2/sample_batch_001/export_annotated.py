"""Export a readable JSONC view without changing machine-consumed JSONL."""
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
COMMENTS = {
    "schema_version": "格式版本。当前固定为tool_harness_rl_v2，不自行改名。",
    "task_id": "任务唯一ID。专家修订任务时应明确版本，不复用已有ID覆盖历史记录。",
    "policy_split": "Agent任务分区。当前训练扩展只接受train；不能导入开发或评价来源。",
    "root_group": "来源分组。相同底层数据及改写、故障变体应保持同组，防止分区泄漏。",
    "data_lineage": "仅供数据管理和环境使用的来源元数据；不作为策略输入。",
    "source_ancestor_ids": "共同来源祖先。三例沿用训练来源A，不代表新增独立科学数据。",
    "scientific_partitions": "科学模型的数据划分，与上面的Agent任务分区policy_split不同。",
    "train": "科学模型拟合数据的来源引用；此处mock地址仅为合成声明，不是真实数组。",
    "validation": "科学模型选模或调参数据的来源引用，不得与封存测试混用。",
    "test": "科学模型最终评价数据的来源引用；不得用它反复调参或筛选方案。",
    "source_kind": "来源类型。synthetic_reference_only表示纯合成示例，不能当真人科学证据。",
    "public": "策略可以看到的目标与约束。不得填写未来模拟结果或期望动作答案。",
    "domain": "场景：darcy或cvit。当前有界环境不自动支持任意新领域。",
    "user_request": "用户研究问题：比较对象、实验范围、主要指标、约束和允许结论应写清楚。",
    "family": "设计家族：crd_two_arm两处理CRD；rcbd_two_arm两处理区组；factorial_2x2全因子。",
    "factors": "受研究的因素与水平。两处理设计一个因素；2×2设计两个因素。",
    "name": "因素名。需与主要检验项、方案和分析模型的命名保持一致。",
    "levels": "该因素的两个不同水平。当前协议使用字符串表示，包括学习率。",
    "unit_definition": "实验单位定义。区分处理分配单位、数据区组与测量点，避免伪重复。",
    "response": "主要响应名称。relative_l2是相对L2误差；不能与training_loss混用。",
    "primary_term": "主要检验项，如predictor或architecture；并非要求模型只保留该项。",
    "direction": "指标有利方向：lower越低越好，higher越高越好。比较方向还需与方案一致。",
    "practical_margin": "实际意义阈值；示例0.01。用于结论判断，不是显著性水平或p值。",
    "minimum_effect": "功效规划目标效应；示例0.02。用途不同于实际意义阈值，不能事后随结果调整。",
    "sigma": "标准差而非方差。0.02只是合成假设；未知必须填null，不能借用模板默认值。",
    "variance_source": "标准差依据。已知时说明来源与层级；sigma为null时此字段也为null。",
    "target_power": "目标功效；0.8表示80%。它是规划目标，不表示现实功效已验证。",
    "resource_budget": "模拟资源总预算。256不是独立样本量；运行成本与数量由当前方案工具核对。",
    "max_decisions": "Agent每回合决策上限，当前8～80；40不是实验重复数。耗尽属于任务终止。",
    "simulator": "环境私有模拟条件。不得整体交给策略，否则会泄漏初始缺陷或未来结果。",
    "initial_fault": "初始草案缺陷。wrong_model为错误模型，none为未注入该类缺陷；由环境布置。",
    "outcome_scenario": "模拟结局：benefit有利、null零效应、harm不利。只供环境使用，策略不能选择。",
    "user_variance_answer": "当前版本只支持null：缺失方差时，提问得到无法提供依据的回答；已知sigma应写入public。",
    "existing_job": "是否布置已有模拟作业。true时应先检查复用，避免无谓重复启动。",
    "job_failure": "null不注入此类故障；mock_oom表示模拟资源失败，不是真实GPU报错。",
    "expert_review": "当前加载器所需的审批字段。本批approved仅为自动化合成夹具许可，不代表真人科学审批。",
    "status": "approved允许此合成任务通过现有扩展加载器；不能据此把本批计入真人专家标注。",
    "reviewer": "实际审阅身份。本批明确是自动化作者而非人类专家；禁止伪造专家身份。",
    "reason": "批准范围与局限。本批仅批准协议兼容性示例，真实科学依据仍待专家审阅。",
    "reviewed_at": "带时区的审阅时间。保留实际记录，不把示例时间冒充新的审阅行为。",
}


def main():
    tasks = [json.loads(line) for line in (HERE/"tasks.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    lines = [
        "// tasks.jsonl的展开注释视图：每个字段独占一行，3个任务放在一个数组中。",
        "// 这是一份JSONC文件（带注释JSON），不能直接替换JSONL训练输入。",
        "// 原tasks.jsonl仍是机器读取的基准；本文件与原数据逐对象相同。",
        "// 正式专家数据须另行审阅。本批真人专家标签0，数值和结果均为合成。",
    ]
    for line in json.dumps(tasks, ensure_ascii=False, indent=2).splitlines():
        match = re.match(r'^(\s*)"([^"\\]+)"\s*:', line)
        if match:
            indentation, name = match.groups()
            if name not in COMMENTS: raise ValueError("Unannotated task field: "+name)
            lines.append(indentation+"// "+COMMENTS[name])
        lines.append(line)
    target = HERE/"tasks_展开注释.jsonc"
    target.write_text("\n".join(lines)+"\n", encoding="utf-8")
    # Comments are whole lines; do not strip // inside mock:// or URLs.
    plain = "\n".join(line for line in target.read_text(encoding="utf-8").splitlines() if not line.lstrip().startswith("//"))
    if json.loads(plain) != tasks: raise ValueError("Annotated view differs from original JSONL")
    print(json.dumps({"tasks": len(tasks), "annotated_fields": sum(bool(re.match(r'^\s*// ', line)) for line in lines),
        "identical_to_source_tasks": True, "original_jsonl_modified": False}, ensure_ascii=False))


if __name__ == "__main__": main()
