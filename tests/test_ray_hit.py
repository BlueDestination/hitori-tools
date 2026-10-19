import numpy as np

from hitori_addon.debug import print_timing
from hitori_addon.mesh import (
    apply_mesh,
    get_clipping_vertex_indices,
    get_clipping_vertex_indices_new_slower,
)
from hitori_addon.obj import get_obj
from hitori_addon.template_link import BODYTIGHT_NAME


def test_ray_hit_mesh(tests=2):
    obj = get_obj("cloth_bot")
    bodytight = get_obj(BODYTIGHT_NAME)
    apply_mesh(obj)
    print_timing(start=True)

    for i in range(tests):
        np.array(get_clipping_vertex_indices(obj, bodytight))
    print_timing("旧方法耗时:")

    for i in range(tests):
        np.array(get_clipping_vertex_indices_new_slower(obj, bodytight))
    print_timing("新方法耗时:")
