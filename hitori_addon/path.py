import ctypes
import re
from collections.abc import Iterable, Sequence
from ctypes import wintypes
from pathlib import Path

ILLEGAL_FILENAME_REGEX = re.compile(r'[<>:"/\\|?*\x00-\x1F]')
VALID_IDENTIFIER_REGEX = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# 名字比对用的切词: ascii 字母数字连写算一个词, 中日韩连写单独取一段
NAME_WORD_REGEX = re.compile(
    r"[0-9a-z]+|[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\uf900-\ufaff]+"
)
# 版本号 / 序号 (v2, 001) 不带语义
NAME_NUMBER_REGEX = re.compile(r"v?\d+$")
# 文件名与材质名里的填充词, 不参与比对
NAME_NOISE_TOKENS = frozenset(
    {
        "base",
        "tex",
        "texture",
        "map",
        "nomal",
        "mixed",
        "ao",
        "uv",
        "uvs",
        "copy",
        "final",
        "new",
        "old",
        "tmp",
        "temp",
        "psd",
        "png",
        "tga",
        "dds",
        "jpg",
        "jpeg",
        "webp",
        "bmp",
    }
)
# 同义词归一到贴图目录里更常见的说法
NAME_SYNONYMS = {
    "heel": "shoes",
    "heels": "shoes",
    "shoe": "shoes",
    "shoes": "shoes",
    "boot": "shoes",
    "boots": "shoes",
    "kemoshippo": "kemomimi",
    "mimimi": "kemomimi",
    "mimikaki": "kemomimi",
    "ear": "kemomimi",
    "ears": "kemomimi",
    "bra": "underwear",
    "panty": "underwear",
    "panties": "underwear",
    "lash": "eye",
    "lashes": "eye",
    "iris": "eye",
    "pupil": "eye",
    "sclera": "eye",
}


def aspath(file_path: str | Path) -> Path:
    if isinstance(file_path, Path):
        return file_path
    return Path(file_path)


def remove_suffix(string: str, suffix: str) -> str:
    if string.endswith(suffix):
        return string[: -len(suffix)]
    else:
        return string


def legalize_filename(filename: str, replacement: str = "_") -> str:
    return ILLEGAL_FILENAME_REGEX.sub(replacement, filename)


def is_valid_identifier(identifier: str) -> bool:
    return bool(VALID_IDENTIFIER_REGEX.match(identifier))


def get_file_dir_stem_ext(file_path: str | Path) -> tuple[Path, str, str]:
    file_path = aspath(file_path)
    return file_path.parent, file_path.stem, file_path.suffix


def get_file_stem(file_path: str | Path) -> str:
    return aspath(file_path).stem


def get_blend_file_stem() -> str:
    import bpy

    return Path(bpy.data.filepath).stem


def get_blend_file_dir() -> Path:
    import bpy

    return Path(bpy.data.filepath).parent


def get_last_import_dir() -> Path | None:
    """上次导入模型时用的目录 (blender 会记住上次导入操作的属性)"""
    import bpy

    window_manager = getattr(bpy.context, "window_manager", None)
    if window_manager is None:
        return None

    for operator_name in ("import_scene.fbx", "import_scene.gltf", "import_scene.obj"):
        properties = window_manager.operator_properties_last(operator_name)
        file_path = (getattr(properties, "filepath", "") or "").strip()
        if file_path and Path(file_path).parent.is_dir():
            return Path(file_path).parent
    return None


def get_image_dir() -> Path | None:
    """场景里能读到的贴图所在目录 (取贴图最多的那个, 常见情况就是模型资源包)"""
    import bpy

    folder_counts: dict[Path, int] = {}
    for image in bpy.data.images:
        if image.source != "FILE" or not image.filepath:
            continue
        folder = Path(bpy.path.abspath(image.filepath)).parent
        if folder.is_dir():
            folder_counts[folder] = folder_counts.get(folder, 0) + 1
    if not folder_counts:
        return None
    return max(folder_counts, key=lambda folder: folder_counts[folder])


def get_default_pick_dir() -> Path | None:
    """选择目录弹窗的起始目录: 上次导入的模型目录 > 能读到的贴图目录 > 当前 blend 目录"""
    import bpy

    folder = get_last_import_dir() or get_image_dir()
    if folder is not None:
        return folder
    return get_blend_file_dir() if bpy.data.filepath else None


def get_file_paths(
    folder_path: str | Path,
    exts: list[str] | None = None,
    recursive: bool = False,
) -> list[Path]:
    folder = aspath(folder_path)

    if exts:
        exts_set = {
            ext.lower() if ext.startswith(".") else "." + ext.lower() for ext in exts
        }
    else:
        exts_set = None

    file_paths = []
    files = folder.rglob("*") if recursive else folder.glob("*")
    for file in files:
        if file.is_file() and (exts_set is None or file.suffix.lower() in exts_set):
            file_paths.append(file)

    return file_paths


def name_tokens(name: str) -> frozenset[str]:
    """名字切成比较用的 token: 小写, 去版本号与填充词, 同义词归一, 中日韩按单字拆开"""
    tokens: set[str] = set()
    for word in NAME_WORD_REGEX.findall(name.lower()):
        if NAME_NUMBER_REGEX.match(word) or word in NAME_NOISE_TOKENS:
            continue
        tokens.add(NAME_SYNONYMS.get(word, word))
        # 中日韩没有词边界, 整段与单字都留一份 (`肌色` 与 `肌_色` 才能对上)
        if len(word) > 1 and not word.isascii():
            tokens.update(word)
    return frozenset(tokens)


def score_name_match(query: frozenset[str], candidate: frozenset[str]) -> float:
    """名字相似度 (0~1): 共同 token 的 F1 为主, 字符相似度小幅加权; 没有共同 token 记 0"""
    import difflib

    common = query & candidate
    if not common:
        return 0.0

    f1 = 2 * len(common) / (len(query) + len(candidate))
    ratio = difflib.SequenceMatcher(
        None, " ".join(sorted(query)), " ".join(sorted(candidate))
    ).ratio()
    return f1 * 0.75 + ratio * 0.25


def find_best_name_match(
    query_names: Iterable[str],
    candidate_names: Sequence[str],
    threshold: float = 0.0,
) -> tuple[str | None, float]:
    """按相似度在候选名里找最匹配的一个, 返回 (候选名, 分数)

    query_names 是同一个目标的多个线索 (越可靠越靠前), 取全场最高分, 平分时靠前的线索赢;
    最高分低于 threshold 时返回 None。
    """
    candidate_tokens = [(name, name_tokens(name)) for name in candidate_names]
    best_name = None
    best_score = 0.0

    for query_name in query_names:
        query = name_tokens(query_name)
        if not query:
            continue
        for name, tokens in candidate_tokens:
            score = score_name_match(query, tokens)
            if score > best_score:
                best_name, best_score = name, score

    if best_score < threshold:
        return None, best_score
    return best_name, best_score


class SHFileOpStruct(ctypes.Structure):
    """windows文件操作的结构体"""

    # windows删除文件
    FO_DELETE = 0x0003
    # windows允许撤销
    FOF_ALLOWUNDO = 0x0040
    # windows不弹出确认对话框
    FOF_NOCONFIRMATION = 0x0010

    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("wFunc", wintypes.UINT),
        ("pFrom", wintypes.LPCWSTR),
        ("pTo", wintypes.LPCWSTR),
        ("fFlags", wintypes.WORD),
        ("fAnyOperationsAborted", wintypes.BOOL),
        ("hNameMappings", wintypes.LPVOID),
        ("lpszProgressTitle", wintypes.LPCWSTR),
    ]


def send_to_trash(path: str | Path, check: bool = True) -> bool:
    path = aspath(path)
    if check and not path.exists():
        return False

    # 确保路径以双 null 结尾
    path_str = f"{path}\0\0"

    # 创建 SHFileOpStruct 结构体
    file_op = SHFileOpStruct()
    file_op.hwnd = None
    file_op.wFunc = SHFileOpStruct.FO_DELETE
    file_op.pFrom = path_str
    file_op.pTo = None
    file_op.fFlags = SHFileOpStruct.FOF_ALLOWUNDO | SHFileOpStruct.FOF_NOCONFIRMATION
    file_op.fAnyOperationsAborted = False
    file_op.hNameMappings = None
    file_op.lpszProgressTitle = None

    # 调用 SHFileOperation 函数，结果为 0 则表示操作成功
    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(file_op))
    return result == 0
