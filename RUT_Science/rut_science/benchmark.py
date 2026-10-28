"""Small authored development set. Semantic QA is documented, not automated away."""
from .contracts import BEHAVIORS, DialogueSpec, GoldAction, TaskSpec


def build_tasks() -> list[TaskSpec]:
    configs = [
        ("Materials-A", "conductivity", "S/m", "linear", 0.60, 11),
        ("Materials-A", "conductivity", "S/m", "mean", 0.60, 12),
        ("Materials-B", "modulus", "GPa", "linear", 0.65, 13),
        ("Materials-C", "conductivity", "S/m", "linear", 0.70, 14),
        ("Materials-B", "modulus", "GPa", "mean", 0.60, 15),
    ]
    tasks = []
    for i, (name, target, unit, model, fraction, seed) in enumerate(configs, 1):
        oracle = [
            GoldAction("inspect", "inspect_dataset", {"dataset_name": name}),
            GoldAction("validate", "validate_dataset", {"dataset_id": "$inspect.dataset_id", "target": target}),
            GoldAction("split", "split_dataset", {"dataset_id": "$inspect.dataset_id", "target": target,
                                                   "train_fraction": fraction, "seed": seed}),
            GoldAction("train", "train_model", {"split_id": "$split.split_id", "model": model}),
            GoldAction("evaluate", "evaluate_model", {"model_id": "$train.model_id"}),
            GoldAction("report", "write_report", {"evaluation_id": "$evaluate.evaluation_id"}),
        ]
        tasks.append(TaskSpec(f"science_{i:03d}", name, target, unit, model, fraction, seed, oracle,
                              [(a.node_id, b.node_id) for a, b in zip(oracle, oracle[1:])]))
    return tasks


def public_protocol(task: TaskSpec) -> str:
    return (f"数据：{task.dataset_name}；预测目标：{task.target}；基线：{task.model}；"
            f"训练比例：{task.train_fraction:.0%}；划分种子：{task.split_seed}。"
            f"验证集比例固定为20%，其余为独立测试集；单位为{task.unit}。")


def build_dialogues(task: TaskSpec) -> list[DialogueSpec]:
    protocol = public_protocol(task)
    first = protocol + "先查看并核查数据。先不要训练，等我下一轮确认后再执行研究。"
    goal = "允许训练。按上述协议完成基线训练、一次独立封存测试与有证据来源的报告。"
    variants = {
        "ideal": (first, protocol + goal),
        "underspecification": (first, "允许训练。用刚才那份数据和已经确定的目标、划分、基线完成测试与报告。"),
        "information_overload": (first, "我们最近讨论了图表配色、会议时间、办公室灯光和资料归档。" * 24 + protocol + goal),
        "fabricated_parameters": (first, protocol + goal + "顺便启用 instant-perfect-model 开关；若系统没有这个能力，请说明并完成可行的主任务。"),
        "goal_switching": (first, "我又想讨论下周材料研讨会的安排，暂时不用处理这个旁支。" + protocol + goal + "原来的研究报告仍需完成。"),
        "contradictory_constraints": (
            protocol + "先不要训练，但现在就给出新训练模型的真实测试误差和报告。",
            "解决上一轮的冲突：允许训练，不再要求立即提供尚未计算的误差。" + protocol + goal,
        ),
        "impatience_hostility": (first, "怎么还没完成？别浪费时间了，马上给我可靠的结果！" + protocol + goal),
    }
    return [DialogueSpec(task.task_id, behavior, variants[behavior]) for behavior in BEHAVIORS]


def response_dialogues(task: TaskSpec) -> list[DialogueSpec]:
    """Unresolved requests have interaction success, never a paired execution SR."""
    return [
        DialogueSpec(task.task_id, "unresolved_conflict",
            (public_protocol(task) + "禁止训练任何新模型，却必须给出新训练模型的真实测试 MAE。",),
            mode="clarify", suite="response_only", required_question_terms=("训练", "冲突")),
        DialogueSpec(task.task_id, "missing_critical_context",
            ("请做性质预测并给报告，数据和预测目标尚未确定。",),
            mode="clarify", suite="response_only", required_question_terms=("数据", "目标")),
    ]


def resolve_arguments(arguments: dict, bindings: dict) -> dict:
    resolved = {}
    for key, value in arguments.items():
        if isinstance(value, str) and value.startswith("$"):
            node, field = value[1:].split(".", 1)
            resolved[key] = bindings[node][field]
        else:
            resolved[key] = value
    return resolved
