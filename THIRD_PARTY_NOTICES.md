# 第三方组件与许可 (THIRD_PARTY_NOTICES)

本项目的自研代码 (`hitori_addon/` / `hitori_addon_ui/` / `addon_scripts/` / `scripts/` / `install/` / `hitori_gui/` 等) 以 MIT 发布 (见 `LICENSE`, 版权人 Hitori)。下面列出随项目一起分发的第三方组件、它们的许可与上游。

拆分后的两个仓库 (2026-10 已收口):

- **主仓库**: 自研代码, MIT; `resources/template/zipmod/` (模板文本 `manifest.xml`) 2026-10 逐个确认也是自研, 决定不再拆独立仓库, 直接随主仓库分发。
- **外部资源包** (只剩 `external_resources/`): 游戏衍生素材 (`external_resources/` 的 `kk_blend/` 模板 / u3d / 人物卡); `external_resources/` 2026-10 已从主仓库移除 (`.gitignore`, 本地保留) 并单独打包成 `hitori-tools_external_resources_v<版本>.zip` (`scripts/pack_external_resources.py`, 压缩包内含中英日说明) 由用户自己解压, 安装脚本与插件都会强制检查; 宽松许可的 Blender 配置 / Python 依赖 / 第三方插件 2026-10 已从 `resources/` 移出, 放仓库根 `install_resources/`, 随主仓库分发。

约定: "可公开" = 上游有明确宽松许可, 可随任一仓库分发 (需附上版权与许可声明); "受限" = 无许可 / 专有 / 游戏衍生, 只能留在外部资源包。

## 1. Python 依赖

位置: `install_resources/Blender/3.6/scripts/addons/modules/` (10 个包, 约 11MB)。每个包的 `*.dist-info/` 里都带完整许可文本。
这里只列**实际留着**的包; 2026-10 已经剪掉 9 个没有任何代码路径会用到的包 (pytest 全家 / send2trash / pyfmodex), 之后又删掉已无人引用的 `watchdog`。
许可复查: 这 453 个文件逐个与各包 `RECORD` 里的 sha256 比对, **0 差异** (全是上游 wheel 原文, 没有手工增补或改过的文件); 少掉的只有 `fmod.dll` 与用不上的 CPU 变体 `.pyd` 等上游文件。

| 许可 | 包 |
|---|---|
| MIT | astc-encoder-py 0.1.11, attrs 24.3.0, Brotli 1.1.0, etcpak 0.9.13, texture2ddecoder 1.0.4, UnityPy 1.20.16 |
| BSD-3-Clause | fsspec 2024.12.0, lz4 4.3.3 |
| MIT-CMU (HPND) | Pillow 11.0.0 |
| Apache-2.0 OR MIT | archspec 0.2.5 |

- UnityPy 里原本还捆着 `UnityPy/lib/FMOD/Windows/{x64,x86}/fmod.dll` (© Firelight Technologies Pty Ltd, **专有**音乐库, 不在这条 MIT 许可里)。
  2026-10 已把这 2 个 dll **删除**, 只留 `__init__.py` 目录骨架: 本项目只用 UnityPy 读写 u3d, 从不走 `UnityPy/export/AudioClipConverter.py`;
  删后真机整条 u3d 路径 (解析 11313 对象 / 解贴图 4 张 / 压贴图 4 种 / 存盘 56,606,855 bytes) 全 PASS, 且全程 `pyfmodex` 为 None、没设置 `PYFMODEX_DLL_PATH`。
- 包装 FMOD 的 `pyfmodex` 更早就按"用不到"删掉了。以后真要转音频: 从 UnityPy 官方 wheel 拿回 `lib/FMOD/Windows/x64/fmod.dll` + `pip install pyfmodex`, 把 FMOD 当可选依赖 (商用需 Firelight 授权)。
- 这 11MB 2026-10 决定**直接留主仓库**随 MIT 代码树分发, 不再改成 `requirements.txt` + 安装时 pip (省掉联网 / 版本漂移)。

## 2. Blender 插件

位置: `install_resources/Blender/3.6/scripts/addons_contrib/`

| 插件 | 版本 | 许可 | 上游 (本地副本对应的提交) |
|---|---|---|---|
| VRM Add-on for Blender | 2.20.38 | MIT (含 MToon 附加组件 MIT) | 老仓库 `iCyP/VRM_Addon_for_Blender` (已注销), 上游现为 `saturday06/VRM-Addon-for-Blender` |
| Abnormal | 1.1.2 | MIT | `BlenderNPR/Abnormal` 提交 `2afd9c5b` |
| io_scene_psk_psa | 6.1.2 | MIT | `DarklightGames/io_scene_psk_psa` tag `6.1.1` (最接近), 该仓库 `7.1.0` 起才改成 GPL |
| ~~mmd_tools~~ | 2.8.0 | GPL-3.0 | 2026-10 已整个删除, 仓库不再随分发 GPL 插件; 来源 `UuuNyaa/blender_mmd_tools` 提交 `3655ee85` |
| ~~better_fbx~~ (Better FBX Importer & Exporter) | 5.4.1 | **商业** | 2026-10 已整个删除: python 部分头声明 GPL-2+ 但 `bin/Windows/x64/fbx-utility.exe` 专有, 来源 `mesh-online.net/fbx.html` |

- MIT 的三个都自带许可原文 (VRM 另有 `LICENSE.MToon`); `io_scene_psk_psa` 的 `LICENSE` (© 2019 Darklight Games) 也已补。
- `mmd_tools` (GPL-3.0) 再分发要求保留上游 `LICENSE`; 既然不再随分发, 2026-10 把整个 GPL 资源树 `resources/install_resources_gpl/` 删掉,
  改为用到 pmx 时懒检查 (`hitori_addon/importer.py` 的 `require_mmd_tools`), 缺失就弹窗请用户自己安装并启用 (推荐 2.8.0)。

## 3. 第三方工具

2026-10 已把仓库里唯一随附的工具 `resources/tools/SB3Utility` (23.0.3) 整目录删除: 它没有任何许可声明 (上游全镜像都没有
LICENSE, 调查见 `docs/licenses.md` 的 SB3U 一节), 不能随公开仓库分发。`addon_scripts/fbx_to_u3d.py` 只把 SB3U 当外部 exe
调用, 所以改为安装时询问用户自己的 SB3U 路径 (存进 `hitori_addon_config.json` 的 `sb3u` 项), 由用户自备 (推荐 v22.4.1)。

原目录里随 SB3U 一起的组件也一并离库 (以下仅存档, 均不再分发):

| 组件 | 许可 | 说明 |
|---|---|---|
| Autodesk FBX SDK `libfbxsdk.dll` | 专有 | © 2019 Autodesk |
| `fmod64.dll` | 专有 | FMOD, © Firelight Technologies |
| 微软运行时 (`api-ms-win-*.dll` / `ucrtbase` / `msvcp100` / `msvcr100` / `vcruntime140` / `System.ValueTuple` / `System.Threading.Tasks.Extensions`) | 微软专有 | 随程序再分发允许 (非开源) |
| SlimDX / WeifenLuo.WinFormsUI.Docking / LZ4 / MessagePack / `niflib_x64` / mikktspace | MIT / BSD / zlib 风格 | 宽松许可的 .NET 依赖 |
| `Jolt.dll` / `Jolt.Testing.GeneratedTypes.dll` / `SyntaxHighlightingTextBox.dll` | 来源不明 | 原项目已停, 找不到许可 |
| Bandizip | — | 已在第 2 步删除 (改用 Python `zipfile`), 不再分发 |

## 4. BepInEx 插件 (@MyPlugins)

位置: `install_resources/KoikatsuSunshine/BepInEx/plugins/@MyPlugins/hitori_plugin/`。
逐个插件 (来源 / 许可 / 是否自修改版) 见 `docs/licenses.md`。

| 类别 | 数量 | 再分发要求 |
|---|---|---|
| 自研 `core/HitoriGui.dll` | 1 | MIT |

2026-10 从仓库移出了 10 个开发 / 捏脸辅助插件 (4 个 GPL 插件 + `LitJSON` + 5 个无许可插件), 本机改放
`@MyPlugins/develop_plugin/`, 不再随仓库分发; 同月 `DragAndDrop` (GPL-3.0) 与 `FPSCounter` (Apache-2.0) 的热重载相关功能
改由自研 `HitoriGui` 重写, 这两个插件的自修改版从仓库与游戏删除 (游戏里原有的上游原版保留)。
另外原 `licensed/` 的 3 个自修改 DLL (GPL-3.0 的 `RuntimeUnityEditor` ×2 + LGPL-3.0 的 `KKS_Sideloader`) 也一并删除:
它们改自上游且版本号更高, 一直覆盖着游戏里更新的上游原版 (Sideloader 尤其回退到 19.1 base), 携带再分发义务, 而功能要么没人用、要么已由
`HitoriGui` 反射 `ZipmodInfo.Dispose()` 接管; 删除后游戏回退到上游 `KKS_BepisPlugins` (20.0) 与 `RuntimeUnityEditor` (4.2)。
所以仓库现在没有随分发的 GPL / LGPL BepInEx 组件。详见 `docs/licenses.md`。

## 5. 游戏衍生 / 第三方素材 (资源受限)

| 内容 | 位置 | 原因 |
|---|---|---|
| 官模模板 / 贴图 | `external_resources/kk_blend/` | 游戏模型与贴图衍生 |
| 游戏导出的 u3d / 人物卡 | `external_resources/{u3d,card}/` | 游戏模型与贴图衍生 |
| 脖颈坐标 / 形态键名 / 表情名 / KKLUT 曲线 | `external_resources/data/` | 游戏数据衍生, 只有数值与名称 |
| zipmod 模板的 img / manifest.xml | `resources/template/zipmod/` | `manifest.xml` 为自研纯文本; `img/` 已不再入库任何图片: 缩略图 `thumb.png` 由用户自行放置 (缺失时自动生成), 头模的 `white.png` / `red.png` 由代码生成, 只在使用头模时打包 |

这些游戏数据衍生已移到 `external_resources/data/kk_game_data.json` (不随 MIT 主仓库分发): 26 个脖颈顶点坐标 (78 个数)
+ 176 个形态键名 + 132 项表情名表 + KKLUT 17×3 曲线节点, 共约 13KB, 没有几何文件 / 贴图 / 骨骼权重。
这些数据不属于 MIT 许可范围, 仅为兼容性目的随外部资源包提供, 相关权利归原游戏权利人。

## 6. 不在仓库里

Blender 本体 (GPL-2.0-or-later) 只复制配置, 二进制没进仓库; Koikatsu Sunshine 游戏文件、`output/` 产物都不入库; SB3Utility 由用户自备 (见 §3)。

`install_resources/.../Blender/3.6/config/` 里的 `startup.blend` / `userpref.blend` 是作者用 Blender 自己保存的场景 / 界面数据, 属程序输出:
GPL 只在其内容本身构成受保护作品时才覆盖输出 (GPLv2 §0 / GPLv3 §2 的 output 条款), 这两个文件不受 GPL 约束, 已在仓库内随主仓库分发。

## 许可收口 (2026-10)

主仓库 `LICENSE` (MIT) 已补; GPL / LGPL 组件已全部移出或删除, Autodesk / FMOD 等二进制随 SB3U 离库, 都不再需要补许可全文;
拆分前记的"补 `resources/**` 许可说明"也已收口:

- `resources/template/zipmod/` 逐项确认是自研 (`manifest.xml` 纯文本; 原先 4 张单色占位图已改成运行时生成), 随 MIT 主仓库分发, 不需要额外许可说明;
- 游戏衍生素材都在 `external_resources/` (不随仓库分发), 版权归属与用途写在外部资源包里的中英日说明文件 (§5);
- 逐项位置 / 动作见 `docs/external_resources.md`;
- 头模 / KKLUT 的游戏数据已挪进 `external_resources/data/kk_game_data.json`, 按 §5 披露; 主仓库代码只留加载逻辑, 不再内嵌数值;
- `pyproject.toml` 补 `license = { text = "MIT" }`;
- 随仓库分发的 `install_resources/.../config/userpref.blend` 里作者本机的 `filepaths.image_editor` 路径已清空, Cycles 设备缓存里的 CPU / GPU 型号与设备 ID 已改成通用名称 (其余偏好逐项比对未变)。
- `external_resources/kk_blend/official_template.blend` 里 12 处失效的 library weak reference 路径 (4 处本机 Desktop 模板 + 8 处 `copybuffer.blend` 临时路径), 以及 `Editing.act_imagedir` / `RenderData.pic` 两处旧模板路径, 已清空 (`pic` 改为 Blender 默认的 `//`); 文件大小与场景数据逐项比对未变, 仅这两个字符串字段有改动。
- 随仓库分发的 `startup.blend` 里继承的上述两处旧路径也已一并清空, 数据块与模板保持一致。
