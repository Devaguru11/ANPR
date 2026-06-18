# Production Deployment Guide: ANPR Dashboard & AI Assistant

This guide outlines the step-by-step deployment procedure once you receive your server access credentials. 

The deployment maps to the directory structure `/home/aiserver/mern-vsp/` assumed by the system's pre-configured `systemd` service files.

---

## Phase 1: Server Access & Preparation
1. **SSH into the server:**
   ```bash
   ssh -i /path/to/key.pem username@server_ip
   ```
2. **Install Git, Node.js, Python 3.11, and Docker:**
   *On Ubuntu/Debian:*
   ```bash
   sudo apt update
   sudo apt install -y git python3-pip python3-venv docker.io docker-compose-v2 nginx
   # Install NVM and Node.js
   curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
   source ~/.bashrc
   nvm install 20
   ```
3. **Setup Repository Directory:**
   ```bash
   # Match the directory path in the systemd service file
   mkdir -p /home/aiserver/
   cd /home/aiserver/
   git clone <your-repository-url> mern-vsp
   cd mern-vsp
   ```

---

## Phase 2: Database & Cache Infrastructure (Docker)
1. **Start the MySQL & Redis containers:**
   ```bash
   docker compose up -d
   ```
   *Tip:* In production, make sure the `docker-compose.yml` has persistent volumes configured so that database records are not lost on container restarts.

---

## Phase 3: Deploy the Node.js API (Backend)
1. **Install PM2 Process Manager:**
   ```bash
   npm install -g pm2
   ```
2. **Setup environment variables:**
   ```bash
   cd /home/aiserver/mern-vsp/server
   cp .env.example .env
   nano .env
   ```
   *Make sure to change `DB_HOST` to `127.0.0.1`, set strong production passwords, configure SMTP credentials, and set `JWT_SECRET`.*
3. **Install dependencies and start the app with PM2:**
   ```bash
   npm install
   pm2 start src/index.js --name "anpr-backend"
   pm2 save
   pm2 startup
   ```

---

## Phase 4: Deploy the Python AI Assistant (`assistant_enhance_service`)
1. **Configure virtual environment & packages:**
   ```bash
   cd /home/aiserver/mern-vsp/assistant_enhance_service
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. **Setup environment variables:**
   ```bash
   cp .env.example .env
   nano .env
   ```
   *Set `DB_HOST=127.0.0.1`, `DB_PORT=3307`, and configure the `VLLM_BASE_URL` to point to either a local Ollama instance or your company's centralized LLM model API.*
3. **Deploy as a Systemd Service:**
   We will copy the service configuration to systemd. If the target service file points to a missing `scripts/start_service.sh`, we can edit it to start `uvicorn` directly.
   ```bash
   sudo cp systemd/assistant-enhance.service /etc/systemd/system/
   ```
   *If you need to edit it to call the virtual environment's uvicorn directly:*
   ```ini
   # /etc/systemd/system/assistant-enhance.service
   [Service]
   WorkingDirectory=/home/aiserver/mern-vsp/assistant_enhance_service
   ExecStart=/home/aiserver/mern-vsp/assistant_enhance_service/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 9103
   ```
4. **Enable and start the service:**
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable assistant-enhance
   sudo systemctl start assistant-enhance
   ```

---

## Phase 5: LLM Setup (Ollama or Central API)
* **Option A: Running Ollama locally on the server (Requires a GPU or high-spec CPU):**
  ```bash
  curl -fsSL https://ollama.com/install.sh | sh
  ollama pull llama3:latest
  ```
* **Option B: Connecting to an external/centralized corporate LLM API:**
  Simply edit `assistant_enhance_service/.env` and update `VLLM_BASE_URL` and `VLLM_MODEL` to point to the remote host.

---

## Phase 6: Build & Host the Frontend Client (React/Vite)
1. **Build Static Files:**
   ```bash
   cd /home/aiserver/mern-vsp/client
   npm install
   # Set the API endpoint URL for Vite
   echo "VITE_API_URL=http://<server-ip-or-domain>/api" > .env.production
   npm run build
   ```
   This compiles everything into a high-performance static folder in `/home/aiserver/mern-vsp/client/dist`.

2. **Configure Nginx Web Server:**
   Edit the Nginx default config:
   ```bash
   sudo nano /etc/nginx/sites-available/default
   ```
   Replace the configuration with the following reverse proxy template:
   ```nginx
   server {
       listen 80;
       server_name your-domain-or-ip;

       # Serve Frontend Static Assets
       location / {
           root /home/aiserver/mern-vsp/client/dist;
           index index.html;
           try_files $uri /index.html;
       }

       # Proxy requests to Node.js Backend API
       location /api {
           proxy_pass http://127.0.0.1:4000;
           proxy_http_version 1.1;
           proxy_set_header Upgrade $http_upgrade;
           proxy_set_header Connection 'upgrade';
           proxy_set_header Host $host;
           proxy_cache_bypass $http_upgrade;
       }

       # Proxy requests to Python AI Assistant
       location /assistant_enhance {
           proxy_pass http://127.0.0.1:9103;
           proxy_http_version 1.1;
           proxy_set_header Upgrade $http_upgrade;
           proxy_set_header Connection 'upgrade';
           proxy_set_header Host $host;
           proxy_cache_bypass $http_upgrade;
       }
   }
   ```
3. **Restart Nginx:**
   ```bash
   sudo nginx -t
   sudo systemctl restart nginx
   ```
