# CViT任务的独立模拟测试

此目录只测试设计/作业协议，不导入 `dynamic_cvit.py`，不读取真实Darcy数据，不启动GPU训练。

- `fixtures/configurations.json`：pilot/full配置的协议夹具。
- `test_copies/configurations.json`：实际复制的测试副本，SHA-256与来源一致。
- `evidence/paused_job.json`：已对账模拟作业的状态快照。
- `evidence/demo.json`：恢复后复用existing-running作业，没有再次launch。

在上一级 `G2_3_Test_Workspace` 目录：

```powershell
& '..\RUT_Science\.venv\Scripts\python.exe' -B run.py demo
```

所有作业状态来自内存夹具，`metric=null`。配置中的epoch、资源单位及内存只是测试数值，不能作为真实CViT训练成本或性能的依据。
