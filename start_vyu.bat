@echo off
echo Starting VYU 24/7 OSINT Backend & Analyst Interface...

start "VYU Backend API" cmd /k "cd /d D:\java\vyu && python -m uvicorn api.main:app --host 0.0.0.0 --port 8000"
start "VYU Analyst Interface" cmd /k "cd /d D:\java\vyu && python -m http.server 8080 --directory frontend"

timeout /t 3 /nobreak >nul
start http://localhost:8080

echo VYU OSINT System is now running!
echo Frontend UI: http://localhost:8080
echo Backend API: http://localhost:8000/docs
