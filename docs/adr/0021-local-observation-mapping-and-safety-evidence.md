# ADR-0021 本机 MuJoCo/Webots 观测映射与安全证据闭环

## 状态

Accepted

## 背景

需求基线要求任务执行、控制安全、训练评估、回放审计形成闭环；所有动作建议必须经过 Safety Shield 后才能进入仿真步进。设计基线要求通过 Simulation Adapter 隔离底层仿真平台，并在新增 MuJoCo/Webots 等本机适配器时保持接口语义稳定、重新建立回归基线。

当前阶段已具备本机 MuJoCo/Webots/Minimal 后端和 C++ 控制增强，但后端观测包中的 `obstacle_state`、混合地形 `terrain_class` 与 API 回放证据仍不完整。答辩演示需要在不依赖 Isaac 的本机环境中展示“场景资产 -> 标准化观测 -> C++ 安全门控 -> API 状态 -> 回放关键帧”的可验证链路。

## 决策

1. 在 Python 与 C++ 两侧扩展统一场景结构，新增障碍物几何描述，并保留既有 `obstacle_set` 兼容字段。
2. 在本机后端中实现确定性的观测映射：
   - `mixed_terrain_pack` 根据机器人 x 坐标映射为 `flat/gravel/slope/low_friction`；
   - 场景障碍物根据当前位置计算最近表面距离并写入 `ObservationPacket.obstacle_state`。
3. C++ `KinematicLocalSimulationAdapter` 对 Minimal、MuJoCo、Webots 采用同一 Simulation Adapter 语义；Minimal 标记为估计观测，MuJoCo/Webots 标记为直接观测语义。
4. `SimulationRunner` 在 handoff 演示路径中读取观测并产生 `CollisionRisk` 安全事件；风险触发时下发 `SafeAction(action_type="replan")`，并把安全事件和关键帧写入控制状态与回放响应。
5. API 场景资产仍保持轻量 payload，不强行引入复杂几何 schema；当前将 `asset_type="obstacle"` 的资产映射为确定性的演示障碍物，后续可用兼容字段扩展真实几何参数。

## 影响

- C++ 核心链路现在可以从仿真观测中得到障碍距离，并通过 `BasicSafetyShield` 触发 `CollisionRisk/Replan`。
- MuJoCo/Webots 本机演示路径不再只返回姿态和接触信息，控制状态、事件、回放均能展示地形和障碍安全证据。
- API `ControlStatusResponse` 与 `ReplayResponse` 新增安全证据字段，但保持旧字段不变。
- 场景配置 loader 支持 `obstacles[]` 与矩形 forbidden zone，减少禁行区只有单点导致 Safety Shield 不可验证的问题。

## 验证

- `ctest --preset dev-gcc-debug --output-on-failure`
- `PYTHONPATH=python python3 -m pytest -q`
- `PYTHONPATH=python python3 -m compileall -q python tests/python`

## 后续

- 将 API `SceneAssetPayload` 扩展为 typed geometry payload，避免长期依赖演示障碍物映射。
- 在真实 Webots world 和 MuJoCo XML 中加入同名障碍物资产，并在运行时读取模拟器对象坐标替代配置推导。
- 将 C++ TaskExecutor 安全事件写入统一 ReplayManifest，而不仅是测试和 API facade 侧证据。