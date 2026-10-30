# 浏览器红色主题与机器人字标 · 2026-10-29

按用户要求，浏览器工作台从绿色改为红色主题。参考[CityU官网标志示例](https://www.cityu.edu.hk/sgs/files/fees/tpg/P79/CityUlogo2a.jpg)的红色/酒红观感，以 `#9F003B` 为界面主色、`#D52042` 为亮红强调，配浅红灰背景与白色卡片。这是本项目的配色适配，未将这些数值声称为学校官方色值。

`Science-Bot` 使用参考[OpenCode品牌页面](https://opencode.ai/brand)的原生像素等宽SVG字标；原字母标记替换为自行绘制的机器人SVG。图形和字标内嵌，无字体下载或外部资源请求。浏览器概览、对话、计划、证据、交付页及独立HTML交付阅读版同步配色；终端和问答策略未改动。

静态示例：[浏览器](../../../examples/interfaces/browser.html)、[HTML交付](../../../examples/interfaces/delivery.html)。启动 `.\science-bot-web.cmd -Example`，已有页面刷新即可读取新样式；重启服务后导出也使用新配色。

## 验证与范围

- 本轮实际执行9项交付/终端展示测试、6项HTTP测试、25项完整性测试，均通过。最近的444项应用全量记录仍属于Question tool版本，本次样式变更未重跑应用全量。
- 52处JavaScript元素绑定完整，JS语法检查通过。抽查的6组正文/按钮/导航颜色对比度最低4.648:1；这是数值检查，不代表完整可访问性验收。
- 5个展示源码/生成示例通过新增授权层核验，之前所有集成JSON、规划逻辑、训练数据和权重保留。
- 浏览器视觉验收未完成：Computer Use无法可靠识别当前Windows浏览器URL而停止；此后未再尝试任何浏览器自动化，也未启动额外预览服务。

```powershell
# 当前完整性与保存的检查
& '.\RUT_Science\.venv\Scripts\python.exe' -B scripts/verify_branding.py
# 重新执行本轮范围的检查
& '.\RUT_Science\.venv\Scripts\python.exe' -B scripts/verify_branding.py --run-checks
```

旧动态/界面/Question tool审计转入当前层，不重写历史收据。显式 `--run-tests` 仍表示重新执行应用全量与完整性测试。
