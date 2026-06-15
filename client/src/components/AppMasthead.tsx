import { Avatar, Badge, Box, Button, IconButton, Typography } from "@mui/material";
import LogoutIcon from "@mui/icons-material/Logout";
import NotificationsNoneOutlinedIcon from "@mui/icons-material/NotificationsNoneOutlined";
import MailOutlineOutlinedIcon from "@mui/icons-material/MailOutlineOutlined";
import { SITE_LABELS } from "../i18n/lang";
import { useShellHeader } from "../context/ShellHeaderContext";
import { pnp, pnpFont } from "../lib/pnpTheme";

type Props = {
  pageTitle: string;
  pageSubtitle?: string;
  userEmail?: string | null;
  onSignOut: () => void;
};

function initialsFromEmail(email?: string | null): string {
  if (!email) return "OP";
  const local = email.split("@")[0] ?? "";
  const parts = local.split(/[._-]+/).filter(Boolean);
  if (parts.length >= 2) return `${parts[0][0] ?? ""}${parts[1][0] ?? ""}`.toUpperCase();
  return local.slice(0, 2).toUpperCase();
}

function displayName(email?: string | null): string {
  if (!email) return "Operations Officer";
  return email
    .split("@")[0]
    .replace(/[._-]+/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function AppMasthead({ pageTitle, pageSubtitle, userEmail, onSignOut }: Props) {
  const { rightSlot, leftSlot } = useShellHeader();
  const subtitle = pageSubtitle?.trim() || undefined;

  return (
    <Box
      sx={{
        width: "100%",
        minWidth: 0,
        boxSizing: "border-box",
        px: { xs: 2, sm: 2.5 },
        py: { xs: 1, sm: 1.25 },
        minHeight: { xs: 64, sm: 72 },
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: { xs: 1.5, md: 2 },
        flexWrap: { xs: "wrap", lg: "nowrap" },
      }}
    >
      {}
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          gap: 1.25,
          minWidth: 0,
          flex: { xs: "1 1 100%", lg: "1 1 auto" },
          order: { xs: 1, lg: 0 },
          overflow: "hidden",
        }}
      >
        {leftSlot}
        <Box sx={{ minWidth: 0, overflow: "hidden" }}>
          <Typography sx={{ ...pnpFont.pageTitle }} noWrap>
            {pageTitle}
          </Typography>
          {subtitle ? (
            <Typography sx={{ ...pnpFont.pageSubtitle, mt: 0.35 }} noWrap>
              {subtitle}
            </Typography>
          ) : null}
        </Box>
      </Box>

      {}
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          gap: { xs: 0.75, sm: 1 },
          flexShrink: 0,
          flexWrap: "nowrap",
          minWidth: 0,
          order: { xs: 2, lg: 1 },
          flex: { xs: "1 1 100%", lg: "0 0 auto" },
          justifyContent: { xs: "flex-start", lg: "flex-end" },
          overflow: "hidden",
        }}
      >
        {rightSlot}
        <IconButton
          size="small"
          aria-label="Notifications"
          sx={{ border: pnp.cardBorder, borderRadius: "8px", width: 36, height: 36, flexShrink: 0 }}
        >
          <Badge badgeContent={3} color="error">
            <NotificationsNoneOutlinedIcon sx={{ fontSize: 20, color: pnp.text }} />
          </Badge>
        </IconButton>
        <IconButton
          size="small"
          aria-label="Messages"
          sx={{
            border: pnp.cardBorder,
            borderRadius: "8px",
            width: 36,
            height: 36,
            flexShrink: 0,
            display: { xs: "none", sm: "inline-flex" },
          }}
        >
          <Badge badgeContent={2} color="error">
            <MailOutlineOutlinedIcon sx={{ fontSize: 20, color: pnp.text }} />
          </Badge>
        </IconButton>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, pl: 0.25, flexShrink: 0, minWidth: 0 }}>
          <Avatar sx={{ width: 38, height: 38, bgcolor: pnp.primary, fontSize: "0.8125rem", fontWeight: 700, flexShrink: 0 }}>
            {initialsFromEmail(userEmail)}
          </Avatar>
          <Box sx={{ display: { xs: "none", md: "block" }, minWidth: 0, maxWidth: 160 }}>
            <Typography sx={{ fontSize: "0.8125rem", fontWeight: 700, color: pnp.text, lineHeight: 1.2 }} noWrap>
              {displayName(userEmail)}
            </Typography>
            <Typography sx={{ fontSize: "0.6875rem", color: pnp.textSecondary }} noWrap>
              Operations Officer
            </Typography>
          </Box>
        </Box>
        <Button
          size="small"
          variant="outlined"
          startIcon={<LogoutIcon sx={{ fontSize: 18 }} />}
          onClick={onSignOut}
          sx={{
            fontWeight: 600,
            fontSize: "0.8125rem",
            borderColor: "rgba(15, 23, 42, 0.12)",
            color: pnp.text,
            borderRadius: "8px",
            textTransform: "none",
            flexShrink: 0,
            display: { xs: "none", xl: "inline-flex" },
          }}
        >
          {SITE_LABELS.signOut}
        </Button>
      </Box>
    </Box>
  );
}
