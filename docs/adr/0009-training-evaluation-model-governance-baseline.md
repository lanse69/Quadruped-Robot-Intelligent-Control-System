# ADR-0009: 训练评测与模型治理基础

## 状态

Accepted

## 背景

当前仓库已经具备任务理解、任务执行、安全门控、监控回放审计和 Python 侧 Isaac Lab Adapter 契约。真实 Isaac Lab 后端仍不应成为默认测试和本机答辩的阻塞项。系统需要先把策略评测指标、门禁结论、策略注册、发布、基线切换、回滚、归档和审计链路固化为平台无关模型。

## 决策

新增训练评测与模型治理基础对象：

- `MetricReport`：承载一次评测运行产生的指标摘要、策略引用、场景引用和评测套件编号。
- `GateReport`：承载门禁阈值、门禁结论、失败规则和评测证据引用。
- `ApprovalRecord`：承载模型发布、基线提升、回滚和归档审批记录。
- `BasicGateEngine`：基于确定性阈值判断候选策略是否通过门禁。
- `InMemoryPolicyRegistry`：提供候选注册、门禁报告绑定、发布、提升基线、回滚基线、归档和查询。
- Python `metric_calculator`：把轻量评测 episode 摘要聚合为与 C++ `MetricsDigest` 同构的指标摘要。

高风险模型治理操作接入既有 `AuditLogStore`。发布、回滚和归档必须带原因，否则审计层会拒绝写入。

## 不做内容

本阶段不启动真实训练，不安装 Isaac Lab，不接真实评测环境，不实现数据库、对象存储、API、WebSocket、RBAC 和异步任务队列，不加载真实模型文件。

## 后果

后续真实 Isaac Lab、训练调度器和评测服务接入后，可以直接复用 `MetricReport -> GateReport -> PolicyRegistry -> AuditLog` 证据链。答辩阶段也可以展示候选策略必须通过门禁才能发布、发布后才能提升为 Baseline、Baseline 不可直接归档、回滚会写审计的完整治理闭环。