@echo off
title Hub de Projetos
cd /d "%~dp0"
echo.
echo   Iniciando o Hub de Projetos...
echo   (deixe esta janela aberta enquanto usa o hub)
echo.
rem instala as dependencias (node-pty, ws, xterm) na primeira vez ou se sumirem
if not exist "node_modules\ws" (
  echo   Instalando dependencias ^(primeira vez^)...
  call npm install
  echo.
)
node server.js
echo.
echo   O Hub foi encerrado. Pressione qualquer tecla para fechar.
pause >nul
