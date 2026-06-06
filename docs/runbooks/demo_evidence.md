# QRICS 本机演示证据包运行手册

## 1. 目标

本手册用于在 MuJoCo / Webots / minimal 本机后端上生成答辩可用证据包。证据包包含任务输入、任务 handoff 状态、仿真后端、障碍感知摘要、安全事件、回放索引、急停审计和事件快照。

## 2. 生成默认证据包

```bash
python scripts/run_demo_evidence.py --output-dir runtime/demo-evidence --backend minimal
```

输出：

```text
runtime/demo-evidence/qrics_demo_evidence.json
runtime/demo-evidence/qrics_demo_evidence.md
```

## 3. 使用 MuJoCo 后端

需要先安装本地仿真依赖：

```bash
python -m pip install -e ".[api,local-sim,dev]"
```

生成 MuJoCo 证据包：

```bash
python scripts/run_demo_evidence.py \
  --output-dir runtime/demo-evidence-mujoco \
  --backend mujoco \
  --runtime-profile headless_fast
```

## 4. 使用 Webots 后端

不启动外部 Webots 进程，仅验证 QRICS 侧命令、场景和证据链：

```bash
python scripts/run_demo_evidence.py \
  --output-dir runtime/demo-evidence-webots \
  --backend webots \
  --runtime-profile webots_fast
```

需要启动真实 Webots 进程时增加：

```bash
--webots-execute
```

## 5. 指定 typed scene JSON

示例：

```json
{
  "scene_id": "defense_scene",
  "version": "0.1.0",
  "terrain_pack": "mixed_terrain_pack",
  "obstacles": [
    {"id": "box_1", "geometry_type": "box", "position": [0.25, 0.0, 0.35], "size": [0.2, 0.16, 0.3]},
    {"id": "sphere_1", "geometry_type": "sphere", "position": [0.7, 0.2, 0.35], "radius_m": 0.09},
    {"id": "barrel_1", "geometry_type": "cylinder", "position": [1.1, -0.1, 0.35], "radius_m": 0.08, "height_m": 0.35}
  ]
}
```

运行：

```bash
python scripts/run_demo_evidence.py \
  --output-dir runtime/defense-evidence \
  --backend minimal \
  --scene-json configs/scenes/defense_scene.json
```

MuJoCo 与 Webots 单独演示脚本也支持同一参数：

```bash
python scripts/run_local_sim_demo.py --profile headless_fast --scene-json configs/scenes/defense_scene.json
python scripts/run_webots_demo.py --dry-run --scene-json configs/scenes/defense_scene.json
```

## 6. 验证命令

```bash
python -m compileall -q python tests/python scripts
python -m pytest tests/python -q
cmake --preset dev-gcc-debug
cmake --build --preset dev-gcc-debug
ctest --preset dev-gcc-debug --output-on-failure
```