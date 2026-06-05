# ADR-0020 控制能力增强：路径跟踪、恢复控制与障碍规避

## 状态

Accepted

## 背景

需求规格说明书将自主导航、地形自适应、恢复控制、障碍规避和动作安全约束列为 V1.0 核心能力。当前代码已经具备任务理解、任务图、规则策略运行时、任务执行器、安全门控和本机 MuJoCo / Webots 后端边界，但控制层仍主要依赖简单直线速度建议，难以支撑答辩演示中“复杂地形通行、遇障处理、跌倒或不稳定恢复”的解释链路。

本机环境不适合把 Isaac Lab 作为前置依赖；因此本阶段继续按 MuJoCo + Webots 本机路线推进，把平台无关的控制能力先落在 C++ 核心库中，再由 Python API / 仿真后端逐步接入。

## 决策

新增三个 C++ 控制构件，并接入既有 `SimpleLocalPlanner`：

1. `PurePursuitPathTracker`：根据 `TaskNode`、目标航点、`RobotState` 和地形类别输出 `BodyVelocity` 动作建议；不同地形使用保守速度上限，低摩擦、楼梯、碎石和坡面自动降速。
2. `StabilityRecoveryController`：在 `Fallen`、`Unstable`、`Recovering` 或高风险分数下优先输出 `SafeStand` / `Stop`，避免路径跟踪继续推动不稳定机器人。
3. `SimpleObstacleAvoidance`：根据 `ObservationPacket.obstacle_state` 对路径跟踪动作进行局部调制；近距离障碍触发 `Replan`，警戒距离内减速并施加横向避让分量。

同时增强 `SafetyShield`：

- `SafetyContext` 增加 `ObservationPacket`、禁行区集合和 `require_observation` 标记。
- `BasicSafetyShield` 增加观测缺失、碰撞距离和禁行区多边形检查。
- 硬约束触发后输出 `Rejected`、`Replan` 或 `SafeStand`，并生成对应 `SafetyEvent`。

`TaskExecutor` 在每个 step 读取 `SimulationAdapter::observe()`，把观测传给策略运行时和安全门控；如果观测失败，则构造缺失质量标记的观测包，后续可按 `require_observation` 决定是否阻断。

## 影响

- C++ 核心库不再只有占位直线规划，而是形成 `恢复控制 -> 路径跟踪 -> 障碍规避 -> 安全门控 -> 仿真步进` 的可测链路。
- Python 层仍作为 API、持久化和本机仿真后端适配辅助层，不承载核心控制决策。
- MuJoCo / Webots 后端可继续通过统一适配接口接收 `SafeAction`，不改变上层任务、训练、回放和审计接口。
- 当前仍不是生产级步态控制器；真实步态、可加载策略模型和复杂动态避障保留为后续增量。

## 验证

新增测试：

- `qrics_path_tracker_test`
- `qrics_recovery_controller_test`
- `qrics_obstacle_avoidance_test`

扩展测试：

- `qrics_safety_shield_test` 覆盖碰撞风险、禁行区和观测缺失。
- 既有 `qrics_policy_runtime_test`、`qrics_task_executor_test` 验证控制链路兼容性。