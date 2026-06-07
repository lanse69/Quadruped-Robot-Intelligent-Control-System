# 基于仿真环境的四足机器人智能控制系统

> Quadruped Robot Intelligent Control System  
> Simulation-based Quadruped Robot Intelligent Control System  
> QRICS

本项目面向四足机器人仿真研发场景，构建单机器人在仿真环境中的任务理解、任务编排、安全控制、策略训练、模型治理、实验回放与审计闭环。

当前仓库以 **C++20 为核心、Python 为应用接口与仿真适配辅助层**。C++ 负责领域模型、任务理解流水线、配置加载、控制链路、任务执行、安全门控、训练治理与回放审计基础模型；Python 当前承担依赖标准库的 API Facade、可选 FastAPI / WebSocket 服务化入口、事件流、Isaac Lab 适配契约、训练指标聚合、本机 MuJoCo / Webots 仿真后端、本机 Web Console 演示入口与后续 NLP / 多模态扩展边界。

当前版本号：`0.1.0`。

---

## 1. 当前实现状态

### 已实现

工程与质量基础：

- C++20 / CMake / Ninja 工程骨架。
- `qrics_core` 静态库。
- `qrics_cli` 命令行入口，用于输出项目名与版本。
- `qrics_core_runtime` C++ 核心任务运行入口，用于输出 `TaskExecutor -> SafetyShield -> SimulationAdapter` JSON 运行证据。
- Python 包：`python/qrics`，包含 API Facade、Isaac Lab 契约、训练指标和本机仿真辅助层。
- GitHub Actions CI：C++ 构建测试、Python 测试、ruff / black / mypy 检查。
- clang-format / clang-tidy / ruff / black / mypy 配置。
- 环境采集脚本：`scripts/collect_env.sh`。
- 一键检查脚本：`scripts/check_all.sh`。
- 基础配置样例：场景、策略、训练配置。
- ADR 文档：工程骨架、安全门控与控制闭环、任务理解基线、任务编排、配置加载、任务执行、监控审计、Isaac Lab 契约、训练治理、API Facade、本机多仿真路线、FastAPI / WebSocket 服务边界、场景资源 API、训练评测运行态 API、策略审批报告导出、Webots 本机演示后端、本机观测映射安全证据闭环、typed scene geometry、MuJoCo/Webots 场景障碍绑定、C++ ReplayManifest 写入器、本机答辩演示证据包、本机 Web Console 与仿真后端选择，以及 C++ 核心任务运行契约与 C++ 回放证据落盘。

领域模型与接口：

- 通用基础类型：`Vec3`、`Quaternion`、`Pose`、`ResourceRef`、`Checksum`、`Result<T>`、`Error`。
- 场景模型：`SceneProfile`、`SceneObstacle`、`SensorProfile`、`RandomizationProfile`、`ForbiddenZone`、`Checkpoint`；API 层 `SceneAssetPayload` 支持 `box` / `sphere` / `cylinder` typed geometry，并可向 MuJoCo / Webots 本机后端映射障碍物对象。
- 任务模型：`TaskScript`、`TaskConstraint`、`Waypoint`、`TaskGraph`、`TaskNode`、`TaskEdge`。
- 任务上下文：`TaskParseContext`、`NamedWaypoint`、`AvoidZoneAlias`。
- 控制动作模型：`ActionProposal`、`SafeAction`、`JointCommand`、`SafetyDecision`。
- 观测与机器人状态：`ObservationPacket`、`ObstacleState`、`RobotState`、`TerrainClass`、`StabilityState`。
- 安全事件与人工接管：`SafetyEvent`、`OverrideCommand`。
- 策略工件模型：`PolicyArtifact`、`MetricsDigest`、`PolicyStage`。
- 实验运行模型：`ExperimentRun`。
- 任务生命周期与会话模型：`TaskLifecycle`、`TaskOrchestratorService`、`TaskSessionStore`。
- 监控、回放与审计模型：`TelemetryFrame`、`AlertEvent`、`ReplayManifest`、`KeyFrameIndex`、`AuditLog`；C++ `ReplayManifestWriter` 可将安全事件追加为关键帧并生成稳定回放清单 JSON。
- 训练评测与模型治理模型：`MetricReport`、`GateReport`、`ApprovalRecord`、`GateEngine`、`PolicyRegistry`。
- 仿真适配接口：`SimulationAdapter`。
- C++ 本机仿真边界：`LocalBackendKind`、`LocalRuntimeProfile`、`LocalBackendDescriptor`、`KinematicLocalSimulationAdapter`，用于将 MuJoCo / Webots / Isaac Lab 后端选择纳入核心库而不是仅留在 Python 层。
- C++ 核心任务运行契约：`LocalTaskRunRequest`、`LocalTaskRunSummary`、`run_local_task()` 与 `qrics_core_runtime` 命令行程序把场景、任务路径、策略运行、任务图、Safety Shield、关键帧和安全事件串成可执行核心链路；新增 `--evidence-dir` 可由 C++ `ReplayManifestWriter` 直接落盘 `<run_id>_core_replay_manifest.json` 和 `<run_id>_core_segment.jsonl`，Python API 与 Web Console 负责触发、探测和展示该核心运行证据。
- C++ 控制能力增强：`PurePursuitPathTracker`、`StabilityRecoveryController`、`SimpleObstacleAvoidance` 与 `TerrainAwareGaitGenerator` 已进入核心库，并由 `SimpleLocalPlanner -> RuleBasedPolicyRuntime -> TaskExecutor -> SafetyShield -> KinematicLocalSimulationAdapter` 串联到任务执行链路。`ActionProposal` 会携带地形感知步态提示、足端相位和 12 关节名义位置提示；`SafetyShield` 只把经校验的 `SafeAction` 下发给仿真适配器，回放证据与 Web Console 可展示 C++ 步态、步频和摆动/支撑足数量。
- 本机行走展示桥接：`SafeAction` 的 `LocomotionHint`、足端相位和 12 关节名义位置提示已扩展到 Python MuJoCo / Webots 演示链路；`SimulationRunner`、`run_local_sim_demo.py` 和 `run_webots_demo.py` 会按当前地形生成展示用步态提示，使本机仿真窗口中的四足机器人不再只做质点式平移，而是同步呈现支撑/摆动足、名义关节目标和地形降速。

安全门控与最小控制闭环：

- `SafetyShield` 抽象接口。
- `BasicSafetyShield` 占位实现。
- `SafetyLimits`、`SafetyContext`、`SafetyEvaluation`。
- EmergencyStop 优先级处理。
- ManualControl / `manual_override_active` 阻断自动动作。
- SafeStand 请求处理。
- Fallen / Unstable / `risk_score` 超限时进入 SafeStand。
- BodyVelocity 线速度和 yaw rate 裁剪。
- JointPosition / JointVelocity 默认阻断，可通过 `allow_joint_commands` 放开。
- `SafetyShield` 已补充观测缺失、障碍碰撞风险和禁行区硬约束检查。
- `ControlLoop::step_once()` 最小闭环：

```text
ActionProposal -> SafetyShield -> SafeAction -> SimulationAdapter::step()
```

控制增强链路：

```text
TaskNode + RobotState + ObservationPacket
  -> StabilityRecoveryController
  -> PurePursuitPathTracker
  -> SimpleObstacleAvoidance
  -> TerrainAwareGaitGenerator
  -> ActionProposal + LocomotionHint
  -> SafetyShield
  -> SafeAction + LocomotionHint
```

任务理解、约束检查、策略选择与执行预览：

- `TaskParser` 抽象接口。
- `RuleBasedChineseTaskParser` 中文规则解析器。
- `ConstraintEngine` 抽象接口。
- `BasicTaskConstraintEngine` 基础任务约束检查器。
- `PolicySelector` 抽象接口。
- `RuleBasedPolicySelector` 规则策略选择器。
- `TaskGraphPlanner` 抽象接口。
- `SequentialTaskGraphPlanner` 顺序任务图规划器。
- `ExplanationService` 抽象接口。
- `BasicExplanationService` 执行预览生成器。
- `TaskUnderstandingPipeline` 完整任务理解流水线：

```text
中文任务文本
  -> RuleBasedChineseTaskParser
  -> TaskScript
  -> BasicTaskConstraintEngine
  -> RuleBasedPolicySelector
  -> SequentialTaskGraphPlanner
  -> BasicExplanationService
  -> ExecutionPreview
```

当前规则解析器已经支持的基础能力：

- 从中文文本中匹配命名路径点，例如 `A`、`B`、`平台`。
- 根据文本顺序生成任务路径点序列。
- 识别“避开 / 绕开 / 不要进入 / 禁止进入 / 禁行”等禁行区约束词。
- 通过上下文中的 `AvoidZoneAlias` 将中文区域别名映射为禁行区 ID。
- 识别“驻留 / 停留 / 等待 / 待命 N 秒”的末尾路径点驻留时间。
- 根据“重新规划 / 绕行 / 回到平台 / 返回起点 / 停止”等语义推断回退动作。
- 在无法匹配路径点时返回 `NO_WAYPOINT_MATCHED`。

当前约束检查器已经支持：

- `task_id`、`version`、`scene_ref`、`waypoints` 基础完整性检查。
- 路径点 ID 空值检查。
- 最大线速度、最大 yaw rate 正值检查。
- 超过 1.0 的速度或 yaw rate 标记为需要裁剪 / 重规划。
- 检查 `avoid_zone_ids` 是否存在于当前 `SceneProfile.forbidden_zones`。

当前策略选择器已经支持：

- 仅允许 `Released` 和 `Baseline` 状态策略进入候选。
- 跳过带有 `risk_flag` 的策略。
- 按任务标签与地形标签筛选策略。
- 无匹配策略时回退到 `placeholder_policy:0.1.0`。

当前顺序任务图规划器已经支持：

- 为每个路径点生成 `MoveTo` 节点。
- 当路径点存在 `dwell_time_s` 时生成 `Dwell` 节点。
- 生成顺序 `completed` 边。
- 追加终止 `Stop` 节点。
- 绑定策略标签与回退动作。

当前执行预览已经支持：

- 生成 `preview_id`。
- 绑定 `task_ref` 与 `graph_ref`。
- 汇总策略选择理由。
- 汇总约束风险摘要。
- 保留是否需要操作者确认的标志。

配置加载、任务执行、监控回放与模型治理基础：

- 场景 / 策略 / 训练配置加载器与结构化错误模型。
- 场景检查点、禁行区、传感器、域随机化、策略状态和训练参数基础校验。
- `TaskOrchestratorService` 应用层任务生命周期骨架。
- `TaskExecutor`、`PolicyRuntime` 抽象、规则策略运行时和简单局部规划器。
- `EventSink` / `InMemoryEventSink` 事件输出接口。
- `ReplayManifest`、`KeyFrameIndex` 和追加式 `AuditLog` 基础实现。
- `GateEngine`、`PolicyRegistry`、策略审批、评测报告导出、策略发布、基线切换和回滚审计基础实现。

Python API、事件流与本机仿真辅助层：

- `python/qrics/api` 分为两层：依赖标准库的应用 API Facade，以及位于 `qrics.api.http_app` 的可选 FastAPI / WebSocket 传输适配层。基础 `import qrics.api` 不应依赖 FastAPI；需要 HTTP 服务时显式导入 `qrics.api.http_app` 或使用 `scripts/run_api_service.py`。
- `routes_scenes`、`routes_tasks`、`routes_control`、`routes_training`、`routes_policies`、`routes_replay`、`routes_audit` 覆盖场景、任务、控制、训练、策略、回放和审计入口。
- `InMemoryEventStream` 支持 `append()`、`list_events()`、`query()`、`drain()`，用于 API 测试和本机演示事件追踪。
- API handoff 可接入本机 `SimulationRunner`，并可通过 HTTP body 的 `run_options` 选择 `minimal` / `mujoco` / `webots` 后端、runtime profile、控制步数、前进速度、yaw rate 与障碍重规划距离；返回 `backend`、`runtime_profile`、`control_step_count`、`sim_time_ns`、`base_position`、`observation_quality`、`terrain_class`、`obstacle_detected`、`nearest_obstacle_distance_m`、`safety_event_count` 等仿真与安全证据字段。MuJoCo/Webots viewer 模式还会返回 `presentation_pid`、`presentation_workspace`、`presentation_command_dir` 和 `presentation_command_path`，用于确认已打开展示窗口接收了运行任务命令；急停、暂停、人工接管和 Safe-Stand override 也会通过同一命令目录向已打开窗口写入 `stop` / `safe_stand` 命令。
- `python/qrics/isaac_lab` 提供 Isaac Lab Adapter 契约、动作映射和观测映射；当前是契约层，不声明已经完成 Isaac Lab 真实仿真闭环。
- `python/qrics/sim` 提供 Minimal 契约后端、MuJoCo 本机物理后端和 Webots 本机可视化后端抽象，并将场景障碍物、混合地形、步态提示、足端接触相位和关节位置提示映射为标准化观测/命令，用于低成本 smoke test、物理步进和答辩演示。
- `python/qrics/training/metric_calculator.py` 提供训练评测指标聚合基础能力；API 层已补齐训练任务配置摘要、状态流转、检查点记录、训练完成注册候选策略、标准化评测报告、策略 gate 状态更新、审批记录和评测报告导出。
- `python/qrics/nlp` 提供本机演示可用的中文自然语言任务解析器、场景感知 waypoint / no-go-zone catalog、TaskScript 草案、TaskGraph 预览、解析置信度、解释字段和 AI 安全边界拒绝逻辑；当前不引入在线 LLM 依赖。
- `python/qrics/demo/rehearsal.py` 提供本机答辩端到端演练器，可自动验证场景创建、仿真预览、中文任务一键运行、安全接管、回放审计和轻量训练-评测-模型门禁链路，并输出 JSON / Markdown 证据。
- API 契约文档位于 `docs/api/openapi.md`，事件契约文档位于 `docs/api/events.md`；场景资源操作说明位于 `docs/runbooks/scene_management.md`，训练评测运行说明位于 `docs/runbooks/training_evaluation.md`，策略审批与报告导出说明位于 `docs/runbooks/policy_approval_report_export.md`，Webots 本机演示说明位于 `docs/runbooks/webots_local_backend.md`，本机观测映射与安全回放说明位于 `docs/runbooks/observation_mapping.md`，Web Console 演示说明位于 `docs/runbooks/web_console.md`，C++ 核心运行时说明位于 `docs/runbooks/cpp_core_runtime.md`，C++ 地形感知步态控制说明位于 `docs/runbooks/cpp_gait_control.md`，本机展示进程命令通道说明位于 `docs/runbooks/presentation_command_channel.md`，答辩演示就绪检查说明位于 `docs/runbooks/demo_readiness.md`，答辩端到端演练说明位于 `docs/runbooks/demo_rehearsal.md`；C++ 核心回放证据设计记录位于 `docs/adr/0033-cpp-core-replay-evidence.md`，C++ 核心证据包设计记录位于 `docs/adr/0034-cpp-core-evidence-bundle.md`，C++ 地形感知步态控制设计记录位于 `docs/adr/0035-cpp-terrain-aware-gait-control.md`，本机步态展示桥接说明位于 `docs/runbooks/gait_presentation.md`，设计记录位于 `docs/adr/0036-local-gait-presentation-bridge.md`。
- RBAC 与审计运行手册位于 `docs/runbooks/rbac_audit.md`，架构决策记录位于 `docs/adr/0014-rbac-and-audit-gates.md`、`docs/adr/0015-api-type-safety-and-rbac-policy-source.md` 和 `docs/adr/0018-policy-approval-and-report-export.md`。
- `python/qrics/api/http_app.py` 提供 FastAPI HTTP / WebSocket 服务化入口，覆盖任务、控制、训练、策略、回放、审计和事件查询。
- `python/qrics/api/security.py` 是 API 权限矩阵、高风险操作策略、override 动作映射、角色规范化和 gate decision 校验的单一事实源；`QricsApiApp` 与 HTTP 适配层只调用该模块，不维护重复权限矩阵。
- 高风险操作的成功、权限失败和业务拒绝路径会写入追加式审计记录；策略注册、门禁报告、审批、评测报告导出、发布和基线切换作为模型状态流转均有审计证据。
- HTTP / WebSocket 层缺失或未知角色统一规范化为非提权 `operator`；训练、策略治理和审计查询必须显式传入 `algorithm_engineer`、`auditor` 或 `admin` 等对应角色。
- `scripts/run_api_service.py` 可启动本机 API 服务；`scripts/run_web_console.py` 可启动带静态 Web Console 的本机演示服务，并默认打开 `/console/`。Web Console 的“运行任务”入口调用 `POST /api/v1/tasks/run`，由应用层一键完成任务解析、确认、handoff、回放创建与 MuJoCo/Webots 展示命令下发，避免前端重复编排生命周期。若预览窗口仍在运行，会复用已有 MuJoCo/Webots 窗口并向其 `commands/` 目录写入任务路径命令；若窗口尚未打开，会按所选 viewer profile 自动打开。点击急停或安全站立时会向同一窗口写入 `stop` / `safe_stand` 命令，使可视化窗口与 API 控制状态一致。Web Console 任务输出会展示 parser version、解析置信度、约束、回退动作、TaskScript 和 TaskGraph 证据。
- `GET /api/v1/sim/readiness`、`scripts/check_demo_readiness.py` 与 Web Console 顶部“演示就绪检查”面板会在不启动仿真窗口的前提下检查 API、MuJoCo、Webots、C++ runtime、桌面入口和状态目录，并输出可复制修复命令；
- `scripts/run_demo_rehearsal.py` 可执行答辩端到端演练，按应用层真实顺序跑通 typed 场景、仿真预览、自然语言任务、handoff、安全接管、回放审计、训练检查点、评测门禁、策略审批发布和基线提升，输出 `qrics_demo_rehearsal.json/.md`。
- `GET /api/v1/sim/core-runtime` 与 Web Console“C++核心自检”按钮可探测已构建的 `qrics_core_runtime`，返回 C++ 核心运行时二进制路径、执行命令、节点状态、关键帧和安全事件摘要；`POST /api/v1/tasks/run` / handoff 会在 MuJoCo/Webots 展示链路之外同步调用 C++ 核心运行时，并把用户保存场景中的 typed obstacles、禁行区和任务路径下发给 C++，状态响应中的 `core_runtime_summary` 可证明一键任务运行经过 C++ TaskExecutor、SafetyShield 和 SimulationAdapter 契约；当配置 `core_runtime_evidence_dir` 或传入 `--evidence-dir` 时，C++ 侧还会落盘 replay、telemetry、audit 和 evidence bundle 文件；`scripts/run_cpp_core_runtime_demo.py` 可在命令行输出同一自检证据。
- `QricsRepository`、`SQLiteQricsRepository` 与 `FileObjectStore` 提供本机持久化元数据、场景配置包、训练任务、评测报告、评测导出工件、策略审批、策略状态、回放清单、审计记录和事件索引能力。
- `scripts/run_api_service.py --state-dir runtime/qrics-api` 可使用 SQLite + 本地不可变对象存储启动 API 服务；场景模板、训练任务、评测报告、评测导出工件、策略审批、策略版本、基线状态与审计事件会随同持久化。

测试覆盖：

- C++ 测试：版本、领域模型、安全门控、控制闭环、任务理解流水线、配置加载、任务编排、任务执行、事件输出、回放索引、回放清单写入器、审计日志、门禁引擎、策略注册、本机仿真适配和控制集成。
- Python 测试：Python 包版本、API Facade、FastAPI HTTP 服务、WebSocket 事件快照、Web Console 静态入口与仿真预览 API、训练/评测运行态、SQLite 持久化、Isaac Lab 契约、指标聚合、仿真后端契约、MuJoCo 后端契约和 Webots 后端契约。

当前 CTest 目标：

```text
qrics_version_test
qrics_domain_model_test
qrics_safety_shield_test
qrics_control_loop_test
qrics_task_understanding_test
qrics_scene_config_loader_test
qrics_policy_config_loader_test
qrics_task_orchestrator_test
qrics_task_executor_test
qrics_event_sink_test
qrics_replay_index_test
qrics_replay_manifest_writer_test
qrics_audit_log_test
qrics_gate_engine_test
qrics_policy_registry_test
qrics_gait_generator_test
qrics_policy_runtime_test
qrics_local_simulation_adapter_test
qrics_path_tracker_test
qrics_recovery_controller_test
qrics_obstacle_avoidance_test
qrics_local_control_integration_test
qrics_cpp_core_runtime_test
```


```text
test_version.py
test_api_facade.py
test_api_scenes.py
test_api_security.py
test_api_security_policy.py
test_http_security.py
test_isaac_lab_adapter_contract.py
test_metric_calculator.py
test_sim_backend_contract.py
test_mujoco_backend_contract.py
test_webots_backend_contract.py
test_api_simulation_runner.py
test_api_mujoco_handoff_optional.py
test_http_api.py
test_websocket_events.py
test_web_console_api.py
test_web_console_desktop_install.py
test_object_store.py
test_repository_persistence.py
test_training_evaluation_runtime.py
test_rule_based_task_parser.py
test_ai_safety_boundaries.py
test_cpp_core_runtime_bridge.py
```

RBAC 与审计门控测试已合入 `test_api_facade.py`、`test_api_security.py`、`test_api_security_policy.py`、`test_http_api.py` 和 `test_http_security.py`。



### 本机桌面应用入口

当前 Web Console 可安装为 Linux 当前用户桌面菜单入口：

```bash
python scripts/install_web_console_app.py install --force
```

卸载入口：

```bash
python scripts/install_web_console_app.py uninstall
```

安装后会创建：

```text
~/.local/bin/qrics-web-console
~/.local/share/applications/qrics-web-console.desktop
```

运行态默认保存在 `~/.local/share/qrics/console`。如需先查看写入内容而不安装，可执行：

```bash
python scripts/install_web_console_app.py install --dry-run
```

### 本机答辩演示证据包

- `scripts/run_demo_evidence.py` 可一键生成本机演示证据包，内容包括任务输入、控制 handoff、后端/profile、障碍感知、安全事件、回放索引、急停审计和事件快照。
- `scripts/run_demo_rehearsal.py` 可一键执行答辩端到端演练，覆盖场景保存、仿真预览、任务运行、安全接管、回放审计和训练/评测/模型门禁，并输出 `qrics_demo_rehearsal.json` 与 `qrics_demo_rehearsal.md`。
- `scripts/run_local_sim_demo.py` 与 `scripts/run_webots_demo.py` 支持 `--scene-json`，可现场切换 typed `box` / `sphere` / `cylinder` 障碍场景。
- 本地仿真 schema 与 C++ `SceneObstacle` 均支持 typed obstacle geometry；MuJoCo 会生成对应 geom，Webots 会生成对应 Solid 节点。
- 运行手册见 `docs/runbooks/demo_evidence.md`、`docs/runbooks/demo_rehearsal.md`，架构决策见 `docs/adr/0023-local-demo-evidence-and-typed-obstacles.md`、`docs/adr/0032-local-defence-rehearsal.md`。

### 尚未实现

以下内容仍为后续开发范围，README 中不把它们描述为已完成能力。部分条目已经有基础模型或内存版骨架，但仍未达到生产级或 V1.0 完整交付状态：

- 正式 YAML / JSON schema 版本治理、兼容迁移和完整字段级校验。
- 场景资产文件依赖、传感器配置和域随机化参数当前已有 API 层基础校验、版本化、基线发布和审计；尚未接入真实资产文件解析、Isaac Lab 深度装载校验和生产级对象存储生命周期策略。
- 面向长任务和异常恢复的生产级 TaskExecutor / 任务执行状态机。
- 可加载真实策略模型的 PolicyRuntime、GaitController 和复杂 LocalPlanner；当前已完成规则版路径跟踪、稳定性恢复控制和障碍规避基础，尚未达到生产级步态控制与真实策略模型加载。
- IsaacLabAdapter 真实运行环境闭环；当前只有契约、映射和适配边界。
- 真实强化学习训练、Isaac Lab 并行训练后端、GPU 资源队列和生产级训练恢复仍待接入；当前 API 层已具备训练任务状态、检查点 URI、完成注册候选策略、标准化评测和 SQLite 持久化证据链。
- MetricCalculator、GateEngine、PolicyRegistryService 已具备基础门禁、审批记录、报告导出与 API 评测报告闭环；生产级外部审批工作流、对象级授权和报告模板治理仍待完善。
- ReplayManifest、KeyFrameIndex、AuditLog、TelemetryFrame、AlertEvent 已有本机回放/审计/事件持久化基础；生产级消息总线、长期归档和高频遥测存储策略仍待完善。
- 生产级身份认证、真实会话、JWT/OIDC、密钥管理、对象级授权和审批工作流；当前已实现应用层 RBAC 与审计门控，但 header 仍只作为本机演示上下文。
- 生产级数据库、对象存储、可靠消息总线和生产级前端应用；当前已有 FastAPI HTTP / WebSocket 服务化入口、本机 Web Console 演示入口、Repository 抽象、SQLite 本机元数据存储、本地不可变对象存储与内存/持久化事件索引。
- 本机展示进程命令通道已经接入 MuJoCo/Webots viewer 模式；当前用于本机答辩演示和调试，生产级实时控制总线仍属于后续开发范围。
- 实体机器人部署与真实机器人闭环验收。

---

## 2. 项目范围

V1.0 聚焦仿真环境内的单机器人、单仿真会话闭环。设计与验收基线平台为 **Isaac Lab**。当前代码阶段仍保持上层平台无关，Isaac Lab 通过适配器契约和后续真实运行环境接入；MuJoCo 当前作为本机物理演示与 smoke test 后端，Webots 当前作为本机可视化演示后端；Gazebo 等平台仍只保留适配扩展边界。Isaac Lab 继续作为设计基线和后续高保真/远程后端，不作为当前本机部署前置条件。

系统目标覆盖：

- 仿真场景、地形、障碍物、检查点、禁行区和传感器配置管理。
- 中文自然语言或模板任务生成 TaskScript，并编排为 TaskGraph。
- AI 辅助的任务语义解析、策略推荐、执行前校验说明和策略选择解释。
- 自主导航、路径跟踪、地形自适应、恢复控制和障碍规避。
- Safety Shield 动作安全约束、急停、Safe-Stand 和人工接管。
- 策略训练、批量实验、标准化评测、模型门禁、发布与回滚。
- 域随机化、强化学习训练和候选策略治理。
- 运行监控、关键事件索引、实验回放、报告导出和审计追踪。
- Simulation Adapter 仿真适配接口，用于隔离上层业务和底层仿真平台。

---

## 3. 不包含内容

V1.0 不实现以下内容：

- 实体四足机器人底层驱动。
- 真实传感器标定。
- 生产级多机器人协同与编队控制。
- 面向公网的开放服务。
- 商业化云平台计费。
- 实体机器人闭环验收。

---

## 4. 架构核心


### 4.0 Scene Profile 与场景资源管理

Python API 层已经增加场景资源管理闭环。场景以 `SceneProfilePayload` 表达 terrain pack、地形/障碍/检查点/禁行区资产、传感器参数和域随机化模板；场景状态包含 `draft`、`published`、`archived`。发布为基线时会对资产引用、传感器采样率、噪声、随机化区间、地形枚举和版本冲突进行校验，生成确定性 checksum，并通过 `scene.lifecycle` 与 `audit.record` 形成可追踪证据。

任务提交和训练计划提交现在会校验 `scene_ref` 是否存在且未归档；控制 handoff 会把任务绑定的场景版本传给本机仿真 runner，避免继续使用硬编码场景版本。默认内置 `minimal_scene:0.1.0` 作为演示与 smoke test 基线。

当前 Scene API：

```text
POST /api/v1/scenes
GET  /api/v1/scenes
GET  /api/v1/scenes/{scene_id}/{scene_version}
POST /api/v1/scenes/{scene_id}/{scene_version}/copy
POST /api/v1/scenes/{scene_id}/{scene_version}/baseline
POST /api/v1/scenes/{scene_id}/{scene_version}/archive
```

### 4.1 Simulation Adapter

上层任务、控制、训练、评测、回放和审计模块通过统一仿真适配接口访问仿真能力。环境初始化、场景加载、环境重置、动作下发、观测采集、机器人状态查询、环境关闭均由适配层承接。

当前接口定义位于：

```text
include/qrics/simulation/simulation_adapter.hpp
```

核心接口包括：

```text
initialize(config)
load_scene(scene_profile)
reset()
step(safe_action)
observe()
robot_state()
close()
```

上层控制链路只向适配器提交 `SafeAction`，不提交未经过 Safety Shield 的 `ActionProposal`。

Python 侧的 `qrics.sim` 进一步提供本机仿真后端抽象。当前默认 `minimal` 后端用于契约和 API Facade 测试；`mujoco` 后端用于本机真实物理 smoke demo；后续 Isaac Lab 后端仍必须遵守同一 Observation / Action 语义。

### 4.2 TaskScript、TaskGraph 与任务理解

`TaskScript` 用于表达任务目标、路径点、约束、场景引用、回退动作和解析器版本。`TaskGraph` 用于表达可执行节点、节点顺序、策略标签、终止节点和回退动作。

当前任务理解链路只输出结构化任务表达、策略选择结果和执行预览，不输出底层关节动作。后续 LLM / VLM / 多模态解析器也必须遵守同一边界：

```text
AI / NLP 输出 -> TaskScript 草稿 -> ConstraintEngine -> PolicySelector -> TaskGraph -> ExecutionPreview
```

不得绕过任务校验、策略状态过滤和 Safety Shield。

### 4.3 Safety Shield

自然语言解析、策略推理、控制器输出和人工指令不能直接下发为底层动作。所有 `ActionProposal` 必须经过 `SafetyShield` 检查，转换为 `SafeAction` 后才能进入仿真步进。

当前 `BasicSafetyShield` 的处理优先级：

1. SafetyLimits 合法性检查。
2. EmergencyStop。
3. ManualControl / manual override。
4. Operator SafeStand。
5. Fallen / Unstable / risk_score 超限。
6. BodyVelocity 裁剪。
7. Stop / SafeStand / Replan 直接接受。
8. JointPosition / JointVelocity 默认拒绝。

### 4.4 Policy Runtime、Policy Registry 与 Gate Engine

当前仓库已经实现策略工件模型、规则策略选择器、基础 `PolicyRuntime` 抽象、规则策略运行时、`GateEngine` 和 `PolicyRegistry` 的内存状态流转。后续需要继续补充：

- PolicyRuntime：加载真实 Released / Baseline 策略模型并生成 ActionProposal。
- PolicyRegistryService：在数据库和对象存储之上管理策略注册、审批、发布、回滚和归档。
- EvaluationHarness：执行标准化评测。
- GateEngine：当前已有基础门禁判断，并已在 API 层绑定评测报告、审批记录、报告导出和审计证据；后续需要接入真实评测后端、资源配额和生产级审批流。

训练生成的候选策略必须经过标准化评测、门禁判断和审批记录后才能进入可执行状态。中间 checkpoint 不应自动替代基线策略。

### 4.5 Replay 与 Audit

当前仓库已经具备 `SafetyEvent`、`ExperimentRun`、`TelemetryFrame`、`AlertEvent`、`ReplayManifest`、`KeyFrameIndex` 和追加式 `AuditLog` 等基础模型与内存实现，但还没有实现生产级持久化回放与审计链路。

后续任务执行、训练、评测、模型状态变更、安全事件和高风险操作都需要关联场景版本、策略版本、配置摘要、指标引用、回放引用和审计记录，以支持实验复现、失败样本定位和模型回滚。

### 4.6 API Facade 与事件流

当前 `python/qrics/api` 同时提供依赖标准库的应用接口 Facade 与可选 FastAPI / WebSocket 传输适配层。Facade 负责稳定 `/api/v1` 族接口的业务边界；HTTP 层只负责请求上下文提取、JSON 转换、错误映射和事件输出，不承载领域规则。生产级鉴权中间件、数据库、对象存储和可靠消息总线仍属于后续开发。

当前 Facade 覆盖：

```text
Scene API     create -> copy -> publish_baseline -> archive -> get/list
Task API      submit -> preview -> confirm -> handoff -> cancel
Control API   status -> override/emergency_stop/safe_stand/resume
Training API  submit training plan
Policy API    register -> attach gate report -> release -> promote baseline
Replay API    query replay manifest / keyframes
Audit API     query audit records
Event Stream  scene.lifecycle / task.lifecycle / control.status / control.alert / training.status / policy.lifecycle / replay.index / audit.record
HTTP API      FastAPI adapter under /api/v1
WebSocket     /api/v1/ws/events?run_id=... 事件快照
```

设计边界：API Facade 不暴露 MuJoCo、Isaac Lab、Webots 等后端内部对象，不下发未建模的底层关节命令；急停、任务取消、策略发布、基线切换等高风险动作必须写入审计。

---

## 5. 技术栈

当前已使用：

- C++20
- CMake 3.24+
- Ninja
- Python 3.11+
- pytest
- ruff / black / mypy 配置
- clang-format / clang-tidy 配置
- GitHub Actions
- Python 标准库 API Facade 与内存事件流
- 可选 FastAPI / WebSocket 服务化入口
- 可选 MuJoCo 本机物理后端

后续接入或扩展：

- Isaac Lab / Isaac Sim
- Python 3.11 Isaac Lab 运行环境
- PyTorch
- CUDA / NVIDIA Driver
- YAML / JSON 配置加载与 schema 治理
- LLM / NLP / 多模态任务解析适配器
- 对象存储、结构化数据库、消息总线、日志与指标系统
- Docker / devcontainer

---

## 6. 仓库结构

```text
Quadruped-Robot-Intelligent-Control-System/
├── README.md
├── CMakeLists.txt
├── CMakePresets.json
├── pyproject.toml
├── .clang-format
├── .clang-tidy
├── .github/
│   └── workflows/
│       └── ci.yml
├── apps/
│   └── qrics_cli.cpp
├── cmake/
│   └── ProjectOptions.cmake
├── configs/
│   ├── policies/
│   │   └── placeholder_policy.yaml
│   ├── scenes/
│   │   └── minimal_scene.yaml
│   ├── sim/
│   │   └── local_mujoco.toml
│   └── training/
│       └── minimal_training.yaml
├── docs/
│   ├── adr/
│   │   ├── 0001-project-skeleton.md
│   │   ├── 0002-safety-shield-and-control-loop.md
│   │   └── ...
│   ├── api/
│   │   ├── events.md
│   │   └── openapi.md
│   └── runbooks/
│       ├── isaac_lab_setup.md
│       └── local_sim_backends.md
├── include/qrics/
│   ├── audit/
│   ├── common/
│   ├── config/
│   ├── control/
│   ├── core/
│   ├── domain/
│   ├── events/
│   ├── experiment/
│   ├── monitoring/
│   ├── replay/
│   ├── safety/
│   ├── scenario/
│   ├── simulation/
│   ├── task/
│   └── training/
├── src/
│   ├── audit/
│   ├── config/
│   ├── control/
│   ├── core/
│   ├── events/
│   ├── monitoring/
│   ├── replay/
│   ├── task/
│   └── training/
├── python/qrics/
│   ├── api/
│   ├── isaac_lab/
│   ├── sim/
│   └── training/
├── scripts/
│   ├── check_all.sh
│   ├── check_local_sim_env.py
│   ├── collect_env.sh
│   └── run_local_sim_demo.py
└── tests/
    ├── cpp/
    └── python/
```

重点目录说明：

| 路径 | 说明 |
|---|---|
| `include/qrics/audit` | 追加式审计日志基础模型 |
| `include/qrics/common` | 通用基础类型和 `Result<T>` |
| `include/qrics/config` | 场景、策略、训练配置加载与错误模型 |
| `include/qrics/control` | 动作建议、安全动作、最小控制闭环、局部规划、任务执行与策略运行时抽象 |
| `include/qrics/safety` | 安全门控接口、基础实现、安全事件、人工接管 |
| `include/qrics/simulation` | 观测模型、机器人状态、仿真适配接口 |
| `include/qrics/scenario` | 场景、传感器、随机化、检查点和禁行区模型 |
| `include/qrics/task` | 任务脚本、任务解析、约束检查、策略选择、任务图、执行预览 |
| `include/qrics/events` | 事件输出接口和内存事件存储 |
| `include/qrics/monitoring` | 遥测帧与告警事件模型 |
| `include/qrics/replay` | 回放清单与关键帧索引 |
| `include/qrics/training` | 策略工件、指标摘要、门禁报告、审批记录和策略注册 |
| `src/task` | 当前任务理解与任务编排基础实现 |
| `python/qrics/api` | 应用 API Facade、场景/任务/控制/训练/策略/回放/审计 route facade、FastAPI / WebSocket transport 和事件流 |
| `python/qrics/isaac_lab` | Isaac Lab 适配契约、动作映射和观测映射 |
| `python/qrics/sim` | 本机仿真后端抽象、Minimal 后端、MuJoCo 后端和 Webots 后端 |
| `docs/api` | HTTP API、API Facade、WebSocket 事件和事件信封契约 |
| `docs/runbooks` | Isaac Lab 和本机仿真运行说明 |
| `tests/cpp` | C++ 单元和集成测试 |
| `configs` | 最小场景、策略、训练配置样例 |
| `docs/adr` | 架构决策记录 |

后续继续补齐或增强的目录：

```text
include/qrics/control/       PolicyRuntime、LocalPlanner、GaitController、RecoveryController、TaskExecutor
include/qrics/monitoring/    TelemetryFrame、AlertEvent、ReplayManifest、KeyFrameIndex、AuditLog
include/qrics/training/      TrainingJob、Checkpoint、MetricReport、GateReport、ApprovalRecord
python/qrics/isaac_lab/      Isaac Lab 真实运行环境接入、环境装载、观测映射、动作映射
python/qrics/training/       训练调度、评测、指标、门禁报告
python/qrics/nlp/            LLM / 多模态任务解析适配器
docs/api/                    REST API HTTP 化、事件契约、错误码、数据 schema
docs/runbooks/               急停、Safe-Stand、训练失败恢复、模型回滚和仿真环境运行手册
```

---

## 7. 本地构建与测试

### 7.1 系统依赖

建议安装：

```bash
sudo apt update
sudo apt install -y \
  build-essential \
  cmake \
  ninja-build \
  clang \
  clang-format \
  clang-tidy \
  ccache \
  python3 \
  python3-venv \
  python-is-python3
```

Python 开发工具：

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip setuptools wheel
python -m pip install -e ".[api,local-sim,dev]"
```

### 7.2 C++ 构建与测试

```bash
cmake --preset dev-gcc-debug
cmake --build --preset dev-gcc-debug
ctest --preset dev-gcc-debug --output-on-failure
```

也可以运行 clang preset：

```bash
cmake --preset dev-clang-debug
cmake --build --preset dev-clang-debug
ctest --preset dev-clang-debug --output-on-failure
```

Release 构建：

```bash
cmake --preset release-gcc
cmake --build --preset release-gcc
```

运行 CLI：

```bash
./build/dev-gcc-debug/qrics_cli
```

预期输出：

```text
QRICS 0.1.0
```

### 7.3 Python 测试与质量检查

```bash
source .venv/bin/activate
pytest
ruff check python tests/python
black --check python tests/python
mypy python tests/python
```

MuJoCo 真实物理后端属于本机仿真扩展依赖，Webots 使用本机外部 `webots` 可执行程序，FastAPI / WebSocket 属于 API 服务化扩展依赖。若只安装 `python -m pip install -e .`，基础 Python 契约测试仍应可运行，但 HTTP 服务测试、本机真实仿真检查和演示会提示安装对应 extra。本阶段建议使用上文的 `python -m pip install -e ".[api,local-sim,dev]"` 作为默认开发安装方式。

本机仿真环境检查：

```bash
python scripts/check_local_sim_env.py
```

本机 MuJoCo 演示：

```bash
python scripts/run_local_sim_demo.py --profile balanced_visual --seconds 15 --viewer
```

无窗口快速检查：

```bash
python scripts/run_local_sim_demo.py --profile headless_fast --seconds 5
```

### 7.4 FastAPI / WebSocket / Web Console 服务运行

安装 API 依赖后可以启动本机 API 服务：

```bash
python scripts/run_api_service.py --host 127.0.0.1 --port 8000
```

开发时可启用自动重载：

```bash
python scripts/run_api_service.py --reload
```

带 Web Console 的本机答辩演示服务：

```bash
python scripts/run_web_console.py --host 127.0.0.1 --port 8000
```

演示前建议先执行就绪检查：

```bash
python scripts/check_demo_readiness.py --format markdown
```

随后执行端到端演练，生成可提交的 JSON / Markdown 证据：

```bash
python scripts/run_demo_rehearsal.py --backend minimal --runtime-profile headless_fast --step-count 12
```

浏览器入口：`http://127.0.0.1:8000/console/`。控制台支持选择 `minimal` / `mujoco` / `webots` 后端、选择 runtime profile、编辑 terrain pack、添加 box / sphere / cylinder 障碍、保存场景、预览仿真、提交中文任务、执行 handoff、急停 / Safe-Stand、查询回放和审计事件。若选择 MuJoCo/Webots 且仿真界面未打开，handoff 会自动打开可视化展示进程并写入任务路径命令；若窗口已打开，同场景运行会复用窗口；急停和 Safe-Stand 会向同一命令目录写入 `stop` / `safe_stand` 命令。若环境缺失，则 API 返回可解释失败结果，不会绕过安全门控。

健康检查：

```bash
curl http://127.0.0.1:8000/api/v1/health
```

典型任务流：

```text
POST /api/v1/tasks
POST /api/v1/tasks/<task_id>/confirm
GET  /api/v1/sim/backends
GET  /api/v1/sim/readiness
POST /api/v1/sim/preview
POST /api/v1/tasks/<task_id>/handoff   # 可带 run_options 选择 minimal/mujoco/webots
POST /api/v1/control/<run_id>/override # emergency_stop / safe_stand 会同步写入展示窗口命令
GET  /api/v1/control/<run_id>
GET  /api/v1/replay/<run_id>
GET  /api/v1/events?run_id=<run_id>
WS   /api/v1/ws/events?run_id=<run_id>
```

WebSocket 端点当前提供真实连接与事件快照：服务端先发送匹配事件，再发送 `snapshot_complete`；客户端发送 `{"op": "close"}` 后关闭连接。它不是生产级增量消息总线，跨进程可靠投递和事件级 RBAC 仍待后续实现。

### 7.5 一键检查

```bash
./scripts/check_all.sh --quick
./scripts/check_all.sh --full
./scripts/check_all.sh --tidy
./scripts/check_all.sh --python-only
./scripts/check_all.sh --local-sim
```

说明：

- `--quick` 会执行 C++ 配置、构建、CTest、pytest、ruff、black、mypy，并以可选方式检查本机 MuJoCo / Webots 仿真环境；本机仿真依赖缺失时不阻断 quick。
- `--full` 会额外尝试 clang debug preset、格式检查、强制本机仿真环境检查和 `headless_fast` smoke demo。
- `--tidy` 会在 full 基础上尝试 clang-tidy。
- 脚本依赖本机已安装对应工具。若未安装 `ruff`、`black`、`mypy` 等 Python 工具，需要先按 7.1 安装。

如果归档包在不同目录解压后出现 CMakeCache 路径不一致，先清理本机构建目录：

```bash
rm -rf build
cmake --preset dev-gcc-debug
```

---

## 8. 当前测试结果说明

在当前压缩包代码上执行过以下检查：

```bash
cmake --preset dev-gcc-debug
cmake --build --preset dev-gcc-debug
ctest --preset dev-gcc-debug --output-on-failure
pytest
```

结果：

```text
CTest: 当前仓库包含版本、领域模型、安全门控、控制闭环、任务理解、配置加载、任务执行、事件、回放、审计、门禁和策略注册等测试目标；以本机实际 CMake 配置输出为准。
pytest: 当前仓库包含版本、API Facade、FastAPI HTTP 服务、WebSocket 事件快照、Isaac Lab 契约、指标聚合、仿真后端契约、MuJoCo 后端契约和 Webots 后端契约测试；以本机实际 pytest 输出为准。
```

若 `./scripts/check_all.sh --quick` 在 `ruff`、`black`、`mypy` 或 MuJoCo / Webots 环境检查处中断，优先确认是否已经按 7.1 安装开发依赖。`--quick` 中本机仿真检查为可选检查；`--full` 与 `--local-sim` 会把本机仿真检查作为必需项。

---

## 9. 环境信息采集

```bash
chmod +x scripts/collect_env.sh
./scripts/collect_env.sh
```

脚本会生成：

```text
reports/env/env_report_YYYYmmdd_HHMMSS.txt
```

脚本只采集环境信息，不安装软件，不修改系统配置。

---

## 10. 提交信息与质量要求

提交信息格式：

```text
<type>: <中文描述>
```

常用类型：

| 类型 | 说明 |
|---|---|
| `feat` | 新增功能 |
| `fix` | 修复缺陷 |
| `docs` | 文档更新 |
| `test` | 测试相关 |
| `refactor` | 重构 |
| `chore` | 工程配置、依赖、脚本等维护工作 |

示例：

```text
feat: 添加任务脚本校验与任务图编排
fix: 修正安全速度阈值判断逻辑
docs: 更新 README 开发路线
test: 添加任务理解流水线单元测试
chore: 调整 CMake 测试目标
```

代码与配置要求：

- C++ 代码使用 C++20。
- Python 代码使用类型标注。
- 领域模型、仿真适配实现和平台私有逻辑分离。
- 配置文件不写入本机绝对路径、密钥、用户名和私有目录。
- 日志不输出 token、密钥、对象存储凭据和模型签名信息。
- 高风险操作需要形成审计记录。
- AI 输出不得绕过 TaskScript 校验、ConstraintEngine、PolicySelector 和 Safety Shield。
- 任务解析器、策略选择器、任务图规划器等能力应优先通过接口抽象接入，避免把规则写死到调用方。

---

## 11. 开发路线

### Phase 0：环境、仓库与工程骨架

状态：已完成主体。

- [x] README 与 `.gitignore`
- [x] 环境信息采集脚本
- [x] CMake / Ninja / C++20 工程骨架
- [x] Python 包骨架
- [x] clang-format / clang-tidy / ruff / black / mypy 配置
- [x] GitHub Actions 初始 CI
- [x] 一键检查脚本

### Phase 1：领域模型与仿真适配接口

状态：已完成主体。

- [x] SceneProfile / SensorProfile / RandomizationProfile / ForbiddenZone / Checkpoint
- [x] TaskScript / TaskConstraint / Waypoint / TaskGraph / TaskNode / TaskEdge
- [x] ObservationPacket / RobotState / TerrainClass / StabilityState
- [x] ActionProposal / SafeAction / SafetyDecision
- [x] SafetyEvent / OverrideCommand
- [x] PolicyArtifact / MetricsDigest / PolicyStage
- [x] ExperimentRun
- [x] SimulationAdapter 抽象接口
- [x] 领域模型统一头文件
- [x] C++ 领域模型测试

### Phase 2：安全门控与最小控制闭环

状态：已完成主体。

- [x] SafetyShield 抽象接口
- [x] BasicSafetyShield 占位实现
- [x] SafetyLimits / SafetyContext / SafetyEvaluation
- [x] BodyVelocity 裁剪
- [x] EmergencyStop、ManualControl、SafeStand、风险状态处理
- [x] 默认阻断 JointPosition / JointVelocity
- [x] ControlLoop::step_once()
- [x] FakeAdapter 集成测试

### Phase 3：任务理解、规则解析与任务图编排

状态：已完成基础闭环。

- [x] TaskParseContext、NamedWaypoint、AvoidZoneAlias
- [x] TaskParser 抽象接口
- [x] RuleBasedChineseTaskParser 中文规则解析器
- [x] ConstraintEngine 抽象接口
- [x] BasicTaskConstraintEngine 约束检查器
- [x] PolicyCandidate、PolicySelection、PolicySelector
- [x] RuleBasedPolicySelector 规则策略选择器
- [x] TaskGraphPlanner 抽象接口
- [x] SequentialTaskGraphPlanner 顺序任务图规划器
- [x] ExplanationService 抽象接口
- [x] BasicExplanationService 执行预览生成器
- [x] TaskUnderstandingPipeline 编排解析、校验、策略选择、任务图和预览
- [x] C++ 任务理解流水线测试
- [x] ADR-0003：任务理解与任务图编排基础实现

当前完成标准：

- 给定中文任务文本和场景上下文，可以生成结构化 TaskScript。
- TaskScript 可被基础规则校验，错误能明确返回。
- 合法 TaskScript 可生成顺序 TaskGraph。
- 每个路径点可得到策略标签。
- 执行预览能说明策略选择和约束校验摘要。
- 所有输出仍停留在任务语义、策略标签和执行预览层，不绕过 Safety Shield。

后续增强：

- 引入正式 TaskValidator，细化错误码与字段级校验。
- 支持中文数字，例如“三秒”。
- 支持更复杂的路径约束、条件分支、失败回退边和任务重规划。
- 支持更细粒度的策略评分、策略注册中心查询和评测摘要排序。
- 引入 LLM / 多模态解析器时，仍输出受 schema 约束的 TaskScript 草案。

### Phase 4：配置加载与资源校验

状态：已完成基础闭环，后续增强 schema 版本治理和更严格资产校验。

目标：让场景、策略、训练和安全配置从样例文件进入可校验数据结构。

建议步骤：

1. 固定 configs schema：scene、sensor、randomization、policy、training、safety。
2. 添加配置加载器，优先支持 YAML 或 JSON。
3. 实现场景检查点、禁行区、传感器配置、随机化参数校验。
4. 实现 PolicyArtifact 配置加载与状态过滤。
5. 实现配置错误码和结构化错误列表。
6. 添加 Python 或 C++ 配置测试。
7. 补充 docs/api 或 docs/schema 中的配置 schema 说明。

完成标准：

- `minimal_scene.yaml`、`placeholder_policy.yaml`、`minimal_training.yaml` 能被加载并校验。
- 缺失场景引用、非法速度、非法随机化区间会被阻断。
- TaskParser / TaskGraphPlanner 可以使用场景检查点和禁行区信息。

### Phase 5：任务执行器与占位策略运行时

状态：已完成基础闭环，后续增强长任务状态机、恢复控制和真实策略模型加载。

目标：在不接 Isaac Lab 的情况下，先跑通：

```text
TaskGraph 节点执行 -> PolicyRuntime -> ActionProposal -> SafetyShield -> SafeAction -> Adapter
```

建议步骤：

1. 添加 PolicyRuntime 抽象接口。
2. 实现 PlaceholderPolicyRuntime，根据 TaskNode 和 RobotState 生成 BodyVelocity ActionProposal。
3. 添加 LocalPlanner 占位接口，负责目标点到速度命令的简单映射。
4. 添加 TaskExecutor，按 TaskGraph 顺序推进任务节点。
5. 添加 ControlRunState / TaskExecutionState。
6. 扩展 FakeAdapter，使其能模拟机器人位置变化、到达路径点、跌倒和急停。
7. 添加任务执行集成测试。

完成标准：

- 不依赖 Isaac Lab，也能完成一个从任务图到安全动作的可重复测试。
- 安全拒绝、人工接管和 SafeStand 能中断或暂停任务执行。
- 控制状态可被后续监控、回放和审计模块消费。

### Phase 6：监控、回放与审计基础模型

状态：已完成基础模型、内存实现、SQLite 持久化、评测报告导出和权限审计；后续增强生产级消息总线、长期归档和高频遥测治理。

目标：把控制闭环产生的状态、安全事件和关键帧变成可追溯证据。

建议步骤：

1. 添加 TelemetryFrame、AlertEvent、ReplaySegment、ReplayManifest、KeyFrameIndex、AuditLog。
2. 添加 EventSink / InMemoryEventStore 占位接口。
3. ControlLoop 和 TaskExecutor 输出状态事件、安全事件和关键帧标记。
4. 实现按 run_id、timestamp、event_type 检索事件。
5. 添加报告摘要 ExperimentReport 占位模型。
6. 添加单元测试和回放索引测试。

完成标准：

- SafetyEvent 能关联 run_id、关键帧和处置动作。
- 任务执行过程可生成可检索事件序列。
- 高风险动作具备追加式审计记录模型。

### Phase 7：Isaac Lab 最小适配

状态：已完成 Python 契约与映射层；真实 Isaac Lab 运行环境闭环仍待开发。

目标：在独立 Python 3.11 / Isaac Lab 环境中接入真实仿真生命周期，但不改变 C++ 上层语义。

建议步骤：

1. 编写 Isaac Lab 环境配置说明，单独管理 Python 3.11 环境。
2. 在 `python/qrics/isaac_lab` 中实现 IsaacLabAdapter 原型。
3. 映射 initialize、load_scene、reset、observe、robot_state、step、close。
4. 实现 ObservationMapper：IMU、接触、位姿、速度、地形、障碍占位映射。
5. 实现 ActionMapper：SafeAction 到 Isaac Lab 动作格式。
6. 添加最小 flat terrain 场景。
7. 添加 smoke test：reset -> observe -> safe body velocity step -> observe。
8. 保持 C++ SimulationAdapter 语义不变；必要时通过 Python 进程桥接或后续绑定层连接。

完成标准：

- Isaac Lab 中能完成最小 reset / step / observe。
- 上层仍只理解 ObservationPacket、RobotState 和 SafeAction。
- 不出现业务模块直接调用 Isaac Lab 私有类的路径。

### Phase 8：控制能力增强与策略运行

状态：待开发。

目标：从占位速度控制进入可用于仿真验证的路径跟踪、地形适配和恢复控制。

建议步骤：

1. 添加路径跟踪控制器接口。
2. 添加地形标签到策略选择映射。
3. 添加 GaitController 抽象接口和占位实现。
4. 添加 RecoveryController，占位处理 Fallen / Unstable。
5. PolicyRuntime 支持加载 Released / Baseline 状态策略。
6. 增加策略置信度、超时、观测缺失降级处理。
7. 对 SafetyShield 增加碰撞风险、禁行区和观测缺失规则。

完成标准：

- 平地路径跟踪可在仿真或 FakeAdapter 中闭环验证。
- 地形标签会影响策略选择。
- 跌倒 / 不稳定时进入 SafeStand 或 Recovery 流程。

### Phase 9：强化学习训练、评测与模型治理

状态：已完成指标、门禁、策略注册基础模型、API 层训练任务状态流转、检查点 URI 记录、训练完成注册候选策略、标准化评测报告、策略 gate 状态更新、策略审批、评测报告导出和 SQLite/对象存储持久化；真实 Isaac Lab 训练后端、GPU 队列和生产级恢复仍待开发。

目标：形成训练、评测、门禁、审批、报告导出、发布、回滚闭环。

建议步骤：

1. 添加 ExperimentPlan / TrainingJob / Checkpoint / MetricReport / GateReport / ApprovalRecord / EvaluationReportExport 数据模型。 `[已完成基础 API schema 与持久化]`
2. 添加 TrainingScheduler 和 TrainerRunner，占位启动训练任务。 `[已完成：API 层 queued/running/succeeded/failed/cancelled 状态机]`
3. 接入 Isaac Lab 并行训练配置。
4. 添加 DomainRandomization 配置使用路径。 `[已完成：训练计划记录 randomization_profile_id；真实注入待 Isaac Lab 后端]`
5. 添加 MetricCalculator：success_rate、collision_rate、tracking_error、recovery_rate、energy_proxy。 `[已完成基础聚合与 API 指标摘要]`
6. 添加 EvaluationHarness，执行固定场景评测。 `[已完成：API 标准化评测报告与门禁阈值判断；真实仿真评测后端待接入]`
7. 添加 GateEngine，根据门限输出 GatePassed / GateFailed。 `[已完成]`
8. 添加 PolicyRegistryService，管理 Candidate、GatePassed、GateFailed、Approved、Released、Baseline、Archived 状态。 `[已完成基础状态流转]`
9. 添加审批、报告导出、发布、回滚、归档审计。 `[已完成 API 审批、报告导出、发布/基线基础审计；生产外部审批流待完善]`
10. 添加训练失败恢复和 checkpoint 检索。 `[已完成检查点 URI 记录；自动恢复待开发]`

完成标准：

- 候选策略不能绕过评测、门禁和审批成为执行策略。
- 门禁报告包含指标、场景、策略版本、配置摘要和结论，并可导出为 JSON / Markdown 证据工件。
- 审批、发布与回滚有状态机和审计记录。

### Phase 10：应用接口、状态推送与控制台

状态：已完成依赖标准库的 API Facade、FastAPI HTTP 服务入口、WebSocket 事件快照、内存事件流、SQLite Repository、本地对象存储、场景资源 API、训练/评测运行态 API、API / 事件契约文档，以及面向本机答辩演示的 Web Console；生产级鉴权、可靠消息总线和生产级前端应用仍待开发。

目标：提供可操作的任务提交、执行预览、监控、回放和模型治理入口。

建议步骤：

1. 设计 `/api/v1` 任务、控制、训练、评测、策略、回放、审计接口。
2. 定义统一请求、响应、错误码和 request_id。
3. 实现 API 服务骨架。 `[已完成：FastAPI adapter]`
4. 实现 WebSocket 或事件推送通道。 `[已完成：WebSocket 事件快照；生产级增量推送待开发]`
5. 实现任务提交、执行预览、确认执行、暂停、恢复、取消、急停接口。
6. 实现训练计划提交、评测报告查询、报告导出、策略审批、策略发布 / 回滚接口。
7. 实现回放关键帧查询和审计检索接口。
8. 补充 Web Console。`[已完成本机演示版：/console/ 静态控制台、场景搭建、仿真后端选择、预览、任务运行、急停、回放和审计查询；生产级前端工程化待完善]`

完成标准：

- 任务操作者能提交任务并看到 TaskScript、TaskGraph、策略理由和风险校验结果。
- 急停和人工接管入口可达。
- 训练、评测、模型治理和回放审计可通过 API 验证。
- HTTP 层可通过 `/api/v1/health`、`/console/`、`/api/v1/sim/backends`、`/api/v1/sim/readiness`、`/api/v1/sim/preview`、任务 handoff、策略审批、报告导出、策略发布、事件查询和 WebSocket 快照测试验证。

### Phase 10.5：本机仿真后端与 API 演示闭环

状态：已完成基础闭环，后续增强更真实的机器人模型、场景资产和可视化演示。

目标：在不依赖 Isaac Lab 的开发机上，使用 Minimal 和 MuJoCo 后端验证 API handoff、控制状态、事件流和回放索引。

已完成：

- [x] `qrics.sim` 通用仿真 schema、后端协议、动作命令和运行档位。
- [x] Minimal 契约后端。
- [x] MuJoCo 本机物理后端基础实现，支持从 typed scene obstacle 重建 MJCF worldbody 障碍对象。
- [x] Webots 本机演示后端基础实现，含 `.wbt` world、supervisor controller、dry-run 契约、typed obstacle 动态导入和演示脚本。
- [x] `scripts/check_local_sim_env.py` 本机环境检查。
- [x] `scripts/run_local_sim_demo.py` 本机演示脚本。
- [x] API handoff 接入 `SimulationRunner`，回填后端、运行档位、控制步数、仿真时间和 base 位置。
- [x] API 事件契约与回放查询契约。
- [x] 场景资产 API 支持 typed geometry，并在 SQLite Repository / HTTP transport / API Facade 间保持字段往返。
- [x] C++ `ReplayManifestWriter` 将 `SafetyEvent` 写入 `ReplayManifest` 关键帧索引，形成安全事件到回放清单的核心链路。

后续增强：

- 使用更贴近四足机器人的 MuJoCo XML / MJCF 资产。
- 将 Webots 演示从 kinematic supervisor 展示升级为带关节控制器与更完整传感器的 Webots PROTO。
- 增加坡面、低摩擦区、碰撞关键帧与更完整的回放导出脚本。
- 将本机 smoke demo 与后续控制台演示脚本联动。

### Phase 11：AI / NLP 与多模态能力增强

状态：已完成本机确定性 NLP 解析器、TaskScript / TaskGraph 预览、解析置信度、场景 catalog 绑定和 AI 安全边界测试；在线 LLM、多模态输入和视觉语言动作协同仍待开发。

目标：在不突破安全边界的前提下增强自然语言、多模态任务理解和策略解释质量。

建议步骤：

1. 在 `python/qrics/nlp` 中添加 TaskParserAdapter。`[已完成：场景 checkpoint / no_go_zone catalog 绑定]`
2. 定义 LLM 输出 JSON schema：intent、goal、waypoints、constraints、fallback、confidence、needs_confirmation。`[已完成本机 TaskScript 草案 schema；在线 LLM schema 待接入]`
3. 所有 LLM 输出先进入 TaskValidator / ConstraintEngine。`[已完成 API 层安全边界拒绝；后续 LLM adapter 继续复用该边界]`
4. 低置信度、缺少路径点、冲突约束时进入人工确认或拒绝执行。`[已完成缺少路径点/低层动作请求拒绝；所有成功解析仍需确认]`
5. 加入 few-shot 示例，覆盖巡检、避障、驻留、返回平台、低摩擦禁行区等句式。`[已完成 prompts/examples 基础文件]`
6. 添加 prompt 版本、parser_version 和原始文本留存。`[已完成 parser_version、source_text、task_script 持久化]`
7. 增加 ExplanationService，将策略选择、约束冲突、安全门控结果转为可展示说明。`[已完成解析说明、策略选择理由和风险摘要输出；复杂解释待增强]`
8. 预留图像、场景标签、地图标注等多模态输入入口。`[待开发]`
9. 增加 AI 输出安全测试：禁止输出 JointPosition、禁止绕过 Safety Shield、禁止执行未知场景点。`[已完成 tests/python/test_ai_safety_boundaries.py]`

完成标准：

- 中文自然语言任务可以稳定转换为 TaskScript 草案。`[本机规则解析已完成]`
- AI 输出受 schema、校验器、约束引擎和安全门控约束。`[本机规则解析与低层动作拒绝已完成]`
- 控制台能够展示“为何选择该策略”和“为何拒绝执行”。`[已展示 parser version、confidence、constraints、fallback、explanation 和 rejection_reason]`

### Phase 12：工程化、运行手册与验收整理

状态：待开发。

目标：把系统整理为可演示、可测试、可审计、可复现的毕业设计交付状态。

建议步骤：

1. 完善 CI：C++、Python、格式、静态检查、核心测试。
2. 增加 Docker / devcontainer 或远程 GPU 运行说明。
3. 增加 docs/runbooks：急停、SafeStand、训练失败恢复、模型回滚。
4. 增加验收场景脚本：复杂地形、自主通行、自然语言任务、训练门禁、回放审计。`[已补充本机答辩端到端演练脚本，覆盖 typed 场景、任务运行、安全接管、回放审计和轻量训练门禁；复杂高保真训练场景继续增强]`
5. 增加 traceability matrix：FR/NFR -> 代码模块 -> 测试 -> 演示证据。
6. 增加最终报告所需截图、日志、评测报告和回放片段索引。

完成标准：

- 系统可从文档按步骤构建、测试和演示。
- 关键需求均有代码落点、测试落点和验收证据。
- README、步骤文件、ADR、API 文档和运行手册保持一致。

---

## 12. 许可证

当前未声明许可证。公开发布前需要补充 `LICENSE` 文件。

---

## 13. 仓库地址

```text
https://github.com/lanse69/Quadruped-Robot-Intelligent-Control-System
```