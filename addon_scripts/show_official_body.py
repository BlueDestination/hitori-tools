from hitori_addon.obj import get_obj
from hitori_addon.template_link import BODYTIGHT_NAME

obj = get_obj(BODYTIGHT_NAME)
obj.hide_set(not obj.hide_get())
