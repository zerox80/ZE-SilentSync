# ZE-SilentSync Setup Guide (v2.0)

This guide explains how to set up ZE-SilentSync in a production environment.

## Prerequisites

1.  **Server:** Windows Server or Linux (Docker recommended).
2.  **Database:** SQLite (default) or PostgreSQL (supported by SQLModel).
3.  **Active Directory:** Service Account with read permissions.

---

## Option A: Docker Deployment (Recommended)

1.  **Build the Backend Image:**
    ```bash
    cd backend
    docker build -t ze-silentsync-backend .
    ```

2.  **Run the Container:**
    ```bash
    docker run -d -p 8000:8000 \
      -e SECRET_KEY="your-super-secret-key" \
      -e AD_SERVER="dc.example.com" \
      -e AD_USER="admin@example.com" \
      -e AD_PASSWORD="secure-password" \
      -e ALLOWED_ORIGINS="http://localhost:5173" \
      -v $(pwd)/uploads:/app/uploads \
      -v $(pwd)/database.db:/app/database.db \
      ze-silentsync-backend
    ```

---

## Option B: Manual Installation (Windows Server)

### 1. Backend Setup

1.  Install **Python 3.10+**.
2.  Navigate to `backend`:
    ```powershell
    cd backend
    python -m venv venv
    .\venv\Scripts\activate
    pip install -r requirements.txt
    ```
3.  Configure `.env`:
    ```ini
    SECRET_KEY=change-me-to-something-secure
    AD_SERVER=dc.example.com
    AD_USER=svc_ldap@example.com
    AD_PASSWORD=secure_password
    ALLOWED_ORIGINS=http://localhost:5173
    ```
4.  Run Server:
    ```powershell
    python -m uvicorn main:app --host 0.0.0.0 --port 8000
    ```

### 2. Frontend Setup

1.  Install **Node.js 18+**.
2.  Navigate to `frontend`:
    ```powershell
    cd frontend
    npm install
    npm run build
    ```
3.  Serve the `dist` folder using IIS or `serve`.

---

## Step 3: Agent Deployment

1.  **Compile Agent:**
    ```powershell
    cd agent
    cargo build --release
    ```
2.  **Configuration:**
    Create a `config.toml` in the same folder as the `.exe`:
    ```toml
    backend_url = "http://your-server-ip:8000/api/v1/agent"
    heartbeat_interval = 60
    auth_token = "agent-change-me-to-match-backend-secret" 
    # Note: Default token logic is "agent-" + first 8 chars of SECRET_KEY
    ```
3.  **Deploy:**
    Copy `ze-silentsync-agent.exe` and `config.toml` to client machines (e.g., via GPO Startup Script).

---

## Step 4: First Login

1.  Open the Web UI (e.g., `http://localhost:5173`).
2.  **Default Admin:**
    -   Username: `admin`
    -   Password: The value of your `SECRET_KEY`.
3.  **Important:** Create a real admin account immediately after logging in.

---

## Features & Usage

-   **Internal Repo:** Upload `.msi` files via the "Software" tab.
-   **Targeting:** Assign software to specific Machines or OUs.
-   **Scheduling:** Set start/end times for deployments.
-   **Audit Logs:** View admin actions in the "Audit" tab.
