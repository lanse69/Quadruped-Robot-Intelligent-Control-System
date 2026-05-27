# ADR-0006: 任务执行器与占位策略运行时

## 状态

Accepted

## 背景

当前代码已经具备任务理解、任务图生成、任务生命周期、配置加载、安全门控和最小控制闭环。系统仍缺少把 `TaskGraph` 转换为控制周期动作建议的执行层，因此 `TaskOrchestratorService::handoff()` 之后没有平台无关的执行闭环。

设计文档要求控制服务负责观测读取、策略推理、恢复控制、局部重规划和动作下发；策略、控制器和人工指令均必须先形成 `ActionProposal`，再经 `SafetyShield` 转换为 `SafeAction`，最后才能交给 `SimulationAdapter::step()`。

## 决策

新增平台无关的占位执行层：

- `control_state.hpp`：定义任务执行快照、节点执行状态和目标点上下文。
- `local_planner.hpp/.cpp`：提供最小局部规划器，把 MoveTo / ReturnHome / Dwell / Stop 转换为局部目标动作。
- `policy_runtime.hpp/.cpp`：提供策略运行时接口和规则占位实现。
- `task_executor.hpp/.cpp`：管理 `TaskGraph` 节点推进，并通过既有 `ControlLoop` 调用 `SafetyShield` 与 `SimulationAdapter`。

任务执行链路固定为：

```text
TaskGraph
  -> TaskExecutor
  -> PolicyRuntime
  -> LocalPlanner
  -> ActionProposal
  -> ControlLoop
  -> SafetyShield
  -> SafeAction
  -> SimulationAdapter::step()
  -> AdapterStepResult / RobotState
  -> TaskExecutionSnapshot
```

## 不做内容

本阶段不实现真实强化学习策略推理，不实现复杂路径规划，不接 Isaac Lab，不接数据库/API/WebSocket，不实现回放审计持久化，不改变 `SimulationAdapter` 既有契约。

## 后果

后续 Control Service 可以在应用层包装 `TaskExecutor`。Isaac Lab 适配接入时，只需要实现真实 `SimulationAdapter`，无需改变上层任务执行语义。后续监控、回放和审计阶段可以直接消费 `TaskExecutionSnapshot`、`SafetyEvent` 与适配器返回的状态。