# Typed Scene Geometry、MuJoCo/Webots 障碍绑定与回放清单运行说明

## 适用范围

本文说明本机 MuJoCo + Webots 演示路径中 typed scene geometry 的使用方式，以及 C++ ReplayManifest 写入器的验证方式。该能力用于把场景障碍、仿真后端和安全事件回放链路串联起来。

## 创建带几何障碍的场景

HTTP 或 API Facade 创建场景时，`assets` 中的 obstacle 可使用内联几何字段，不必提供外部 `uri`：

```json
{
  "scene_id": "demo_obstacle_scene",
  "name": "demo_obstacle_scene",
  "assets": [
    {
      "asset_id": "obs_01",
      "asset_type": "obstacle",
      "geometry_type": "cylinder",
      "position": [1.5, 0.0, 0.0],
      "radius_m": 0.25,
      "height_m": 0.6,
      "size": [0.0, 0.0, 0.0],
      "metadata": {"label": "demo obstacle"}
    }
  ]
}
```

字段规则：

- `geometry_type` 可取 `none`、`sphere`、`box`、`cylinder`。
- `position` 为 `[x, y, z]`，单位为米。
- `cylinder` 障碍要求 `radius_m > 0` 且 `height_m > 0`。
- `box` 障碍要求 `size` 三个分量均大于 0。
- `sphere` 障碍要求 `radius_m > 0`。
- 未设置 typed geometry 的 legacy 资产仍按 `uri` / `checksum` 校验。

## 本机后端行为

### MuJoCo

MuJoCo 后端加载场景时会把 typed obstacle 转换为 MJCF `geom`，并重建模型。当前实现优先把 typed obstacle 绑定为圆柱障碍对象，供本机物理演示、避障距离估计和后续碰撞关键帧扩展使用。

### Webots

Webots 后端把 typed obstacle 写入运行 spec JSON。Supervisor controller 启动后读取 spec，并向 world root 动态导入 `Solid` 障碍节点。dry-run 模式只验证命令和 spec，不启动 Webots 进程。

## 验证命令

推荐先安装开发依赖：

```bash
python -m pip install -e ".[api,local-sim,dev]"
```

执行快速质量门禁：

```bash
./scripts/check_all.sh --quick
```

仅验证 C++ 回放清单写入器：

```bash
cmake --preset dev
cmake --build --preset dev
ctest --test-dir build --output-on-failure -R qrics_replay_manifest_writer_test
```

仅验证相关 Python 契约：

```bash
pytest -q \
  tests/python/test_api_scenes.py \
  tests/python/test_api_facade.py \
  tests/python/test_mujoco_backend_contract.py \
  tests/python/test_webots_backend_contract.py
```

## 本机演示建议

MuJoCo 默认演示：

```bash
python scripts/run_local_sim_demo.py --profile balanced_visual --seconds 8 --viewer
```

Webots 默认演示：

```bash
python scripts/run_webots_demo.py --profile webots_fast --seconds 8
```

Webots QRICS 侧 dry-run：

```bash
python scripts/run_webots_demo.py --dry-run --seconds 2
```

若本机未安装 MuJoCo 或 Webots，`./scripts/check_all.sh --quick` 仍会报告可选依赖缺失但不阻断；正式演示前应在本机安装对应运行环境，并使用 `--full` 或显式演示脚本确认外部进程可启动。当前默认演示脚本加载内置 demo scene；若要演示自定义 typed obstacle，可通过 API 创建场景后走后端契约或扩展演示脚本的场景参数。