from hitori_addon.debug import print_timing
from hitori_addon.obj import get_obj
from hitori_addon.template_link import BODYTIGHT_NAME
from hitori_addon.vg import get_weight_matrix


def test_ray_hit_mesh(tests=15):
    obj = get_obj(BODYTIGHT_NAME)
    print_timing(start=True)

    for i in range(tests):
        get_weight_matrix(obj)
    print_timing("旧方法耗时:")

    # for i in range(tests):
    #     b = get_weight_matrix_new(obj)
    # print_timing('新方法耗时:')
    #
    # print('结果是否相等:', np.array_equal(a, b))
