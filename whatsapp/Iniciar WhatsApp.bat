@echo off
title Hub - Ponte WhatsApp
cd /d "%~dp0"
echo.
echo   Iniciando a ponte do WhatsApp...
echo   Na primeira vez, escaneie o QR que aparecer aqui com o seu WhatsApp.
echo   (WhatsApp ^> Aparelhos conectados ^> Conectar aparelho)
echo.
echo   IMPORTANTE: o Hub (Iniciar Hub.bat) precisa estar rodando.
echo.
node bot.js
echo.
echo   A ponte foi encerrada. Pressione qualquer tecla para fechar.
pause >nul
