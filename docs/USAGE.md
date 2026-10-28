# 统一使用说明：工作区、工具、访谈与研究接口

本页合并原工作区、模型输出、G1／G2／G2.1和研究接口使用说明。安装与依赖见[复现说明](REPRODUCIBILITY.md)，实现位置见[架构](ARCHITECTURE.md)。

## 启动与工作区

在根目录运行`science-bot.cmd`，默认API模式；`science-bot.cmd -Backend offline`无需模型API。使用`-Workspace 'D:\my-project'`绑定已存在的项目目录。工作区文件列表不等于内容读取授权；读取前用户需明确选择文件。密钥、依赖目录、越界路径和二进制文件不能作为普通项目上下文读取。

会话、工作区、任务路由、工具调用与模型输出分别持久化。历史会话原件已移到同级归档目录；不从旧输出目录推断当前默认策略。

## 常用交互

| 输入 | 用途 |
|---|---|
| `/status` | 当前任务、工作区与阶段 |
| `/tools list` / `/tools status` | 详细工具库契约、实现状态与会话制品 |
| `/tools call <工具名> <JSON>` | 无需模型API调用已实现离线工具 |
| `/tools chat <研究任务>` | API模式规划并调用20个离线工具，引用实际证据 |
| `/model-output` | 查看已保存的模型提议；不能替代执行证据 |
| `/report` | 当前实验／任务的报告 |
| `/research status` | 已接入研究范围与当前结果 |
| `/research results g2_2` | 冻结BC基准结果 |
| `/research results g2_3` | 严格公开证据评分及修订试验摘要 |
| `/research verify g2_4` | 检查注册的G2.4冻结制品 |
| `/research simulate g2_3 --policy bc_ppo --seed 37` | CViT开发场景中进行冻结策略推理 |
| `/research compare g2_3 --seed 37` | 相同场景比较规则与研究策略 |
| `/doe demo` | 错误模型与脚本修订演示 |
| `/doe template factorial_2x2` | 合成2×2方案模板与检查 |
| `/doe report` | 本会话最近DOE检查 |
| `/doe recheck` | 重新核对已选输入；文件变化重新读取 |

研究种子只接受当前注册的21、37、59。G2.2可选rule／bc；G2.3可选rule／bc／bc_ppo／ppo_scratch／feedback_baseline／feedback_ppo。可用场景和参数以命令反馈为准，没有聊天重训或封存评测入口。

## 表格任务与访谈

显式选择已有CSV后，Agent可检查列名、类型和缺失情况；随后通过访谈确定研究问题、响应、因素、实验单位、来源、随机化／抽样依据和缺失处理。

当前支持独立组Welch比较、按单位ID匹配的配对比较、固定划分下的均值／OLS预测。时间、聚类或复杂因果任务不能被默认当作独立行处理。准备方案不等于执行；宿主确认后才运行表格执行节点。

访谈允许补充信息、处理冲突、讨论设计选项或合理停止，默认rule。BC参数仍保存，可供明确选择与研究，不暗示已优于规则。

## 检查自己的DOE计划

先将需求JSON与合同JSON放在绑定项目中，聊天输入：

```text
/doe validate "request.json" "contract.json"
```

需求／方案需满足G2.4闭合Schema并带有相应来源与哈希；可先通过template了解结构。支持CRD两处理、RCBD两处理、2×2固定效应设计。检查来源一致性、运行顺序、设计矩阵、可估计性、自由度、主要比较、条件名义功效和预算。

通过返回可审阅状态，不证明真实独立性、正态同方差、实际随机化、因果关系或科学成功。自然语言访谈尚不自动填写完整DOE协议。

## 专家审阅与训练

聊天`/research review-export g2_2`或`/doe review-export`导出待审副本；原队列和权重保留。真实审阅后将版本、身份、理由和带时区时间按相应协议导入；导入不自动训练。

新增v2任务及决策标注使用[统一专家交接](../Training_Data_Darcy_CViT/RL训练数据_专家交接文档.md)。工具库独立调用与Schema见[详细工具库](../Research_Tool_Library/README_详细工具库.md)。静态示范不能补造log probability作为PPO数据，更新前后权重与真实采样单独保留。
