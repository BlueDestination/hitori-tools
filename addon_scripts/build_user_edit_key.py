from hitori_addon.const import USER_EDIT_KEY_NAME
from hitori_addon.menu import message_box
from hitori_addon.mesh import add_key, get_key_names, get_keys, selected_meshes

TITLE = "构建user_edit_key"

objs = selected_meshes()
if not objs:
    message_box("请先选中网格", title=TITLE, icon="ERROR")
else:
    built_names: list[str] = []
    skipped_names: list[str] = []

    for obj in objs:
        keys = get_keys(obj, create_if_none=True)

        # 已有同名形态键就跳过, 免得重复运行堆出 user_edit_key.001
        if USER_EDIT_KEY_NAME in get_key_names(obj):
            skipped_names.append(obj.name)
            continue

        new_key = add_key(obj, key_name=USER_EDIT_KEY_NAME, from_mix=True, select=True)

        for key in keys:
            key.value = 0

        new_key.value = 1
        built_names.append(obj.name)

    built_text = f": {', '.join(built_names)}" if built_names else ""
    lines = [f"构建 {len(built_names)} 个网格{built_text}"]
    if skipped_names:
        lines.append(
            f"跳过 {len(skipped_names)} 个网格 (已有 {USER_EDIT_KEY_NAME}): "
            f"{', '.join(skipped_names)}"
        )
    message_box("\n".join(lines), title=TITLE)
