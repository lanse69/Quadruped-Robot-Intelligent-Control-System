# ADR-0011：本机 MuJoCo 真实物理后端与多仿真适配路线

## 状态

Accepted

## 背景

需求和设计基线以 Isaac Lab / Isaac Sim 作为高保真仿真平台，但当前本机硬件更适合轻量真实物理仿真和短时可视化演示。此前 `python/qrics/isaac_lab` 包中已经固定了 Python 侧 adapter 生命周期和 schema，但其中 `MinimalQuadrupedEnv` 只适合契约测试，不应继续作为真实物理演示后端。

系统已有 C++ `SimulationAdapter` 抽象、`SafetyShield`、`ControlLoop`、`TaskExecutor`、监控回放和审计模型。新增仿真后端不得改变上层业务语义，也不得让 `ActionProposal` 或被拒绝的 `SafeAction` 绕过安全层。

## 决策

新增通用 Python 仿真包 `qrics.sim`，将跨后端 schema、动作映射、运行档位和后端协议从 `isaac_lab` 命名中抽离。新增 MuJoCo 后端作为本机主力真实物理后端，使用项目内置 MJCF 四足模型执行 `mujoco.mj_step()`，输出 `ObservationPacket` 和 `RobotState`。

运行档位定义为：

- `balanced_visual`：默认本机演示档，保留 viewer、核心状态观测、接触/IMU、少量场景要素。
- `headless_fast`：自动化测试和无显示回归档。
- `rich_demo`：短视频、截图和展示增强档。

Isaac Lab 仍保留为需求/设计基线和远程高配后端；Webots 作为后续可视化辅助后端候选。本阶段不删除 Isaac Lab 兼容层。

## 后果

正面影响：

- 本机可以运行真实物理仿真，不再依赖完整 Isaac Sim 才能展示机器人闭环。
- 上层业务仍通过统一适配接口访问仿真能力。
- 答辩演示可以用 MuJoCo 稳定展示，同时说明 Isaac Lab 基线和远程高保真路线。
- 后续新增 Webots / IsaacLabAdapter 真实后端时可复用 `qrics.sim` schema 和后端协议。

代价和限制：

- MuJoCo 后端内置的速度伺服和程序步态不是最终高性能四足步态控制器。
- MuJoCo 的视觉和资产生态不替代 Isaac Sim 高保真渲染。
- 若将 MuJoCo 结果用于训练评测报告，必须在报告中标明后端、运行档位和场景版本。

## 安全约束

- `ActionProposal` 不进入 Python 仿真后端。
- `Rejected SafeAction` 不允许映射为仿真命令。
- `EmergencyStop` 和 `SafeStand` 在后端中必须转为停止或安全站立命令。
- 后端输出的风险、姿态和接触信息应继续进入监控、回放和审计链路。