"""Conservative host routing, separate from model planning and execution."""
import re

from .contracts import TaskRequest


_EXT = r"(?:py|md|txt|rst|toml|ya?ml|json|csv|tsv)"
_FILE = re.compile(r"(?:[A-Za-z]:[/\\])?[\w./\\-]+\."+_EXT+r"(?![A-Za-z0-9_])", re.I)
_QUOTED_FILE = re.compile(r"[`\"']([^`\"'\r\n]+\."+_EXT+r")[`\"']", re.I)
_EXEC = re.compile(r"运行|执行|开展|开始|启动|训练|拟合|预测|做.{0,5}实验|run\b|execute\b|train\b|fit\b|predict\b", re.I)
_EXPLAIN = re.compile(r"是什么|什么是|为什么|如何|怎么|解释|说明|介绍|含义|原理|区别|总结|what\b|why\b|how\b|explain\b|describe\b|summari[sz]e\b", re.I)
_METHOD = re.compile(r"(?<![A-Za-z0-9_])(?:CViT|FNO|XGBoost|CNN|DNN|MLP|LSTM|Transformer|SVM|KNN|GPR|random\s+forest|gaussian\s+process|polynomial\s+regression)(?![A-Za-z0-9_])|神经网络|随机森林|高斯过程|多项式回归|逻辑回归|贝叶斯回归|普通最小二乘|决策树|支持向量|核回归", re.I)


def _unregistered_method(text):
    """Catch explicitly requested named methods outside the frozen fit tools."""
    names = re.findall(r"(?:使用|采用|用)\s*([A-Za-z][A-Za-z0-9_+/-]*)|\b(?:using|use)\s+(?:the\s+)?([A-Za-z][A-Za-z0-9_+/-]*)", text, re.I)
    allowed = {"generated", "darcy", "mean", "ridge", "mean/ridge", "ridge/mean", "registered", "the"}
    if any((left or right).casefold() not in allowed for left, right in names):
        return True
    chinese_names = re.findall(r"(?:使用|采用|用)\s*([^，,。；;\s]{1,30}?)(?=在|对|进行|开展|运行|拟合|预测|训练|做|$)", text)
    for name in chinese_names:
        if re.search(r"回归|模型|方法|网络|算法", name) and not re.search(r"岭回归|均值|已注册|mean|ridge", name, re.I):
            return True
    return False


def _unsupported_numeric_scope(text, dataset):
    """Reject concrete task/target changes that the old engine cannot execute.

    The numeric adapter has fixed dataset targets. Merely naming a registered
    dataset must not turn an unsupported classification or new-output request
    into its default regression experiment.
    """
    if re.search(r"分类|聚类|分割|多变量|多目标|多输出|时间序列|(?<![A-Za-z_])(?:classification|classify|clustering|cluster|segmentation|multivariate|multitarget|multioutput|forecasting)(?![A-Za-z_])", text, re.I):
        return True
    if re.search(r"(?<![A-Za-z_])(?:accuracy|f1|auc|mae|rmse|mse)(?![A-Za-z_])|准确率|分类精度", text, re.I):
        return True
    if dataset == "generated" and re.search(r"pressure_field|压力场", text, re.I):
        return True
    if dataset == "darcy" and re.search(r"regression_output|回归输出", text, re.I):
        return True
    targets = []
    for match in re.finditer(r"预测|(?<![A-Za-z_])predict(?:ing)?(?![A-Za-z_])", text, re.I):
        clause = re.split(r"[,，。；;\n]|并|然后|同时|使用|采用|基于|预算|门槛|给出|报告|达到|\b(?:using|with|budget|threshold|and\s+(?:explain|report|compare))\b", text[match.end():], maxsplit=1, flags=re.I)[0]
        targets.append(clause.strip())
    targets.extend(re.findall(r"(?:目标|响应变量|输出变量)\s*[:：=为是]\s*([^,，。；;\n]+)|\btarget(?:\s+variable)?\s*[:=]\s*([^,，.;\n]+)", text, re.I))
    allowed_words = {"the", "a", "an", "target", "value", "values", "output", "outputs", "field", "on", "from", "for", "of",
                     "data", "dataset", "regression", "pressure", "mean", "ridge", "and", "or", "to", "using", "with"}
    allowed_words.update({"generated", "darcy", "regression_output" if dataset == "generated" else "pressure_field"})
    for target in targets:
        if isinstance(target, tuple):
            target = next((item for item in target if item), "")
        words = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", target)
        if any(word.casefold() not in allowed_words for word in words):
            return True
        chinese = re.sub(r"[A-Za-z_][A-Za-z0-9_]*|[\s/、和及与:：=()（）-]", "", target)
        # Keep familiar task shorthand; any other explicit Chinese output name
        # needs a domain adapter rather than silently retaining the default.
        for allowed in sorted(["数据集上的", "数据集上", "数据集", "压力场", "压力", "回归输出", "回归目标", "回归", "目标值", "响应值", "输出", "结果", "实验", "任务", "模型", "的", "在", "上", "值"], key=len, reverse=True):
            chinese = chinese.replace(allowed, "")
        if chinese:
            return True
    return False


def _numeric_protocol_override(text):
    """Intake can vary budget/threshold, never the frozen fit/split protocol."""
    assignments = re.findall(r"(?<![A-Za-z0-9_])([A-Za-z][A-Za-z0-9_]*)[\"']?\s*[:=]", text)
    fixed_fields = {"budget", "compute_units", "threshold", "quality_threshold", "dataset", "dataset_name", "target"}
    if any(name.casefold() not in fixed_fields for name in assignments):
        return True
    names = (r"alpha|feature_grid|fidelity|seed|task_seed|split_seed|split|train_ratio|test_ratio|val_ratio|validation_ratio|"
             r"train_size|test_size|group|fault_rate|tool_attempts|decision_steps|llm_requests|llm_tokens|active_seconds|"
             r"random_state|n_samples|batch_size|epochs|learning_rate|lr")
    if re.search(r"(?<![A-Za-z0-9_])(?:"+names+r")(?![A-Za-z0-9_])\s*(?:[:=]|is\b|为|设为|设置为|取|\d|half\b|full\b|train\b|dev\b|test\b|demo\b)", text, re.I):
        return True
    if re.search(r"(?:随机)?种子\s*(?:设置?为|设为|设成|固定为|为|是|[:：=])?\s*\d|"
                 r"(?:保真度|特征网格|正则化(?:系数|参数)?|样本数|迭代次数|学习率|训练轮数)\s*(?:设置?为|设为|设成|固定为|为|是|取|[:：=])|"
                 r"(?:训练集|验证集|测试集|训练/测试|训练/验证/测试|train/test|train/val/test).{0,12}\d|"
                 r"(?:训练|测试|验证)(?:集|数据)?\s*(?:占比|比例|比率|占)?\s*\d|"
                 r"\b(?:train|test|validation|val)(?:\s+\w+)?\s+(?:ratio|fraction|split)\b|"
                 r"\d+(?:\.\d+)?\s*[:/]\s*\d+(?:\.\d+)?\s*(?:train|test|split)\b|"
                 r"\b(?:half|full)\s+fidelity\b|(?:固定|设置|指定).{0,3}(?:随机)?种子|"
                 r"(?:划分比例|分割比例|数据划分为|按\s*\d+\s*[:：/]\s*\d+\s*划分)|"
                 r"(?:使用|采用|固定|指定).{0,8}(?:train|dev|test|demo)\s*(?:split|划分|集)|α\s*[:=]", text, re.I):
        return True
    exclusive = bool(re.search(r"(?:只|仅|单独|\bonly\b|\bexclusively\b|\bsolely\b).{0,12}(?:mean|ridge|岭回归|均值)", text, re.I))
    mean = bool(re.search(r"(?<![A-Za-z0-9_])mean(?![A-Za-z0-9_])|均值", text, re.I))
    ridge = bool(re.search(r"(?<![A-Za-z0-9_])ridge(?![A-Za-z0-9_])|岭回归", text, re.I))
    return exclusive and not (mean and ridge)


def _paths(text, workspace):
    candidates = _QUOTED_FILE.findall(text)
    candidates.extend(_FILE.findall(_QUOTED_FILE.sub(" ", text)))
    selected, invalid = [], []
    for candidate in candidates:
        variants = [candidate]
        # Chinese verbs may touch a bare filename without whitespace.
        stripped = re.sub(r"^(?:请|帮我|阅读|读取|查看|解释|分析|总结|文件|对|在|从|把|一下)+", "", candidate)
        if stripped != candidate:
            variants.append(stripped)
        found = None
        if workspace is not None:
            for variant in variants:
                try:
                    found = workspace.resolve_file(variant).relative_to(workspace.root).as_posix()
                    break
                except (ValueError, OSError):
                    continue
        else:
            found = variants[-1].replace("\\", "/")
        if found is not None:
            if found not in selected:
                selected.append(found)
        else:
            invalid.append(variants[-1])
    return selected, invalid


def route_request(text, workspace=None):
    from .tool_library import recognizes as detailed_command, natural_command as detailed_natural
    if isinstance(text, str) and (detailed_command(text) or detailed_natural(text)):
        return TaskRequest(detailed_natural(text) or text, "research", reason="explicit_detailed_tool_library")
    if not isinstance(text, str) or not text.strip() or len(text) > 20000:
        return TaskRequest(str(text)[:20000], "clarify", questions=["请描述希望回答的问题或执行的具体任务。"], reason="missing_or_oversized_request")
    text = text.strip()
    from .research import natural_command
    research_command = natural_command(text)
    if research_command:
        return TaskRequest(research_command, "research", reason="explicit_research_interface")
    if text.startswith("/design "):
        from .provider import _strict_json
        from .experiment import ExperimentSpec
        try:
            specification = ExperimentSpec.from_dict(_strict_json(text[8:].strip()))
            if workspace is None:
                raise ValueError("请先使用 -Workspace 绑定数据项目")
            path = workspace.resolve_file(specification.data_path).relative_to(workspace.root).as_posix()
            if path != specification.data_path:
                raise ValueError("data_path 需使用工作区内规范相对路径")
        except (ValueError, TypeError, OSError) as exc:
            return TaskRequest(text, "clarify", questions=[str(exc)], reason="invalid_experiment_spec")
        return TaskRequest(text, "tabular", input_paths=[path], specification=specification.to_dict(), reason="explicit_experiment_spec")
    paths, invalid = _paths(text, workspace)
    low = text.casefold()
    datasets = [name for name in ("generated", "darcy") if re.search(r"(?<![a-z0-9_])"+name+r"(?![a-z0-9_])", low)]
    if re.search(r"合成(?:回归|数据)", text) and "generated" not in datasets:
        datasets.append("generated")
    dataset = datasets[0] if len(datasets) == 1 else None
    execute = bool(_EXEC.search(text))
    question = bool(re.search(r"是不是|是否|能否|[?？]|[吗么]$|请问|什么|如何|怎么|为什么|\b(?:what|why|how)\b", text, re.I))
    explicit_run = bool(re.search(r"运行|执行|开展|启动|开始|\b(?:run|execute|train|fit|predict)\b", text, re.I))
    explain = question or bool(_EXPLAIN.search(text)) and not explicit_run
    negate = bool(re.search(r"不要|别(?:再)?|不(?:用|要|想)(?:去)?|禁止|do\s+not|don't|never", text, re.I))
    list_request = bool(re.search(r"(?:列出|列一下|有哪些|浏览|查看).{0,12}(?:文件|目录)|(?:list|browse|show)\b.{0,30}\b(?:files|directory|project)\b", text, re.I))
    read_request = bool(re.search(r"阅读|读取|查看|读一下|\bread\b|\binspect\b", text, re.I))
    mutation = bool(re.search(r"修改|删除|写入|覆盖|安装|下载|\b(?:modify|delete|write|install|download)\b", text, re.I))
    deny_read = bool(re.search(r"(?:不要|别|不用|不想|禁止|do\s+not|don't|never).{0,12}(?:阅读|读取|查看|读|\bread\b|\binspect\b)", text, re.I))
    # Explanatory questions and explicitly negated requests never authorize jobs.
    # A separate prohibition on training does not erase explicit permission to
    # explain a selected file; a prohibition on reading still takes precedence.
    if negate and not (paths and (explain or read_request) and not deny_read):
        return TaskRequest(text, "chat", dataset=dataset, reason="execution_not_authorized")
    csv_paths = [path for path in paths if path.casefold().endswith(".csv")]
    tabular_action = bool(re.search(r"分析|检查|比较|对比|设计|规划|预测|检验|缺失|列信息|\b(?:analy[sz]e|inspect|compare|design|predict|test|profile)\b", text, re.I))
    if csv_paths and tabular_action and not mutation and not negate:
        if workspace is None:
            return TaskRequest(text, "clarify", questions=["请先使用 -Workspace <CSV所在项目> 绑定数据工作区。"], reason="workspace_missing")
        if invalid or len(paths) != 1:
            return TaskRequest(text, "clarify", questions=["G2 每次仅分析一个明确选择且有效的 CSV，请分别提交任务。"], reason="tabular_input_ambiguous")
        if (_METHOD.search(text.replace("普通最小二乘", "OLS")) or re.search(r"分类|聚类|时间序列|多因素|多重比较|区组|因果|(?<![A-Za-z0-9_])(?:classification|cluster|anova|time.series|causal|xgboost|svm|fno|cvit)(?![A-Za-z0-9_])", text, re.I)):
            return TaskRequest(text, "unsupported", questions=["G2 当前支持两独立组 Welch、配对 t 检验和独立单位的 mean/OLS 预测比较；该请求需要其他领域工具。"], reason="tabular_method_not_registered")
        if re.search(r"训练集.{0,6}\d|验证集.{0,6}\d|测试集.{0,6}\d|划分.{0,10}\d|(?<![A-Za-z0-9_])(?:split|train_ratio|test_ratio|epochs|learning_rate|mae|auc|accuracy)(?![A-Za-z0-9_])", text, re.I):
            return TaskRequest(text, "clarify", questions=["G2预测比较使用固定60/20/20划分、训练集标准化、验证MSE选择和一次测试；暂不接受该协议修改。"], reason="tabular_protocol_override")
        if re.search(r"(?:仅|只|\bonly\b).{0,8}(?:OLS|线性回归|均值|mean)", text, re.I):
            return TaskRequest(text, "clarify", questions=["G2预测设计固定比较均值基线与OLS，暂不支持仅执行一个候选方法；请明确是否采用该比较协议。"], reason="tabular_candidate_override")
        return TaskRequest(text, "tabular", input_paths=csv_paths, reason="explicit_tabular_task")
    unsupported_method = bool(_METHOD.search(text)) or _unregistered_method(text)
    if paths and not (execute and unsupported_method and not negate) and not (mutation and not explain):
        if any(path.casefold().endswith((".csv", ".tsv")) for path in paths) and not read_request and not explain:
            return TaskRequest(text, "unsupported", input_paths=paths, reason="tabular_execution_requires_g2")
        if workspace is None:
            return TaskRequest(text, "clarify", input_paths=paths, questions=["请先使用 -Workspace <项目目录> 或 --workspace <项目目录> 启动并绑定这些文件所在的项目。"], reason="workspace_missing")
        return TaskRequest(text, "project_qa", input_paths=paths, reason="explicit_file_context")
    if invalid:
        return TaskRequest(text, "clarify", questions=["指定文件不存在、受工作区策略限制或不在当前项目中；请提供有效的项目相对路径。"], reason="invalid_file_reference")
    if mutation and not explain:
        return TaskRequest(text, "unsupported", reason="write_or_shell_tool_not_registered")
    if list_request:
        if workspace is None:
            return TaskRequest(text, "clarify", questions=["请先使用 -Workspace <项目目录> 或 --workspace <项目目录> 启动并绑定项目。"], reason="workspace_missing")
        return TaskRequest(text, "project_qa", reason="list_requested")
    if (read_request or explain) and re.search(r"(?:当前|这个|本|我的)?项目|文件|代码|模型结构|\b(?:project|file|code)\b", text, re.I):
        return TaskRequest(text, "clarify", questions=["请指定要阅读的文件相对路径；也可以先让我列出项目文件。"], reason="explicit_file_selection_needed")
    if explain:
        return TaskRequest(text, "chat", dataset=dataset, reason="explanation_only")
    if not execute and re.search(r"比较|对比|\bcompare\b|\bcomparison\b", text, re.I) and not re.search(r"设计|规划|\b(?:design|plan|DOE)\b", text, re.I):
        return TaskRequest(text, "chat", dataset=dataset, reason="comparison_only")
    if execute and re.search(r"(?:使用|采用|用)\s*(?:一个|某个|一种|某种|新的|其他|另一个|任意|合适的|最好的|更好的|不同的)?\s*(?:模型|方法|算法|回归模型)", text):
        return TaskRequest(text, "clarify", dataset=dataset, questions=["请明确要采用的模型或方法；当前执行器只注册了 mean / ridge。"], reason="method_selection_ambiguous")
    if unsupported_method and execute:
        return TaskRequest(text, "unsupported", dataset=dataset, reason="requested_method_not_registered")
    if dataset is not None and _unsupported_numeric_scope(text, dataset):
        return TaskRequest(text, "unsupported", dataset=dataset, reason="requested_task_or_target_not_registered")
    if re.search(r"(?:设计|规划).{0,12}实验|实验设计|\b(?:design|plan)\b.{0,20}\bexperiment|\bDOE\b", text, re.I):
        return TaskRequest(text, "design", dataset=dataset, reason="experimental_design_requires_g2")
    if re.search(r"\.csv\b|\.tsv\b|CSV|表格数据", text, re.I):
        return TaskRequest(text, "unsupported", reason="tabular_execution_requires_g2")
    if len(datasets) > 1:
        return TaskRequest(text, "clarify", questions=["请选择本次实验使用 generated 还是 darcy，两个数据集需分别确认执行。"], reason="ambiguous_dataset")
    # Preserve the documented short commands without accepting dataset mentions
    # in an unrelated question as permission to execute.
    short = bool(re.fullmatch(r"\s*(?:darcy\s+pressure_field|generated\s+regression_output)\s*", low))
    numeric_task = execute or bool(re.search(r"预算\s*\d|门槛\s*\d|\b(?:budget|threshold)\s*\d", text, re.I))
    if dataset is not None and (short or numeric_task):
        if _numeric_protocol_override(text):
            return TaskRequest(text, "clarify", dataset=dataset,
                               questions=["当前数值入口只能调整预算和质量门槛，使用固定数据划分及完整 mean/ridge 候选目录；请求中的额外参数或候选限制尚未接入，请删除这些修改或先扩展工具适配器。"],
                               reason="numeric_protocol_override_not_supported")
        return TaskRequest(text, "numeric", dataset=dataset, reason="explicit_registered_numeric_task")
    if execute or dataset is not None:
        return TaskRequest(text, "clarify", dataset=dataset, questions=["请明确任务和已注册数据集：generated 回归或 Darcy 压力场预测。其他工具场景尚需接入。"], reason="numeric_scope_missing")
    if re.search(r"[?？]|^(?:你好|您好|嗨|hello\b|hi\b)|请问|告诉我|\b(?:compare|define|discuss)\b|工具|能力", text, re.I):
        return TaskRequest(text, "chat", reason="general_question")
    return TaskRequest(text, "clarify", questions=["希望我回答问题、读取指定项目文件，还是运行 generated / Darcy 实验？请补充具体目标。"], reason="unrecognized_request")
