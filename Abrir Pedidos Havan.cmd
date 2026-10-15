@echo off
setlocal
if exist "%~dp0Pedidos Havan.exe" (
    start "" /D "%~dp0." "%~dp0Pedidos Havan.exe"
    exit /b 0
)
if exist "%~dp0.venv\Scripts\pythonw.exe" (
    start "" /D "%~dp0." "%~dp0.venv\Scripts\pythonw.exe" "%~dp0havan.py"
    exit /b 0
)
if exist "%~dp0venv32\Scripts\pythonw.exe" (
    start "" /D "%~dp0." "%~dp0venv32\Scripts\pythonw.exe" "%~dp0havan.py"
    exit /b 0
)
echo O executavel Pedidos Havan.exe e o ambiente Python nao foram encontrados.
echo Solicite ao responsavel o executavel atualizado ou um ambiente Python de 32 bits.
echo Consulte o README na pasta deste programa.
pause
exit /b 1
