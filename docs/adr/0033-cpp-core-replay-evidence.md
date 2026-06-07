# ADR-0033：C++ 核心运行时回放证据落盘

## 状态

Accepted

## 背景

当前系统已经具备 Web Console 场景搭建、MuJoCo/Webots 本机展示、一键任务运行和 C++ `qrics_core_runtime` 自检能力。为了满足“系统以 C++ 为主要、核心开发语言”的演示口径，仅返回 C++ JSON 摘要还不够：答辩时需要能说明核心任务执行、安全门控和回放证据不是完全由 Python 层生成。

需求规格说明书要求任务、实验、策略、回放和审计可追溯；软件设计说明书也将 Replay/Audit 作为核心机制之一。此前 Python 本机 runner 会生成回放响应，但 C++ 核心运行时没有直接落盘回放清单。

## 决策

在 C++ `LocalTaskRunRequest` 中新增 `evidence_dir`，在 `LocalTaskRunSummary` 中新增：

- `replay_manifest_uri`
- `replay_manifest_path`
- `replay_segment_uri`
- `replay_segment_path`
- `replay_keyframe_count`

`qrics_core_runtime` 新增命令行参数：

```bash
--evidence-dir DIR
```

当该参数存在时，C++ 核心运行时在任务完成后调用 `ReplayManifestWriter`：

```text
TaskExecutor
  -> SafetyShield
  -> SimulationAdapter
  -> ReplayManifestWriter
  -> <run_id>_core_replay_manifest.json
  -> <run_id>_core_segment.jsonl
```

Python API 桥接层新增 `CoreRuntimeRunRequest.evidence_dir` 并把该路径传给 C++ runtime。Web Console 持久化启动器将 evidence dir 固定到：

```text
<state-dir>/core_runtime_evidence
```

## 后果

优点：

- C++ 核心运行证据从“stdout 摘要”提升为“stdout + 回放清单文件 + segment 文件”。
- Web Console 一键运行响应中可以展示 C++ 回放清单路径，便于答辩截图和问题复盘。
- 不引入第三方依赖；沿用既有 C++ `ReplayManifestWriter`。

代价：

- C++ runtime 需要访问本地文件系统；无 `--evidence-dir` 时保持无落盘副作用。
- 当前 segment 文件仍是轻量 JSONL 摘要，不替代后续高频遥测流完整持久化。

## 验证

新增或更新验证点：

- C++ `qrics_cpp_core_runtime_test` 检查 manifest/segment 文件生成、路径回填和 keyframe 数量。
- Python `test_cpp_core_runtime_bridge.py` 检查 `--evidence-dir` 被传入 C++ runtime 命令。
- Web Console 前端显示 C++ 回放清单路径与关键帧数量。