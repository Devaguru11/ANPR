import { useCallback, useEffect, useState, type ReactNode } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import {
  Alert,
  Box,
  Button,
  Chip,
  Divider,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import ShieldOutlinedIcon from "@mui/icons-material/ShieldOutlined";
import CalendarTodayOutlinedIcon from "@mui/icons-material/CalendarTodayOutlined";
import AccessTimeOutlinedIcon from "@mui/icons-material/AccessTimeOutlined";
import GroupsOutlinedIcon from "@mui/icons-material/GroupsOutlined";
import VerifiedUserOutlinedIcon from "@mui/icons-material/VerifiedUserOutlined";
import PsychologyOutlinedIcon from "@mui/icons-material/PsychologyOutlined";
import DownloadOutlinedIcon from "@mui/icons-material/DownloadOutlined";
import EmailOutlinedIcon from "@mui/icons-material/EmailOutlined";
import ScheduleOutlinedIcon from "@mui/icons-material/ScheduleOutlined";
import TrendingUpIcon from "@mui/icons-material/TrendingUp";
import TrendingDownIcon from "@mui/icons-material/TrendingDown";
import TrendingFlatIcon from "@mui/icons-material/TrendingFlat";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import { api } from "../lib/api";
import { useShellHeader } from "../context/ShellHeaderContext";
import { MastheadDashboardToolbar } from "../components/MastheadDashboardToolbar";
import {
  type DatePreset,
  defaultTodayRange,
  datedRangeFromPreset,
} from "../lib/dashboardRange";
import { downloadDailyBriefingPdf } from "../lib/dailyBriefingPdf";
import { violationTypeMeta } from "../lib/violationTypes";

export type DailyBriefingData = {
  meta: {
    from: string;
    to: string;
    spanDays: number;
    generatedAt: string;
    generatedAtLabel: string;
    comparisonWindowLabel?: string;
    generatedBy: string;
    reportDateLabel: string;
    preparedFor: string;
  };
  report: {
    operationalStatus: string;
    operationalStatusLabel: string;
    aiConfidenceScore: number;
    executiveSummary: string;
    aiNarrative: string;
    comparisonPeriodLabel?: string;
    comparisonWindowLabel?: string;
    keyFindings: {
      id: string;
      title: string;
      value: string;
      detail: string;
      badge: string;
      badgeTone: "danger" | "warning" | "success" | "info" | "neutral";
      changeDirection?: "up" | "down" | "flat";
      changePct?: number;
      changeLabel?: string;
      priorValue?: number;
      currentValue?: number;
    }[];
    siteRanking: {
      rank: number;
      name: string;
      violations: number;
      priorViolations?: number;
      trafficVolume: number;
      riskLevel: string;
      trend: string;
      trendPct?: number;
      changeLabel?: string;
      violationSharePct: number;
    }[];
    violationBreakdown: {
      code: string;
      label: string;
      count: number;
      priorCount?: number;
      changePct?: number;
      changeDirection?: "up" | "down" | "flat";
      changeLabel?: string;
      sharePct: number;
    }[];
    commandRecommendations: {
      priority: number;
      label: string;
      title: string;
      body: string;
      tone: "danger" | "warning" | "info" | "success";
    }[];
    archive: {
      from: string;
      to: string;
      dateLabel: string;
      reportType: string;
      generatedAtLabel?: string;
      isCurrent: boolean;
    }[];
    watchlistHits: number;
  };
};

const reportPaperSx = {
  borderRadius: "12px",
  border: "1px solid rgba(15, 23, 42, 0.08)",
  bgcolor: "#fff",
  boxShadow: "0 4px 24px rgba(15, 23, 42, 0.06)",
  overflow: "hidden",
} as const;

function badgeSx(tone: string) {
  const map: Record<string, { bg: string; color: string }> = {
    danger: { bg: "rgba(220,38,38,0.12)", color: "#b91c1c" },
    warning: { bg: "rgba(245,158,11,0.15)", color: "#b45309" },
    success: { bg: "rgba(22,163,74,0.12)", color: "#15803d" },
    info: { bg: "rgba(37,99,235,0.10)", color: "#1d4ed8" },
    neutral: { bg: "rgba(100,116,139,0.12)", color: "#475569" },
  };
  const c = map[tone] || map.neutral;
  return { fontWeight: 800, bgcolor: c.bg, color: c.color };
}

function riskSx(level: string) {
  const l = level.toLowerCase();
  if (l === "high") return { bgcolor: "rgba(220,38,38,0.12)", color: "#b91c1c" };
  if (l === "medium") return { bgcolor: "rgba(245,158,11,0.15)", color: "#b45309" };
  return { bgcolor: "rgba(22,163,74,0.12)", color: "#15803d" };
}

function TrendGlyph({ trend }: { trend: string }) {
  if (trend === "up") return <TrendingUpIcon sx={{ fontSize: 18, color: "#dc2626" }} />;
  if (trend === "down") return <TrendingDownIcon sx={{ fontSize: 18, color: "#16a34a" }} />;
  return <TrendingFlatIcon sx={{ fontSize: 18, color: "#64748b" }} />;
}

function changeLabelColor(direction?: string) {
  if (direction === "up") return "#dc2626";
  if (direction === "down") return "#16a34a";
  return "#64748b";
}

function MetaItem({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <Box sx={{ display: "flex", gap: 1, alignItems: "flex-start", minWidth: 0 }}>
      <Box sx={{ color: "#2563EB", mt: 0.15 }}>{icon}</Box>
      <Box sx={{ minWidth: 0 }}>
        <Typography sx={{ fontSize: "0.6875rem", fontWeight: 800, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.06em" }}>
          {label}
        </Typography>
        <Typography sx={{ fontSize: "0.8125rem", fontWeight: 800, color: "#0f172a", lineHeight: 1.35 }}>{value}</Typography>
      </Box>
    </Box>
  );
}

function violationBarColor(code: string) {
  return violationTypeMeta(code as never)?.color || "#64748b";
}

export function DailyBriefingPage() {
  const { setRightSlot } = useShellHeader();
  const initial = defaultTodayRange();
  const [preset, setPreset] = useState<DatePreset>("today");
  const [customFrom, setCustomFrom] = useState(initial.from);
  const [customTo, setCustomTo] = useState(initial.to);
  const [emailMsg, setEmailMsg] = useState<string | null>(null);
  const [pdfBusy, setPdfBusy] = useState(false);

  const { from: resolvedFrom, to: resolvedTo } = datedRangeFromPreset(preset, customFrom, customTo);

  const briefingQ = useQuery({
    queryKey: ["daily-briefing", resolvedFrom, resolvedTo],
    queryFn: async ({ signal }) =>
      (await api.get<DailyBriefingData>("/dashboard/daily-briefing", { params: { from: resolvedFrom, to: resolvedTo }, signal }))
        .data,
    placeholderData: keepPreviousData,
  });

  const data = briefingQ.data;
  const report = data?.report;

  const resetToToday = useCallback(() => {
    const t = defaultTodayRange();
    setPreset("today");
    setCustomFrom(t.from);
    setCustomTo(t.to);
  }, []);

  useEffect(() => {
    setRightSlot(
      <MastheadDashboardToolbar
        preset={preset}
        onPresetChange={setPreset}
        customFrom={customFrom}
        customTo={customTo}
        onCustomFromChange={setCustomFrom}
        onCustomToChange={setCustomTo}
        resolvedFrom={resolvedFrom}
        resolvedTo={resolvedTo}
        onResetToToday={resetToToday}
      />
    );
    return () => setRightSlot(null);
  }, [preset, customFrom, customTo, resolvedFrom, resolvedTo, resetToToday, setRightSlot]);

  const handleEmail = async () => {
    setEmailMsg(null);
    try {
      const { data: res } = await api.post<{ ok: boolean; message?: string }>("/dashboard/daily-briefing/email", {
        from: resolvedFrom,
        to: resolvedTo,
      });
      setEmailMsg(res.message || "Brief queued for email.");
    } catch (e: unknown) {
      const msg =
        (e as { response?: { data?: { message?: string } } })?.response?.data?.message ||
        "Email is not configured. Download the PDF instead.";
      setEmailMsg(msg);
    }
  };

  const downloadArchive = async (archiveFrom: string, archiveTo: string) => {
    setPdfBusy(true);
    try {
      const { data: archiveData } = await api.get<DailyBriefingData>("/dashboard/daily-briefing", {
        params: { from: archiveFrom, to: archiveTo },
      });
      downloadDailyBriefingPdf(archiveData, "full");
    } finally {
      setPdfBusy(false);
    }
  };

  const maxViolationCount = Math.max(1, ...(report?.violationBreakdown.map((v) => v.count) || [1]));

  return (
    <Box sx={{ maxWidth: 1100, mx: "auto", pb: 4 }}>
      {emailMsg ? (
        <Alert severity="info" onClose={() => setEmailMsg(null)} sx={{ mb: 2 }}>
          {emailMsg}
        </Alert>
      ) : null}
      {briefingQ.isError ? <Alert severity="error" sx={{ mb: 2 }}>Failed to load intelligence brief.</Alert> : null}

      {}
      <Paper sx={{ ...reportPaperSx, mb: 2.5 }}>
        <Box
          sx={{
            px: { xs: 2, sm: 3 },
            py: 2.5,
            background: "linear-gradient(180deg, rgba(37,99,235,0.08) 0%, rgba(255,255,255,0) 100%)",
            borderBottom: "1px solid rgba(15,23,42,0.06)",
          }}
        >
          <Box sx={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 1, mb: 2 }}>
            <ShieldOutlinedIcon sx={{ color: "#1e3a8a", fontSize: 28 }} />
            <Typography
              sx={{
                fontWeight: 900,
                fontSize: { xs: "0.95rem", sm: "1.05rem" },
                letterSpacing: "0.14em",
                color: "#1e3a8a",
                textAlign: "center",
              }}
            >
              DAILY TRAFFIC INTELLIGENCE BRIEF
            </Typography>
          </Box>
          <Box
            sx={{
              display: "grid",
              gridTemplateColumns: { xs: "1fr 1fr", md: "repeat(5, minmax(0, 1fr))" },
              gap: 2,
            }}
          >
            <MetaItem icon={<CalendarTodayOutlinedIcon fontSize="small" />} label="Report Date" value={data?.meta.reportDateLabel || "—"} />
            <MetaItem icon={<AccessTimeOutlinedIcon fontSize="small" />} label="Generated At" value={data?.meta.generatedAtLabel || "—"} />
            <MetaItem icon={<GroupsOutlinedIcon fontSize="small" />} label="Prepared For" value={data?.meta.preparedFor || "PNP Operations"} />
            <MetaItem
              icon={<VerifiedUserOutlinedIcon fontSize="small" />}
              label="Operational Status"
              value={report?.operationalStatusLabel || "—"}
            />
            <MetaItem
              icon={<AutoAwesomeOutlinedIcon fontSize="small" />}
              label="AI Confidence"
              value={report ? `${report.aiConfidenceScore}%` : "—"}
            />
          </Box>
          {report ? (
            <Box sx={{ mt: 1.5, display: "flex", justifyContent: { xs: "flex-start", md: "flex-end" }, gap: 1, flexWrap: "wrap" }}>
              <Chip
                size="small"
                label={report.operationalStatusLabel}
                sx={{
                  ...(report.operationalStatus === "NORMAL"
                    ? badgeSx("success")
                    : report.operationalStatus === "ELEVATED"
                      ? badgeSx("warning")
                      : badgeSx("danger")),
                  fontWeight: 900,
                }}
              />
              <Chip size="small" label="High Confidence" sx={{ ...badgeSx("info"), fontWeight: 800 }} />
            </Box>
          ) : null}
        </Box>
      </Paper>

      {}
      <Paper sx={{ ...reportPaperSx, p: { xs: 2, sm: 2.5 }, mb: 2.5 }}>
        <Typography sx={{ fontWeight: 900, fontSize: "1rem", color: "#0f172a", mb: 1.5 }}>Executive Summary</Typography>
        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "1fr auto" }, gap: 2, alignItems: "center" }}>
          <Typography sx={{ fontSize: "0.9375rem", lineHeight: 1.75, color: "#334155", fontWeight: 500 }}>
            {report?.executiveSummary ||
              (briefingQ.isLoading ? "Generating operational summary from live database…" : "No summary available for this period.")}
          </Typography>
          <Box
            sx={{
              width: { xs: "100%", md: 140 },
              height: 100,
              borderRadius: 2,
              bgcolor: "rgba(37,99,235,0.06)",
              border: "1px dashed rgba(37,99,235,0.25)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <ShieldOutlinedIcon sx={{ fontSize: 48, color: "rgba(37,99,235,0.35)" }} />
          </Box>
        </Box>
      </Paper>

      {}
      <Box sx={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 1, mb: 1.25, flexWrap: "wrap" }}>
        <Typography sx={{ fontWeight: 900, fontSize: "1rem", color: "#0f172a" }}>Key Findings</Typography>
        {report?.comparisonPeriodLabel ? (
          <Typography sx={{ fontSize: "0.75rem", fontWeight: 700, color: "#64748b" }}>
            Compared with {report.comparisonPeriodLabel}
            {report.comparisonWindowLabel ? ` (${report.comparisonWindowLabel})` : ""}
          </Typography>
        ) : null}
      </Box>
      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: { xs: "1fr", sm: "repeat(2, 1fr)", lg: "repeat(5, minmax(0, 1fr))" },
          gap: 1.25,
          mb: 2.5,
        }}
      >
        {(report?.keyFindings || []).map((f) => (
          <Paper key={f.id} sx={{ ...reportPaperSx, p: 1.5 }}>
            <Typography sx={{ fontSize: "0.6875rem", fontWeight: 800, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.05em" }}>
              {f.title}
            </Typography>
            <Typography sx={{ mt: 0.75, fontWeight: 900, fontSize: "1.05rem", color: "#0f172a", lineHeight: 1.2 }}>{f.value}</Typography>
            {f.changeLabel ? (
              <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, mt: 0.5 }}>
                <TrendGlyph trend={f.changeDirection === "flat" ? "stable" : f.changeDirection || "stable"} />
                <Typography sx={{ fontSize: "0.75rem", fontWeight: 800, color: changeLabelColor(f.changeDirection) }}>
                  {f.changeLabel}
                </Typography>
              </Box>
            ) : null}
            <Typography sx={{ mt: 0.5, fontSize: "0.75rem", color: "#64748b", fontWeight: 600, lineHeight: 1.35 }}>{f.detail}</Typography>
            <Chip size="small" label={f.badge} sx={{ mt: 1.25, ...badgeSx(f.badgeTone), fontWeight: 800 }} />
          </Paper>
        ))}
      </Box>

      {}
      <Paper sx={{ ...reportPaperSx, p: { xs: 2, sm: 2.5 }, mb: 2.5 }}>
        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "1fr auto" }, gap: 2, alignItems: "center" }}>
          <Box>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1 }}>
              <Typography sx={{ fontWeight: 900, fontSize: "1rem", color: "#0f172a" }}>AI Narrative</Typography>
              <Chip size="small" label="Beta" sx={{ ...badgeSx("info"), fontWeight: 800 }} />
            </Box>
            <Typography sx={{ fontSize: "0.9375rem", lineHeight: 1.8, color: "#334155", fontWeight: 500 }}>
              {report?.aiNarrative ||
                (briefingQ.isLoading ? "Composing intelligence narrative…" : "No narrative available.")}
            </Typography>
          </Box>
          <PsychologyOutlinedIcon sx={{ fontSize: 72, color: "rgba(139,92,246,0.35)", justifySelf: "center" }} />
        </Box>
      </Paper>

      {}
      <Typography sx={{ fontWeight: 900, fontSize: "1rem", color: "#0f172a", mb: 1.25 }}>Intelligence Data</Typography>
      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", lg: "1.2fr 0.8fr" }, gap: 2, mb: 2.5 }}>
        <Paper sx={{ ...reportPaperSx, p: 2 }}>
          <Typography sx={{ fontWeight: 900, fontSize: "0.9375rem", mb: 1.5 }}>Site Intelligence Ranking</Typography>
          <Box sx={{ overflowX: "auto" }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  {[
                    "Rank",
                    "Site / Checkpoint",
                    "Violations",
                    "Traffic Volume",
                    "Risk Level",
                    report?.comparisonPeriodLabel ? `vs ${report.comparisonPeriodLabel}` : "Trend",
                  ].map((h) => (
                    <TableCell key={h} sx={{ fontWeight: 900, fontSize: "0.6875rem", color: "#64748b", whiteSpace: "nowrap" }}>
                      {h}
                    </TableCell>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {(report?.siteRanking || []).slice(0, 10).map((s) => (
                  <TableRow key={s.rank} hover>
                    <TableCell sx={{ fontWeight: 900 }}>{s.rank}</TableCell>
                    <TableCell sx={{ fontWeight: 700 }}>{s.name}</TableCell>
                    <TableCell sx={{ fontWeight: 800 }}>{s.violations}</TableCell>
                    <TableCell>{s.trafficVolume.toLocaleString()}</TableCell>
                    <TableCell>
                      <Chip size="small" label={s.riskLevel} sx={{ fontWeight: 800, ...riskSx(s.riskLevel) }} />
                    </TableCell>
                    <TableCell>
                      <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
                        <TrendGlyph trend={s.trend} />
                        <Typography sx={{ fontSize: "0.75rem", fontWeight: 800, color: changeLabelColor(s.trend) }}>
                          {s.changeLabel || "—"}
                        </Typography>
                      </Box>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Box>
        </Paper>

        <Paper sx={{ ...reportPaperSx, p: 2 }}>
          <Typography sx={{ fontWeight: 900, fontSize: "0.9375rem", mb: 1.5 }}>Violation Breakdown</Typography>
          <Stack spacing={1.5}>
            {(report?.violationBreakdown || []).map((v) => (
              <Box key={v.code}>
                <Box sx={{ display: "flex", justifyContent: "space-between", mb: 0.5, gap: 1, flexWrap: "wrap" }}>
                  <Typography sx={{ fontSize: "0.8125rem", fontWeight: 700 }}>{v.label}</Typography>
                  <Box sx={{ textAlign: "right" }}>
                    <Typography sx={{ fontSize: "0.75rem", fontWeight: 800, color: "#64748b" }}>
                      {v.count} ({v.sharePct}%)
                    </Typography>
                    {v.changeLabel ? (
                      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 0.35 }}>
                        <TrendGlyph trend={v.changeDirection === "flat" ? "stable" : v.changeDirection || "stable"} />
                        <Typography sx={{ fontSize: "0.6875rem", fontWeight: 800, color: changeLabelColor(v.changeDirection) }}>
                          {v.changeLabel}
                        </Typography>
                      </Box>
                    ) : null}
                  </Box>
                </Box>
                <Box sx={{ height: 10, borderRadius: 1, bgcolor: "rgba(15,23,42,0.06)", overflow: "hidden" }}>
                  <Box
                    sx={{
                      height: "100%",
                      width: `${(v.count / maxViolationCount) * 100}%`,
                      bgcolor: violationBarColor(v.code),
                      borderRadius: 1,
                    }}
                  />
                </Box>
              </Box>
            ))}
          </Stack>
          <Divider sx={{ my: 2 }} />
          <Typography sx={{ textAlign: "right", fontWeight: 900, fontSize: "1.1rem", color: "#0f172a" }}>
            Total Violations: {(report?.violationBreakdown || []).reduce((n, v) => n + v.count, 0).toLocaleString()}
          </Typography>
        </Paper>
      </Box>

      {}
      <Typography sx={{ fontWeight: 900, fontSize: "1rem", color: "#0f172a", mb: 1.25 }}>Command Recommendations</Typography>
      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: { xs: "1fr", sm: "repeat(2, 1fr)", lg: "repeat(4, minmax(0, 1fr))" },
          gap: 1.25,
          mb: 2.5,
        }}
      >
        {(report?.commandRecommendations || []).map((r) => (
          <Paper
            key={r.priority}
            sx={{
              ...reportPaperSx,
              p: 1.75,
              borderLeft: `4px solid ${
                r.tone === "danger" ? "#dc2626" : r.tone === "warning" ? "#f59e0b" : r.tone === "info" ? "#2563eb" : "#16a34a"
              }`,
            }}
          >
            <Chip size="small" label={r.label} sx={{ mb: 1, ...badgeSx(r.tone), fontWeight: 800 }} />
            <Typography sx={{ fontWeight: 900, fontSize: "0.875rem", mb: 0.75, lineHeight: 1.35 }}>{r.title}</Typography>
            <Typography sx={{ fontSize: "0.8125rem", color: "#64748b", lineHeight: 1.55, fontWeight: 500 }}>{r.body}</Typography>
          </Paper>
        ))}
      </Box>

      {}
      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", lg: "1fr 1fr" }, gap: 2, mb: 2 }}>
        <Paper sx={{ ...reportPaperSx, p: 2 }}>
          <Typography sx={{ fontWeight: 900, fontSize: "0.9375rem", mb: 1.5 }}>Daily Briefing Archive</Typography>
          <Table size="small">
            <TableHead>
              <TableRow>
                {["Date", "Report Type", "Generated", ""].map((h) => (
                  <TableCell key={h} sx={{ fontWeight: 900, fontSize: "0.6875rem", color: "#64748b" }}>
                    {h}
                  </TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {(report?.archive || []).map((a) => (
                <TableRow key={a.from} selected={a.isCurrent}>
                  <TableCell sx={{ fontWeight: 700, fontSize: "0.8125rem" }}>{a.dateLabel}</TableCell>
                  <TableCell sx={{ fontSize: "0.8125rem" }}>{a.reportType}</TableCell>
                  <TableCell sx={{ fontSize: "0.8125rem", color: "#64748b" }}>{a.generatedAtLabel || "—"}</TableCell>
                  <TableCell align="right">
                    <Button
                      size="small"
                      variant="text"
                      disabled={pdfBusy}
                      onClick={() => void downloadArchive(a.from, a.to)}
                      sx={{ fontWeight: 800, textTransform: "none" }}
                    >
                      Download PDF
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>

        <Paper sx={{ ...reportPaperSx, p: 2 }}>
          <Typography sx={{ fontWeight: 900, fontSize: "0.9375rem", mb: 0.5 }}>Export Daily Brief</Typography>
          <Typography sx={{ fontSize: "0.8125rem", color: "#64748b", mb: 2 }}>
            Download or distribute today&apos;s intelligence report for command staff.
          </Typography>
          <Stack spacing={1}>
            <Button
              variant="contained"
              fullWidth
              size="large"
              startIcon={<DownloadOutlinedIcon />}
              disabled={!data || pdfBusy}
              onClick={() => data && downloadDailyBriefingPdf(data, "full")}
              sx={{ fontWeight: 900, py: 1.35, borderRadius: 2 }}
            >
              Download Daily Intelligence Brief (PDF)
            </Button>
            <Button
              variant="outlined"
              fullWidth
              startIcon={<DownloadOutlinedIcon />}
              disabled={!data || pdfBusy}
              onClick={() => data && downloadDailyBriefingPdf(data, "executive")}
              sx={{ fontWeight: 800, borderRadius: 2 }}
            >
              Download Executive Summary (PDF)
            </Button>
            <Button variant="outlined" fullWidth startIcon={<EmailOutlinedIcon />} disabled={!data} onClick={() => void handleEmail()} sx={{ fontWeight: 800, borderRadius: 2 }}>
              Email Daily Brief
            </Button>
            <Button variant="outlined" fullWidth startIcon={<ScheduleOutlinedIcon />} disabled sx={{ fontWeight: 800, borderRadius: 2 }}>
              Schedule Daily Brief
            </Button>
          </Stack>
        </Paper>
      </Box>

      <Typography sx={{ textAlign: "center", fontSize: "0.75rem", color: "#94a3b8", fontWeight: 600 }}>
        Secured Government System | PNP Network — Authorized Access Only · AI generated report · Data as of{" "}
        {data?.meta.generatedAtLabel || "—"}, {data?.meta.reportDateLabel || "—"}
      </Typography>
    </Box>
  );
}
