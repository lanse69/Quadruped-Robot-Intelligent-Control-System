# ADR-0025 本机仿真展示进程命令通道

## 状态

Accepted

## 背景

本机答辩演示链路已经支持 Web Console 选择 MuJoCo / Webots、编辑并保存场景、打开仿真预览、提交中文任务和执行 API handoff。此前为避免预览窗口被关闭重开，展示进程复用签名已经排除了 `task_path`；但复用后的已打开 MuJoCo / Webots 窗口曾经不能接收新的任务图，实际任务只在 API 的 headless summary 路径中执行。后续还需要保证急停、暂停、人工接管和 Safe-Stand 这类高优先级 override 不只更新 API 状态，也要同步影响已经打开的可视化窗口。

这与演示目标不一致：用户点击“运行任务”时，如果仿真窗口已经打开，应在同一窗口开始展示任务路径；如果窗口未打开，应自动打开并执行任务。

## 决策

新增本机展示进程 JSON 文件命令通道：

```text
Web Console / API handoff 或 control override
  -> LocalSimulationRunner
  -> presentation workspace/commands/*.json
  -> MuJoCo demo process 或 Webots Supervisor controller
  -> 已打开窗口执行任务路径、stop 或 safe_stand
```

核心约束：

1. 命令通道只承载安全层之后的高层演示命令：`run_path`、`stop`、`safe_stand`。
2. 命令内容为任务路径点、步数、控制周期和速度建议，不暴露 MuJoCo / Webots 私有对象，不传递底层关节命令。
3. API 仍保留 bounded headless summary，用于回放、审计、状态和测试证据。
4. 展示进程是可替换边界；MuJoCo 脚本和 Webots controller 各自实现同一命令文件消费语义。

## 实现落点

- `python/qrics/sim/presentation_channel.py`：定义 `PresentationCommand`、`PresentationTarget`、命令写入与读取函数。
- `python/qrics/api/simulation_runner.py`：为每个展示进程创建 `commands/` 工作目录；同场景复用窗口时写入 `run_path` 命令；首次运行任务时先启动窗口再写入命令；`send_control_command()` 将 EmergencyStop / Pause / ManualControl 映射为 `stop`，将 Safe-Stand 映射为 `safe_stand`。
- `scripts/run_local_sim_demo.py`：新增 `--command-dir`，MuJoCo viewer 在保持期间轮询命令目录并执行任务路径。
- `scripts/run_webots_demo.py` 与 `python/qrics/sim/backends/webots_env.py`：新增 `command_dir` 参数，Webots spec 写入命令目录。
- `python/qrics/sim/assets/webots/controllers/qrics_controller/qrics_controller.py`：Webots Supervisor 在 hold 阶段轮询命令目录，直接驱动可视化机器人沿任务路径移动。
- `ControlStatusResponse`：任务 handoff 和 override 都返回 `presentation_command_dir` 与 `presentation_command_path`，便于现场排查任务路径、stop 和 safe_stand 是否已经送达展示进程。

## 后果

正向影响：

- 预览窗口不必关闭重开即可接收“运行任务”。
- Web Console 的“预览 -> 运行 -> 急停 / 安全站立”流程更接近最终演示目标。
- 命令协议保持文件级、可审计、易调试，不增加重型消息总线依赖。

限制：

- 当前命令通道用于本机展示与答辩演示，不等同于生产级仿真控制总线。
- MuJoCo 路径仍是演示级 task-directed motion，不是训练完成的真实四足步态策略。
- Webots 仍以 Supervisor 可视化运动为主，不替代后续完整 Webots Robot/PROTO 关节控制器。