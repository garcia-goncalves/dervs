@echo off
title Hub - Notifier (avisos proativos)
cd /d "%~dp0"
echo.
echo   Iniciando o Notifier (avisos proativos pro Telegram)...
echo   (o Hub - Iniciar Hub.bat - precisa estar rodando)
echo.
node notifier.js
echo.
echo   O Notifier foi encerrado. Pressione qualquer tecla para fechar.
pause >nul
