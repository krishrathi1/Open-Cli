@echo off
echo [Installing Rathi CLI locally...]
cd cli
call npm install
call npm link
echo.
echo [Installation Complete!]
echo You can now run the tool from ANY folder by simply typing:
echo   rathi
echo.
pause
