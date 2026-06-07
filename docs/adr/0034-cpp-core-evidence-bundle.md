# ADR-0034：C++ 核心运行时证据包

## 状态

Accepted

## 背景

上一阶段已经让 `qrics_core_runtime` 在 `--evidence-dir` 下生成 C++ replay manifest 与 segment 文件。该能力证明了 C++ 控制链可以独立产生回放证据，但答辩和验收仍需要更完整的可追溯链路：运行遥测、审计记录、文件清单与核心控制链说明应由 C++ 运行时一并落盘，而不是只依赖 Python API 或 Web Console 的响应摘要。

需求规格说明书要求系统支持任务执行、训练评估、回放审计闭环；软件设计说明书强调 `TaskGraph -> PolicyRuntime -> SafetyShield -> SimulationAdapter` 的安全边界和回放审计证据链。因此本阶段继续把证据生产前移到 C++ 核心运行时。

## 决策

`qrics_core_runtime --evidence-dir DIR` 除原有 replay manifest / segment 外，新增生成：

- `<run_id>_core_telemetry.jsonl`：按控制步记录底座位置、风险值、稳定性、地形、障碍感知、控制步数、adapter step 数和节点完成数。
- `<run_id>_core_audit.jsonl`：追加式记录运行开始、SafetyEvent 记录和运行完成事件。
- `<run_id>_core_evidence_bundle.json`：汇总 replay、segment、telemetry、audit 文件路径、计数、场景引用和 C++ 核心控制链。

C++ JSON 摘要新增 `telemetry_*`、`audit_*` 和 `evidence_bundle_*` 字段。Web Console 的运行证据展示同步显示这些路径和计数。

## 影响

正面影响：

- 答辩时可以直接打开 C++ 证据包清单，证明核心链路不是 Python 侧模拟文本。
- 回放、遥测、审计三类证据统一由 C++ runtime 生成，降低后续定位问题时的跨层解释成本。
- 证据包不引入新第三方依赖，保持本机 CMake 构建可复现。

约束与边界：

- 当前 telemetry 记录的是 C++ 本机运动学适配器控制步摘要，不替代真实 MuJoCo/Webots 高保真传感器原始流。
- audit 文件用于本地证据和答辩验收，不替代 API 层 RBAC 审计库。
- 若未传入 `--evidence-dir`，C++ runtime 保持无文件副作用，只输出 stdout JSON。

## 验证

- `qrics_cpp_core_runtime_test` 校验证据目录中 replay manifest、segment、telemetry、audit 和 bundle 文件均存在。
- 测试校验 telemetry frame 数、audit event 数与 safety event 数关系。
- `ctest --preset dev-gcc-debug --output-on-failure` 通过。