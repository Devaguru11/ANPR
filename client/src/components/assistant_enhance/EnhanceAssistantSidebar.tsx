import { Box, Typography } from "@mui/material";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import BarChartOutlinedIcon from "@mui/icons-material/BarChartOutlined";
import PolicyOutlinedIcon from "@mui/icons-material/PolicyOutlined";
import VideocamOutlinedIcon from "@mui/icons-material/VideocamOutlined";
import TrendingUpOutlinedIcon from "@mui/icons-material/TrendingUpOutlined";
import type { ReactNode } from "react";
import { chatUi } from "../../lib/chatAssistantTheme";

const PROMPTS: { label: string; message: string; icon: ReactNode; color: string }[] = [
  { label: "Violations at Chowking", message: "Show all violations at Chowking", icon: <PolicyOutlinedIcon sx={{ fontSize: 18 }} />, color: chatUi.warning },
  { label: "Detections yesterday", message: "How many detections yesterday", icon: <BarChartOutlinedIcon sx={{ fontSize: 18 }} />, color: chatUi.primary },
  { label: "Most active camera", message: "Which camera is most active", icon: <VideocamOutlinedIcon sx={{ fontSize: 18 }} />, color: "#EAB308" },
  { label: "Violation trend 30 days", message: "Show violation trend for last 30 days", icon: <TrendingUpOutlinedIcon sx={{ fontSize: 18 }} />, color: chatUi.success },
  { label: "Top 10 violating vehicles", message: "Show top 10 violating vehicles", icon: <BarChartOutlinedIcon sx={{ fontSize: 18 }} />, color: "#F97316" },
];

function Panel({ title, icon, children }: { title: string; icon: ReactNode; children: ReactNode }) {
  return (
    <Box sx={{ borderRadius: chatUi.radius, border: chatUi.border, bgcolor: chatUi.surface, p: 2, mb: 2 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1.5 }}>
        <Box sx={{ color: chatUi.primary, display: "flex" }}>{icon}</Box>
        <Typography sx={{ fontWeight: 700, fontSize: "0.875rem", color: chatUi.text }}>{title}</Typography>
      </Box>
      {children}
    </Box>
  );
}

export function EnhanceAssistantSidebar({
  onPrompt,
  disabled = false,
}: {
  onPrompt: (message: string) => void;
  disabled?: boolean;
}) {
  return (
    <Box sx={{ width: { xs: "100%", lg: 300 }, flexShrink: 0 }}>
      <Panel title="Suggested Prompts" icon={<AutoAwesomeIcon sx={{ fontSize: 18 }} />}>
        <Box sx={{ display: "flex", flexDirection: "column", gap: 0.5 }}>
          {PROMPTS.map((p) => (
            <Box
              key={p.label}
              component="button"
              type="button"
              onClick={() => !disabled && onPrompt(p.message)}
              disabled={disabled}
              sx={{
                display: "flex",
                alignItems: "center",
                gap: 1.25,
                width: "100%",
                textAlign: "left",
                border: "none",
                cursor: disabled ? "not-allowed" : "pointer",
                opacity: disabled ? 0.5 : 1,
                borderRadius: chatUi.radiusSm,
                py: 1,
                px: 1,
                bgcolor: "transparent",
                color: chatUi.text,
                "&:hover": { bgcolor: "rgba(255,255,255,0.06)" },
              }}
            >
              <Box
                sx={{
                  width: 32,
                  height: 32,
                  borderRadius: "8px",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  bgcolor: `${p.color}22`,
                  color: p.color,
                  flexShrink: 0,
                }}
              >
                {p.icon}
              </Box>
              <Typography sx={{ flex: 1, fontSize: "0.8125rem", fontWeight: 500 }}>{p.label}</Typography>
              <ChevronRightIcon sx={{ fontSize: 18, color: chatUi.textMuted }} />
            </Box>
          ))}
        </Box>
      </Panel>
    </Box>
  );
}
