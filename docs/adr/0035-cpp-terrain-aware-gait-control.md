# ADR-0035 C++ 地形感知步态控制进入核心控制链路

## 状态

Accepted

## 背景

前一阶段已经完成 C++ 核心任务运行时、路径跟踪、恢复控制、障碍规避、安全门控、MuJoCo/Webots 本机演示桥接和回放证据落盘。但历史步骤文件仍明确指出：MuJoCo 展示侧存在 task-directed motion + 名义腿部相位，尚未形成可追踪的核心步态控制证据。

当前阶段需要在不依赖 Isaac 和不引入在线训练依赖的前提下，把“机器人行走”能力继续下沉到 C++ 核心链路。该能力必须服从既有安全边界：策略运行时和局部规划器只能生成 ActionProposal；最终下发给仿真适配器的动作必须经过 Safety Shield 转换为 SafeAction。

## 决策

新增 `TerrainAwareGaitGenerator`，在 C++ `SimpleLocalPlanner` 内把路径跟踪和障碍规避后的机体速度建议转换为 `LocomotionHint`：

- 平地和正常速度：选择 `trot`。
- 台阶、低摩擦或低速：选择 `crawl`，提高 duty factor。
- 坡面、碎石或未知地形：选择 `cautious_trot`，降低机身高度并降低步频。
- 近零速度：选择 `stand`，全部足端保持支撑相。

`LocomotionHint` 包含步态类型、步态名称、归一化相位、步频、步长、摆动高度、duty factor、机身高度和四足足端目标。局部规划器同时生成 12 个关节名义位置提示，但这些关节提示仍只是高层建议，不会绕过安全门控直接下发。

`BasicSafetyShield` 复制经过校验的 `LocomotionHint` 到 `SafeAction`。`KinematicLocalSimulationAdapter` 使用 `SafeAction.locomotion_hint` 生成足端接触状态和机身高度观测。`LocalTaskRunSummary`、telemetry JSONL、summary JSON 和 Web Console 证据展示新增步态字段。

## 后果

正向影响：

- C++ 核心运行时能输出可检索的步态、步频、相位和摆动/支撑足证据。
- MuJoCo/Webots 本机演示链路之外，核心控制链路已经具备地形感知 gait runtime 的可测试实现。
- 后续可把训练得到的 RL/gait policy 替换为策略插件，但不改变 `ActionProposal -> SafetyShield -> SafeAction -> SimulationAdapter` 合约。

约束与风险：

- 本阶段实现的是可演示、可测试、可审计的参数化步态生成器，不声称已经完成高性能 RL 步态策略。
- 外部 MuJoCo/Webots viewer 仍可继续使用现有展示控制通道；C++ 核心证据通过 `core_runtime_summary` 展示。
- 后续接入真实动力学关节控制时，应保持 Safety Shield 为唯一动作下发门控。

## 验证

- `qrics_gait_generator_test` 覆盖平地 trot、低摩擦 crawl、stand 和非法 task node 输入。
- `qrics_policy_runtime_test` 验证策略运行时输出包含 `LocomotionHint` 与 12 关节提示。
- `qrics_local_simulation_adapter_test` 验证仿真适配器根据步态提示生成摆动足接触状态。
- `qrics_cpp_core_runtime_test` 验证 C++ 核心运行 summary JSON 包含 gait 字段。