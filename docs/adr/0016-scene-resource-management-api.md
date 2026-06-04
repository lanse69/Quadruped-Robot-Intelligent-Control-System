# ADR 0016：场景资源管理 API 与持久化边界

## 状态

已接受。

## 背景

需求基线将场景与资产管理定义为 P0 能力，并要求场景模板、地形或障碍资产、传感器参数、域随机化模板能够在训练与回归测试中复用。软件设计说明书将该能力域拆分到 Scene Service、Asset Validator、Sensor Profile Manager、Randomization Template Service 和 Scene Version Manager 等构件中。

此前的应用 API 已经暴露任务、控制、训练、策略、回放、审计、事件、RBAC、SQLite 元数据和本地对象存储能力。但任务与训练请求仍可能依赖隐式场景引用，而不是依赖已持久化、已版本化、可审计的场景配置档案。这会导致当前实现与场景基线需求之间存在缺口。

## 决策

将场景资源管理作为下一阶段交付内容，落地到 Python API Facade 和 HTTP 传输层。

场景 API 引入以下内容：

- `SceneProfilePayload`、`SceneAssetPayload`、`SensorProfilePayload` 和 `RandomizationProfilePayload`，作为面向 API 的场景 schema。
- 场景状态值：`draft`、`published` 和 `archived`。
- 场景资产类型：地形、障碍物、检查点、禁行区、传感器和元数据资产。
- `QricsRepository` 场景持久化方法，以及 SQLite `scenes` 存储表。
- `scene.read`、`scene.write`、`scene.publish_baseline` 和 `scene.archive` 权限。
- 将 `scene.publish_baseline` 和 `scene.archive` 定义为必须填写原因的高风险操作。
- `scene.lifecycle` 事件，用于记录创建、复制、发布和归档状态迁移。
- 任务与训练请求的 `scene_ref` 仓储校验。
- 本地演示与冒烟测试使用的默认基线种子：`minimal_scene:0.1.0`。

HTTP 层暴露以下接口：

```text
POST /api/v1/scenes
GET  /api/v1/scenes
GET  /api/v1/scenes/{scene_id}/{scene_version}
POST /api/v1/scenes/{scene_id}/{scene_version}/copy
POST /api/v1/scenes/{scene_id}/{scene_version}/baseline
POST /api/v1/scenes/{scene_id}/{scene_version}/archive
```

## 影响

正向影响：

- 任务与训练请求不再接受未注册或已归档的场景版本。
- 场景生命周期迁移具备审计记录，并可通过事件流观察。
- SQLite 持久化能够在 API 重启后保留场景版本、校验和、基线状态和校验状态。
- 当前实现为 FR-01、FR-02、FR-03 和 FR-10 提供了直接的应用边界。

限制：

- 资产 URI 校验仍处于 API 层。当前能够检测空 URI、重复资产和显式 `missing:` 引用，但尚未检查真实 Isaac Lab 资产或对象存储清单。
- 传感器校验覆盖启用标志、采样率、噪声和观测来源元数据，但尚未连接实时仿真器传感器图。
- 域随机化校验覆盖参数范围和 seed 元数据，但尚未在 Isaac Lab 内部真正注入扰动。

## 验证

本阶段新增以下测试：

- 内存仓储下的场景生命周期与 RBAC 边界测试。
- HTTP 场景管理流程与角色限制测试。
- SQLite 场景持久化与重启后重新打开测试。
- 当 `scene_ref` 缺失或已归档时，任务与训练请求应被拒绝。
- 当资产与随机化配置无效时，基线发布应被拒绝。