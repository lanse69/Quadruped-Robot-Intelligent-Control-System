# QRICS 持久化运行手册

## 1. 运行态目录

默认运行态目录：

```text
runtime/qrics-api/
  qrics.sqlite3
  qrics.sqlite3-wal
  qrics.sqlite3-shm
  object_store/
    replay_manifest/
```

这些文件属于本机运行证据，不进入 Git 提交。

## 2. 启动 API 服务

```bash
python scripts/run_api_service.py --host 127.0.0.1 --port 8000 --state-dir runtime/qrics-api
```

## 3. 验证持久化

1. 启动服务并执行任务提交、确认、handoff。
2. 查询 `GET /api/v1/replay/<run_id>`，确认返回 `manifest_uri` 和 `manifest_checksum`。
3. 停止服务。
4. 重新启动服务，使用同一个 `--state-dir`。
5. 再次查询 `GET /api/v1/replay/<run_id>`、`GET /api/v1/events?run_id=<run_id>` 和 `GET /api/v1/audit`。

## 4. 清理运行态数据

仅在确认不再需要本地演示证据时执行：

```bash
rm -rf runtime/qrics-api
```

不要在测试失败时直接删除运行证据；先复制相关 sqlite 和 object_store 供问题定位。

## 5. 约束

- SQLite 只作为本机开发和演示持久化，不是生产级数据库。
- `object_store` 中的 JSON 工件以 checksum 识别，不允许原地覆盖。
- 审计记录追加写入，不提供物理删除 API。
- 高频传感器原始流不在本阶段长期保存。