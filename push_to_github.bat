@echo off
cd /d "%~dp0"
title Push to GitHub (Bst-dc/hanwoo-smart-consulting)

echo ======================================================
echo   Pushing to GitHub: Bst-dc/hanwoo-smart-consulting
echo ======================================================
echo.

git push -u origin main

echo.
if %ERRORLEVEL% EQU 0 (
    echo ======================================================
    echo   SUCCESS! Pushed to GitHub successfully!
    echo   Now deploy at: https://share.streamlit.io
    echo ======================================================
) else (
    echo ======================================================
    echo   ERROR: Push failed.
    echo ======================================================
)

echo.
pause
