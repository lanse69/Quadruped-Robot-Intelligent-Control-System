# ADR 0018：策略审批与评测报告导出

## 状态

Accepted

## 背景

训练评测运行态已经可以提交训练计划、注册候选策略、执行标准化评测并根据门禁阈值更新策略 gate 状态。但模型治理闭环仍缺少两类证据：

1. 门禁通过后的人工或角色化审批记录。
2. 可归档的评测报告导出工件。

如果策略发布只依赖 `gate_passed` 状态，会导致“指标通过”和“发布批准”混在同一个状态里，无法满足发布追责、回滚复盘和验收报告归档要求。

## 决策

在 API 层引入独立的策略审批与报告导出机制：

- 新增 `PolicyApprovalPayload` / `PolicyApprovalResponse`，审批结论为 `approved` 或 `rejected`。
- 新增 `EvaluationReportExportPayload` / `EvaluationReportExportResponse`，导出格式为 `json` 或 `markdown`。
- `policy.approve` 作为高风险操作，必须具备权限并提供非空 `reason`。
- `evaluation.export` 作为受控操作，要求具备 `evaluation.export` 权限，并写入审计与 `report.export` 事件。
- `release_policy` 不再只接受 `gate_passed`；发布前必须同时满足：
  1. 目标策略已有 passed 门禁证据；
  2. 最新审批记录为 `approved`；
  3. 当前策略阶段处于 `approved`、`released` 或 `baseline`。
- SQLite 仓储持久化 `policy_approvals` 与 `evaluation_report_exports`，并在配置 `FileObjectStore` 时把导出内容写入本地不可变对象存储。

## 后果

正向影响：

- 模型治理链路从“训练 -> 评测 -> 门禁 -> 发布”扩展为“训练 -> 评测 -> 门禁 -> 审批 -> 报告导出 -> 发布”。
- 发布拒绝原因更明确：门禁未通过、缺少审批或阶段不允许会分别产生 `result=rejected` 审计记录。
- 报告导出工件具备 URI、checksum 和 size，可用于答辩、验收、归档和回放证据串联。
- 内存仓储和 SQLite 仓储保持同一接口语义，测试可覆盖无对象存储和本地对象存储两种模式。

代价与约束：

- 生产级外部审批流、签名验真、对象级授权和报告模板治理仍需后续实现。
- 当前审批上下文来自应用层 `RequestContext`，不是生产级身份认证。
- 报告导出内容只包含当前 API 层已有的指标、门禁、审批和引用信息；真实 Isaac Lab 失败样本详情仍依赖后续仿真评测后端接入。

## 验证

- Python API facade、HTTP、RBAC 和训练评测运行态测试覆盖审批、导出、发布前置条件和 SQLite 持久化。
- `python -m compileall -q python tests/python scripts` 验证 Python 语法。
- C++ CTest 回归验证未破坏既有领域模型、控制、安全、任务、事件、回放、审计、门禁和策略注册测试。