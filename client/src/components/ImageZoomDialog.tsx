import { useEffect, useState } from "react";
import { Box, Chip, Dialog, IconButton, Typography } from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import FlipIcon from "@mui/icons-material/Flip";

export type ImageZoomPayload = {

  src: string;
  sceneSrc?: string;
  plateSrc?: string;
};

type ImageZoomDialogProps = {
  open: boolean;
  payload: ImageZoomPayload | null;
  onClose: () => void;
  title?: string;
};

export function ImageZoomDialog({ open, payload, onClose, title = "Capture" }: ImageZoomDialogProps) {
  const [view, setView] = useState<"scene" | "plate">("scene");

  const sceneSrc = payload?.sceneSrc;
  const plateSrc = payload?.plateSrc;
  const hasScene = Boolean(sceneSrc);
  const hasPlate = Boolean(plateSrc);
  const showToggle = hasScene && hasPlate;

  useEffect(() => {
    if (!open || !payload) return;
    if (plateSrc && payload.src === plateSrc) setView("plate");
    else setView("scene");
  }, [open, payload, plateSrc]);

  const activeSrc =
    showToggle && view === "plate" && plateSrc
      ? plateSrc
      : showToggle && view === "scene" && sceneSrc
        ? sceneSrc
        : payload?.src;

  const modalIconShell = {
    zIndex: 2,
    bgcolor: "rgba(15,23,42,0.72)",
    color: "#fff",
    "&:hover": { bgcolor: "rgba(15,23,42,0.88)" },
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="lg" fullWidth slotProps={{ paper: { sx: { borderRadius: 2 } } }}>
      <Box sx={{ position: "relative", p: { xs: 2, sm: 2.5 }, pt: { xs: 5.5, sm: 3 } }}>
        {showToggle ? (
          <IconButton
            onClick={() => setView((v) => (v === "scene" ? "plate" : "scene"))}
            aria-label={view === "scene" ? "Show plate crop" : "Show scene"}
            title={view === "scene" ? "Show plate crop" : "Show scene"}
            size="small"
            sx={{ position: "absolute", top: 8, right: 48, ...modalIconShell }}
          >
            <FlipIcon fontSize="small" />
          </IconButton>
        ) : null}

        <IconButton
          onClick={onClose}
          aria-label="Close"
          size="small"
          sx={{ position: "absolute", top: 8, right: 8, ...modalIconShell }}
        >
          <CloseIcon fontSize="small" />
        </IconButton>

        <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap", pr: showToggle ? 12 : 5, mb: 2 }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 900 }}>
            {title}
          </Typography>
          {showToggle ? (
            <Chip
              size="small"
              label={view === "plate" ? "Plate crop" : "Scene"}
              sx={{ fontWeight: 800, bgcolor: "rgba(29,78,216,0.1)", color: "primary.dark" }}
            />
          ) : null}
        </Box>

        {activeSrc ? (
          <Box
            sx={{
              display: "flex",
              justifyContent: "center",
              alignItems: "center",
              bgcolor: "#0b1220",
              borderRadius: 2,
              overflow: "hidden",
            }}
          >
            <img
              src={activeSrc}
              alt={view === "plate" ? "Plate crop" : "Scene capture"}
              style={{ maxWidth: "100%", maxHeight: "75vh", objectFit: "contain", display: "block" }}
            />
          </Box>
        ) : null}
      </Box>
    </Dialog>
  );
}
