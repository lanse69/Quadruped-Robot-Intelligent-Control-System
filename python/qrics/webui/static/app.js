const headers = (role = "operator") => ({
  "content-type": "application/json",
  "x-request-id": `web-${Date.now()}`,
  "x-actor-id": "web-console",
  "x-actor-role": role,
});

const WORLD_SCALE = 185;
const WORLD_ORIGIN = { x: 98, y: 245 };

const state = {
  sceneRef: { id: "minimal_scene", version: "0.1.0" },
  runId: "",
  obstacles: [],
  checkpoints: {},
  noGoZone: { x: 2.45, y: 0.0, width: 1.15, height: 1.65 },
  drag: null,
  lastStatus: null,
  lastSceneSignature: "",
};

const $ = (id) => document.getElementById(id);

function obstacleTemplate(type) {
  const index = state.obstacles.length + 1;
  const base = {
    id: `${type}_${index}`,
    type,
    x: 0.55 + index * 0.22,
    y: index % 2 === 0 ? -0.25 : 0.22,
    z: type === "sphere" ? 0.18 : 0.2,
    size: type === "box" ? 0.26 : 0.16,
    height: type === "cylinder" ? 0.38 : 0.24,
  };
  return base;
}

function resetDefaultScene() {
  state.checkpoints = {
    platform: { id: "platform", label: "平台", x: 0.0, y: 0.0 },
    A: { id: "A", label: "A", x: 0.90, y: 0.34 },
    B: { id: "B", label: "B", x: 1.85, y: -0.30 },
  };
  state.noGoZone = { x: 2.45, y: 0.0, width: 1.15, height: 1.65 };
  state.obstacles = [
    { id: "演示箱体", type: "box", x: 1.12, y: 0.68, z: 0.14, size: 0.20, height: 0.22 },
    { id: "演示圆柱", type: "cylinder", x: 1.48, y: -0.62, z: 0.15, size: 0.09, height: 0.30 },
    { id: "演示球体", type: "sphere", x: 2.20, y: 0.50, z: 0.12, size: 0.12, height: 0.12 },
  ];
  renderObstacleList();
  drawScene();
}

function renderObstacleList() {
  const root = $("obstacleList");
  root.innerHTML = "";
  state.obstacles.forEach((obstacle, index) => {
    const card = document.createElement("div");
    card.className = "obstacle-card";
    card.innerHTML = `
      <label>ID<input data-field="id" value="${obstacle.id}" /></label>
      <label>类型<select data-field="type">
        <option value="box">箱体</option><option value="cylinder">圆柱</option><option value="sphere">球体</option>
      </select></label>
      <label>X<input data-field="x" type="number" step="0.05" value="${obstacle.x}" /></label>
      <label>Y<input data-field="y" type="number" step="0.05" value="${obstacle.y}" /></label>
      <label>Z<input data-field="z" type="number" step="0.05" value="${obstacle.z}" /></label>
      <label>尺寸<input data-field="size" type="number" step="0.01" value="${obstacle.size}" /></label>
      <button data-action="remove">删除</button>`;
    card.querySelector("select").value = obstacle.type;
    card.querySelectorAll("input, select").forEach((input) => {
      input.addEventListener("input", () => {
        const field = input.dataset.field;
        if (!field) return;
        state.obstacles[index][field] = ["x", "y", "z", "size"].includes(field)
          ? Number(input.value)
          : input.value;
        drawScene();
      });
    });
    card.querySelector("button").addEventListener("click", () => {
      state.obstacles.splice(index, 1);
      renderObstacleList();
      drawScene();
    });
    root.appendChild(card);
  });
}

function scenePayload() {
  const terrain = $("terrainSelect").value;
  const assets = [
    {
      asset_id: `${terrain}_terrain`,
      asset_type: "terrain",
      uri: `builtin://qrics/terrain/${terrain}`,
      checksum: `builtin-${terrain}`,
    },
    { asset_id: "巡检点A", asset_type: "checkpoint", uri: "builtin://qrics/checkpoint/A", checksum: "builtin-checkpoint-A", position: [state.checkpoints.A.x, state.checkpoints.A.y, 0.02] },
    { asset_id: "巡检点B", asset_type: "checkpoint", uri: "builtin://qrics/checkpoint/B", checksum: "builtin-checkpoint-B", position: [state.checkpoints.B.x, state.checkpoints.B.y, 0.02] },
    { asset_id: "平台", asset_type: "checkpoint", uri: "builtin://qrics/checkpoint/platform", checksum: "builtin-platform", position: [state.checkpoints.platform.x, state.checkpoints.platform.y, 0.02] },
    { asset_id: "低摩擦区", asset_type: "no_go_zone", uri: "builtin://qrics/no_go_zone/low_friction", checksum: "builtin-low-friction-zone", position: [state.noGoZone.x, state.noGoZone.y, 0.01], size: [state.noGoZone.width, state.noGoZone.height, 0.02] },
    ...state.obstacles.map((obstacle) => {
      const size = Number(obstacle.size) || 0.16;
      const common = {
        asset_id: obstacle.id,
        asset_type: "obstacle",
        geometry_type: obstacle.type,
        position: [Number(obstacle.x), Number(obstacle.y), Number(obstacle.z)],
        checksum: `inline-${obstacle.type}-${obstacle.id}`,
      };
      if (obstacle.type === "box") {
        return { ...common, size: [size, size, Number(obstacle.height) || size] };
      }
      if (obstacle.type === "sphere") {
        return { ...common, radius_m: size, height_m: size };
      }
      return { ...common, radius_m: size, height_m: Number(obstacle.height) || 0.38 };
    }),
  ];
  return {
    scene_id: $("sceneIdInput").value.trim() || "local_demo_scene",
    version: $("sceneVersionInput").value.trim() || "0.1.0",
    name: "QRICS Web Console local scene",
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
      friction_range: terrain === "gravel" ? [0.55, 0.95] : [0.8, 1.1],
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
    terrain_pack: scene.terrain_pack,
    assets,
  };
}

function sceneComparable(payload) {
  return JSON.stringify(comparableSceneObject(payload));
}

function existingComparable(existing) {
  return JSON.stringify(comparableSceneObject(existing));
}

function nextSceneVersion(baseVersion) {
  const prefix = String(baseVersion || "0.1.0").split("+")[0];
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
  if (target.run_id) lines.push(`运行编号：${target.run_id}`);
  if (target.state) lines.push(`状态：${stateLabel(target.state)}`);
  if (target.backend) lines.push(`仿真后端：${optionLabel(target.backend)}`);
  if (target.runtime_profile) lines.push(`运行模式：${optionLabel(target.runtime_profile)}`);
  if (target.terrain_class) lines.push(`地形识别：${terrainLabel(target.terrain_class)}`);
  if (Array.isArray(target.base_position)) lines.push(`机器人位置：${target.base_position.map((v) => Number(v).toFixed(2)).join(", ")}`);
  if (target.risk_score !== undefined) lines.push(`风险值：${target.risk_score}`);
  if (target.obstacle_detected !== undefined) lines.push(`障碍感知：${target.obstacle_detected ? "检测到" : "未检测"}`);
  if (target.presentation_pid) lines.push(`仿真窗口进程：${target.presentation_pid}`);
  if (target.presentation_command_path) lines.push(`窗口命令文件：${target.presentation_command_path}`);
  if (data.task?.waypoints) lines.push(`任务路径点：${data.task.waypoints.join(" → ")}`);
  lines.push("", "原始接口证据：", JSON.stringify(data, null, 2));
  return lines.join("\n");
}

function stateLabel(value) {
  const labels = {
    running: "运行中",
    succeeded: "已完成",
    failed: "失败",
    paused: "暂停",
    cancelled: "已取消",
    preview_ready: "预览就绪",
    confirmed: "已确认",
    handed_off: "已移交控制",
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

async function loadCatalog() {
  const status = $("serviceStatus");
  try {
    await api("/api/v1/health");
    const catalog = await api("/api/v1/sim/backends");
    fillSelect("backendSelect", catalog.backends, $("backendSelect").value);
    fillSelect("runtimeProfileSelect", catalog.runtime_profiles, $("runtimeProfileSelect").value);
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

async function saveScene() {
  const payload = scenePayload();
  const signature = sceneComparable(payload);
  try {
    const saved = await api("/api/v1/scenes", { method: "POST", body: payload, role: "test_engineer" });
    state.sceneRef = { id: saved.scene_id, version: saved.scene_version };
    state.lastSceneSignature = signature;
    $("sceneRefLabel").textContent = `${saved.scene_id}:${saved.scene_version}（已保存）`;
    $("taskOutput").textContent = formatEvidence("场景保存成功", saved);
    return saved;
  } catch (error) {
    if (!String(error).includes("Scene already exists")) throw error;
    const existing = await api(`/api/v1/scenes/${payload.scene_id}/${payload.version}`);
    if (existingComparable(existing) === signature) {
      state.sceneRef = { id: payload.scene_id, version: payload.version };
      state.lastSceneSignature = signature;
      $("sceneRefLabel").textContent = `${payload.scene_id}:${payload.version}（已存在，内容一致）`;
      $("taskOutput").textContent = formatEvidence("场景已存在且内容一致", existing);
      return existing;
    }
    const versionedPayload = { ...payload, version: nextSceneVersion(payload.version), change_summary: "网页控制台自动创建新场景版本" };
    const saved = await api("/api/v1/scenes", { method: "POST", body: versionedPayload, role: "test_engineer" });
    $("sceneVersionInput").value = saved.scene_version;
    state.sceneRef = { id: saved.scene_id, version: saved.scene_version };
    state.lastSceneSignature = sceneComparable(versionedPayload);
    $("sceneRefLabel").textContent = `${saved.scene_id}:${saved.scene_version}（已自动新建版本）`;
    $("taskOutput").textContent = formatEvidence("场景已自动新建版本", saved);
    return saved;
  }
}

async function previewScene() {
  await saveScene();
  const data = await api("/api/v1/sim/preview", {
    method: "POST",
    body: { scene_ref: state.sceneRef, run_options: { ...runOptions(), step_count: Math.max(60, Math.min(240, runOptions().step_count)) } },
  });
  state.lastStatus = data;
  updateTelemetry(data);
  $("telemetryOutput").textContent = formatEvidence("仿真预览完成", data);
  drawScene(data);
}

async function runTask() {
  await saveScene();
  const task = await api("/api/v1/tasks", {
    method: "POST",
    body: { source_text: $("taskText").value, scene_ref: state.sceneRef, require_confirmation: true },
  });
  await api(`/api/v1/tasks/${task.task_id}/confirm`, { method: "POST" });
  const status = await api(`/api/v1/tasks/${task.task_id}/handoff`, {
    method: "POST",
    body: { run_options: runOptions() },
  });
  state.runId = status.run_id;
  state.lastStatus = status;
  updateTelemetry(status);
  $("taskOutput").textContent = formatEvidence("任务运行已启动", { task, status });
  await refreshReplay();
  drawScene(status);
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
  drawSemanticScene(ctx, terrain);
  ctx.fillStyle = "#4b5563";
  ctx.font = "16px sans-serif";
  ctx.fillText(`地形：${terrainLabel(terrain)}`, 18, 28);
  state.obstacles.forEach((obstacle) => drawObstacle(ctx, obstacle));
  const base = status?.base_position || [0, 0, 0.32];
  drawRobot(ctx, Number(base[0]), Number(base[1]), Boolean(status?.obstacle_detected));
}

function drawSemanticScene(ctx, terrain) {
  const low = canvasPoint(state.noGoZone.x, state.noGoZone.y);
  const lowWidth = state.noGoZone.width * WORLD_SCALE;
  const lowHeight = state.noGoZone.height * WORLD_SCALE;
  ctx.fillStyle = "rgba(64, 98, 149, 0.20)";
  ctx.strokeStyle = "#315da8";
  ctx.lineWidth = 2;
  ctx.setLineDash([8, 5]);
  ctx.fillRect(low.x - lowWidth / 2, low.y - lowHeight / 2, lowWidth, lowHeight);
  ctx.strokeRect(low.x - lowWidth / 2, low.y - lowHeight / 2, lowWidth, lowHeight);
  ctx.setLineDash([]);
  ctx.fillStyle = "#234073";
  ctx.font = "14px sans-serif";
  ctx.fillText("低摩擦区 / 禁行提示（区域，不是障碍物）", low.x - 120, low.y - lowHeight / 2 - 8);

  Object.values(state.checkpoints).forEach((marker) => drawCheckpoint(ctx, marker));

  if (terrain === "slope") {
    ctx.fillStyle = "rgba(71, 128, 71, 0.28)";
    ctx.fillRect(260, 90, 240, 110);
    ctx.fillStyle = "#2f6b2f";
    ctx.fillText("坡面区域", 340, 150);
  } else if (terrain === "gravel" || terrain === "mixed_terrain_pack") {
    ctx.fillStyle = "rgba(126, 111, 83, 0.28)";
    ctx.fillRect(245, 220, 260, 120);
    ctx.fillStyle = "#5c4d33";
    ctx.fillText("碎石区域", 330, 285);
  } else if (terrain === "stairs") {
    ctx.fillStyle = "rgba(100, 100, 100, 0.28)";
    for (let i = 0; i < 4; i += 1) ctx.fillRect(260 + i * 45, 250 - i * 18, 42, 30 + i * 18);
    ctx.fillStyle = "#555";
    ctx.fillText("台阶区域", 340, 230);
  }
}

function canvasPoint(x, y) {
  return { x: WORLD_ORIGIN.x + x * WORLD_SCALE, y: WORLD_ORIGIN.y - y * WORLD_SCALE };
}

function worldPoint(clientX, clientY) {
  const rect = $("sceneCanvas").getBoundingClientRect();
  const x = (clientX - rect.left - WORLD_ORIGIN.x) / WORLD_SCALE;
  const y = (WORLD_ORIGIN.y - (clientY - rect.top)) / WORLD_SCALE;
  return { x, y };
}

function drawCheckpoint(ctx, marker) {
  const p = canvasPoint(Number(marker.x), Number(marker.y));
  const isPlatform = marker.id === "platform";
  ctx.strokeStyle = isPlatform ? "#1f6feb" : marker.id === "A" ? "#21a366" : "#c88719";
  ctx.fillStyle = isPlatform ? "rgba(31,111,235,0.14)" : "rgba(255,255,255,0.82)";
  ctx.lineWidth = 3;
  if (isPlatform) {
    ctx.fillRect(p.x - 42, p.y - 30, 84, 60);
    ctx.strokeRect(p.x - 42, p.y - 30, 84, 60);
  } else {
    ctx.beginPath();
    ctx.arc(p.x, p.y, 15, 0, Math.PI * 2);
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
  ctx.fillStyle = "#111827";
  ctx.font = "15px sans-serif";
  ctx.fillText(marker.label, p.x + 18, p.y - 10);
}

function drawObstacle(ctx, obstacle) {
  const p = canvasPoint(Number(obstacle.x), Number(obstacle.y));
  const size = Math.max(12, Number(obstacle.size) * 180);
  ctx.fillStyle = "#e0832d";
  ctx.strokeStyle = "#8f3d11";
  ctx.lineWidth = 2;
  if (obstacle.type === "sphere") {
    ctx.beginPath(); ctx.arc(p.x, p.y, size, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
  } else if (obstacle.type === "box") {
    ctx.fillRect(p.x - size, p.y - size, size * 2, size * 2); ctx.strokeRect(p.x - size, p.y - size, size * 2, size * 2);
  } else {
    ctx.beginPath(); ctx.ellipse(p.x, p.y, size, size * 0.75, 0, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
  }
  ctx.fillStyle = "#4a2b13";
  ctx.font = "12px sans-serif";
  ctx.fillText(obstacle.id, p.x + size + 4, p.y + 4);
}

function drawRobot(ctx, x, y, risk) {
  const p = canvasPoint(x, y);
  ctx.fillStyle = "#1f6feb";
  ctx.strokeStyle = risk ? "#c62834" : "#0b3d91";
  ctx.lineWidth = risk ? 5 : 2;
  ctx.beginPath();
  ctx.moveTo(p.x + 24, p.y);
  ctx.lineTo(p.x - 18, p.y - 16);
  ctx.lineTo(p.x - 18, p.y + 16);
  ctx.closePath();
  ctx.fill();
  ctx.stroke();
  ctx.fillStyle = "#0d2442";
  ctx.font = "13px sans-serif";
  ctx.fillText("四足机器人", p.x - 30, p.y + 34);
}

function findDraggableAt(clientX, clientY) {
  const world = worldPoint(clientX, clientY);
  for (let i = state.obstacles.length - 1; i >= 0; i -= 1) {
    const obstacle = state.obstacles[i];
    const radius = Math.max(0.10, Number(obstacle.size) || 0.12);
    if (Math.hypot(world.x - Number(obstacle.x), world.y - Number(obstacle.y)) <= radius + 0.08) {
      return { kind: "obstacle", index: i, offsetX: Number(obstacle.x) - world.x, offsetY: Number(obstacle.y) - world.y };
    }
  }
  for (const marker of Object.values(state.checkpoints)) {
    const radius = marker.id === "platform" ? 0.24 : 0.15;
    if (Math.hypot(world.x - Number(marker.x), world.y - Number(marker.y)) <= radius + 0.08) {
      return { kind: "checkpoint", id: marker.id, offsetX: Number(marker.x) - world.x, offsetY: Number(marker.y) - world.y };
    }
  }
  if (Math.abs(world.x - state.noGoZone.x) <= state.noGoZone.width / 2 && Math.abs(world.y - state.noGoZone.y) <= state.noGoZone.height / 2) {
    return { kind: "no_go_zone", offsetX: state.noGoZone.x - world.x, offsetY: state.noGoZone.y - world.y };
  }
  return null;
}

function updateDrag(clientX, clientY) {
  if (!state.drag) return;
  const world = worldPoint(clientX, clientY);
  const x = Number((world.x + state.drag.offsetX).toFixed(2));
  const y = Number((world.y + state.drag.offsetY).toFixed(2));
  if (state.drag.kind === "obstacle") {
    state.obstacles[state.drag.index].x = x;
    state.obstacles[state.drag.index].y = y;
  } else if (state.drag.kind === "checkpoint") {
    state.checkpoints[state.drag.id].x = x;
    state.checkpoints[state.drag.id].y = y;
  } else if (state.drag.kind === "no_go_zone") {
    state.noGoZone.x = x;
    state.noGoZone.y = y;
  }
  drawScene(state.lastStatus);
}

function bindSceneDragging() {
  const canvas = $("sceneCanvas");
  canvas.addEventListener("mousedown", (event) => {
    state.drag = findDraggableAt(event.clientX, event.clientY);
    canvas.classList.toggle("dragging", Boolean(state.drag));
  });
  canvas.addEventListener("mousemove", (event) => {
    if (!state.drag) return;
    updateDrag(event.clientX, event.clientY);
  });
  const stop = () => {
    if (state.drag?.kind === "obstacle") renderObstacleList();
    state.drag = null;
    canvas.classList.remove("dragging");
  };
  canvas.addEventListener("mouseup", stop);
  canvas.addEventListener("mouseleave", stop);
}

function bind(id, handler) {
  $(id).addEventListener("click", async () => {
    try { await handler(); } catch (error) { $("telemetryOutput").textContent = String(error); }
  });
}

bind("loadCatalogBtn", loadCatalog);
bind("addBoxBtn", () => { state.obstacles.push(obstacleTemplate("box")); renderObstacleList(); drawScene(); });
bind("addCylinderBtn", () => { state.obstacles.push(obstacleTemplate("cylinder")); renderObstacleList(); drawScene(); });
bind("addSphereBtn", () => { state.obstacles.push(obstacleTemplate("sphere")); renderObstacleList(); drawScene(); });
bind("resetSceneBtn", resetDefaultScene);
bind("saveSceneBtn", saveScene);
bind("previewSceneBtn", previewScene);
bind("runTaskBtn", runTask);
bind("emergencyStopBtn", () => override("emergency_stop", "网页控制台触发急停"));
bind("safeStandBtn", () => override("safe_stand", "网页控制台触发安全站立"));
bind("refreshReplayBtn", refreshReplay);
bind("refreshAuditBtn", refreshAudit);
bind("refreshEventsBtn", refreshEvents);

$("backendSelect").addEventListener("change", () => {
  if ($("backendSelect").value === "webots") $("runtimeProfileSelect").value = "webots_fast";
  if ($("backendSelect").value === "mujoco") $("runtimeProfileSelect").value = "balanced_visual";
  if ($("backendSelect").value === "minimal") $("runtimeProfileSelect").value = "headless_fast";
});

bindSceneDragging();
resetDefaultScene();
loadCatalog();