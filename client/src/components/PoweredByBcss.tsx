import { Box, Tooltip, Typography } from "@mui/material";

const LOGO_SRC = `${import.meta.env.BASE_URL}BcssLogo.png`;

type Variant = "sidebar" | "sidebarCollapsed" | "login" | "loginCompact" | "loginCard" | "footerCompact";

type Props = {
  variant?: Variant;
};

export function PoweredByBcss({ variant = "sidebar" }: Props) {
  if (variant === "sidebarCollapsed") {
    return (
      <Tooltip title="Powered by BCSS" placement="right" arrow>
        <Box
          sx={{
            width: 52,
            mx: "auto",
            p: 0.65,
            borderRadius: 1.5,
            bgcolor: "#FFFFFF",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            boxShadow: "0 4px 14px rgba(15,23,42,0.18)",
          }}
        >
          <Box
            component="img"
            src={LOGO_SRC}
            alt="BCSS"
            sx={{ width: "100%", height: "auto", display: "block", objectFit: "contain" }}
          />
        </Box>
      </Tooltip>
    );
  }

  if (variant === "footerCompact") {
    return (
      <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
        <Typography sx={{ fontSize: "0.5625rem", fontWeight: 600, color: "rgba(203,213,225,0.75)" }}>Powered by</Typography>
        <Box
          sx={{
            width: 88,
            px: 0.85,
            py: 0.5,
            borderRadius: 1,
            bgcolor: "#FFFFFF",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <Box component="img" src={LOGO_SRC} alt="BCSS" sx={{ width: "100%", height: "auto", maxHeight: 22, objectFit: "contain" }} />
        </Box>
      </Box>
    );
  }

  if (variant === "loginCard") {
    return (
      <Box
        sx={{
          mt: 2,
          pt: 2,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 0.65,
        }}
      >
        <Typography
          sx={{
            fontWeight: 600,
            fontSize: "0.5625rem",
            letterSpacing: "0.14em",
            textTransform: "uppercase",
            color: "#94A3B8",
          }}
        >
          Powered by
        </Typography>
        <Box
          sx={{
            width: 132,
            px: 1.1,
            py: 0.75,
            borderRadius: 1.5,
            bgcolor: "#FFFFFF",
            border: "1px solid rgba(23,38,56,0.08)",
            boxShadow: "0 4px 16px rgba(15,23,42,0.08)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <Box
            component="img"
            src={LOGO_SRC}
            alt="BCSS"
            sx={{ width: "100%", height: "auto", maxHeight: 36, objectFit: "contain" }}
          />
        </Box>
      </Box>
    );
  }

  if (variant === "loginCompact") {
    return (
      <Box
        sx={{
          mt: 3,
          pt: 2.5,
          borderTop: "1px solid",
          borderColor: "divider",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 0.75,
        }}
      >
        <Typography
          sx={{
            fontWeight: 600,
            fontSize: "0.625rem",
            letterSpacing: "0.14em",
            textTransform: "uppercase",
            color: "text.secondary",
          }}
        >
          Powered by
        </Typography>
        <Box
          sx={{
            width: 148,
            px: 1.25,
            py: 0.85,
            borderRadius: 1.5,
            bgcolor: "#FFFFFF",
            border: "1px solid rgba(23,38,56,0.08)",
            boxShadow: "0 6px 20px rgba(15,23,42,0.08)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <Box
            component="img"
            src={LOGO_SRC}
            alt="BCSS"
            sx={{ width: "100%", height: "auto", maxHeight: 40, objectFit: "contain" }}
          />
        </Box>
      </Box>
    );
  }

  if (variant === "login") {
    return (
      <Box
        sx={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 1,
          width: "100%",
        }}
      >
        <Typography
          sx={{
            fontWeight: 600,
            fontSize: "0.6875rem",
            letterSpacing: "0.16em",
            textTransform: "uppercase",
            color: "rgba(248,250,252,0.62)",
            textAlign: "center",
          }}
        >
          Powered by
        </Typography>
        <Box
          sx={{
            width: { md: 200, lg: 220 },
            px: 1.5,
            py: 1.1,
            borderRadius: 2,
            bgcolor: "#FFFFFF",
            boxShadow: "0 10px 32px rgba(0,0,0,0.22)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <Box
            component="img"
            src={LOGO_SRC}
            alt="BCSS"
            sx={{ width: "100%", height: "auto", maxHeight: 52, objectFit: "contain" }}
          />
        </Box>
      </Box>
    );
  }

  return (
    <Box
      sx={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 0.75,
        width: "100%",
      }}
    >
      <Typography
        sx={{
          fontWeight: 600,
          fontSize: "0.625rem",
          letterSpacing: "0.14em",
          textTransform: "uppercase",
          color: "rgba(241,245,249,0.68)",
          lineHeight: 1,
        }}
      >
        Powered by
      </Typography>
      <Box
        sx={{
          width: "100%",
          maxWidth: 210,
          px: 1.35,
          py: 1,
          borderRadius: 2,
          bgcolor: "#FFFFFF",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          boxShadow: "0 8px 22px rgba(15,23,42,0.2)",
        }}
      >
        <Box
          component="img"
          src={LOGO_SRC}
          alt="BCSS"
          sx={{ width: "100%", height: "auto", maxHeight: 46, objectFit: "contain" }}
        />
      </Box>
    </Box>
  );
}
