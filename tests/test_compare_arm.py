from pprint import pprint

import numpy as np

from hitori_addon.obj import get_obj, select_obj, set_mode
from hitori_addon.template_link import ARMATURE_NAME

arm = get_obj(ARMATURE_NAME)
arm1 = get_obj("Armature.001")

set_mode("OBJECT")
select_obj(arm)
set_mode("EDIT")
mat_map = {eb.name: eb.matrix for eb in arm.data.edit_bones}

set_mode("OBJECT")
select_obj(arm1)
set_mode("EDIT")
mat_map1 = {eb.name: eb.matrix for eb in arm1.data.edit_bones}

set_mode("OBJECT")
print("长度:", len(mat_map), len(mat_map1))
print("键相等:", list(mat_map.keys()) == list(mat_map1.keys()))

tolerance = 1e-5
diff_keys = [
    key
    for key in mat_map
    if key in mat_map1 and not np.allclose(mat_map[key], mat_map1[key], atol=tolerance)
]
pprint(["值不相等的键:", diff_keys])
