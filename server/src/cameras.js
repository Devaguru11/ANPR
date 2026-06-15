
const CAMERA_REGISTRY = [
  {
    id: "AEYE_1",
    name: "Highway",
  },
  {
    id: "AEYE_2",
    name: "Luvers",
    streamUrl: "rtsp://122.55.178.78:8554/live/liveStream_9F0377EPAG7663A_0_0",
  },
  {
    id: "AEYE_3",
    name: "Market",
  },
  {
    id: "AEYE_4",
    name: "Baliwag",
    streamUrl: "rtsp://122.55.178.78:8554/live/liveStream_9F0377EPAG4DE6C_0_0",
  },
  {
    id: "AEYE_5",
    name: "Chowking",
    streamUrl: "rtsp://122.55.178.78:8554/live/liveStream_8L0D58DPAGBD6D0_0_0",
  },
  {
    id: "AEYE_6",
    name: "Bridge",
    streamUrl: "rtsp://122.55.178.78:8554/live/liveStream_9F0377EPAG35579_0_0",
  },
];

function normalizeCameraId(v) {
  if (v == null) return "";
  if (typeof v === "object" && Buffer.isBuffer(v)) {
    return v.toString("utf8").replace(/\0+$/g, "").replace(/\0/g, "").trim();
  }
  return String(v)
    .replace(/\0+$/g, "")
    .replace(/\0/g, "")
    .trim();
}

function getCameraMap() {
  const map = {};
  for (const c of CAMERA_REGISTRY) {
    map[c.id] = c.name;
  }
  return map;
}

function mergeCameraMap(extraIds = []) {
  const map = { ...getCameraMap() };
  const known = new Set(Object.keys(map));
  for (const raw of extraIds) {
    const id = normalizeCameraId(raw);
    if (!id || known.has(id)) continue;
    const alias = Object.keys(map).find((k) => k.toLowerCase() === id.toLowerCase());
    if (alias) continue;
    map[id] = id;
    known.add(id);
  }
  return map;
}

const LEGACY_CAMERA_ALIASES = {
  Total: "Baliwag",
  Julieta: "Baliwag",
  AEYE_4: "Baliwag",
};

function resolveCameraName(cameraId, map) {
  const id = normalizeCameraId(cameraId);
  if (!id) return "";
  if (LEGACY_CAMERA_ALIASES[id]) return LEGACY_CAMERA_ALIASES[id];
  if (map[id]) return LEGACY_CAMERA_ALIASES[map[id]] || map[id];
  const hit = Object.keys(map).find((k) => k.toLowerCase() === id.toLowerCase());
  const resolved = hit ? map[hit] : id;
  return LEGACY_CAMERA_ALIASES[resolved] || resolved;
}

function listCameraRegistry() {
  return CAMERA_REGISTRY.map((c) => ({ id: c.id, name: c.name, hasStream: Boolean(c.streamUrl) }));
}

function listStreamConfigs() {
  return CAMERA_REGISTRY.filter((c) => c.streamUrl).map((c) => ({
    id: c.id,
    name: c.name,
    url: c.streamUrl,
  }));
}

async function loadMergedCameraMap(pool) {
  let dbIds = [];
  try {
    const [rows] = await pool.query(`SELECT DISTINCT camera_id FROM vehicle_events`);
    dbIds = (rows || []).map((r) => r.camera_id);
  } catch {

  }
  return mergeCameraMap(dbIds);
}

function camerasWithCounts(camRows, cameraMap) {
  const totals = new Map();
  for (const r of camRows || []) {
    const id = normalizeCameraId(r.camera_id);
    if (!id) continue;
    totals.set(id, Number(r.total || 0));
  }

  const order = Object.keys(cameraMap);
  const out = order.map((id) => ({
    camera_id: id,
    name: resolveCameraName(id, cameraMap),
    total: totals.get(id) ?? totals.get(normalizeCameraId(id)) ?? 0,
  }));

  for (const [id, total] of totals) {
    if (!order.includes(id)) {
      out.push({
        camera_id: id,
        name: resolveCameraName(id, cameraMap),
        total,
      });
    }
  }
  return out.sort((a, b) => b.total - a.total);
}

module.exports = {
  CAMERA_REGISTRY,
  normalizeCameraId,
  getCameraMap,
  mergeCameraMap,
  resolveCameraName,
  listCameraRegistry,
  listStreamConfigs,
  loadMergedCameraMap,
  camerasWithCounts,
};
