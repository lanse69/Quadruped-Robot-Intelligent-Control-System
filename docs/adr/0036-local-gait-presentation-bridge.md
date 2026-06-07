# ADR-0036 本机步态行走展示桥接

## 状态

Accepted

## 背景

当前 C++ 核心链路已经能够在 `ActionProposal -> SafetyShield -> SafeAction -> SimulationAdapter` 中携带地形感知步态、足端相位和 12 关节名义位置提示。但本机 MuJoCo / Webots 演示链路仍主要按底盘速度推进，可视化层难以直接展示“机器人正在按地形切换步态行走”的效果。

毕业答辩演示需要在本机硬件上优先跑通 MuJoCo + Webots。由于用户当前硬件无法承担 Isaac 环境，下一阶段应把既有 C++ 步态证据投射到本机可视化后端，而不是继续只扩展管理页面。

## 决策

1. 在 Python 本机仿真 schema 中补齐 `JointCommand`、`FootstepTarget` 与 `LocomotionHint`，与 C++ 控制模型保持同名同义字段。
2. 新增 `qrics.sim.gait`，按地形、速度、yaw rate 和时间戳合成展示用步态提示：
   - 平地中速：`trot`。
   - 楼梯、低摩擦、极低速：`crawl`。
   - 坡面、碎石、未知地形：`cautious_trot`。
   - 近零速度：`stand`。
3. `SimulationRunner` 与本机演示脚本在生成 `SafeAction` 后补充步态提示，仍保持“安全动作先生成、仿真适配器只接收 SafeAction”的边界。
4. MuJoCo 后端优先把 12 关节名义位置提示映射到已有位置 actuator，使可视化腿部运动跟随步态；无关节提示时保留旧的演示相位兜底。
5. Minimal / Webots dry-run 后端根据足端相位生成接触状态，使测试、回放和演示日志能看到支撑足/摆动足证据。
6. C++ `KinematicLocalSimulationAdapter` 读取 `LocomotionHint` 后按地形与步态调整位移比例、body height 和接触力，避免核心证据仍表现为无差别平面平移。

## 影响

- 本机 MuJoCo / Webots 演示可以展示步态类型、足端相位、名义关节目标和地形降速。
- Python 本机展示链路与 C++ 核心控制链路共享同一类字段，后续接入真实策略模型时可以替换 gait synthesis，而不需要改 API / Simulation Adapter 语义。
- 这不是生产级全身动力学控制器；当前目标是本机答辩可运行、可解释、可验收的步态展示桥接。

## 验证

- `tests/python/test_local_gait_presentation.py` 覆盖步态合成、低摩擦 crawl、Minimal 接触相位和 Webots dry-run 接触相位。
- C++ 本机适配器测试继续验证携带 `LocomotionHint` 的 `SafeAction` 可推进状态并生成 swing foot 接触证据。