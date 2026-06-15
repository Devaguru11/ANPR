const jwt = require("jsonwebtoken");

const JWT_SECRET = process.env.JWT_SECRET || "anpr-demo-jwt-secret";

function requireAuth(req, res, next) {
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
