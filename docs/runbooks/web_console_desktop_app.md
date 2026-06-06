# QRICS Web Console 桌面应用安装与卸载手册

## 1. 目标

本手册用于把 QRICS 本机 Web Console 安装为 Linux 当前用户可见的桌面应用入口。安装后，桌面菜单中会出现 `QRICS Web Console` / `QRICS 四足智控演示控制台`，点击后启动本机 API 服务并打开控制台。

当前入口用于本机答辩演示，不是生产级系统服务。它会复用当前 Python 环境中的 QRICS 代码、FastAPI、Uvicorn、MuJoCo / Webots 可选依赖。

## 2. 安装依赖

建议在项目虚拟环境内安装 API 与本机仿真依赖：

```bash
python -m pip install -e ".[api,local-sim,dev]"
```

`httpx2` 在当前项目中按本机 TestClient warning 规避依赖保留，不需要额外删除。

## 3. 直接命令启动

```bash
python scripts/run_web_console.py --host 127.0.0.1 --port 8000
```

默认状态目录为：

```text
~/.local/share/qrics/console
```

如需使用仓库内运行态目录：

```bash
python scripts/run_web_console.py --state-dir runtime/qrics-console
```

## 4. 安装桌面入口

```bash
python scripts/install_web_console_app.py install --force
```

默认写入：

```text
~/.local/bin/qrics-web-console
~/.local/share/applications/qrics-web-console.desktop
~/.local/share/qrics/console
```

安装完成后，可以从桌面菜单启动，也可以直接运行：

```bash
qrics-web-console
```

如需指定端口和状态目录：

```bash
python scripts/install_web_console_app.py install \
  --port 8010 \
  --state-dir ~/.local/share/qrics/console-demo \
  --force
```

安装前预览写入内容：

```bash
python scripts/install_web_console_app.py install --dry-run
```

## 5. 卸载桌面入口

```bash
python scripts/install_web_console_app.py uninstall
```

卸载只删除 `.desktop` 文件和启动脚本，不删除 `~/.local/share/qrics/console` 中的场景、训练、评测、回放和审计数据。若需要清空演示数据，可以手动删除状态目录。

## 6. 场景导入导出

Web Console 中的场景编辑区提供：

- `保存场景`：将当前场景写入 API repository。
- `加载已保存场景`：从持久化场景列表读取场景，并同步画布、障碍物、巡检点和低摩擦区。
- `导出场景 JSON`：把当前编辑状态保存为 JSON 文件。
- `导入场景 JSON`：从 JSON 文件恢复编辑状态；导入后仍需点击 `保存场景` 才会写入系统。
- `预览 / 打开仿真`：按当前选择的 MuJoCo / Webots / Minimal 后端打开预览或执行本机仿真 handoff。

## 7. 验证命令

```bash
python -m pytest tests/python/test_web_console_desktop_install.py tests/python/test_web_console_api.py -q
```

完整 Python 回归：

```bash
python -m pytest tests/python -q
```