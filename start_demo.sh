#!/bin/bash

echo "--- Setting up ZE-SilentSync Demo Environment ---"

# 1. Backend Setup
echo "[1/4] Setting up Backend..."
cd backend
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install -r requirements.txt > /dev/null 2>&1
echo "Backend dependencies installed."

# Start Backend in background
echo "[2/4] Starting Backend (Mock Mode)..."
# Ensure we don't have a .env file overriding the Mock setting, or ensure it is set to True
export USE_MOCK_LDAP=True
nohup python -m uvicorn main:app --host 0.0.0.0 --port 8000 > ../backend.log 2>&1 &
BACKEND_PID=$!
echo "Backend started with PID $BACKEND_PID (Log: backend.log)"

# 2. Frontend Setup
echo "[3/4] Setting up Frontend..."
cd ../frontend
npm install > /dev/null 2>&1
echo "Frontend dependencies installed."

# Start Frontend
echo "[4/4] Starting Frontend..."
echo "------------------------------------------------"
echo "The app will be available at: http://localhost:5173"
echo "Backend API is at: http://localhost:8000"
echo "------------------------------------------------"
echo "Press Ctrl+C to stop everything."

# Trap Ctrl+C to kill background processes
trap "kill $BACKEND_PID; exit" INT

npm run dev
