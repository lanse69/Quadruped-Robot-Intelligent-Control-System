# ADR-0038 API 步态遥测与 MuJoCo Hint 驱动

## 状态

Accepted

## 背景

前一阶段已经将 C++ 核心步态提示、Python 本机步态合成、MuJoCo / Webots 展示桥接和 Webots 视觉步态控制器串联起来。但 API 一键运行链路仍存在两个问题：

1. `LocalSimulationRunner` 在生成 `SafeAction` 时使用循环序号作为纳秒时间戳，导致本机 API / Web Console 路径中的 `LocomotionHint.normalized_phase` 几乎不变化，MuJoCo 关节提示无法随仿真时间连续摆动。
2. API `ControlStatusResponse` 只返回地形、位置、风险和障碍信息，未显式返回本机步态、步频、足端相位和关节目标数量。答辩演示时只能通过 C++ runtime summary 或控制台原始 JSON 间接判断步态链路是否生效。

## 决策

本阶段在应用层和本机仿真层引入 API 级步态遥测：

- `SimulationRunSummary` 与 `ControlStatusResponse` 增加 `gait_name`、`gait_phase`、`gait_step_frequency_hz`、`swing_foot_count`、`stance_foot_count`、`joint_command_count`。
- `LocalSimulationRunner` 生成 `SafeAction` 时优先使用当前 `ObservationPacket.timestamp_ns`，无观测时才回退到固定 20 ms 步长，确保 gait phase 随仿真时间推进。
- MuJoCo 后端在收到带 `LocomotionHint` 但缺少显式 `JointCommand` 的安全动作时，会由本机步态合成器派生 12 关节位置目标，保持 `SafeAction -> backend command` 边界不变。
- Web Console 运行状态卡片和证据输出展示本机步态、步频、摆动/支撑足数量和关节目标数量；二维场景预览中的机器人图标绘制四条腿，按步态相位显示摆动脚。

## 约束

- 本阶段不新增绕过安全门控的底层控制入口；所有仿真后端仍只消费 `SafeAction`。
- API 暴露的是 QRICS 标准步态遥测字段，不暴露 MuJoCo/Webots 内部对象、句柄或平台私有状态。
- MuJoCo hint 驱动仍属于本机演示级步态播放，不声明为生产级 RL 策略或实体机器人控制器。

## 影响

- Web Console 一键任务运行可以直接证明本机 MuJoCo / Webots 展示链路正在执行 crawl / cautious_trot / trot / stand 等步态。
- SQLite 持久化控制状态时保留新增步态字段，回放和审计查询不会丢失本机步态证据。
- 后续若接入真实策略模型，可继续复用这些 API 字段作为控制状态与评测证据摘要。