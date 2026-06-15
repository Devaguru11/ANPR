
const LEGACY_CAMERA_NAMES: Record<string, string> = {
  Total: "Baliwag",
  Julieta: "Baliwag",
};

const CAMERA_ID_ALIASES: Record<string, string> = {
  AEYE_4: "Baliwag",
};

export function heatmapCheckpointDot(): string {
  return "#22C55E";
}

export function locationDotColor(name?: string | null, cameraId?: string | null): string {
  const label = displayCameraName(name, cameraId).toLowerCase();
  if (label.includes("chowking")) return "#7C3AED";
  if (label.includes("baliwag") || label.includes("julieta")) return "#EA580C";
  if (label.includes("market") || label.includes("highway") || label.includes("luvers")) return "#22C55E";
  return "#94A3B8";
}

export function cameraDotColor(cameraId?: string | null, rowIndex = 0): string {
  void cameraId;
  void rowIndex;
  return heatmapCheckpointDot();
}

export function displayCameraName(name?: string | null, cameraId?: string | null): string {
  const id = cameraId?.trim();
  if (id && CAMERA_ID_ALIASES[id]) return CAMERA_ID_ALIASES[id];

  const label = (name ?? "").trim();
  if (!label && id) return CAMERA_ID_ALIASES[id] ?? id;
  if (!label) return "";

  return LEGACY_CAMERA_NAMES[label] ?? label;
}
