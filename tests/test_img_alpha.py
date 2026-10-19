import bpy
import numpy as np

from hitori_addon.image import get_img_min_alpha


def test_get_min_alpha():
    imgs = bpy.data.images
    result = [get_img_min_alpha(img) for img in imgs]
    arr = np.array(result).round(6)
    print(arr)
