# C++ 地形感知步态控制运行说明

## 目标

本运行手册说明 C++ 核心中的地形感知步态控制链路。该链路用于在 MuJoCo/Webots 本机演示条件下，为任务执行输出可测试、可回放、可审计的机器人行走证据。

## 控制链路

```text
TaskGraph node
  -> RuleBasedPolicyRuntime
  -> StabilityRecoveryController
  -> PurePursuitPathTracker
  -> SimpleObstacleAvoidance
  -> TerrainAwareGaitGenerator
  -> ActionProposal + LocomotionHint
  -> BasicSafetyShield
  -> SafeAction + LocomotionHint
  -> KinematicLocalSimulationAdapter
  -> RobotState / ObservationPacket / replay telemetry
```

`TerrainAwareGaitGenerator` 不直接下发底层动作。它只生成高层步态提示和 12 关节名义位置提示；真正进入仿真的仍是 Safety Shield 处理后的 `SafeAction`。

## 步态选择规则

| 场景 | 步态 | 处理策略 |
|---|---|---|
| 近零速度 | `stand` | 全足支撑，步频 0 |
| 低摩擦、台阶或低速 | `crawl` | 高 duty factor，降低滑移风险 |
| 坡面、碎石、未知地形 | `cautious_trot` | 降低步频与机身高度 |
| 平地正常前进 | `trot` | 对角步态相位，保持较高步频 |

## 构建与测试

```bash
cmake --preset dev-gcc-debug
cmake --build --preset dev-gcc-debug -j2
ctest --preset dev-gcc-debug --output-on-failure
python3 -m pytest -q
```

重点测试目标：

```bash
ctest --preset dev-gcc-debug -R "gait|policy_runtime|local_simulation_adapter|cpp_core_runtime" --output-on-failure
```

## 运行 C++ 核心任务

```bash
./build/dev-gcc-debug/qrics_core_runtime \
  --run-id gait_demo \
  --backend mujoco \
  --profile headless_fast \
  --terrain mixed_terrain_pack \
  --scene-id gait_scene \
  --scene-version 0.1.0 \
  --task-path "A:0.35:0.00:0.35,B:0.70:0.00:0.35" \
  --steps 100 \
  --evidence-dir runtime/qrics-core-evidence
```

输出 JSON 中应包含：

```json
{
  "gait_name": "trot",
  "gait_phase": 0.72,
  "gait_step_frequency_hz": 1.6,
  "swing_foot_count": 2,
  "stance_foot_count": 2
}
```

不同地形或速度下字段值会变化。低摩擦或台阶地形应偏向 `crawl`，坡面或碎石应偏向 `cautious_trot`。

## Web Console 验证

启动本机服务后，Web Console 的任务运行证据中会显示：

- C++ 步态
- C++ 步频
- C++ 足端相位：摆动 / 支撑数量
- C++ replay、telemetry、audit 与 evidence bundle 路径

Web Console 只负责展示和触发，不绕过 C++ 核心控制证据链。

## 后续演进

后续可以把 `TerrainAwareGaitGenerator` 替换或扩展为 RL/ONNX 策略加载器，但必须保持以下边界不变：

```text
ActionProposal -> SafetyShield -> SafeAction -> SimulationAdapter
```

任何策略、AI 解析或人工指令都不得绕过 Safety Shield。