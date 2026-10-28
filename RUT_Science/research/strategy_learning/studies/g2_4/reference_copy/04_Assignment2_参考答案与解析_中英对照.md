# DSC6008 Assignment 2：参考答案与完整解析（中英对照）

**课程：** Design of Experiments｜2026/2027 Fall  
**整理日期：** 2026-10-18  
**依据：** 本目录 `Assignment #2.pdf`（7 页）及课程 Week 2–6 讲义。  
**用途：** 学习、复习及自行核算参考。原题明确规定不得使用生成式 AI 产出提交答案；本资料包含题干，不是符合原题提交要求的作业文件。

## 0. 使用说明与答案总览

### 0.1 原题的提交要求：英文与中文

**English — original requirements**

Please include your full name and student number on the first page of your assignment and in the submitted file name, for example: `LastName_FirstName_StudentNumber_Assignment2.pdf`.

You have two weeks to complete the assignment. All work submitted must be your own; plagiarism or unauthorized copying is not allowed. Generative AI tools should not be used to produce assignment answers. For questions involving R, include your R code and output, and add brief comments explaining the main steps. Show your calculations and reasoning clearly; if important steps are skipped, unclear, or overly simplified, marks may be deducted even if the final answer is correct.

Only submit your answers (as .doc, .docx, .pdf, or scan of your hand-written) to Canvas. Clearly label your answer but don’t copy & paste the question stems.

**中文翻译**

请在作业首页和提交文件名中写明全名及学号，例如 `LastName_FirstName_StudentNumber_Assignment2.pdf`。作业完成时间为两周。提交内容必须由本人完成，不得抄袭或未经授权复制；不得使用生成式 AI 工具生成作业答案。涉及 R 的题目需要提供 R 代码、运行输出，并用简短注释说明主要步骤。计算和推理必须清晰；即使最后答案正确，省略重要步骤、表述不清或过度简化仍可能扣分。仅将答案以 Word、PDF 或手写扫描件形式提交 Canvas；清晰标注题号，不要复制粘贴题干。

**原题排版提醒：** Q2 标注总分 18，但可见细项为 2、3、6、5 分，合计 16 分；“(a) One-way ANOVA and F-test”下又出现了 (a)、(b)。本资料统一写为 Q2(a) 假设、Q2(b) ANOVA、Q2(c) Tukey、Q2(d) 残差，不自行补出缺失题目或分值。

### 0.2 最终数值速查

| 小题 | 参考结果 | 结论 |
| --- | --- | --- |
| Q1(b) | $n_2\geq\frac{10\sigma^2}{3\theta^2}(z_{1-\alpha}+z_{1-\beta})^2$ | 右侧单侧检验；不可换成双侧临界值 |
| Q1(c) | 连续解 $n_2=82.46892$，$n_1=35.34382$ | 严格保持 3:7 时取新治疗 36 人、标准治疗 84 人，总计 120 人 |
| Q1(c) 补充 | 36 人、83 人，总计 119 人 | 允许近似比例时也满足功效；须说明比例只是近似 |
| Q2(b) | $F(2,9)=7.03556$，$p=0.0144638$ | 拒绝三组总体均值相等 |
| Q2(c) | 40–20：差值 15，调整后 $p=0.0114434$ | 仅 40 g 与 20 g 显著；其余两对不显著 |
| Q2(d) | 最大标准化残差绝对值约 1.4793 | 无明显极端异常点；模型可暂认为适用，小样本诊断能力有限 |
| Q3(a) | 观察比例差 $0.10$；模拟 $p=0.0482976$ | 5% 水平拒绝原假设，证据接近显著性边界 |
| Q3(a) 精确核验 | 超几何双侧 $p=0.0462111$ | 与本次 Monte Carlo 判断一致 |
| Q3(b) | $\delta=2.020305$，功效 $0.524092$ | 功效约 52.41%，不是 80% |

**复现说明：** 上表来自实际运行的 [完整 R 脚本](Assignment2_reference_analysis.R) 与 [原始 R 输出](reference_output/R_output.txt)。Q3 使用 `set.seed(123)`、20,000 次随机化及下文明确给出的抽样方式。相同种子不保证不同算法得到相同的 Monte Carlo 数值。

## 1. 本次作业的知识框架

### 1.1 三题分别在回答什么

| 题目 | 研究阶段 | 核心问题 | 主要工具 |
| --- | --- | --- | --- |
| Q1 | 实验开始前 | 需要多少人，才能较可靠地发现指定差异？ | 均值差的标准误、单侧检验、功效、分配比 |
| Q2 | 得到连续型数据后 | 三个剂量的总体均值是否相同？哪些剂量不同？ | ANOVA、F 检验、Tukey HSD、残差诊断 |
| Q3(a) | 得到二分类数据后 | 随机分组本身能否解释观察到的比例差？ | 随机化检验、置换分布、Monte Carlo p 值 |
| Q3(b) | 规划下一次实验 | 指定真实比例下，现有样本量的检出能力多高？ | 非中心参数、正态近似、双侧功效 |

### 1.2 必须区分的概念

**总体参数与样本统计量。** $\mu_1-\mu_2$、$p_T-p_C$ 是未知总体差异；$\bar Y_1-\bar Y_2$、$\hat p_T-\hat p_C$ 是从样本得到的统计量。样本差异不等于真实效应。

**标准差与标准误。** $\sigma$ 描述个体响应的变异；标准误描述估计量在重复实验中的变异。独立两组的均值差标准误是

$$
SE(\bar Y_1-\bar Y_2)=\sigma\sqrt{\frac1{n_1}+\frac1{n_2}}.
$$

二项比例差在指定真实比例下的标准误是

$$
SE(\hat p_T-\hat p_C)=\sqrt{\frac{p_T(1-p_T)}{n_T}+\frac{p_C(1-p_C)}{n_C}}.
$$

**显著性水平、p 值与功效。** $\alpha$ 是原假设成立时预先控制的错误拒绝概率；p 值是在原假设及检验机制下，得到与观察值同样或更极端统计量的概率；功效是某个指定备择为真时拒绝原假设的概率。p 值不是“原假设为真的概率”，功效也不是“本次结论正确的概率”。

**单侧与双侧。** Q1 只关心新治疗优于标准治疗，使用 $z_{0.95}$；Q3 允许两个方向的比例差，使用 $z_{0.975}$，并在功效计算中加上两个拒绝尾部。

**随机化、独立性与可推广性。** 随机分配为处理比较及因果解释提供依据，但不能消除所有执行问题；同一学生重复观测、同一批次实验的共享误差等仍需设计上处理。随机分配不等于从所有大学生中随机抽样，因此向其他人群推广需要额外依据。

**总体检验与多重比较。** ANOVA 检验“所有均值相等”；显著意味着至少一个均值不同。Tukey HSD 才回答“具体哪两组不同”，并控制整个两两比较家族的第一类错误率。

## 2. Q1：不等比例分组的样本量计算（15 分）

### 2.1 题目英文与中文翻译

**English — problem statement**

A clinical trial is being planned to compare a new treatment with a standard treatment for reducing a continuous clinical outcome, such as blood pressure or HbA1c. Let $Y_1$ be the response from the new treatment group and $Y_2$ the response from the standard treatment group. A larger value of $Y_1-Y_2$ indicates that the new treatment is better. Assume normally distributed responses with a common standard deviation $\sigma=2$.

The investigators want to test $H_0:\mu_1-\mu_2\leq0$ against $H_a:\mu_1-\mu_2>0$. They want a one-sided test at significance level $\alpha=0.05$, with power $1-\beta=0.80$ to detect the clinically important difference $\theta=\mu_1-\mu_2=1$. The sample sizes satisfy $n_1=\frac37n_2$.

**中文翻译**

计划开展一项临床试验，比较新治疗与标准治疗在改善某个连续型临床结局（如血压或 HbA1c）方面的效果。$Y_1$ 表示新治疗组的响应，$Y_2$ 表示标准治疗组的响应。按题目定义，$Y_1-Y_2$ 越大，表示新治疗越好。假设响应服从正态分布，两组具有共同标准差 $\sigma=2$。

研究者拟进行右侧单侧检验 $H_0:\mu_1-\mu_2\leq0$，$H_a:\mu_1-\mu_2>0$。显著性水平为 0.05，希望在真实差异 $\theta=1$ 时达到 80% 的检验功效。成本与招募限制要求 $n_1=\frac37n_2$，其中 $n_1$ 为新治疗组人数、$n_2$ 为标准治疗组人数。

**方向提醒：** 原题一方面提到降低血压/HbA1c，一方面规定差值越大越好。此处应遵循原题明确的效应方向；可将响应理解为改善量。若实际响应是“治疗后原始血压”，方向需要重新定义，但不能擅自改动本题给定的假设。

**Subquestions / 小题翻译**

- **(a), 4 marks:** State the null and alternative hypotheses and explain Type I and Type II errors in context. / 写出原假设与备择假设，并结合临床试验解释第一类和第二类错误。
- **(b), 6 marks:** Starting from the normal distribution of the sample mean difference, derive the formula for $n_2$ using $n_1=\frac37n_2$. / 从样本均值差的正态分布出发，在给定分配比例下推导 $n_2$ 的样本量公式。
- **(c), 4 marks:** Use the supplied positive critical values 1.645 and 0.842, calculate both sample sizes, and round up while preserving the allocation ratio as closely as possible. / 使用给定正临界值 1.645、0.842 计算人数，向上取整并尽可能保持比例。
- **(d), 1 mark:** Interpret the final sample size recommendation. / 结合临床试验解释最终推荐样本量。

### 2.2 Q1(a)：假设与两类错误

令 $\theta=\mu_1-\mu_2$。

$$
H_0:\theta\leq0,\qquad H_a:\theta>0.
$$

**第一类错误（Type I error）：** 实际上新治疗不优于标准治疗，即 $\theta\leq0$，却拒绝原假设并宣称新治疗更好。该检验将这一错误概率控制在不超过 5%；最大值出现在边界 $\theta=0$。

**第二类错误（Type II error）：** 实际上新治疗更好，即 $\theta>0$，却未能拒绝原假设、未能发现其优势。本题只要求在指定差异 $\theta=1$ 时将该概率控制为约 20%，不是对任意正效应都保证 80% 功效。

**English reference answer / 英文参考答案**

The hypotheses are $H_0:\mu_1-\mu_2\leq0$ and $H_a:\mu_1-\mu_2>0$. A Type I error occurs when we conclude that the new treatment is superior although its true mean response is no greater than that of the standard treatment. A Type II error occurs when we fail to detect superiority although the new treatment truly has a larger mean response. At the planning difference of 1, the target Type II error probability is 0.20.

### 2.3 Q1(b)：逐步推导样本量公式

**第 1 步：写出均值差的分布与标准误。** 令 $D=\bar Y_1-\bar Y_2$，则题目给定

$$
D\sim N\left(\theta,\sigma^2\left(\frac1{n_1}+\frac1{n_2}\right)\right),\qquad SE=\sigma\sqrt{\frac1{n_1}+\frac1{n_2}}.
$$

**第 2 步：根据原假设确定拒绝域。** 在最不利边界 $\theta=0$，$Z=D/SE\sim N(0,1)$。右侧单侧检验的拒绝规则为

$$
Z>z_{1-\alpha},\qquad\text{等价于 }D>z_{1-\alpha}SE.
$$

这里 $z_q=\Phi^{-1}(q)$ 表示标准正态分布的下侧分位数。原题的 $z_{0.05}=1.645$、$z_{0.20}=0.842$ 使用的是“上尾概率”记号，分别等于本文的 $z_{0.95}$、$z_{0.80}$。不能在 R 中直接将 `qnorm(.05)` 当成正的 1.645。

**第 3 步：在指定备择下写出功效。** 当真实差异为 $\theta>0$ 时，$(D-\theta)/SE\sim N(0,1)$，因此

$$
\operatorname{Power}(\theta)=P_\theta(D>z_{1-\alpha}SE)=1-\Phi\left(z_{1-\alpha}-\frac{\theta}{SE}\right).
$$

要求功效至少为 $1-\beta$，相当于

$$
\Phi\left(z_{1-\alpha}-\frac{\theta}{SE}\right)\leq\beta.
$$

利用 $\Phi^{-1}(\beta)=-z_{1-\beta}$，得到

$$
\frac{\theta}{SE}\geq z_{1-\alpha}+z_{1-\beta}.
$$

**第 4 步：代入分配比例。** 由 $n_1=3n_2/7$，

$$
\frac1{n_1}+\frac1{n_2}=\frac7{3n_2}+\frac1{n_2}=\frac{10}{3n_2}.
$$

所以 $SE=\sigma\sqrt{10/(3n_2)}$。平方并整理得

$$
\boxed{n_2\geq\frac{10\sigma^2}{3\theta^2}(z_{1-\alpha}+z_{1-\beta})^2,\qquad n_1=\frac37n_2.}
$$

**一般形式：** 若 $r=n_1/n_2$，则

$$
n_2\geq\frac{\sigma^2(1+1/r)}{\theta^2}(z_{1-\alpha}+z_{1-\beta})^2.
$$

**English reference answer / 英文参考答案**

Let $SE=\sigma\sqrt{1/n_1+1/n_2}$. The level-0.05 one-sided test rejects when $D>z_{1-\alpha}SE$. At a true difference $\theta$, its power is $1-\Phi(z_{1-\alpha}-\theta/SE)$. Requiring power at least $1-\beta$ gives $\theta/SE\geq z_{1-\alpha}+z_{1-\beta}$. Because $n_1=3n_2/7$, the variance factor is $1/n_1+1/n_2=10/(3n_2)$. Thus the required formula is $n_2\geq10\sigma^2(z_{1-\alpha}+z_{1-\beta})^2/(3\theta^2)$.

### 2.4 Q1(c)：计算、取整与功效回代

按题目给定的临界值计算：

$$
n_2\geq\frac{10\times2^2}{3\times1^2}(1.645+0.842)^2=\frac{40}{3}(2.487)^2=82.46892.
$$

$$
n_1=\frac37\times82.46892=35.34382286.
$$

**主推荐：严格保持 3:7。** 写成 $n_1=3k$、$n_2=7k$，其中 $k$ 为正整数。需要

$$
k\geq\frac{82.46892}{7}=11.78127429.
$$

故取 $k=12$：

$$
\boxed{n_1=36,\qquad n_2=84,\qquad N=120.}
$$

这是满足给定比例与目标功效的最小整数倍方案。新治疗组人数较少，切勿写反组别。

**可说明的近似方案：** 对两个连续解分别向上取整，得到 $n_1=36$、$n_2=83$，共 119 人。这时 $36/83\approx0.433735$，与 $3/7\approx0.428571$ 接近，但并不严格相等。原题同时出现等式约束与“尽可能保持比例”的文字，因此将两种方案讲清楚最稳妥；本资料主答案采用严格比例的 36、84。

回代功效公式（这里用 R 的完整精度正态临界值）：

$$
\operatorname{Power}=\Phi\left(\frac{1}{2\sqrt{1/n_1+1/n_2}}-z_{0.95}\right).
$$

| 方案 | 新治疗 $n_1$ | 标准治疗 $n_2$ | 总人数 | 正态近似功效 |
| --- | --- | --- | --- | --- |
| 近似比例 | 36 | 83 | 119 | 0.8052715 |
| 严格 3:7 | 36 | 84 | 120 | 0.8065153 |

两者均达到目标 0.80。使用完整精度的 `qnorm(.95)` 与 `qnorm(.80)` 时，连续解 $n_2=82.4340964$；与题目四舍五入临界值的结果略有差异，不影响整数主推荐。

```r
sigma <- 2
theta <- 1
r <- 3/7
n2 <- sigma^2 * (1 + 1/r) * (1.645 + 0.842)^2 / theta^2
n1 <- r * n2
k <- ceiling(n2 / 7)
c(n1_continuous = n1, n2_continuous = n2,
  n1_exact_ratio = 3*k, n2_exact_ratio = 7*k)
pnorm(theta / (sigma * sqrt(1/36 + 1/84)) - qnorm(.95))
```

**English reference answer / 英文参考答案**

Using the supplied quantiles, the continuous sample sizes are $n_2=82.46892$ and $n_1=35.34382$. To preserve the 3:7 ratio exactly, set $n_1=3k$ and $n_2=7k$; the smallest feasible integer is $k=12$. Therefore recruit 36 participants to the new treatment and 84 to the standard treatment, for a total of 120. The normal-approximation power is approximately 0.8065. If a slightly approximate allocation is permitted, 36 and 83 also exceed 80% power.

### 2.5 Q1(d)：结合情境解释

**中文答案 / Chinese translation**

建议招募新治疗组 36 人、标准治疗组 84 人。若两组共同标准差为 2、真实均值差为 1，该设计在单侧 5% 显著性水平下发现新治疗优势的概率约为 80.65%。这是可分析样本量，题目未给脱落率，故没有额外加入脱落膨胀；也不能保证每一次实验都得到显著结果。

**English reference answer**

Recruit 36 participants to the new-treatment group and 84 to the standard-treatment group. With a common standard deviation of 2 and a true mean advantage of 1, this design has approximately 80.65% power at a one-sided 5% significance level. These are analyzable sample sizes; no dropout allowance has been specified.

### 2.6 Q1 的知识点与常见错误

- 样本量与 $\sigma^2$ 成正比、与 $\theta^2$ 成反比：差异减半通常需要约四倍样本量。
- 在方差相同且每名受试者成本相同时，固定总人数下均衡分配可使标准误最小；本题由于约束采用不均衡分配。
- 必须先确定检验方向，再选择临界值；Q1 不使用 1.96。
- $\beta=0.20$ 对应“漏检概率”，不是 80%；目标功效是 $1-\beta=0.80$。
- 不能只给公式而省略“拒绝域 → 备择下功效 → 解不等式”这条推导链。
- 本题要求正态近似；未知标准差下的精确两样本 t 检验样本量是另一个计算问题。

## 3. Q2：单因素方差分析、多重比较与残差（原题标 18 分）

### 3.1 题目英文与中文翻译

**English — problem statement**

A pharmaceutical manufacturer wants to investigate whether the dosage level of a new drug affects its bioactivity. A completely randomized single-factor experiment was conducted using three dosage levels: 20 g, 30 g, and 40 g. Assume that the observations are independent.

**中文翻译**

某药品制造商希望研究一种新药的剂量是否影响其生物活性。实验采用完全随机化单因素设计，剂量水平为 20 g、30 g 和 40 g。假设各次观测相互独立。数据如下：

| Dosage level / 剂量水平 | Bioactivity observations / 生物活性观测值 |
| --- | --- |
| 20 g | 24，28，37，30 |
| 30 g | 37，44，31，35 |
| 40 g | 42，47，52，38 |

**English — model and questions**

The one-way ANOVA model is $Y_{ij}=\mu+\tau_i+\varepsilon_{ij}$, where $Y_{ij}$ is the bioactivity of experimental unit $j$ at dosage level $i$, $\mu$ is the overall mean, $\tau_i$ is the dosage effect, and the errors are independently distributed as $N(0,\sigma^2)$.

- **(a), 2 marks:** State the null and alternative hypotheses.
- **(b), 3 marks:** At $\alpha=0.05$, conduct ANOVA in R, provide the ANOVA table, R code, and a screenshot of the output. Report the F-statistic, p-value, decision, and contextual conclusion.
- **(c), 6 marks:** State whether pairwise comparisons are appropriate and why. Perform Tukey HSD comparisons, controlling for multiple testing; identify significant pairs and provide code and output.
- **(d), 5 marks:** Always analyze residuals. Provide suitable residual plots with code and output; comment on normality, constant variance, independence, and possible outliers. State whether the model appears adequate.

**中文翻译 — 模型与问题**

单因素方差分析模型为 $Y_{ij}=\mu+\tau_i+\varepsilon_{ij}$：$Y_{ij}$ 是剂量 $i$ 下第 $j$ 个实验单位的生物活性，$\mu$ 是总体平均水平，$\tau_i$ 是剂量效应，误差独立服从 $N(0,\sigma^2)$。

- **(a)** 写出原假设与备择假设。
- **(b)** 在 0.05 显著性水平下，用 R 检验剂量是否影响平均生物活性，提供代码、ANOVA 表和输出截图，报告 F 值、p 值、检验决策及情境结论。
- **(c)** 判断是否适合开展两两比较并说明理由；用 Tukey HSD 控制多重检验，指出显著差异的剂量对，并提供代码及输出。
- **(d)** 无论整体检验结果如何，都要分析残差；提供合适的图、代码和输出，讨论正态性、方差齐性、独立性、潜在异常点及模型是否适用。

### 3.2 Q2(a)：研究对象与假设

一个因素是剂量，三个处理水平为 20、30、40 g；响应为连续型生物活性；每组独立重复 4 次，共 $N=12$。本题是**固定效应单因素 ANOVA**，不是把数值剂量强制拟合为一条直线。

令 $\mu_{20}$、$\mu_{30}$、$\mu_{40}$ 分别为三个剂量的总体平均生物活性。

$$
H_0:\mu_{20}=\mu_{30}=\mu_{40},\qquad H_a:\text{not all three means are equal}.
$$

中文备择含义是“至少一个总体均值不同”，不是“三组任意两组都不同”。在约束 $\sum_i\tau_i=0$ 下，原假设也可以写成全部 $\tau_i=0$，备择为至少一个效应非零。

**English reference answer / 英文参考答案**

The null hypothesis is $H_0:\mu_{20}=\mu_{30}=\mu_{40}$. The alternative is that not all three population mean bioactivities are equal. Equivalently, under a sum-to-zero constraint, the null states that all dosage effects are zero.

### 3.3 Q2(b)：手算 ANOVA 的完整过程

**第 1 步：组均值与总均值。**

| 剂量 | 组内合计 | 样本量 | 样本均值 | 样本方差 |
| --- | --- | --- | --- | --- |
| 20 g | 119 | 4 | 29.75 | 29.58333 |
| 30 g | 147 | 4 | 36.75 | 29.58333 |
| 40 g | 179 | 4 | 44.75 | 36.91667 |

$$
\bar y_{\cdot\cdot}=\frac{119+147+179}{12}=\frac{445}{12}=37.08333333.
$$

**第 2 步：组间平方和。** 衡量各组均值相对总均值的差异：

$$
SS_B=\sum_{i=1}^3n_i(\bar y_i-\bar y_{\cdot\cdot})^2.
$$

$$
SS_B=4\left[(29.75-37.08333)^2+(36.75-37.08333)^2+(44.75-37.08333)^2\right]=450.6666667.
$$

上式小数仅为显示简化，实际计算保留完整精度。

**第 3 步：组内误差平方和。** 衡量同一剂量下的随机变异：

$$
SS_E=\sum_{i=1}^3\sum_{j=1}^4(y_{ij}-\bar y_i)^2.
$$

20 g 组的误差平方和为

$$
(-5.75)^2+(-1.75)^2+7.25^2+0.25^2=88.75.
$$

30 g 组为 88.75，40 g 组为 110.75，因此

$$
SS_E=88.75+88.75+110.75=288.25.
$$

总平方和检查：

$$
SS_T=SS_B+SS_E=738.9166667.
$$

**第 4 步：自由度、均方及 F 统计量。**

$$
df_B=3-1=2,\qquad df_E=12-3=9,\qquad df_T=12-1=11.
$$

$$
MS_B=\frac{450.6666667}{2}=225.3333333,\qquad MS_E=\frac{288.25}{9}=32.0277778.
$$

$$
\boxed{F=\frac{MS_B}{MS_E}=7.0355594.}
$$

在原假设及模型假设下，$F\sim F_{2,9}$。F 越大，表明“组间变异相对组内变异”越大；所以是 F 分布的右尾检验。

**ANOVA 表**

| Source / 来源 | df | SS | MS | F | p |
| --- | --- | --- | --- | --- | --- |
| Dosage / 剂量 | 2 | 450.666667 | 225.333333 | 7.035559 | 0.0144638 |
| Error / 残差 | 9 | 288.250000 | 32.027778 | — | — |
| Total / 总计 | 11 | 738.916667 | — | — | — |

临界值 $F_{2,9;0.95}=4.2564947$。由于 $7.03556>4.25649$，或等价地 $p=0.0144638<0.05$，拒绝原假设。数据提供证据表明，所研究三个剂量的总体平均生物活性并非全部相同。

**R 代码**

```r
dose <- factor(rep(c("20", "30", "40"), each = 4),
               levels = c("20", "30", "40"))
bioactivity <- c(24,28,37,30, 37,44,31,35, 42,47,52,38)
dat <- data.frame(dose, bioactivity)
fit <- aov(bioactivity ~ dose, data = dat)
summary(fit)
pf(7.035559410, df1 = 2, df2 = 9, lower.tail = FALSE)
```

`factor()` 很关键：若将 20、30、40 当作普通连续自变量，`aov(bioactivity ~ dose)` 检验的会是线性趋势，而不是题目要求的三水平分类因素总体比较。

**实际 R 输出（节选）**

```text
            Df  Sum Sq  Mean Sq F value   Pr(>F)
dose         2 450.667 225.3333 7.03556 0.014464 *
Residuals    9 288.250  32.0278
```

**English reference answer / 英文参考答案**

The sample means are 29.75, 36.75, and 44.75 for 20 g, 30 g, and 40 g, respectively. The ANOVA gives $SS_B=450.6667$ and $SS_E=288.25$, with 2 and 9 degrees of freedom. Thus $F(2,9)=7.03556$ and $p=0.0144638$. Since the p-value is below 0.05, reject the null hypothesis. There is evidence that mean bioactivity differs among the dosage levels. This result does not identify which particular pairs differ.

**中文对应结论：** 三组样本均值依次为 29.75、36.75、44.75；整体 F 检验显著，说明至少一个剂量的总体均值不同，但还不能据此宣布所有剂量对均显著。

### 3.4 Q2(c)：Tukey HSD 多重比较

**是否适合开展？** 适合。本题的整体 ANOVA 在 5% 水平显著，研究目标又涉及三个剂量之间的两两比较，因此使用 Tukey HSD 进一步定位差异。它控制这三次两两比较所构成家族的整体第一类错误率。不能用三次未经校正的普通 t 检验代替。

补充理解：Tukey 法本身提供全体两两比较的多重性控制；整体 F 显著不是它在所有分析情境下的逻辑前提。本题已经满足常见的“先总体、后比较”流程。

**计算原理。** 本题是均衡设计，每组 $n=4$。95% 同时置信区间为

$$
(\bar y_j-\bar y_i)\pm q_{0.95;3,9}\sqrt{\frac{MS_E}{n}}.
$$

其中 $q_{0.95;3,9}=3.9484922$ 是学生化极差分布临界值，不是 t 临界值。

$$
HSD=3.9484922\sqrt{\frac{32.0277778}{4}}=11.1728686.
$$

两组均值差绝对值超过 11.1728686 才显著。这里 7、15、8 三个差值中，只有 15 超过该阈值。

**Tukey HSD 结果**

| 比较（前者减后者） | 均值差 | 95% 同时置信区间 | 调整后 p 值 | 5% 水平结论 |
| --- | --- | --- | --- | --- |
| 30 g – 20 g | 7 | [-4.172869, 18.172869] | 0.2402975 | 不显著 |
| 40 g – 20 g | 15 | [3.827131, 26.172869] | 0.0114434 | 显著，40 g 更高 |
| 40 g – 30 g | 8 | [-3.172869, 19.172869] | 0.1680265 | 不显著 |

**R 代码及输出**

```r
tuk <- TukeyHSD(fit, "dose", conf.level = .95)
tuk
qtukey(.95, nmeans = 3, df = 9) * sqrt(32.02777778/4)
plot(tuk, las = 1)
```

```text
      diff         lwr        upr       p adj
30-20    7 -4.17286863 18.1728686 0.240297541
40-20   15  3.82713137 26.1728686 0.011443398
40-30    8 -3.17286863 19.1728686 0.168026548
```

![Q2 Tukey 同时置信区间：仅 40–20 的区间不含 0](reference_output/Q2_Tukey_intervals.png)

**English reference answer / 英文参考答案**

Pairwise comparisons are appropriate because the overall ANOVA is significant and identifying dosage differences is of interest. Tukey HSD controls the family-wise error rate for all pairwise comparisons. Only 40 g versus 20 g is significant: the estimated mean difference is 15, with a 95% simultaneous confidence interval of [3.8271, 26.1729] and an adjusted p-value of 0.01144. Neither 30 g versus 20 g nor 40 g versus 30 g is significant.

**中文对应结论：** 只有 40 g 的总体平均生物活性显著高于 20 g。其他两对比较未达到显著水平，这表示当前数据证据不足，不能解释为“已证明这两组完全相等”。此外，本题只测量生物活性，不能由此直接推荐临床最佳或最安全剂量。

### 3.5 Q2(d)：残差分析与模型适用性

**残差是什么？** 模型对同一组所有观测的拟合值都等于该组均值，因此

$$
\hat y_{ij}=\bar y_i,\qquad e_{ij}=y_{ij}-\bar y_i.
$$

| 剂量 | 拟合值 | 残差（与题目观测顺序一致） |
| --- | --- | --- |
| 20 g | 29.75 | -5.75，-1.75，7.25，0.25 |
| 30 g | 36.75 | 0.25，7.25，-5.75，-1.75 |
| 40 g | 44.75 | -2.75，2.25，7.25，-6.75 |

每组残差之和为 0，这是拟合方式带来的性质，不能把它当成“已经证实模型正确”。要检查的是残差的分布、离散程度和结构。

**诊断图 R 代码**

```r
par(mfrow = c(2,2))
plot(fitted(fit), resid(fit),
     xlab = "Fitted", ylab = "Residual", main = "Residuals vs fitted")
abline(h = 0, lty = 2)
qqnorm(resid(fit)); qqline(resid(fit))
plot(fitted(fit), sqrt(abs(rstandard(fit))),
     xlab = "Fitted", ylab = "sqrt(|standardized residual|)",
     main = "Scale-location")
plot(seq_along(resid(fit)), resid(fit), type = "b",
     xlab = "Index in table, not execution order", ylab = "Residual")
abline(h = 0, lty = 2)
par(mfrow = c(1,1))
shapiro.test(resid(fit))  # supplementary; low diagnostic power at n=12
max(abs(rstandard(fit)))
```

![Q2 实际 R 残差诊断图：残差-拟合值、Q-Q、尺度位置、列表顺序](reference_output/Q2_residual_diagnostics.png)

**正态性（normality）。** Q-Q 图存在可见偏离与上端并列值，不能描述为“完全贴合直线”；但没有明显的单侧极端点或严重不对称。补充 Shapiro–Wilk 检验为 $W=0.8966296$、$p=0.143498$，未在 5% 水平检出偏离正态的证据。由于总共只有 12 个观测，且拟合残差受到组内和为零的约束，这一 p 值只作辅助；它不证明误差正态。

**方差齐性（constant variance）。** 三组样本方差为 29.5833、29.5833、36.9167，最大/最小约为 1.2479。残差图的三个竖向点簇离散范围接近，没有明显随拟合值增大而扩张的漏斗形。方差相同的假设暂可接受，但每组 4 个观测不足以精确判断方差。

**独立性（independence）。** 题目明确假定独立，并采用完全随机化设计，这是独立性的主要依据。右下图的横轴只是按剂量排列的题目列表顺序，**并非真实实验执行顺序**；不能用这张图证明“没有时间自相关”。如果要检查漂移或批次效应，需要真实执行顺序、批次信息及实验单位的独立性记录。

**异常值（outliers）。** 本题各观测杠杆值为 $h_{ii}=1/4$，标准化残差为

$$
r_{ij}=\frac{e_{ij}}{\sqrt{MS_E(1-h_{ii})}}.
$$

最大绝对标准化残差约为 1.4793，未显示通常以 2 或 3 为经验参考的明显异常点。该经验规则不是绝对判据，不应据此自动删除数据。

**模型是否适用？** 就现有数据而言，没有发现足以明显否定 ANOVA 的严重方差不齐、极端异常点或严重分布问题；在题目独立性假设下，单因素 ANOVA 可暂认为适用。由于样本小，结论应保留诊断能力有限这一条件。这里剂量作为分类因素，不要求三个均值必须位于一条直线上。

**English reference answer / 英文参考答案**

The residual-versus-fitted and scale-location plots show comparable spread across the three fitted group means, without a clear funnel pattern. The Q-Q plot has some departures and tied upper residuals but no obvious severe skewness or isolated extreme point; the supplementary Shapiro–Wilk p-value is 0.1435. The maximum absolute standardized residual is approximately 1.479, so there is no conspicuous outlier. Independence is assumed in the question and supported by the randomized design; the table order is not the experimental run order and cannot establish absence of serial dependence. Overall, the model appears provisionally adequate, subject to the limited diagnostic information in this small sample.

### 3.6 Q2 的知识点与常见错误

- ANOVA 的原假设涉及总体均值，而不是三组样本均值数值恰好相等。
- F 分母应为组内均方 $MS_E$，不能使用总平方和或组间平方和直接相除。
- 残差自由度是 $N-a=9$，不是 11，也不是每组的 3。
- Tukey 的 `p adj` 是调整后的 p 值；应按整个比较家族解释。
- 置信区间含 0 与“不显著”对应，不能把不显著当成等效性结论。
- 残差诊断应始终进行，不以 ANOVA 是否显著为前提。
- 正态性假设针对误差或组内偏离，不能要求合并后的三组原始响应必须服从单一正态分布。

## 4. Q3：随机化检验、非中心参数与功效（10 分）

### 4.1 题目英文与中文翻译

**English — problem statement**

A university runs a randomized experiment to compare two reminder messages encouraging students to book a free flu-shot appointment. The treatment group receives a personalized text reminder; the control group receives a standard text reminder. A total of 400 students are randomly assigned, with 200 in each group. The binary outcome is 1 if the student books within 7 days, and 0 otherwise.

**中文翻译**

某大学开展随机实验，比较两种用于鼓励学生预约免费流感疫苗的提醒信息。处理组收到个性化短信，对照组收到标准短信。400 名学生随机分成两组，每组 200 人。若学生在 7 天内预约，结局记为 1，否则记为 0。观察结果如下：

| Group / 分组 | Booked / 已预约 | Did not book / 未预约 | Total / 合计 |
| --- | --- | --- | --- |
| Treatment / 个性化短信组 | 80 | 120 | 200 |
| Control / 标准短信组 | 60 | 140 | 200 |
| Total / 合计 | 140 | 260 | 400 |

**English — parameters and questions**

The parameter of interest is $p_T-p_C$, and the hypotheses are $H_0:p_T-p_C=0$ against $H_A:p_T-p_C\ne0$.

**(a), 7 marks:** Use a randomization test under complete random assignment. Include the idea, observed sample proportion difference, R code with at least 20,000 randomizations and `set.seed(123)`, an approximate two-sided p-value, and a contextual conclusion at the 5% significance level.

**(b), 3 marks:** For a future experiment with 200 students per group and true proportions $p_T=0.50$ and $p_C=0.40$, compute the specified noncentrality parameter $\delta$ and approximate the power of a two-sided 5% test. Use the large-sample approximation $Z\sim N(\delta,1)$ under the alternative.

**中文翻译 — 参数与问题**

关心的参数是处理组与对照组的预约概率差 $p_T-p_C$。原假设为两组预约概率相同，备择为两组概率不相同。

**(a)** 在完全随机分配机制下，采用随机化检验判断观察到的比例差是否可由随机分组合理解释。答案包括检验思想、观察比例差、至少 20,000 次随机化的 R 代码且设 `set.seed(123)`、近似双侧 p 值和 5% 水平结论。

**(b)** 未来每组仍为 200 人，假定真实预约概率分别为 0.50、0.40。使用题目给定的大样本非中心参数公式求 $\delta$，再按备择下 $Z\sim N(\delta,1)$ 近似计算双侧 5% 检验的功效。

### 4.2 Q3(a)：随机化检验的思想

在课程使用的“处理不影响结局、处理标签可交换”的随机化原假设下，将 400 个已观察到的 0/1 结局固定，只重新随机分配处理标签。每次仍恰好分配 200 人到处理组，其余 200 人到对照组，并重新计算比例差。

重复后得到原假设下由随机分组产生的差异分布。双侧 p 值估计为：其中有多大比例满足“比例差的绝对值至少与观察值一样大”。

**严谨性补充：** 有限总体中，Fisher 随机化检验的精确解释通常基于个体层面的“无处理效应”尖锐原假设；单独写总体比例相等是较弱的表述。在两组二项样本的共同概率模型下，也可将本题解释为固定总成功数后的条件检验。以下按照作业预期的固定结局、随机标签方法完成，不声称在任意效应异质情形下仅凭平均比例相等就自动获得同一精确性。

### 4.3 Q3(a)：观察统计量

$$
\hat p_T=\frac{80}{200}=0.40,\qquad\hat p_C=\frac{60}{200}=0.30.
$$

$$
\boxed{D_{obs}=\hat p_T-\hat p_C=0.10.}
$$

个性化短信组观察预约率高 **10 个百分点**。不能将它写成“相对增加 10%”；相对增加的样本比值为 $(0.40-0.30)/0.30\approx33.33\%$，与本题采用的差值不是同一个效应度量。

### 4.4 Q3(a)：Monte Carlo R 代码与实际结果

```r
set.seed(123)
B <- 20000L
y <- c(rep(1L, 140), rep(0L, 260))
obs_diff <- 80/200 - 60/200

perm_diff <- replicate(B, {
  # Sample exactly 200 treatment students, without replacement.
  trt <- sample.int(400L, size = 200L, replace = FALSE)
  x <- sum(y[trt])
  # The control group then contains 140 - x booked students.
  (2*x - 140)/200
})

# Include ties; tolerance protects against floating-point roundoff.
b <- sum(abs(perm_diff) >= abs(obs_diff) - 1e-12)
p_raw <- b/B
p_mc <- (b + 1)/(B + 1)
mc_se <- sqrt(p_raw * (1 - p_raw)/B)
c(extreme = b, B = B, p_raw = p_raw, p_mc = p_mc, MC_SE = mc_se)
```

**实际运行输出**

```text
RNG settings: Mersenne-Twister, Inversion, Rejection
Observed difference = 0.100000000
B = 20000; extreme count = 965
Raw p = 0.048250000
Plus-one p = 0.048297585
Monte Carlo SE = 0.001515288
```

因此本次模拟的主报告 p 值为

$$
\boxed{\hat p_{MC}=\frac{965+1}{20000+1}=0.0482976.}
$$

使用 $b/B=0.04825$ 也是常见的 Monte Carlo 尾概率估计；此处主报告采用加一修正，避免有限次模拟得到机械的零 p 值。两者不改变本次判断。

![Q3 随机化原假设分布：虚线为正负 0.10](reference_output/Q3_randomization_distribution.png)

**为什么不能在每次随机化中使用有放回抽样？** 原实验固定每组 200 名不同学生；有放回抽样会重复学生、遗漏其他学生，改变原分配机制，得到的不是本题的随机化分布。也不应逐人独立掷硬币后允许两组人数任意变化。

**为什么必须包括并列值？** “同样或更极端”包含等于观察值的情况。本题统计量是离散的，忽略等号会明显改变 p 值。浮点数的 `0.4 - 0.3` 与直接写的 `0.1` 可能在末位不同，因此代码添加 $10^{-12}$ 容差，或可直接使用整数条件 $X\leq60$ 或 $X\geq80$。

### 4.5 Q3(a)：超几何精确核验

固定全体 400 人中有 140 人预约，重新随机选择 200 人作为处理组。令处理组预约人数为 $X$，则

$$
X\sim\operatorname{Hypergeometric}(N=400,K=140,n=200).
$$

其中 $N$ 是总体人数、$K$ 是预约总人数、$n$ 是抽入处理组的人数。R 的 `phyper(q, m, n, k)` 则依次使用“成功数、失败数、抽取数”参数，注意两个记号体系不同。

每次的比例差是

$$
D=\frac{X}{200}-\frac{140-X}{200}=\frac{2X-140}{200}.
$$

于是双侧极端条件为

$$
|D|\geq0.10\quad\Longleftrightarrow\quad X\leq60\text{ 或 }X\geq80.
$$

```r
p_exact <- phyper(60, m = 140, n = 260, k = 200) +
  phyper(79, m = 140, n = 260, k = 200, lower.tail = FALSE)
p_exact
# [1] 0.046211128
```

第二个尾部使用 79 而不是 80，因为要计算 $P(X\geq80)=P(X>79)$。

精确双侧 p 值为 **0.0462111**，与模拟值约 0.04830 的差约为 0.00209，即约 1.38 个 Monte Carlo 标准误，属于合理模拟波动。由于结果靠近 0.05，报告模拟次数、固定种子、抽样方法和精确核验尤其有用。模拟代码改用 `rhyper()`、改变结局排列、改变随机数版本，即使 `set.seed(123)` 相同，也可能得到不同近似 p 值；这不构成数学矛盾。

### 4.6 Q3(a)：中英文结论

**中文答案 / Chinese translation**

观察到个性化短信组预约率为 40%，标准短信组为 30%，相差 10 个百分点。本次 20,000 次随机化的双侧 p 值约为 0.04830；精确条件 p 值约为 0.04621。由于它们低于 0.05，在 5% 水平拒绝两组预约概率相同的原假设。数据为两种提醒方式的预约率不同提供了证据，观察方向支持个性化短信更高；但结果接近显著性边界，不能说随机机会绝不可能解释差异，也不能说个性化短信一定对每个学生有效。

**English reference answer**

Under the randomization null, keep the 400 observed outcomes fixed and repeatedly assign exactly 200 students to treatment. The observed difference is $80/200-60/200=0.10$. With `set.seed(123)` and 20,000 randomizations using the stated algorithm, 965 randomized differences are at least as extreme in absolute value. The plus-one two-sided Monte Carlo p-value is 0.04830; the exact conditional p-value is 0.04621. At the 5% level, reject the null hypothesis. There is evidence of a difference in booking rates, with the observed direction favoring personalized reminders. The evidence is close to the significance threshold.

### 4.7 Q3(b)：计算非中心参数 NCP

这里是**未来实验的设定**，必须使用题目给定的真实比例 0.50 和 0.40，不能拿当前样本的 0.40 和 0.30 代入。

题目定义

$$
\delta=\frac{|p_T-p_C|}{\sqrt{p_T(1-p_T)/n_T+p_C(1-p_C)/n_C}}.
$$

先计算备择下标准误：

$$
SE_A=\sqrt{\frac{0.50\times0.50}{200}+\frac{0.40\times0.60}{200}}=\sqrt{0.00245}=0.0494974747.
$$

因此

$$
\boxed{\delta=\frac{0.10}{0.0494974747}=2.02030509.}
$$

这个数表示真实差异为大约 2.02 个标准误。它是标准化偏移量，不是概率，也不是某次实验观察到的 Z 统计量。

### 4.8 Q3(b)：计算双侧 5% 检验功效

原假设下近似拒绝域为

$$
|Z|>z_{0.975}=1.95996398.
$$

题目要求在备择下使用 $Z\sim N(\delta,1)$。令 $W=Z-\delta\sim N(0,1)$，则

$$
\operatorname{Power}=P_\delta(Z>z_{0.975})+P_\delta(Z<-z_{0.975}).
$$

$$
\operatorname{Power}=1-\Phi(z_{0.975}-\delta)+\Phi(-z_{0.975}-\delta).
$$

代入得

$$
\operatorname{Power}=\Phi(0.06034110)+\Phi(-3.98026907).
$$

$$
\operatorname{Power}=0.524058018+0.000034419=\boxed{0.524092436\approx52.41\%.}
$$

相应第二类错误概率为 $\beta\approx0.4759076$。右尾是主要部分，但完整双侧公式仍应写出左尾。

**R 代码与输出**

```r
pT <- .50; pC <- .40
nT <- 200; nC <- 200
se_alt <- sqrt(pT*(1-pT)/nT + pC*(1-pC)/nC)
delta <- abs(pT-pC)/se_alt
zcrit <- qnorm(.975)
power <- pnorm(delta-zcrit) + pnorm(-zcrit-delta)
c(SE = se_alt, delta = delta, power = power, beta = 1-power)
```

```text
Alternative SE = 0.049497475
delta = 2.020305089
Critical z = 1.959963985
Two-sided power = 0.524092436 (52.4092%)
beta = 0.475907564
```

**English reference answer / 英文参考答案**

The alternative standard error is $\sqrt{0.50(0.50)/200+0.40(0.60)/200}=0.04949747$, giving $\delta=2.020305$. With $z_{0.975}=1.959964$ and $Z\sim N(\delta,1)$ under the alternative, the approximate power is $1-\Phi(1.959964-2.020305)+\Phi(-1.959964-2.020305)=0.524092$. Thus the study has approximately 52.41% power to detect the specified 10-percentage-point difference.

**中文对应解释：** 如果真实预约率为 50% 和 40%，每组 200 人时，重复进行这种设计并使用题目指定的双侧正态近似检验，约 52.41% 的实验会拒绝原假设。它不表示有 52.41% 的学生预约，也不表示个性化短信有 52.41% 的概率有效。此处计算的是题目指定的大样本 Z 近似功效，不是对 Q3(a) 精确离散随机化检验功效的逐项枚举。

### 4.9 Q3 的知识点与常见错误

- 随机化检验固定结局、重抽处理标签；不是重新生成一批 0/1 结局。
- 双侧比较使用 $|D^*|\geq|D_{obs}|$，必须包括等号。
- 本题两组均为 200 人；每次随机化必须保持这一分配机制。
- 正态比例检验、连续性校正卡方检验、随机化检验和其他近似可能给出不同 p 值，不能将别的检验结果直接冒充本题的随机化结果。
- 样本量 $n=200$ 与模拟次数 $B=20000$ 作用不同：前者影响实验功效，后者影响 Monte Carlo 估计精度。增加 $B$ 不会增加现有实验的信息量。
- 功效计算使用预设真实效应；Q3(b) 的 $\delta$ 分母按题目规定使用备择比例，不能擅自替换成当前样本合并比例。
- 统计显著不等于大效应或重要效应；本题观察差异为 10 个百分点，统计证据接近 5% 边界。

## 5. 复习用公式表与解题流程

### 5.1 公式表

| 知识点 | 公式或规则 | 适用条件 |
| --- | --- | --- |
| 两独立均值差标准误 | $\sigma\sqrt{1/n_1+1/n_2}$ | 共同标准差、独立两组 |
| 单侧功效 | $\Phi(\theta/SE-z_{1-\alpha})$ | 本题正态规划近似 |
| 不等分配样本量 | $n_2\geq\sigma^2(1+1/r)(z_{1-\alpha}+z_{1-\beta})^2/\theta^2$ | $r=n_1/n_2$，单侧比较 |
| ANOVA 平方和 | $SS_T=SS_B+SS_E$ | 单因素组均值模型 |
| ANOVA F | $F=(SS_B/(a-1))/(SS_E/(N-a))$ | 独立、正态、共同方差下使用 F 分布 |
| 均衡 Tukey HSD | $q_{1-\alpha;a,N-a}\sqrt{MS_E/n}$ | 所有组样本量相同 |
| 残差 | $e_{ij}=y_{ij}-\bar y_i$ | 单因素分类模型 |
| Monte Carlo p 值 | $(b+1)/(B+1)$ | $b$ 计数同样或更极端的模拟统计量 |
| 比例差 NCP | $\delta=\lvert p_T-p_C\rvert/SE_A$ | 使用指定真实比例 |
| 双侧正态近似功效 | $1-\Phi(c-\delta)+\Phi(-c-\delta)$ | $c=z_{1-\alpha/2}$，备择下方差近似为 1 |

### 5.2 拿到同类题目的操作顺序

1. 明确实验单位、因素、处理水平和响应类型，区分设计前规划与设计后分析。
2. 定义总体参数，写清检验方向，并说明原假设。
3. 写统计量及其标准误；推导题从拒绝域进入功效，再反解样本量。
4. 对多组连续响应先进行整体 ANOVA，再按研究目标进行有校正的比较。
5. 用图与实验设计记录评估模型假设；避免把“不显著”写成“已经证明”。
6. 对随机化问题严格复现原分配规则，并明确双侧尾部和并列值的处理。
7. 将统计结论翻译成研究情境中的一句话，同时报告效应大小。

## 6. 文件清单、运行方法与输出图像

### 6.1 本资料配套文件

- `Assignment2_参考答案与解析_中英对照.md`：完整题目翻译、中英文参考答案、推导、知识点。
- `output/pdf/Assignment2_参考答案与解析_中英对照.pdf`：便于阅读与打印的排版版本。
- [Assignment2_reference_analysis.R](Assignment2_reference_analysis.R)：实际运行过的完整 R 脚本，只依赖 base R。
- [reference_output/R_output.txt](reference_output/R_output.txt)：真实运行日志，包含 R 版本、全部核心数值、残差及会话信息。
- `reference_output/Q2_*.csv`：原始数据、组描述、ANOVA 表、Tukey 表及残差表。
- `reference_output/Q2_residual_diagnostics.png`、`Q2_Tukey_intervals.png`、`Q3_randomization_distribution.png`：R 实际绘制的图。
- `reference_output/Q2_R_output.png`、`Q3_R_output.png`：对真实 R 日志的忠实图像排版，便于阅读核对；不是 RStudio 界面截图。正式作业如要求界面截图，应本人运行代码后按教师要求截取。

### 6.2 如何运行

在 RStudio 中将工作目录设为本 Assignment2 文件夹，打开脚本并运行全部代码；也可用 `source()` 执行该文件，或在终端运行：

```text
Rscript Assignment2_reference_analysis.R
```

若 Rscript 没有加入 PATH，可在 PowerShell 中使用本机现有路径：

```powershell
& 'D:\Program Files\R\R-4.6.1\bin\Rscript.exe' --vanilla '.\Assignment2_reference_analysis.R'
```

使用 Rscript 或 `source()` 执行时，脚本把输出写入自身所在目录下的 `reference_output/`；逐行运行时则写入当前工作目录下的同名文件夹。学习版中展示的 R 结果在 R 4.6.1、默认 Mersenne-Twister / Inversion / Rejection 随机数设置下实际生成。R 版本、算法和原始结局排列已记录，以便区分可复现计算与 Monte Carlo 波动。

### 6.3 实际输出图像

**Q2：ANOVA 与 Tukey 真实输出的图像排版**

![Q2 实际运行输出](reference_output/Q2_R_output.png)

**Q3：随机化检验与功效真实输出的图像排版**

![Q3 实际运行输出](reference_output/Q3_R_output.png)

## 7. 资料定位与核验范围

以下页码均为 PDF 文件中的物理页码，可能与幻灯片自带页码不同。

| 本资料内容 | 本地依据与位置 |
| --- | --- |
| 题目、数值、分配约束、提交要求 | `Assignment #2.pdf`，第 1–7 页 |
| 两均值比较的功效、标准化偏移及样本量 | `../lecture/6008-week2-canvas.pdf`，第 33–39 页 |
| 随机化检验与标签可交换性 | `../lecture/6008-week3-canvas.pdf`，第 85–89 页 |
| 临床试验样本量与非中心参数思想 | `../lecture/6008-week4-new-canvas.pdf`，第 29–31、47–52 页 |
| ANOVA 误差假设与残差检查 | `../lecture/6008-week5-canvas.pdf`，第 59–67 页 |
| Tukey 临界值、同时区间及 R 实现 | `../lecture/6008-week6-new-canvas.pdf`，第 20–29 页 |

**核验范围：** Q1 使用题目给定分位数推导并用完整精度分位数回代功效；Q2 同时核对手算平方和与 R 的 `aov()`，并核对 Tukey 区间；Q3 同时进行 20,000 次 Monte Carlo 随机化和超几何分布精确求和。中间计算未提前四舍五入，表格为显示而取适当小数位。
