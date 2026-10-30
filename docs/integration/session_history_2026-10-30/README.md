# 删除研究与对话历史

用户要求为每条历史研究/对话增加删除按钮。本轮按整段会话实现：左侧“最近研究”每条右侧显示“删除”，确认后移除该会话的聊天、计划快照、会话内工具记录和导出。原始项目目录与所选论文源文件保留。

删除当前会话后切换到可用的其他会话；没有剩余会话时显示空白入口，不回退合成预览。取消确认或请求失败保留原页面。正在处理、后台运行或被其他进程锁定的会话拒绝删除；清理中断的条目显示“删除未完成”，可重试。

后端入口是 `POST /ui/sessions/<id>/delete`，请求体为 `{"confirm":"<id>"}`，保留本地token和同源检查。删除仅接受会话根目录内、身份匹配的应用会话，拒绝路径越界、符号链接及Windows目录联接。递归删除前重新核对绝对路径。删除标记仅保存会话ID，避免重放旧请求或重新加载已删除会话。

HTTP缓存现在记录所属会话，删除时清理对应结果。旧缓存没有归属信息，其结果载荷一并清理，保留请求哈希和失效状态，避免重试触发旧模型/工具操作；其他会话的正式记录和带归属的新缓存保留。

实现期间仅删除测试创建的临时会话，没有清理用户已有研究。本轮没有调用模型、训练或真实科研执行。

## 验证

[当前验收](verification.json)保存实际测试数量、HTTP删除及界面状态检查；[测试回执](tests.json)绑定执行的源码。界面测试执行发布的JavaScript并使用模拟DOM，覆盖取消、非当前会话、当前会话切换、删除最后一条和请求失败，不等于浏览器视觉验收。

本轮应用回归478项，0失败/错误、2项跳过；完整性与评分检查40项通过，界面状态检查5项通过，便携检查通过。旧集成JSON保持一致，原研究权重未改。

源码变更通过本目录的 `before_snapshot.json`、`authorized_source_changes.json` 和 `runtime_manifest.json` 接续原保护链，旧集成JSON与研究权重不重写。原 `verify_dynamic_upgrade.py` 等当前验收链转入本层，旧测试回执保留历史含义。

```powershell
& '.\RUT_Science\.venv\Scripts\python.exe' -B scripts/check_repository.py
& '.\RUT_Science\.venv\Scripts\python.exe' -B scripts/verify_session_history.py
# 修改代码后重跑当前应用、完整性和界面状态测试：
& '.\RUT_Science\.venv\Scripts\python.exe' -B scripts/verify_session_history.py --run-tests
```

使用时重启本地浏览器服务并刷新页面；静态示例没有私有会话连接，删除按钮只在已连接的历史列表中生效。
