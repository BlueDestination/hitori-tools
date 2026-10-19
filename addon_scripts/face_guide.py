"""把捏脸指南写进文本块 `捏脸指南`

正交视图下叠加正交模型截图, 按部位逐项对齐五官; 指南较长弹窗放不下,
所以写进文本块让用户自己看。
"""

from hitori_addon.menu import message_box
from hitori_addon.text import write_text_data

TITLE = "查看捏脸指南"

text_data_name = "捏脸指南"

GUIDE = """\
正交视图捏脸, 叠加正交模型截图, 精确捏脸重合
(视图 -> 正交, 用背景图 / 参考图叠加, 一次只调一项)

眼睛(影响眼珠, 眼线): 眼睛高度, 眼睛宽度, 眼睛上下, 眼睛左右, 眼睛角度
眼线(眼睑): 上/下眼睑 * 内/中/外(6种), 眼头, 眼尾
瞳孔(眼珠): 瞳孔高度, 瞳孔宽度, 瞳孔上下, 瞳孔左右

脸型: 下巴尖宽度, 下巴宽度, 脸颊宽度, 颧骨宽度
嘴巴: 嘴巴上下, 嘴巴宽度, 嘴角
鼻子: 鼻子上下
眉毛: 眉毛角度, 眉毛高度
"""

write_text_data(text_data_name, GUIDE)

lines = [
    f"捏脸指南已写入文本块 {text_data_name}",
    f"文本编辑器 -> 文本块 {text_data_name} 查看",
]
message_box("\n".join(lines), title=TITLE)
