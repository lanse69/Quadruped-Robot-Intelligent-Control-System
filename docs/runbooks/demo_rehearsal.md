# QRICS 本机答辩端到端演练运行手册

本手册用于答辩前做一次完整系统级自检。它不同于 `check_demo_readiness.py`：

- readiness 检查本机环境是否具备运行条件；
- rehearsal 直接走完整业务链路，验证场景、任务、控制、安全、回放、审计和训练门禁是否能串起来。

## 覆盖范围

`scripts/run_demo_rehearsal.py` 会依次执行：

1. 创建 typed 本机演示场景，包含平台、巡检点 A/B、低摩擦禁行提示区和 box/cylinder/sphere 障碍物。
2. 调用仿真预览，验证所选 `minimal` / `mujoco` / `webots` 后端可以读取场景并返回标准化观测。
3. 调用 `POST /api/v1/tasks/run` 对应的应用层一键路径，完成中文任务解析、TaskScript / TaskGraph、确认、handoff、C++ runtime 探测、回放创建与事件沉淀。
4. 查询控制状态、回放索引、审计记录和事件快照。
5. 下发 Safe-Stand 与 EmergencyStop，验证安全接管和高风险操作审计。
6. 执行轻量训练-评测-模型门禁闭环：训练计划、启动、检查点、完成候选策略注册、标准化评测、审批、发布、提升为基线。
7. 生成 JSON 与 Markdown 演练证据。

## 推荐命令

答辩前先跑环境就绪检查：

```bash
python scripts/check_demo_readiness.py --format markdown
```

再跑快速端到端演练：

```bash
python scripts/run_demo_rehearsal.py \
  --backend minimal \
  --runtime-profile headless_fast \
  --step-count 12 \
  --output-dir runtime/demo-rehearsal
```

本机已安装 MuJoCo 后，可用 headless MuJoCo 验证真实物理后端：

```bash
python scripts/run_demo_rehearsal.py \
  --backend mujoco \
  --runtime-profile headless_fast \
  --step-count 120 \
  --output-dir runtime/demo-rehearsal-mujoco
```

需要让 MuJoCo viewer 自动打开时，建议优先通过 Web Console 演示；命令行演练默认更偏向可重复验收证据。如果需要预览窗口，先启动：

```bash
python scripts/run_web_console.py --host 127.0.0.1 --port 8000
```

然后在 `/console/` 选择 MuJoCo / `balanced_visual` 并点击“预览 / 打开仿真”和“运行任务”。

Webots 本机展示已安装后，可先执行 dry-run 式链路：

```bash
python scripts/run_demo_rehearsal.py \
  --backend webots \
  --runtime-profile webots_fast \
  --step-count 12 \
  --output-dir runtime/demo-rehearsal-webots
```

如需允许 Webots 外部进程启动：

```bash
python scripts/run_demo_rehearsal.py \
  --backend webots \
  --runtime-profile webots_fast \
  --step-count 12 \
  --webots-execute \
  --output-dir runtime/demo-rehearsal-webots
```

## 输出文件

默认输出：

```text
runtime/demo-rehearsal/qrics_demo_rehearsal.json
runtime/demo-rehearsal/qrics_demo_rehearsal.md
```

Markdown 文件适合答辩材料引用，JSON 文件适合保留为验收证据。报告中每个步骤都有 `passed` / `failed` 状态；只要任一步失败，脚本退出码为 `1`。

## 常用参数

| 参数 | 说明 |
| --- | --- |
| `--backend minimal|mujoco|webots` | 选择演练后端。 |
| `--runtime-profile` | 选择运行档位，例如 `headless_fast`、`balanced_visual`、`webots_fast`。 |
| `--step-count` | 仿真控制步数。答辩前可设大一点，CI/smoke 可设小一点。 |
| `--skip-training-gate` | 只验证任务执行链路，不跑训练/评测/策略门禁。 |
| `--skip-overrides` | 不下发 Safe-Stand / EmergencyStop。 |
| `--fixed-scene-version` | 使用固定场景版本；默认会追加时间戳后缀，避免重复运行冲突。 |
| `--format markdown|json|summary` | 控制终端输出格式。证据文件始终会写入输出目录。 |

## 通过标准

演练通过时应看到：

```text
status: passed
failed_steps: 0
```

关键步骤应包含：

- `scene_create`
- `simulation_preview`
- `task_one_click_run`
- `replay_query`
- `override_safe_stand`
- `override_emergency_stop`
- `audit_query`
- `events_query`
- `training_plan`
- `training_checkpoint`
- `evaluation_gate`
- `policy_baseline`

## 故障定位

- `simulation_preview` 失败：优先跑 `python scripts/check_demo_readiness.py --format markdown`，确认 MuJoCo/Webots 依赖和运行模式。
- `task_one_click_run` 失败：检查中文任务是否包含已存在的场景点位，例如 A、B、平台。
- `override_*` 失败：确认前置任务已经生成 `run_id`，且 high-risk reason 不为空。
- `evaluation_gate` 失败：查看报告中的 metrics，门禁要求硬约束违规为 0、成功率不低于阈值、碰撞率和轨迹偏差不超限。
- `policy_release` 或 `policy_baseline` 失败：确认评测门禁和审批步骤已经通过。