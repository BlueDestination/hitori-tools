@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

:: 从插件配置读路径(cwd 已切到 scripts 目录)
for /f "usebackq delims=" %%a in (`powershell -NoProfile -Command "(Get-Content -Raw -Encoding UTF8 '..\hitori_addon\hitori_addon_config.json' | ConvertFrom-Json).desktop" 2^>nul`) do set "desktop_dir=%%a"
for /f "usebackq delims=" %%a in (`powershell -NoProfile -Command "(Get-Content -Raw -Encoding UTF8 '..\hitori_addon\hitori_addon_config.json' | ConvertFrom-Json).magick" 2^>nul`) do set "magick_dir=%%a"

:: 循环处理每一个传入的图片路径
for %%f in (%*) do (
    :: 获取文件名(不含扩展名),然后转换格式
    set "filename=%%~nf"
    "%magick_dir%\magick.exe" "%%~f" -quality 90 "%desktop_dir%\!filename!.jpg"
)
