@echo off
setlocal

set "PROJECT_DIR=%~dp0"
set "APP_URL=http://127.0.0.1:5173/"
set "API_URL=http://127.0.0.1:8787/api/health"
set "COZE_API_TOKEN=pat_kL4JqoNjZHwQvPCeH0u6vpCXMVbA9QzRmnSiUn86OOmLh7C5Qk9txpx86CtuaLNo"
set "COZE_RECOMMEND_WORKFLOW_ID=7684482984275542051"
set "COZE_APP_ID=7684185393868439603"
set "COZE_BASE_URL=https://api.coze.cn"
set "COZE_RECOMMEND_MAX_RETRIES=3"
set "COZE_RECOMMEND_TIMEOUT=120"
set "AMAP_WEB_SERVICE_KEY=71e1f878bb08cc4d9703240b7348c216"
set "AMAP_FACILITY_SEARCH_KEY=876dc5a98b8aceef3ee960b3ef0c2116"
set "VITE_AMAP_JS_KEY=23569ba6254f98d4410aea61282c7a9c"
set "VITE_AMAP_SECURITY_CODE=7f931b8b2f27ca08ccfd8d079a41bccd"

cd /d "%PROJECT_DIR%"
if errorlevel 1 (
  echo Project folder not found:
  echo %PROJECT_DIR%
  pause
  exit /b 1
)

if not exist "package.json" (
  echo package.json not found. Please check the project files.
  pause
  exit /b 1
)

where npm.cmd >nul 2>nul
if errorlevel 1 (
  echo npm.cmd was not found. Please install Node.js first.
  pause
  exit /b 1
)

where python >nul 2>nul
if errorlevel 1 (
  echo python was not found. Please install Python 3 first.
  pause
  exit /b 1
)

if not exist "node_modules" (
  echo First run: installing dependencies...
  call npm.cmd install
  if errorlevel 1 (
    echo Dependency installation failed.
    pause
    exit /b 1
  )
)

echo Restarting local servers...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='SilentlyContinue'; foreach ($port in 8787,5173) { $conns=Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort $port -State Listen; foreach ($conn in $conns) { Stop-Process -Id $conn.OwningProcess -Force } }" >nul 2>nul

echo Starting Ninganju auth API...
start "Ninganju Auth API" cmd /k "python server\api_server.py"
ping 127.0.0.1 -n 3 >nul

echo Building static files...
call npm.cmd run build
if errorlevel 1 (
  echo Build failed.
  pause
  exit /b 1
)

echo Starting Ninganju preview server...
echo App URL: %APP_URL%
echo.
start "Ninganju Server" cmd /k "npm.cmd run preview -- --host 127.0.0.1 --port 5173 --strictPort"
ping 127.0.0.1 -n 4 >nul
start "" "%APP_URL%"
exit /b 0
