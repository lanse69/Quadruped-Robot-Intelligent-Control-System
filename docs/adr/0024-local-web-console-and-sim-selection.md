# ADR-0024 本机 Web Console 与仿真后端选择

## 状态

Accepted

## 背景

当前代码已经具备 C++ 核心控制、安全门控、任务理解、回放审计基础，以及 Python API、MuJoCo / Webots / Minimal 本机仿真后端。但面向答辩演示时，操作者仍需要通过脚本或手工 HTTP 请求完成场景保存、仿真预览、任务提交、确认、handoff、急停和回放审计查询。该路径无法满足“先有 UI，用户选择仿真软件、地形、障碍物、场地元素，保存并预览，再输入任务并运行”的演示链路。

## 决策

增加本机静态 Web Console，并将仿真后端选择从脚本参数提升为 HTTP API 运行参数：

- 新增 `SimulationRunOptionsPayload`，统一表达 `backend`、`runtime_profile`、控制步数、演示速度和障碍重规划距离。
- 新增 `GET /api/v1/sim/backends`，向控制台暴露允许的本机后端和推荐运行档位。
- 新增 `POST /api/v1/sim/preview`，用于保存场景后的短仿真预览，返回与控制运行一致的状态证据。
- 扩展 `POST /api/v1/tasks/{task_id}/handoff`，允许在 body 中传入 `run_options`，同时保持空 body 向后兼容。
- 新增 `python/qrics/webui/static`，提供无构建步骤的静态控制台，覆盖场景搭建、保存、预览、任务输入、运行、急停、Safe-Stand、回放和审计查询。
- 新增 `scripts/run_web_console.py`，以 SQLite + 本地对象存储启动本机可演示服务并打开 `/console/`。

## 约束

- Web Console 只调用 `/api/v1` 接口，不直接访问数据库、对象存储或仿真后端内部对象。
- 任务 handoff 仍走 Task API -> Control API -> Safety Shield -> Simulation Runner 语义链路，不允许 UI 提交底层关节命令。
- MuJoCo / Webots 缺失时不以示例数据伪造成功；后端返回失败状态和可解释错误，用户可切换到 `minimal` 完成无依赖演示。
- Webots 可视化启动由后端适配器负责，UI 只表达用户选择和运行参数。
- 当前控制台是本机答辩演示 UI，不声明为生产级前端工程；生产级登录、路由、状态管理、权限会话和前端构建流水线后续补充。

## 影响

正向影响：

- 答辩演示路径从脚本/HTTP 请求收敛到一个浏览器页面。
- MuJoCo / Webots 的选择进入 API 契约，避免 UI 与脚本各自维护后端枚举。
- 场景保存、预览、任务运行和安全操作产生统一事件、回放和审计证据。
- 不破坏 C++ 核心作为主要开发语言的定位，Python 仍作为传输适配、UI 承载和本机仿真桥接层。

代价：

- 静态 UI 为本机演示版，尚无生产级前端工程化能力。
- 真实 MuJoCo / Webots 可视化效果仍受本机依赖、显示环境和外部 `webots` 可执行程序影响。

## 验证

- `python -m pytest -q`
- `python -m ruff check python tests/python`
- `python -m black --check python tests/python`
- `python -m mypy python tests/python`
- `cmake --preset dev-gcc-debug`
- `cmake --build --preset dev-gcc-debug`
- `ctest --preset dev-gcc-debug --output-on-failure`

新增测试覆盖：

- `/console/` 静态入口可访问。
- `/api/v1/sim/backends` 返回后端目录。
- `/api/v1/sim/preview` 能使用保存场景和运行参数返回状态证据。
- `/api/v1/tasks/{task_id}/handoff` 能接受 `run_options` 并回传指定后端/profile。