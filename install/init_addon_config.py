import os
import shutil
import sys
from enum import Enum
from pathlib import Path

# 项目根目录(本脚本在 <项目>/install 下)
PROJECT_DIR = Path(__file__).absolute().parent.parent

# 示例路径里的用户名按当前电脑自动获取, 避免发布版写死作者路径
HOME_DIR = Path.home()
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

# 配置读写与插件共用一份实现
from hitori_addon.config import CONFIG_FILE_NAME, load_config, write_config

# 插件配置文件, 会随 hitori_addon/ 一起复制进 Blender
CONFIG_PATH = PROJECT_DIR / "hitori_addon" / CONFIG_FILE_NAME

# 推荐(测试过)的 SB3Utility 版本, 只用于提示; 用户也可用其他版本
RECOMMENDED_SB3U_VERSION = "22.4.1"


class HitoriParma(Enum):
    """
    以下所有路径都是文件夹, 运行后按提示逐个输入.
    直接回车可沿用上次设置的值, 没有上次的值时沿用在当前电脑上存在的示例路径.
    blender / project / resources 文件夹自动推断, 不需要输入.
    sb3u 文件夹本工具不随附, 需要手动输入, 会提示推荐版本.
    abdata / desktop / release / shapekey_screenshot 文件夹自动推断, 会在项目文件夹的 output 里自动创建.
    mods 文件夹自动推断, 会在KKS文件夹里自动创建. magick 自动从PATH里查找, 找不到时不询问.
    找到自己存放Blender的地方, 然后将文件拖拽到 .../Blender/3.6/python/bin/python.exe 松开即可运行插件初始化.
    枚举值为 (说明, 示例路径).
    """

    # 手动输入
    # KKS文件夹(移植工具包暂不支持KK,不过移植工具包有自动转化KKS卡成为KK卡的功能,因此不用担心)
    # 建议用 [BR] Better Repack R10 版本, 太新或太久的整合包可能插件不兼容
    kk = ("KKS文件夹", r"C:\Games\KoikatsuSunshine")

    # 自动推断
    # Blender软件文件夹
    blender = ("Blender软件文件夹", r"C:\Documents\Blender")

    # 自动推断
    # hitori-tools主文件夹
    project = ("hitori-tools主文件夹", str(HOME_DIR / "PycharmProjects" / "hitori-tools"))

    # 自动推断
    # hitori-tools资源文件夹
    resources = (
        "hitori-tools资源文件夹",
        str(HOME_DIR / "BlenderProject" / "resources"),
    )

    # 手动输入
    # SB3Utility文件夹(该软件用于编辑kk的mod文件,简称sb3u), 本工具不随附, 需要自己下载
    sb3u = (
        "SB3Utility文件夹(sb3u)",
        r"C:\Games\KoikatsuSunshine\[MODDING] Tools\SB3Utility v22.4.1",
    )

    # 自动推断
    # abdata文件夹(文件夹名字一定要叫abdata!)
    # 注意:必须填游戏文件夹外自己新建的abdata文件夹,不能填游戏文件夹里的那个abdata,文件夹名字也必须叫abdata,否则后续sb3u会报错
    # 该文件夹是sb3u的工作文件夹,用于放mod临时文件,里面的带.bak的备份文件可以随时删除(但是删了后就没法备份恢复)
    # 但.unity3d结尾的文件是mod文件,请在彻底完成一个角色项目的移植后再删除,不然插件找不到该角色项目的.unity3d文件会报错
    abdata = (
        "abdata文件夹(游戏文件夹外的abdata,文件夹名字必须是abdata)",
        str(HOME_DIR / "Desktop" / "abdata"),
    )

    # 自动推断
    # 插件生成和修改mod的文件夹(在KKS的mods的子文件夹下即可)
    mods = (
        "mod文件夹(在KKS的mods的子文件夹下即可)",
        r"C:\Games\KoikatsuSunshine\mods\MyMods\@MyMod",
    )

    # 自动推断
    # 桌面文件夹(用于放模型和贴图临时文件)
    # 也可以填桌面外的其他位置,模型和贴图临时文件也可随时删除,不过删除后下次运行插件更新mod可能会多花一些时间重新生成
    desktop = (
        "桌面文件夹(用于放模型和贴图临时文件)",
        str(HOME_DIR / "Desktop"),
    )

    # 自动推断
    # 发布用文件夹(用于存储发布用的KK卡,KKS卡,mod的文件夹,会自动打包成易于发布的压缩包格式)
    release = (
        "发布用文件夹",
        str(HOME_DIR / "Desktop" / "KK_Modding" / "配布" / "KK_Release"),
    )

    # 自动推断
    # 形态键截图文件夹(形态键即头模的表情,可随意填写合适路径,生成的截图也可随时删除)
    shapekey_screenshot = (
        "形态键截图文件夹",
        str(HOME_DIR / "Desktop" / "KK_Modding" / "形态键截图"),
    )

    # 自动推断
    # Magick文件夹(非必须,可留空跳过,magick主要是用于简单处理图像等操作)
    magick = ("Magick文件夹(非必须,可留空跳过)", r"C:\Documents\ImageMagick")

    @property
    def description(self) -> str:
        """参数说明"""
        return self.value[0]

    @property
    def example(self) -> str:
        """示例路径(用户名按当前电脑自动获取)"""
        return self.value[1]


# 允许留空跳过的项目
OPTIONAL_PARMA = (HitoriParma.magick,)

# 不随本工具安装, 装完后推荐用户自行获取的插件 (插件名, 推荐理由)
RECOMMENDED_PLUGINS = (
    ("KKS_MakerCameraPresets", "(☆捏脸必装) 相机预设, 精准回到正/侧视图"),
    ("KKS_ExpressionControl", "(头模用) 查看各类表情"),
    ("FreeHDefaults.KoikatuSunshine", "(开发用) 场景人物自动沿用上次的"),
    ("KKS_OrthographicCamera", "(☆捏脸必装) 正交视角, 叠加对比图可精准还原面部"),
    ("KKS_CharacterReplacer", "(☆必装) 自动设置捏人默认角色为当前开发中角色卡"),
    ("KKS_Boop", "(☆推荐) 鼠标可与动骨交互测试效果"),
)


def get_child_names(path: Path) -> set[str]:
    """文件夹里直接子项的名字(小写), 读不到时返回空集合"""
    try:
        return {child.name.lower() for child in path.iterdir()}
    except OSError:
        return set()


def is_kk_dir(path: Path) -> bool:
    """判断文件夹是否是恋活游戏根目录(游戏根目录里有abdata和UserData或*_Data文件夹)"""
    names = get_child_names(path)
    has_game_dir = "userdata" in names or any(name.endswith("_data") for name in names)
    return has_game_dir and "abdata" in names


def is_in_kk_dir(value_path: Path, kk_text: str = "") -> bool:
    """判断文件夹是否位于恋活游戏文件夹里"""
    kk_dir = Path(kk_text) if kk_text else None
    if kk_dir and kk_dir.is_dir():
        try:
            value_path.relative_to(kk_dir)
            return True
        except ValueError:
            pass
    return any(is_kk_dir(parent) for parent in value_path.parents)


def check_kk_dir(value_path: Path) -> str:
    """校验 KKS 游戏根目录, 通过时返回空字符串"""
    names = get_child_names(value_path)
    if "abdata" not in names:
        return (
            f"KKS 游戏根目录里应该有 abdata 文件夹, 但 {value_path} 里没有, "
            f"请填 KKS 游戏根目录而不是里面的子文件夹, 例如 {HitoriParma.kk.example}, 请重新输入。"
        )
    if "userdata" not in names and not any(name.endswith("_data") for name in names):
        print(
            f"提示: {value_path} 里没有 UserData 或 *_Data 文件夹, 如果不是 KKS 游戏根目录, 后续插件可能报错。"
        )
    return ""


def check_parma(parma: HitoriParma, value_path: Path, kk_text: str = "") -> str:
    """额外校验, 通过时返回空字符串, 不通过时返回提示信息"""
    if parma is HitoriParma.kk:
        return check_kk_dir(value_path)
    if parma is HitoriParma.sb3u:
        if not (value_path / "SB3UtilityScript.exe").is_file():
            return (
                f"{value_path} 里没有 SB3UtilityScript.exe, "
                f"请填 SB3Utility 的文件夹(例如 {parma.example}), 请重新输入。"
            )
        return ""
    if parma is not HitoriParma.abdata:
        return ""
    if value_path.name.lower() != "abdata":
        return f"abdata 的文件夹名字必须是 abdata(当前为 {value_path.name}), 否则后续 sb3u 会报错, 请重新输入。"
    if is_in_kk_dir(value_path, kk_text):
        return (
            f"abdata 不能填游戏文件夹里的那个 abdata(当前为 {value_path}), "
            f"请填游戏文件夹外其他位置自己新建的 abdata, 例如 {parma.example}, 请重新输入。"
        )
    if value_path.name != "abdata":
        print("提示: abdata 文件夹建议改成全小写名字, 否则后续 sb3u 可能报错。")
    return ""


def is_blender_version_dir(name: str) -> bool:
    """判断文件夹名是否是 Blender 的版本文件夹, 如 3.6"""
    name_part = name.split(".")
    return len(name_part) == 2 and all(part.isdigit() for part in name_part)


def get_blender_dir() -> Path | None:
    """
    从运行本脚本的 python 推断 Blender 软件文件夹.
    插件初始化脚本由 Blender 自带的 python 运行, 该 python 路径形如 .../Blender/3.6/python/bin/python.exe
    """
    exe_path = Path(sys.executable)
    # 优先找放着 blender.exe 的文件夹
    blender_dir = next(
        (path for path in exe_path.parents if (path / "blender.exe").is_file()), None
    )
    if blender_dir:
        return blender_dir
    # 找不到 blender.exe 时, 找 3.6 这类版本文件夹的上一层
    return next(
        (path.parent for path in exe_path.parents if is_blender_version_dir(path.name)),
        None,
    )


def get_project_dir() -> Path | None:
    """
    从本脚本位置推断项目主文件夹.
    本脚本放在 <项目>/install 下, 项目里应该有 hitori_addon 文件夹, 否则说明本脚本没放在项目里
    """
    project_dir = Path(__file__).absolute().parent.parent
    return project_dir if (project_dir / "hitori_addon").is_dir() else None


def get_output_dir(project_dir: Path | None, sub_name: str) -> Path | None:
    """在项目文件夹的 output 里自动创建插件输出文件夹"""
    if not project_dir:
        return None
    output_dir = project_dir / "output" / sub_name
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    return output_dir


def get_magick_dir() -> Path | None:
    """从PATH里查找 magick.exe, 找不到时返回None"""
    magick_exe = shutil.which("magick")
    return Path(magick_exe).parent if magick_exe else None


def get_mods_dir(kk_dir: Path | None) -> Path | None:
    """KKS只能读取游戏自己mods文件夹里的mod, 所以在游戏文件夹里自动创建"""
    if not kk_dir or not is_kk_dir(kk_dir):
        return None
    mods_dir = kk_dir / "mods" / "MyMods" / "@MyMod"
    try:
        mods_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    return mods_dir


def get_auto_value(parma: HitoriParma, parma_values: dict) -> str:
    """不需要询问的参数的自动值, 无法自动推断时返回空字符串"""
    project_dir = get_project_dir()
    resources_dir = (project_dir / "resources") if project_dir else None
    kk_dir = Path(parma_values["kk"]) if parma_values.get("kk") else None
    auto_dir_map = {
        # 自动推断: 运行本脚本的 Blender
        HitoriParma.blender: get_blender_dir(),
        # 自动推断: 本脚本所在的 <项目>/install 的上两层
        HitoriParma.project: project_dir,
        # 自动推断: 项目文件夹里的 resources
        HitoriParma.resources: resources_dir,
        # 自动推断: 项目文件夹的 output 里自动创建
        HitoriParma.abdata: get_output_dir(project_dir, "abdata"),
        HitoriParma.desktop: get_output_dir(project_dir, "desktop"),
        HitoriParma.release: get_output_dir(project_dir, "release"),
        HitoriParma.shapekey_screenshot: get_output_dir(
            project_dir, "shapekey_screenshot"
        ),
        # 自动推断: 游戏文件夹里的 mods/MyMods/@MyMod
        HitoriParma.mods: get_mods_dir(kk_dir),
        # 自动推断: 从PATH里查找 magick
        HitoriParma.magick: get_magick_dir(),
    }
    if parma not in auto_dir_map:
        return ""
    auto_dir = auto_dir_map[parma]
    if auto_dir and auto_dir.is_dir():
        return str(auto_dir)
    if parma in OPTIONAL_PARMA:
        print("如果需要 magick 功能, 可以自己安装 ImageMagick 并添加到 PATH。")
        return ""
    print(f"未能自动推断 {parma.name} 文件夹, 改为手动输入。")
    return ""


def ask_parma(parma: HitoriParma, saved_values: dict, kk_text: str = "") -> str:
    """询问单个参数, 只做校验不产生副作用, 输入为空时返回空字符串"""
    saved = saved_values.get(parma.name, "")
    if parma is HitoriParma.kk:
        print(
            "提示: KKS 最好是 [BR] Better Repack R10 版本, 太新或太久的整合包可能插件不兼容。"
        )
    if parma is HitoriParma.sb3u:
        print(
            f"提示: SB3Utility 推荐 v{RECOMMENDED_SB3U_VERSION} (本工具在该版本测试, 其他版本可能不兼容), 需要自己下载。"
        )
    # 回车默认值: 优先上次设置的值, 其次当前电脑上存在的示例路径
    default = next(
        (value for value in (saved, parma.example) if value and Path(value).is_dir()),
        "",
    )
    if default:
        enter_tip = "直接回车使用当前值" if default == saved else "直接回车使用示例"
    else:
        enter_tip = "直接回车跳过" if parma in OPTIONAL_PARMA else "必须输入(回车无效)"
    saved_tip = f"当前值: {saved}, " if saved else ""
    while True:
        try:
            text = input(
                f"请输入 {parma.description} ({parma.name}) [{saved_tip}示例: {parma.example}, {enter_tip}]: "
            )
        except (EOFError, KeyboardInterrupt):
            print("\n未获取到输入, 已取消配置初始化, 配置文件未被修改。")
            os.system("pause")
            raise SystemExit(1)
        # 拖拽到终端粘贴的路径可能带引号或空格
        value = text.strip().strip('"').strip("'").strip() or default
        if not value:
            if parma in OPTIONAL_PARMA:
                print(f"{parma.name} 未填写, 跳过。")
                return ""
            print("路径不能为空, 请重新输入。")
            continue
        value_path = Path(value)
        if not value_path.is_dir():
            print(f"文件夹不存在或不是文件夹: {value}, 请重新输入。")
            continue
        error_str = check_parma(parma, value_path, kk_text)
        if error_str:
            print(error_str)
            continue
        return value


# 游戏衍生的外部资源不随仓库分发(见 .gitignore), 缺失时插件要到运行时才报错, 所以安装前先挡住
# 清单与 hitori_addon/const.py 的 EXTERNAL_RESOURCES_FILE_LIST 保持一致
EXTERNAL_RESOURCES_DIR_NAME = "external_resources"
EXTERNAL_RESOURCES_FILE_LIST = (
    "card/chara_name.png",
    "data/kk_game_data.json",
    "kk_blend/official_template.blend",
    "u3d/chara_name.unity3d",
    "u3d/chara_name-head.unity3d",
)


def check_external_resources(project_dir: Path) -> bool:
    """检查外部资源是否齐全; 缺了就打印获取方法并返回 False."""
    resources_dir = project_dir / EXTERNAL_RESOURCES_DIR_NAME
    missing = [
        name
        for name in EXTERNAL_RESOURCES_FILE_LIST
        if not (resources_dir / name).is_file()
    ]
    if not missing:
        print(f"外部资源检查通过: {resources_dir}")
        return True

    print()
    print("=" * 70)
    print(f"缺少外部资源, 已中止安装: {resources_dir}")
    print("游戏模型与贴图衍生的模板不随本工具分发, 需要先自己下载解压:")
    for name in missing:
        print(f"    缺少 {name}")
    print()
    print("请先从下载本工具的地方获取外部资源包 (约 9MB, 压缩包里有中英日说明),")
    print(
        f"解压后把 {EXTERNAL_RESOURCES_DIR_NAME} 文件夹放到这里 (和 setup.bat 同一个文件夹):"
    )
    print(f"    {project_dir}")
    print("放好后重新运行 setup.bat.")
    print("=" * 70)
    print()
    return False


def merge_preserved_values(
    parma_values: dict[str, str], saved_values: dict[str, str]
) -> dict[str, str]:
    """本脚本不认识的配置项(手写的开发开关, 如 hotreload)原样保留, 重跑安装不会清掉"""
    parma_names = {parma.name for parma in HitoriParma}
    preserved_values = {
        name: value
        for name, value in saved_values.items()
        if name not in parma_names
    }
    return {**preserved_values, **parma_values}


def main():
    print("开始设置插件参数 (直接回车沿用上次的值或示例路径):")
    # 先收集全部输入, 确认无误解后再写配置文件
    saved_values = load_config(CONFIG_PATH)
    parma_values = {}
    for parma in HitoriParma:
        auto_value = get_auto_value(parma, parma_values)
        if auto_value:
            print(f"{parma.name} 已自动设置: {auto_value}")
            parma_values[parma.name] = auto_value
            continue
        # 可选的 magick 自动推断失败时不询问用户(重写配置文件时旧值自然被丢掉)
        if parma in OPTIONAL_PARMA:
            continue
        parma_value = ask_parma(parma, saved_values, parma_values.get("kk", ""))
        if parma_value:
            parma_values[parma.name] = parma_value

    # 写在复制之前, 这样配置会随 hitori_addon/ 一起复制进 Blender
    write_config(merge_preserved_values(parma_values, saved_values), CONFIG_PATH)
    print(f"已写入插件配置: {CONFIG_PATH}")

    blender_dir = Path(parma_values["blender"])
    project_dir = Path(parma_values["project"])
    resources_dir = Path(parma_values["resources"])
    kk_dir = Path(parma_values["kk"])
    install_resources_dir = project_dir / "install_resources"

    if not check_external_resources(project_dir):
        os.system("pause")
        raise SystemExit(1)

    print("开始复制覆盖安装新插件:")
    # 资源里带有旧版 hitori_addon_ui, 所以要放在前面, 让项目里的代码最后覆盖进去
    copy_dir_map = {
        install_resources_dir / "Blender": blender_dir,
        install_resources_dir / "KoikatsuSunshine": kk_dir,
        project_dir / "hitori_addon": blender_dir
        / "3.6/scripts/addons_contrib/hitori_addon",
        project_dir / "hitori_addon_ui": blender_dir
        / "3.6/scripts/addons_contrib/hitori_addon_ui",
    }
    for src_dir, dst_dir in copy_dir_map.items():
        print(f"复制覆盖 {src_dir} 至 {dst_dir}:")
        if src_dir.is_symlink():
            print(f"{src_dir} 是一个软链接,跳过复制覆盖避免可能出现循环引用")
        for src_path in src_dir.rglob("*"):
            if src_path.is_dir():
                continue
            dst_path = dst_dir / src_path.relative_to(src_dir)
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            if (
                src_path.exists()
                and dst_path.exists()
                and os.path.samefile(src_path, dst_path)
            ):
                print(f"{src_path}与 {dst_path} 是同一个文件,跳过复制覆盖")
            else:
                shutil.copy2(src_path, dst_path)
                # print(f'已复制覆盖 {src_path} 至 {dst_path}')

    print("插件已完成配置初始化。")
    print(f"请保留本文件夹, 不要删除和移动: {project_dir}")
    print("否则插件会因为找不到资源而报错, 需要重新运行本安装脚本。")
    print(
        f"也不要删除 {EXTERNAL_RESOURCES_DIR_NAME} 文件夹 (游戏衍生的模板资源, 缺了插件会在用到时弹窗)."
    )
    print("可以自行修改 mod 模板, 修改后新建的 mod 都会使用新模板:")
    print(f"    作者名称, 网站等: {resources_dir / 'template/zipmod/manifest.xml'}")
    print(f"    mod 缩略图: {resources_dir / 'template/zipmod/img/thumb.png'}")
    print("        缩略图不随本工具分发, 请自行放一张 256x256 的 png 到这个路径 (目录不存在就自己新建);")
    print("        不放的话, 新建 mod 时会自动生成一张带角色 ID 的透明底图.")
    print()
    print(
        "以下插件不随本工具安装, 需要的话自行获取 (下载后放进游戏 BepInEx 文件夹的 plugins 里即可):"
    )
    for plugin_name, reason in RECOMMENDED_PLUGINS:
        print(f"    {plugin_name}: {reason}")
    os.system("pause")


if __name__ == "__main__":
    main()
