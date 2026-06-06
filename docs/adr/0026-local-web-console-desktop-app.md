# ADR-0026: 本机 Web Console 桌面化启动与场景导入导出

## 状态

Accepted

## 背景

当前仓库已经具备 FastAPI / WebSocket 服务入口、本机 MuJoCo / Webots 后端、Web Console 场景编辑与任务运行能力。答辩演示需要一个更接近“可安装应用”的入口，而不是要求操作者记忆 `python scripts/run_web_console.py` 命令。

同时，场景编辑已经支持在画布中拖动障碍物、巡检点和低摩擦区，但用户自建场景在控制台中的导入、导出和再次加载路径还不够直接。

## 决策

新增 `qrics.webui.launcher` 和 `qrics.webui.desktop`：

- `qrics.webui.launcher` 作为包内可运行入口，统一创建 SQLite repository、本地 object store 和 FastAPI Web Console。
- `scripts/run_web_console.py` 改为委托 `qrics.webui.launcher.main()`，避免脚本与桌面入口重复维护服务启动逻辑。
- `scripts/install_web_console_app.py` 支持 `install` / `uninstall`，在 Linux 用户目录安装 `.desktop` 文件和 `qrics-web-console` 启动脚本。
- 桌面入口默认使用 `~/.local/share/qrics/console` 持久化 SQLite 元数据与本地对象存储。
- Web Console 增加已保存场景下拉框、加载已保存场景、导出场景 JSON、导入场景 JSON 和障碍物高度编辑。

## 约束

- 桌面安装只写入当前用户目录，不需要 root 权限。
- 桌面入口不打包 MuJoCo、Webots 或 Python 运行环境；它启动当前 Python 环境中的 QRICS Web Console。
- `.desktop` 入口以 `Terminal=true` 运行，便于演示时看到服务日志，也便于关闭服务。
- 场景 JSON 导入只更新本地编辑器状态；用户仍需点击“保存场景”后才写入系统 repository。

## 后果

- 演示者可以通过桌面应用入口打开本机 UI，满足“先有一个 UI，一个可安装卸载应用”的答辩演示路径。
- 用户自建场景可以通过 JSON 文件在不同演示会话之间迁移，也可以从 SQLite 持久化的场景列表直接加载。
- 服务启动逻辑集中在包内 launcher，后续若迁移到 PyInstaller、Briefcase 或系统服务，只需要复用该入口。