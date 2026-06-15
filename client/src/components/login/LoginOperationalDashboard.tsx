import {
  Box,
  Chip,
  Divider,
  Stack,
  Typography,
} from "@mui/material";
import VideocamOutlinedIcon from "@mui/icons-material/VideocamOutlined";
import DirectionsCarFilledOutlinedIcon from "@mui/icons-material/DirectionsCarFilledOutlined";
import GppBadOutlinedIcon from "@mui/icons-material/GppBadOutlined";
import GroupsOutlinedIcon from "@mui/icons-material/GroupsOutlined";
import GavelOutlinedIcon from "@mui/icons-material/GavelOutlined";
import VerifiedUserOutlinedIcon from "@mui/icons-material/VerifiedUserOutlined";
import SmartToyOutlinedIcon from "@mui/icons-material/SmartToyOutlined";
import ScheduleOutlinedIcon from "@mui/icons-material/ScheduleOutlined";
import FiberManualRecordIcon from "@mui/icons-material/FiberManualRecord";
import { SITE_BRANDING } from "../../i18n/lang";
import { loginMiniCard, loginPanelBg } from "./loginTheme";
import { PhilippinesMapSvg } from "./PhilippinesMapSvg";
import { PnpBadge } from "../PnpBadge";

const AI_ALERTS = [
  { title: "Stolen Vehicle Detected", loc: "NCR, Quezon City", ago: "2 min ago", hot: true },
  { title: "No RFID / Blacklist Hit", loc: "Manila, Taft Ave", ago: "6 min ago", hot: true },
  { title: "Expired Registration", loc: "Cebu City", ago: "14 min ago", hot: false },
];

const ANPR_FEED = [
  { plate: "NDA 1234", region: "NCR" },
  { plate: "ABC 5678", region: "Region IV-A" },
  { plate: "ZXC 9012", region: "Region VII" },
];

const WATCHLIST = [
  { plate: "ABC 1234", status: "STOLEN", color: "#EF4444" },
  { plate: "DEF 5678", status: "WARRANT", color: "#F97316" },
  { plate: "GHI 9012", status: "ALERT", color: "#EAB308" },
];

const TRUST_BADGES = [
  { icon: <VerifiedUserOutlinedIcon sx={{ fontSize: 13 }} />, label: "SECURED Government System" },
  { icon: <SmartToyOutlinedIcon sx={{ fontSize: 13 }} />, label: "AI POWERED by AccessGenie" },
  { icon: <ScheduleOutlinedIcon sx={{ fontSize: 13 }} />, label: "24/7 Monitoring" },
];

const STAT_CARDS = [
  {
    icon: <VideocamOutlinedIcon sx={{ fontSize: 20 }} />,
    color: "#3B82F6",
    label: "Active Cameras",
    value: "1,248",
    sub: "Online",
  },
  {
    icon: <DirectionsCarFilledOutlinedIcon sx={{ fontSize: 20 }} />,
    color: "#22C55E",
    label: "Vehicles Scanned Today",
    value: "128,540",
    sub: "+18.6% vs yesterday",
    subColor: "#4ADE80",
  },
  {
    icon: <GppBadOutlinedIcon sx={{ fontSize: 20 }} />,
    color: "#EF4444",
    label: "Wanted Vehicle Alerts",
    value: "23",
    sub: "Requires attention",
    subColor: "#FCA5A5",
  },
  {
    icon: <GroupsOutlinedIcon sx={{ fontSize: 20 }} />,
    color: "#A855F7",
    label: "Officers Online",
    value: "3,542",
    sub: "Across all units",
  },
  {
    icon: <GavelOutlinedIcon sx={{ fontSize: 20 }} />,
    color: "#EAB308",
    label: "Violations Today",
    value: "2,847",
    sub: "+12.4% vs yesterday",
    subColor: "#FDE047",
  },
];

function MiniPanel({
  title,
  badge,
  badgeColor,
  liveDot,
  children,
  footer,
  footerColor,
}: {
  title: string;
  badge?: string;
  badgeColor?: string;
  liveDot?: "green" | "red";
  children: React.ReactNode;
  footer?: string;
  footerColor?: string;
}) {
  return (
    <Box sx={{ ...loginMiniCard, borderRadius: 2, p: 1.35, minWidth: 0 }}>
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mb: 1 }}>
        <Typography
          sx={{
            fontSize: "0.625rem",
            fontWeight: 800,
            letterSpacing: "0.14em",
            color: "rgba(226,232,240,0.95)",
            textTransform: "uppercase",
          }}
        >
          {title}
        </Typography>
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
          {liveDot ? (
            <>
              <FiberManualRecordIcon sx={{ fontSize: 8, color: liveDot === "green" ? "#22C55E" : "#EF4444" }} />
              <Typography sx={{ fontSize: "0.5625rem", fontWeight: 700, color: liveDot === "green" ? "#4ADE80" : "#F87171" }}>
                Live
              </Typography>
            </>
          ) : null}
          {badge ? (
            <Chip
              label={badge}
              size="small"
              sx={{
                height: 18,
                fontSize: "0.5625rem",
                fontWeight: 800,
                bgcolor: badgeColor ?? "#EF4444",
                color: "#fff",
                "& .MuiChip-label": { px: 0.75 },
              }}
            />
          ) : null}
        </Box>
      </Box>
      {children}
      {footer ? (
        <Typography
          sx={{
            mt: 1,
            fontSize: "0.625rem",
            fontWeight: 600,
            color: footerColor ?? "#60A5FA",
            cursor: "default",
          }}
        >
          {footer}
        </Typography>
      ) : null}
    </Box>
  );
}

export function LoginOperationalDashboard() {
  return (
    <Box
      sx={{
        display: { xs: "none", lg: "flex" },
        flexDirection: "column",
        minHeight: "100%",
        background: loginPanelBg,
        color: "#F8FAFC",
        overflow: "hidden",
        position: "relative",
      }}
    >
      <Box sx={{ px: { lg: 2.5, xl: 3 }, pt: 2.25, pb: 1.25, flexShrink: 0 }}>
        <Box sx={{ display: "flex", alignItems: "flex-start", gap: 2, mb: 1.25 }}>
          <PnpBadge size={112} sx={{ flexShrink: 0 }} />
          <Box sx={{ minWidth: 0, pt: 0.25 }}>
            <Typography
              sx={{
                fontWeight: 800,
                fontSize: { lg: "0.9375rem", xl: "1rem" },
                letterSpacing: "0.05em",
                lineHeight: 1.2,
                textTransform: "uppercase",
              }}
            >
              {SITE_BRANDING.productName}
            </Typography>
            <Typography
              sx={{
                fontWeight: 600,
                fontSize: { lg: "0.8125rem", xl: "0.875rem" },
                color: "rgba(226,232,240,0.92)",
                mt: 0.4,
                lineHeight: 1.35,
              }}
            >
              {SITE_BRANDING.loginHeroTitle}
            </Typography>
            <Typography
              sx={{
                mt: 0.65,
                fontSize: "0.6875rem",
                color: "rgba(148,163,184,0.95)",
                lineHeight: 1.5,
                maxWidth: 480,
              }}
            >
              {SITE_BRANDING.loginTagline}
            </Typography>
          </Box>
        </Box>
        <Stack direction="row" spacing={1} sx={{ mt: 0.75, flexWrap: "wrap", gap: 0.75 }}>
          {TRUST_BADGES.map((b) => (
            <Box
              key={b.label}
              sx={{
                display: "flex",
                alignItems: "center",
                gap: 0.65,
                px: 1,
                py: 0.45,
                borderRadius: 10,
                bgcolor: "rgba(15, 23, 42, 0.55)",
                border: "1px solid rgba(148, 163, 184, 0.18)",
              }}
            >
              <Box
                sx={{
                  width: 22,
                  height: 22,
                  borderRadius: "50%",
                  display: "grid",
                  placeItems: "center",
                  bgcolor: "rgba(59, 130, 246, 0.2)",
                  color: "#93C5FD",
                }}
              >
                {b.icon}
              </Box>
              <Typography sx={{ fontSize: "0.5625rem", fontWeight: 700, color: "rgba(226,232,240,0.92)", letterSpacing: "0.02em" }}>
                {b.label}
              </Typography>
            </Box>
          ))}
        </Stack>
      </Box>

      <Box
        sx={{
          flex: 1,
          display: "grid",
          gridTemplateColumns: {
            lg: "minmax(0, 228px) minmax(0, 1fr) minmax(0, 196px)",
          },
          gap: 1.25,
          px: { lg: 2.5, xl: 3 },
          pb: 1.25,
          minHeight: 0,
          alignItems: "stretch",
        }}
      >
        <Stack spacing={1.15} sx={{ minWidth: 0 }}>
          <MiniPanel title="AI Alerts" badge="3" footer="View all alerts →">
            <Stack spacing={0.9} divider={<Divider sx={{ borderColor: "rgba(148,163,184,0.12)" }} />}>
              {AI_ALERTS.map((a) => (
                <Box key={a.title} sx={{ display: "flex", gap: 0.75, alignItems: "flex-start" }}>
                  <FiberManualRecordIcon sx={{ fontSize: 8, color: a.hot ? "#EF4444" : "#64748B", mt: 0.55, flexShrink: 0 }} />
                  <Box sx={{ minWidth: 0, flex: 1 }}>
                    <Typography sx={{ fontSize: "0.6875rem", fontWeight: 700, lineHeight: 1.3 }}>{a.title}</Typography>
                    <Typography sx={{ fontSize: "0.5625rem", color: "rgba(148,163,184,0.92)", mt: 0.15 }}>{a.loc}</Typography>
                  </Box>
                  <Typography sx={{ fontSize: "0.5rem", color: "rgba(100,116,139,0.95)", flexShrink: 0, mt: 0.2 }}>
                    {a.ago}
                  </Typography>
                </Box>
              ))}
            </Stack>
          </MiniPanel>

          <MiniPanel title="Live ANPR Feed" liveDot="green">
            <Stack direction="row" spacing={0.75}>
              {ANPR_FEED.map((r) => (
                <Box key={r.plate} sx={{ flex: 1, minWidth: 0 }}>
                  <Box
                    sx={{
                      position: "relative",
                      aspectRatio: "4/3",
                      borderRadius: 1.25,
                      bgcolor: "rgba(2, 6, 23, 0.85)",
                      border: "1px solid rgba(59, 130, 246, 0.25)",
                      overflow: "hidden",
                      display: "grid",
                      placeItems: "center",
                    }}
                  >
                    <DirectionsCarFilledOutlinedIcon sx={{ fontSize: 22, color: "rgba(100,116,139,0.45)" }} />
                    <Box
                      sx={{
                        position: "absolute",
                        bottom: 4,
                        left: "50%",
                        transform: "translateX(-50%)",
                        px: 0.5,
                        py: 0.15,
                        borderRadius: 0.5,
                        bgcolor: "rgba(15, 23, 42, 0.92)",
                        border: "1px solid rgba(96, 165, 250, 0.45)",
                      }}
                    >
                      <Typography sx={{ fontSize: "0.5rem", fontWeight: 800, letterSpacing: "0.06em", color: "#F8FAFC" }}>
                        {r.plate}
                      </Typography>
                    </Box>
                  </Box>
                  <Typography sx={{ fontSize: "0.5rem", color: "rgba(148,163,184,0.88)", textAlign: "center", mt: 0.35 }}>
                    {r.region}
                  </Typography>
                </Box>
              ))}
            </Stack>
          </MiniPanel>

          <MiniPanel title="Watchlist Matches" liveDot="red" footer="View all watchlist →" footerColor="#FB923C">
            <Stack spacing={0.7}>
              {WATCHLIST.map((w) => (
                <Box key={w.plate} sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 0.5 }}>
                  <Typography sx={{ fontSize: "0.6875rem", fontWeight: 700, letterSpacing: "0.04em" }}>{w.plate}</Typography>
                  <Chip
                    label={w.status}
                    size="small"
                    sx={{
                      height: 17,
                      fontSize: "0.5rem",
                      fontWeight: 800,
                      bgcolor: w.color,
                      color: "#fff",
                      borderRadius: 0.75,
                      "& .MuiChip-label": { px: 0.65 },
                    }}
                  />
                </Box>
              ))}
            </Stack>
          </MiniPanel>
        </Stack>

        <Box
          sx={{
            ...loginMiniCard,
            borderRadius: 2,
            p: 1.35,
            display: "flex",
            flexDirection: "column",
            minWidth: 0,
            minHeight: 280,
          }}
        >
          <Box sx={{ flex: 1, minHeight: 240, display: "flex", flexDirection: "column" }}>
            <PhilippinesMapSvg />
          </Box>
        </Box>

        <Stack spacing={0.9} sx={{ minWidth: 0 }}>
          {STAT_CARDS.map((s) => (
            <Box
              key={s.label}
              sx={{
                ...loginMiniCard,
                borderRadius: 2,
                p: 1.15,
                borderLeft: `4px solid ${s.color}`,
                display: "flex",
                gap: 1,
                alignItems: "flex-start",
              }}
            >
              <Box
                sx={{
                  width: 36,
                  height: 36,
                  borderRadius: 1.25,
                  display: "grid",
                  placeItems: "center",
                  bgcolor: `${s.color}24`,
                  color: s.color,
                  flexShrink: 0,
                  boxShadow: `0 0 16px ${s.color}33`,
                }}
              >
                {s.icon}
              </Box>
              <Box sx={{ minWidth: 0 }}>
                <Typography sx={{ fontSize: "0.5625rem", fontWeight: 700, color: "rgba(148,163,184,0.95)", lineHeight: 1.2, textTransform: "uppercase", letterSpacing: "0.03em" }}>
                  {s.label}
                </Typography>
                <Typography sx={{ fontSize: "1.0625rem", fontWeight: 800, lineHeight: 1.15, letterSpacing: "-0.02em", mt: 0.1 }}>
                  {s.value}
                </Typography>
                <Typography
                  sx={{
                    fontSize: "0.5625rem",
                    fontWeight: 600,
                    color: s.subColor ?? "rgba(148,163,184,0.9)",
                    mt: 0.2,
                  }}
                >
                  {s.sub}
                </Typography>
              </Box>
            </Box>
          ))}
        </Stack>
      </Box>
    </Box>
  );
}
