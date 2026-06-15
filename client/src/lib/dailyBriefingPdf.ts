import { jsPDF } from "jspdf";
import autoTable from "jspdf-autotable";
import type { DailyBriefingData } from "../pages/DailyBriefingPage";

function fmtDate(iso: string) {
  try {
    return new Date(iso).toLocaleString("en-PH", { timeZone: "Asia/Manila" });
  } catch {
    return iso;
  }
}

function addCover(doc: jsPDF, data: DailyBriefingData, title: string) {
  doc.setFillColor(30, 58, 138);
  doc.rect(0, 0, 210, 297, "F");
  doc.setTextColor(255, 255, 255);
  doc.setFontSize(20);
  doc.text(title, 105, 85, { align: "center" });
  doc.setFontSize(11);
  doc.text("DAILY TRAFFIC INTELLIGENCE BRIEF", 105, 98, { align: "center" });
  doc.setFontSize(10);
  doc.text(data.meta.reportDateLabel, 105, 112, { align: "center" });
  doc.text(
    `Generated: ${data.meta.generatedAtLabel || fmtDate(data.meta.generatedAt)}`,
    105,
    122,
    { align: "center" }
  );
  doc.text(data.meta.preparedFor, 105, 132, { align: "center", maxWidth: 170 });
  doc.setFontSize(9);
  doc.setTextColor(203, 213, 225);
  doc.text("Confidential — For official use only", 105, 270, { align: "center" });
}

export function downloadDailyBriefingPdf(data: DailyBriefingData, mode: "full" | "executive" = "full") {
  const doc = new jsPDF({ unit: "mm", format: "a4" });
  const r = data.report;
  const title = mode === "executive" ? "Executive Intelligence Summary" : "Daily Intelligence Brief";

  addCover(doc, data, title);
  doc.addPage();
  doc.setTextColor(15, 23, 42);
  doc.setFontSize(12);
  doc.text(`Operational Status: ${r.operationalStatusLabel}  |  AI Confidence: ${r.aiConfidenceScore}%`, 14, 18);

  doc.setFontSize(14);
  doc.text("Executive Summary", 14, 28);
  doc.setFontSize(10);
  const summaryLines = doc.splitTextToSize(r.executiveSummary, 182);
  doc.text(summaryLines, 14, 34);

  let y = 34 + summaryLines.length * 5 + 8;
  if (mode === "executive") {
    doc.setFontSize(14);
    doc.text("Key Findings", 14, y);
    y += 6;
    doc.setFontSize(10);
    for (const f of r.keyFindings) {
      const line = doc.splitTextToSize(
        `• ${f.title}: ${f.value} — ${f.detail}${f.changeLabel ? ` (${f.changeLabel})` : ""}`,
        182
      );
      doc.text(line, 14, y);
      y += line.length * 5 + 2;
    }
    y += 4;
    doc.setFontSize(14);
    doc.text("Command Recommendations", 14, y);
    y += 6;
    doc.setFontSize(10);
    for (const c of r.commandRecommendations) {
      const line = doc.splitTextToSize(`• [${c.label}] ${c.title}: ${c.body}`, 182);
      doc.text(line, 14, y);
      y += line.length * 5 + 2;
    }
    doc.save(`daily-intelligence-brief-${data.meta.from}_${data.meta.to}-executive.pdf`);
    return;
  }

  doc.setFontSize(14);
  doc.text("AI Narrative", 14, y);
  y += 6;
  doc.setFontSize(10);
  const narrativeLines = doc.splitTextToSize(r.aiNarrative, 182);
  doc.text(narrativeLines, 14, y);
  y += narrativeLines.length * 5 + 10;

  autoTable(doc, {
    startY: y,
    head: [["Finding", "Value", "Detail"]],
    body: r.keyFindings.map((f) => [f.title, f.value, `${f.detail}${f.changeLabel ? ` · ${f.changeLabel}` : ""}`]),
    styles: { fontSize: 9 },
    headStyles: { fillColor: [30, 58, 138] },
  });
  y = (doc as jsPDF & { lastAutoTable?: { finalY: number } }).lastAutoTable?.finalY ?? y + 40;

  autoTable(doc, {
    startY: y + 8,
    head: [["Rank", "Site", "Violations", "Traffic", "Risk", "Change"]],
    body: r.siteRanking.map((s) => [
      String(s.rank),
      s.name,
      String(s.violations),
      s.trafficVolume.toLocaleString(),
      s.riskLevel,
      s.changeLabel || s.trend,
    ]),
    styles: { fontSize: 8 },
    headStyles: { fillColor: [30, 58, 138] },
  });
  y = (doc as jsPDF & { lastAutoTable?: { finalY: number } }).lastAutoTable?.finalY ?? y + 50;

  doc.addPage();
  doc.setFontSize(14);
  doc.text("Violation Breakdown", 14, 20);
  autoTable(doc, {
    startY: 24,
    head: [["Type", "Count", "Share %"]],
    body: r.violationBreakdown.map((v) => [v.label, String(v.count), `${v.sharePct}%`]),
    styles: { fontSize: 9 },
    headStyles: { fillColor: [30, 58, 138] },
  });
  y = (doc as jsPDF & { lastAutoTable?: { finalY: number } }).lastAutoTable?.finalY ?? 50;

  doc.setFontSize(14);
  doc.text("Command Recommendations", 14, y + 12);
  let cy = y + 18;
  doc.setFontSize(10);
  for (const c of r.commandRecommendations) {
    const line = doc.splitTextToSize(`[${c.label}] ${c.title}: ${c.body}`, 182);
    doc.text(line, 14, cy);
    cy += line.length * 5 + 3;
  }

  doc.save(`daily-intelligence-brief-${data.meta.from}_${data.meta.to}.pdf`);
}
