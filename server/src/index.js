const path = require("path");
require("dotenv").config();

const smtpEnv = path.join(__dirname, "..", "smtp.env");
require("dotenv").config({ path: smtpEnv });
if (!String(process.env.SMTP_PASS || "").trim()) {
  require("dotenv").config({ path: path.join(__dirname, "..", "smtp.env.example") });
}
const express = require("express");
const cors = require("cors");
const helmet = require("helmet");
const { authRouter } = require("./routes/auth");
const { dashboardRouter } = require("./routes/dashboard");
const { streamsRouter } = require("./routes/streams");
const { watchlistRouter } = require("./routes/watchlist");
const { chatRouter } = require("./routes/chat");
const { assistantEnhanceRouter } = require("./routes/assistantEnhance");
const { chatAuditRouter } = require("./routes/chatAudit");
const { challanRouter } = require("./routes/challan");
const { requireAuth } = require("./middleware/requireAuth");
const { requireAuditAdmin } = require("./middleware/requireAuditAdmin");

const app = express();

app.set("trust proxy", 1);

app.use(helmet({ contentSecurityPolicy: false }));
app.use(cors({ origin: true, credentials: true }));
app.use(express.json({ limit: "2mb" }));

app.get("/api/health", (_req, res) => res.json({ ok: true }));

app.use("/api/auth", authRouter);
app.use("/api/dashboard", requireAuth, dashboardRouter);
app.use("/api/streams", requireAuth, streamsRouter);
app.use("/api/watchlist", requireAuth, watchlistRouter);
app.use("/api/chat", requireAuth, chatRouter);
app.use("/api/assistant-enhance", requireAuth, assistantEnhanceRouter);
app.use("/api/chat-audit", requireAuth, requireAuditAdmin, chatAuditRouter);
app.use("/api/challan", requireAuth, challanRouter);

app.use("/api/challan-public", challanRouter);

const port = Number(process.env.PORT || 4000);
app.listen(port, "0.0.0.0", () => {

  console.log(`API listening on :${port}`);
});
