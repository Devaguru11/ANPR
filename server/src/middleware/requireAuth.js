const jwt = require("jsonwebtoken");

const JWT_SECRET = process.env.JWT_SECRET || "anpr-demo-jwt-secret";
const INTERNAL_API_KEY = process.env.INTERNAL_API_KEY || "";

function requireAuth(req, res, next) {
  // Allow internal service-to-service calls via X-Internal-Key header.
  // This lets the Python assistant_enhance_service call dashboard endpoints
  // without going through the browser JWT flow.
  if (INTERNAL_API_KEY && req.headers["x-internal-key"] === INTERNAL_API_KEY) {
    req.user = { id: 0, email: "internal@service", role: "INTERNAL" };
    return next();
  }

  const h = String(req.headers.authorization || "");
  const m = /^Bearer\s+(.+)$/i.exec(h);
  if (!m) {
    return res.status(401).json({ error: "unauthorized", message: "Missing or invalid Authorization header." });
  }
  try {
    const payload = jwt.verify(m[1], JWT_SECRET);
    if (payload.typ !== "access") throw new Error("wrong token type");
    req.user = {
      id: Number(payload.sub),
      email: String(payload.email || ""),
      role: String(payload.role || "USER"),
      mustChangePassword: Boolean(payload.mc),
    };
    return next();
  } catch {
    return res.status(401).json({ error: "unauthorized", message: "Missing or invalid Authorization header." });
  }
}

module.exports = { requireAuth };

