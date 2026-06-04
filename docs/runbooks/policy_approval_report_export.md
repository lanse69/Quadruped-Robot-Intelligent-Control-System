# QRICS 策略审批与评测报告导出运行手册

## 1. 适用范围

本手册覆盖本机 API 层的策略审批、评测报告导出和发布前证据校验。它用于把标准化评测结果转化为可追溯的模型治理证据；当前实现不代表已经接入生产级身份认证、电子签名或外部审批系统。

## 2. 前置条件

发布策略前应先完成以下链路：

1. 注册候选策略或由训练完成自动注册候选策略。
2. 执行标准化评测并生成 `passed` 门禁报告。
3. 对该评测报告执行策略审批，结论为 `approved`。
4. 导出评测报告作为评审或验收证据。
5. 执行发布接口。

## 3. 权限

| 操作 | 权限 | 推荐角色 |
|---|---|---|
| 运行评测 | `evaluation.run` | `algorithm_engineer` |
| 导出评测报告 | `evaluation.export` | `algorithm_engineer` / `test_engineer` / `auditor` |
| 审批策略 | `policy.approve` | `algorithm_engineer` / `admin` |
| 读取审批记录 | `policy.approval.read` | `algorithm_engineer` / `auditor` / `admin` |
| 发布策略 | `policy.release` | `algorithm_engineer` / `admin` |

## 4. 审批策略

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/policies/demo_nav/1.0.0/approval \
  -H 'content-type: application/json' \
  -H 'x-request-id: req-approval-demo' \
  -H 'x-actor-id: algo-1' \
  -H 'x-actor-role: algorithm_engineer' \
  -d '{
    "evaluation_id": "eval-demo-nav-1",
    "decision": "approved",
    "reason": "标准化评测通过，批准进入发布候选"
  }'
```

关键规则：

- `reason` 必须非空。
- `decision` 只能是 `approved` 或 `rejected`。
- 审批引用的评测报告必须属于 URL 中的目标策略。
- `approved` 只能用于 `passed` 评测报告。
- 审批通过后策略阶段进入 `approved`。

查询审批记录：

```bash
curl -s http://127.0.0.1:8000/api/v1/policies/demo_nav/1.0.0/approvals \
  -H 'x-request-id: req-approval-list' \
  -H 'x-actor-id: auditor-1' \
  -H 'x-actor-role: auditor'
```

## 5. 导出评测报告

导出 Markdown：

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/evaluations/eval-demo-nav-1/exports \
  -H 'content-type: application/json' \
  -H 'x-request-id: req-export-md' \
  -H 'x-actor-id: algo-1' \
  -H 'x-actor-role: algorithm_engineer' \
  -d '{"format":"markdown","reason":"形成评审附件"}'
```

导出 JSON：

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/evaluations/eval-demo-nav-1/exports \
  -H 'content-type: application/json' \
  -H 'x-request-id: req-export-json' \
  -H 'x-actor-id: algo-1' \
  -H 'x-actor-role: algorithm_engineer' \
  -d '{"format":"json","reason":"形成机器可读证据"}'
```

响应中的关键字段：

| 字段 | 含义 |
|---|---|
| `export_id` | 导出记录 ID。 |
| `uri` | 导出工件 URI。配置 `FileObjectStore` 时为本地对象存储 URI；否则为 `sqlite://evaluation_report/<export_id>`。 |
| `checksum` | 导出内容 SHA-256 摘要。 |
| `size_bytes` | 导出内容大小。 |
| `summary` | 评测套件、门禁结论和策略引用摘要。 |

查询某次评测的导出记录：

```bash
curl -s http://127.0.0.1:8000/api/v1/evaluations/eval-demo-nav-1/exports \
  -H 'x-request-id: req-export-list' \
  -H 'x-actor-id: auditor-1' \
  -H 'x-actor-role: auditor'
```

## 6. 发布策略

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/policies/demo_nav/1.0.0/release \
  -H 'content-type: application/json' \
  -H 'x-request-id: req-release-demo' \
  -H 'x-actor-id: algo-1' \
  -H 'x-actor-role: algorithm_engineer' \
  -d '{"reason":"标准化评测和审批均通过，发布为可执行策略"}'
```

发布前置条件：

- 策略存在。
- 至少一个门禁报告为 `passed`。
- 最新审批记录为 `approved`。
- 策略阶段为 `approved`、`released` 或 `baseline`。

不满足前置条件时，接口返回 `409 STATE_CONFLICT` 并写入 `result=rejected` 审计记录。

## 7. 验证命令

```bash
python -m pytest tests/python/test_api_facade.py tests/python/test_api_security.py tests/python/test_http_api.py tests/python/test_http_security.py tests/python/test_training_evaluation_runtime.py
```

持久化验证应使用 `SQLiteQricsRepository` + `FileObjectStore`，确认：

- `policy_approvals` 可跨仓储重启读取。
- `evaluation_report_exports` 可跨仓储重启读取。
- 导出文件存在且 checksum 非空。
- 缺少审批时发布被拒绝。