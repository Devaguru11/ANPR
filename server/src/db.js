const mysql = require("mysql2/promise");

function required(name, val) {
  if (!val) throw new Error(`Missing env var: ${name}`);
  return val;
}

const pool = mysql.createPool({
  host: required("DB_HOST", process.env.DB_HOST),
  port: Number(process.env.DB_PORT || 3306),
  user: required("DB_USER", process.env.DB_USER),
  password: required("DB_PASSWORD", process.env.DB_PASSWORD),
  database: required("DB_NAME", process.env.DB_NAME),
  waitForConnections: true,
  connectionLimit: 10,
  queueLimit: 0,
  charset: "utf8mb4",
});

module.exports = { pool };
