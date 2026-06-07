# ADR 0039: 任务路径闭环到达进度与自动步数预算

## 状态

Accepted

## 背景

前一阶段已经将步态遥测暴露到 API、Web Console 与 MuJoCo 后端，但 `POST /api/v1/tasks/run` 的本机演示仍主要依赖固定 `step_count`。当用户输入“先巡检 A，再巡检 B，最后回到平台待命”这类完整任务时，如果控制步数过小，演示会在到达中途目标前结束，导致状态证据只能证明机器人开始移动，不能证明任务路径闭环完成。

答辩演示需要在不绕过 `TaskScript -> TaskGraph -> Control Service -> Safety Shield -> Simulation Adapter` 的前提下，展示机器人按任务路径依次到达检查点、完成驻留，并向操作者返回明确的路线进度证据。

## 决策

在 Python API 本机仿真 runner 中增加任务路径控制器与自动步数预算：

1. `LocalSimulationRunner` 对 `SimulationTaskTarget` 序列执行闭环跟踪，按当前标准化观测中的 base 位置计算目标距离。
2. 当机器人进入到达阈值后，记录 `reached_target_ids`，按目标 `dwell_steps` 执行保持动作，随后切换到下一个目标。
3. `SimulationRunOptionsPayload.auto_extend_task_steps` 作为显式演示选项。开启后，根据路径长度、运行档位控制周期、目标驻留步数和稳定冗余估算 `effective_step_count`，上限固定为 1200，避免无限运行。
4. `ControlStatusResponse`、事件 payload、SQLite repository 和 Web Console 统一暴露路线进度字段：当前目标、已到达目标、总目标数、进度比例、是否完成、目标剩余距离、用户请求步数、实际执行步数和估算步数。
5. 路径控制器只生成 `SafeAction` 层的高层 `body_velocity` 建议，并继续由既有仿真适配器消费；不新增低层关节直通路径。

## 影响

- Web Console 默认对一键任务运行开启 `auto_extend_task_steps`，使短步数配置也能完成典型 A/B/平台路线。
- API 调用方仍可关闭自动扩展，用于验证短时控制和部分路径进度。
- 状态响应和事件流可直接作为答辩证据，证明任务路径不是只启动仿真，而是已经按目标序列推进或完成。
- 自动步数上限避免演示卡死，但超长路径仍可能只返回部分进度；这种情况下 `route_completed=false` 与 `route_progress_ratio<1.0` 会如实暴露。

## 验证

- `tests/python/test_api_simulation_runner.py` 验证自动扩展能完成路径，关闭自动扩展时返回部分进度。
- `tests/python/test_api_facade.py` 验证一键任务运行可返回并持久化路线进度。
- `tests/python/test_http_api.py` 验证 HTTP `run_options.auto_extend_task_steps` 可驱动完整路径 handoff。
- Web Console 二维场景中会高亮当前目标，并标记已到达检查点。