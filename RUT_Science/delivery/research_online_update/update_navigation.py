"""Make current entry state discoverable; retain stage reports as dated evidence."""
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]


def note(relative, body):
    path = PROJECT/relative
    original = path.read_text(encoding="utf-8")
    if body in original:
        return
    backup = HERE/"documents_before"/relative
    backup.parent.mkdir(parents=True, exist_ok=True)
    if not backup.exists():
        shutil.copy2(path, backup)
    title, rest = original.split("\n", 1)
    path.write_text(title+"\n\n"+body+"\n"+rest, encoding="utf-8")


def main():
    note("README.md", "**研究接口已上线（2026-10-27）**：G2.2/G2.3/G2.4现在可从原 `science-bot.cmd` 使用。聊天中输入 `/research`、`/doe demo` 或 `/research simulate g2_3`。支持结果、完整性检查、冻结策略开发模拟、DOE验收和审阅导入；默认访谈仍为规则，真实实验禁用。[使用说明](RUT_Science/docs/Science_Bot_研究接口上线_zh.md) · [交付验收](RUT_Science/delivery/research_online_update/README_本轮交付.md)。下方阶段交付记录描述各自交付当时状态，以本条为当前接入状态。")
    note("science_Bot_交接.md", "当前接入状态：三轮研究功能已接入原终端和HTTP消息入口，命令 `/research`、`/doe`。见 [研究接口上线](RUT_Science/docs/Science_Bot_研究接口上线_zh.md)。学习权重仅显式用于开发模拟，默认访谈保持规则。G2.4可在聊天中检查显式DOE协议，未开放真实执行或自动训练。下方旧交付描述保留其阶段范围。")
    note("science_Bot_交付.md", "研究接口当前可直接使用：启动原 `science-bot.cmd` 后输入 `/research` 或 `/doe demo`。完整参数与示例见 [研究接口使用](RUT_Science/docs/Science_Bot_研究接口上线_zh.md)，当前总验收见 [上线交付](RUT_Science/delivery/research_online_update/README_本轮交付.md)。")
    note("RUT_Science/README.md", "**研究接口上线更新**：G2.2/G2.3/G2.4已接入现有终端与HTTP消息接口，输入 `/research` 查看；`/doe demo`、显式DOE协议验收与冻结策略开发模拟可用。[使用说明](docs/Science_Bot_研究接口上线_zh.md)。下面未接入时的阶段说明保留历史范围。")
    note("RUT_Science/research/strategy_learning/README.md", "**当前应用接入**：[G2.2/G2.3/G2.4研究接口](../../docs/Science_Bot_研究接口上线_zh.md) 已可通过原science Bot聊天及HTTP messages使用。原研究CLI保留，当前统一 `verify` 使用G2.4上线兼容审计。冻结的各轮说明、隔离保护清单和结果不改写；以本条说明当前状态。")
    note("RUT_Science/docs/Science_Bot_Workspace_zh.md", "研究接口当前已接入：`/research` 和 `/doe` 的证据保存到当前会话 `research/`；工作区读取路径和预算沿用已有约束。见 [研究接口上线](Science_Bot_研究接口上线_zh.md)。此前‘尚未注册’说明为当时交付状态。")
    note("RUT_Science/docs/Science_Bot_G2_4_DOE协议与统一验收_zh.md", "上线补充：G2.4现在已通过独立只读桥接接入原聊天入口，支持 `/doe demo/template/validate/recheck/report/review-export/review-import`。详见 [当前使用说明](Science_Bot_研究接口上线_zh.md)。下文记录G2.4最初交付时的隔离实现和边界，冻结协议不变。")
    note("阶段性总结2_2026-10-27.md", "> 当前入口更新：G2.2/G2.3/G2.4已接入原聊天终端与HTTP消息路由；本次上线是研究检查、开发模拟与DOE验收，不包含默认学习策略替换或真实实验。见第12节和 [上线说明](RUT_Science/docs/Science_Bot_研究接口上线_zh.md)。各节原研究数据与当时的接入状态保持历史范围。")
    path = PROJECT/"阶段性总结2_2026-10-27.md"
    text = path.read_text(encoding="utf-8")
    if "## 12. 研究接口上线" not in text:
        path.write_text(text+"""

## 12. 研究接口上线（2026-10-27）

按照用户要求，将G2.2/G2.3/G2.4接入现有science Bot入口：[使用说明](RUT_Science/docs/Science_Bot_研究接口上线_zh.md)、[本轮验收](RUT_Science/delivery/research_online_update/README_本轮交付.md)。重启应用后，聊天可直接使用 `/research` 和 `/doe`；本地HTTP沿用原messages、status和report路由。

- G2.2：结果、完整性核对、规则/冻结BC开发模拟、72条待审副本和审阅验证。
- G2.3：严格评分结果、六种规则/冻结策略比较、CViT配置/作业模拟和快照恢复；不训练或推广默认权重。
- G2.4：三种DOE模板、显式需求/草案检查、步骤和反馈、文件变更复核、42条待审副本与审阅验证。
- 主会话：共享工具/读取预算，结果存入research目录，状态/报告/恢复有哈希核对；重复请求不重复消耗工具次数，实时完整性检查例外。
- 隔离：固定只读子进程，阻止网络、写入和真实Agent/CViT导入；原研究源码、权重、任务和历史报告不变。
- 数值边界：极端统计诊断若产生非有限数值，桥接层返回阻断，未改写冻结验收协议。
- 授权：明确修改6个宿主源码接入接口，原启动文件不变；原‘应用未改动’验收保持历史范围，当前增加上线兼容审计。

本次没有真实模型API、科学工具或GPU作业，也没有正式训练transitions。默认访谈保持规则，真人专家标签仍为0。旧G2.4封存记录未打开用于当前评分。后续先进行专家审阅与独立任务验证，再决定新的策略训练。
""", encoding="utf-8")
    print("Research online entry and stage summary navigation updated")


if __name__ == "__main__":
    main()
