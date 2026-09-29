@echo off
REM MIGRATE_DATA.bat (v20.50) -- move this project's data to its new folder. On the same drive this is a RENAME:
REM instant, nothing is copied, the output folder inside moves with it. Close Jupyter / RStudio / Explorer windows first.
REM     D:\LKT\TST_ArtalR   ->   D:\LKT\RWDR\data
set "OLD=D:\LKT\TST_ArtalR"
set "NEW=D:\LKT\RWDR\data"
if not exist "%OLD%\" ( echo Nothing to move: %OLD% does not exist. & goto :end )
if exist "%NEW%\" ( echo %NEW% already exists -- nothing moved. Move the files by hand if needed. & goto :end )
if not exist "D:\LKT\RWDR\" mkdir "D:\LKT\RWDR"
move "%OLD%" "%NEW%"
if errorlevel 1 ( echo The move failed -- close every program that uses %OLD% and run this again. & goto :end )
echo Moved: %OLD% -^> %NEW%
:end
pause
