# QRICS API 服务运行手册

## 1. 安装 API 依赖

```bash
python -m pip install -e '.[api,dev]'
```

如需同时运行 MuJoCo 本机后端：

```bash
python -m pip install -e '.[all]'
```

## 2. 启动服务

```bash
python scripts/run_api_service.py --host 127.0.0.1 --port 8000
```

开发时可使用：

```bash
python scripts/run_api_service.py --reload
```

## 3. 健康检查

```bash
curl http://127.0.0.1:8000/api/v1/health
```

## 4. 任务演示

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/tasks \
  -H 'content-type: application/json' \
  -H 'x-request-id: req-demo-1' \
  -H 'x-actor-id: operator-1' \
  -H 'x-actor-role: operator' \
  -d '{"source_text":"避开低摩擦区，先巡检A，再巡检B，最后回到平台待命"}'
```

随后调用：

```text
POST /api/v1/tasks/<task_id>/confirm
POST /api/v1/tasks/<task_id>/handoff
GET  /api/v1/control/<run_id>
GET  /api/v1/replay/<run_id>
GET  /api/v1/events?run_id=<run_id>
```

## 5. WebSocket 事件快照

连接：

```text
ws://127.0.0.1:8000/api/v1/ws/events?run_id=<run_id>
```

服务端会先输出当前事件快照，再输出 `snapshot_complete`。客户端发送 `{"op":"close"}` 后关闭。

## 6. 约束

- HTTP 层不承载领域规则。
- 所有高风险动作必须通过 `RequestContext` 写入审计或事件。
- 当前 WebSocket 是事件快照，不是生产级消息总线。
- 当前数据仍为进程内内存状态，重启后清空；下一阶段应接 repository 和持久化存储。

## Webots 本机演示

API handoff 的 `LocalSimulationRunner` 已支持 `backend="webots"`。直接演示可执行：

```bash
python scripts/run_webots_demo.py --dry-run --seconds 3
python scripts/run_webots_demo.py --profile webots_fast --seconds 12
```

Webots 运行细节见 `docs/runbooks/webots_local_backend.md`。