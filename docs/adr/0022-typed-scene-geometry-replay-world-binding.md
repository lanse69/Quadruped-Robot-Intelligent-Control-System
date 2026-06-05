# ADR-0022：Typed Scene Geometry、回放清单写入器与本机世界障碍绑定

## 状态

Accepted

## 背景

前一阶段已经将本机观测映射、安全证据、MuJoCo / Webots 后端契约和 API handoff 串联起来，但场景障碍仍主要依赖 URI / checksum 形式的资产占位。该方式可以满足场景资源登记，却不足以在本机 MuJoCo / Webots 演示中直接把障碍物实例化到仿真世界，也不利于把碰撞、避障和安全事件回放与场景几何建立一致证据链。

本阶段需要在不依赖 Isaac Lab 的开发机上继续推进演示闭环：场景 API 能描述可执行几何障碍，MuJoCo / Webots 能消费同一份 typed obstacle 数据，C++ 核心能把安全事件稳定写入回放清单。

## 决策

1. 在 Python API 层为 `SceneAssetPayload` 增加 typed geometry 字段：`geometry_type`、`position`、`size`、`radius_m`、`height_m`。
2. `geometry_type` 采用受限枚举：`none`、`sphere`、`box`、`cylinder`。缺省为 `none`，保持旧 URI / checksum 资产兼容。
3. 带 typed geometry 的 obstacle 资产允许不提供外部 URI；API 校验改为优先验证几何参数、尺寸和半径/高度。
4. `SQLiteQricsRepository`、FastAPI HTTP transport 和 API Facade 全部持久化并往返 typed geometry 字段。
5. MuJoCo 后端在加载场景时根据 typed obstacle 重建 MJCF worldbody 障碍对象，使障碍物进入实际 MuJoCo model。
6. Webots 后端把 typed obstacle 写入运行 spec，Supervisor controller 在 world root 下动态导入 `Solid { children [ Shape { geometry Cylinder ... } ] }` 节点。
7. 在 C++ 核心增加 `ReplayManifestWriter`，将 `SafetyEvent` 转换为 `KeyFrameIndexEntry` 并写入 `ReplayManifest`，再序列化为稳定 JSON 文本。

## 结果

- API 场景资源不再只是文件资产登记，也可以直接表达本机演示可执行的障碍几何。
- MuJoCo 和 Webots 后端共享同一 typed obstacle 输入，减少演示路径分叉。
- 回放清单写入进入 C++ 核心库，安全事件、关键帧和回放 Manifest 的证据链更接近需求与设计文档中的 Replay / Audit 边界。
- 旧的 URI / checksum 资产仍然可用；只有设置了 `geometry_type != none` 的 obstacle 资产才触发内联几何校验和本机世界绑定。

## 边界

- 当前仅绑定基础圆柱障碍。`sphere` / `box` 字段已进入 API schema 和持久化链路，后续可继续扩展到 Webots / MuJoCo 的完整几何实例化。
- Webots 动态导入依赖 Supervisor 控制器能力；dry-run 环境仅验证 spec 写入与命令构造，不启动外部 Webots。
- MuJoCo 真实后端测试在未安装 `mujoco` Python 包时跳过，不阻断基础质量门禁。