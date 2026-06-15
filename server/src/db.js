const fs = require("fs/promises");
const path = require("path");
const mysql = require("mysql2/promise");

function required(name, val) {
  if (!val) throw new Error(`Missing env var: ${name}`);
  return val;
}

function hasDbConfig() {
  return Boolean(process.env.DB_HOST && process.env.DB_USER && process.env.DB_PASSWORD && process.env.DB_NAME);
}

function normalizeSql(sql) {
  return String(sql || "").trim().replace(/\s+/g, " ");
}

function mockCountRow(sql) {
  const match = /COUNT\(\*\)\s+AS\s+([a-zA-Z_][a-zA-Z0-9_]*)/i.exec(sql);
  const key = match ? match[1] : "total";
  return [{ [key]: 0 }];
}

function mockQuery(sql) {
  const text = normalizeSql(sql);
  if (/^SHOW TABLES LIKE /i.test(text)) {
    return [[]];
  }
  if (/^SELECT 1(\s+AS\s+1)?$/i.test(text)) {
    return [[{ 1: 1 }]];
  }
  if (/COUNT\(\*\)/i.test(text)) {
    return [mockCountRow(text)];
  }
  if (/^SELECT\s+id,\s+name\s+FROM\s+sites\b/i.test(text)) {
    return [[{ id: 1, name: "Default site" }]];
  }
  if (/^SELECT\s+enabled\s+FROM\s+lpr_(vehicle_lists|rules)\b/i.test(text)) {
    return [[]];
  }
  if (/^INSERT\b|^UPDATE\b|^DELETE\b/i.test(text)) {
    return [[{ affectedRows: 0, insertId: 0, warningStatus: 0 }]];
  }
  if (/^SELECT\b/i.test(text)) {
    return [[]];
  }
  return [[]];
}

function createMockPool() {
  const mockPool = {
    async query(sql) {
      return mockQuery(sql);
    },
    async execute(sql) {
      return mockQuery(sql);
    },
    async getConnection() {
      return mockPool;
    },
    async end() {},
  };
  return mockPool;
}

const mockPool = createMockPool();
const dumpPath = path.resolve(__dirname, "../../aiserver_anpr_last_3_days.sql");
const demoAdmin = {
  email: "admin@anpr.local",
  passwordHash: "$2b$10$BWCedgkLoZWG/kRTA/K17uDLHPA6SkayBxvMzf33x2AUZ8C..L.mi",
  role: "admin",
};
const realPool = hasDbConfig()
  ? mysql.createPool({
      host: required("DB_HOST", process.env.DB_HOST),
      port: Number(process.env.DB_PORT || 3306),
      user: required("DB_USER", process.env.DB_USER),
      password: required("DB_PASSWORD", process.env.DB_PASSWORD),
      database: required("DB_NAME", process.env.DB_NAME),
      waitForConnections: true,
      connectionLimit: 10,
      queueLimit: 0,
      charset: "utf8mb4",
    })
  : null;

let warnedFallback = false;
let databaseReadyPromise = null;

function shouldFallbackToMock(error) {
  const code = String(error?.code || "");
  return ["ER_NO_SUCH_TABLE", "ER_BAD_DB_ERROR", "ECONNREFUSED", "PROTOCOL_CONNECTION_LOST", "ER_ACCESS_DENIED_ERROR", "ENOTFOUND"].includes(code);
}

async function tableExistsDirect(pool, name) {
  const [rows] = await pool.query("SHOW TABLES LIKE ?", [name]);
  return Array.isArray(rows) && rows.length > 0;
}

async function importDumpIfNeeded() {
  if (!realPool) return;
  if (await tableExistsDirect(realPool, "anpr_app_audit_log")) return;

  const dumpSql = await fs.readFile(dumpPath, "utf8");
  const connection = await mysql.createConnection({
    host: required("DB_HOST", process.env.DB_HOST),
    port: Number(process.env.DB_PORT || 3306),
    user: required("DB_USER", process.env.DB_USER),
    password: required("DB_PASSWORD", process.env.DB_PASSWORD),
    database: required("DB_NAME", process.env.DB_NAME),
    multipleStatements: true,
    charset: "utf8mb4",
  });

  try {
    await connection.query(dumpSql);
    console.log(`[db] imported ${path.basename(dumpPath)}`);
  } finally {
    await connection.end();
  }
}

async function seedLocalDemoData() {
  if (!realPool) return;

  await realPool.query(
    `INSERT INTO anpr_app_users
      (email, password_hash, role, disabled_at, failed_login_count, locked_until, must_change_password, token_version)
     VALUES (?, ?, ?, NULL, 0, NULL, 0, 0)
     ON DUPLICATE KEY UPDATE
       password_hash = VALUES(password_hash),
       role = VALUES(role),
       disabled_at = NULL,
       failed_login_count = 0,
       locked_until = NULL,
       must_change_password = 0,
       token_version = 0`,
    [demoAdmin.email, demoAdmin.passwordHash, demoAdmin.role]
  );

  const [[listCountRow]] = await realPool.query(
    "SELECT COUNT(*) AS total FROM lpr_vehicle_lists WHERE name = ?",
    ["Stolen vehicles"]
  );
  if (Number(listCountRow?.total || 0) === 0) {
    const [result] = await realPool.query(
      `INSERT INTO lpr_vehicle_lists (enabled, name, notes, site_id, created_at, updated_at)
       VALUES (1, 'Stolen vehicles', 'Demo watchlist', 1, NOW(), NOW())`
    );
    await realPool.query(
      `INSERT INTO lpr_vehicle_list_vehicles (vehicle_list_id, conditions, created_at, updated_at)
       VALUES (?, ?, NOW(), NOW())`,
      [result.insertId, JSON.stringify([{ lp: { eq: "ABC1234" } }])]
    );
  }

  const [[ruleCountRow]] = await realPool.query(
    "SELECT COUNT(*) AS total FROM lpr_rules WHERE name = ?",
    ["Demo alert rule"]
  );
  if (Number(ruleCountRow?.total || 0) === 0) {
    await realPool.query(
      `INSERT INTO lpr_rules (
        enabled, barrierOpen, filterType, vehicleListIds, name, access_type, security_type,
        priority, site_id, conditions, valid_from, valid_to, created_at, updated_at
      ) VALUES (
        1, 0, 'plate', '""', 'Demo alert rule', 'deny', 'hotlist',
        10, 1, ?, NULL, NULL, NOW(), NOW()
      )`,
      [JSON.stringify([{ _cameras: { ids: ["AEYE_1", "AEYE_2"] } }, { lp: { eq: "ABC1234" } }])]
    );
  }
}

async function ensureDatabaseReady() {
  if (!realPool) return;
  if (!databaseReadyPromise) {
    databaseReadyPromise = (async () => {
      try {
        await importDumpIfNeeded();
        await seedLocalDemoData();
      } catch (error) {
        databaseReadyPromise = null;
        console.warn("[db] bootstrap import skipped:", String(error?.code || error?.message || error));
      }
    })();
  }
  return databaseReadyPromise;
}

async function query(sql, params = []) {
  if (realPool) {
    try {
      await ensureDatabaseReady();
      return await realPool.query(sql, params);
    } catch (error) {
      if (!shouldFallbackToMock(error)) {
        throw error;
      }
      if (!warnedFallback) {
        warnedFallback = true;
        console.warn("[db] Falling back to mock database results:", String(error?.code || error?.message || error));
      }
    }
  }
  return mockPool.query(sql, params);
}

async function execute(sql, params = []) {
  return query(sql, params);
}

module.exports = {
  pool: {
    query,
    execute,
    getConnection: mockPool.getConnection,
    end: async () => {
      if (realPool) return realPool.end();
      return mockPool.end();
    },
  },
  isMockDb: !realPool,
};
