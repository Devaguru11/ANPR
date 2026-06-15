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

function shouldFallbackToMock(error) {
  const code = String(error?.code || "");
  return ["ER_NO_SUCH_TABLE", "ER_BAD_DB_ERROR", "ECONNREFUSED", "PROTOCOL_CONNECTION_LOST", "ER_ACCESS_DENIED_ERROR", "ENOTFOUND"].includes(code);
}

async function query(sql, params = []) {
  if (realPool) {
    try {
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
