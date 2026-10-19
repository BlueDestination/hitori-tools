"""网格命名: 按关键词把网格改成游戏里的合法名称

匹配顺序: 服装类(top / bot / bra / pants / glove / panty / sock / shoe)
-> 饰品(acc, 头发排最前, 超出 acc9 继续编号但加 `_` 前缀)
-> 身体类(body / body-head / body-eye …, 只为归类, 不参与导出)。
同一目标有多个网格时第一个用本名, 后面的加 `_2` / `_3` 等用户合并;
无法归类的网格加 `_` 前缀提示手动处理。
`.001` 只在基名是合法名时才算半脱网格(如 `cloth_top.001`, 需要用户自己做);
Blender 复制产生的 `名字.001` 照样命名。已经是合法名的网格不动。
"""

import re
from collections.abc import Iterable, Sequence

import bpy
from bpy.types import Object

from hitori_addon.const import ACC_TYPES
from hitori_addon.sb3u import MESH_ANIMATOR_MAP

# ==================== 配置区 ====================
# 只收基本不连在服装上的配件: 能贴合身体 / 很像服装(丝带, 蝴蝶结, 腰带, 围巾)的不收,
# 它们要自己传递权重。
# 头发类优先匹配, 匹配到即归入 acc 并排在最前
HAIR_KEYWORDS: tuple[str, ...] = (
    "hair",
    "hairs",
    "头发",
    "髮",
    "髪",
    "发",
    "前发",
    "后发",
    "ahoge",
    "アホ毛",
    "呆毛",
    "发尖",
    "髪先",
    "ponytail",
    "马尾",
    "ポニーテール",
    "braid",
    "braids",
    "plait",
    "plaits",
    "辫子",
    "お下げ",
    "おさげ",
    "三つ編み",
    "みつあみ",
    "twin tail",
    "twin tails",
    "twintail",
    "双马尾",
    "ツインテール",
    "bangs",
    "刘海",
    "前髪",
    "发饰",
    "hairpin",
    "hairband",
    "hairbands",
    "ヘアピン",
    "ヘアバンド",
    "ヘアクリップ",
    "sidelock",
    "sidelocks",
)

# 尾巴类
TAIL_KEYWORDS: tuple[str, ...] = (
    "tail",
    "tails",
    "テール",
    "尾巴",
    "尾",
    "しっぽ",
    "尻尾",
)

# 翅膀类
WING_KEYWORDS: tuple[str, ...] = (
    "wing",
    "wings",
    "ウイング",
    "翅膀",
    "翅",
    "翼",
    "つばさ",
    "羽",
)

# 其他不连在服装上的配件
OTHER_ACC_KEYWORDS: tuple[str, ...] = (
    # 角
    "horn",
    "horns",
    "角",
    "つの",
    "ツノ",
    # 兽耳 / 耳饰 / 面饰 (普通的耳朵归 body-ear, 在 acc 之后才匹配)
    "cat ear",
    "cat ears",
    "dog ear",
    "dog ears",
    "fox ear",
    "fox ears",
    "animal ear",
    "animal ears",
    "nekomimi",
    "kemomimi",
    "猫耳",
    "犬耳",
    "狐耳",
    "ケモミミ",
    "獣耳",
    "earring",
    "earrings",
    "piercing",
    "耳环",
    "耳饰",
    "イヤリング",
    "ピアス",
    # 腰饰 / 背饰
    "背饰",
    "腰饰",
    "腰飾り",
    "mask",
    "masks",
    "マスク",
    "口罩",
    "面具",
    "面罩",
    "镜框",
    "eyepatch",
    "eyepatches",
    "眼罩",
    "アイパッチ",
    "glasses",
    "眼鏡",
    "眼镜",
    "メガネ",
    "めがね",
    "monocle",
    "单片眼镜",
    "モノクル",
    # 头饰
    "hat",
    "hats",
    "帽子",
    "ハット",
    "cap",
    "caps",
    "帽",
    "helmet",
    "helmets",
    "头盔",
    "ヘルメット",
    "crown",
    "皇冠",
    "王冠",
    "クラウン",
    "tiara",
    "ティアラ",
    "halo",
    "光环",
    "天使环",
    "ヘイロー",
    "头饰",
    "headacc",
    # 颈 / 手饰品
    "necklace",
    "necklaces",
    "项链",
    "ネックレス",
    "首飾り",
    "choker",
    "chokers",
    "チョーカー",
    "pendant",
    "pendants",
    "ペンダント",
    "挂坠",
    "挂饰",
    "bracelet",
    "bracelets",
    "手链",
    "ブレスレット",
    # 背包 / 手持物品
    "bag",
    "bags",
    "バッグ",
    "背包",
    "backpack",
    "backpacks",
    "handbag",
    "handbags",
    "リュック",
    "鞄",
    "weapon",
    "weapons",
    "武器",
    "sword",
    "swords",
    "katana",
    "刀",
    "刀剣",
    "剣",
    "剑",
    "ナイフ",
    "弓",
    "盾",
    "shield",
    "shields",
    "umbrella",
    "umbrellas",
    "傘",
    "伞",
)

# 以下三类都归 acc, 未命中再试服装
# 按顺序匹配: 序号小(头发)优先占用前面的 acc 槽位
ACC_KEYWORD_GROUPS: tuple[tuple[str, ...], ...] = (
    HAIR_KEYWORDS,
    TAIL_KEYWORDS,
    WING_KEYWORDS,
    OTHER_ACC_KEYWORDS,
)

# 上衣
TOP_KEYWORDS: tuple[str, ...] = (
    # 英文
    "top",
    "tops",
    "shirt",
    "shirts",
    "tshirt",
    "tshirts",
    "blouse",
    "blouses",
    "jacket",
    "jackets",
    "coat",
    "coats",
    "overcoat",
    "overcoats",
    "sweater",
    "sweaters",
    "sweatshirt",
    "sweatshirts",
    "hoodie",
    "hoodies",
    "parka",
    "parkas",
    "vest",
    "vests",
    "cardigan",
    "cardigans",
    "tunic",
    "tunics",
    "camisole",
    "camisoles",
    "blazer",
    "blazers",
    "jersey",
    "jerseys",
    "apron",
    "aprons",
    "tanktop",
    "tanktops",
    "crop top",
    "tube top",
    "dress",
    "dresses",
    "onepiece",
    # 日文
    "トップス",
    "シャツ",
    "ブラウス",
    "ジャケット",
    "コート",
    "セーター",
    "パーカー",
    "ベスト",
    "カーディガン",
    "キャミソール",
    "インナー",
    "上着",
    "羽織",
    "トレーナー",
    "ポロシャツ",
    "ワンピース",
    # 中文
    "上衣",
    "衬衫",
    "衬衣",
    "T恤",
    "t恤",
    "恤",
    "夹克",
    "外套",
    "大衣",
    "毛衣",
    "卫衣",
    "背心",
    "开衫",
    "罩衫",
    "吊带",
    "围裙",
    "打底衫",
    "衣服",
    "连衣裙",
    "连身裙",
    # 材质名只有"服1" / "服2" / "衣袖" / "衣领" 这类编号或部件名, 只能先归上衣
    "clothes",
    "cloth",
    "服",
    "袖",
    "衣领",
    "领",
    "领带",
    "衣饰",
)

# 胸罩
BRA_KEYWORDS: tuple[str, ...] = (
    "bra",
    "bras",
    "brassiere",
    "brassieres",
    "bralette",
    "bralettes",
    "ブラ",
    "ブラジャー",
    "胸罩",
    "文胸",
    "乳罩",
    "胸衣",
)

# 内裤 (游戏里叫 pants, 不收日文"パンツ": 会被"ショートパンツ"抢)
PANTS_KEYWORDS: tuple[str, ...] = (
    "panty",
    "panties",
    "underwear",
    "underpants",
    "briefs",
    "knickers",
    "ショーツ",
    "下着",
    "内裤",
    "短裤头",
    "三角裤",
)

# 裤袜 / 丝袜 (游戏里叫 panty; 单独的英文 panty 归内裤, 裤袜用 pantyhose / stocking)
PANTY_KEYWORDS: tuple[str, ...] = (
    "stocking",
    "stockings",
    "tights",
    "pantyhose",
    "pantyhoses",
    "thighhigh",
    "thighhighs",
    "thigh high",
    "thigh highs",
    "ストッキング",
    "タイツ",
    "パンスト",
    "ニーハイ",
    "網タイツ",
    "丝袜",
    "裤袜",
    "长筒袜",
    "过膝袜",
    "连裤袜",
    "大腿袜",
    "网袜",
    "吊带袜",
    # 按颜色叫的丝袜 (黑丝 / 白丝 / 肉丝)
    "黑丝",
    "白丝",
    "肉丝",
    "黑絲",
    "白絲",
    "肉絲",
)

# 短袜
SOCK_KEYWORDS: tuple[str, ...] = (
    "sock",
    "socks",
    "ソックス",
    "靴下",
    "くつした",
    "袜",
    "袜子",
    "短袜",
)

# 鞋
SHOE_KEYWORDS: tuple[str, ...] = (
    "shoe",
    "shoes",
    "boot",
    "boots",
    "bootie",
    "booties",
    "sneaker",
    "sneakers",
    "sandal",
    "sandals",
    "heel",
    "heels",
    "high heel",
    "high heels",
    "highheel",
    "highheels",
    "stiletto",
    "stilettos",
    "pump",
    "pumps",
    "loafer",
    "loafers",
    "oxford",
    "oxfords",
    "slipper",
    "slippers",
    "flat",
    "flats",
    "wedge",
    "wedges",
    "mule",
    "mules",
    "clog",
    "clogs",
    "geta",
    "mary jane",
    "mary janes",
    "maryjane",
    # 日文
    "靴",
    "ブーツ",
    "スニーカー",
    "サンダル",
    "ヒール",
    "ハイヒール",
    "パンプス",
    "ローファー",
    "ミュール",
    "スリッパ",
    "草履",
    "下駄",
    "長靴",
    # 中文
    "鞋",
    "鞋子",
    "靴子",
    "靴",
    "高跟",
    "高跟鞋",
    "细高跟",
    "平底鞋",
    "皮鞋",
    "运动鞋",
    "球鞋",
    "帆布鞋",
    "凉鞋",
    "凉拖",
    "拖鞋",
    "短靴",
    "长靴",
    "马丁靴",
    "乐福鞋",
    "单鞋",
    "草鞋",
)

# 手套
GLOVE_KEYWORDS: tuple[str, ...] = (
    "glove",
    "gloves",
    "mitten",
    "mittens",
    "gauntlet",
    "gauntlets",
    "手袋",
    "グローブ",
    "ミトン",
    "手套",
)

# 下装 (裙 / 裤)
BOT_KEYWORDS: tuple[str, ...] = (
    "bot",
    "bottom",
    "bottoms",
    "skirt",
    "skirts",
    "pants",
    "trousers",
    "jeans",
    "shorts",
    "slacks",
    "leggings",
    "hakama",
    "ボトムス",
    "ボトム",
    "スカート",
    "ズボン",
    "半ズボン",
    "ショートパンツ",
    "袴",
    "下装",
    "裙",
    "裙子",
    "短裙",
    "长裙",
    "半身裙",
    "裤",
    "裤子",
    "短裤",
    "长裤",
    "牛仔裤",
    "打底裤",
    "阔腿裤",
    "腰布",
)

# 完全不改名的网格: 表情 / 眨眼 / 口型这类材质既不是服装也不是身体部件,
# 加了 `_` 前缀反而添乱
SKIP_KEYWORDS: tuple[str, ...] = (
    "表情",
    "emotion",
    "exp",
    "まばたき",
    "blink",
    "口パク",
)

# 一件衣服跨语义(连衣裙 / 连体衣 / 泳装), 必须由人划分割线, 不做自动命名
EXCLUDE_KEYWORDS: tuple[str, ...] = (
    "jumpsuit",
    "jumpsuits",
    "bodysuit",
    "bodysuits",
    "romper",
    "rompers",
    "play suit",
    "swimsuit",
    "swimsuits",
    "swimwear",
    "水着",
    "连体衣",
    "连体裤",
    "连身衣",
    "泳装",
    "泳衣",
)

# 身体类: 不是服装饰品, 只把同一套零部件归到一起方便批量处理。
# 在服装 / 饰品之后才匹配, 所以"头发"仍归 acc, "头饰"仍归 acc。
HITOMI_KEYWORDS: tuple[str, ...] = (
    "pupil",
    "pupils",
    "hitomi",
    "iris",
    "瞳",
    "瞳孔",
    "ひとみ",
    "黒目",
    "黑目",
)

EYE_KEYWORDS: tuple[str, ...] = (
    "eye",
    "eyes",
    "eyeball",
    "eyeballs",
    "eyewhite",
    "sclera",
    "目",
    "目玉",
    "白目",
    "眼",
    "眼睛",
    "眼球",
    "眼珠",
    "眼白",
)

EYE_HI_KEYWORDS: tuple[str, ...] = (
    "eyehi",
    "hi",
    "hl",
    "hilite",
    "highlight",
    "highlights",
    "ハイライト",
    "高光",
)

EYE_SHADOW_KEYWORDS: tuple[str, ...] = (
    "目影",
    "eye shadow",
    "eye shadows",
)

EYEBROW_KEYWORDS: tuple[str, ...] = (
    "eyebrow",
    "eyebrows",
    "brow",
    "brows",
    "眉",
    "眉毛",
    "まゆ",
    "まゆげ",
    "まゆ毛",
)

EYELINE_KEYWORDS: tuple[str, ...] = (
    "eyeline",
    "eyelines",
    "eyeliner",
    "eyeliners",
    "eyelash",
    "eyelashes",
    "lash",
    "lashes",
    "eyeshadow",
    "アイライン",
    "アイラッシュ",
    "アイシャドウ",
    "まつげ",
    "まつ毛",
    "眼线",
    "睫毛",
    "睫",
    "eyelid",
    "eyelids",
    "眼影",
)

MOUTH_KEYWORDS: tuple[str, ...] = (
    "mouth",
    "mouths",
    "tongue",
    "tongues",
    "teeth",
    "tooth",
    "口内",
    "口腔",
    "舌",
    "歯",
    "齿",
    "牙",
    "牙齿",
    "ベロ",
    "口",
    "唇",
    "唇线",
    "嘴",
    "嘴线",
)

EAR_KEYWORDS: tuple[str, ...] = (
    "ear",
    "ears",
    "ミミ",
    "耳",
    "耳朵",
    "耳部",
    "耳介",
    "みみ",
)

NECK_KEYWORDS: tuple[str, ...] = (
    "neck",
    "ネック",
    "脖",
    "脖子",
    "颈",
    "颈部",
)

HEAD_KEYWORDS: tuple[str, ...] = (
    "head",
    "heads",
    "face",
    "faces",
    "頭",
    "頭部",
    "顔",
    "顔面",
    "头",
    "头部",
    "脸",
    "脸部",
    "脸蛋",
    # "面"(脸), 口罩 / 面罩 / 面具 已在 acc 里先匹配
    "面",
)

NAIL_KEYWORDS: tuple[str, ...] = (
    "nail",
    "nails",
    "ツメ",
    "ネイル",
    "爪",
    "指甲",
)

HAND_KEYWORDS: tuple[str, ...] = (
    "hand",
    "hands",
    "finger",
    "fingers",
    "arm",
    "arms",
    "ハンド",
    "手",
    "手指",
    "臂",
    "腕",
)

LEG_KEYWORDS: tuple[str, ...] = (
    "leg",
    "legs",
    "thigh",
    "thighs",
    "脚",
    "足",
    "腿",
    "腿部",
    "脚部",
)

BODY_KEYWORDS: tuple[str, ...] = (
    "body",
    "bodies",
    "skin",
    "skins",
    "素体",
    "肌",
    "皮膚",
    "身体",
    "躯干",
    "胴体",
    "皮肤",
    "躯体",
    "体",
)

# 身体目标名 -> 关键词。具体部位在前, 笼统的 body 在最后;
# 名称里含多个关键词时先命中的赢, 所以"眼线"要先于"眼"。
BODY_KEYWORD_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("body-hitomi", HITOMI_KEYWORDS),
    # 高光 / 阴影 / 眼线 里含 "眼", 必须排在 body-eye 前面
    ("body-eye-hi", EYE_HI_KEYWORDS),
    ("body-eye-shadow", EYE_SHADOW_KEYWORDS),
    ("body-eyeline", EYELINE_KEYWORDS),
    ("body-eyebrow", EYEBROW_KEYWORDS),
    ("body-eye", EYE_KEYWORDS),
    ("body-mouth", MOUTH_KEYWORDS),
    ("body-nail", NAIL_KEYWORDS),
    ("body-hand", HAND_KEYWORDS),
    ("body-leg", LEG_KEYWORDS),
    ("body-ear", EAR_KEYWORDS),
    ("body-neck", NECK_KEYWORDS),
    ("body-head", HEAD_KEYWORDS),
    ("body", BODY_KEYWORDS),
)
BODY_TARGET_NAMES: tuple[str, ...] = tuple(
    target for target, _keywords in BODY_KEYWORD_GROUPS
)

# 服装目标名 -> 关键词。按越具体越靠前的顺序匹配:
# 袜 / 鞋 先于裤, 不然后者的"裤"会抢走"连裤袜", 前者的"靴"会抢走"靴下";
# 上衣先于胸罩, 不然后者的"ブラ"会抢走"ブラウス"。
# 跨语义的(连体衣 / 泳装)不收, 由人划分割线; 连衣裙按上衣处理, 裸裙部分自己归 cloth_bot。
CLOTH_KEYWORD_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("cloth_top", TOP_KEYWORDS),
    ("cloth_bra", BRA_KEYWORDS),
    ("pants", PANTS_KEYWORDS),
    ("panty", PANTY_KEYWORDS),
    ("sock", SOCK_KEYWORDS),
    ("shoe", SHOE_KEYWORDS),
    ("glove", GLOVE_KEYWORDS),
    ("cloth_bot", BOT_KEYWORDS),
)
CLOTH_TARGET_NAMES: tuple[str, ...] = tuple(
    target for target, _keywords in CLOTH_KEYWORD_GROUPS
)
# 会自动命名的目标名 (服装 + 身体), 出现这些名字就说明已经处理过
RENAME_TARGET_NAMES: tuple[str, ...] = CLOTH_TARGET_NAMES + BODY_TARGET_NAMES
# ==================== 配置区结束 ====================

HEADMOD_SUFFIX = "_headmod"
MANUAL_PREFIX = "_"
BLENDER_NUMBER_RE = r"\.\d{3}$"

_LATIN_WORD_RE = re.compile(r"[a-z0-9]+")


def _latin_words(name: str) -> list[str]:
    return _LATIN_WORD_RE.findall(name.lower())


def _fold_plural(word: str) -> set[str]:
    """去掉数字后缀和复数后缀, 返回可能的单数形式"""
    word = word.rstrip("0123456789")
    forms = {word}
    if word.endswith("es"):
        forms.add(word[:-2])
    if word.endswith("s"):
        forms.add(word[:-1])
    return forms


def _match_keywords(name: str, keywords: Sequence[str]) -> bool:
    """英文按整词(含单复数)比对, 中日文按子串比对"""
    lower = name.lower()
    words = _latin_words(lower)
    folded: set[str] = set()
    for word in words:
        folded |= _fold_plural(word)

    phrase = " ".join(words)
    for keyword in keywords:
        if not keyword.isascii():
            if keyword in lower:
                return True
        elif " " in keyword:
            pattern = r"\b" + r"\s+".join(map(re.escape, keyword.split())) + r"s?\b"
            if re.search(pattern, phrase):
                return True
        elif keyword in folded:
            return True

    return False


def match_acc_priority(name: str) -> int | None:
    """命中 acc 关键词时返回分组序号(越小越靠前), 未命中返回 None"""
    for priority, keywords in enumerate(ACC_KEYWORD_GROUPS):
        if _match_keywords(name, keywords):
            return priority

    return None


def match_cloth_target(name: str) -> str | None:
    """命中服装关键词时返回目标服装名, 未命中返回 None"""
    for target, keywords in CLOTH_KEYWORD_GROUPS:
        if _match_keywords(name, keywords):
            return target

    return None


def match_body_target(name: str) -> str | None:
    """命中身体部位关键词时返回目标身体名, 未命中返回 None"""
    for target, keywords in BODY_KEYWORD_GROUPS:
        if _match_keywords(name, keywords):
            return target

    return None


def is_skip_name(name: str) -> bool:
    """表情 / 眨眼 / 口型这类网格完全不动"""
    return _match_keywords(name, SKIP_KEYWORDS)


def is_excluded(name: str) -> bool:
    """跨语义的衣服(连衣裙 / 连体衣 / 泳装), 交给用户自己拆"""
    return _match_keywords(name, EXCLUDE_KEYWORDS)


def get_acc_slot_name(index: int) -> str:
    """acc 槽位名: 1 -> acc, 9 -> acc9, 10 -> _acc10(超出游戏槽位, 加前缀提示手动处理)"""
    if index > len(ACC_TYPES):
        return f"{MANUAL_PREFIX}acc{index}"

    return ACC_TYPES[index - 1]


def is_export_mesh_name(name: str) -> bool:
    """能直接导出的名字 (游戏里的网格名 / 头模名)"""
    return name in MESH_ANIMATOR_MAP or name.endswith(HEADMOD_SUFFIX)


def is_merge_name(name: str) -> bool:
    """同一目标的重名网格 cloth_top_2 / body-eye_2 …, 需要用户自己合并"""
    base = _strip_duplicate_suffix(name)
    return base != name and base in RENAME_TARGET_NAMES


def is_legal_mesh_name(name: str) -> bool:
    """已经命名好的网格: 合法导出名 / 身体名 / 同目标的重名后缀, 不再改"""
    # cloth_top_2 是给用户合并用的, 重跑时不能再改一次
    return is_export_mesh_name(name) or name in RENAME_TARGET_NAMES or is_merge_name(name)


def _strip_duplicate_suffix(name: str) -> str:
    """去掉给重名网格加的 _2 / _3 后缀"""
    return re.sub(r"_\d+$", "", name)


def is_half_off_mesh(name: str) -> bool:
    """半脱网格: 合法名 + .001 (例如 cloth_top.001), 需要用户自己做

    不能把所有 .001 结尾都当半脱: Blender 复制出来的物体也是 名字.001。
    """
    base = _strip_blender_number(name)
    return base != name and is_export_mesh_name(base)


def _strip_blender_number(name: str) -> str:
    """去掉 Blender 复制时自动加的 .001 / .002 后缀"""
    return re.sub(BLENDER_NUMBER_RE, "", name)


def strip_manual_prefix(name: str) -> str:
    return name.lstrip(MANUAL_PREFIX) or name


def plan_mesh_names(
    selected_names: Iterable[str], taken_names: Iterable[str]
) -> dict[str, str]:
    """计算 旧名 -> 新名, 不需要改名的网格不在结果里

    taken_names: 场景里所有物体名, 用来避开已被占用的 acc 槽位和重名。
    """
    taken = set(taken_names)
    cloth_names: list[tuple[str, str]] = []
    acc_names: list[tuple[int, str]] = []
    body_names: list[tuple[str, str]] = []
    manual_names: list[str] = []
    for name in selected_names:
        # 忽略表排最前: "面 表情" 不能被 "面" 抢成 body-head
        if is_skip_name(name) or is_half_off_mesh(name) or is_legal_mesh_name(name):
            continue

        target = None if is_excluded(name) else match_cloth_target(name)
        if target:
            cloth_names.append((target, name))
            continue

        priority = match_acc_priority(name)
        if priority is not None:
            acc_names.append((priority, name))
            continue

        # 身体类最后匹配: "头发" / "头饰" 要在 acc 里就被拿走
        target = match_body_target(name)
        if target:
            body_names.append((target, name))
            continue

        manual_names.append(name)

    renames: dict[str, str] = {}
    # 同一目标有多个网格时第一个用本名, 后面的加 _2 / _3 (等用户合并), 同目标按名字排序
    for target, name in sorted(cloth_names + body_names):
        new_name = target
        index = 2
        while new_name in taken:
            new_name = f"{target}_{index}"
            index += 1

        taken.add(new_name)
        renames[name] = new_name

    # 头发优先占用前面的槽位, 同组按名字排序保证每次结果一致
    slot_index = 1
    for _priority, name in sorted(acc_names):
        slot_name = get_acc_slot_name(slot_index)
        while slot_name in taken:
            slot_index += 1
            slot_name = get_acc_slot_name(slot_index)

        slot_index += 1
        taken.add(slot_name)
        renames[name] = slot_name

    for name in manual_names:
        base = strip_manual_prefix(_strip_blender_number(name))
        new_name = MANUAL_PREFIX + base
        if new_name == name:
            continue

        index = 2
        while new_name in taken:
            new_name = f"{MANUAL_PREFIX}{base}_{index}"
            index += 1

        taken.add(new_name)
        renames[name] = new_name

    return renames


def rename_meshes(objs: Iterable[Object]) -> dict[str, str]:
    """按关键词给选中的网格改名, 返回 旧名 -> 新名"""
    objs = list(objs)
    taken = {obj.name for obj in bpy.data.objects}
    renames = plan_mesh_names([obj.name for obj in objs], taken)
    if not renames:
        return renames

    obj_map = {obj.name: obj for obj in objs}
    # 两段改名: 先换成临时名, 避免目标名被别的物体占着时 Blender 自动补 .001
    pending = [(obj_map[old_name], new_name) for old_name, new_name in renames.items()]
    for index, (obj, _new_name) in enumerate(pending):
        temp_name = f"{MANUAL_PREFIX}tmp{index}"
        while temp_name in taken:
            temp_name += MANUAL_PREFIX
        obj.name = temp_name
        taken.add(temp_name)

    for obj, new_name in pending:
        obj.name = new_name

    return renames
