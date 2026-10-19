@echo off
setlocal EnableDelayedExpansion

::切换bat所在目录为工作目录
cd /d "%~dp0"

::从插件配置读路径(cwd 已切到 scripts 目录)
for /f "usebackq delims=" %%a in (`powershell -NoProfile -Command "(Get-Content -Raw -Encoding UTF8 '..\hitori_addon\hitori_addon_config.json' | ConvertFrom-Json).project" 2^>nul`) do set "project_dir=%%a"
for /f "usebackq delims=" %%a in (`powershell -NoProfile -Command "(Get-Content -Raw -Encoding UTF8 '..\hitori_addon\hitori_addon_config.json' | ConvertFrom-Json).blender" 2^>nul`) do set "blender_dir=%%a"

::设置脚本所在路径
set pyscript="%project_dir%\scripts\to_kk_png.py"
set "file_paths="

::将拖入的多个文件的路径存储在一个变量中,以空格分隔,路径会自动加上双引号
for %%i in (%*) do (
    set "file_paths=!file_paths! %%i"
)

::调用Python脚本文件，并将文件路径作为参数传递给它
"%blender_dir%\blender.exe" -b -P %pyscript% -- %file_paths%

