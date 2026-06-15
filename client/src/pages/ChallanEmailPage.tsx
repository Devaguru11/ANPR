import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  Alert,
  Box,
  Button,
  Chip,
  Divider,
  IconButton,
  Link,
  Paper,
  Stack,
  Tab,
  Tabs,
  TextField,
  Typography,
} from "@mui/material";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import LocalPoliceOutlinedIcon from "@mui/icons-material/LocalPoliceOutlined";
import VisibilityOutlinedIcon from "@mui/icons-material/VisibilityOutlined";
import CheckCircleOutlinedIcon from "@mui/icons-material/CheckCircleOutlined";
import AutorenewOutlinedIcon from "@mui/icons-material/AutorenewOutlined";
import AccessTimeOutlinedIcon from "@mui/icons-material/AccessTimeOutlined";
import PlaceOutlinedIcon from "@mui/icons-material/PlaceOutlined";
import FlipIcon from "@mui/icons-material/Flip";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Pie, PieChart, Cell, ResponsiveContainer, Tooltip as ReTooltip } from "recharts";
import { api } from "../lib/api";
import { contentCardSx, gridCols, pageLayoutSx } from "../lib/uiSurfaces";
import { pnp } from "../lib/pnpTheme";
import { ymdSite } from "../lib/siteTimeZone";
import { violationTypeLabel } from "../lib/violationTypes";
import { isConfirmedPlate } from "../lib/plateConfirm";
import { ChallanHistoryPanel } from "../components/challan/ChallanHistoryPanel";
import { violationEventPath } from "../lib/violationNav";
import { receiverImageUrl } from "../lib/receiverImageUrl";

type FeedRow = {
  id: number;
  plate: string;
  violationType: string;
  score: number;
  cameraId: string;
  siteName?: string;
  detectedAt: string;
  createdAt?: string;
  sceneUrl: string | null;
  plateUrl: string | null;
};

type ChallanRow = {
  id: number;
  plate: string;
  violationType: string;
  amount: number;
  siteName: string | null;
  cameraId: string | null;
  detectedAt: string | null;
  proofUrl: string | null;
  ownerEmail: string;
  ownerName: string | null;
  status: string;
  paymentStatus?: string;
  penaltyType?: string;
};

function money(n: number) {
  return `₱ ${Number(n || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function imgUrl(u: string) {
  return receiverImageUrl(u);
}

function kpiChipSx() {
  return {
    bgcolor: "rgba(15,23,42,0.72)",
    color: "rgba(248,250,252,0.92)",
    border: "1px solid rgba(148,163,184,0.28)",
    backdropFilter: "blur(10px)",
  } as const;
}

const AMOUNTS: Record<string, number> = {
  WRONG_PARKING: 1000,
  NO_HELMET: 500,
  WRONG_ROUTE: 750,
  TRIPLE_RIDING: 1500,
};

const primaryActionBtnSx = {
  borderRadius: 2,
  py: 1.15,
  fontWeight: 900,
  color: "#fff",
  background: "linear-gradient(135deg, #2563EB 0%, #1D4ED8 55%, #1E40AF 100%)",
  boxShadow: "0 16px 34px rgba(37, 99, 235, 0.28)",
  "&:hover": {
    background: "linear-gradient(135deg, #1D4ED8 0%, #1E40AF 55%, #1E3A8A 100%)",
  },
} as const;

export function ChallanEmailPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const pageTab = searchParams.get("tab") === "history" ? "history" : "create";
  const setPageTab = useCallback(
    (tab: "create" | "history") => {
      if (tab === "history") setSearchParams({ tab: "history" });
      else setSearchParams({});
    },
    [setSearchParams]
  );

  const today = ymdSite();

  const from = "";
  const to = "";
  const [order] = useState<"asc" | "desc">("asc");
  const [page, setPage] = useState(1);
  const pageSize = 30;

  const [selected, setSelected] = useState<FeedRow | null>(null);
  const [imageMode, setImageMode] = useState<"scene" | "plate">("scene");
  const [feedIdx, setFeedIdx] = useState(0);

  const [ownerName, setOwnerName] = useState<string>("");
  const [ownerEmail, setOwnerEmail] = useState<string>("");
  const [ownerPhone, setOwnerPhone] = useState<string>("");
  const [ownerAddress, setOwnerAddress] = useState<string>("");

  const [plate, setPlate] = useState("");
  const [violationType, setViolationType] = useState<string>("WRONG_PARKING");
  const [amount, setAmount] = useState<number>(AMOUNTS.WRONG_PARKING);
  const [siteName, setSiteName] = useState<string>("");
  const [cameraId, setCameraId] = useState<string>("");
  const [detectedAt, setDetectedAt] = useState<string>("");
  const [proofUrl, setProofUrl] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [savingPlate, setSavingPlate] = useState(false);
  const [, setCreated] = useState<ChallanRow | null>(null);

  const feedQ = useQuery({
    queryKey: ["challan-feed", from, to, order, page, pageSize],
    queryFn: async () => {
      const { data } = await api.get<{ rows: FeedRow[]; total: number; page: number; pageSize: number }>("/challan-public/violations-feed", {
        params: {
          ...(from && to ? { from, to } : {}),
          order,
          page,
          pageSize,
        },
      });
      return data;
    },
    placeholderData: keepPreviousData,
  });

  const smtpQ = useQuery({
    queryKey: ["challan-smtp-status"],
    queryFn: async () => {
      const { data } = await api.get<{ configured: boolean; mode: string; from?: string }>("/challan-public/smtp-status");
      return data;
    },
    refetchInterval: 30_000,
  });

  const statsQ = useQuery({
    queryKey: ["ticket-stats-today", today],
    queryFn: async () => {
      const { data } = await api.get("/challan/stats", { params: { from: today, to: today } });
      return data as any;
    },
    placeholderData: keepPreviousData,
    refetchInterval: 12_000,
  });

  const loadOwnerForPlate = useCallback(async (plateValue: string) => {
    const { data } = await api.get<{ owner: { email: string; name?: string | null; phone?: string | null; address?: string | null } }>(
      "/challan/resolve-owner",
      { params: { plate: plateValue } }
    );
    setOwnerEmail(data.owner.email || "");
    setOwnerName(data.owner.name || "");
    setOwnerPhone(data.owner.phone || ownerPhone || "09" + String(Math.floor(100000000 + Math.random() * 899999999)));
    setOwnerAddress(data.owner.address || "");
    return data.owner;
  }, [ownerPhone]);

  const submitPlate = useCallback(async () => {
    const p = plate.trim();
    if (!p) return;
    if (!isConfirmedPlate(p)) {
      setError("Enter a valid vehicle number before fetching owner details.");
      return;
    }
    setError(null);
    setSavingPlate(true);
    try {
      let savedPlate = p;
      if (selected?.id) {
        const { data } = await api.post<{ plate: string }>("/challan/confirm-plate", {
          violationId: selected.id,
          plate: p,
        });
        savedPlate = data.plate || p;
        setPlate(savedPlate);
        setSelected((row) => (row ? { ...row, plate: savedPlate } : row));
        await Promise.all([feedQ.refetch(), statsQ.refetch()]);
      }
      await loadOwnerForPlate(savedPlate);
    } catch (e: any) {
      setError(String(e?.response?.data?.message || e?.message || "Failed to save vehicle number or fetch owner."));
    } finally {
      setSavingPlate(false);
    }
  }, [feedQ, loadOwnerForPlate, plate, selected?.id, statsQ]);

  const displaySite = siteName || selected?.siteName || "—";

  useEffect(() => {
    if (!selected) return;
    const p = selected.plate || "";
    setPlate(p);
    setViolationType(String(selected.violationType || "").toUpperCase());
    const a = AMOUNTS[String(selected.violationType || "").toUpperCase()] ?? 1000;
    setAmount(a);
    setSiteName(selected.siteName || "");
    setCameraId(selected.cameraId || "");
    setDetectedAt(selected.detectedAt || "");
    setProofUrl(selected.sceneUrl || selected.plateUrl || "");
    setOwnerEmail("");
    setOwnerName("");
    setOwnerPhone("");
    setOwnerAddress("");
    setCreated(null);

    if (isConfirmedPlate(p)) {
      void (async () => {
        try {
          const { data } = await api.get<{ owner: { email: string; name?: string | null; phone?: string | null; address?: string | null } }>(
            "/challan/resolve-owner",
            { params: { plate: p } }
          );
          setOwnerEmail(data.owner.email || "");
          setOwnerName(data.owner.name || "");
          setOwnerPhone(data.owner.phone || "");
          setOwnerAddress(data.owner.address || "");
        } catch {

        }
      })();
    }
  }, [selected]);

  useEffect(() => {
    const a = AMOUNTS[String(violationType || "").toUpperCase()] ?? amount;
    setAmount(a);

  }, [violationType]);

  const canSubmit = useMemo(() => {
    return Boolean(isConfirmedPlate(plate) && violationType && amount > 0);
  }, [plate, violationType, amount]);

  const feedRows = feedQ.data?.rows || [];
  const feedTotal = Number(feedQ.data?.total || 0);

  const applyFeedSelection = useCallback((rows: FeedRow[], idx: number) => {
    if (!rows.length) {
      setFeedIdx(0);
      setSelected(null);
      return;
    }
    const clamped = Math.min(Math.max(idx, 0), rows.length - 1);
    setFeedIdx(clamped);
    setSelected(rows[clamped] ?? null);
  }, []);

  const advanceAfterProcessed = useCallback(
    async (processedViolationId?: number) => {
      const idxBefore = feedIdx;
      const feedResult = await feedQ.refetch();
      await statsQ.refetch();
      const rows = feedResult.data?.rows || [];
      const total = Number(feedResult.data?.total || 0);
      const pageCount = Math.max(1, Math.ceil(total / pageSize));

      if (!rows.length) {
        if (page < pageCount) {
          setPage((p) => p + 1);
          setFeedIdx(0);
          setSelected(null);
        } else {
          applyFeedSelection([], 0);
        }
        return;
      }

      const stillIdx =
        processedViolationId != null ? rows.findIndex((r) => r.id === processedViolationId) : -1;

      if (stillIdx >= 0) {
        if (stillIdx < rows.length - 1) {
          applyFeedSelection(rows, stillIdx + 1);
        } else if (page < pageCount) {
          setPage((p) => p + 1);
          setFeedIdx(0);
          setSelected(null);
        } else {
          applyFeedSelection(rows, stillIdx);
        }
        return;
      }

      applyFeedSelection(rows, Math.min(idxBefore, rows.length - 1));
    },
    [applyFeedSelection, feedIdx, feedQ, page, pageSize, statsQ]
  );

  const createAndSend = useCallback(async () => {
    setError(null);
    setSending(true);
    try {
      const { data } = await api.post<{ challan: ChallanRow }>("/challan/create", {
        violationId: selected?.id ?? null,
        plate,
        violationType,
        amount,
        siteName: siteName || null,
        cameraId: cameraId || null,
        detectedAt: detectedAt || null,
        proofUrl: proofUrl || null,
        source: "auto",
      });
      setCreated(data.challan);
      const { data: send } = await api.post<{ challan: ChallanRow; send?: { mode?: string } }>(`/challan/send/${data.challan.id}`);
      setCreated(send.challan);

      await advanceAfterProcessed(selected?.id);
    } catch (e: any) {
      setError(String(e?.response?.data?.message || e?.message || "Failed to send violation ticket."));
    } finally {
      setSending(false);
    }
  }, [advanceAfterProcessed, amount, cameraId, detectedAt, plate, proofUrl, selected?.id, siteName, violationType]);

  useEffect(() => {
    if (!feedRows.length) {
      if (selected != null) setSelected(null);
      return;
    }
    let idx = feedIdx;
    if (idx < 0) idx = 0;
    if (idx >= feedRows.length) idx = feedRows.length - 1;
    if (idx !== feedIdx) {
      setFeedIdx(idx);
      return;
    }
    const row = feedRows[idx];
    if (row?.id !== selected?.id) setSelected(row ?? null);
  }, [feedIdx, feedRows, selected]);

  const markInvalid = useCallback(async () => {
    if (!selected?.id) return;
    setError(null);
    try {
      await api.post("/challan/flag", { violationId: selected.id, flag: 0 });
      await advanceAfterProcessed(selected.id);
    } catch (e: any) {
      setError(String(e?.response?.data?.message || e?.message || "Failed to mark invalid."));
    }
  }, [advanceAfterProcessed, selected?.id]);

  const advanceViolation = useCallback(() => {
    if (!feedRows.length) return;
    const pageCount = Math.max(1, Math.ceil(feedTotal / pageSize));
    if (feedIdx < feedRows.length - 1) {
      setFeedIdx((v) => v + 1);
      return;
    }
    if (page < pageCount) {
      setPage((p) => p + 1);
      setFeedIdx(0);
      return;
    }
    setFeedIdx(0);
  }, [feedIdx, feedRows.length, feedTotal, page, pageSize]);

  const donutData = useMemo(() => {
    const generated = Number(statsQ.data?.generated ?? 0);
    const invalid = Number(statsQ.data?.invalid ?? 0);
    const pending = Number(statsQ.data?.pending ?? 0);
    const failed = Number(statsQ.data?.failed ?? 0);
    const total = Math.max(0, generated + invalid + pending + failed);
    const safeTotal = total > 0 ? total : 1;
    return {
      total,
      series: [
        { name: "Generated", value: generated, color: "#2563EB" },
        { name: "Invalid", value: invalid, color: "#64748B" },
        { name: "Pending", value: pending, color: "#F59E0B" },
        { name: "Failed", value: failed, color: "#DC2626" },
      ].filter((s) => s.value > 0),
      pctGenerated: Math.round((generated / safeTotal) * 100),
    };
  }, [statsQ.data?.failed, statsQ.data?.generated, statsQ.data?.invalid, statsQ.data?.pending]);

  const autoPanel = (
    <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", lg: `${gridCols(12)}` }, gap: 2 }}>
      <Paper sx={{ ...contentCardSx, gridColumn: { xs: "1 / -1", lg: "span 12" } }}>
        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", lg: "repeat(12, minmax(0, 1fr))" }, gap: 2 }}>
          {}
          <Box sx={{ gridColumn: { xs: "1 / -1", lg: "span 5" } }}>
            <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 1, mb: 1 }}>
              <Typography sx={{ fontWeight: 800, fontSize: "0.875rem" }}>
                Violation{" "}
                {feedTotal
                  ? `${(page - 1) * pageSize + feedIdx + 1} of ${feedTotal}`
                  : feedRows.length
                    ? `${feedIdx + 1} of ${feedRows.length}`
                    : "—"}
              </Typography>
              <Box>
                <IconButton size="small" onClick={() => setFeedIdx((v) => Math.max(0, v - 1))} disabled={!feedRows.length}>
                  <ChevronLeftIcon fontSize="small" />
                </IconButton>
                <IconButton size="small" onClick={() => advanceViolation()} disabled={!feedRows.length}>
                  <ChevronRightIcon fontSize="small" />
                </IconButton>
              </Box>
            </Box>

            <Box sx={{ borderRadius: 3, overflow: "hidden", border: "1px solid rgba(15,23,42,0.12)", bgcolor: "#0B1220", boxShadow: "0 18px 48px rgba(2,6,23,0.10)" }}>
              {feedQ.isError ? (
                <Box sx={{ p: 1.25, bgcolor: "#111827" }}>
                  <Alert severity="error">
                    Failed to load live violations feed. {String((feedQ.error as any)?.response?.data?.message || (feedQ.error as any)?.message || "")}
                  </Alert>
                </Box>
              ) : null}
              {(() => {
                const src =
                  imageMode === "plate"
                    ? selected?.plateUrl || selected?.sceneUrl || ""
                    : selected?.sceneUrl || selected?.plateUrl || "";
                const finalSrc = imgUrl(src);
                if (!finalSrc) {
                  return (
                    <Box
                      sx={{
                        height: 260,
                        display: "grid",
                        placeItems: "center",
                        color: "rgba(226,232,240,0.82)",
                        bgcolor: "#111827",
                        px: 2,
                        textAlign: "center",
                      }}
                    >
                      <Box>
                        <Typography sx={{ fontWeight: 900, fontSize: "0.95rem" }}>
                          {feedRows.length ? "No image available" : feedQ.isLoading ? "Loading…" : "No violations returned"}
                        </Typography>
                        <Typography sx={{ fontSize: "0.75rem", color: "rgba(148,163,184,0.9)", mt: 0.5 }}>
                          {feedRows.length
                            ? `This violation record does not have a stored ${imageMode === "plate" ? "plate crop" : "scene capture"} URL.`
                            : "The API returned zero rows for the current feed query."}
                        </Typography>
                      </Box>
                    </Box>
                  );
                }
                return (
                  <Box sx={{ position: "relative" }}>
                    <Box
                      component="img"
                      alt=""
                      src={finalSrc}
                      sx={{
                        width: "100%",
                        height: 260,
                        objectFit: imageMode === "scene" ? "cover" : "contain",
                        bgcolor: "#111827",
                        display: "block",
                      }}
                    />
                    {}
                    <Box sx={{ position: "absolute", left: 10, right: 10, top: 10, display: "flex", gap: 1, alignItems: "center" }}>
                      <Chip
                        size="small"
                        icon={<AccessTimeOutlinedIcon sx={{ color: "rgba(248,250,252,0.92)" }} />}
                        label={`Captured: ${selected?.detectedAt || "—"}`}
                        sx={kpiChipSx()}
                      />
                      <Box sx={{ flex: 1 }} />
                      <Chip
                        size="small"
                        icon={<PlaceOutlinedIcon sx={{ color: "rgba(248,250,252,0.92)" }} />}
                        label={selected?.siteName || "—"}
                        sx={kpiChipSx()}
                      />
                    </Box>

                    {}
                    {selected?.sceneUrl && selected?.plateUrl ? (
                      <IconButton
                        onClick={() => setImageMode((m) => (m === "scene" ? "plate" : "scene"))}
                        size="small"
                        title={imageMode === "scene" ? "Show plate crop" : "Show scene"}
                        sx={{
                          position: "absolute",
                          top: 10,
                          right: 10,
                          zIndex: 20,
                          width: 36,
                          height: 36,
                          borderRadius: 2,
                          border: "1px solid rgba(148,163,184,0.35)",
                          bgcolor: "rgba(15,23,42,0.55)",
                          color: "#E2E8F0",
                          "&:hover": { bgcolor: "rgba(15,23,42,0.75)" },
                        }}
                      >
                        <FlipIcon sx={{ fontSize: 18 }} />
                      </IconButton>
                    ) : null}

                    <Box
                      sx={{
                        position: "absolute",
                        left: 0,
                        right: 0,
                        bottom: 0,
                        height: 64,
                        background: "linear-gradient(180deg, transparent, rgba(2,6,23,0.68))",
                        pointerEvents: "none",
                      }}
                    />
                  </Box>
                );
              })()}
            </Box>

            {}
            <Box sx={{ mt: 1.25, p: 1.5, borderRadius: 3, border: "1px solid rgba(15,23,42,0.10)", bgcolor: "rgba(255,255,255,0.92)" }}>
              <Box sx={{ display: "grid", gridTemplateColumns: "1.1fr 0.9fr", gap: 1.25, alignItems: "start" }}>
                <Box>
                  <Typography
                    sx={{
                      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace',
                      fontWeight: 900,
                      fontSize: "1.1rem",
                      letterSpacing: "-0.02em",
                      color: "rgba(15,23,42,0.92)",
                    }}
                  >
                    {isConfirmedPlate(plate) ? plate : "NOT INFERRED"}
                  </Typography>
                  <Chip
                    size="small"
                    label={isConfirmedPlate(plate) ? "CONFIRMED" : "PENDING"}
                    color={isConfirmedPlate(plate) ? "success" : "default"}
                    variant={isConfirmedPlate(plate) ? "filled" : "outlined"}
                    sx={{ mt: 0.75, fontWeight: 800 }}
                  />
                </Box>
                <Box sx={{ display: "grid", gap: 0.75 }}>
                  <Box sx={{ display: "flex", justifyContent: "space-between", gap: 1 }}>
                    <Typography sx={{ fontSize: "0.75rem", color: pnp.textSecondary, fontWeight: 800 }}>Detected At</Typography>
                    <Typography sx={{ fontSize: "0.75rem", color: "rgba(15,23,42,0.86)", fontWeight: 900, textAlign: "right" }}>{detectedAt || "—"}</Typography>
                  </Box>
                  <Box sx={{ display: "flex", justifyContent: "space-between", gap: 1 }}>
                    <Typography sx={{ fontSize: "0.75rem", color: pnp.textSecondary, fontWeight: 800 }}>Location</Typography>
                    <Typography sx={{ fontSize: "0.75rem", color: "rgba(15,23,42,0.86)", fontWeight: 900, textAlign: "right" }}>{siteName || selected?.siteName || "—"}</Typography>
                  </Box>
                </Box>
              </Box>

              <Box sx={{ mt: 1.25, pt: 1.25, borderTop: "1px solid rgba(15,23,42,0.08)", display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 1 }}>
                <Box>
                  <Typography sx={{ fontSize: "0.6875rem", fontWeight: 900, letterSpacing: "0.12em", color: "rgba(100,116,139,0.95)", textTransform: "uppercase" }}>
                    Violation Type
                  </Typography>
                  <Typography sx={{ mt: 0.3, fontSize: "0.875rem", fontWeight: 900, color: "rgba(15,23,42,0.90)" }}>{violationTypeLabel(violationType)}</Typography>
                </Box>
                <Box>
                  <Typography sx={{ fontSize: "0.6875rem", fontWeight: 900, letterSpacing: "0.12em", color: "rgba(100,116,139,0.95)", textTransform: "uppercase" }}>
                    Amount
                  </Typography>
                  <Typography sx={{ mt: 0.3, fontSize: "0.875rem", fontWeight: 900, color: "rgba(15,23,42,0.90)" }}>{money(amount)}</Typography>
                </Box>
                <Box>
                  <Typography sx={{ fontSize: "0.6875rem", fontWeight: 900, letterSpacing: "0.12em", color: "rgba(100,116,139,0.95)", textTransform: "uppercase" }}>
                    Status
                  </Typography>
                  <Chip size="small" label="Pending" sx={{ mt: 0.55, fontWeight: 900, bgcolor: "rgba(245,158,11,0.14)", color: "rgba(124,45,18,0.9)" }} />
                </Box>
              </Box>

              <Box sx={{ mt: 1.25, display: "grid", gridTemplateColumns: "1fr", gap: 1 }}>
                <Button
                  variant="contained"
                  fullWidth
                  disabled={!feedRows.length}
                  onClick={() => advanceViolation()}
                  startIcon={<AutorenewOutlinedIcon sx={{ color: "#fff" }} />}
                  sx={primaryActionBtnSx}
                >
                  Skip This Violation
                </Button>
                <Button
                  variant="outlined"
                  fullWidth
                  color="error"
                  disabled={!selected?.id}
                  onClick={() => void markInvalid()}
                  sx={{ borderRadius: 2, py: 1.05, fontWeight: 900 }}
                >
                  Mark Invalid
                </Button>
              </Box>
            </Box>
          </Box>

          {}
          <Box sx={{ gridColumn: { xs: "1 / -1", lg: "span 4" } }}>
            <Typography sx={{ fontWeight: 800, fontSize: "0.875rem", mb: 1 }}>Vehicle & Owner Details</Typography>
            <Box sx={{ p: 1.25, borderRadius: 2, border: pnp.cardBorder }}>
              <Stack spacing={1.25}>
                <TextField
                  label="Vehicle Number"
                  value={plate}
                  onChange={(e) => setPlate(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && plate.trim() && !savingPlate) void submitPlate();
                  }}
                />
                <Button variant="outlined" onClick={() => void submitPlate()} disabled={!isConfirmedPlate(plate) || savingPlate}>
                  {savingPlate ? "Fetching…" : "Fetch owner details"}
                </Button>
                <Divider />
                <TextField
                  label="Owner Name"
                  value={ownerName}
                  slotProps={{ input: { readOnly: true } }}
                  sx={{ "& .MuiInputBase-root": { bgcolor: "rgba(15,23,42,0.04)" } }}
                />
                <TextField
                  label="Email"
                  value={ownerEmail}
                  slotProps={{ input: { readOnly: true } }}
                  sx={{ "& .MuiInputBase-root": { bgcolor: "rgba(15,23,42,0.04)" } }}
                />
                <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" }, gap: 1.25 }}>
                  <TextField label="Phone" value={ownerPhone} onChange={(e) => setOwnerPhone(e.target.value)} />
                  <TextField label="Address" value={ownerAddress} onChange={(e) => setOwnerAddress(e.target.value)} />
                </Box>
                <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
                  <Chip
                    size="small"
                    icon={<CheckCircleOutlinedIcon />}
                    label={ownerEmail && isConfirmedPlate(plate) ? "Owner matched" : "Owner not loaded"}
                    color={ownerEmail && isConfirmedPlate(plate) ? "success" : "default"}
                    variant={ownerEmail && isConfirmedPlate(plate) ? "filled" : "outlined"}
                  />
                </Box>
              </Stack>
            </Box>

            <Typography sx={{ fontWeight: 800, fontSize: "0.875rem", mt: 2, mb: 1 }}>Violation Summary</Typography>
            <Box sx={{ p: 1.25, borderRadius: 2, border: pnp.cardBorder }}>
              <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" }, gap: 1 }}>
                {[
                  { k: "Ticket No.", v: selected?.id ? `VT-${String(selected.id).padStart(6, "0")}` : "—" },
                  { k: "Violation", v: violationTypeLabel(violationType) },
                  { k: "Amount", v: money(amount) },
                  { k: "Detected", v: detectedAt || "—" },
                  { k: "Site", v: displaySite },
                  { k: "Status", v: "Pending" },
                ].map((it) => (
                  <Box key={it.k} sx={{ p: 1, borderRadius: 2, border: "1px solid rgba(15,23,42,0.08)", bgcolor: "rgba(255,255,255,0.7)" }}>
                    <Typography sx={{ fontSize: "0.6875rem", fontWeight: 900, letterSpacing: "0.1em", color: "rgba(100,116,139,0.95)", textTransform: "uppercase" }}>
                      {it.k}
                    </Typography>
                    <Typography sx={{ mt: 0.35, fontWeight: 800, fontSize: "0.8125rem" }}>{String(it.v)}</Typography>
                  </Box>
                ))}
              </Box>
            </Box>

            <Typography sx={{ fontWeight: 800, fontSize: "0.875rem", mt: 2, mb: 1 }}>Issue Ticket</Typography>
            <Box sx={{ p: 1.25, borderRadius: 2, border: pnp.cardBorder }}>
              <Stack spacing={1.25}>
                <TextField label="Amount (PHP)" value={amount} onChange={(e) => setAmount(Number(e.target.value || 0))} />
                <TextField label="Violation Date & Time" value={detectedAt} onChange={(e) => setDetectedAt(e.target.value)} />
                <TextField label="Site / Location" value={siteName} onChange={(e) => setSiteName(e.target.value)} placeholder={displaySite} />
                <Divider />
                {error ? <Alert severity="error">{error}</Alert> : null}
                <Button
                  variant="contained"
                  startIcon={<LocalPoliceOutlinedIcon />}
                  disabled={!canSubmit || sending}
                  onClick={() => void createAndSend()}
                  sx={{ ...primaryActionBtnSx, py: 1.35 }}
                >
                  Issue Ticket &amp; Notify Owner
                </Button>
              </Stack>
            </Box>
          </Box>

          {}
          <Box sx={{ gridColumn: { xs: "1 / -1", lg: "span 3" } }}>
            <Typography sx={{ fontWeight: 800, fontSize: "0.875rem", mb: 1 }}>Ticket Stats (Today)</Typography>
            <Box sx={{ p: 1.25, borderRadius: 2, border: pnp.cardBorder }}>
              <Box sx={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 1 }}>
                {[
                  { label: "Generated", value: statsQ.data?.generated ?? 0 },
                  { label: "Invalid", value: statsQ.data?.invalid ?? 0 },
                  { label: "Pending", value: statsQ.data?.pending ?? 0 },
                  { label: "Failed", value: statsQ.data?.failed ?? 0 },
                ].map((k) => (
                  <Box
                    key={k.label}
                    sx={{
                      textAlign: "center",
                      p: 1.25,
                      minWidth: 0,
                      borderRadius: 2,
                      bgcolor: "rgba(15,23,42,0.03)",
                      border: "1px solid rgba(15, 23, 42, 0.06)",
                    }}
                  >
                    <Typography sx={{ fontWeight: 900, fontSize: "1.125rem", lineHeight: 1.2 }}>{k.value}</Typography>
                    <Typography
                      sx={{
                        fontSize: "0.6875rem",
                        color: pnp.textSecondary,
                        fontWeight: 700,
                        mt: 0.35,
                        lineHeight: 1.2,
                        wordBreak: "keep-all",
                      }}
                    >
                      {k.label}
                    </Typography>
                  </Box>
                ))}
              </Box>

              <Box sx={{ mt: 1.5, height: 150 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={donutData.series.length ? donutData.series : [{ name: "No data", value: 1, color: "rgba(148,163,184,0.35)" }]}
                      dataKey="value"
                      nameKey="name"
                      innerRadius={48}
                      outerRadius={68}
                      paddingAngle={2}
                      isAnimationActive={false}
                    >
                      {(donutData.series.length ? donutData.series : [{ name: "No data", value: 1, color: "rgba(148,163,184,0.35)" }]).map((entry, idx) => (
                        <Cell key={idx} fill={(entry as any).color} stroke="rgba(255,255,255,0.75)" strokeWidth={1} />
                      ))}
                    </Pie>
                    <ReTooltip />
                  </PieChart>
                </ResponsiveContainer>
                <Box sx={{ mt: -11.5, textAlign: "center", pointerEvents: "none" }}>
                  <Typography sx={{ fontWeight: 900, fontSize: "1.25rem", lineHeight: 1 }}>{donutData.total ? `${donutData.pctGenerated}%` : "—"}</Typography>
                </Box>
              </Box>

              <Box sx={{ mt: 1.25, display: "flex", justifyContent: "space-between" }}>
                <Typography sx={{ fontSize: "0.75rem", color: pnp.textSecondary }}>Total Amount</Typography>
                <Typography sx={{ fontWeight: 900 }}>{money(statsQ.data?.amount ?? 0)}</Typography>
              </Box>
              <Box sx={{ mt: 1 }}>
                <Link href="/violations" underline="none" sx={{ fontSize: "0.75rem", fontWeight: 800 }}>
                  View full report →
                </Link>
              </Box>
            </Box>

            <Typography sx={{ fontWeight: 800, fontSize: "0.875rem", mt: 2, mb: 1 }}>Recent Activity</Typography>
            <Box sx={{ p: 1.25, borderRadius: 2, border: pnp.cardBorder }}>
              <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 1 }}>
                <Typography sx={{ fontSize: "0.75rem", color: pnp.textSecondary }}>Latest tickets</Typography>
                <Button size="small" onClick={() => setPageTab("history")} sx={{ fontSize: "0.75rem", fontWeight: 800, minWidth: 0, p: 0 }}>
                  View all
                </Button>
              </Box>
              <Stack spacing={1}>
                {(statsQ.data?.recent || []).slice(0, 5).map((r: any) => {
                  const violationId = Number(r.violationId);
                  const canOpen = Number.isFinite(violationId) && violationId > 0;
                  const openViolation = () => {
                    if (!canOpen) return;
                    navigate(
                      violationEventPath({
                        violationId,
                        violationType: r.violationType,
                        plate: r.plate,
                        detectedAt: r.detectedAt,
                      })
                    );
                  };
                  return (
                    <Box
                      key={r.violationId ?? r.id}
                      role={canOpen ? "button" : undefined}
                      tabIndex={canOpen ? 0 : undefined}
                      onClick={canOpen ? openViolation : undefined}
                      onKeyDown={
                        canOpen
                          ? (e) => {
                              if (e.key === "Enter" || e.key === " ") {
                                e.preventDefault();
                                openViolation();
                              }
                            }
                          : undefined
                      }
                      sx={{
                        display: "flex",
                        justifyContent: "space-between",
                        gap: 1,
                        alignItems: "center",
                        p: 1,
                        borderRadius: 2,
                        bgcolor: "rgba(15,23,42,0.03)",
                        cursor: canOpen ? "pointer" : "default",
                        transition: "background 0.15s ease, box-shadow 0.15s ease",
                        "&:hover": canOpen ? { bgcolor: "rgba(37,99,235,0.08)", boxShadow: "0 0 0 1px rgba(37,99,235,0.2)" } : undefined,
                      }}
                    >
                      <Box sx={{ minWidth: 0 }}>
                        <Typography sx={{ fontWeight: 800, fontSize: "0.8125rem" }}>{r.plate || "—"}</Typography>
                        <Typography sx={{ fontSize: "0.6875rem", color: pnp.textSecondary }}>
                          {violationTypeLabel(r.violationType)}
                          {r.detectedAt ? ` · ${r.detectedAt}` : ""}
                        </Typography>
                      </Box>
                      <Chip
                        size="small"
                        icon={<VisibilityOutlinedIcon />}
                        label={r.status === "generated" ? "Generated" : r.status === "invalid" ? "Invalid" : String(r.status || "—")}
                        color={r.status === "generated" ? "success" : r.status === "invalid" ? "default" : "default"}
                        variant="filled"
                        onClick={(e) => {
                          e.stopPropagation();
                          openViolation();
                        }}
                        sx={{ fontWeight: 800 }}
                      />
                    </Box>
                  );
                })}
                {!statsQ.data?.recent?.length ? (
                  <Typography sx={{ fontSize: "0.75rem", color: pnp.textSecondary }}>No recent tickets yet.</Typography>
                ) : null}
              </Stack>
            </Box>
          </Box>
        </Box>
      </Paper>

    </Box>
  );

  return (
    <Box sx={pageLayoutSx}>
      {smtpQ.data && !smtpQ.data.configured && pageTab === "create" ? (
        <Alert severity="warning" sx={{ mb: 2 }}>
          Email is not active (demo mode). Add your Google App Password to{" "}
          <strong>/home/aiserver/mern-vsp/server/smtp.env</strong> on the <code>SMTP_PASS=</code> line, then restart the API.
          Tickets will not reach owners until this is done.
        </Alert>
      ) : null}

      <Paper sx={{ ...contentCardSx, mb: 2, px: { xs: 0.5, sm: 1 }, pt: 0.5 }}>
        <Tabs
          value={pageTab}
          onChange={(_, v) => setPageTab(v as "create" | "history")}
          sx={{
            minHeight: 44,
            "& .MuiTab-root": { fontWeight: 800, fontSize: "0.875rem", textTransform: "none", minHeight: 44 },
            "& .Mui-selected": { color: "#2563EB" },
            "& .MuiTabs-indicator": { height: 3, borderRadius: 2, bgcolor: "#2563EB" },
          }}
        >
          <Tab label="Generate Ticket" value="create" />
          <Tab label="Ticket History" value="history" />
        </Tabs>
      </Paper>

      {pageTab === "create" ? autoPanel : <ChallanHistoryPanel />}
    </Box>
  );
}

