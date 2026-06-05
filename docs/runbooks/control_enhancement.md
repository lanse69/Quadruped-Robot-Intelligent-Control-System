# 控制能力增强运行手册

## 目标

本手册说明本机 MuJoCo + Webots 路线下新增的 C++ 控制能力如何进入任务执行链路，以及如何验证路径跟踪、恢复控制、障碍规避和安全硬约束。

## 控制链路

```text
TaskGraph / TaskNode
  -> TaskExecutor
  -> RuleBasedPolicyRuntime
  -> SimpleLocalPlanner
  -> StabilityRecoveryController
  -> PurePursuitPathTracker
  -> SimpleObstacleAvoidance
  -> ActionProposal
  -> BasicSafetyShield
  -> SafeAction
  -> SimulationAdapter::step()
```

## 控制构件职责

| 构件 | 职责 |
|---|---|
| `PurePursuitPathTracker` | 按目标航点生成地形感知速度命令；低摩擦、楼梯、碎石、坡面自动降速。 |
| `StabilityRecoveryController` | 在跌倒、不稳定、恢复中或风险分数升高时输出 `SafeStand` / `Stop`。 |
| `SimpleObstacleAvoidance` | 根据最近障碍距离调制速度；硬距离内输出 `Replan`。 |
| `BasicSafetyShield` | 对动作输出进行最终硬约束检查，覆盖急停、人工接管、姿态/风险、速度裁剪、障碍风险、禁行区和观测缺失。 |

## 本机验证命令

```bash
cmake --preset dev-gcc-debug
cmake --build --preset dev-gcc-debug
ctest --preset dev-gcc-debug --output-on-failure
python -m pytest -q
```

重点测试目标：

```text
qrics_path_tracker_test
qrics_recovery_controller_test
qrics_obstacle_avoidance_test
qrics_safety_shield_test
qrics_policy_runtime_test
qrics_task_executor_test
```

## MuJoCo / Webots 演示关系

- MuJoCo 与 Webots 仍通过 `SimulationAdapter` / `qrics.sim` 后端进入系统。
- C++ 控制层只产生 `ActionProposal`，不直接调用 MuJoCo / Webots 私有 API。
- 后端只接收经过 `SafetyShield` 处理的 `SafeAction`。
- 当前 Webots 仍定位为本机可视化演示后端；MuJoCo 作为本机主力物理后端和 smoke test 后端。

## 后续扩展

1. 将 Python `SimulationRunner` 的任务执行从固定命令进一步切换为 C++ 控制链路绑定。
2. 引入真实步态控制器、恢复控制状态机和可加载策略模型。
3. 将 MuJoCo / Webots 的障碍观测、地形观测和禁行区加载映射到 `ObservationPacket` 与 `SafetyContext`。