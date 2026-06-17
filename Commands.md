# Development Server Commands

Here are the exact commands to start and stop each part of the ANPR system individually. 

> **Tip:** You will need to open a separate terminal window/tab for each service you want to start.

---

### 1. Database & External Services
Before starting the backend or AI services, ensure your infrastructure is running.
- **MySQL Database**: Expected on `127.0.0.1:3307`
- **Redis Cache**: Expected on `127.0.0.1:6380`
- **VLLM Server**: Expected on `http://127.0.0.1:11434/v1`

*(These are typically started via Docker, e.g., `docker-compose up -d` depending on your setup)*

---

### 2. Backend Node API Server
Runs on port `4001`.
```bash
cd server
npm run dev
```

### 3. Frontend React Dashboard (Client)
Runs on port `5173`.
```bash
cd client
npm run dev
```

### 4. Enhanced Analytics Assistant Service
The new enhanced AI assistant runs on port `9103`.
```bash
cd assistant_enhance_service
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 9103
```

### 5. Standard AI Assistant Service (Legacy)
If you need the older standard assistant, it runs on port `9001`.
```bash
cd assistant_ai_service
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 9001
```

---

## How to Stop the Servers

Because these are development servers running in the foreground of your terminal, you simply need to kill the process in the terminal window where it is running:

1. Go to the terminal tab running the specific server.
2. Press `Ctrl + C` (Control + C) on your keyboard.
3. The server will shut down safely.

**To forcefully stop processes (if a port is stuck):**
If you try to start a server and get an "address already in use" error, you can find and kill the process manually:
```bash
# Find what is running on a port (e.g., 9103)
lsof -i :9103

# Kill the process using the PID found from the command above
kill -9 <PID>
```

---

## Default Credentials

### 1. App Login (React Dashboard)
To log in at `http://localhost:5173/enterprise/login`, use the following default demo credentials:
- **Email:** `admin@anpr.local`
- **Password:** `admin123`

### 2. MySQL Database (Docker)
If you need to connect directly to the local database, use the following details:
- **Host/Port:** `127.0.0.1:3307`
- **Database:** `aiserver`
- **Root User:** `root` / `anpr_root`
- **App User:** `aiserver` / `anpr_dev`
- **Analytics AI User:** `analytics_ai` / `anpr_dev`