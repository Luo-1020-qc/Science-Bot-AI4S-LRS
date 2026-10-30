# PDF读取与论文理解接入

用户要求Harness读取PDF并由LLM理解提取含义。沿用显式证据选择与现有DeepSeek接口，新增按页文字提取和结构化理解；当前操作见[规划指南](../../HARNESS_PLANNING.md#显式选择论文片段)。

## 使用

用 `science-bot-web.cmd -Workspace <论文目录>` 启动API会话。在证据页填PDF相对路径、物理页码，明确允许模型使用所选内容后保存，再点“让LLM理解所选页”。终端支持：

```text
/plan evidence add {"path":"paper.pdf","start_page":1,"end_page":3,"share_with_model":true}
/plan evidence list
/plan evidence understand <片段编号>
```

工作区内文件由用户选择，PDF最多16 MiB，一次最多12页、18000字节文本；所有证据总计仍限制18000字节，并服从会话读取预算。超限明确拒绝，不静默截断。扫描/图片页需先OCR。表格、公式与排版顺序仍需对照原文；[pypdf提取边界](https://pypdf.readthedocs.io/en/stable/user/extract-text.html)说明相关限制。

## 数据与权限

- 解析在独立进程运行，20秒超时，拒绝加密、损坏、缺可靠文本和过大的页面。解析器不跟随链接或执行PDF动作。
- 保存文件/片段哈希、物理页码、原始页文本、提取器版本和共享标记；旧Markdown/TXT快照仍可恢复。
- 模型仅收到当前明确共享的片段，每条要点须有同页原文。仅允许空白差异对齐，保存实际原文；结构、引用或数值失败的要点逐条拒绝，不因其余内容正确而放行。
- 理解覆盖问题、方法、数据、结果、局限与复现信息，始终标为未核实的模型提议，不自动填入实验事实。引用存在不证明语义正确。
- 解读随快照保存和导出，改变内容哈希并撤销旧确认；重复查看复用结果。普通聊天历史继续保存本地规划摘要，所选页不自动进入后续聊天。

## 实际验证

使用自编两页合成论文 `examples/papers/synthetic_paper.pdf`，两页已渲染并检查。没有读取用户IDE中的真实论文。

真实接口联调共3次请求：`initial_live.json`保留引用/数值检查未通过的初次结果，`second_live.json`保留未注册字段导致的失败；完善空白对齐与逐项拒绝后，`live.json`保存成功的8条解读及实际资源。最终每条引用可在原页定位，实验声明保持空。此文件用于开发诊断，未经独立专家语义评分，不是泛化评测。

[当前验收](verification.json)与[测试回执](tests.json)记录实际范围：原证据兼容、真实PDF提取、授权、页码/数值/引用拒绝、失败原子性、缓存、导出、普通聊天隔离、HTTP和发布脚本的模拟DOM检查。当前未完成浏览器视觉验收。

本轮全量应用回归495项，0失败/错误、2项跳过；完整性与评分检查43项、模拟DOM交互检查7项通过。真实接口最终一轮接受8条要点，全部页码与引文重新校验；模型语义与科学适用性仍需人工审核。

PDF解析依赖 `pypdf`已加入应用依赖和固定版本清单；`pdf-test`额外依赖只用于创建/渲染合成示例。旧集成JSON、权重和原始数据保持原字节，通过本层授权链接续。

```powershell
& '.\RUT_Science\.venv\Scripts\python.exe' -B scripts/check_repository.py
& '.\RUT_Science\.venv\Scripts\python.exe' -B scripts/verify_pdf_reading.py
# 需要重跑当前应用和完整性检查时：
& '.\RUT_Science\.venv\Scripts\python.exe' -B scripts/verify_pdf_reading.py --run-tests
```
