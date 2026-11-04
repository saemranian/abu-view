@echo off
setlocal
cd /d "%~dp0"
if exist "%USERPROFILE%\miniconda3\envs\vggt\python.exe" (
    "%USERPROFILE%\miniconda3\envs\vggt\python.exe" abu_m54_app.py %*
) else (
    python abu_m54_app.py %*
)
