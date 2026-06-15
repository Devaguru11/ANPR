
export const pnp = {

  navy: "#001529",
  navySidebar: "#001529",
  navyMuted: "#0A2540",
  pageBg: "#F5F7FA",
  headerBg: "#FFFFFF",
  footerBg: "#0A192F",

  cardBg: "#FFFFFF",
  cardRadius: 10,
  cardBorder: "1px solid rgba(15, 23, 42, 0.07)",
  cardShadow: "0 1px 3px rgba(15, 23, 42, 0.06), 0 4px 16px rgba(15, 23, 42, 0.04)",

  primary: "#2563EB",
  primaryDark: "#1D4ED8",
  primarySoft: "#EFF6FF",
  success: "#16A34A",
  successSoft: "#DCFCE7",
  danger: "#DC2626",
  dangerSoft: "#FEE2E2",
  warning: "#EA580C",
  warningSoft: "#FFEDD5",
  purple: "#7C3AED",
  purpleSoft: "#F3E8FF",
  amber: "#EAB308",
  amberSoft: "#FEF9C3",

  text: "#0F172A",
  textSecondary: "#64748B",
  textMuted: "#94A3B8",

  navActiveGradient: "linear-gradient(90deg, #1D4ED8 0%, #2563EB 55%, #3B82F6 100%)",
  navActiveBar: "#60A5FA",
  navText: "rgba(226, 232, 240, 0.9)",
  navTextMuted: "rgba(148, 163, 184, 0.85)",

  loginBg: "#050B14",
  mapDark: "#0B1220",

  kpiBlue: "#2563EB",
  kpiGreen: "#16A34A",
  kpiRed: "#DC2626",
  kpiPurple: "#7C3AED",
  kpiOrange: "#EA580C",
} as const;

export const pnpSidebarBg = pnp.navySidebar;

export const pnpFont = {
  family: '"Inter", system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
  kpiLabel: { fontSize: "0.8125rem", fontWeight: 600, lineHeight: 1.35, color: pnp.textSecondary },
  kpiValue: { fontSize: "1.75rem", fontWeight: 800, lineHeight: 1.1, letterSpacing: "-0.03em", color: pnp.text },
  kpiTrend: { fontSize: "0.75rem", fontWeight: 600, lineHeight: 1.3 },
  cardTitle: { fontSize: "0.875rem", fontWeight: 700, lineHeight: 1.35, color: pnp.text },
  cardSubtitle: { fontSize: "0.75rem", fontWeight: 500, lineHeight: 1.4, color: pnp.textSecondary },
  pageTitle: { fontSize: "1.375rem", fontWeight: 700, letterSpacing: "-0.02em", lineHeight: 1.2, color: pnp.text },
  pageSubtitle: { fontSize: "0.8125rem", fontWeight: 500, lineHeight: 1.45, color: pnp.textSecondary },
} as const;

export const pnpNavItemSx = (selected: boolean) => ({
  position: "relative" as const,
  borderRadius: "8px",
  mb: 0.5,
  minHeight: 42,
  px: 1.5,
  py: 1,
  bgcolor: selected ? "transparent" : "transparent",
  background: selected ? pnp.navActiveGradient : "transparent",
  color: selected ? "#FFFFFF" : pnp.navText,
  boxShadow: selected ? "0 4px 14px rgba(37, 99, 235, 0.35)" : "none",
  "&::before": selected
    ? {
        content: '""',
        position: "absolute",
        left: 0,
        top: "20%",
        bottom: "20%",
        width: 4,
        borderRadius: "0 4px 4px 0",
        bgcolor: pnp.navActiveBar,
      }
    : {},
  "&:hover": {
    bgcolor: selected ? undefined : "rgba(255, 255, 255, 0.07)",
    background: selected ? pnp.navActiveGradient : "rgba(255, 255, 255, 0.07)",
  },
  "& .MuiListItemIcon-root": {
    color: "inherit",
    minWidth: 38,
  },
});
