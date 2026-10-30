# 终端与本地浏览器入口交付 · 2026-10-29

按用户要求分别交付终端和本地浏览器示例，不引入 MetaGPT。使用与试用步骤统一维护在[使用说明](../../USAGE.md)，可直接打开[终端](../../../examples/interfaces/terminal.html)、[浏览器](../../../examples/interfaces/browser.html)与[交付阅读版](../../../examples/interfaces/delivery.html)。

终端新增入口卡片、规划摘要、交付概览和 `/deliver`；浏览器提供概览、对话、计划、显式证据选择、版本确认及三格式下载。两者通过共享只读投影连接原会话、版本账本和校验，HTML 导出对照冻结快照并检查确认决定。合成示例保留未知和模型提议，不调用模型、不读取真实论文、不执行实验。

## 完整性与验证

- `before_snapshot.json`、`before_packaging.json` 固定改动前文件及历史证据；`authorized_source_changes.json`、`runtime_manifest.json` 仅追加终端、启动器、包资源和新界面共11个运行文件，不改历史清单。
- `full_tests.json` 保存本次应用与完整性测试的实际结果、运行清单及测试源码哈希；`verification.json` 核对当前完整性、历史评估、64个训练制品及可重生成的示例。具体数量以这两份机器记录为准。
- 本次应用回归427项，0失败/错误、2跳过；完整性测试19项通过。便携检查通过1745个保护文件、78个冻结研究制品和离线启动/研究流程；JavaScript语法及52处页面绑定检查通过，原终端启动器预览运行成功。
- 新测试实际走终端命令与 HTTP：合成内容、离线边界、版本确认与失效、三格式导出、篡改拒绝、同源和本地凭据校验、恢复及请求幂等。
- 浏览器视觉验收**未完成**：Computer Use 安全检查无法可靠识别当前浏览器 URL，已终止 UI 自动操作。代码、HTTP 与导出检查不能替代浏览器视觉及可用性验收。

```powershell
& '.\RUT_Science\.venv\Scripts\python.exe' -B scripts/preview_interfaces.py
& '.\RUT_Science\.venv\Scripts\python.exe' -B scripts/verify_interfaces.py --run-tests
```

旧 `verify_dynamic_upgrade.py` 自动转入本层审计，历史412项测试及真实接口评估仍按原版本保存，不覆盖、不累计为当前质量结论。没有真人理解测试、科学有效性验证、真实执行或自动提交/推送。
