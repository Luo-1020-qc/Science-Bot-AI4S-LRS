"""Update current navigation; leave application and frozen research unchanged."""
from pathlib import Path
import shutil

PROJECT = Path(__file__).resolve().parents[3]
STUDY = PROJECT/"RUT_Science/research/strategy_learning/studies/g2_4"


def update(relative, transform):
    path = PROJECT/relative
    original = path.read_text(encoding="utf-8")
    backup = STUDY/"evidence/documents_before"/relative
    if not backup.exists():
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup)
    path.write_text(transform(original), encoding="utf-8")


def note(text, body):
    if body in text:
        return text
    title, rest = text.split("\n", 1)
    return title+"\n\n"+body+"\n"+rest


def main():
    update("README.md", lambda text: note(text,
        "**G2.4已交付（2026-10-27）**：[DOE协议与统一验收](RUT_Science/delivery/g2_4_update/README_本轮交付.md) 已纳入研究入口，覆盖三种有界DOE设计、来源校验、功效、设计步骤与待审任务库。G2.4的49项测试通过，三轮研究合计125项；真人专家标签仍为0，线上访谈与真实工具范围不变。"
        ).replace("│       └── integration_results/", "│       ├── studies/g2_4/                  # DOE协议、验收、专家待审与封存任务\n│       └── integration_results/") if "studies/g2_4/" not in text else text)
    update("science_Bot_交接.md", lambda text: note(text,
        "G2.4更新：[本轮交付](RUT_Science/delivery/g2_4_update/README_本轮交付.md) 已完成研究层DOE协议、统一验收/评分和待专家校准任务库。49项新增研究测试通过，整体125项；84/42/42案例、42条待审、0真人专家标签。协议审核不授权真实执行，未训练新策略。"
        ).replace("建议下一步先统一严格评分与开发选模，再取得真正的专家审阅、建立新盲测与跨任务验证。", "G2.4已提供一致的严格评分与开发选模接口；下一步取得真正的专家审阅、校准规则并建立独立案例与跨任务验证。"))
    update("science_Bot_交付.md", lambda text: note(text,
        "当前新增交付：[G2.4 DOE协议与统一验收](RUT_Science/delivery/g2_4_update/README_本轮交付.md)。使用同一研究脚本的 `--study g2_4`，默认all现覆盖三轮125项测试。专家校准待审，线上入口保持原状。"))
    update("RUT_Science/README.md", lambda text: note(text,
        "**G2.4研究更新**：[DOE协议与统一验收](docs/Science_Bot_G2_4_DOE协议与统一验收_zh.md) 已交付三种有界设计与42条专家待审记录。没有新增线上DOE工具或新策略训练；研究测试现为39＋37＋49＝125项。"))
    update("RUT_Science/research/strategy_learning/README.md", lambda text: note(text,
        "**G2.4已加入统一研究入口**：[DOE协议、统一验收与待专家校准任务库](studies/g2_4/README_本轮交付.md)。新增49项测试，三轮合计125项；当前真人专家标签0。"
        ).replace("| G2.3 修订试验 |", "| [G2.4](studies/g2_4/README_本轮交付.md) | `studies/g2_4/` | 84/42/42；DOE编译、统一评分、42条待审 | 开发42/42符合脚本预期，尚未专家校准，无新策略训练 |\n| G2.3 修订试验 |") if "| [G2.4]" not in text else text)
    update("RUT_Science/docs/Science_Bot_Workspace_zh.md", lambda text: note(text,
        "> G2.4更新：[DOE协议研究](Science_Bot_G2_4_DOE协议与统一验收_zh.md) 位于统一研究模块，尚未注册为对话工具；工作区绑定、读取设置和默认规则访谈沿用现有实现。"))
    def summary(text):
        body = "> G2.4更新（2026-10-27）：DOE协议、统一验收/评分和待专家校准任务库已交付研究层；49项测试通过，三轮研究合计125项。详细记录见本文第11节，原合并数据保持其历史范围。"
        text = note(text, body).replace("截至 G2.3 的已保存实现", "截至 G2.4 的已保存实现")
        if "## 11. G2.4" not in text:
            text += """

## 11. G2.4：DOE协议与统一验收（2026-10-27）

已完成研究层交付：[G2.4说明](RUT_Science/research/strategy_learning/studies/g2_4/README_本轮交付.md) 与 [验收入口](RUT_Science/delivery/g2_4_update/README_本轮交付.md)。保留原应用和研究入口，不新增ZIP，不改变线上访谈或注册真实工具。

- 闭合ExperimentContract与宿主需求绑定，保存字段来源、实验单位、随机化、区组、模型、主要对比、功效和预算。
- 支持两处理完全随机设计、两处理随机完全区组设计、可带完整区组的2×2全因子设计；编译计划、矩阵和附验收条件的实验步骤。
- 核对单位与重复、随机计划、目标可估计性、模型、自由度和非中心t名义功效，报告方差敏感性与尚未验证的现实假设。
- 反馈、开发选模与最终评分使用同一严格接口，合理停止须有当前公开证据，完成奖励高于有界决策成本。
- 任务84训练/42开发/42封存，42条训练案例专家待审；真人专家标签0，封存记录未用于本轮评分。
- 49项G2.4测试通过，三轮研究合计125项；开发42/42符合脚本期望，属于合成回归诊断，不是专家认可度或Agent性能。
- 设计通过只表示ready_for_review；执行未授权、实际结果为空。没有BC/PPO新训练、模型API、真实CViT或GPU作业。

G2.4提供了下一轮强化学习所需的协议和验收基础，但专家校准、独立案例及完整学习闭环尚未完成。接下来先审阅42条待审记录、修订争议标准，再开展BC与状态聚合；随后按冻结协议比较PPO。
"""
        return text
    update("阶段性总结2_2026-10-27.md", summary)
    print("Current navigation and stage summary updated for G2.4")


if __name__ == "__main__":
    main()
