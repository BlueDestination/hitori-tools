@echo off
chcp 936 >nul 2>nul
setlocal
title hitori-tools 安装
cd /d "%~dp0"

set "INSTALL_PY=%~dp0install\init_addon_config.py"
set "CONFIG_PATH=hitori_addon\hitori_addon_config.json"

echo.
echo  ==============================================================
echo    hitori-tools 安装 (需要 Blender 3.6)
echo  ==============================================================
echo.
echo  本脚本会先让你输入 blender.exe 的完整路径并检查是否有效,
echo  再用该 Blender 自带的 python.exe 运行插件初始化脚本。
echo.
echo  要求: 必须是 Blender 3.6 版本, 其他版本不行.
echo        最好单独准备一份 Blender 3.6 专门用于本项目, 不要用平时在用的那份.
echo.
echo  注意: 安装会改变 Blender 的行为, 会往 Blender 安装目录里写入配置,
echo        脚本和插件, 并覆盖同名的旧文件, 请确认后再继续.
echo        安装前请先关闭正在运行的 Blender, 安装完成后再重新打开 Blender.
echo.
echo  小技巧: 可以直接把 blender.exe 拖拽到本窗口, 然后按回车;
echo          也可以直接把 blender.exe 拖拽到本 bat 文件上。
echo.

if not exist "%INSTALL_PY%" (
    echo  [错误] 找不到初始化脚本:
    echo         %INSTALL_PY%
    echo         请确认本 bat 文件放在 hitori-tools 项目根目录下。
    goto :end
)

rem 拖拽到本 bat 上运行时, blender.exe 会作为第一个参数传进来
set "BLENDER_EXE=%~1"
if defined BLENDER_EXE set "BLENDER_EXE=%BLENDER_EXE:"=%"

rem 上次用的 Blender 文件夹: 从插件配置文件读(初始化脚本写入)
set "SAVED_BLENDER="
if exist "%CONFIG_PATH%" for /f "usebackq delims=" %%a in (`powershell -NoProfile -Command "(Get-Content -Raw -Encoding UTF8 '%CONFIG_PATH%' | ConvertFrom-Json).blender" 2^>nul`) do set "SAVED_BLENDER=%%a"
set "SAVED_EXE="
if defined SAVED_BLENDER if exist "%SAVED_BLENDER%\blender.exe" set "SAVED_EXE=%SAVED_BLENDER%\blender.exe"
if defined SAVED_EXE (
    echo  上次用的 blender.exe: %SAVED_EXE%
    echo  直接回车即可使用它, 也可以输入新的完整路径。
    echo.
)
if defined SAVED_BLENDER if not defined SAVED_EXE (
    echo  上次的 Blender 文件夹里找不到 blender.exe: %SAVED_BLENDER%
    echo  请重新输入 blender.exe 的完整路径。
    echo.
)
set /a TRY_COUNT=0

:ask_exe
if defined BLENDER_EXE goto :check_exe
set /a TRY_COUNT+=1
if %TRY_COUNT% GTR 10 (
    echo  [错误] 已连续 10 次没有输入有效的 blender.exe 路径, 本次安装已取消。
    goto :end
)
set "BLENDER_TIP="
if defined SAVED_EXE set "BLENDER_TIP= [当前值: %SAVED_EXE%, 直接回车使用它]"
set "BLENDER_EXE="
set /p "BLENDER_EXE=请输入 Blender 3.6 版 blender.exe 的完整路径%BLENDER_TIP%: "
if not defined BLENDER_EXE set "BLENDER_EXE=%SAVED_EXE%"
if defined BLENDER_EXE set "BLENDER_EXE=%BLENDER_EXE:"=%"

:check_exe
if not defined BLENDER_EXE (
    echo  [错误] 路径不能为空, 请重新输入。
    goto :ask_exe
)
if not exist "%BLENDER_EXE%" (
    echo  [错误] 找不到该文件: %BLENDER_EXE%
    set "BLENDER_EXE="
    goto :ask_exe
)
for %%f in ("%BLENDER_EXE%") do (
    set "BLENDER_EXE=%%~f"
    set "BLENDER_NAME=%%~nxf"
    set "BLENDER_DIR=%%~dpf"
)
if /i not "%BLENDER_NAME%"=="blender.exe" (
    echo  [提示] 你输入的文件名不是 blender.exe, 而是 %BLENDER_NAME%
    echo         仍将按 Blender 安装目录继续。
)

set "PYTHON_EXE="
if exist "%BLENDER_DIR%3.6\python\bin\python.exe" set "PYTHON_EXE=%BLENDER_DIR%3.6\python\bin\python.exe"
if not defined PYTHON_EXE for /d %%d in ("%BLENDER_DIR%*") do if not defined PYTHON_EXE if exist "%%d\python\bin\python.exe" set "PYTHON_EXE=%%d\python\bin\python.exe"
if not defined PYTHON_EXE (
    echo  [错误] 在 Blender 安装目录里找不到自带的 python.exe
    echo         已查找: %BLENDER_DIR%3.6\python\bin\python.exe
    echo         请确认输入的是 Blender 3.6 软件目录下的 blender.exe
    set "BLENDER_EXE="
    goto :ask_exe
)

echo.
echo  已找到 Blender 自带的 python:
echo         %PYTHON_EXE%
echo  正在检查 python 是否可用...
"%PYTHON_EXE%" -c "import sys; print('python ok:', sys.version)"
if errorlevel 1 (
    echo  [错误] Blender 自带的 python 无法运行, 请检查 Blender 是否安装完整。
    set "BLENDER_EXE="
    goto :ask_exe
)

echo.
echo  开始运行插件初始化脚本, 请按提示依次输入各个文件夹路径:
echo         %INSTALL_PY%
echo.
"%PYTHON_EXE%" "%INSTALL_PY%"
set "EXIT_CODE=%errorlevel%"
echo.
if not "%EXIT_CODE%"=="0" (
    echo  [错误] 初始化脚本异常退出, 退出码: %EXIT_CODE%
    echo         常见原因是输入的路径不存在, 或文件被占用, 可重新运行本脚本再试一次。
) else (
    echo  插件初始化脚本已正常结束。
)

:end
echo.
echo  按任意键关闭本窗口...
pause >nul
endlocal
