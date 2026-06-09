const headers = (role = "operator") => ({
  "content-type": "application/json",
  "x-request-id": `web-${Date.now()}`,
  "x-actor-id": "web-console",
  "x-actor-role": role,
});

const VIEW_DEFAULT = { scale: 185, originX: 98, originY: 245 };
const ROBOT_BODY = { length: 0.56, width: 0.26 };
const ROBOT_ROUTE_RADIUS = 0.34;
const PLATFORM_SIZE = { width: 1.05, height: 0.78 };
const CHECKPOINT_RADIUS = 0.18;
const DEFAULT_SCENE_NAME = "本机场景";
const DEFAULT_SCENE_REF = { id: "local", version: "1" };
const DRAW_EDIT_HANDLES = false;
const DRAW_SAFETY_ENVELOPES = false;

const defaultTerrainRegions = () => ({
  slope: { id: "slope", label: "坡面", x: 1.35, y: 0.60, width: 1.20, height: 0.56, slopeDeg: 12 },
  gravel: { id: "gravel", label: "碎石", x: 0.95, y: -0.48, width: 0.88, height: 0.58, roughness: 0.035 },
  stairs: { id: "stairs", label: "台阶", x: 1.72, y: -0.46, width: 0.95, height: 0.56, stepHeight: 0.045, stepCount: 5 },
});

const state = {
  sceneRef: { ...DEFAULT_SCENE_REF },
  sceneName: DEFAULT_SCENE_NAME,
  runId: "",
  obstacles: [],
  checkpoints: {},
  noGoZones: [],
  terrainRegions: defaultTerrainRegions(),
  view: { ...VIEW_DEFAULT },
  drag: null,
  lastStatus: null,
  lastSceneSignature: "",
  savedScenes: [],
  animationFrame: 0,
  animationToken: 0,
  runTaskBusy: false,
  pendingRunStatus: null,
  runSessionToken: 0,
};

const $ = (id) => document.getElementById(id);

function viewScale() {
  return Math.max(70, Math.min(420, Number(state.view.scale) || VIEW_DEFAULT.scale));
}

function resetView() {
  state.view = { ...VIEW_DEFAULT };
  drawScene(state.lastStatus);
}

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
    { id: "低摩擦区", label: "低摩擦区", x: 1.35, y: 0.0, width: 0.62, height: 0.84 },
  ];
  state.obstacles = [
    { id: "箱体", type: "box", x: 0.82, y: 0.40, z: 0.22, size: 0.36, height: 0.44 },
    { id: "圆柱", type: "cylinder", x: 1.42, y: -0.66, z: 0.24, size: 0.19, height: 0.48 },
    { id: "球体", type: "sphere", x: 2.05, y: 0.48, z: 0.20, size: 0.21, height: 0.21 },
  ];
  renderSceneEditors();
  drawScene();
}

function renderSceneEditors() {
  renderCheckpointList();
  renderTerrainRegionList();
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

function renderTerrainRegionList() {
  const root = $("terrainRegionList");
  if (!root) return;
  root.innerHTML = "";
  activeTerrainKeys().forEach((key) => {
    const region = state.terrainRegions[key] || defaultTerrainRegions()[key];
    const card = document.createElement("div");
    card.className = "object-card terrain-card";
    card.dataset.kind = "terrain";
    card.dataset.key = key;
    const extra = key === "slope"
      ? `<label>坡度°<input data-field="slopeDeg" type="number" min="2" max="24" step="1" value="${region.slopeDeg ?? 12}" /></label>`
      : key === "gravel"
        ? `<label>碎石粒径m<input data-field="roughness" type="number" min="0.012" max="0.08" step="0.005" value="${region.roughness ?? 0.035}" /></label>`
        : `<label>台阶高m<input data-field="stepHeight" type="number" min="0.015" max="0.09" step="0.005" value="${region.stepHeight ?? 0.045}" /></label>
           <label>级数<input data-field="stepCount" type="number" min="2" max="8" step="1" value="${region.stepCount ?? 5}" /></label>`;
    card.innerHTML = `
      <div class="object-card-title"><strong>${escapeHtml(region.label || key)}</strong><span>可拖动/边缘拉伸</span></div>
      <div class="object-card-grid">
        <label>X 坐标<input data-field="x" type="number" step="0.05" value="${region.x}" /></label>
        <label>Y 坐标<input data-field="y" type="number" step="0.05" value="${region.y}" /></label>
        <label>宽度<input data-field="width" type="number" min="0.12" step="0.05" value="${region.width}" /></label>
        <label>高度<input data-field="height" type="number" min="0.12" step="0.05" value="${region.height}" /></label>
        ${extra}
      </div>`;
    card.querySelectorAll("input").forEach((input) => {
      input.addEventListener("input", () => {
        const field = input.dataset.field;
        if (!field) return;
        const active = state.terrainRegions[key];
        active[field] = field === "stepCount" ? Math.round(Number(input.value)) : Number(input.value);
        drawScene(state.lastStatus);
      });
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
      checksum: `inline-terrain-${key}-${region.x}-${region.y}-${region.width}-${region.height}-${region.slopeDeg || 0}-${region.roughness || 0}-${region.stepHeight || 0}-${region.stepCount || 0}`,
      required: false,
      position: [Number(region.x), Number(region.y), 0.0],
      terrain_class: key,
      size: [Math.max(0.05, Number(region.width)), Math.max(0.05, Number(region.height)), terrainVisualThickness(key, region)],
      slope_deg: key === "slope" ? Number(region.slopeDeg || 12) : 0,
      roughness_m: key === "gravel" ? Number(region.roughness || 0.035) : 0,
      step_height_m: key === "stairs" ? Number(region.stepHeight || 0.045) : 0,
      step_count: key === "stairs" ? Math.max(2, Math.min(8, Math.round(Number(region.stepCount || 5)))) : 0,
    };
  });
}

function terrainVisualThickness(key, region = {}) {
  if (key === "slope") return Math.max(0.06, Math.min(0.26, Math.tan((Number(region.slopeDeg || 12) * Math.PI) / 180) * Number(region.width || 1.2) * 0.45));
  if (key === "gravel") return Math.max(0.04, Math.min(0.12, Number(region.roughness || 0.035) * 2.0));
  if (key === "stairs") return Math.max(0.08, Math.min(0.72, Number(region.stepHeight || 0.045) * Number(region.stepCount || 5)));
  return 0.03;
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
    obstacle_replan_distance_m: ROBOT_ROUTE_RADIUS,
    auto_extend_task_steps: true,
  };
}

function previewRunOptions() {
  const options = runOptions();
  return {
    ...options,
    step_count: Math.max(240, Number($("stepCountInput").value) || 240),
    forward_velocity_mps: 0.0,
    yaw_rate_radps: 0.0,
    obstacle_replan_distance_m: ROBOT_ROUTE_RADIUS,
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
    slope_deg: asset.slope_deg || 0,
    roughness_m: asset.roughness_m || 0,
    step_height_m: asset.step_height_m || 0,
    step_count: asset.step_count || 0,
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
          slopeDeg: Number(asset.slope_deg) || state.terrainRegions[key].slopeDeg,
          roughness: Number(asset.roughness_m) || state.terrainRegions[key].roughness,
          stepHeight: Number(asset.step_height_m) || state.terrainRegions[key].stepHeight,
          stepCount: Number(asset.step_count) || state.terrainRegions[key].stepCount,
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
  stopRouteAnimation();
  state.pendingRunStatus = null;
  state.runId = "";
  state.lastStatus = stripTaskExecutionFields(data);
  updateTelemetry(state.lastStatus);
  $("telemetryOutput").textContent = formatEvidence("场景预览完成（未启动任务）", state.lastStatus);
  drawScene(state.lastStatus);
}

async function runTask() {
  if (state.runTaskBusy) {
    $("telemetryOutput").textContent = "任务运行请求正在处理中，请等待本次运行完成后再提交下一次。";
    return;
  }

  const runToken = beginRunSession();
  const sourceText = $("taskText").value;
  const localTask = taskPreviewFromInputText(sourceText);
  const pendingStatus = pendingRunStatusFromTask(localTask);
  let result = null;
  let finalStatus = pendingStatus;

  state.runTaskBusy = true;
  setRunTaskBusy(true);
  state.pendingRunStatus = pendingStatus;
  state.lastStatus = stripTaskExecutionFields(pendingStatus);
  updateTelemetry(pendingStatus);
  drawScene(state.lastStatus);
  $("taskOutput").textContent = `${formatEvidence("任务已接收，正在执行", { task: localTask, status: pendingStatus })}\n\n正在保存场景、生成 C++ 规划路径并启动异步控制闭环。`;

  try {
    await saveScene();
    if (!isCurrentRunSession(runToken)) return;

    result = await api("/api/v1/tasks/run", {
      method: "POST",
      body: {
        source_text: sourceText,
        scene_ref: state.sceneRef,
        require_confirmation: false,
        wait_for_completion: false,
        run_options: runOptions(),
        reason: "Web Console 一键运行",
      },
    });
    if (!isCurrentRunSession(runToken)) return;

    const task = result.task || localTask;
    const status = result.status || {};
    if (!result.run_started) {
      stopRouteAnimation();
      state.pendingRunStatus = null;
      $("taskOutput").textContent = formatEvidence("任务未启动：解析或安全边界拒绝", result);
      drawScene(state.lastStatus);
      return;
    }

    stopRouteAnimation();
    state.runId = result.run_id || status.run_id;
    finalStatus = normalizeFinalRunStatus(status, task, pendingStatus);
    applyRunStatus(finalStatus);
    $("taskOutput").textContent = `${formatEvidence("任务运行中", { task, status: finalStatus, result })}\n\n控制状态由后端持续刷新；场景预览区使用同一 run_id 的规划路径与位置更新，不沿用上一次运行结果。`;

    const completionStatus = await waitForRunCompletion(state.runId, {
      timeoutMs: runCompletionTimeoutMs(),
      intervalMs: 350,
      onStatus: (latestStatus) => {
        if (!isCurrentRunSession(runToken)) return;
        const liveStatus = normalizeFinalRunStatus(latestStatus, task, finalStatus);
        finalStatus = liveStatus;
        applyRunStatus(liveStatus);
        $("taskOutput").textContent = `${formatEvidence("任务运行中", { task, status: liveStatus, result })}\n\n正在接收 C++/仿真闭环的实时进度。`;
      },
    });
    if (!isCurrentRunSession(runToken)) return;

    stopRouteAnimation();
    state.pendingRunStatus = null;
    if (completionStatus) {
      finalStatus = normalizeFinalRunStatus(completionStatus, task, finalStatus);
      applyRunStatus(finalStatus);
      const title = runStatusIsComplete(finalStatus) ? "任务运行完成" : "任务运行已返回状态";
      $("taskOutput").textContent = formatEvidence(title, { task, status: finalStatus, result });
      refreshReplay().catch((error) => { $("telemetryOutput").textContent = `回放查询失败：${error}`; });
    } else {
      finalStatus = {
        ...finalStatus,
        state: "running",
        reason: "后端仍在执行，已解除前端按钮锁定；可继续查询事件/回放。",
      };
      applyRunStatus(finalStatus);
      $("taskOutput").textContent = `${formatEvidence("任务仍在后台执行", { task, status: finalStatus, result })}\n\n控制台不会继续卡在按钮忙状态；可稍后点击“查询事件”或“查询回放”。`;
    }
  } catch (error) {
    if (isCurrentRunSession(runToken)) {
      stopRouteAnimation();
      state.pendingRunStatus = null;
      $("telemetryOutput").textContent = String(error);
    }
  } finally {
    if (isCurrentRunSession(runToken)) {
      state.runTaskBusy = false;
      setRunTaskBusy(false);
    }
  }
}

function beginRunSession() {
  stopRouteAnimation();
  state.runSessionToken += 1;
  state.runId = "";
  state.pendingRunStatus = null;
  return state.runSessionToken;
}

function isCurrentRunSession(token) {
  return token === state.runSessionToken;
}

function applyRunStatus(status) {
  state.lastStatus = status;
  updateTelemetry(status);
  drawScene(status);
}

function runCompletionTimeoutMs() {
  const selected = $("runtimeProfileSelect").value;
  if (selected === "rich_demo") return 90000;
  if (selected === "balanced_visual" || selected === "webots_fast") return 65000;
  return 30000;
}

function runStatusIsComplete(status) {
  if (!status) return false;
  if (["succeeded", "failed", "cancelled", "paused"].includes(status.state)) return true;
  if (status.route_completed) return true;
  const reason = String(status.reason || "");
  return Number(status.control_step_count || 0) > 0 && reason.includes("simulation runner");
}

async function waitForRunCompletion(
  runId, { timeoutMs = 30000, intervalMs = 650, onStatus = null } = {},
) {
  if (!runId) return null;
  const deadline = Date.now() + Math.max(1000, timeoutMs);
  let latest = null;
  while (Date.now() <= deadline) {
    await sleep(intervalMs);
    try {
      latest = await api(`/api/v1/control/${encodeURIComponent(runId)}`);
    } catch (error) {
      latest = null;
      continue;
    }
    if (latest && typeof onStatus === "function") onStatus(latest);
    if (runStatusIsComplete(latest)) return latest;
  }
  return latest && runStatusIsComplete(latest) ? latest : null;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, Math.max(0, ms)));
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
  if (!state.runId) {
    $("telemetryOutput").textContent = "还没有已启动的任务运行，暂无可查询回放。";
    return;
  }
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
  drawPlannedRoute(ctx, status);
  ctx.fillStyle = "#4b5563";
  ctx.font = "16px sans-serif";
  ctx.fillText(`地形：${terrainLabel(terrain)}`, 18, 28);
  state.obstacles.forEach((obstacle) => drawObstacle(ctx, obstacle));
  const base = status?.base_position || [0, 0, 0.32];
  drawRobot(ctx, Number(base[0]), Number(base[1]), Boolean(status?.obstacle_detected), status);
}

function drawTerrainRegions(ctx, terrain) {
  const keys = activeTerrainKeys(terrain);
  keys.forEach((key) => {
    const region = state.terrainRegions[key] || defaultTerrainRegions()[key];
    if (!region) return;
    drawTerrainRegion(ctx, key, region);
  });
}

function drawSemanticScene(ctx, terrain, status = null) {
  drawTerrainRegions(ctx, terrain);
  state.noGoZones.forEach((zone) => drawNoGoZone(ctx, zone));
  Object.values(state.checkpoints).forEach((marker) => drawCheckpoint(ctx, marker, status));
}

function drawPlannedRoute(ctx, status = null) {
  const route = plannedRouteFromStatus(status);
  if (route.length < 2) return;
  ctx.save();
  ctx.strokeStyle = "#dc2626";
  ctx.lineWidth = 3;
  ctx.setLineDash([10, 6]);
  ctx.beginPath();
  route.forEach((point, index) => {
    const p = canvasPoint(point.x, point.y);
    if (index === 0) ctx.moveTo(p.x, p.y);
    else ctx.lineTo(p.x, p.y);
  });
  ctx.stroke();
  ctx.setLineDash([]);
  route.forEach((point, index) => {
    const p = canvasPoint(point.x, point.y);
    ctx.fillStyle = point.isMissionTarget ? "#dc2626" : "#f97316";
    ctx.beginPath();
    ctx.arc(p.x, p.y, point.isMissionTarget ? 5 : 3, 0, Math.PI * 2);
    ctx.fill();
    if (!point.isMissionTarget && index % 2 === 0) {
      ctx.font = "11px sans-serif";
      ctx.fillText("via", p.x + 4, p.y - 4);
    }
  });
  ctx.restore();
}

function drawTerrainRegion(ctx, key, region) {
  const p = canvasPoint(Number(region.x), Number(region.y));
  const width = Math.max(0.05, Number(region.width)) * viewScale();
  const height = Math.max(0.05, Number(region.height)) * viewScale();
  const left = p.x - width / 2;
  const top = p.y - height / 2;
  if (key === "slope") {
    ctx.fillStyle = "rgba(71, 128, 71, 0.28)";
    ctx.strokeStyle = "#2f6b2f";
    ctx.fillRect(left, top, width, height);
    ctx.strokeRect(left, top, width, height);
    ctx.beginPath();
    ctx.moveTo(left + 12, top + height - 12);
    ctx.lineTo(left + width - 14, top + 12);
    ctx.stroke();
  } else if (key === "gravel") {
    ctx.fillStyle = "rgba(126, 111, 83, 0.28)";
    ctx.strokeStyle = "#5c4d33";
    ctx.fillRect(left, top, width, height);
    ctx.strokeRect(left, top, width, height);
    const rockRadius = Math.max(2, Number(region.roughness || 0.035) * viewScale() * 0.55);
    for (let i = 0; i < 18; i += 1) {
      const rx = left + ((i % 6) + 0.5) * width / 6;
      const ry = top + (Math.floor(i / 6) + 0.5) * height / 3;
      ctx.beginPath(); ctx.arc(rx, ry, rockRadius + (i % 3), 0, Math.PI * 2); ctx.fill();
    }
  } else if (key === "stairs") {
    ctx.fillStyle = "rgba(100, 100, 100, 0.28)";
    ctx.strokeStyle = "#555";
    const steps = Math.max(2, Math.min(8, Math.round(Number(region.stepCount || 5))));
    const stepWidth = width / steps;
    for (let i = 0; i < steps; i += 1) {
      const stepHeight = height * (0.35 + (i + 1) / steps * 0.50);
      ctx.fillRect(left + i * stepWidth, p.y - stepHeight / 2, stepWidth - 3, stepHeight);
      ctx.strokeRect(left + i * stepWidth, p.y - stepHeight / 2, stepWidth - 3, stepHeight);
    }
  }
  drawResizeHandles(ctx, left, top, width, height);
  ctx.fillStyle = key === "gravel" ? "#5c4d33" : key === "slope" ? "#2f6b2f" : "#555";
  ctx.font = "14px sans-serif";
  const detail = key === "slope" ? `${region.slopeDeg || 12}°` : key === "gravel" ? `${Number(region.roughness || 0.035).toFixed(3)}m` : `${region.stepCount || 5}级/${Number(region.stepHeight || 0.045).toFixed(3)}m`;
  ctx.fillText(`${region.label} · ${detail}`, left + 10, top + 22);
}

function drawResizeHandles(ctx, left, top, width, height) {
  if (!DRAW_EDIT_HANDLES) return;
  ctx.save();
  ctx.fillStyle = "#ffffff";
  ctx.strokeStyle = "#111827";
  const points = [
    [left, top], [left + width, top], [left, top + height], [left + width, top + height],
    [left + width / 2, top], [left + width / 2, top + height], [left, top + height / 2], [left + width, top + height / 2],
  ];
  points.forEach(([x, y]) => { ctx.fillRect(x - 3, y - 3, 6, 6); ctx.strokeRect(x - 3, y - 3, 6, 6); });
  ctx.restore();
}

function canvasPoint(x, y) {
  return { x: state.view.originX + x * viewScale(), y: state.view.originY - y * viewScale() };
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
  const x = (point.x - state.view.originX) / viewScale();
  const y = (state.view.originY - point.y) / viewScale();
  return { x, y };
}

function drawNoGoZone(ctx, zone) {
  const p = canvasPoint(Number(zone.x), Number(zone.y));
  const zoneWidth = Math.max(0.05, Number(zone.width)) * viewScale();
  const zoneHeight = Math.max(0.05, Number(zone.height)) * viewScale();
  ctx.fillStyle = "rgba(64, 98, 149, 0.20)";
  ctx.strokeStyle = "#315da8";
  ctx.lineWidth = 2;
  ctx.setLineDash([8, 5]);
  const left = p.x - zoneWidth / 2;
  const top = p.y - zoneHeight / 2;
  const pad = ROBOT_ROUTE_RADIUS * viewScale();
  if (DRAW_SAFETY_ENVELOPES) {
    ctx.strokeStyle = "rgba(220, 38, 38, 0.45)";
    ctx.strokeRect(left - pad, top - pad, zoneWidth + pad * 2, zoneHeight + pad * 2);
  }
  ctx.strokeStyle = "#315da8";
  ctx.fillRect(left, top, zoneWidth, zoneHeight);
  ctx.strokeRect(left, top, zoneWidth, zoneHeight);
  ctx.setLineDash([]);
  drawResizeHandles(ctx, left, top, zoneWidth, zoneHeight);
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
    const halfW = (PLATFORM_SIZE.width * viewScale()) / 2;
    const halfH = (PLATFORM_SIZE.height * viewScale()) / 2;
    ctx.fillRect(p.x - halfW, p.y - halfH, halfW * 2, halfH * 2);
    ctx.strokeRect(p.x - halfW, p.y - halfH, halfW * 2, halfH * 2);
  } else {
    ctx.beginPath();
    ctx.arc(p.x, p.y, CHECKPOINT_RADIUS * viewScale(), 0, Math.PI * 2);
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
    ctx.arc(p.x, p.y, isPlatform ? (PLATFORM_SIZE.width * viewScale()) / 2 + 8 : CHECKPOINT_RADIUS * viewScale() + 8, 0, Math.PI * 2);
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
  const radius = Math.max(8, metricSize * viewScale());
  if (DRAW_SAFETY_ENVELOPES) {
    ctx.save();
    ctx.strokeStyle = "rgba(220, 38, 38, 0.40)";
    ctx.setLineDash([6, 5]);
    if (obstacle.type === "box") {
      const halfSafe = Math.max(8, (metricSize * viewScale()) / 2 + ROBOT_ROUTE_RADIUS * viewScale());
      ctx.strokeRect(p.x - halfSafe, p.y - halfSafe, halfSafe * 2, halfSafe * 2);
    } else {
      ctx.beginPath();
      ctx.arc(p.x, p.y, radius + ROBOT_ROUTE_RADIUS * viewScale(), 0, Math.PI * 2);
      ctx.stroke();
    }
    ctx.restore();
  }
  ctx.fillStyle = "#e0832d";
  ctx.strokeStyle = "#8f3d11";
  ctx.lineWidth = 2;
  if (obstacle.type === "sphere") {
    ctx.beginPath(); ctx.arc(p.x, p.y, radius, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
  } else if (obstacle.type === "box") {
    const half = Math.max(8, (metricSize * viewScale()) / 2);
    ctx.fillRect(p.x - half, p.y - half, half * 2, half * 2);
    ctx.strokeRect(p.x - half, p.y - half, half * 2, half * 2);
  } else {
    ctx.beginPath(); ctx.ellipse(p.x, p.y, radius, radius * 0.75, 0, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
  }
  drawResizeHandles(ctx, p.x - radius, p.y - radius, radius * 2, radius * 2);
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
  const bodyHalfLength = (ROBOT_BODY.length * viewScale()) / 2;
  const bodyHalfWidth = (ROBOT_BODY.width * viewScale()) / 2;
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

function rectHit(world, item, edgeTolerance = 0.055) {
  const halfW = Math.max(0.05, Number(item.width)) / 2;
  const halfH = Math.max(0.05, Number(item.height)) / 2;
  const dx = world.x - Number(item.x);
  const dy = world.y - Number(item.y);
  if (Math.abs(dx) > halfW + edgeTolerance || Math.abs(dy) > halfH + edgeTolerance) return null;
  const nearLeft = Math.abs(dx + halfW) <= edgeTolerance;
  const nearRight = Math.abs(dx - halfW) <= edgeTolerance;
  const nearBottom = Math.abs(dy + halfH) <= edgeTolerance;
  const nearTop = Math.abs(dy - halfH) <= edgeTolerance;
  if (nearLeft || nearRight || nearTop || nearBottom) {
    return { resize: true, axisX: nearLeft || nearRight, axisY: nearTop || nearBottom };
  }
  if (Math.abs(dx) <= halfW && Math.abs(dy) <= halfH) return { resize: false };
  return null;
}

function findDraggableAt(clientX, clientY) {
  const world = worldPoint(clientX, clientY);
  for (let i = state.obstacles.length - 1; i >= 0; i -= 1) {
    const obstacle = state.obstacles[i];
    const radius = obstacle.type === "box" ? Math.max(0.12, (Number(obstacle.size) || 0.12) * 0.65) : Math.max(0.10, Number(obstacle.size) || 0.12);
    const distance = Math.hypot(world.x - Number(obstacle.x), world.y - Number(obstacle.y));
    if (Math.abs(distance - radius) <= 0.08) return { kind: "obstacle_resize", index: i };
    if (distance <= radius + 0.08) return { kind: "obstacle", index: i, offsetX: Number(obstacle.x) - world.x, offsetY: Number(obstacle.y) - world.y };
  }
  for (let i = state.noGoZones.length - 1; i >= 0; i -= 1) {
    const zone = state.noGoZones[i];
    const hit = rectHit(world, zone);
    if (!hit) continue;
    if (hit.resize) return { kind: "no_go_resize", index: i, axisX: hit.axisX, axisY: hit.axisY };
    return { kind: "no_go_zone", index: i, offsetX: Number(zone.x) - world.x, offsetY: Number(zone.y) - world.y };
  }
  const terrainKeys = activeTerrainKeys().slice().reverse();
  for (const key of terrainKeys) {
    const region = state.terrainRegions[key];
    if (!region) continue;
    const hit = rectHit(world, region);
    if (!hit) continue;
    if (hit.resize) return { kind: "terrain_resize", key, axisX: hit.axisX, axisY: hit.axisY };
    return { kind: "terrain", key, offsetX: Number(region.x) - world.x, offsetY: Number(region.y) - world.y };
  }
  for (const [key, marker] of Object.entries(state.checkpoints)) {
    const radius = marker.id === "platform" ? Math.max(PLATFORM_SIZE.width, PLATFORM_SIZE.height) * 0.5 : CHECKPOINT_RADIUS;
    if (Math.hypot(world.x - Number(marker.x), world.y - Number(marker.y)) <= radius + 0.08) {
      return { kind: "checkpoint", key, offsetX: Number(marker.x) - world.x, offsetY: Number(marker.y) - world.y };
    }
  }
  return null;
}

function updateDrag(clientX, clientY) {
  if (!state.drag) return;
  const world = worldPoint(clientX, clientY);
  if (state.drag.kind === "pan") {
    const point = clientCanvasPoint(clientX, clientY);
    state.view.originX = state.drag.originX + point.x - state.drag.startX;
    state.view.originY = state.drag.originY + point.y - state.drag.startY;
    drawScene(state.lastStatus);
    return;
  }
  const x = Number((world.x + (state.drag.offsetX || 0)).toFixed(2));
  const y = Number((world.y + (state.drag.offsetY || 0)).toFixed(2));
  if (state.drag.kind === "obstacle") {
    const item = state.obstacles[state.drag.index]; if (!item) return;
    item.x = x; item.y = y; syncObjectEditor("obstacle", state.drag.index, item);
  } else if (state.drag.kind === "obstacle_resize") {
    const item = state.obstacles[state.drag.index]; if (!item) return;
    const radius = Math.max(0.04, Math.min(0.60, Math.hypot(world.x - Number(item.x), world.y - Number(item.y))));
    item.size = Number(radius.toFixed(2));
    if (item.type === "box") item.height = Math.max(Number(item.height) || 0.3, item.size);
    syncObjectEditor("obstacle", state.drag.index, item);
  } else if (state.drag.kind === "checkpoint") {
    const item = state.checkpoints[state.drag.key]; if (!item) return;
    item.x = x; item.y = y; syncObjectEditor("checkpoint", state.drag.key, item);
  } else if (state.drag.kind === "no_go_zone") {
    const item = state.noGoZones[state.drag.index]; if (!item) return;
    item.x = x; item.y = y; syncObjectEditor("no_go_zone", state.drag.index, item);
  } else if (state.drag.kind === "no_go_resize") {
    const item = state.noGoZones[state.drag.index]; if (!item) return;
    if (state.drag.axisX) item.width = Number(Math.max(0.12, Math.abs(world.x - Number(item.x)) * 2).toFixed(2));
    if (state.drag.axisY) item.height = Number(Math.max(0.12, Math.abs(world.y - Number(item.y)) * 2).toFixed(2));
    syncObjectEditor("no_go_zone", state.drag.index, item);
  } else if (state.drag.kind === "terrain") {
    const item = state.terrainRegions[state.drag.key]; if (!item) return;
    item.x = x; item.y = y; syncObjectEditor("terrain", state.drag.key, item);
  } else if (state.drag.kind === "terrain_resize") {
    const item = state.terrainRegions[state.drag.key]; if (!item) return;
    if (state.drag.axisX) item.width = Number(Math.max(0.12, Math.abs(world.x - Number(item.x)) * 2).toFixed(2));
    if (state.drag.axisY) item.height = Number(Math.max(0.12, Math.abs(world.y - Number(item.y)) * 2).toFixed(2));
    syncObjectEditor("terrain", state.drag.key, item);
  }
  drawScene(state.lastStatus);
}

function syncObjectEditor(kind, keyOrIndex, item) {
  const selector = kind === "checkpoint"
    ? `.object-card[data-kind="checkpoint"][data-key="${CSS.escape(String(keyOrIndex))}"]`
    : kind === "terrain"
      ? `.object-card[data-kind="terrain"][data-key="${CSS.escape(String(keyOrIndex))}"]`
      : `.object-card[data-kind="${kind}"][data-index="${keyOrIndex}"]`;
  const card = document.querySelector(selector);
  if (!card) return;
  ["x", "y", "z", "size", "height", "width", "slopeDeg", "roughness", "stepHeight", "stepCount"].forEach((field) => {
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
  const platform = waypointPosition("platform") || { id: "platform", x: 0, y: 0, isMissionTarget: true };
  const normalized = targets.length === 0 || targets[0].id !== "platform" ? [platform, ...targets] : targets;
  return normalized.map((target) => ({ ...target, isMissionTarget: true }));
}

function taskPreviewFromInputText(text) {
  const source = String(text || "");
  const ids = [];
  const add = (id) => {
    const normalized = checkpointIdFromAsset(id);
    if (waypointPosition(normalized)) ids.push(normalized);
  };
  if (/平台|platform/i.test(source)) add("platform");
  Object.keys(state.checkpoints).forEach((id) => {
    if (id === "platform") return;
    const marker = state.checkpoints[id];
    const escapedId = id.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const escapedLabel = String(marker.label || id).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const pattern = new RegExp(`巡检${escapedId}|检查点${escapedId}|${escapedId}|${escapedLabel}`, "i");
    if (pattern.test(source)) add(id);
  });
  if (/回到平台|返回平台|平台待命|return_home/i.test(source)) add("platform");
  if (ids.length === 0) Object.keys(state.checkpoints).filter((id) => id !== "platform").forEach(add);
  if (ids[0] !== "platform") ids.unshift("platform");
  const waypoints = ids.filter((id, index) => index === 0 || id !== ids[index - 1]);
  return {
    task_id: `ui_${Date.now()}`,
    state: "running",
    goal: source.trim() || "网页控制台任务",
    waypoints,
    waypoint_details: waypoints.map((id) => ({ waypoint_id: id, label: state.checkpoints[id]?.label || id })),
    parse_confidence: 1.0,
    constraints: [],
    explanation: ["前端根据当前场景检查点生成即时播放路径；后端仍执行权威 TaskScript/C++ 控制闭环"],
  };
}

function pendingRunStatusFromTask(task) {
  const targets = routeTargetsFromTask(task);
  const first = targets[0] || { id: "platform", x: 0, y: 0 };
  const next = targets[1] || first;
  return {
    run_id: `pending_${Date.now()}`,
    state: "running",
    backend: $("backendSelect").value,
    runtime_profile: $("runtimeProfileSelect").value,
    base_position: [first.x, first.y, 0.35],
    risk_score: 0,
    terrain_class: $("terrainSelect").value,
    obstacle_detected: false,
    nearest_obstacle_distance_m: 0,
    gait_name: "cautious_trot",
    gait_phase: 0,
    gait_step_frequency_hz: 1.8,
    swing_foot_count: 2,
    stance_foot_count: 2,
    active_target_id: next.id,
    reached_target_ids: [],
    reached_target_count: 0,
    target_count: targets.filter((item) => item.isMissionTarget !== false).length,
    route_completed: false,
    route_progress_ratio: 0,
    target_distance_m: Math.hypot(next.x - first.x, next.y - first.y),
    planned_route: targets.map((target, index) => ({
      waypoint_id: target.id,
      target_id: target.id,
      source_target_id: target.id,
      x: target.x,
      y: target.y,
      mission_target_index: index,
      is_mission_target: true,
    })),
  };
}

function stripTaskExecutionFields(status) {
  const next = { ...(status || {}) };
  delete next.active_target_id;
  delete next.reached_target_ids;
  delete next.reached_target_count;
  delete next.target_count;
  delete next.route_completed;
  delete next.route_progress_ratio;
  delete next.target_distance_m;
  delete next.planned_route;
  return next;
}

function normalizeFinalRunStatus(status, task, fallbackStatus) {
  const planned = plannedRouteFromStatus(status);
  const fallbackRoute = plannedRouteFromStatus(fallbackStatus);
  const route = planned.length >= 2 ? planned : fallbackRoute;
  const finalTarget = route.length > 0 ? route[route.length - 1] : null;
  const normalized = {
    ...fallbackStatus,
    ...status,
    planned_route: route.length >= 2 ? route.map((point, index) => ({
      waypoint_id: point.id,
      target_id: point.id,
      source_target_id: point.sourceTargetId || point.id,
      x: point.x,
      y: point.y,
      mission_target_index: index,
      is_mission_target: point.isMissionTarget !== false,
    })) : fallbackStatus.planned_route,
  };
  if (finalTarget && normalized.route_completed) {
    normalized.base_position = [finalTarget.x, finalTarget.y, normalized.base_position?.[2] || 0.35];
    normalized.active_target_id = finalTarget.id;
    normalized.target_distance_m = 0;
  }
  normalized.target_count = normalized.target_count || routeTargetsFromTask(task).length;
  return normalized;
}

function plannedRouteFromStatus(status) {
  const route = Array.isArray(status?.planned_route) ? status.planned_route : [];
  const platform = waypointPosition("platform") || { id: "platform", x: 0, y: 0, isMissionTarget: true };
  const points = route
    .map((item) => {
      const fromPosition = Array.isArray(item.position) ? item.position : [];
      const waypointId = String(item.source_target_id || item.waypoint_id || item.target_id || "via");
      const x = item.x !== undefined ? Number(item.x) : Number(fromPosition[0]);
      const y = item.y !== undefined ? Number(item.y) : Number(fromPosition[1]);
      const missionFlag = item.is_mission_target ?? item.is_task_target ?? true;
      return {
        id: waypointId,
        x,
        y,
        isMissionTarget: Boolean(missionFlag),
        sourceTargetId: String(item.source_target_id || waypointId),
      };
    })
    .filter((item) => Number.isFinite(item.x) && Number.isFinite(item.y));
  if (points.length === 0) return points;
  const first = points[0];
  if (first.id !== "platform" && Math.hypot(first.x - platform.x, first.y - platform.y) > 0.02) {
    return [platform, ...points];
  }
  return points;
}

function animationTargets(task, finalStatus) {
  const planned = plannedRouteFromStatus(finalStatus);
  if (planned.length >= 2) return planned;
  return routeTargetsFromTask(task);
}

function stopRouteAnimation() {
  if (state.animationFrame) cancelAnimationFrame(state.animationFrame);
  state.animationFrame = 0;
  state.animationToken += 1;
}

function setRunTaskBusy(isBusy) {
  const button = $("runTaskBtn");
  if (!button) return;
  button.disabled = Boolean(isBusy);
  button.textContent = isBusy ? "运行中..." : "运行任务";
}

function startRouteAnimation(task, initialStatus, options = {}) {
  const targets = animationTargets(task, initialStatus);
  if (targets.length < 2) {
    state.lastStatus = initialStatus;
    updateTelemetry(initialStatus);
    drawScene(initialStatus);
    return Promise.resolve();
  }
  stopRouteAnimation();
  const token = state.animationToken + 1;
  state.animationToken = token;
  const segmentDurationMs = 1250;
  const totalDurationMs = Math.max(1800, (targets.length - 1) * segmentDurationMs);
  const startedAt = performance.now();
  const missionTargets = targets.filter((item) => item.isMissionTarget !== false);
  return new Promise((resolve) => {
    const animate = (now) => {
      if (token !== state.animationToken) {
        resolve();
        return;
      }
      const elapsed = Math.min(totalDurationMs, now - startedAt);
      const rawSegment = elapsed / segmentDurationMs;
      const segmentIndex = Math.min(targets.length - 2, Math.floor(rawSegment));
      const localT = Math.min(1, rawSegment - segmentIndex);
      const eased = localT < 0.5 ? 2 * localT * localT : 1 - ((-2 * localT + 2) ** 2) / 2;
      const from = targets[segmentIndex];
      const to = targets[segmentIndex + 1];
      const x = from.x + (to.x - from.x) * eased;
      const y = from.y + (to.y - from.y) * eased;
      const reached = targets.slice(0, segmentIndex + 1).filter((item) => item.isMissionTarget !== false).map((item) => item.id);
      const progress = Math.min(0.99, elapsed / totalDurationMs);
      const animatedStatus = {
        ...initialStatus,
        run_id: state.runId || initialStatus.run_id,
        state: "running",
        base_position: [x, y, initialStatus.base_position?.[2] || 0.35],
        active_target_id: to.id,
        reached_target_ids: reached,
        reached_target_count: reached.length,
        target_count: initialStatus.target_count || missionTargets.length,
        route_completed: false,
        route_progress_ratio: progress,
        target_distance_m: Math.hypot(to.x - x, to.y - y),
        gait_phase: (elapsed / 1000) % 1,
        gait_name: initialStatus.gait_name || "cautious_trot",
        gait_step_frequency_hz: initialStatus.gait_step_frequency_hz || 1.8,
        swing_foot_count: initialStatus.swing_foot_count || 2,
        stance_foot_count: initialStatus.stance_foot_count || 2,
      };
      state.lastStatus = animatedStatus;
      updateTelemetry(animatedStatus);
      drawScene(animatedStatus);
      if (elapsed < totalDurationMs) {
        state.animationFrame = requestAnimationFrame(animate);
      } else {
        state.animationFrame = 0;
        if (!options.waitForFinalStatus || state.pendingRunStatus) {
          resolve();
          return;
        }
        resolve();
      }
    };
    state.animationFrame = requestAnimationFrame(animate);
  });
}

function bindSceneDragging() {
  const canvas = $("sceneCanvas");
  canvas.addEventListener("pointerdown", (event) => {
    state.drag = findDraggableAt(event.clientX, event.clientY);
    if (!state.drag) {
      const point = clientCanvasPoint(event.clientX, event.clientY);
      state.drag = { kind: "pan", startX: point.x, startY: point.y, originX: state.view.originX, originY: state.view.originY };
    }
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
  canvas.addEventListener("wheel", (event) => {
    event.preventDefault();
    const point = clientCanvasPoint(event.clientX, event.clientY);
    const before = { x: (point.x - state.view.originX) / viewScale(), y: (state.view.originY - point.y) / viewScale() };
    const factor = event.deltaY < 0 ? 1.12 : 0.89;
    state.view.scale = Math.max(70, Math.min(420, viewScale() * factor));
    state.view.originX = point.x - before.x * viewScale();
    state.view.originY = point.y + before.y * viewScale();
    drawScene(state.lastStatus);
  }, { passive: false });
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

$("terrainSelect").addEventListener("change", () => { renderTerrainRegionList(); drawScene(state.lastStatus); });
$("sceneNameInput").addEventListener("input", () => setSceneName($("sceneNameInput").value, { resetRef: true }));

bindSceneDragging();
resetDefaultScene();
loadCatalog();