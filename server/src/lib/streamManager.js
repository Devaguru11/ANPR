const path = require("path");
const fs = require("fs");
const os = require("os");
const { spawn } = require("child_process");

const { listStreamConfigs } = require("../cameras");

const STREAMS = listStreamConfigs();

const HLS_BASE = path.join(os.tmpdir(), "anpr-streams");
const IDLE_KILL_MS = 60_000;
const STATUS_TTL_MS = 15_000;
const NEGATIVE_TTL_MS = 5_000;
const PROBE_TIMEOUT_MS = 8_000;

fs.mkdirSync(HLS_BASE, { recursive: true });

const procs = new Map();

const statusCache = new Map();

const inFlightChecks = new Map();

let probeQueue = Promise.resolve();

function listStreams() {
  return STREAMS.map((s) => ({ id: s.id, name: s.name, url: s.url }));
}

function getStreamById(id) {
  return STREAMS.find((s) => s.id === id);
}

function hlsDir(id) {
  return path.join(HLS_BASE, id);
}

function touchStream(id) {
  const p = procs.get(id);
  if (p) p.lastTouch = Date.now();
}

function killStream(id) {
  const p = procs.get(id);
  if (!p) return;
  procs.delete(id);
  try {
    p.proc.kill("SIGKILL");
  } catch {

  }
  try {
    fs.rmSync(p.dir, { recursive: true, force: true });
  } catch {

  }
}

setInterval(() => {
  const now = Date.now();
  for (const [id, p] of procs.entries()) {
    if (now - p.lastTouch > IDLE_KILL_MS) {
      killStream(id);
    }
  }
}, 15_000).unref?.();

process.on("exit", () => {
  for (const id of [...procs.keys()]) killStream(id);
});
process.on("SIGINT", () => process.exit(0));
process.on("SIGTERM", () => process.exit(0));

function ensureStreamRunning(id) {
  const stream = getStreamById(id);
  if (!stream) return null;
  const existing = procs.get(id);
  if (existing && !existing.proc.killed) {
    existing.lastTouch = Date.now();
    return existing;
  }

  const dir = hlsDir(id);
  fs.mkdirSync(dir, { recursive: true });

  for (const f of fs.readdirSync(dir)) {
    try { fs.unlinkSync(path.join(dir, f)); } catch {  }
  }

  const args = [
    "-loglevel", "error",
    "-fflags", "nobuffer",
    "-rtsp_transport", "tcp",
    "-stimeout", "5000000",
    "-i", stream.url,
    "-an",
    "-c:v", "copy",
    "-f", "hls",
    "-hls_time", "2",
    "-hls_list_size", "4",
    "-hls_flags", "delete_segments+independent_segments+omit_endlist",
    "-hls_segment_type", "mpegts",
    "-hls_segment_filename", path.join(dir, "seg%05d.ts"),
    path.join(dir, "index.m3u8"),
  ];

  const proc = spawn("ffmpeg", args, { stdio: ["ignore", "ignore", "pipe"] });
  const entry = { proc, dir, lastTouch: Date.now(), startedAt: Date.now() };
  procs.set(id, entry);

  let errBuf = "";
  proc.stderr.on("data", (d) => {
    errBuf += String(d);
    if (errBuf.length > 4_000) errBuf = errBuf.slice(-4_000);
  });
  proc.on("exit", (code) => {

    if (code !== 0 && code !== null) console.warn(`[stream ${id}] ffmpeg exited code=${code} tail=`, errBuf.slice(-400));
    if (procs.get(id) === entry) procs.delete(id);
  });

  return entry;
}

function isHlsProcessHealthy(id) {
  const p = procs.get(id);
  if (!p || p.proc.killed) return false;
  try {
    const playlist = path.join(p.dir, "index.m3u8");
    if (!fs.existsSync(playlist)) return false;
    const stat = fs.statSync(playlist);
    return Date.now() - stat.mtimeMs < 10_000;
  } catch {
    return false;
  }
}

function checkStreamStatus(id, force = false) {
  const stream = getStreamById(id);
  if (!stream) return Promise.resolve({ id, online: false, checkedAt: Date.now(), error: "unknown" });

  if (isHlsProcessHealthy(id)) {
    const entry = { online: true, checkedAt: Date.now(), error: null };
    statusCache.set(id, entry);
    return Promise.resolve({ id, ...entry });
  }

  if (!force) {
    const cached = statusCache.get(id);
    const ttl = cached?.online ? STATUS_TTL_MS : NEGATIVE_TTL_MS;
    if (cached && Date.now() - cached.checkedAt < ttl) {
      return Promise.resolve({ id, ...cached });
    }
  }
  const inflight = inFlightChecks.get(id);
  if (inflight) return inflight;

  const runProbe = () =>
    new Promise((resolve) => {

      if (isHlsProcessHealthy(id)) {
        const entry = { online: true, checkedAt: Date.now(), error: null };
        statusCache.set(id, entry);
        return resolve({ id, ...entry });
      }

      const args = [
        "-v", "error",
        "-rtsp_transport", "tcp",
        "-stimeout", "5000000",
        "-show_streams",
        "-of", "json",
        stream.url,
      ];
      const proc = spawn("ffprobe", args, { stdio: ["ignore", "pipe", "pipe"] });
      let stdout = "";
      let stderr = "";
      let settled = false;

      const finalize = (online, error) => {
        if (settled) return;
        settled = true;
        const entry = { online, checkedAt: Date.now(), error: error || null };
        statusCache.set(id, entry);
        resolve({ id, ...entry });
      };

      const timer = setTimeout(() => {
        try { proc.kill("SIGKILL"); } catch {  }
        finalize(false, "timeout");
      }, PROBE_TIMEOUT_MS);

      proc.stdout.on("data", (d) => { stdout += String(d); });
      proc.stderr.on("data", (d) => { stderr += String(d); });
      proc.on("error", () => {
        clearTimeout(timer);
        finalize(false, "spawn_error");
      });
      proc.on("close", (code) => {
        clearTimeout(timer);
        if (code === 0) {
          try {
            const json = JSON.parse(stdout || "{}");
            const hasVideo = (json.streams || []).some((s) => s.codec_type === "video");
            finalize(hasVideo, hasVideo ? null : "no_video");
          } catch (e) {
            finalize(false, "parse_error");
          }
        } else {
          finalize(false, stderr.slice(-200) || `ffprobe_exit_${code}`);
        }
      });
    });

  const p = probeQueue.then(runProbe, runProbe).finally(() => {
    inFlightChecks.delete(id);
  });
  probeQueue = p.catch(() => {});

  inFlightChecks.set(id, p);
  return p;
}

async function getAllStatuses(force = false) {
  const results = await Promise.all(STREAMS.map((s) => checkStreamStatus(s.id, force)));
  return STREAMS.map((s, i) => ({
    id: s.id,
    name: s.name,
    online: !!results[i].online,
    checkedAt: results[i].checkedAt,
    error: results[i].error,
  }));
}

module.exports = {
  listStreams,
  getStreamById,
  hlsDir,
  ensureStreamRunning,
  touchStream,
  checkStreamStatus,
  getAllStatuses,
  killStream,
};
