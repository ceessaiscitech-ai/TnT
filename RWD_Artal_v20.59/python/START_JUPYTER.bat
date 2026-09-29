@echo off
REM Opens Jupyter Lab on this project (RWD_Artal v20.50); its notebooks read D:\LKT\RWD_Artal\data
set "ANACONDA=C:\ProgramData\anaconda3"
if not exist "%ANACONDA%\Scripts\activate.bat" set "ANACONDA=%USERPROFILE%\anaconda3"
call "%ANACONDA%\Scripts\activate.bat" base
cd /d "%~dp0"
jupyter lab --notebook-dir="%~dp0"
pause
