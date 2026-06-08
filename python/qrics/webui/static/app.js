const headers = (role = "operator") => ({
  "content-type": "application/json",
  "x-request-id": `web-${Date.now()}`,
  "x-actor-id": "web-console",
  "x-actor-role": role,
});

const WORLD_SCALE = 185;
const WORLD_ORIGIN = { x: 98, y: 245 };
const ROBOT_BODY = { length: 0.56, width: 0.26 };
const PLATFORM_SIZE = { width: 0.86, height: 0.62 };
const CHECKPOINT_RADIUS = 0.135;
const DEFAULT_SCENE_NAME = "本机场景";
const DEFAULT_SCENE_REF = { id: "local", version: "1" };

const defaultTerrainRegions = () => ({
  slope: { id: "slope", label: "坡面", x: 1.55, y: 0.54, width: 1.30, height: 0.60 },
  gravel: { id: "gravel", label: "碎石", x: 1.50, y: -0.19, width: 1.40, height: 0.65 },
  stairs: { id: "stairs", label: "台阶", x: 1.42, y: -0.38, width: 1.15, height: 0.62 },
});

const state = {
  sceneRef: { ...DEFAULT_SCENE_REF },
  sceneName: DEFAULT_SCENE_NAME,
  runId: "",
  obstacles: [],
  checkpoints: {},
  noGoZones: [],
  terrainRegions: defaultTerrainRegions(),
  drag: null,
  lastStatus: null,
  lastSceneSignature: "",
  savedScenes: [],
  animationFrame: 0,
  animationToken: 0,
};

const $ = (id) => document.getElementById(id);

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function shortHash(value) {
  let hash = 2166136261;
  for (const char of String(value || DEFAULT_SCENE_NAME)) {
    hash ^= char.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(36);
}

function sceneIdFromName(name) {
  const ascii = String(name || DEFAULT_SCENE_NAME)
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 36);
  return ascii || `scene_${shortHash(name)}`;
}

function normalizeName(value, fallback) {
  const text = String(value || "").trim();
  return text || fallback;
}

function setSceneName(name, { resetRef = false } = {}) {
  state.sceneName = normalizeName(name, DEFAULT_SCENE_NAME);
  $("sceneNameInput").value = state.sceneName;
  if (resetRef) {
    state.sceneRef = { id: sceneIdFromName(state.sceneName), version: "1" };
  }
  updateSceneRefLabel();
}

function updateSceneRefLabel(statusText = "未保存") {
  $("sceneRefLabel").textContent = `${state.sceneName}（${statusText}）`;
}

function obstacleTemplate(type) {
  const index = state.obstacles.length + 1;
  const names = { box: "箱体", cylinder: "圆柱", sphere: "球体" };
  return {
    id: `${names[type] || "障碍物"}${index}`,
    type,
    x: Number((0.55 + index * 0.22).toFixed(2)),
    y: index % 2 === 0 ? -0.25 : 0.22,
    z: type === "sphere" ? 0.18 : 0.2,
    size: type === "box" ? 0.32 : 0.16,
    height: type === "cylinder" ? 0.38 : 0.30,
  };
}

function checkpointTemplate() {
  const index = Object.keys(state.checkpoints).length + 1;
  const id = `C${index}`;
  return { id, label: `检查点${index}`, x: 0.65 + index * 0.28, y: index % 2 === 0 ? 0.52 : -0.48 };
}

function noGoZoneTemplate() {
  const index = state.noGoZones.length + 1;
  return { id: `限制区${index}`, label: `限制区${index}`, x: 2.15 + index * 0.15, y: index % 2 === 0 ? 0.35 : -0.35, width: 0.75, height: 0.55 };
}

function resetDefaultScene() {
  state.sceneRef = { ...DEFAULT_SCENE_REF };
  setSceneName(DEFAULT_SCENE_NAME);
  state.terrainRegions = defaultTerrainRegions();
  state.checkpoints = {
    platform: { id: "platform", label: "平台", x: 0.0, y: 0.0 },
    A: { id: "A", label: "A", x: 0.90, y: 0.34 },
    B: { id: "B", label: "B", x: 1.85, y: -0.30 },
  };
  state.noGoZones = [
    { id: "低摩擦区", label: "低摩擦区", x: 2.45, y: 0.0, width: 1.15, height: 1.65 },
  ];
  state.obstacles = [
    { id: "箱体", type: "box", x: 1.12, y: 0.68, z: 0.15, size: 0.32, height: 0.30 },
    { id: "圆柱", type: "cylinder", x: 1.48, y: -0.62, z: 0.18, size: 0.14, height: 0.36 },
    { id: "球体", type: "sphere", x: 2.20, y: 0.50, z: 0.16, size: 0.16, height: 0.16 },
  ];
  renderSceneEditors();
  drawScene();
}

function renderSceneEditors() {
  renderCheckpointList();
  renderNoGoZoneList();
  renderObstacleList();
}

function renderCheckpointList() {
  const root = $("checkpointList");
  root.innerHTML = "";
  Object.entries(state.checkpoints).forEach(([key, marker]) => {
    const locked = key === "platform" ? "disabled" : "";
    const card = document.createElement("div");
    card.className = "object-card checkpoint-card";
    card.dataset.kind = "checkpoint";
    card.dataset.key = key;
    card.innerHTML = `
      <div class="object-card-title">
        <label>名称<input data-field="label" value="${escapeHtml(marker.label || marker.id)}" /></label>
        <button data-action="remove" ${locked}>删除</button>
      </div>
      <div class="object-card-grid">
        <label>X 坐标<input data-field="x" type="number" step="0.05" value="${marker.x}" /></label>
        <label>Y 坐标<input data-field="y" type="number" step="0.05" value="${marker.y}" /></label>
      </div>`;
    card.querySelectorAll("input").forEach((input) => {
      input.addEventListener("input", () => {
        const field = input.dataset.field;
        const current = state.checkpoints[key];
        if (!current || !field) return;
        if (field === "label") {
          current.label = normalizeName(input.value, current.id);
          if (key !== "platform") current.id = current.label;
        } else {
          current[field] = Number(input.value);
        }
        drawScene(state.lastStatus);
      });
    });
    card.querySelector("button").addEventListener("click", () => {
      if (key === "platform") return;
      delete state.checkpoints[key];
      renderCheckpointList();
      drawScene(state.lastStatus);
    });
    root.appendChild(card);
  });
}

function renderNoGoZoneList() {
  const root = $("noGoZoneList");
  root.innerHTML = "";
  state.noGoZones.forEach((zone, index) => {
    const card = document.createElement("div");
    card.className = "object-card zone-card";
    card.dataset.kind = "no_go_zone";
    card.dataset.index = String(index);
    card.innerHTML = `
      <div class="object-card-title">
        <label>名称<input data-field="label" value="${escapeHtml(zone.label || zone.id)}" /></label>
        <button data-action="remove">删除</button>
      </div>
      <div class="object-card-grid">
        <label>X 坐标<input data-field="x" type="number" step="0.05" value="${zone.x}" /></label>
        <label>Y 坐标<input data-field="y" type="number" step="0.05" value="${zone.y}" /></label>
        <label>宽度<input data-field="width" type="number" min="0.05" step="0.05" value="${zone.width}" /></label>
        <label>高度<input data-field="height" type="number" min="0.05" step="0.05" value="${zone.height}" /></label>
      </div>`;
    card.querySelectorAll("input").forEach((input) => {
      input.addEventListener("input", () => {
        const field = input.dataset.field;
        if (!field) return;
        if (field === "label") {
          const name = normalizeName(input.value, `限制区${index + 1}`);
          state.noGoZones[index].label = name;
          state.noGoZones[index].id = name;
        } else {
          state.noGoZones[index][field] = Number(input.value);
        }
        drawScene(state.lastStatus);
      });
    });
    card.querySelector("button").addEventListener("click", () => {
      state.noGoZones.splice(index, 1);
      renderNoGoZoneList();
      drawScene(state.lastStatus);
    });
    root.appendChild(card);
  });
}

function renderObstacleList() {
  const root = $("obstacleList");
  root.innerHTML = "";
  state.obstacles.forEach((obstacle, index) => {
    const card = document.createElement("div");
    card.className = "object-card obstacle-card";
    card.dataset.kind = "obstacle";
    card.dataset.index = String(index);
    card.innerHTML = `
      <div class="object-card-title">
        <label>名称<input data-field="id" value="${escapeHtml(obstacle.id)}" /></label>
        <button data-action="remove">删除</button>
      </div>
      <div class="object-card-grid">
        <label>形状<select data-field="type">
          <option value="box">箱体</option><option value="cylinder">圆柱</option><option value="sphere">球体</option>
        </select></label>
        <label>X 坐标<input data-field="x" type="number" step="0.05" value="${obstacle.x}" /></label>
        <label>Y 坐标<input data-field="y" type="number" step="0.05" value="${obstacle.y}" /></label>
        <label>Z 高度<input data-field="z" type="number" step="0.05" value="${obstacle.z}" /></label>
        <label>尺寸<input data-field="size" type="number" min="0.01" step="0.01" value="${obstacle.size}" /></label>
        <label>物体高度<input data-field="height" type="number" min="0.01" step="0.01" value="${obstacle.height}" /></label>
      </div>`;
    card.querySelector("select").value = obstacle.type;
    card.querySelectorAll("input, select").forEach((input) => {
      input.addEventListener("input", () => {
        const field = input.dataset.field;
        if (!field) return;
        state.obstacles[index][field] = ["x", "y", "z", "size", "height"].includes(field)
          ? Number(input.value)
          : normalizeName(input.value, `障碍物${index + 1}`);
        drawScene(state.lastStatus);
      });
    });
    card.querySelector("button").addEventListener("click", () => {
      state.obstacles.splice(index, 1);
      renderObstacleList();
      drawScene(state.lastStatus);
    });
    root.appendChild(card);
  });
}

function activeTerrainKeys(terrain = $("terrainSelect").value) {
  if (terrain === "mixed_terrain_pack" || terrain === "mixed") return ["slope", "gravel", "stairs"];
  if (["slope", "gravel", "stairs"].includes(terrain)) return [terrain];
  return [];
}

function terrainRegionAssets(terrain) {
  return activeTerrainKeys(terrain).map((key) => {
    const region = state.terrainRegions[key] || defaultTerrainRegions()[key];
    return {
      asset_id: `terrain_${key}_region`,
      asset_type: "terrain",
      geometry_type: "box",
      uri: `builtin://qrics/terrain-region/${key}`,
      checksum: `inline-terrain-${key}-${region.x}-${region.y}-${region.width}-${region.height}`,
      required: false,
      position: [Number(region.x), Number(region.y), 0.0],
      terrain_class: key,
      size: [Math.max(0.05, Number(region.width)), Math.max(0.05, Number(region.height)), terrainVisualThickness(key)],
    };
  });
}

function terrainVisualThickness(key) {
  return { slope: 0.07, gravel: 0.05, stairs: 0.20 }[key] || 0.03;
}

function scenePayload() {
  const terrain = $("terrainSelect").value;
  const sceneName = normalizeName($("sceneNameInput").value, DEFAULT_SCENE_NAME);
  state.sceneName = sceneName;
  const sceneId = state.sceneRef.id || sceneIdFromName(sceneName);
  const sceneVersion = state.sceneRef.version || "1";
  const assets = [
    {
      asset_id: `${terrain}_terrain_base`,
      asset_type: "terrain",
      uri: `builtin://qrics/terrain/${terrain}`,
      checksum: `builtin-${terrain}`,
    },
    ...terrainRegionAssets(terrain),
    ...Object.values(state.checkpoints).map((checkpoint) => ({
      asset_id: checkpoint.id,
      asset_type: "checkpoint",
      uri: `builtin://qrics/checkpoint/${checkpoint.id}`,
      checksum: `inline-checkpoint-${checkpoint.id}-${checkpoint.x}-${checkpoint.y}`,
      position: [Number(checkpoint.x), Number(checkpoint.y), 0.02],
    })),
    ...state.noGoZones.map((zone) => ({
      asset_id: zone.id,
      asset_type: "no_go_zone",
      geometry_type: "box",
      uri: `builtin://qrics/no_go_zone/${zone.id}`,
      checksum: `inline-zone-${zone.id}-${zone.x}-${zone.y}-${zone.width}-${zone.height}`,
      position: [Number(zone.x), Number(zone.y), 0.01],
      size: [Math.max(0.05, Number(zone.width)), Math.max(0.05, Number(zone.height)), 0.02],
    })),
    ...state.obstacles.map((obstacle) => {
      const size = Number(obstacle.size) || 0.16;
      const common = {
        asset_id: obstacle.id,
        asset_type: "obstacle",
        geometry_type: obstacle.type,
        position: [Number(obstacle.x), Number(obstacle.y), Number(obstacle.z)],
        checksum: `inline-${obstacle.type}-${obstacle.id}`,
      };
      if (obstacle.type === "box") return { ...common, size: [size, size, Number(obstacle.height) || size] };
      if (obstacle.type === "sphere") return { ...common, radius_m: size, height_m: size };
      return { ...common, radius_m: size, height_m: Number(obstacle.height) || 0.38 };
    }),
  ];
  return {
    scene_id: sceneId,
    version: sceneVersion,
    name: sceneName,
    terrain_pack: terrain,
    assets,
    sensor_profile: {
      profile_id: "web_console_imu_contact",
      camera_enabled: true,
      imu_enabled: true,
      foot_contact_enabled: true,
      sample_rate_hz: 100,
      source_quality: "estimated",
    },
    randomization_profile: {
      profile_id: "web_console_randomization",
      enabled: terrain !== "flat",
      friction_range: terrain === "gravel" || terrain === "mixed_terrain_pack" ? [0.55, 0.95] : [0.8, 1.1],
      mass_scale_range: [0.95, 1.05],
      sensor_noise_std: 0.01,
    },
    change_summary: "saved from local Web Console",
  };
}

function runOptions() {
  return {
    backend: $("backendSelect").value,
    runtime_profile: $("runtimeProfileSelect").value,
    step_count: Number($("stepCountInput").value) || 240,
    forward_velocity_mps: 0.32,
    yaw_rate_radps: 0.04,
    obstacle_replan_distance_m: 0.18,
    auto_extend_task_steps: true,
  };
}

function previewRunOptions() {
  const options = runOptions();
  return {
    ...options,
    step_count: 1,
    forward_velocity_mps: 0.0,
    yaw_rate_radps: 0.0,
    obstacle_replan_distance_m: 0.0,
    auto_extend_task_steps: false,
  };
}

function comparableSceneObject(scene) {
  const assets = (scene.assets || []).map((asset) => ({
    asset_id: asset.asset_id,
    asset_type: asset.asset_type,
    geometry_type: asset.geometry_type || "none",
    position: asset.position || [0, 0, 0],
    size: asset.size || [0, 0, 0],
    radius_m: asset.radius_m || 0,
    height_m: asset.height_m || 0,
  }));
  return {
    scene_id: scene.scene_id,
    name: scene.name,
    terrain_pack: scene.terrain_pack,
    assets,
  };
}

const sceneComparable = (payload) => JSON.stringify(comparableSceneObject(payload));
const existingComparable = (existing) => JSON.stringify(comparableSceneObject(existing));

function nextSceneVersion(baseVersion) {
  const prefix = String(baseVersion || "1").split("+")[0];
  return `${prefix}+web${Date.now()}`;
}

const labelMap = {
  minimal: "Minimal 内置演示",
  mujoco: "MuJoCo 本机物理仿真",
  webots: "Webots 本机可视化仿真",
  headless_fast: "快速无窗口",
  balanced_visual: "MuJoCo 可视化",
  webots_fast: "Webots 可视化",
  rich_demo: "增强演示",
};

function optionLabel(value) {
  return labelMap[value] || value;
}

function formatEvidence(title, data) {
  const lines = [`【${title}】`];
  const target = data.status || data;

  if (data.name || data.scene_id || data.scene_version) {
    lines.push(`场景：${data.name || state.sceneName || data.scene_id || "未命名场景"}`);
    if (data.terrain_pack) lines.push(`地形：${terrainLabel(data.terrain_pack)}`);
    if (data.asset_count !== undefined) lines.push(`场景物体：${data.asset_count} 个`);
    if (data.state) lines.push(`状态：${stateLabel(data.state)}`);
  }
  if (target.run_id) lines.push(`运行编号：${target.run_id}`);
  if (target.state) lines.push(`状态：${stateLabel(target.state)}`);
  if (target.backend) lines.push(`仿真后端：${optionLabel(target.backend)}`);
  if (target.runtime_profile) lines.push(`运行模式：${optionLabel(target.runtime_profile)}`);
  if (target.terrain_class) lines.push(`地形识别：${terrainLabel(target.terrain_class)}`);
  if (Array.isArray(target.base_position)) lines.push(`机器人位置：${target.base_position.map((v) => Number(v).toFixed(2)).join(", ")}`);
  if (target.risk_score !== undefined) lines.push(`风险值：${target.risk_score}`);
  if (target.obstacle_detected !== undefined) lines.push(`障碍感知：${target.obstacle_detected ? "检测到" : "未检测"}`);
  if (target.gait_name) lines.push(`步态：${gaitLabel(target.gait_name)}`);
  if (target.gait_step_frequency_hz !== undefined) lines.push(`步频：${Number(target.gait_step_frequency_hz).toFixed(2)} Hz`);
  if (target.swing_foot_count !== undefined && target.stance_foot_count !== undefined) {
    lines.push(`足端相位：摆动 ${target.swing_foot_count} / 支撑 ${target.stance_foot_count}`);
  }
  if (target.target_count !== undefined && target.target_count > 0) {
    lines.push(`任务进度：${target.reached_target_count || 0}/${target.target_count}（${Math.round(Number(target.route_progress_ratio || 0) * 100)}%）`);
    if (target.active_target_id) lines.push(`当前目标：${target.active_target_id}`);
    if (Array.isArray(target.reached_target_ids) && target.reached_target_ids.length > 0) lines.push(`已到达：${target.reached_target_ids.join(" → ")}`);
    if (target.target_distance_m !== undefined) lines.push(`目标剩余距离：${Number(target.target_distance_m).toFixed(2)} m`);
    lines.push(`路径完成：${target.route_completed ? "是" : "否"}`);
  }
  if (target.presentation_pid) lines.push(`仿真窗口：已打开（进程 ${target.presentation_pid}）`);
  if (target.core_runtime_available !== undefined) {
    lines.push(`C++核心运行时：${target.core_runtime_available ? "可用" : "不可用"}`);
    const coreSummary = target.core_runtime_summary?.summary || {};
    if (coreSummary.state) lines.push(`C++任务状态：${stateLabel(coreSummary.state)}`);
    if (coreSummary.scene_obstacle_count !== undefined) lines.push(`C++场景障碍数量：${coreSummary.scene_obstacle_count}`);
    if (coreSummary.scene_forbidden_zone_count !== undefined) lines.push(`C++禁行区数量：${coreSummary.scene_forbidden_zone_count}`);
    if (coreSummary.gait_name) lines.push(`C++步态：${gaitLabel(coreSummary.gait_name)}`);
    if (target.core_runtime_error) lines.push(`C++运行时提示：${target.core_runtime_error}`);
  }
  if (data.task?.waypoints) lines.push(`任务路径点：${data.task.waypoints.join(" → ")}`);
  if (data.task?.parse_confidence !== undefined) lines.push(`解析置信度：${data.task.parse_confidence}`);
  if (Array.isArray(data.task?.constraints) && data.task.constraints.length > 0) lines.push(`任务约束：${data.task.constraints.join("，")}`);
  if (data.task?.fallback_action) lines.push(`回退动作：${fallbackActionLabel(data.task.fallback_action)}`);
  if (Array.isArray(data.task?.explanation) && data.task.explanation.length > 0) lines.push(`解析说明：${data.task.explanation.join("；")}`);
  if (data.rejection_reason) lines.push(`拒绝原因：${data.rejection_reason}`);
  if (data.segment_count !== undefined) lines.push(`回放片段：${data.segment_count} 段`);
  if (data.keyframe_count !== undefined) lines.push(`关键帧：${data.keyframe_count} 个`);
  if (Array.isArray(data.keyframes) && data.keyframes.length > 0) lines.push(`关键帧标签：${data.keyframes.slice(0, 8).join("，")}`);
  if (data.count !== undefined && Array.isArray(data.records)) {
    lines.push(`审计记录：${data.count} 条`);
    data.records.slice(0, 8).forEach((item) => lines.push(`- ${auditActionLabel(item.action)}：${stateLabel(item.result)}${item.reason ? `；${item.reason}` : ""}`));
  }
  if (data.count !== undefined && Array.isArray(data.events)) {
    lines.push(`事件：${data.count} 条`);
    data.events.slice(0, 8).forEach((item) => lines.push(`- ${eventTopicLabel(item.topic)}：${item.message || item.event_id}`));
  }
  if (lines.length === 1) lines.push("操作完成。 ");
  return lines.join("\n");
}

function stateLabel(value) {
  const labels = {
    draft: "草稿",
    archived: "已归档",
    baseline: "基线",
    running: "运行中",
    succeeded: "已完成",
    failed: "失败",
    paused: "暂停",
    cancelled: "已取消",
    preview_ready: "预览就绪",
    confirmed: "已确认",
    handed_off: "已移交控制",
    success: "成功",
    denied: "已拒绝",
  };
  return labels[value] || value;
}

function fallbackActionLabel(value) {
  return { safe_stand: "安全站立", emergency_stop: "急停", replan: "重新规划" }[value] || value;
}

function auditActionLabel(value) {
  const labels = {
    "scene.create": "保存场景",
    "scene.read": "读取场景",
    "task.run": "运行任务",
    "control.override": "控制命令",
    "audit.query": "审计查询",
  };
  return labels[value] || value;
}

function eventTopicLabel(value) {
  const labels = {
    "scene.lifecycle": "场景",
    "task.lifecycle": "任务",
    "control.status": "控制状态",
    "control.alert": "控制告警",
    "replay.index": "回放索引",
    "audit.record": "审计",
  };
  return labels[value] || value;
}

async function api(path, { method = "GET", body = null, role = "operator" } = {}) {
  const response = await fetch(path, {
    method,
    headers: headers(role),
    body: body ? JSON.stringify(body) : null,
  });
  const json = await response.json();
  if (!response.ok || !json.ok) {
    const msg = json.errors?.map((e) => `${e.code}: ${e.message}`).join("; ") || response.statusText;
    throw new Error(msg);
  }
  return json.data;
}

async function checkReadiness() {
  const readiness = await api("/api/v1/sim/readiness");
  updateReadiness(readiness);
}

function updateReadiness(readiness) {
  const items = Array.isArray(readiness.items) ? readiness.items : [];
  const ready = items.filter((item) => item.status === "ready").length;
  const blocked = items.filter((item) => item.status === "blocked").length;
  $("readinessStateLabel").textContent = readinessStatusLabel(readiness.status || "unknown");
  $("readinessReadyLabel").textContent = String(ready);
  $("readinessBlockedLabel").textContent = String(blocked);
  const lines = [
    `总体状态：${readinessStatusLabel(readiness.status || "unknown")}`,
    readiness.summary || "",
    "",
    "检查项：",
    ...items.map((item) => {
      const pathPart = item.item_id === "state_dir" && item.path ? `（保存目录：${item.path}）` : item.path ? `（路径：${item.path}）` : "";
      return `- ${item.name}：${readinessStatusLabel(item.status)}；${item.detail}${pathPart}`;
    }),
  ];
  $("readinessOutput").textContent = lines.join("\n");
}

function readinessStatusLabel(value) {
  const labels = { ready: "就绪", degraded: "部分降级", blocked: "存在阻断", unknown: "未知" };
  return labels[value] || value;
}

async function loadCatalog() {
  const status = $("serviceStatus");
  try {
    await api("/api/v1/health");
    const catalog = await api("/api/v1/sim/backends");
    fillSelect("backendSelect", catalog.backends, $("backendSelect").value);
    fillSelect("runtimeProfileSelect", catalog.runtime_profiles, $("runtimeProfileSelect").value);
    await refreshSavedScenes();
    await checkReadiness();
    status.textContent = "API 已连接";
    status.className = "status-pill ok";
  } catch (error) {
    status.textContent = "API 连接失败";
    status.className = "status-pill fail";
    $("taskOutput").textContent = String(error);
  }
}

function fillSelect(id, values, selected) {
  const select = $(id);
  select.innerHTML = "";
  values.forEach((value) => {
    const opt = document.createElement("option");
    opt.value = value;
    opt.textContent = optionLabel(value);
    select.appendChild(opt);
  });
  if (values.includes(selected)) select.value = selected;
}

async function refreshSavedScenes() {
  try {
    const data = await api("/api/v1/scenes", { role: "test_engineer" });
    state.savedScenes = Array.isArray(data.scenes) ? data.scenes : [];
    const select = $("savedSceneSelect");
    select.innerHTML = "";
    if (state.savedScenes.length === 0) {
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = "暂无已保存场景";
      select.appendChild(opt);
      return;
    }
    state.savedScenes
      .slice()
      .sort((left, right) => `${left.name || left.scene_id}`.localeCompare(`${right.name || right.scene_id}`))
      .forEach((scene) => {
        const opt = document.createElement("option");
        opt.value = `${scene.scene_id}:${scene.scene_version}`;
        opt.textContent = `${scene.name || scene.scene_id} · ${terrainLabel(scene.terrain_pack)} · ${stateLabel(scene.state)}`;
        select.appendChild(opt);
      });
    const current = `${state.sceneRef.id}:${state.sceneRef.version}`;
    if ([...select.options].some((item) => item.value === current)) select.value = current;
  } catch (error) {
    $("telemetryOutput").textContent = `刷新已保存场景失败：${error}`;
  }
}

async function loadSelectedScene() {
  const selected = $("savedSceneSelect").value;
  if (!selected) throw new Error("没有可加载的已保存场景。 ");
  const [sceneId, sceneVersion] = selected.split(":");
  const scene = await api(`/api/v1/scenes/${encodeURIComponent(sceneId)}/${encodeURIComponent(sceneVersion)}`, { role: "test_engineer" });
  applySceneProfile(scene);
  $("taskOutput").textContent = formatEvidence("已加载场景", scene);
}

function applySceneProfile(scene) {
  state.sceneRef = {
    id: scene.scene_id || scene.scene_ref?.id || sceneIdFromName(scene.name),
    version: scene.scene_version || scene.scene_ref?.version || "1",
  };
  setSceneName(scene.name || scene.scene_id || DEFAULT_SCENE_NAME);
  $("terrainSelect").value = scene.terrain_pack || "flat";
  state.terrainRegions = defaultTerrainRegions();
  const nextCheckpoints = {};
  const nextObstacles = [];
  const nextNoGoZones = [];
  (scene.assets || []).forEach((asset) => {
    const position = Array.isArray(asset.position) ? asset.position : [0, 0, 0];
    const [x, y, z] = position.map((value) => Number(value) || 0);
    if (asset.asset_type === "terrain" && asset.asset_id?.startsWith("terrain_") && asset.asset_id.endsWith("_region")) {
      const key = asset.asset_id.replace(/^terrain_/, "").replace(/_region$/, "");
      const size = Array.isArray(asset.size) ? asset.size : [];
      if (state.terrainRegions[key]) {
        state.terrainRegions[key] = {
          ...state.terrainRegions[key],
          x,
          y,
          width: Number(size[0]) || state.terrainRegions[key].width,
          height: Number(size[1]) || state.terrainRegions[key].height,
        };
      }
    } else if (asset.asset_type === "checkpoint") {
      const normalized = checkpointIdFromAsset(asset.asset_id);
      const label = checkpointLabelFromAsset(asset.asset_id, normalized);
      nextCheckpoints[normalized] = { id: normalized, label, x, y };
    } else if (asset.asset_type === "no_go_zone") {
      const size = Array.isArray(asset.size) ? asset.size : [1.15, 1.65, 0.02];
      nextNoGoZones.push({
        id: asset.asset_id || `限制区${nextNoGoZones.length + 1}`,
        label: asset.asset_id || `限制区${nextNoGoZones.length + 1}`,
        x,
        y,
        width: Number(size[0]) || 1.15,
        height: Number(size[1]) || 1.65,
      });
    } else if (asset.asset_type === "obstacle") {
      const geometry = asset.geometry_type || "box";
      const size = Array.isArray(asset.size) ? asset.size : [asset.radius_m || 0.16, asset.radius_m || 0.16, asset.height_m || 0.24];
      nextObstacles.push({
        id: asset.asset_id || `${geometry}_${nextObstacles.length + 1}`,
        type: geometry === "none" ? "box" : geometry,
        x,
        y,
        z,
        size: Number(asset.radius_m || size[0]) || 0.16,
        height: Number(asset.height_m || size[2]) || 0.24,
      });
    }
  });
  state.checkpoints = Object.keys(nextCheckpoints).length > 0
    ? nextCheckpoints
    : { platform: { id: "platform", label: "平台", x: 0.0, y: 0.0 } };
  if (!state.checkpoints.platform) state.checkpoints.platform = { id: "platform", label: "平台", x: 0.0, y: 0.0 };
  state.noGoZones = nextNoGoZones;
  state.obstacles = nextObstacles;
  state.lastSceneSignature = sceneComparable(scenePayload());
  updateSceneRefLabel("已加载");
  renderSceneEditors();
  drawScene(state.lastStatus);
}

function checkpointIdFromAsset(assetId) {
  if (assetId === "巡检点A" || assetId === "A") return "A";
  if (assetId === "巡检点B" || assetId === "B") return "B";
  if (assetId === "平台" || assetId === "platform") return "platform";
  return assetId;
}

function checkpointLabelFromAsset(assetId, waypointId) {
  if (waypointId === "A") return "A";
  if (waypointId === "B") return "B";
  if (waypointId === "platform") return "平台";
  return assetId;
}

function exportSceneJson() {
  const payload = scenePayload();
  const blob = new Blob([`${JSON.stringify(payload, null, 2)}\n`], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${payload.name || payload.scene_id}.json`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function importSceneJson() {
  $("importSceneFile").click();
}

async function handleSceneFile(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  try {
    const text = await file.text();
    const parsed = JSON.parse(text);
    applySceneProfile(normalizeImportedScene(parsed));
    $("taskOutput").textContent = formatEvidence("场景 JSON 已导入，点击保存场景后写入系统", scenePayload());
  } finally {
    event.target.value = "";
  }
}

function normalizeImportedScene(scene) {
  if (scene.scene_version) return scene;
  return { ...scene, scene_version: scene.version || "1" };
}

async function saveScene() {
  const payload = scenePayload();
  const signature = sceneComparable(payload);
  try {
    const saved = await api("/api/v1/scenes", { method: "POST", body: payload, role: "test_engineer" });
    state.sceneRef = { id: saved.scene_id, version: saved.scene_version };
    state.sceneName = saved.name || payload.name;
    state.lastSceneSignature = signature;
    updateSceneRefLabel("已保存");
    $("taskOutput").textContent = formatEvidence("场景保存成功", saved);
    await refreshSavedScenes();
    return saved;
  } catch (error) {
    if (!String(error).includes("Scene already exists")) throw error;
    const existing = await api(`/api/v1/scenes/${payload.scene_id}/${payload.version}`);
    if (existingComparable(existing) === signature) {
      state.sceneRef = { id: payload.scene_id, version: payload.version };
      state.lastSceneSignature = signature;
      updateSceneRefLabel("已保存");
      $("taskOutput").textContent = formatEvidence("场景已存在，内容未变化", existing);
      await refreshSavedScenes();
      return existing;
    }
    const versionedPayload = { ...payload, version: nextSceneVersion(payload.version), change_summary: "网页控制台自动创建新场景版本" };
    const saved = await api("/api/v1/scenes", { method: "POST", body: versionedPayload, role: "test_engineer" });
    state.sceneRef = { id: saved.scene_id, version: saved.scene_version };
    state.sceneName = saved.name || versionedPayload.name;
    state.lastSceneSignature = sceneComparable(versionedPayload);
    updateSceneRefLabel("已保存");
    $("taskOutput").textContent = formatEvidence("场景保存成功，系统已保留新版本", saved);
    await refreshSavedScenes();
    return saved;
  }
}

async function previewScene() {
  await saveScene();
  const data = await api("/api/v1/sim/preview", {
    method: "POST",
    body: { scene_ref: state.sceneRef, run_options: previewRunOptions() },
  });
  state.lastStatus = data;
  updateTelemetry(data);
  $("telemetryOutput").textContent = formatEvidence("仿真预览完成", data);
  drawScene(data);
}

async function runTask() {
  await saveScene();
  const result = await api("/api/v1/tasks/run", {
    method: "POST",
    body: {
      source_text: $("taskText").value,
      scene_ref: state.sceneRef,
      require_confirmation: false,
      run_options: runOptions(),
      reason: "Web Console 一键运行",
    },
  });
  const task = result.task || {};
  const status = result.status || {};
  if (!result.run_started) {
    $("taskOutput").textContent = formatEvidence("任务未启动：解析或安全边界拒绝", result);
    drawScene(state.lastStatus);
    return;
  }
  state.runId = result.run_id || status.run_id;
  state.lastStatus = status;
  updateTelemetry(status);
  $("taskOutput").textContent = `${formatEvidence("任务运行已启动", { task, status, result })}\n\n场景预览正在按任务路径回放中。`;
  await refreshReplay();
  startRouteAnimation(task, status);
}

async function override(command_type, reason) {
  if (!state.runId) throw new Error("还没有运行任务，无法执行控制命令。 ");
  const status = await api(`/api/v1/control/${state.runId}/override`, {
    method: "POST",
    body: { command_type, reason },
  });
  state.lastStatus = status;
  updateTelemetry(status);
  $("telemetryOutput").textContent = formatEvidence("控制命令已下发", status);
}

async function refreshReplay() {
  if (!state.runId) return;
  const replay = await api(`/api/v1/replay/${state.runId}`);
  $("telemetryOutput").textContent = formatEvidence("回放查询结果", replay);
}

async function refreshAudit() {
  const query = state.runId ? `?object_id=${encodeURIComponent(state.runId)}` : "";
  const audit = await api(`/api/v1/audit${query}`, { role: "auditor" });
  $("telemetryOutput").textContent = formatEvidence("审计查询结果", audit);
}

async function refreshEvents() {
  const query = state.runId ? `?run_id=${encodeURIComponent(state.runId)}` : "";
  const events = await api(`/api/v1/events${query}`, { role: "auditor" });
  $("telemetryOutput").textContent = formatEvidence("事件查询结果", events);
}

async function probeCoreRuntime() {
  const probe = await api("/api/v1/sim/core-runtime");
  $("telemetryOutput").textContent = formatEvidence("C++核心运行时自检", probe);
}

function updateTelemetry(status) {
  state.runId = status.run_id || state.runId;
  $("runIdLabel").textContent = status.run_id || "-";
  $("backendLabel").textContent = optionLabel(status.backend || "-");
  $("terrainLabel").textContent = terrainLabel(status.terrain_class || "-");
  $("riskLabel").textContent = status.risk_score ?? "-";
  $("obstacleLabel").textContent = status.obstacle_detected ? `${Number(status.nearest_obstacle_distance_m).toFixed(2)} 米` : "未检测";
  $("positionLabel").textContent = Array.isArray(status.base_position)
    ? status.base_position.map((v) => Number(v).toFixed(2)).join(", ")
    : "-";
  $("gaitLabel").textContent = status.gait_name ? `${gaitLabel(status.gait_name)} / ${Number(status.gait_step_frequency_hz || 0).toFixed(2)} Hz` : "-";
  $("footPhaseLabel").textContent = status.swing_foot_count !== undefined
    ? `摆动 ${status.swing_foot_count} / 支撑 ${status.stance_foot_count}`
    : "-";
  $("routeProgressLabel").textContent = status.target_count
    ? `${status.reached_target_count || 0}/${status.target_count} · ${Math.round(Number(status.route_progress_ratio || 0) * 100)}%`
    : "-";
  $("activeTargetLabel").textContent = status.active_target_id
    ? `${status.active_target_id} / ${Number(status.target_distance_m || 0).toFixed(2)} m`
    : "-";
}

function gaitLabel(value) {
  const labels = { stand: "站立", crawl: "爬行步态", cautious_trot: "谨慎小跑", trot: "小跑", recovery: "恢复步态" };
  return labels[value] || value;
}

function terrainLabel(value) {
  const labels = {
    flat: "平地",
    slope: "坡面",
    gravel: "碎石",
    stairs: "台阶",
    low_friction: "低摩擦",
    mixed: "混合地形",
    mixed_terrain_pack: "混合地形",
    unknown: "未知",
  };
  return labels[value] || value;
}

function drawScene(status = null) {
  const canvas = $("sceneCanvas");
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  const terrain = $("terrainSelect").value;
  ctx.fillStyle = terrain === "gravel" ? "#e7dcc6" : terrain === "slope" ? "#e2ead9" : "#eef6e9";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.strokeStyle = "#cad7e4";
  for (let x = 0; x < canvas.width; x += 40) {
    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, canvas.height); ctx.stroke();
  }
  for (let y = 0; y < canvas.height; y += 40) {
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(canvas.width, y); ctx.stroke();
  }
  drawSemanticScene(ctx, terrain, status);
  ctx.fillStyle = "#4b5563";
  ctx.font = "16px sans-serif";
  ctx.fillText(`地形：${terrainLabel(terrain)}`, 18, 28);
  state.obstacles.forEach((obstacle) => drawObstacle(ctx, obstacle));
  const base = status?.base_position || [0, 0, 0.32];
  drawRobot(ctx, Number(base[0]), Number(base[1]), Boolean(status?.obstacle_detected), status);
}

function drawSemanticScene(ctx, terrain, status = null) {
  drawTerrainRegions(ctx, terrain);
  state.noGoZones.forEach((zone) => drawNoGoZone(ctx, zone));
  Object.values(state.checkpoints).forEach((marker) => drawCheckpoint(ctx, marker, status));
}

function drawTerrainRegions(ctx, terrain) {
  activeTerrainKeys(terrain).forEach((key) => {
    const region = state.terrainRegions[key];
    if (!region) return;
    drawTerrainRegion(ctx, key, region);
  });
}

function drawTerrainRegion(ctx, key, region) {
  const p = canvasPoint(Number(region.x), Number(region.y));
  const width = Math.max(0.05, Number(region.width)) * WORLD_SCALE;
  const height = Math.max(0.05, Number(region.height)) * WORLD_SCALE;
  if (key === "slope") {
    ctx.fillStyle = "rgba(71, 128, 71, 0.28)";
    ctx.strokeStyle = "#2f6b2f";
    ctx.fillRect(p.x - width / 2, p.y - height / 2, width, height);
    ctx.strokeRect(p.x - width / 2, p.y - height / 2, width, height);
  } else if (key === "gravel") {
    ctx.fillStyle = "rgba(126, 111, 83, 0.28)";
    ctx.strokeStyle = "#5c4d33";
    ctx.fillRect(p.x - width / 2, p.y - height / 2, width, height);
    ctx.strokeRect(p.x - width / 2, p.y - height / 2, width, height);
  } else if (key === "stairs") {
    ctx.fillStyle = "rgba(100, 100, 100, 0.28)";
    ctx.strokeStyle = "#555";
    const stepWidth = width / 4;
    for (let i = 0; i < 4; i += 1) {
      const stepHeight = height * (0.45 + i * 0.13);
      ctx.fillRect(p.x - width / 2 + i * stepWidth, p.y - stepHeight / 2, stepWidth - 3, stepHeight);
      ctx.strokeRect(p.x - width / 2 + i * stepWidth, p.y - stepHeight / 2, stepWidth - 3, stepHeight);
    }
  }
  ctx.fillStyle = key === "gravel" ? "#5c4d33" : key === "slope" ? "#2f6b2f" : "#555";
  ctx.font = "14px sans-serif";
  ctx.fillText(region.label, p.x - width / 2 + 10, p.y - height / 2 + 22);
}

function canvasPoint(x, y) {
  return { x: WORLD_ORIGIN.x + x * WORLD_SCALE, y: WORLD_ORIGIN.y - y * WORLD_SCALE };
}

function clientCanvasPoint(clientX, clientY) {
  const canvas = $("sceneCanvas");
  const rect = canvas.getBoundingClientRect();
  return {
    x: (clientX - rect.left) * (canvas.width / rect.width),
    y: (clientY - rect.top) * (canvas.height / rect.height),
  };
}

function worldPoint(clientX, clientY) {
  const point = clientCanvasPoint(clientX, clientY);
  const x = (point.x - WORLD_ORIGIN.x) / WORLD_SCALE;
  const y = (WORLD_ORIGIN.y - point.y) / WORLD_SCALE;
  return { x, y };
}

function drawNoGoZone(ctx, zone) {
  const p = canvasPoint(Number(zone.x), Number(zone.y));
  const zoneWidth = Math.max(0.05, Number(zone.width)) * WORLD_SCALE;
  const zoneHeight = Math.max(0.05, Number(zone.height)) * WORLD_SCALE;
  ctx.fillStyle = "rgba(64, 98, 149, 0.20)";
  ctx.strokeStyle = "#315da8";
  ctx.lineWidth = 2;
  ctx.setLineDash([8, 5]);
  ctx.fillRect(p.x - zoneWidth / 2, p.y - zoneHeight / 2, zoneWidth, zoneHeight);
  ctx.strokeRect(p.x - zoneWidth / 2, p.y - zoneHeight / 2, zoneWidth, zoneHeight);
  ctx.setLineDash([]);
  ctx.fillStyle = "#234073";
  ctx.font = "14px sans-serif";
  ctx.fillText(zone.label || zone.id, p.x - zoneWidth / 2, p.y - zoneHeight / 2 - 8);
}

function drawCheckpoint(ctx, marker, status = null) {
  const p = canvasPoint(Number(marker.x), Number(marker.y));
  const isPlatform = marker.id === "platform";
  ctx.strokeStyle = isPlatform ? "#1f6feb" : marker.id === "A" ? "#21a366" : "#c88719";
  ctx.fillStyle = isPlatform ? "rgba(31,111,235,0.14)" : "rgba(255,255,255,0.82)";
  const isActiveTarget = status?.active_target_id === marker.id;
  const reachedTargets = Array.isArray(status?.reached_target_ids) ? status.reached_target_ids : [];
  const isReached = reachedTargets.includes(marker.id);
  ctx.lineWidth = isActiveTarget ? 5 : 3;
  if (isPlatform) {
    const halfW = (PLATFORM_SIZE.width * WORLD_SCALE) / 2;
    const halfH = (PLATFORM_SIZE.height * WORLD_SCALE) / 2;
    ctx.fillRect(p.x - halfW, p.y - halfH, halfW * 2, halfH * 2);
    ctx.strokeRect(p.x - halfW, p.y - halfH, halfW * 2, halfH * 2);
  } else {
    ctx.beginPath();
    ctx.arc(p.x, p.y, CHECKPOINT_RADIUS * WORLD_SCALE, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(p.x, p.y - 20);
    ctx.lineTo(p.x, p.y - 38);
    ctx.lineTo(p.x + 18, p.y - 30);
    ctx.lineTo(p.x, p.y - 24);
    ctx.fillStyle = ctx.strokeStyle;
    ctx.fill();
  }
  if (isActiveTarget) {
    ctx.strokeStyle = "#ef4444";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(p.x, p.y, isPlatform ? (PLATFORM_SIZE.width * WORLD_SCALE) / 2 + 8 : CHECKPOINT_RADIUS * WORLD_SCALE + 8, 0, Math.PI * 2);
    ctx.stroke();
  }
  if (isReached) {
    ctx.fillStyle = "#16a34a";
    ctx.font = "13px sans-serif";
    ctx.fillText("已到达", p.x + 18, p.y + 8);
  }
  ctx.fillStyle = "#111827";
  ctx.font = "15px sans-serif";
  ctx.fillText(marker.label || marker.id, p.x + 18, p.y - 10);
}

function drawObstacle(ctx, obstacle) {
  const p = canvasPoint(Number(obstacle.x), Number(obstacle.y));
  const metricSize = Math.max(0.03, Number(obstacle.size) || 0.12);
  const radius = Math.max(8, metricSize * WORLD_SCALE);
  ctx.fillStyle = "#e0832d";
  ctx.strokeStyle = "#8f3d11";
  ctx.lineWidth = 2;
  if (obstacle.type === "sphere") {
    ctx.beginPath(); ctx.arc(p.x, p.y, radius, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
  } else if (obstacle.type === "box") {
    const half = Math.max(8, (metricSize * WORLD_SCALE) / 2);
    ctx.fillRect(p.x - half, p.y - half, half * 2, half * 2);
    ctx.strokeRect(p.x - half, p.y - half, half * 2, half * 2);
  } else {
    ctx.beginPath(); ctx.ellipse(p.x, p.y, radius, radius * 0.75, 0, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
  }
  ctx.fillStyle = "#4a2b13";
  ctx.font = "12px sans-serif";
  ctx.fillText(obstacle.id, p.x + radius + 4, p.y + 4);
}

function drawRobot(ctx, x, y, risk, status = null) {
  const p = canvasPoint(x, y);
  const phase = Number(status?.gait_phase || 0);
  const swingCount = Number(status?.swing_foot_count || 0);
  const stanceCount = Number(status?.stance_foot_count ?? 4);
  const legs = [
    { x0: -10, y0: -13, phase: 0.00 },
    { x0: 12, y0: 13, phase: 0.00 },
    { x0: 12, y0: -13, phase: 0.50 },
    { x0: -10, y0: 13, phase: 0.50 },
  ];
  legs.forEach((leg, index) => {
    const local = (phase + leg.phase) % 1;
    const isSwing = swingCount > 0 && index < Math.max(1, swingCount);
    const reach = 16 + Math.sin(local * Math.PI * 2) * 5;
    ctx.strokeStyle = isSwing ? "#f97316" : "#0b3d91";
    ctx.lineWidth = isSwing ? 4 : 3;
    ctx.beginPath();
    ctx.moveTo(p.x + leg.x0, p.y + leg.y0);
    ctx.lineTo(p.x + leg.x0 - reach, p.y + leg.y0 + (leg.y0 > 0 ? 12 : -12));
    ctx.stroke();
  });
  ctx.fillStyle = "#1f6feb";
  ctx.strokeStyle = risk ? "#c62834" : "#0b3d91";
  ctx.lineWidth = risk ? 5 : 2;
  const bodyHalfLength = (ROBOT_BODY.length * WORLD_SCALE) / 2;
  const bodyHalfWidth = (ROBOT_BODY.width * WORLD_SCALE) / 2;
  ctx.beginPath();
  ctx.moveTo(p.x + bodyHalfLength, p.y);
  ctx.lineTo(p.x - bodyHalfLength * 0.72, p.y - bodyHalfWidth);
  ctx.lineTo(p.x - bodyHalfLength * 0.72, p.y + bodyHalfWidth);
  ctx.closePath();
  ctx.fill();
  ctx.stroke();
  ctx.fillStyle = "#0d2442";
  ctx.font = "13px sans-serif";
  ctx.fillText(`四足机器人 · ${stanceCount}支撑/${swingCount}摆动`, p.x - 52, p.y + bodyHalfWidth + 26);
}

function findDraggableAt(clientX, clientY) {
  const world = worldPoint(clientX, clientY);
  for (let i = state.obstacles.length - 1; i >= 0; i -= 1) {
    const obstacle = state.obstacles[i];
    const radius = obstacle.type === "box" ? Math.max(0.12, (Number(obstacle.size) || 0.12) * 0.65) : Math.max(0.10, Number(obstacle.size) || 0.12);
    if (Math.hypot(world.x - Number(obstacle.x), world.y - Number(obstacle.y)) <= radius + 0.08) {
      return { kind: "obstacle", index: i, offsetX: Number(obstacle.x) - world.x, offsetY: Number(obstacle.y) - world.y };
    }
  }
  for (const [key, marker] of Object.entries(state.checkpoints)) {
    const radius = marker.id === "platform" ? Math.max(PLATFORM_SIZE.width, PLATFORM_SIZE.height) * 0.5 : CHECKPOINT_RADIUS;
    if (Math.hypot(world.x - Number(marker.x), world.y - Number(marker.y)) <= radius + 0.08) {
      return { kind: "checkpoint", key, offsetX: Number(marker.x) - world.x, offsetY: Number(marker.y) - world.y };
    }
  }
  for (let i = state.noGoZones.length - 1; i >= 0; i -= 1) {
    const zone = state.noGoZones[i];
    if (Math.abs(world.x - Number(zone.x)) <= Number(zone.width) / 2
      && Math.abs(world.y - Number(zone.y)) <= Number(zone.height) / 2) {
      return { kind: "no_go_zone", index: i, offsetX: Number(zone.x) - world.x, offsetY: Number(zone.y) - world.y };
    }
  }
  const terrainKeys = activeTerrainKeys().slice().reverse();
  for (const key of terrainKeys) {
    const region = state.terrainRegions[key];
    if (!region) continue;
    if (Math.abs(world.x - Number(region.x)) <= Number(region.width) / 2
      && Math.abs(world.y - Number(region.y)) <= Number(region.height) / 2) {
      return { kind: "terrain", key, offsetX: Number(region.x) - world.x, offsetY: Number(region.y) - world.y };
    }
  }
  return null;
}

function updateDrag(clientX, clientY) {
  if (!state.drag) return;
  const world = worldPoint(clientX, clientY);
  const x = Number((world.x + state.drag.offsetX).toFixed(2));
  const y = Number((world.y + state.drag.offsetY).toFixed(2));
  if (state.drag.kind === "obstacle") {
    const item = state.obstacles[state.drag.index];
    if (!item) return;
    item.x = x;
    item.y = y;
    syncObjectEditor("obstacle", state.drag.index, item);
  } else if (state.drag.kind === "checkpoint") {
    const item = state.checkpoints[state.drag.key];
    if (!item) return;
    item.x = x;
    item.y = y;
    syncObjectEditor("checkpoint", state.drag.key, item);
  } else if (state.drag.kind === "no_go_zone") {
    const item = state.noGoZones[state.drag.index];
    if (!item) return;
    item.x = x;
    item.y = y;
    syncObjectEditor("no_go_zone", state.drag.index, item);
  } else if (state.drag.kind === "terrain") {
    const item = state.terrainRegions[state.drag.key];
    if (!item) return;
    item.x = x;
    item.y = y;
  }
  drawScene(state.lastStatus);
}

function syncObjectEditor(kind, keyOrIndex, item) {
  const selector = kind === "checkpoint"
    ? `.object-card[data-kind="checkpoint"][data-key="${CSS.escape(String(keyOrIndex))}"]`
    : `.object-card[data-kind="${kind}"][data-index="${keyOrIndex}"]`;
  const card = document.querySelector(selector);
  if (!card) return;
  ["x", "y", "z", "size", "height", "width"].forEach((field) => {
    const input = card.querySelector(`[data-field="${field}"]`);
    if (input && item[field] !== undefined && document.activeElement !== input) input.value = item[field];
  });
}


function waypointPosition(waypointId) {
  const normalized = checkpointIdFromAsset(waypointId);
  const marker = state.checkpoints[normalized] || state.checkpoints[waypointId];
  if (!marker) return null;
  return { id: normalized, x: Number(marker.x), y: Number(marker.y) };
}

function routeTargetsFromTask(task) {
  const details = Array.isArray(task?.waypoint_details) ? task.waypoint_details : [];
  const ids = details.length > 0
    ? details.map((item) => item.waypoint_id || item.id).filter(Boolean)
    : (Array.isArray(task?.waypoints) ? task.waypoints : []);
  const targets = ids.map((id) => waypointPosition(String(id))).filter(Boolean);
  const platform = waypointPosition("platform") || { id: "platform", x: 0, y: 0 };
  if (targets.length === 0 || targets[0].id !== "platform") return [platform, ...targets];
  return targets;
}

function startRouteAnimation(task, finalStatus) {
  const targets = routeTargetsFromTask(task);
  if (targets.length < 2) {
    state.lastStatus = finalStatus;
    updateTelemetry(finalStatus);
    drawScene(finalStatus);
    return;
  }
  if (state.animationFrame) cancelAnimationFrame(state.animationFrame);
  const token = state.animationToken + 1;
  state.animationToken = token;
  const segmentDurationMs = 1050;
  const totalDurationMs = Math.max(1500, (targets.length - 1) * segmentDurationMs);
  const startedAt = performance.now();
  const animate = (now) => {
    if (token !== state.animationToken) return;
    const elapsed = Math.min(totalDurationMs, now - startedAt);
    const rawSegment = elapsed / segmentDurationMs;
    const segmentIndex = Math.min(targets.length - 2, Math.floor(rawSegment));
    const localT = Math.min(1, rawSegment - segmentIndex);
    const eased = localT < 0.5 ? 2 * localT * localT : 1 - ((-2 * localT + 2) ** 2) / 2;
    const from = targets[segmentIndex];
    const to = targets[segmentIndex + 1];
    const x = from.x + (to.x - from.x) * eased;
    const y = from.y + (to.y - from.y) * eased;
    const reached = targets.slice(0, segmentIndex + 1).map((item) => item.id);
    const animatedStatus = {
      ...finalStatus,
      base_position: [x, y, finalStatus.base_position?.[2] || 0.35],
      active_target_id: to.id,
      reached_target_ids: reached,
      reached_target_count: reached.length,
      target_count: targets.length,
      route_completed: false,
      route_progress_ratio: Math.min(0.98, elapsed / totalDurationMs),
      target_distance_m: Math.hypot(to.x - x, to.y - y),
      gait_phase: (elapsed / 1000) % 1,
      gait_name: finalStatus.gait_name || "cautious_trot",
      swing_foot_count: finalStatus.swing_foot_count || 2,
      stance_foot_count: finalStatus.stance_foot_count || 2,
    };
    state.lastStatus = animatedStatus;
    updateTelemetry(animatedStatus);
    drawScene(animatedStatus);
    if (elapsed < totalDurationMs) {
      state.animationFrame = requestAnimationFrame(animate);
    } else {
      state.lastStatus = finalStatus;
      updateTelemetry(finalStatus);
      drawScene(finalStatus);
    }
  };
  state.animationFrame = requestAnimationFrame(animate);
}

function bindSceneDragging() {
  const canvas = $("sceneCanvas");
  canvas.addEventListener("pointerdown", (event) => {
    state.drag = findDraggableAt(event.clientX, event.clientY);
    canvas.classList.toggle("dragging", Boolean(state.drag));
    if (state.drag) canvas.setPointerCapture(event.pointerId);
  });
  canvas.addEventListener("pointermove", (event) => {
    if (!state.drag) return;
    updateDrag(event.clientX, event.clientY);
  });
  const stop = (event) => {
    if (event.pointerId !== undefined && canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
    state.drag = null;
    canvas.classList.remove("dragging");
  };
  canvas.addEventListener("pointerup", stop);
  canvas.addEventListener("pointercancel", stop);
  canvas.addEventListener("lostpointercapture", stop);
}

function bind(id, handler) {
  $(id).addEventListener("click", async () => {
    try { await handler(); } catch (error) { $("telemetryOutput").textContent = String(error); }
  });
}

bind("readinessBtn", checkReadiness);
bind("loadCatalogBtn", loadCatalog);
bind("addCheckpointBtn", () => {
  const checkpoint = checkpointTemplate();
  state.checkpoints[checkpoint.id] = checkpoint;
  renderCheckpointList();
  drawScene(state.lastStatus);
});
bind("addNoGoZoneBtn", () => { state.noGoZones.push(noGoZoneTemplate()); renderNoGoZoneList(); drawScene(state.lastStatus); });
bind("addBoxBtn", () => { state.obstacles.push(obstacleTemplate("box")); renderObstacleList(); drawScene(state.lastStatus); });
bind("addCylinderBtn", () => { state.obstacles.push(obstacleTemplate("cylinder")); renderObstacleList(); drawScene(state.lastStatus); });
bind("addSphereBtn", () => { state.obstacles.push(obstacleTemplate("sphere")); renderObstacleList(); drawScene(state.lastStatus); });
bind("resetSceneBtn", resetDefaultScene);
bind("saveSceneBtn", saveScene);
bind("loadSceneBtn", loadSelectedScene);
bind("exportSceneBtn", exportSceneJson);
bind("importSceneBtn", importSceneJson);
$("importSceneFile").addEventListener("change", (event) => {
  handleSceneFile(event).catch((error) => { $("telemetryOutput").textContent = String(error); });
});
bind("previewSceneBtn", previewScene);
bind("runTaskBtn", runTask);
bind("emergencyStopBtn", () => override("emergency_stop", "网页控制台触发急停"));
bind("safeStandBtn", () => override("safe_stand", "网页控制台触发安全站立"));
bind("refreshReplayBtn", refreshReplay);
bind("refreshAuditBtn", refreshAudit);
bind("refreshEventsBtn", refreshEvents);
bind("probeCoreRuntimeBtn", probeCoreRuntime);

$("backendSelect").addEventListener("change", () => {
  if ($("backendSelect").value === "webots") $("runtimeProfileSelect").value = "webots_fast";
  if ($("backendSelect").value === "mujoco") $("runtimeProfileSelect").value = "balanced_visual";
  if ($("backendSelect").value === "minimal") $("runtimeProfileSelect").value = "headless_fast";
});

$("terrainSelect").addEventListener("change", () => drawScene(state.lastStatus));
$("sceneNameInput").addEventListener("input", () => setSceneName($("sceneNameInput").value, { resetRef: true }));

bindSceneDragging();
resetDefaultScene();
loadCatalog();