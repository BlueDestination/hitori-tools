"""构建 HitoriGui 插件并复制到安装资源目录"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
PROJ_DIR = REPO_DIR / "hitori_gui"
OUT_DLL = PROJ_DIR / "bin" / "Release" / "HitoriGui.dll"
TARGET_DIR = (
    REPO_DIR
    / "install_resources/KoikatsuSunshine/BepInEx/plugins"
    / "@MyPlugins/hitori_plugin/core"
)


def has_sdk(dotnet_exe: Path) -> bool:
    """只有运行时没有 SDK 时 `--list-sdks` 输出为空"""
    try:
        result = subprocess.run(
            [str(dotnet_exe), "--list-sdks"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return False
    return result.returncode == 0 and bool(result.stdout.strip())


def find_dotnet() -> Path:
    """PATH 里的 dotnet 常常只有运行时, 这里按优先级找带 SDK 的那个"""
    candidates = []
    if dotnet_root := os.environ.get("DOTNET_ROOT"):
        candidates.append(Path(dotnet_root) / "dotnet.exe")
    if which_dotnet := shutil.which("dotnet"):
        candidates.append(Path(which_dotnet))
    candidates.append(
        Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        / "dotnet"
        / "dotnet.exe"
    )
    candidates.append(Path.home() / ".dotnet" / "dotnet.exe")
    for scoop_dir in (os.environ.get("SCOOP"), r"C:\Scoop", str(Path.home() / "scoop")):
        if scoop_dir:
            candidates.append(
                Path(scoop_dir) / "apps" / "dotnet-sdk" / "current" / "dotnet.exe"
            )
    for candidate in candidates:
        if candidate.is_file() and has_sdk(candidate):
            return candidate
    raise RuntimeError("找不到带 SDK 的 dotnet, 请安装 dotnet SDK 或设置 DOTNET_ROOT")


def main():
    dotnet = find_dotnet()
    print(f"使用 dotnet: {dotnet}")
    result = subprocess.run(
        [str(dotnet), "build", str(PROJ_DIR / "HitoriGui.csproj"), "-c", "Release"],
        check=False,
        cwd=PROJ_DIR,
    )
    if result.returncode != 0:
        sys.exit(result.returncode)

    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    target = TARGET_DIR / OUT_DLL.name
    shutil.copy2(OUT_DLL, target)
    print(f"已复制: {target}")


if __name__ == "__main__":
    main()
