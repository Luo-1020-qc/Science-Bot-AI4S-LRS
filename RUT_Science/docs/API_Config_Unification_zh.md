# v0.3.1：统一 Agent API 凭据入口

当前所有真实 API 运行统一默认使用项目级 `CityU_Hackathon_AI4S/API_key_Agent.json`。

## 已修改的入口

| 入口 | 修改 |
|---|---|
| `rut_science.configuration` | 唯一默认文件位置，由模块位置确定绝对路径；工作目录改变不影响定位 |
| 科研基准 `rut_science run` | 默认读取同一文件，端点和凭据来自同一 profile；取消环境变量与单独端点覆盖 |
| Darcy `rut_science darcy run` | 使用同一默认文件，支持一致的 profile / credential-field 选择 |
| `JSONHTTPAgent` | 未显式注入已读取凭据时从同一配置读取，并核对端点；不会读取环境变量 |
| `LangGraph_Demo/02_tool_loop.py` | 复用科研项目配置读取器，默认同一文件；offline 模式不读取凭据 |
| 两个核验脚本 | 密钥扫描从同一配置文件获取当前凭据，取消旧文件与工作区根目录回退 |
| `.gitignore` | 忽略新凭据文件 |

当前文件提供 DeepSeek 端点和有效凭据，没有 `model` 字段；仍需使用 `--model deepseek-flash` 或在配置中填写账户可用模型。`--api-config` 可显式指定同名文件的其他位置；没有读取旧凭据文件的隐式回退。

## 验证

- RUT-Science **58 项测试通过**；LangGraph Demo **3 项配置测试通过**。
- 配置测试使用名为 `API_key_Agent.json` 的临时文件与假密钥，模型请求被 mock；不在单元测试中调用用户服务。
- 覆盖默认文件路径、工作目录变更、环境变量不覆盖文件、缺失文件不回退、端点与凭据绑定，以及科研、Darcy 和 LangGraph 各入口的配置传递。
- 真实 DeepSeek Flash 接口确认通过：[检查结果](../outputs/agent_api_config_check_v031_confirmed.json)。该次检查限一个请求，核对动作 JSON 格式、请求体哈希及凭据文件未改写。
- 首次简短检查已获得真实服务响应，但未满足要求的动作 JSON 格式；保留 [首次记录](../outputs/agent_api_config_check_v031.json)。明确动作协议后重新检查通过，没有覆盖原记录。

本次没有重新执行完整科研对比评测，也没有修改原实验产物或源码快照。v0.3.0 的源码哈希与更新后的当前代码会不同；正式复跑应选新输出目录。

## 使用示例

在 `RUT_Science` 目录：

```powershell
# 不需要另外配置密钥环境变量或显式传入 --api-config。
& '.\.venv\Scripts\python.exe' -m rut_science run --agents api_direct --model deepseek-flash --task science_001 --max-seconds 180 --output outputs/live_agent_config_new
& '.\.venv\Scripts\python.exe' -m rut_science darcy run --agent api_direct --model deepseek-flash --data data/darcy_cpu_v1 --output outputs/darcy_agent_config_new

# 默认仅检查配置，不调用服务；--live 才发出一次实际请求。
& '.\.venv\Scripts\python.exe' -m scripts.check_agent_api_config --model deepseek-flash --output outputs/agent_config_new.json
& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -v
```

在 `LangGraph_Demo` 目录：

```powershell
& '.\.venv\Scripts\python.exe' .\02_tool_loop.py --backend deepseek --model deepseek-flash
& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -v
```
