const fs = require("fs");
const path = require("path");

const RECEIVER_ROOT = process.env.RECEIVER_RESULTS_DIR || "/home/aiserver/receiver-results";
const PUBLIC_SITE_URL = String(process.env.PUBLIC_SITE_URL || "https://ag.bcss.ai").replace(/\/+$/, "");

function violationLabel(type) {
  const t = String(type || "").toUpperCase();
  if (t === "NO_HELMET") return "No Helmet";
  if (t === "WRONG_PARKING") return "Wrong Parking";
  if (t === "TRIPLE_RIDING") return "Triple Riding";
  if (t === "WRONG_ROUTE") return "Wrong Route";
  return String(type || "Violation").replace(/_/g, " ");
}

function money(n) {
  const v = Number(n || 0);
  return `₱ ${v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function escapeHtml(s) {
  return String(s || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function normalizeProofRelPath(proofUrl) {
  let p = String(proofUrl || "").trim();
  if (!p) return null;
  if (p.startsWith("/receiver-results/")) p = p.slice("/receiver-results".length);
  if (!p.startsWith("/")) p = `/${p}`;
  return p;
}

function resolveLocalProofPath(proofUrl) {
  const rel = normalizeProofRelPath(proofUrl);
  if (!rel) return null;
  const root = path.resolve(RECEIVER_ROOT);
  const full = path.resolve(root, rel.replace(/^\//, ""));
  if (!full.startsWith(root + path.sep) && full !== root) return null;
  return fs.existsSync(full) ? full : null;
}

function publicProofUrl(proofUrl) {
  const rel = normalizeProofRelPath(proofUrl);
  if (!rel) return null;
  return `${PUBLIC_SITE_URL}/receiver-results${rel}`;
}

function ticketRef(challan) {
  const id = Number(challan?.id);
  return Number.isFinite(id) && id > 0 ? `VT-${String(id).padStart(6, "0")}` : "VT-PENDING";
}

async function buildChallanEmail(challan) {
  const plate = escapeHtml(challan.plate);
  const vLabel = escapeHtml(violationLabel(challan.violationType));
  const amount = escapeHtml(money(challan.amount));
  const site = challan.siteName ? escapeHtml(challan.siteName) : "—";
  const detected = challan.detectedAt ? escapeHtml(challan.detectedAt) : "—";
  const owner = challan.ownerName ? escapeHtml(challan.ownerName) : "Registered owner";
  const ref = escapeHtml(ticketRef(challan));

  const attachments = [];
  let proofImgHtml = "";
  const localPath = resolveLocalProofPath(challan.proofUrl);
  const publicUrl = publicProofUrl(challan.proofUrl);

  if (localPath) {
    attachments.push({
      filename: path.basename(localPath),
      path: localPath,
      cid: "violation-proof",
    });
    proofImgHtml = `
      <tr>
        <td colspan="2" style="padding:16px 24px 8px;">
          <p style="margin:0 0 10px;font-size:12px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:#64748b;">Violation evidence</p>
          <img src="cid:violation-proof" alt="Violation capture" style="display:block;width:100%;max-width:560px;border-radius:12px;border:1px solid #e2e8f0;" />
        </td>
      </tr>`;
  } else if (publicUrl) {
    proofImgHtml = `
      <tr>
        <td colspan="2" style="padding:16px 24px 8px;">
          <p style="margin:0 0 10px;font-size:12px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:#64748b;">Violation evidence</p>
          <img src="${escapeHtml(publicUrl)}" alt="Violation capture" style="display:block;width:100%;max-width:560px;border-radius:12px;border:1px solid #e2e8f0;" />
        </td>
      </tr>`;
  }

  const subject = `Violation Ticket Notice — ${challan.plate}`;

  const text = [
    "PNP VIOLATION TICKET NOTICE",
    "",
    `Ticket: ${ticketRef(challan)}`,
    `Vehicle: ${challan.plate}`,
    `Violation: ${violationLabel(challan.violationType)}`,
    `Amount due: ${money(challan.amount)}`,
    `Location: ${challan.siteName || "—"}`,
    `Detected: ${challan.detectedAt || "—"}`,
    "",
    "This notice is issued based on automated traffic enforcement records.",
    "Please contact the issuing authority for inquiries or contest procedures.",
    publicUrl ? `Evidence image: ${publicUrl}` : null,
  ]
    .filter(Boolean)
    .join("\n");

  const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>${subject}</title>
</head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#0f172a;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f1f5f9;padding:24px 12px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:600px;background:#ffffff;border-radius:16px;overflow:hidden;border:1px solid #e2e8f0;box-shadow:0 12px 32px rgba(15,23,42,0.08);">
          <tr>
            <td style="background:linear-gradient(135deg,#1e3a8a 0%,#2563eb 55%,#1d4ed8 100%);padding:22px 24px;">
              <p style="margin:0;font-size:11px;font-weight:700;letter-spacing:0.14em;text-transform:uppercase;color:rgba(255,255,255,0.82);">PNP Operations</p>
              <h1 style="margin:8px 0 0;font-size:22px;line-height:1.25;font-weight:800;color:#ffffff;">Violation Ticket Notice</h1>
              <p style="margin:8px 0 0;font-size:13px;color:rgba(255,255,255,0.9);">Ticket ${ref} · ${plate}</p>
            </td>
          </tr>
          <tr>
            <td style="padding:20px 24px 8px;">
              <p style="margin:0;font-size:15px;line-height:1.6;color:#334155;">Dear <strong>${owner}</strong>,</p>
              <p style="margin:12px 0 0;font-size:14px;line-height:1.65;color:#475569;">
                Our records show a traffic violation associated with the vehicle below. Please review the details and supporting evidence.
              </p>
            </td>
          </tr>
          <tr>
            <td style="padding:8px 24px 16px;">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border:1px solid #e2e8f0;border-radius:12px;overflow:hidden;">
                <tr style="background:#f8fafc;">
                  <td style="padding:12px 14px;font-size:12px;font-weight:700;color:#64748b;width:38%;">Vehicle number</td>
                  <td style="padding:12px 14px;font-size:15px;font-weight:800;color:#0f172a;">${plate}</td>
                </tr>
                <tr>
                  <td style="padding:12px 14px;font-size:12px;font-weight:700;color:#64748b;border-top:1px solid #e2e8f0;">Violation</td>
                  <td style="padding:12px 14px;font-size:14px;font-weight:700;color:#0f172a;border-top:1px solid #e2e8f0;">${vLabel}</td>
                </tr>
                <tr style="background:#f8fafc;">
                  <td style="padding:12px 14px;font-size:12px;font-weight:700;color:#64748b;border-top:1px solid #e2e8f0;">Amount due</td>
                  <td style="padding:12px 14px;font-size:18px;font-weight:900;color:#b45309;border-top:1px solid #e2e8f0;">${amount}</td>
                </tr>
                <tr>
                  <td style="padding:12px 14px;font-size:12px;font-weight:700;color:#64748b;border-top:1px solid #e2e8f0;">Location</td>
                  <td style="padding:12px 14px;font-size:14px;color:#0f172a;border-top:1px solid #e2e8f0;">${site}</td>
                </tr>
                <tr style="background:#f8fafc;">
                  <td style="padding:12px 14px;font-size:12px;font-weight:700;color:#64748b;border-top:1px solid #e2e8f0;">Detected at</td>
                  <td style="padding:12px 14px;font-size:14px;color:#0f172a;border-top:1px solid #e2e8f0;">${detected}</td>
                </tr>
              </table>
            </td>
          </tr>
          ${proofImgHtml}
          <tr>
            <td style="padding:8px 24px 22px;">
              <p style="margin:0;font-size:12px;line-height:1.6;color:#64748b;">
                This is an official violation notice generated from the traffic enforcement system.
                For questions or to contest this notice, contact your local PNP traffic enforcement office.
              </p>
            </td>
          </tr>
          <tr>
            <td style="background:#f8fafc;padding:14px 24px;border-top:1px solid #e2e8f0;">
              <p style="margin:0;font-size:11px;color:#94a3b8;">Automated message · Do not reply to this email</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>`;

  return { subject, text, html, attachments };
}

module.exports = {
  buildChallanEmail,
  violationLabel,
  money,
  publicProofUrl,
  resolveLocalProofPath,
};
