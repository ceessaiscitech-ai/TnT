@echo off
REM Opens Jupyter Lab on the four-model project (RWD_4Models_v20.58); its notebooks read D:\LKT\RWD_Artal\data and write to D:\LKT\RWD_Artal\data\output_4Models
set "ANACONDA=C:\ProgramData\anaconda3"
if not exist "%ANACONDA%\Scripts\activate.bat" set "ANACONDA=%USERPROFILE%\anaconda3"
call "%ANACONDA%\Scripts\activate.bat" base
cd /d "%~dp0"
jupyter lab --notebook-dir="%~dp0"
pause
