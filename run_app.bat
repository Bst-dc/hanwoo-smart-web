@echo off
chcp 65001 > nul
title 한우 스마트 컨설팅 통합 웹 플랫폼 (외부 접속 지원)

echo ======================================================================
echo   한우 스마트 컨설팅 통합 웹 플랫폼 실행기 (외부 인터넷 접속 지원)
echo ======================================================================
echo.

:: 1. 로컬 IP 주소 추출
set LOCAL_IP=127.0.0.1
for /f "tokens=4" %%a in ('route print ^| findstr 0.0.0.0.*0.0.0.0 ^| findstr /v "255.255.255.255"') do (
    set LOCAL_IP=%%a
)

echo [1] 로컬 PC 접속 주소:
echo     👉 http://localhost:8080
echo.
echo [2] 같은 와이파이(Wi-Fi) 기기 접속 주소:
echo     👉 http://%LOCAL_IP%:8080
echo.

:: 2. 백엔드 웹 서버 백그라운드 시작
start "한우컨설팅_웹서버" /min python "%~dp0src\backend\app.py" 8080

:: 3. PC 기본 브라우저 오픈
start "" "http://localhost:8080"

:: 4. Cloudflare 보안 터널 시작 (외부 모바일/LTE/5G 접속용)
echo ======================================================================
echo [3] 외부 인터넷 접속용 보안 HTTPS 주소를 생성 중입니다...
echo     (외부 어디서든 스마트폰 LTE/5G, 태블릿으로 접속 가능)
echo     아래에 나타나는 "https://xxxx.trycloudflare.com" 주소로 접속하세요!
echo     (종료하려면 이 창을 닫으시면 됩니다)
echo ======================================================================
echo.

if exist "%~dp0cloudflared.exe" (
    "%~dp0cloudflared.exe" tunnel --url http://localhost:8080
) else (
    echo [안내] cloudflared.exe가 없어 로컬 모드로만 실행됩니다.
    pause
)
