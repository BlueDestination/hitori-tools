from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import Any, Optional

import UnityPy
from UnityPy import Environment
from UnityPy.files import ObjectReader

from hitori_addon.const import ACC_TYPES, CLOTH_TYPES
from hitori_addon.menu import format_name_list
from hitori_addon.path import aspath
from hitori_addon.printf import color_text
from hitori_addon.sb3u import CLOTH_TYPE_ANIMATOR_NAME_MAP


def get_obj_names(objs: list[ObjectReader]) -> list[str]:
    return [obj.read_typetree()["m_Name"] for obj in objs]


def get_u3d_mats(env_objs: list[ObjectReader]) -> list[ObjectReader]:
    return [obj for obj in env_objs if obj.type.name == "Material"]


def get_u3d_imgs(env_objs: list[ObjectReader]) -> list[ObjectReader]:
    return [obj for obj in env_objs if obj.type.name == "Texture2D"]


def get_u3d_mat_names(env_objs: list[ObjectReader]) -> list[str]:
    u3d_mats = get_u3d_mats(env_objs)
    u3d_mat_names = get_obj_names(u3d_mats)
    return u3d_mat_names


def get_u3d_img_names(env_objs: list[ObjectReader]) -> list[str]:
    u3d_imgs = get_u3d_imgs(env_objs)
    u3d_img_names = get_obj_names(u3d_imgs)
    return u3d_img_names


def get_component_index_map(env_objs: list[ObjectReader]) -> dict[str, int]:
    """注:
    componentIndex(连续)是env.objects的列表索引(连续);
    pathID(断续)是env.assets[0].objects的字典索引(断续);
    两者的顺序完全相同,只是索引之间有间隔差别.
    """
    return {
        obj.read_typetree()["m_Name"]: i
        for i, obj in enumerate(env_objs)
        if obj.type.name == "GameObject"
    }


@dataclass
class RootBonesReport:
    """一次注册写了什么: 动骨 (db_mono 名, 子骨名) / 接骨 (bi_mono 名, 根骨名, 父骨名)"""

    dynbones: list[tuple[str, str]] = field(default_factory=list)
    join_bones: list[tuple[str, str, str]] = field(default_factory=list)
    # 这条链挂到的网格名, 弹窗里标出类型是怎么来的 (u3d 里没有这个信息, 由调用方填)
    mesh_names: set[str] = field(default_factory=set)

    @property
    def is_empty(self) -> bool:
        return not self.dynbones and not self.join_bones


class RootBonesError(RuntimeError):
    """u3d 里缺少要注册的骨骼 / mono 槽位, 写不进动骨接骨"""


MAX_REPORT_MESH_NAMES = 6


def format_mesh_names(mesh_names: Iterable[str]) -> str:
    """一行写完的网格名列表 (弹窗里是括号内联, 不能换行)"""
    names = sorted(mesh_names)
    text = ", ".join(names[:MAX_REPORT_MESH_NAMES])
    if len(names) > MAX_REPORT_MESH_NAMES:
        text += f" ... 共 {len(names)} 个"
    return text


def format_root_bones_report(
    kind: str, file_name: str, reports: Mapping[str, RootBonesReport]
) -> tuple[str, bool]:
    """弹窗文本 + 是否写了东西: 每类的来源网格、接骨 (根骨 -> 父骨) 与动骨 (顺序即 db_mono 编号)"""
    written = {
        cloth_type: report
        for cloth_type, report in reports.items()
        if not report.is_empty
    }
    if not written:
        return f"没有找到任何{kind}动骨接骨 ({file_name} 里的 mono 都是空的)", False

    lines = [f"已写入 {file_name}:"]
    for cloth_type, report in written.items():
        text = f"{cloth_type}: 动骨 {len(report.dynbones)} 根"
        if report.join_bones:
            text += f", 接骨 {len(report.join_bones)} 根"
        if report.mesh_names:
            text += f" (网格 {format_mesh_names(report.mesh_names)})"
        lines.append(text)
        for bi_mono_name, root_bone, parent_bone in report.join_bones:
            lines.append(f"    接骨 {bi_mono_name}: {root_bone} -> {parent_bone}")
        if report.dynbones:
            lines.append("    动骨:")
            dynbone_names = [name for _, name in report.dynbones]
            lines.append(format_name_list(dynbone_names, indent="        "))
    return "\n".join(lines), True


def count_mono_slots(box: "EasyObjectBox", prefix: str, animator_name: str) -> int:
    """u3d 里 `<prefix>NN` 槽位的数量 (从 00 数到第一个缺失)"""
    index = 0
    while box.find_or_none(f"{prefix}{index:02}", "MonoBehaviour", animator_name):
        index += 1
    return index


def get_cloth_dynbone_names(
    box: "EasyObjectBox", cloth_type: str, parent_bones: Iterable[str]
) -> list[str]:
    """服装动骨 = 接骨根骨的所有子骨 (根骨自己参与接骨, 不参与物理)"""
    animator_name = CLOTH_TYPE_ANIMATOR_NAME_MAP[cloth_type]
    names: list[str] = []
    for parent_bone in parent_bones:
        transform = box.find_or_none(parent_bone, "Transform", animator_name)
        if transform is not None:
            names.extend(child.name for child in transform.children)
    return names


def validate_dynbones(
    box: "EasyObjectBox", dynbone_names_map: Mapping[str, list[str]]
) -> list[str]:
    """动骨写入前的检查: Transform 在不在, db_mono 槽位够不够"""
    problems: list[str] = []
    for cloth_type, dynbone_names in dynbone_names_map.items():
        animator_name = CLOTH_TYPE_ANIMATOR_NAME_MAP[cloth_type]
        for dynbone_name in dynbone_names:
            if box.find_or_none(dynbone_name, "Transform", animator_name) is None:
                problems.append(
                    f'"{animator_name}" 里没有动骨 "{dynbone_name}" 的 Transform'
                )
        db_slots = count_mono_slots(box, f"{cloth_type}_db_mono_", animator_name)
        if len(dynbone_names) > db_slots:
            problems.append(
                f'"{cloth_type}" 有 {len(dynbone_names)} 根动骨, "{animator_name}" 里只有'
                f' {db_slots} 个 "{cloth_type}_db_mono" 槽位'
            )
    return problems


def validate_root_bones(
    box: "EasyObjectBox", cloth_root_bones_map: Mapping[str, list[str]]
) -> list[str]:
    """服装写入前的全量检查, 返回问题描述 (一次把问题说完, 不写到一半才炸)"""
    problems = validate_dynbones(
        box,
        {
            cloth_type: get_cloth_dynbone_names(box, cloth_type, parent_bones)
            for cloth_type, parent_bones in cloth_root_bones_map.items()
        },
    )
    for cloth_type, parent_bones in cloth_root_bones_map.items():
        animator_name = CLOTH_TYPE_ANIMATOR_NAME_MAP[cloth_type]
        for parent_bone in parent_bones:
            transform = box.find_or_none(parent_bone, "Transform", animator_name)
            if transform is None:
                problems.append(
                    f'"{animator_name}" 里没有骨骼 "{parent_bone}" 的 Transform'
                )
            elif transform.parent is None:
                problems.append(
                    f'"{parent_bone}" 在 "{animator_name}" 里没有父骨, 写不了接骨'
                )
        bi_slots = count_mono_slots(box, f"{cloth_type}_bi_mono_", animator_name)
        if len(parent_bones) > bi_slots:
            problems.append(
                f'"{cloth_type}" 有 {len(parent_bones)} 根接骨, "{animator_name}" 里只有'
                f' {bi_slots} 个 "{cloth_type}_bi_mono" 槽位'
            )
    return problems


def write_dynbones(
    box: "EasyObjectBox",
    cloth_type: str,
    dynbone_names: Iterable[str],
    report: RootBonesReport,
) -> None:
    """按顺序把骨名写进 `<cloth_type>_db_mono_NN` 的 m_Root"""
    animator_name = CLOTH_TYPE_ANIMATOR_NAME_MAP[cloth_type]
    for index, dynbone_name in enumerate(dynbone_names):
        db_mono_name = f"{cloth_type}_db_mono_{index:02}"
        db_mono = box.find(db_mono_name, "MonoBehaviour", animator_name)
        transform = box.find(dynbone_name, "Transform", animator_name)
        db_mono.tree["m_Root"]["m_PathID"] = transform.id
        db_mono.save()
        report.dynbones.append((db_mono_name, dynbone_name))
        print(color_text(f"成功填写动骨: {dynbone_name}", "g"))


def save_u3d_reports(
    box: "EasyObjectBox", reports: Mapping[str, RootBonesReport]
) -> dict[str, RootBonesReport]:
    """一个 mono 都没填时不覆盖 u3d (避免无意义地重打包)"""
    if all(report.is_empty for report in reports.values()):
        print(color_text("\n没有要写入的动骨接骨, 跳过保存", "y"))
    else:
        box.save_file()
        print(color_text("\n填写动骨接骨成功", "c"))
    return dict(reports)


def register_u3d_dynbones(
    u3d_path: str | Path, dynbone_names_map: Mapping[str, list[str]]
) -> dict[str, RootBonesReport]:
    """把动骨写进 u3d: 传入的骨名直接当 `m_Root` (饰品用, 饰品没有接骨)

    饰品导出时多根根骨已经统一成一根, 动骨链起点由 `dynbone.find_acc_dynbone_bone_names` 定。
    槽位不够 / 找不到骨骼时抛 `RootBonesError`, 此时 u3d 文件不会被动过;
    一个 mono 都没填时不重建 zipmod。
    """
    box = EasyObjectBox(u3d_path)
    problems = validate_dynbones(box, dynbone_names_map)
    if problems:
        raise RootBonesError(
            "无法写入动骨 (u3d 没有被改动):\n"
            + "\n".join(f"    {problem}" for problem in problems)
        )

    reports: dict[str, RootBonesReport] = {}
    for cloth_type, dynbone_names in dynbone_names_map.items():
        report = reports[cloth_type] = RootBonesReport()
        write_dynbones(box, cloth_type, dynbone_names, report)
    return save_u3d_reports(box, reports)


def register_u3d_root_bones(
    u3d_path: str | Path,
    cloth_root_bones_map: Mapping[str, list[str]],
) -> dict[str, RootBonesReport]:
    """服装: 动骨 (根骨的每个子骨) 与接骨 (根骨 -> 父骨) 写进 u3d, 按类型返回分别写了哪些

    槽位不够 / 找不到骨骼时抛 `RootBonesError`, 此时 u3d 文件不会被动过;
    一个 mono 都没填时不重建 zipmod。
    """
    box = EasyObjectBox(u3d_path)
    problems = validate_root_bones(box, cloth_root_bones_map)
    if problems:
        raise RootBonesError(
            "无法写入动骨接骨 (u3d 没有被改动):\n"
            + "\n".join(f"    {problem}" for problem in problems)
        )

    reports: dict[str, RootBonesReport] = {}

    for cloth_type, parent_bones in cloth_root_bones_map.items():
        animator_name = CLOTH_TYPE_ANIMATOR_NAME_MAP[cloth_type]
        report = reports[cloth_type] = RootBonesReport()
        dynbone_names = get_cloth_dynbone_names(box, cloth_type, parent_bones)
        write_dynbones(box, cloth_type, dynbone_names, report)

        for index, parent_bone in enumerate(parent_bones):
            parent_transform = box.find(parent_bone, "Transform", animator_name)
            bi_mono_name = f"{cloth_type}_bi_mono_{index:02}"
            bi_mono = box.find(bi_mono_name, "MonoBehaviour", animator_name)
            bi_mono.tree["trfSrc"]["m_PathID"] = parent_transform.id
            bi_mono.tree["trfDst"]["m_PathID"] = parent_transform.parent.id
            bi_mono.save()
            report.join_bones.append(
                (bi_mono_name, parent_transform.name, parent_transform.parent.name)
            )
            print(color_text(f"成功填写接骨: {parent_transform.name}", "y"))

    return save_u3d_reports(box, reports)


def read_u3d_root_bones(
    u3d_path: str | Path,
    cloth_types: Iterable[str] = (*CLOTH_TYPES, *ACC_TYPES),
) -> dict[str, RootBonesReport]:
    """从 u3d 反读已填的动骨 / 接骨 (按 mono 里的 path_id 查名字), 空类型也返回空报告

    饰品注册跑在无头子进程里 (弹窗只会在控制台打印), 所以主进程用这个把刚写进去的内容读回来弹窗。
    """
    box = EasyObjectBox(u3d_path)
    reports: dict[str, RootBonesReport] = {}

    for cloth_type in cloth_types:
        animator_name = CLOTH_TYPE_ANIMATOR_NAME_MAP[cloth_type]
        report = reports[cloth_type] = RootBonesReport()

        db_mono_prefix = f"{cloth_type}_db_mono_"
        for index in range(count_mono_slots(box, db_mono_prefix, animator_name)):
            db_mono = box.find(f"{db_mono_prefix}{index:02}", "MonoBehaviour", animator_name)
            child = box.get_by_path_id(db_mono.tree["m_Root"]["m_PathID"])
            if child is not None:
                report.dynbones.append((f"{db_mono_prefix}{index:02}", child.name))

        if cloth_type in ACC_TYPES:
            continue

        bi_mono_prefix = f"{cloth_type}_bi_mono_"
        for index in range(count_mono_slots(box, bi_mono_prefix, animator_name)):
            bi_mono = box.find(f"{bi_mono_prefix}{index:02}", "MonoBehaviour", animator_name)
            src = box.get_by_path_id(bi_mono.tree["trfSrc"]["m_PathID"])
            dst = box.get_by_path_id(bi_mono.tree["trfDst"]["m_PathID"])
            if src is not None and dst is not None:
                report.join_bones.append((f"{bi_mono_prefix}{index:02}", src.name, dst.name))

    return reports


class EasyObject:
    def __init__(self, data: ObjectReader, box: "EasyObjectBox"):
        self._data: ObjectReader = data
        self.box: EasyObjectBox = box

        self.type: str = data.type.name
        self.id: int = data.path_id
        self.component_id: int = box.get_component_id(self.id)

        self.tree: dict[str, Any] = data.read_typetree()
        self.name: str | None = self.tree.get("m_Name")

    def __after_box_init__(self):
        if self.type == "Transform":
            self.name = self.game_obj.name
        elif self.type == "SkinnedMeshRenderer":
            self.name = self.mesh.name if self.mesh else None
        elif self.type == "Shader":
            self.name = self.tree["m_ParsedForm"]["m_Name"]

    def __repr__(self) -> str:
        return f'<"{self.name}" {self.type} id={self.id}>'

    def save(self):
        self._data.save_typetree(self.tree)

    def get_type_obj(self, type_name: str) -> Optional["EasyObject"]:
        obj_tree: dict[str, int] | None = self.tree.get(type_name)
        if obj_tree is None:
            return None

        obj_path_id: int = obj_tree["m_PathID"]
        if obj_path_id == 0 or obj_path_id not in self.box.id_obj_map:
            return None

        return self.box[obj_path_id]

    @cached_property
    def parent(self) -> Optional["EasyObject"]:
        if self.type != "Transform":
            raise TypeError("只有Transform类型有parent属性")
        return self.get_type_obj("m_Father")

    @cached_property
    def ancestor(self) -> Optional["EasyObject"]:
        if self.type != "Transform":
            raise TypeError("只有Transform类型有ancestor属性")

        current = self
        while current.parent:
            current = current.parent
        return current

    @cached_property
    def animator(self) -> Optional["EasyObject"]:
        if self.game_obj is None:
            return None
        return self.game_obj.transform.ancestor.game_obj

    @cached_property
    def children(self) -> list["EasyObject"]:
        if self.type != "Transform":
            raise TypeError("只有Transform类型有children属性")
        return [
            self.box[child_info["m_PathID"]] for child_info in self.tree["m_Children"]
        ]

    @cached_property
    def game_obj(self) -> Optional["EasyObject"]:
        if self.type == "GameObject":
            return self
        return self.get_type_obj("m_GameObject")

    @cached_property
    def transform(self) -> Optional["EasyObject"]:
        if self.type == "Transform":
            return self

        first_component = self.game_obj.tree["m_Component"][0]["component"]
        transform_path_id = first_component["m_PathID"]
        return self.box[transform_path_id]

    @cached_property
    def mesh(self) -> Optional["EasyObject"]:
        return self.get_type_obj("m_Mesh")


class EasyObjectBox:
    """初始化env用时90ms,初始化box用时150ms,如果需要频繁访问u3d可以避免初始化该类,而是初始化UnityPy的env"""

    def __init__(self, u3d_path: str | Path):
        u3d_path = aspath(u3d_path)
        if not u3d_path.exists():
            raise FileNotFoundError(f"不存在文件: {u3d_path}")

        self._env: Environment = UnityPy.load(str(u3d_path))
        self._path: Path = u3d_path
        self._filepath: str = str(u3d_path)
        self._id_component_id_map: dict[int, int] = {
            data.path_id: i for i, data in enumerate(self._env.objects)
        }
        self._assets = self._env.assets
        if len(self._assets) == 0:
            raise RuntimeError(f"{self._filepath}不存在有效资源包")
        self._id_data_map: dict[int, ObjectReader] = self._assets[0].objects
        self.id_obj_map: dict[int, EasyObject] = {
            path_id: EasyObject(data, self)
            for path_id, data in self._id_data_map.items()
        }
        self.ids: list[int] = list(self.id_obj_map.keys())
        self._objs: list[EasyObject] = list(self.id_obj_map.values())
        self._len: int = len(self._objs)
        self.__post_init__()

    def __post_init__(self):
        for obj in self._objs:
            obj.__after_box_init__()

        self.obj_names: list[str] = [obj.name for obj in self._objs]
        self.obj_animator_names: list[str] = [
            obj.animator.name if obj.animator else None for obj in self._objs
        ]

    def __getitem__(self, path_id: int) -> EasyObject:
        if path_id not in self.id_obj_map:
            raise KeyError(f"不存在path_id={path_id}的物体")
        return self.id_obj_map[path_id]

    def __iter__(self):
        return iter(self._objs)

    def __len__(self):
        return self._len

    def find(self, name: str, type_name: str, animator_name: str):
        type_correct = False
        animator_correct = False
        start = 0
        while not (type_correct and animator_correct):
            index = self.obj_names.index(name, start)
            obj_animator_name = self.obj_animator_names[index]
            obj_type_name = self._objs[index].type
            type_correct = obj_type_name == type_name
            animator_correct = obj_animator_name == animator_name
            if type_correct and animator_correct:
                return self._objs[index]
            start = index + 1

    def find_or_none(
        self, name: str, type_name: str, animator_name: str
    ) -> EasyObject | None:
        """同 find, 找不到返回 None"""
        try:
            return self.find(name, type_name, animator_name)
        except ValueError:
            return None

    def get_by_path_id(self, path_id: int) -> EasyObject | None:
        """按 path_id 取物体, 0 / 不存在返回 None (mono 里没填时是 0)"""
        if not path_id or path_id not in self.id_obj_map:
            return None
        return self.id_obj_map[path_id]

    def get_component_id(self, path_id: int) -> int:
        return self._id_component_id_map[path_id]

    def save_file(self, filepath: str | None = None):
        if not filepath:
            filepath = self._filepath

        raw = self._env.file.save(packer="original")
        with open(filepath, "wb") as f:
            f.write(raw)
