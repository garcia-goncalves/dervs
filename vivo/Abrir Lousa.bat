@echo off
title Lousa
cd /d "%~dp0"

rem deps na primeira vez (node-pty, ws, xterm)
if not exist "node_modules\ws" call npm install

rem o Hub ja esta de pe na 4321?
powershell -NoProfile -Command "try{$c=New-Object Net.Sockets.TcpClient;$c.Connect('127.0.0.1',4321);$c.Close();exit 0}catch{exit 1}"
if errorlevel 1 goto subir

rem ja rodando: so abre a Lousa no navegador
start "" "http://127.0.0.1:4321/canvas.html"
exit

:subir
rem sobe o Hub ja abrindo DIRETO na Lousa (janela do servidor minimizada)
set HUB_OPEN_URL=http://127.0.0.1:4321/canvas.html
start "Hub de Projetos" /min cmd /k "node server.js"
exit
