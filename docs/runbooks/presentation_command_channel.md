# 本机 MuJoCo / Webots 展示进程命令通道运行手册

## 目标

该通道用于让已经打开的本机 MuJoCo / Webots 展示窗口接收 Web Console 的运行任务。流程是：先预览场景打开仿真窗口，再输入中文任务并点击运行；API 会复用已有窗口，并向展示进程的 `commands/` 目录写入 JSON 命令。

## 启动 Web Console

```bash
source .venv/bin/activate
python scripts/run_web_console.py --host 127.0.0.1 --port 8000
```

浏览器打开：

```text
http://127.0.0.1:8000/console/
```

## 推荐演示流程

1. 选择 `MuJoCo` 或 `Webots`。
2. 选择可视化 profile：MuJoCo 推荐 `balanced_visual`，Webots 推荐 `webots_fast`。
3. 拖动 A/B 点、平台、禁行区或障碍物，然后保存场景。
4. 点击“预览 / 打开仿真”。
5. 输入任务：

```text
从平台出发，避开低摩擦区，先巡检A，再巡检B，最后回到平台待命
```

6. 点击“运行任务”。
7. 状态响应中应包含：

```text
presentation_pid
presentation_workspace
presentation_command_dir
presentation_command_path
```

其中 `presentation_command_path` 指向本次运行写入的命令 JSON。

## 直接验证命令通道

### Webots dry-run

不启动真实 Webots，只验证 QRICS 侧参数和命令目录：

```bash
mkdir -p runtime/presentation-commands
python scripts/run_webots_demo.py \
  --dry-run \
  --profile webots_fast \
  --seconds 3 \
  --command-dir runtime/presentation-commands
```

### MuJoCo viewer

安装 MuJoCo 后运行：

```bash
mkdir -p runtime/presentation-commands
python scripts/run_local_sim_demo.py \
  --profile balanced_visual \
  --viewer \
  --seconds 60 \
  --command-dir runtime/presentation-commands
```

另一个终端可写入命令文件进行调试。正常使用时不需要手工写入，API 会自动写入。

## 命令文件格式

命令文件位于：

```text
<presentation_workspace>/commands/*.json
```

核心字段：

```json
{
  "schema_version": "qrics.presentation.command.v1",
  "command_type": "run_path",
  "run_id": "run_task_1",
  "step_count": 80,
  "control_dt_s": 0.032,
  "forward_velocity_mps": 0.25,
  "yaw_rate_radps": 0.05,
  "task_path": [
    {"id": "A", "position": [0.8, 0.3, 0.32], "dwell_steps": 0},
    {"id": "B", "position": [1.6, -0.3, 0.32], "dwell_steps": 0}
  ]
}
```

## 排错

- `presentation_pid` 为 `0`：所选 profile 不是 viewer 模式，或本机缺少 MuJoCo/Webots 外部环境。
- `presentation_command_path` 为空：当前任务没有生成路径点，或尚未打开/复用展示进程。
- Webots 窗口不动：检查 `QRICS_WEBOTS_HOLD_SECONDS` 不应为 `0`；同时检查 `presentation_command_path` 对应文件是否存在。
- MuJoCo 窗口不动：确认 `run_local_sim_demo.py` 启动命令中包含 `--command-dir`，且窗口进程仍在运行。