from hitori_addon.debug import print_timing
from hitori_addon.mesh import selected_vertex_indices_arr
from hitori_addon.obj import get_obj


def test_ray_hit_mesh():
    obj = get_obj("acc")
    print_timing(start=True)

    for i in range(100):
        selected_vertex_indices_arr(obj)
    print_timing("新方法耗时:")
