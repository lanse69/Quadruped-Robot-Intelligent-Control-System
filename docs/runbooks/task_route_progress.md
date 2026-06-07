# 任务路径到达进度与自动步数预算运行手册

本文档说明如何验证 QRICS 在本机 MuJoCo / Webots / minimal 后端中按任务路径推进，并通过 API、事件和 Web Console 展示到达进度。

## 1. 适用场景

典型演示任务：

```text
避开低摩擦区，先巡检 A，再巡检 B，最后回到平台待命
```

该任务会被解析为顺序路径目标。API handoff 会将路径目标传给本机仿真 runner，runner 按当前机器人 base 位置追踪目标，并在到达阈值内记录目标已到达。

## 2. API 运行示例

启动服务：

```bash
PYTHONPATH=python python scripts/run_api_service.py --state-dir runtime/qrics-api
```

提交任务并开启自动步数预算：

```bash
curl -sS -X POST http://127.0.0.1:8000/api/v1/tasks/run \
  -H 'content-type: application/json' \
  -H 'x-request-id: demo-route-progress' \
  -d '{
    "source_text": "避开低摩擦区，先巡检A，再巡检B，最后回到平台待命",
    "run_options": {
      "backend": "minimal",
      "runtime_profile": "headless_fast",
      "step_count": 5,
      "auto_extend_task_steps": true
    }
  }' | python -m json.tool
```

重点检查响应中的字段：

| 字段 | 说明 |
|---|---|
| `requested_step_count` | 用户请求步数，例如 5。 |
| `effective_step_count` | 实际执行步数；启用自动扩展后可能大于请求值。 |
| `estimated_required_step_count` | 按路径长度、控制周期、驻留步数和冗余估算出的步数。 |
| `active_target_id` | 当前目标。路径完成后为末端目标。 |
| `reached_target_ids` | 已到达目标 ID 列表。 |
| `target_count` / `reached_target_count` | 总目标数与已到达数量。 |
| `route_progress_ratio` | 到达进度，范围 0.0 到 1.0。 |
| `route_completed` | 是否已完成全部路径目标。 |
| `target_distance_m` | 当前目标剩余距离，单位 m。 |

## 3. Web Console 验证

运行：

```bash
PYTHONPATH=python python scripts/run_web_console.py --state-dir runtime/qrics-api
```

在控制台选择仿真后端和地形后输入演示任务。点击运行后，状态区域会显示：

- `任务到达进度`：已到达目标数 / 总目标数。
- `当前目标 / 距离`：当前目标 ID 与剩余距离。
- `任务步数预算`：请求步数到实际执行步数。
- `路径完成`：是否完成完整任务路径。

二维场景画布会高亮当前目标，已经到达的检查点会标记“已到达”。

## 4. 手工回归命令

```bash
PYTHONPATH=python pytest -q \
  tests/python/test_api_simulation_runner.py \
  tests/python/test_api_facade.py \
  tests/python/test_http_api.py \
  tests/python/test_repository_persistence.py \
  tests/python/test_web_console_api.py
```

前端语法检查：

```bash
node --check python/qrics/webui/static/app.js
```

## 5. 边界说明

- `auto_extend_task_steps=false` 时，系统严格按请求步数运行，可能只返回部分进度。
- 自动扩展最多执行 1200 步，避免异常任务导致演示阻塞。
- 路线控制只产生安全动作层高层速度命令，不绕过 Safety Shield 或 Simulation Adapter 边界。