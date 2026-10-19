from pathlib import Path

import bpy
from bpy.props import BoolProperty, FloatProperty, StringProperty
from bpy.types import Context

from hitori_addon.image import (
    DEFAULT_TEXTURE_EXCLUDE_DIRS,
    DEFAULT_TEXTURE_MATCH_THRESHOLD,
    TEXTURE_EXTENSIONS,
    TextureImportReport,
    import_missing_texture,
)
from hitori_addon.menu import DirectoryPicker, message_box


def split_names(text: str) -> list[str]:
    """逗号 / 空格 / 分号分隔的名字列表"""
    for separator in ",;|":
        text = text.replace(separator, " ")
    return text.split()


def format_result(texture_dir: str, report: TextureImportReport) -> str:
    results = report.results
    matched = [result for result in results if result.path]
    skipped = [result for result in results if not result.path]
    lines = [f"贴图目录: {texture_dir}"]
    lines.append(f"命中 {len(matched)} 个材质, 未配图 {len(skipped)} 个")
    lines.extend(
        f"{result.material} -> {Path(result.path).name} ({result.score:.2f})"
        for result in matched
    )
    for result in skipped:
        lines.append(f"{result.material}: {result.reason} ({result.score:.2f})")

    if report.removed_nodes or report.removed_normal_maps or report.removed_images:
        lines.append(
            f"清理: 贴图节点 {report.removed_nodes} 个, 没法线贴图的法线节点 {report.removed_normal_maps} 个, "
            f"没用的贴图 {len(report.removed_images)} 张"
        )
    return "\n".join(lines)


class SelectTextureFolder(DirectoryPicker):
    bl_idname: str = "wm.select_texture_folder"
    bl_label: str = "选择当前材质文件夹"

    recursive: BoolProperty(
        name="搜索贴图时包含子文件夹",
        description="",
        default=True,
    )
    exclude_dirs: StringProperty(
        name="排除文件夹",
        description="按文件夹名排除 (逗号分隔), 这些文件夹里的图不当贴图",
        default=", ".join(DEFAULT_TEXTURE_EXCLUDE_DIRS),
    )
    extensions: StringProperty(
        name="扩展名优先级",
        description="逗号分隔, 排前面的优先 (同一张图 png 优先于 psd)",
        default=", ".join(TEXTURE_EXTENSIONS),
    )
    threshold: FloatProperty(
        name="相似度阈值",
        description="材质名与贴图名的相似度低于该值就不配图",
        default=DEFAULT_TEXTURE_MATCH_THRESHOLD,
        min=0.0,
        max=1.0,
        step=5,
        precision=2,
        subtype="FACTOR",
    )
    only_missing: BoolProperty(
        name="只处理丢失贴图的材质",
        description="Base Color 已经有能读到的贴图就跳过",
        default=True,
    )
    skip_masks: BoolProperty(
        name="跳过 Alpha / 遮罩类材质",
        description="alpha / shadow / outline 这类材质需要专门的遮罩图, 不拿漫反射贴图填",
        default=True,
    )
    cleanup: BoolProperty(
        name="清理旧贴图节点",
        description="换下来的丢失贴图节点与没人引用的贴图数据块一并删掉",
        default=True,
    )

    def execute(self, context: Context) -> set[str]:
        try:
            report = import_missing_texture(
                self.directory,
                recursive=self.recursive,
                extensions=split_names(self.extensions),
                exclude_dirs=split_names(self.exclude_dirs),
                threshold=self.threshold,
                only_missing=self.only_missing,
                skip_masks=self.skip_masks,
                cleanup=self.cleanup,
            )
        except LookupError as error:
            message_box(str(error), title="材质寻找缺失贴图", icon="ERROR")
            return {"CANCELLED"}

        message_box(format_result(self.directory, report), title="材质寻找缺失贴图")
        return {"FINISHED"}


if __name__ == "__main__":
    bpy.utils.register_class(SelectTextureFolder)
    bpy.ops.wm.select_texture_folder("INVOKE_DEFAULT")
