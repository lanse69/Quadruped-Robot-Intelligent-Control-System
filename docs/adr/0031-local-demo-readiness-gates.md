# ADR-0031：本机答辩演示就绪门禁与 Web Console 自检

## 状态

Accepted

## 背景

当前系统已经具备 MuJoCo/Webots 本机展示后端、Web Console 场景搭建、一键任务运行、展示进程命令通道和 C++ 核心运行证据。但答辩前的实际部署风险不再主要来自业务接口缺失，而来自本机环境不一致：FastAPI/Uvicorn 未安装、MuJoCo Python 包缺失、Webots 未进入 PATH、C++ `qrics_core_runtime` 未构建、桌面入口未安装或状态目录不可写。

若这些问题只在点击“预览/运行”后暴露，任务操作者无法快速定位原因，也不利于形成可重复的验收证据。因此本阶段新增本机演示就绪门禁，把环境状态、缺失项和修复命令作为系统能力的一部分展示出来。

## 决策

1. 新增 `qrics.demo.readiness`，以无副作用方式检查 Python 版本、Web Console 静态资源、FastAPI/Uvicorn、MuJoCo、Webots 可执行程序、C++ 核心运行时、桌面应用安装脚本和本机状态目录。
2. 新增 `GET /api/v1/sim/readiness`，由应用层统一返回 `ready/degraded/blocked` 状态、检查项列表和建议执行命令。
3. Web Console 顶部新增“演示就绪检查”面板，启动后自动刷新，也可手工点击检查。
4. 新增 `scripts/check_demo_readiness.py`，支持 Markdown/JSON 输出，可用于答辩前命令行自检和证据归档。
5. 就绪检查不启动 MuJoCo/Webots 窗口、不修改桌面入口；若 C++ 二进制存在，会运行一个有步数上限的 `minimal` smoke case 来确认核心链路可执行，并且仅在状态目录写入一个短生命周期 probe 文件以确认可写性。

## 影响

- 操作者在进入场景编辑前即可看到本机演示链路是否具备必需依赖。
- C++ 核心运行时缺失时，系统直接给出 CMake 构建与 `QRICS_CPP_CORE_RUNTIME_BIN` 设置命令。
- Webots 缺失被标记为 `degraded/optional`，不阻断 MuJoCo 本机演示。
- MuJoCo、API 服务依赖、C++ runtime 和状态目录被标记为 `required`，缺失时总体状态为 `blocked`。

## 验证

- `tests/python/test_demo_readiness.py` 覆盖 ready、blocked、Markdown 渲染和 HTTP endpoint。
- Web Console 通过 `/api/v1/sim/readiness` 展示检查结果。
- 命令行可运行：

```bash
python scripts/check_demo_readiness.py --format markdown
python scripts/check_demo_readiness.py --format json
```