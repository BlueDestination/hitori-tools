# 许可与来源

主仓库挂 MIT 的两份依据: ①随仓库分发的第三方组件都有明确宽松许可 (汇总在 `THIRD_PARTY_NOTICES.md`);
②自研代码里没有从 GPL 项目搬运的片段 (本文的"血统审计")。

判定口径:

- **主仓库**: 自研, 可挂 MIT。
- **可公开**: 上游有明确宽松许可, 可随公开仓库分发 (需附版权与许可声明)。
- **私有**: 无许可声明或来源不明, 不能公开 (含 GPL / LGPL: 合法但会给 MIT 仓库带来再分发义务, 本仓库选择不带)。

## 随仓库分发的 BepInEx 插件: 只有 1 个自研

位置 `install_resources/KoikatsuSunshine/BepInEx/plugins/@MyPlugins/hitori_plugin/`, 只留 `core/`:

| 文件 | FileVersion | 来源 | 许可 |
|---|---|---|---|
| `core/HitoriGui.dll` | 1.5.1 | 自研 (`hitori_gui/`) | MIT |

- `HitoriGui` 自己实现读卡热重载: socket 监听 (14145) 收 `ReadCard` / `ClearCacheReadCard` / `ClearCache` / `ClearCacheOne`,
  再反射 Sideloader 的 `Zipmods` 逐个 `ZipmodInfo.Dispose()` 放掉 zipmod 句柄, 让 Blender 侧替换得了 zipmod。
  清缓存只在主线程执行 (监听线程只置 `_pendingClear`); 捏人面板另有 "Release Mods" 按钮做全量释放。
- 定向释放 `ClearCacheOne <zipmod全路径>` 只卸这一个 mod 的 AssetBundle 并只关它自己的句柄 (全量要卸 195 个 bundle / 127ms,
  定向只卸 1 个 / 3ms); 路径匹配不上时自动退全量。

### 自研替换的 2 个, 与删除的 3 个自修改 DLL

- `DragAndDrop` (GPL-3.0) / `FPSCounter` (Apache-2.0) 的热重载相关功能 (读卡 / 14145 监听) 已由 `HitoriGui` 重写;
  游戏里**上游原版仍在** (`plugins/DragAndDrop.KoikatsuSunshine.dll`、`plugins/@MyPlugins/Misc/FPSCounter.dll`), 拖拽读卡与 FPS 面板不受影响。
- 原 `licensed/` 的 3 个自修改 DLL (`KKS_Sideloader` 20.0 -> 99.1、`RuntimeUnityEditor` ×2) 已删除:
  它们改自上游且版本号更高, 一直覆盖游戏里更新的原版 (Sideloader 回退到带 `GetPng` NRE 的 19.1 base), 又背 copyleft 义务。
  删除后游戏回退到上游 `KKS_BepisPlugins` 20.0 与 `RuntimeUnityEditor` 4.2, zipmod 句柄释放由 `HitoriGui` 接手。
- 10 个开发 / 捏脸辅助插件 2026-10 已移出仓库 (本机 `@MyPlugins/develop_plugin/`), 安装脚本改为打印推荐清单
  (`install/init_addon_config.py` 的 `RECOMMENDED_PLUGINS`); 其中 5 个无许可 (ExpressionControl / HCtrl / HeadUtl /
  KeyboardShortcuts / MakerCameraPresets), 如果以后要随安装包或整合包分发, 仍需先拿授权或换带许可替代品 (PerspectiveX / KK_PovX / RealPoV)。

**BepInEx 的版本号规则** (删插件前必读): 同名插件在多个目录各有一份 DLL 时按程序集版本号取最高的加载, 不看目录顺序;
删掉"高版本自修改 DLL"后游戏会自动回退加载低版本原版, 插件并没有真的消失。所以不能因为"仓库里没有这个插件了"就清
`BepInEx/config/<guid>.cfg` (如 `MarC0.FPSCounter.cfg`、`keelhauled.draganddrop.cfg` 仍被回退的原版使用),
也不要照仓库清单去删游戏目录。

## 第三方工具: SB3Utility 由用户自备

`resources/tools/SB3Utility` (23.0.3, ~33MB, 含 Autodesk FBX SDK / FMOD) 2026-10 已整目录删除: **上游没有任何许可声明,
按保留所有权利处理**, 不能随公开仓库分发。`addon_scripts/fbx_to_u3d.py` 只把 SB3U 当外部 exe 调用, 所以安装时询问用户自己的路径
(存进 `hitori_addon_config.json` 的 `sb3u`), 推荐 v22.4.1。

调查结论 (2026-10, 复现方法见文末):

| 来源 | 版本 | 结论 |
|---|---|---|
| 本仓库 `resources/tools/SB3Utility` (已删) | 23.0.3 | DLL / exe / chm 里搜不到 license / GPL / MIT |
| `enimaroah/SB3Utility`、`kkdevs/sb3u`、`HF-Alamar/SB3Utility` | 1.x / 1.12 | 无 LICENSE / COPYING / NOTICE, 文件头只有 `using`, `AssemblyInfo.cs` 只有 `Copyright © 2012` |
| Gitee `heng32032/SB3Utility` (镜像) | 1.0.x | 页面直接显示 `License: Not specified` |
| gitgud.io / gitea.com 旧发布位 | — | 前者匿名访问被重定向到登录页, 后者账号与仓库已 404 (改名重定向表里也没有) |
| `enimaroah-cubic/Sb3UGS` (接手的继续维护版) | 26.2.1 (2026-09) | release 带源码, 包里仍无 LICENSE, 命中许可字样的都是第三方依赖 |

结论: 属于 "源码可下但未授权" (source-available != open source); 要随仓库分发得先联系作者。

## 自研代码血统审计

目的: 确认 `hitori_addon/` / `addon_scripts/` / `hitori_gui/` / `scripts/` / `install/` 里没有从 GPL 项目直接搬运的片段。

方法: ①逐文件通读重点模块 (`u3d.py` / `mesh.py` / `bonenames.py` / `card.py` / `template.py` / `arm.py` 与较大的 `addon_scripts/*`);
②机器逐行比对: 取长度 >= 30 的非中文代码行 (2508 个去重候选), 与 `resources/**/*.py` (770 个文件, 含当时的 GPL `mmd_tools`)
及上游 CATS (`cats-blender-plugin`, GPL, 117 个 `.py`) 逐行匹配;
③英文注释 / docstring 单独列出做人工溯源; ④C# 侧逐方法核对 `HitoriGui.cs` 调用的游戏 API 与上游同名插件, 确认没沿用其代码。

结果: 与 CATS 相同行数 **0**; 与 `resources` 里的 GPL addon 命中的全是 `import ...` / `bpy.ops.mesh.select_all(action='...')`
这类 Blender API 通用惯用法, 没有成片段的相同代码。只有 2 处第三方来源, 均已重写:

| 位置 | 来源 | 处理 |
|---|---|---|
| `hitori_addon/image.py` 的 `get_img_min_alpha` (2 行注释 + 2 行 numpy 惯用法) | Blender 官方模板 `scripts/templates_py/image_processing.py` (GPL-2.0-or-later) | 已重写: `np.empty` + `foreach_get` + 一维切片 `[3::4]` 取 alpha, 行为不变 |
| `HitoriGui.cs` 的 `ClearModCache` (整段反射结构与调用序列) | `RuntimeUnityEditor.Core` 的 `AssetBundleManagerHelper.ClearAssetBundleCache` (GPL-3.0) | 已重写: 直接调游戏公开的 `AssetBundleManager` / `BundlePack.LoadedAssetBundles` / `UnloadAssetBundle`, 去掉全部反射 |

容易被怀疑但确认自研的项:

| 内容 | 说明 |
|---|---|
| `hitori_addon/bonenames.py` | 纯 VRC / MMD / KK 骨骼名数据, 无逻辑 |
| `hitori_addon/msgpack.py` | 自研极简 msgpack 编解码 (不是 msgpack-python / Cython) |
| `hitori_addon/card.py` | 自研人物卡二进制改写 (KSOX / Material Editor / Sideloader 解析信息) |
| `hitori_addon/u3d.py`, `mesh.py` | UnityPy 封装 + 网格工具 |
| `hitori_addon/sb3u.py`, `addon_scripts/fbx_to_u3d.py` | 只生成 SB3U 脚本字符串并调外部 exe, 未用 SB3U 源码 (C#) |
| `hitori_addon/headmod.py` | 只留表情类型常量; 头模坐标 / 形态键 / 表情名与 KKLUT 曲线已移到 `external_resources/data/kk_game_data.json`, 见 `THIRD_PARTY_NOTICES.md` §5 |
| `HitoriGui.cs` 的读卡热重载 / `SHFileOperation` P/Invoke | 只调游戏公开 API 与 Win32 公共声明, 未沿用上游插件代码 |

未决 / 说明: 机器比对只覆盖 `resources` 与 CATS; SB3U (C#) 与各类 KK 卡工具的源码未逐一比对, 但 Python 侧已人工通读,
C# 侧只有自研 `HitoriGui.cs`。结论: 自研代码可整体挂 MIT。

## 依据与复现方法

- 元数据: PowerShell `[System.Diagnostics.FileVersionInfo]::GetVersionInfo()` 取 FileVersion / ProductVersion;
  `Assembly.LoadFile()` + `GetCustomAttributesData()` 取 Company / Product / Copyright; `pefile` 取 PDB 名。
- 与上游二进制比对: 以安装目录里其它位置的同名原版 DLL 为基准, 比 sha1 与模块 MVID (PE 元数据 `#GUID` 堆)。
- 上游许可查证: `gh api repos/<owner>/<repo> -q .license.spdx_id`; `Frostation/KK-Plugins-Compendium` (插件作者与来源);
  `ManlyMarco/KKS-HF_Patch` 的 `components.iss` (官方整合收录情况)。
- 依赖关系: 直接读 DLL 字节里目标程序集名出现的次数 (程序集引用会写进 PE 的 `#Strings` 堆)。
- `BepInEx/config/<GUID>.cfg` 头部的 `## Plugin GUID: ...` 与插件版本是判断来源的强指纹。
- 注意 AssemblyVersion 与 FileVersion 不一致属作者设置 (如 `KKS_OrthographicCamera` 的 `9.1.2.0` vs `1.1.2`), 不代表文件被改过。
