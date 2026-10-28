# Harness Engineering：面向 Agent 设计与应用的核心 Insights

> 基于课程 **Harness Engineering — Designing environments in which agents can succeed** 整理  
> 课程主线：Model、Agent、Harness、Environment；Workflow、Memory、Context、Tools、Verification、Observability、Self-Improvement、Safety

---

## 1. 课程核心观点

这门课最核心的思想不是“如何得到一个更强的模型”，而是：

> **如何设计一个让模型能够持续、可靠、可验证地工作的环境。**

课程给出的核心公式是：

\[
\text{Observed capability}
=
f(\text{model, context, tools, workflow, feedback, permissions})
\]

也就是说，一个 Agent 的实际表现不只由模型本身决定。  
即使使用同一个模型，只要上下文、工具、工作流、反馈机制和权限设计不同，其表现也可能有巨大差异。

因此，Harness Engineering 可以理解为：

\[
\boxed{
\text{Harness Engineering}
\approx
\text{Agent Systems Engineering}
}
\]

它研究的不是模型“会不会思考”，而是如何把模型的能力组织成一个真正能完成任务的系统。

---

# 2. Model、Agent、Harness、Environment 的关系

课程明确区分了四个层级。

| 层级 | 核心问题 | 典型内容 |
|---|---|---|
| Model | 下一步该做什么？ | 权重、Tokenizer、Inference |
| Agent | 如何持续追求目标？ | Loop、Plan、Memory、Tool Calls |
| Harness | Agent 在什么运行条件下工作？ | Context、Tools、Permissions、Jobs、Logs、Verifiers、Recovery |
| Environment | 哪些真实状态可以被改变？ | Repository、Browser、Database、Laboratory、Users |

因此可以把一个完整 Agent 系统写成：

\[
\boxed{
\text{Agent System}
=
\text{LLM}
+
\text{Planning}
+
\text{Memory}
+
\text{Tools}
+
\text{Workflow}
+
\text{Feedback}
+
\text{Verification}
+
\text{Permissions}
}
\]

其中，Harness 主要负责组织 LLM 之外的这些系统机制。

---

# 3. Insight 1：不要把 Agent 当作“一次推理”，而要当作“长期运行的系统”

普通 LLM 应用常见结构是：

\[
Input \rightarrow Model \rightarrow Output
\]

但真正的 Agent 更应该被设计成闭环：

\[
Goal
\rightarrow
Plan
\rightarrow
Execute
\rightarrow
Observe
\rightarrow
Verify
\rightarrow
Improve
\rightarrow \cdots
\]

课程给出的典型 Workflow 是：

\[
\text{Plan}
\rightarrow
\text{Execute}
\rightarrow
\text{Observe}
\rightarrow
\text{Test}
\rightarrow
\text{Improve}
\]

直到满足：

\[
\text{Accepted}
\quad \text{or} \quad
\text{Budget Ends}
\]

一个真正可工作的 Agent Workflow 还需要：

- executable checks
- error handling
- progress representation
- retry policy
- stop condition
- human escalation

### 关键 Insight

> **Prompt 描述行为，Workflow 才让行为可重复。**

因此，Harness 应用的基本单位不应该是一个 Prompt，而应该是一个完整的任务生命周期。

---

# 4. Insight 2：Planning 不只是“让 LLM 输出计划”，而是把计划变成可执行控制流

Agent 研究经常强调 Planning，但 Harness Engineering 给了 Planning 一个更工程化的定义。

真正的 Planning 不只是：

```text
Step 1 ...
Step 2 ...
Step 3 ...
```

而应该进一步变成：

- graph
- state machine
- queue
- conditional routing
- retry
- termination condition
- parallel execution

因此：

\[
\boxed{
\text{Planning}
\rightarrow
\text{Executable Control Flow}
}
\]

这也是为什么 LangGraph 与 Harness Engineering 高度一致。

可以把 Workflow 表示为：

\[
W=(V,E)
\]

其中：

- \(V\)：Model / Tool / Evaluator 等操作节点
- \(E\)：Control Flow

因此 LangGraph 可以理解为 Harness 中 **Workflow Layer** 的一种具体实现形式。

---

# 5. Insight 3：状态应该存在于系统里，而不是存在于聊天记录里

长任务会产生大量状态：

- plans
- decisions
- experiment outputs
- screenshots
- traces
- previous attempts
- code diffs
- source summaries
- task status

这些信息通常远远超过单次 context window 的容量。

课程因此提出：

> **Keep rich state outside the prompt; load only the relevant slice into context.**

也就是：

\[
\text{Persistent State}
\xrightarrow{\text{Retrieval}}
\text{Relevant Context}
\]

而不是：

\[
\text{Everything}
\rightarrow
\text{Context Window}
\]

### 对 Agent 设计的启发

应该明确区分：

### Short-term Memory

当前运行所需内容，例如：

- 当前用户目标
- 当前 Plan
- 最近工具输出
- 当前中间结果

### Long-term / Persistent Memory

长期保存：

- 历史实验
- 已失败方案
- 决策记录
- 文献摘要
- 数据集说明
- checkpoint
- 项目状态

因此，Memory 在 Harness 中更像：

\[
\boxed{
\text{Storage + Retrieval + State Management}
}
\]

而不只是“让模型记住”。

---

# 6. Insight 4：Context Engineering 的本质是 Information Architecture

课程提出一个很有代表性的原则：

> **Give the agent a map, not a giant manual.**

也就是说，不应该把所有说明都塞进一个超长 Prompt。

超大 Prompt 容易产生：

- context scarcity
- conflicting priorities
- stale rules
- low salience
- difficult verification

更好的方式是 **Progressive Disclosure**：

先给 Agent 一个简短入口，再让它根据当前任务逐步获取相关信息。

例如：

```text
AGENTS.md
ARCHITECTURE.md
SECURITY.md
RELIABILITY.md
docs/
    design-docs/
    exec-plans/
    product-specs/
```

Agent 根据当前问题选择性进入。

因此：

\[
\text{More Context}
\neq
\text{Better Context}
\]

更合理的是：

\[
\boxed{
\text{Right Context at the Right Time}
}
\]

### 更深层理解

Context Engineering 可以理解为 Agent 的“感知设计”：

\[
\text{Task}
\rightarrow
\text{Identify Relevant Information}
\rightarrow
\text{Retrieve}
\rightarrow
\text{Reason}
\]

因此很多 Agent 失败并不是模型“不知道”，而是：

> **系统没有在正确时间把正确的信息暴露给模型。**

---

# 7. Insight 5：Tool Use 本质上是在定义 Agent 的 Action Space

Agent 和普通 Chatbot 的一个根本区别是：

\[
\boxed{
\text{Agent can act}
}
\]

例如：

- Search
- Read files
- Write files
- Run Python
- Execute shell commands
- Query APIs
- Run experiments
- Use simulators
- Inspect screenshots
- Interact with databases

如果用强化学习语言描述：

\[
s_t = \text{current state}
\]

Agent 根据 policy 选择：

\[
a_t \in A
\]

而 Tool System 实际上定义了：

\[
\boxed{
A = \text{Agent Action Space}
}
\]

如果工具只有文字输出：

\[
A=\{\text{text}\}
\]

Agent 的能力就很有限。

如果 Tools 包含：

\[
A=
\{
\text{Search},
\text{Code},
\text{Experiment},
\text{Simulation},
\text{Database}
\}
\]

Agent 才能真正改变环境。

---

# 8. Insight 6：好的 Tool 不是“一个函数”，而是一个可观测、可约束的能力接口

课程将工具划分为：

- Discovery
- Mutation
- Execution
- External Context
- Inspection
- Coordination

并强调每个 Tool 都应该具备：

\[
\boxed{
\text{Schema}
+
\text{Permission Boundary}
+
\text{Failure Contract}
+
\text{Observable Result}
}
\]

例如：

```text
run_simulation()
```

如果只返回：

```text
done
```

那么 Agent 很难继续推理。

更好的返回应该包括：

```text
status
runtime
output artifact
error message
parameters
metrics
log path
```

所以：

\[
\boxed{
\text{Good Tool}
=
\text{Actionable Before Execution}
+
\text{Inspectable After Execution}
}
\]

---

# 9. Insight 7：Observability 决定 Agent 能“看见”什么

Agent 执行完动作之后，必须能够读取环境反馈。

Harness 应该暴露：

- structured logs
- metrics
- traces
- screenshots
- DOM
- tool inputs / outputs
- model metadata
- cost metadata

这样 Agent 才能回答：

- 哪里失败了？
- 哪一步最耗时？
- 哪个假设错了？
- 是否可以复现？
- 修改之后有没有变好？

课程中的核心思想可以概括为：

\[
\boxed{
\text{Unobservable State}
=
\text{Unusable State}
}
\]

或者：

> 如果 Agent 无法检查某个状态，那么这个状态对它的决策过程而言几乎等于不存在。

因此，真正的 Agent 闭环应该是：

\[
Agent
\rightarrow
Tool
\rightarrow
Environment
\rightarrow
Observation
\rightarrow
Agent
\]

---

# 10. Insight 8：Verification 将“模糊质量要求”转化为 Agent 可利用的反馈

课程中非常关键的一句话是：

> **Verification converts vague quality expectations into feedback the agent can act on.**

这句话的意思是：

Agent 无法直接对“做得更好”“更可靠”“更科学”这种模糊要求采取行动。

必须把这些抽象要求转换为具体、可观察、最好可执行的信号。

例如：

```text
“代码写得好”
```

可以转换为：

```text
compile: PASS
unit tests: PASS
integration tests: PASS
latency < 200 ms
coverage > 90%
```

于是：

\[
\text{Vague Quality Expectation}
\]

变成：

\[
\text{Concrete Feedback}
\]

从而支持：

\[
\text{Feedback}
\rightarrow
\text{Next Action}
\]

---

# 11. Verification 和 Reflection 的区别

这两个概念很容易混淆。

## Verification

回答：

> 哪里错了？

例如：

```text
Validation RMSE = 0.41
Required RMSE < 0.30
```

## Reflection

回答：

> 为什么错？下一步怎么改？

例如：

```text
Training error is low but validation error is high.
This suggests overfitting.
I should inspect regularization and the data split.
```

因此：

\[
\boxed{
\text{Verification}
\rightarrow
\text{Evidence}
}
\]

\[
\boxed{
\text{Reflection}
\rightarrow
\text{Reasoning over Evidence}
}
\]

真正有效的 self-correction 应该是：

\[
\text{Execute}
\rightarrow
\text{Verify}
\rightarrow
\text{Reflect}
\rightarrow
\text{Revise}
\]

而不是：

\[
\text{Execute}
\rightarrow
\text{Model judges itself}
\]

---

# 12. Insight 9：Verifier 在某种意义上定义了“什么叫变好”

课程进一步提出：

> **The verifier determines what improvement means.**

容易验证的属性包括：

- unit test
- compiler success
- exact answer
- benchmark score
- latency
- cost

难验证的属性包括：

- scientific novelty
- usefulness
- factual completeness
- subtle security risk
- long-term maintainability

因此：

\[
\boxed{
\text{Optimization Quality}
\le
\text{Evaluator Quality}
}
\]

如果 evaluator 测错了目标，Agent 会“成功地优化错误的东西”。

这与强化学习中的 reward function 非常类似。

例如：

\[
R=\text{Accuracy}
\]

则 Agent 会优先提升 Accuracy。

如果定义：

\[
R
=
Accuracy
-0.1 Cost
-10\times ConstraintViolation
\]

那么行为会发生明显变化。

因此可以粗略类比：

\[
\boxed{
\text{Verifier}
\approx
\text{Definition of Success}
}
\]

\[
\boxed{
\text{Feedback}
\approx
\text{Signal for Changing Behavior}
}
\]

---

# 13. Insight 10：把重要规则变成系统约束，而不是反复写进 Prompt

课程有一个非常重要的工程原则：

> **Rules that matter should become executable checks whenever possible.**

例如，与其不断提醒 Agent：

```text
Please do not modify the raw dataset.
```

不如直接：

\[
raw\_data = read\_only
\]

与其提醒：

```text
Please stay within budget.
```

不如：

\[
cost > budget
\Rightarrow stop
\]

与其提醒：

```text
Run tests before merging.
```

不如：

\[
merge
\Rightarrow
tests = PASS
\]

因此：

\[
\boxed{
\text{Do not persuade the model when you can constrain the system.}
}
\]

Prompt 更多是 soft constraint；

Harness 可以提供 hard constraint。

---

# 14. Insight 11：Enforce invariants; allow local freedom

一个好的 Harness 不应该完全控制 Agent，也不应该完全放开。

更合理的是：

### 固定不变的 Central Invariants

例如：

- security boundary
- permission
- budget
- data validation
- dependency rules
- testing requirements
- artifact format

### 允许 Agent 自由决定的 Local Autonomy

例如：

- exact implementation
- variable names
- internal organization
- sequence of reversible edits
- choice among approved patterns

因此：

\[
\boxed{
\text{Good Autonomy}
=
\text{Hard Boundaries}
+
\text{Local Freedom}
}
\]

限制太强：

\[
Agent \rightarrow Script
\]

限制太弱：

\[
Agent \rightarrow Unpredictable System
\]

真正需要的是：

```text
Goal fixed
Safety fixed
Budget fixed
Evaluator fixed

but

Reasoning flexible
Tool sequence flexible
Implementation flexible
```

---

# 15. Insight 12：不要对所有失败都盲目 Retry

“Retry every error blindly” 是典型 Harness Anti-pattern。

因为不同错误代表不同问题。

合理 Recovery Policy 应该是：

\[
\text{Transient Error}
\rightarrow
\text{Retry}
\]

\[
\text{Invalid Parameters}
\rightarrow
\text{Revise Action}
\]

\[
\text{Permission Failure}
\rightarrow
\text{Escalate}
\]

\[
\text{Safety Violation}
\rightarrow
\text{Stop}
\]

\[
\text{No Progress}
\rightarrow
\text{Replan}
\]

因此：

\[
\boxed{
\text{Failure Classification}
\rightarrow
\text{Recovery Policy}
}
\]

而不是：

\[
\text{Failure}
\rightarrow
\text{Retry}
\]

---

# 16. Insight 13：更高的 Agent 自治，需要更强的 Isolation

当 Agent 能：

- 修改代码
- 执行程序
- 操作数据库
- 调用网络
- 运行实验
- 使用凭据

就必须考虑错误的 blast radius。

因此课程建议给任务建立隔离 workspace，包括：

- independent checkout / worktree
- test data
- isolated application instance
- logs and traces
- time limit
- resource limit
- network boundary
- credential boundary

可以写成：

\[
\boxed{
\text{More Autonomy}
\Rightarrow
\text{More Isolation}
}
\]

例如：

```text
main repository
        ↓
isolated worktree
        ↓
agent modification
        ↓
test
        ↓
review
        ↓
merge
```

而不是：

```text
Agent → Production
```

---

# 17. Insight 14：Multi-Agent 的难点不是“多个 Agent”，而是 Coordination

多个 Agent 可以用于：

- 搜索不同假设
- 运行独立实验
- 检查不同风险
- 监控长任务

但是多 Agent 系统真正需要 Harness 管理：

- job ID
- status
- logs
- timeout
- cancellation
- artifact locations
- merge protocol

所以 Multi-Agent 的核心问题不是：

```text
Agent A
Agent B
Agent C
```

而是：

\[
\boxed{
\text{How do Agents Coordinate?}
}
\]

例如：

```text
Planner
 ├── Literature Agent
 ├── Data Agent
 └── Experiment Agent
          ↓
        Results
          ↓
      Reviewer
          ↓
       Planner
```

因此 AutoGen、CrewAI、MetaGPT 等框架中最值得研究的，也不只是角色定义，而是状态共享、任务分配、冲突解决和结果合并。

---

# 18. Insight 15：Human-in-the-loop 不是“人退出系统”，而是“人上移一层”

课程描述的人机关系可以概括为：

\[
\text{Specify Intent}
\rightarrow
\text{Design Environment}
\rightarrow
\text{Encode Criteria}
\rightarrow
\text{Agent Executes}
\rightarrow
\text{Judge Outcomes}
\]

随着 Agent 自治增强，人类逐渐减少手工执行，转向：

- 定义目标
- 定义边界
- 设计环境
- 定义质量标准
- 处理模糊 trade-off
- 审核高风险结果

因此：

\[
\boxed{
\text{Autonomy changes where human judgment is applied;
it does not remove responsibility.}
}
\]

---

# 19. Insight 16：Harness 本身可以成为优化对象

课程后半部分提出：

\[
W=(V,E)
\]

其中 Workflow \(W\) 可以看成由：

- model operations
- tool operations
- evaluator operations
- control flow

组成。

然后定义任务目标：

\[
J(W)
\]

于是可以求：

\[
\boxed{
W^*
=
\arg\max_W J(W)
}
\]

并同时满足：

\[
\text{Cost Constraints}
\]

\[
\text{Safety Constraints}
\]

因此 Harness 不只是人工搭建的系统，也可以被：

- RL
- evolutionary search
- Bayesian optimization
- LLM-based mutation
- workflow search

自动改进。

---

# 20. Insight 17：Self-Improvement 的关键不是“Self”，而是“Bounded”

真正合理的 Self-Harness 流程是：

\[
\text{Weakness Mining}
\rightarrow
\text{Bounded Proposal}
\rightarrow
\text{Validation}
\rightarrow
\text{Acceptance}
\]

也就是说：

1. 从大量 Trace 中找到重复失败模式；
2. 只允许修改声明过的 Harness 部分；
3. 在目标失败集和 held-out tasks 上验证；
4. 只有无明显 regression 的修改才接受。

Self-improvement 应该满足：

\[
\boxed{
\text{Bounded}
+
\text{Versioned}
+
\text{Evaluated}
+
\text{Reversible}
}
\]

---

# 21. Insight 18：必须有 Protected Control Plane

有一些 Harness 部分可以允许 Agent 修改，例如：

```text
prompt
skills
routing
memory
workflow
```

但有一些部分不能让 Agent 自己改：

```text
permissions
evaluator
audit log
model identity
budget
```

否则可能发生：

\[
\text{Improve Performance}
\]

退化为：

\[
\text{Change the Scoring Rule}
\]

也就是 reward hacking。

因此，一个 Self-Improving Harness 应该分成：

\[
\boxed{
\text{Editable Execution Layer}
+
\text{Protected Control Layer}
}
\]

---

# 22. Insight 19：Harness 优化必须看 Held-Out Performance

如果只在已经失败过的任务上优化，Agent 很容易出现：

\[
\text{Workflow Overfitting}
\]

因此候选 Harness \(h'\) 不应该只看：

\[
\Delta_{in}
\]

还应该看：

\[
\Delta_{out}
\]

也就是：

- targeted failures 有没有改善？
- held-out tasks 有没有退化？
- cost 是否上升？
- latency 是否上升？
- safety 是否退化？

这和机器学习中的 train / validation generalization 非常类似。

---

# 23. Insight 20：Harness 会产生系统熵，需要持续“垃圾回收”

Agent 会模仿系统已有模式，包括坏模式。

小问题可能不断积累为：

- architectural drift
- duplicated logic
- inconsistent conventions
- stale documents
- technical debt

因此 Harness 还需要维护循环：

\[
\text{Scan}
\rightarrow
\text{Grade}
\rightarrow
\text{Open Fix}
\rightarrow
\text{Verify}
\rightarrow
\text{Merge}
\]

因此成熟 Harness 实际上有两个循环。

## Task Loop

\[
\text{Plan}
\rightarrow
\text{Execute}
\rightarrow
\text{Verify}
\rightarrow
\text{Improve}
\]

## System Loop

\[
\text{Observe Failures}
\rightarrow
\text{Improve Harness}
\rightarrow
\text{Regression Test}
\]

这是区分“能运行的 Agent Demo”和“长期可维护 Agent System”的关键。

---

# 24. 一个最小 Harness Blueprint

课程最后给出了一个非常好的最小设计：

\[
\boxed{
\text{Task Contract}
\rightarrow
\text{Context Map}
\rightarrow
\text{Typed Tools}
\rightarrow
\text{Workflow}
\rightarrow
\text{Verifiers}
\rightarrow
\text{Trace}
}
\]

随后根据风险和后果增加：

\[
\text{Isolation}
+
\text{Budgets}
+
\text{Permission Gates}
+
\text{Recovery}
+
\text{Regression Evaluation}
\]

### 重要原则

> **Start small.**

不要为了“架构看起来先进”而不断添加机制。

每一个新增 Harness 组件都应该回答：

> 它具体解决了哪个已经观察到的 failure mode 或明确风险？

---

# 25. Harness Engineering 与 Agent 核心机制的映射

| Agent 核心机制 | Harness Engineering 对应内容 |
|---|---|
| Planning | Workflow / Graph / State Machine |
| Memory | Persistent State / Files / Retrieval |
| Tool Use | Tool Router / Typed Tools / Permissions |
| Reflection | Verification + Reasoning over Feedback |
| Multi-Agent | Jobs / Subagents / Coordination |
| Perception | Context + Observability |
| Recovery | Failure Classification + Retry / Replan |
| Autonomy | Workflow + Tools + Permissions |
| Safety | Isolation + Protected Boundaries |
| Learning | Trace → Failure Pattern → Harness Update |
| Self-Improvement | Harness Optimization |
| Evaluation | Verifier / Benchmark / Human Judgment |

因此传统的：

\[
\text{Planning + Memory + Tool Use + Reflection}
\]

实际上可以被视为：

\[
\boxed{
\text{Harness Engineering}
}
\]

中的核心组成部分。

---

# 26. 对 Scientific Agent 的直接启发

如果把课程思想应用到科研 Agent，可以得到：

```text
                  Scientific Goal
                        ↓
                    Planner
                        ↓
         ┌──────────────┼──────────────┐
         ↓              ↓              ↓
 Literature Agent   Data Agent   Method Agent
         ↓              ↓              ↓
         └──────────────┼──────────────┘
                        ↓
                  Experiment Plan
                        ↓
                Code / Simulation Tool
                        ↓
                    Results
                        ↓
                    Verifier
                        ↓
             ┌──────────┴──────────┐
             ↓                     ↓
          Success                Failure
             ↓                     ↓
        Research Report         Reflection
                                   ↓
                            Workflow Update
```

对应的 Scientific Harness 可以写成：

\[
\boxed{
\text{Scientific Harness}
=
\text{Scientific State}
+
\text{Workflow}
+
\text{Tools}
+
\text{Experiment Memory}
+
\text{Verification}
+
\text{Protected Boundaries}
}
\]

---

# 27. Scientific Agent 中，Verifier 可能比 Planner 更难设计

对于代码 Agent：

```text
unit test PASS / FAIL
```

很容易自动判断。

但对于科研 Agent，目标通常更加模糊：

- 是否真正有创新？
- 实验是否有科学意义？
- 结论是否充分？
- 方法是否合理？
- 是否存在 data leakage？
- 统计结论是否可靠？
- 是否可复现？
- 是否值得继续投入资源？

因此科研 Agent 的核心难点之一是：

\[
\boxed{
\text{How do we operationalize scientific quality?}
}
\]

也就是：

> 如何把“科学上做得好”拆成 Agent 可以观察、验证和优化的信号？

一个科研 Harness 可以设计：

```text
Data verifier
→ leakage?

Baseline verifier
→ meaningful baseline included?

Statistical verifier
→ uncertainty / significance reported?

Reproducibility verifier
→ seed / config / data split stored?

Performance verifier
→ exceeds baseline?

Cost verifier
→ resource budget respected?
```

这样：

```text
Performance: PASS
Leakage: PASS
Baseline comparison: FAIL
Reproducibility: PASS
Statistical significance: FAIL
```

Agent 才能进一步决定：

```text
add baseline
run repeated experiments
perform statistical test
```

而不是笼统地“再思考一下”。

---

# 28. 对当前 Scientific Agent 项目的研究启发

一个自然的研究问题是：

\[
\boxed{
\text{Can scientific-agent performance be improved by automatically optimizing its harness?}
}
\]

可以固定基础 LLM：

\[
M = \text{fixed}
\]

优化：

\[
H=
\{
\text{Workflow},
\text{Context},
\text{Memory},
\text{Tools},
\text{Verifier},
\text{Reflection}
\}
\]

例如：

```text
Baseline LangGraph Agent
        ↓
run scientific tasks
        ↓
collect trajectories
        ↓
mine failure patterns
        ↓
modify routing / workflow / memory / reflection
        ↓
evaluate
        ↓
accept or reject
```

对应优化目标可以写成：

\[
H^*
=
\arg\max_H
J(H)
\]

例如：

\[
J(H)
=
\alpha \cdot TaskSuccess
+
\beta \cdot ScientificQuality
+
\gamma \cdot Reproducibility
-
\lambda_1 Cost
-
\lambda_2 Latency
-
\lambda_3 SafetyViolation
\]

---

# 29. 为什么 Harness Optimization 可能比直接 RLHF 更适合课程项目

如果直接做 RLHF 或模型权重更新，需要优化：

\[
\theta_{\text{LLM}}
\]

成本较高，需要：

- training pipeline
- preference data / reward design
- GPU resources
- checkpoint management
- evaluation
- alignment / safety consideration

而 Harness Optimization 可以固定模型：

\[
LLM = M
\]

只优化：

\[
H
=
\{
Workflow,
Prompt,
Context,
Memory,
Tools,
Verifier
\}
\]

它通常：

- 更容易解释
- 更容易实验
- 更容易部署
- 更容易回滚
- 成本更低
- 更适合课程项目和 Hackathon

因此当前项目可以从：

> “用 RLHF 让科研 Agent 变聪明”

调整为：

> **“固定基础 LLM，研究如何自动优化科研 Agent Harness，尤其是 Planning / Routing / Verification。”**

---

# 30. 整门课最值得记住的总结

可以把 Harness Engineering 的应用原则压缩成一句话：

\[
\boxed{
\text{A good harness does not tell the agent everything;}
}
\]

\[
\boxed{
\text{it makes the right state visible,}
}
\]

\[
\boxed{
\text{the right actions possible,}
}
\]

\[
\boxed{
\text{the right constraints enforceable,}
}
\]

\[
\boxed{
\text{and the right failures learnable.}
}
\]

即：

> **好的 Harness 不是不断给 Agent 更多指令，而是让正确的信息可见、正确的行动可执行、关键约束可强制、失败结果可学习。**

从这个角度看：

\[
\boxed{
\text{Harness Engineering}
\approx
\text{Designing the conditions under which intelligence can be applied reliably}
}
\]

而对于 Scientific Agent：

\[
\boxed{
\text{Scientific Agent}
=
\text{LLM}
+
\text{Scientific Harness}
}
\]

其中真正有研究价值的问题，是：

1. 哪些 Harness components 最影响科研 Agent 的表现？
2. 如何定义科研任务中的 verifier？
3. 如何把科研质量转换为可执行的 feedback？
4. 如何利用 traces 自动发现 Agent 的 failure patterns？
5. Workflow / Routing / Memory / Reflection 能否通过 RL 或搜索自动优化？
6. 如何保证 Harness 改进不会在 held-out 科研任务上退化？
7. 哪些部分可以 self-edit，哪些必须保持 protected？

---

# 31. 建议记忆的 10 条 Harness Engineering 原则

1. **Model is only one component.**
2. **Design workflows, not only prompts.**
3. **Keep persistent state outside the context window.**
4. **Give the agent a map, not a giant manual.**
5. **Tools define the agent's action space.**
6. **If the agent cannot observe a state, it cannot reason about it.**
7. **Verification turns vague quality into actionable feedback.**
8. **Encode important rules as executable constraints.**
9. **Allow local autonomy inside protected boundaries.**
10. **Treat the harness itself as an object that can be evaluated and improved.**

---

## Source

Course: **Harness Engineering — Designing environments in which agents can succeed**

Primary themes used in this note:

- Model / Agent / Harness / Environment
- Workflow Automation
- Persistent Memory
- Progressive Disclosure
- Tool Design
- Verification
- Observability
- Isolation
- Subagents
- Harness Optimization
- Self-Harness
- Recursive Self-Improvement
- Protected Control Plane
- Held-Out Evaluation
- Minimal Harness Blueprint

