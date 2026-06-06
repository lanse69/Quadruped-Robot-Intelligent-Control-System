# ADR-0028：Web Console 一键任务运行应用层契约

## 状态

Accepted

## 背景

本机演示链路已经具备场景编辑与保存、MuJoCo/Webots 预览、中文任务解析、任务 handoff、展示进程命令通道、急停与 Safe-Stand override。此前 Web Console 的“运行任务”按钮在前端依次调用：

```text
POST /api/v1/tasks
POST /api/v1/tasks/{task_id}/confirm
POST /api/v1/tasks/{task_id}/handoff
```

该方式虽然可运行，但把任务生命周期编排分散到了 JavaScript 中。若自然语言输入被安全边界拒绝，前端仍可能继续请求 confirm；同时，答辩演示期望“输入任务并点击运行”是一个明确的应用级动作，后端应负责保存 TaskScript/TaskGraph 证据、确认语义、打开或复用仿真窗口、写入展示命令和生成回放事件。

## 决策

新增 `TaskRunPayload` 与 `QricsApiApp.run_task()`，并暴露 HTTP 接口：

```text
POST /api/v1/tasks/run
```

应用层按固定顺序执行：

```text
source_text + scene_ref + run_options
  -> submit_task：生成 TaskScript / TaskGraph 预览，执行 NLP 安全边界检查
  -> confirm_task：将“点击运行”作为操作者确认
  -> handoff_task：按 run_options 进入本机 minimal / MuJoCo / Webots 仿真运行
  -> replay/event：写入控制状态、回放索引和 task.lifecycle 事件
```

若解析结果为 `state=rejected`，接口返回：

```json
{
  "run_started": false,
  "task": {"state": "rejected"},
  "status": {},
  "run_id": "",
  "rejection_reason": "..."
}
```

拒绝路径不执行 confirm，不执行 handoff，不打开仿真窗口。

## 影响

- Web Console “运行任务”改为调用 `/api/v1/tasks/run`，不再在前端复制生命周期状态机。
- 原有 submit / confirm / handoff 接口保持兼容，用于测试、脚本和分步调试。
- 一键响应同时返回 `task`、`confirmation`、`status`、`task_script`、`task_graph`、`parser_version`、`parse_confidence` 和 `presentation_command_path`，便于 UI 展示演示证据。
- MuJoCo/Webots viewer 模式仍通过既有 presentation command channel 打开或复用窗口；API 不暴露底层关节动作。

## 安全边界

`run_task()` 不引入任何绕过 Safety Shield 的路径。自然语言解析器仍只输出 TaskScript 草案，且会拒绝 `SafeAction`、`JointPosition`、`JointVelocity`、`SimulationAdapter` 和“绕过安全”等低层动作语义。`handoff_task()` 仍调用本机仿真 runner，runner 内部只接收任务路径与安全动作摘要。

## 验证

新增测试覆盖：

```text
tests/python/test_api_facade.py::test_one_click_task_run_parses_confirms_handoffs_and_records_events
tests/python/test_api_facade.py::test_one_click_task_run_returns_rejection_without_handoff
tests/python/test_http_api.py::test_http_one_click_task_run_endpoint
tests/python/test_http_api.py::test_http_one_click_task_run_rejects_low_level_action
```