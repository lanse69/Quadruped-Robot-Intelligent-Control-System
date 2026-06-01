# ADR-0008: Python Isaac Lab Adapter 契约准备

## 状态

Accepted

## 背景

当前仓库已经完成平台无关的任务理解、配置加载、任务执行器、安全门控、监控、回放和审计基础模型。C++ 层已经通过 `SimulationAdapter` 固定了仿真生命周期和动作下发边界。

完整路线的下一阶段是 Isaac Lab 最小适配，但本机和 CI 不应强制安装 Isaac Sim / Isaac Lab。若直接依赖真实 Isaac Lab，会导致基础测试、类型检查和持续集成受 GPU、驱动、Python 版本和仿真依赖影响。

## 决策

先新增 Python 侧 Isaac Lab Adapter 契约和轻量占位后端：

- `schema.py` 定义 Python 侧的 `AdapterConfig`、`SceneProfile`、`SafeAction`、`ObservationPacket`、`RobotState`、`AdapterStepResult` 和 `AdapterResult`。
- `action_mapper.py` 负责把 `SafeAction` 转成 Isaac-style command payload。
- `observation_mapper.py` 负责把 Isaac-style raw observation/state 转成 QRICS schema。
- `minimal_env.py` 提供确定性轻量后端，用于不依赖 Isaac Lab 的生命周期测试。
- `adapter.py` 暴露与 C++ `SimulationAdapter` 语义一致的 Python `IsaacLabAdapter` 门面。
- `test_isaac_lab_adapter_contract.py` 验证初始化、场景加载、重置、步进、关闭和拒绝动作阻断。

## 安全边界

`IsaacLabAdapter` 只接收 `SafeAction`，不接收 `ActionProposal`。  
`Rejected SafeAction` 不允许映射为仿真动作。  
`JointPosition` 和 `JointVelocity` 暂不映射到 Python Isaac command，避免占位阶段误导为真实底层控制能力。  
真实 Isaac Lab 后端接入后仍不得绕过 `SafetyShield`。

## 不做内容

本阶段不安装 Isaac Lab，不接真实 GPU 仿真，不实现真实物理环境，不启动训练，不接数据库/API/WebSocket，不改变 C++ `SimulationAdapter` 契约。

## 后果

后续接入真实 Isaac Lab 时，只需要替换或扩展后端实现，并复用当前 action mapper、observation mapper 和 adapter lifecycle contract。CI 可以继续在无 Isaac Lab 环境中验证 Python 契约。