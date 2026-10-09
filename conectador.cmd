@echo off
rem DERVS - conectar este computador.
rem
rem Este arquivo e o MOLDE. O painel o entrega com o programa em Python colado no
rem fim (depois da linha de marcador), com todas as linhas em CRLF. O molde:
rem   1. baixa o Python oficial (embutivel) UMA vez e confere o SHA-256;
rem   2. extrai o programa do proprio fim deste arquivo;
rem   3. roda o programa, que pede a pasta e abre o navegador para autorizar.
rem Nada aqui roda texto codificado nem baixa por outro caminho que o curl.
setlocal
title DERVS - conectar este computador
set "CASA=%LOCALAPPDATA%\DERVS"
set "PYDIR=%CASA%\python"
set "PY=%PYDIR%\python.exe"
set "ZIP=%CASA%\python-embed.zip"
set "URL=https://www.python.org/ftp/python/3.14.8/python-3.14.8-embed-amd64.zip"
set "SHA=a93abe456ab01bd96d7a085b3cdb6566b3063f4241360d114142fbdb07f0a310"
goto principal

:sem_download
if exist "%ZIP%" del "%ZIP%"
echo Nao consegui baixar o Python. Confira a internet e abra este arquivo de novo.
pause
exit /b 1

:sem_programa
echo Este arquivo esta incompleto. Baixe de novo pelo painel do DERVS.
pause
exit /b 1

:principal
if not exist "%CASA%" mkdir "%CASA%"
if exist "%PY%" goto extrair

echo Baixando o Python oficial (uma vez so, cerca de 12 MB)...
curl.exe -L --fail --silent --show-error -o "%ZIP%" "%URL%"
if errorlevel 1 goto sem_download

certutil -hashfile "%ZIP%" SHA256 | findstr /i /c:"%SHA%" >nul
if errorlevel 1 (
  del "%ZIP%"
  echo O arquivo baixado nao e o Python oficial esperado. Nada foi instalado.
  pause
  exit /b 1
)

if exist "%PYDIR%.novo" rmdir /s /q "%PYDIR%.novo"
mkdir "%PYDIR%.novo"
tar.exe -xf "%ZIP%" -C "%PYDIR%.novo"
if errorlevel 1 (
  del "%ZIP%"
  rmdir /s /q "%PYDIR%.novo"
  echo Nao consegui abrir o Python baixado. Nada foi instalado.
  pause
  exit /b 1
)
del "%ZIP%"
if exist "%PYDIR%" rmdir /s /q "%PYDIR%"
move "%PYDIR%.novo" "%PYDIR%" >nul
if not exist "%PY%" goto sem_download

:extrair
"%PY%" -I -c "import sys;d=open(sys.argv[1],'rb').read();d=d[d.index(b'\n#:DERVS-PYTHON')+1:];open(sys.argv[2],'wb').write(d[d.index(b'\n')+1:])" "%~f0" "%CASA%\conectador.py"
if errorlevel 1 goto sem_programa
"%PY%" -I "%CASA%\conectador.py"
exit /b %ERRORLEVEL%
