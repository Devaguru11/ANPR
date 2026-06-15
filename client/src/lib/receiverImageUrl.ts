const IMAGE_BASE = String(import.meta.env.VITE_IMAGE_BASE_URL || "/receiver-results").trim().replace(/\/$/, "");

export function receiverImageUrl(path: string | null | undefined): string {
  const raw = String(path || "").trim();
  if (!raw) return "";
  if (/^https?:\/\//i.test(raw)) return raw;

  let rel = raw;
  if (rel.startsWith("/receiver-results/")) {
    rel = rel.slice("/receiver-results".length);
  } else if (rel.startsWith("/receiver-results")) {
    rel = rel.slice("/receiver-results".length);
  }
  if (!rel.startsWith("/")) rel = `/${rel}`;

  if (IMAGE_BASE.startsWith("http")) {
    return `${IMAGE_BASE}${rel}`;
  }
  return `${IMAGE_BASE}${rel}`;
}
