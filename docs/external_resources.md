# 外部资源与素材归属

范围: 跟随分发的第三方 / 游戏衍生内容里还没收尾的部分。许可详见 `THIRD_PARTY_NOTICES.md`, 插件来源与自研血统见
`docs/licenses.md`。

## 只有三类内容不能进 MIT 主仓库

| 内容 | 位置 | 体积 | 卡点 | 出路 / 公开版影响 |
|---|---|---|---|---|
| 官模模板 | `external_resources/kk_blend/` | 5.2MB | Illusion 游戏模型与贴图衍生。`official_template.blend` 被 3 个脚本硬引用 (`hitori_addon/template_link.py` 的 `TEMPLATE_BLEND`), 模板里的 `kk_arm` / `kk_leg` 是手工烘焙基准 (无代码引用, 不进任何场景) | 只能等"用户自备游戏资源 + 自研重建模板脚本" (中期工程)。删掉 -> 构建表情布局 / 贴合 / 追加官模头模眼线 失效 |
| u3d / 人物卡模板 | `external_resources/{u3d,card}/` | 1.5MB | 同上; 2 个 u3d 模板已用 SB3U GUI 的 LZMA 压缩 (16.0MB -> 1.4MB, 导出链路不受影响, SB3U 保存默认不压缩); 代码硬依赖 `template.py` 的 `TEMPLATE_CARD_PATH` / `U3D_TEMPLATE_DIR` | 删掉 -> 初始化 mod / 发布人物卡 失效 |
| 游戏数据小表 | `external_resources/data/` | 13KB | `kk_game_data.json`: 26 个脖颈顶点坐标 + 176 个形态键名 + 132 项表情名表 + KKLUT 17×3 曲线节点; 均为游戏数据衍生, 不含几何 / 贴图 / 权重 | 删掉 -> 头模初始化 / 形态键导出 / 贴图校色 失效 |

`external_resources/` 整目录 2026-10 已从仓库移除 (`.gitignore`, 本地磁盘保留), 打包成
`hitori-tools_external_resources_v<版本>.zip` (`python scripts/pack_external_resources.py`, 压缩包内的中英日 `README.txt` 唯一出处就在该脚本)
交给用户自己解压到项目根。`setup.bat` 的安装脚本强制检查它是否齐全, 缺文件就中止并打印放置路径;
插件侧 `const.require_external_resources` 会在用到模板时再查一次, 缺失就弹窗。

`official_template.blend` 里 12 处失效的 library weak reference 路径 (4 处本机 Desktop 模板路径 + 8 处
`//..\..\..\AppData\Local\Temp\copybuffer.blend`) 2026-10 已清空; 模板自带的 `Editing.act_imagedir`
(`//../../../../Desktop/`) 与 `RenderData.pic` (`/tmp\`) 两处旧路径也已清空 (后者改为 Blender 默认的 `//`),
文件大小与场景数据未变, 仅这两个字符串字段有改动 (见 `THIRD_PARTY_NOTICES.md` §6)。

其余都安全:

- `resources/template/zipmod/` 只剩自研内容 (`manifest.xml` 纯文本, `img/` 默认是空目录), 随 MIT 主仓库分发;
  缩略图 `img/thumb.png` 不入库 (`create_zipmod` 没有它时自动生成 256x256 文字缩略图;
  初始化 mod 时选默认的 "框选截取" 会把它写成 256x256 的正交投影图, 之后一直沿用);
  头模用的 `white.png` (纯白 MainTex) / `red.png` (纯红 ColorMask) 也在运行时生成, 生成头模时才打包, 不再入库;
  `bodymask.png` / `bramask.png` 已删除 (默认纯黄 = 不遮挡, 效果等同 CSV 里留 0)。
- `install_resources/` 的 pip 包 (10 个 / 10.9MB) 与 3 个 MIT Blender 插件 (6.5MB) 许可全宽松, 直接留主仓库。
- `install_resources/KoikatsuSunshine/BepInEx/plugins/**` 只剩自研 `HitoriGui.dll` + 2 个第三方插件 cfg。

## Blender 用户配置 (保留)

2 份 `.blend` (`config/` 下的 `startup.blend` + `userpref.blend`, 1.20MB) 都保留:

- `startup.blend` 是作者自己排的启动场景 (8 个中文工作区, 场景与视口设置和官模模板一致: EEVEE / 24fps / 1 帧 / 毫米 /
  Standard 色彩 / Cycles GPU 烘焙 / SOLID FLAT 光照 / 正交镜头), 保留则用户开箱即是这套布局;
  由 `python scripts/build_startup_blend.py` 从官模模板派生 (模板的物体 / 集合 / 网格 / 骨架 / 材质 / 文本块全删,
  界面与场景设置原样), 改了模板的设置后重跑该脚本即可; `Editing.act_imagedir` 与 `RenderData.pic`
  两处旧模板路径也已清空 (`pic` 改为 Blender 默认的 `//`);
- `userpref.blend` 保留是为了开箱即用 (省去自己调设置), `addons` 列表已去掉已删插件 (`better_fbx` / `setup_wizard` / `mmd_tools`) 的启用项;
  内存上限 8G, 自动保存 5 分钟;
- 默认禁用的三个插件 (`VRM_Addon_for_Blender-release` / `rigify` / `io_scene_psk_psa`) 都可能往保存的 blend 里写垃圾数据
  (VRM 把整份 glTF 数据挂到场景 / 骨架 / 骨骼 / 材质上, 官模模板里曾占 10.9MB), 因此默认关闭;
  VRM 由 `hitori_addon/importer.py` 的 `import_vrm` 临时启用 (`addon_utils.enable` 不写偏好设置) 并在导入后调
  `strip_vrm_extension` 清掉这些属性; `psk`/`psa` (UE 模型) 与 `rigify` 需要时手动在偏好设置里启用即可;
- 隐私: 个人路径 / recent / bookmark 存在单独的 `config/*.txt`, 这三份**没有入库**, 安装脚本只复制 `resources/` 里已有的文件;
- 许可: 这两个 `.blend` 是作者用 Blender 自己保存的产物 (场景 / 界面数据), 属程序输出, 放 MIT 仓库没有许可问题
  (见 `THIRD_PARTY_NOTICES.md` §6)。

`ViewModel` 应用模板 (`config/ViewModel/` 与 `scripts/startup/bl_app_templates_user/ViewModel/`, 4 份 `.blend` / 1.99MB)
2026-10 已删: 只有 `scripts/view_model.bat` 的 `--app-template ViewModel` 用它, 而导入外部模型现在只走菜单按钮
(`addon_scripts/import_external_model.py`, 用当前 userpref, 不换场景)。`scripts/view_model.py` 本体留着, 按钮靠它导入。

## KKLUT 校色: 已改可分离曲线, 数值已移到外部资源

原 `KKLUT.cube` (7.0MB) 已从仓库与本机 Blender 删除, 本机 `config.ocio` 的 KKLUT look 段也一并清除。
`hitori_addon/image.py` 改用 numpy 可分离曲线直接作用于 `img.pixels` (实测已加载 sRGB 图片的 `img.pixels` 就是 sRGB 值,
Standard / 无 look 时 `save_render` 逐像素恒等, 不需要线性空间转换), 存盘仍走原 `img_save_render`;
17×3 节点值从 `external_resources/data/kk_game_data.json` 读取, 主仓库不再内嵌。

| 对拍 (300x200 渐变 + 8x8 极色角点) | 结果 |
|---|---|
| numpy + 完整 3D LUT vs 旧 look | max 1/255, 平均 0.000, 100% 像素相同 (新落地方式与旧链路等价) |
| 内置 17 节点/通道曲线 vs 旧 look | 普通图 max 19 / 平均 2.6; 灰度 max 6; 极色角点 max 35 (可分曲线的固有偏差) |
| 1024² RGB 单张 | 旧 152ms -> 新 217ms (曲线查表约 50ms) |

剩余 (**可选, 后续再决定**): 17 个节点值目前是从原 64³ LUT 的通道均值曲线抽的 (**①a, 数值上仍是衍生数据**),
要彻底干净可按游戏里贴图的实际观感重定这 17×3 的小表 (**①b**) —— 校色数据只有这一张表, 改起来是纯数值替换。
