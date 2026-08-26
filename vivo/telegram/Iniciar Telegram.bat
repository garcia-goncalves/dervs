@echo off
title Hub - Ponte Telegram
cd /d "%~dp0"
echo.
echo   Iniciando a ponte do Telegram...
echo   (o Hub - Iniciar Hub.bat - precisa estar rodando)
echo.
node bot.js
echo.
echo   A ponte foi encerrada. Pressione qualquer tecla para fechar.
pause >nul
