"""把 external_resources/ 打包成一个 zip, 交给用户自己解压到项目根目录.

外部资源是游戏模型 / 贴图 / 小型数据表衍生的模板与数据, 版权受限, 不随仓库分发 (见 .gitignore),
所以单独打包; 压缩包里带一份中英日说明 README.txt, 说明文件的唯一出处就是本脚本.

压缩包结构 (在项目根目录"解压到当前文件夹"即可就位):
    README.txt
    external_resources/{card,data,kk_blend,u3d}/...

用法:
    python scripts/pack_external_resources.py            # 输出到 output/release
    python scripts/pack_external_resources.py D:/桌面     # 再指定输出目录

版本号固定取 pyproject.toml 的 version (单一口径, 不单独维护): 资源内容变了就升级项目版本号。
"""

import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(__file__).absolute().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

# 清单与路径都以插件侧为准, 避免打包和运行时检查对不上
from hitori_addon.const import (
    EXTERNAL_RESOURCES_DIR,
    EXTERNAL_RESOURCES_FILE_LIST,
    RELEASE_DIR,
)

# 压缩包名, 版本号取 pyproject.toml
ARCHIVE_NAME_FORMAT = "hitori-tools_external_resources_v{version}.zip"

# 说明文件放在压缩包根目录, 带 BOM 的 UTF-8 + CRLF, 记事本打开不乱码
README_BASENAME = "README.txt"
UTF8_BOM = b"\xef\xbb\xbf"

VERSION_PATTERN = re.compile(r'^version\s*=\s*"([^"]+)"', re.MULTILINE)

# 中英日三语说明 (标题用英文), {version} 与 {date} 会被替换
README_TEMPLATE = """hitori-tools external resources v{version}   ({date})
====================================================

这里装的是游戏模型 / 贴图 / 小型数据表衍生的资源, 版权受限, 不随本工具一起分发.
缺了它, setup.bat 会中止安装, 插件用到相关功能时也会弹窗提示.

怎么用
------
1. 把 external_resources 文件夹解压到工具根目录, 也就是放着 setup.bat 的那个文件夹:
       <工具根目录>
         |- setup.bat
         \\- external_resources
              |- card        人物卡模板
              |- data        游戏数据小表 (脖颈坐标 / 形态键名 / 校色曲线)
              |- kk_blend    官模模板 official_template (含手工烘焙基准 kk_arm / kk_leg)
              \\- u3d         游戏导出的 .unity3d 模板
2. 重新运行 setup.bat
3. 放好之后, 本说明文件可以删掉


This pack contains templates and small data tables derived from the game
(models, textures, names and coordinates).
They are subject to the game's copyright and are NOT distributed with the tool.
Without them the installer stops, and the add-on shows a popup when needed.

How to use
----------
1. Extract the external_resources folder into the tool's root directory,
   i.e. the folder that contains setup.bat.
2. Run setup.bat again.
3. You can delete this file after that.


このパックにはゲームのモデル・テクスチャ・小型データ表から派生したテンプレートが入っています.
著作権の都合でツール本体には同梱していません.
無い場合, インストーラーは中断し, アドオンは必要時に警告を表示します.

使い方
------
1. external_resources フォルダをツールのルート (setup.bat と同じ場所) に解凍してください.
2. setup.bat をもう一度実行してください.
3. 配置したら, このファイルは削除してかまいません.
"""


def get_version() -> str:
    """版本号只认 pyproject.toml, 与项目版本保持一致"""
    match = VERSION_PATTERN.search(
        (PROJECT_DIR / "pyproject.toml").read_text(encoding="utf-8")
    )
    if not match:
        raise SystemExit("读不到 pyproject.toml 里的 version")
    return match.group(1)


def check_resources() -> None:
    missing = [
        name
        for name in EXTERNAL_RESOURCES_FILE_LIST
        if not (EXTERNAL_RESOURCES_DIR / name).is_file()
    ]
    if missing:
        print(f"外部资源不完整, 不打包: {EXTERNAL_RESOURCES_DIR}")
        for name in missing:
            print(f"    缺少 {name}")
        raise SystemExit(1)

    packed = {Path(name).parts[0] for name in EXTERNAL_RESOURCES_FILE_LIST}
    extra = sorted(
        str(path.relative_to(EXTERNAL_RESOURCES_DIR)).replace("\\", "/")
        for path in EXTERNAL_RESOURCES_DIR.rglob("*")
        if path.is_file()
        and str(path.relative_to(EXTERNAL_RESOURCES_DIR)).replace("\\", "/")
        not in EXTERNAL_RESOURCES_FILE_LIST
    )
    if extra:
        # 清单之外的文件不会进包, 列出来免得以为是漏了
        print(f"注意: 以下 {len(extra)} 个文件不在清单里, 不会打包:")
        for name in extra:
            print(f"    {name}")
        print(
            f"(清单见 hitori_addon/const.py 的 EXTERNAL_RESOURCES_FILE_LIST, 目录: {sorted(packed)})"
        )
        print()


def create_readme_bytes(version: str) -> bytes:
    text = README_TEMPLATE.format(
        version=version, date=datetime.now().strftime("%Y-%m-%d")
    )
    return UTF8_BOM + text.replace("\n", "\r\n").encode("utf-8")


def pack(archive_path: Path, version: str) -> None:
    dir_name = EXTERNAL_RESOURCES_DIR.name
    with zipfile.ZipFile(
        archive_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9
    ) as zip_file:
        zip_file.writestr(README_BASENAME, create_readme_bytes(version))
        for name in EXTERNAL_RESOURCES_FILE_LIST:
            zip_file.write(EXTERNAL_RESOURCES_DIR / name, f"{dir_name}/{name}")


def verify(archive_path: Path) -> None:
    """回读校验: 每个资源条目解开后与源文件逐字节一致"""
    dir_name = EXTERNAL_RESOURCES_DIR.name
    with zipfile.ZipFile(archive_path) as zip_file:
        bad = zip_file.testzip()
        if bad:
            raise SystemExit(f"压缩包损坏: {bad}")

        for name in EXTERNAL_RESOURCES_FILE_LIST:
            if (
                zip_file.read(f"{dir_name}/{name}")
                != (EXTERNAL_RESOURCES_DIR / name).read_bytes()
            ):
                raise SystemExit(f"压缩包里 {name} 与源文件不一致")
        if not zip_file.read(README_BASENAME).startswith(UTF8_BOM):
            raise SystemExit("说明文件缺少 BOM")


def main(argv: list[str]) -> None:
    version = get_version()
    out_dir = Path(argv[0]) if argv else RELEASE_DIR
    archive_path = out_dir / ARCHIVE_NAME_FORMAT.format(version=version)

    print(f"外部资源: {EXTERNAL_RESOURCES_DIR}")
    check_resources()

    out_dir.mkdir(parents=True, exist_ok=True)
    pack(archive_path, version)
    verify(archive_path)

    total = sum(
        (EXTERNAL_RESOURCES_DIR / name).stat().st_size
        for name in EXTERNAL_RESOURCES_FILE_LIST
    )
    print(f"已生成: {archive_path}")
    print(f"版本 {version}, {len(EXTERNAL_RESOURCES_FILE_LIST)} 个资源 + 1 个说明文件")
    print(
        f"{total / 1024 / 1024:.1f}MB -> {archive_path.stat().st_size / 1024 / 1024:.2f}MB (zip deflate)"
    )
    print("校验通过: 每个条目解开后与源文件逐字节一致, 说明文件是 UTF-8(BOM) + CRLF")


if __name__ == "__main__":
    # 走 blender -P 调用时取 `--` 之后的参数
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else sys.argv[1:]
    main(args)
