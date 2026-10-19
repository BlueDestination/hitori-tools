import UnityPy

from hitori_addon.template import U3D_TEMPLATE_DIR
from hitori_addon.u3d import get_component_index_map

chara_u3d = U3D_TEMPLATE_DIR / "chara_name.unity3d"
head_u3d = U3D_TEMPLATE_DIR / "chara_name-head.unity3d"

for u3d_path in [chara_u3d, head_u3d]:
    # UnityPy.load不支持Path只支持str
    env = UnityPy.load(str(u3d_path))
    env_objs = env.objects
    component_index_map = get_component_index_map(env_objs)
    print(u3d_path)
    print(env_objs)
    print(component_index_map)
