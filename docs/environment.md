# 开发环境

实际路径以 `hitori_addon/hitori_addon_config.json` 为准 (安装脚本写入, 随插件复制进 Blender)。
下表是作者本机的示例路径 (2026-10), 换成自己的目录即可。

| 用途 | 示例路径 |
|---|---|
| 项目 (本仓库) | `C:\Users\<用户名>\BlenderProject` |
| 资源 (随安装包分发) | `C:\Users\<用户名>\BlenderProject\resources` |
| 游戏导出的模板 (u3d / 人物卡; 由 `project` 推出; 已出库) | `C:\Users\<用户名>\BlenderProject\external_resources` |
| Blender 3.6 (便携版) | `C:\Users\<用户名>\Desktop\Blender` |
| Koikatsu Sunshine | `C:\Games\KoikatsuSunshine` |
| 游戏 mods 输出 | `C:\Games\KoikatsuSunshine\mods\MyMods\@MyMod` |
| 本地输出 | `C:\Users\<用户名>\BlenderProject\output\{abdata, desktop, release, shapekey_screenshot}` |
| SB3U (用户自备) | `C:\Games\KoikatsuSunshine\[MODDING] Tools\SB3Utility v22.4.1` |

## 开发工具 (仅本机, 不随分发)

| 工具 | 版本 / 来源 | 用途 |
|---|---|---|
| fake-bpy-module | `fake-bpy-module-3.6` (nutti/fake-bpy-module, `pyproject.toml` 的 `dev` 依赖组, `uv sync` 装进 `.venv`) | 外部编辑器 (VSCode / PyCharm) 的 `bpy` / `bmesh` / `mathutils` 补全, 只在写代码时用 |

- 只装进本机的外部编辑器环境, **不要**复制进 `install_resources/` 或任何随仓库分发的目录:
  生成的 stub 里有约 1.6 万条 docstring 是 Blender RNA 描述的逐字原文 (来自 GPL-2.0-or-later 源码), 仓库约定不留 GPL 衍生内容。
  函数签名 / 枚举值 / 类型标注是接口事实, 不构成复制风险。生成器本身 (nutti/fake-bpy-module) 是 MIT。

## 需要备份的目录 (按更新频率)

- 不常更新 (kk 插件, blender 资源):
  - `<KKS>\BepInEx\plugins\@MyPlugins\hitori_plugin`
  - `<项目>\resources`
  - `<项目>\external_resources`
- 更新频率适中 (blender 软件 / 配置 / 插件, 已整合进 `install_resources/`, 体积大可用增量备份): `<Blender>`
- 更新频繁 (插件项目脚本代码): `<项目>`
