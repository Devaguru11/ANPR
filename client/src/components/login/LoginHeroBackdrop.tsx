import { Box } from "@mui/material";
import { LOGIN_FLAG_IMAGE, LOGIN_HERO_IMAGE } from "./loginTheme";

export function LoginHeroBackdrop() {
  return (
    <>
      <Box
        component="img"
        src={LOGIN_HERO_IMAGE}
        alt=""
        aria-hidden
        sx={{
          position: "absolute",
          inset: 0,
          width: "100%",
          height: "100%",
          objectFit: "cover",
          objectPosition: "center center",
          filter: "saturate(1.05) brightness(0.92)",
        }}
      />
      <Box
        component="img"
        src={LOGIN_FLAG_IMAGE}
        alt=""
        aria-hidden
        sx={{
          position: "absolute",
          top: 0,
          right: 0,
          width: { xs: "52%", md: "48%" },
          maxWidth: 340,
          height: "auto",
          objectFit: "contain",
          objectPosition: "top right",
          pointerEvents: "none",
          filter: "drop-shadow(0 8px 24px rgba(0,0,0,0.35))",
        }}
      />
      <Box
        sx={{
          position: "absolute",
          inset: 0,
          background: `
            linear-gradient(105deg, rgba(5, 11, 20, 0.55) 0%, rgba(5, 11, 20, 0.2) 42%, rgba(2, 6, 23, 0.35) 100%),
            linear-gradient(180deg, rgba(5, 11, 20, 0.15) 0%, rgba(2, 6, 23, 0.75) 100%)
          `,
          pointerEvents: "none",
        }}
      />
    </>
  );
}
