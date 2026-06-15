import { createTheme } from "@mui/material/styles";
import { pnp } from "./lib/pnpTheme";

const easeOut = "cubic-bezier(0.22, 1, 0.36, 1)";
const reducedMotion = "@media (prefers-reduced-motion: reduce)";

export const theme = createTheme({
  palette: {
    mode: "light",
    primary: { main: pnp.primary, light: "#60A5FA", dark: pnp.primaryDark, contrastText: "#FFFFFF" },
    secondary: { main: pnp.textSecondary, light: "#94A3B8", dark: "#475569", contrastText: "#FFFFFF" },
    info: { main: "#0EA5E9", light: "#38BDF8", dark: "#0284C7", contrastText: "#FFFFFF" },
    success: { main: pnp.success, light: "#4ADE80", dark: "#15803D", contrastText: "#FFFFFF" },
    error: { main: pnp.danger, light: "#F87171", dark: "#B91C1C", contrastText: "#FFFFFF" },
    warning: { main: pnp.warning, light: "#FB923C", dark: "#C2410C", contrastText: "#FFFFFF" },
    background: { default: pnp.pageBg, paper: pnp.cardBg },
    text: { primary: pnp.text, secondary: pnp.textSecondary },
    divider: "rgba(15, 23, 42, 0.08)",
  },
  shape: { borderRadius: pnp.cardRadius },
  typography: {
    fontFamily: ['"Inter"', "system-ui", "-apple-system", "Segoe UI", "Roboto", "Helvetica", "Arial", "sans-serif"].join(","),
    fontSize: 14,
    body1: { fontSize: "0.875rem", lineHeight: 1.5 },
    body2: { fontSize: "0.8125rem", lineHeight: 1.45 },
    h3: { fontWeight: 700, letterSpacing: "-0.03em", lineHeight: 1.2, fontSize: "1.5rem" },
    h4: { fontWeight: 700, letterSpacing: "-0.02em", lineHeight: 1.22, fontSize: "1.25rem" },
    h5: { fontWeight: 700, letterSpacing: "-0.02em", lineHeight: 1.25, fontSize: "1.0625rem" },
    h6: { fontWeight: 700, letterSpacing: "-0.01em", lineHeight: 1.3, fontSize: "0.9375rem" },
    subtitle1: { fontWeight: 600, fontSize: "0.9375rem" },
    subtitle2: { fontWeight: 600, fontSize: "0.8125rem" },
    button: { fontWeight: 600, fontSize: "0.875rem", textTransform: "none" },
    overline: { fontWeight: 700, fontSize: "0.625rem", letterSpacing: "0.1em", textTransform: "uppercase" },
  },
  transitions: {
    duration: { standard: 200, enteringScreen: 240, leavingScreen: 160 },
    easing: { easeOut, sharp: "cubic-bezier(0.4, 0, 0.6, 1)" },
  },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        body: { backgroundColor: pnp.pageBg, WebkitFontSmoothing: "antialiased", MozOsxFontSmoothing: "grayscale" },
        "::selection": { backgroundColor: "rgba(37, 99, 235, 0.2)", color: pnp.text },
        "#root": { minHeight: "100%" },
        [reducedMotion]: {
          "*": {
            animationDuration: "0.01ms !important",
            animationIterationCount: "1 !important",
            transitionDuration: "0.01ms !important",
          },
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          borderRadius: pnp.cardRadius,
          border: pnp.cardBorder,
          boxShadow: pnp.cardShadow,
          backgroundImage: "none",
          backgroundColor: pnp.cardBg,
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          borderRadius: pnp.cardRadius,
          border: pnp.cardBorder,
          boxShadow: pnp.cardShadow,
          [reducedMotion]: { transition: "none" },
        },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: { textTransform: "none", borderRadius: pnp.cardRadius, fontWeight: 600, [reducedMotion]: { transition: "none" } },
      },
      variants: [
        {
          props: { variant: "contained", color: "primary" },
          style: {
            backgroundImage: "linear-gradient(180deg, #3B82F6 0%, #2563EB 100%)",
            boxShadow: "0 2px 8px rgba(37, 99, 235, 0.28)",
            "&:hover": { backgroundImage: "linear-gradient(180deg, #2563EB 0%, #1D4ED8 100%)" },
          },
        },
      ],
    },
    MuiChip: { styleOverrides: { root: { fontWeight: 600, borderRadius: 6 } } },
    MuiOutlinedInput: {
      styleOverrides: {
        root: {
          borderRadius: pnp.cardRadius,
          background: "#FFFFFF",
          "&.Mui-focused": { boxShadow: "0 0 0 3px rgba(37, 99, 235, 0.18)" },
        },
      },
    },
    MuiListItemButton: { styleOverrides: { root: { borderRadius: pnp.cardRadius } } },
    MuiAlert: { styleOverrides: { root: { borderRadius: pnp.cardRadius } } },
  },
});

