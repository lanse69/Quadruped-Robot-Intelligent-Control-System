# QRICS 本机 Web Console 运行手册

## 目标

本手册用于在一台无法运行 Isaac 的普通开发机上，按 MuJoCo + Webots 本机部署路径演示 QRICS 的任务执行闭环。演示入口提供浏览器 UI，用户可选择仿真软件、地形、障碍物和运行档位，保存场景、预览仿真、输入中文任务并运行，同时验证急停、Safe-Stand、回放和审计证据。

## 安装依赖

基础开发安装：

```bash
python -m pip install -e ".[api,dev]"
```

如需 MuJoCo 物理后端：

```bash
python -m pip install -e ".[api,local-sim,dev]"
```

如需 Webots 可视化后端，需要本机已安装 Webots，并保证命令行可以找到 `webots`：

```bash
webots --version
```

如果 Webots 不在 `PATH` 中，可在 shell 中设置路径，例如：

```bash
export WEBOTS_HOME=/path/to/Webots
export PATH="$WEBOTS_HOME:$PATH"
```

## 启动 Web Console

```bash
python scripts/run_web_console.py --host 127.0.0.1 --port 8000
```

默认会打开浏览器。也可关闭自动打开：

```bash
python scripts/run_web_console.py --host 127.0.0.1 --port 8000 --no-browser
```

浏览器访问：

```text
http://127.0.0.1:8000/console/
```

运行数据默认写入：

```text
runtime/qrics-console/
```

该目录包含 SQLite 元数据、本地对象存储工件、回放与审计证据。需要重新开始演示时可删除该目录。

## 演示步骤

1. 在“仿真与场景”区域选择后端：`MuJoCo`、`Webots` 或 `Minimal`。
2. 选择运行档位：
   - `balanced_visual`：适合 MuJoCo 本机可视化或较完整演示。
   - `webots_fast`：适合 Webots 快速预览。
   - `headless_fast`：适合无图形环境或自动测试。
   - `rich_demo`：预留给更丰富视觉和场景资产的演示档位。
3. 输入场景 ID、版本和 terrain pack。
4. 添加障碍物，可选 `box`、`sphere`、`cylinder`，设置位置、尺寸、半径和高度。
5. 点击“保存场景”，后端会通过 Scene API 写入版本化场景。
6. 点击“预览/打开仿真”，后端调用 `/api/v1/sim/preview` 执行短仿真。若选择 Webots 且本机环境可用，后端会尝试启动 Webots。
7. 在“任务执行”区域输入中文任务，例如：

```text
避开障碍，先巡检A，再回到平台待命
```

8. 点击“运行任务”。控制台会依次执行保存场景、提交任务、确认任务、handoff，并将选择的后端/profile 写入 `run_options`。
9. 点击“急停”或“Safe-Stand”验证控制覆盖路径。
10. 点击“查询回放/审计/事件”查看 replay、audit 和 event evidence。

## 关键 API

```text
GET  /api/v1/sim/backends
POST /api/v1/sim/preview
POST /api/v1/scenes
POST /api/v1/tasks
POST /api/v1/tasks/{task_id}/confirm
POST /api/v1/tasks/{task_id}/handoff
POST /api/v1/control/{run_id}/override
GET  /api/v1/replay/{run_id}
GET  /api/v1/audit?object_id={run_id}
GET  /api/v1/events?run_id={run_id}
```

`handoff` 可带运行参数：

```json
{
  "run_options": {
    "backend": "webots",
    "runtime_profile": "webots_fast",
    "step_count": 80,
    "forward_velocity_mps": 0.25,
    "yaw_rate_radps": 0.05,
    "obstacle_replan_distance_m": 0.25
  }
}
```

## 故障处理

- `Webots executable not found`：安装 Webots 或设置 `PATH` / `WEBOTS_HOME`，也可以切换到 `minimal` 完成 API 闭环演示。
- `mujoco` import 失败：执行 `python -m pip install -e ".[local-sim]"`，或切换到 `minimal`。
- 端口占用：使用 `--port 8001` 或停止已有服务。
- 场景保存失败：检查障碍物 ID 是否重复、半径/高度/尺寸是否为正数、scene id/version 是否填写。
- 控制台查询审计失败：审计查询需要 `auditor` 角色；Web Console 查询按钮已自动带 `x-actor-role: auditor`。

## 验证命令

```bash
python -m pytest -q
python -m ruff check python tests/python
python -m black --check python tests/python
python -m mypy python tests/python
cmake --preset dev-gcc-debug
cmake --build --preset dev-gcc-debug
ctest --preset dev-gcc-debug --output-on-failure
```

## 边界说明

当前 Web Console 是本机答辩演示控制台，不是生产级前端。它不包含真实账号登录、JWT/OIDC、对象级授权、前端路由框架和生产级消息总线。UI 只调用后端 API；动作仍必须经过 Safety Shield 语义链路，急停和人工接管仍通过控制 override API 写入审计。