# 项目

把 Blender 3.6 + 一批特定版本的插件 / 工具 / 资源打包成能一键安装的 KKS mod 制作工具链:

- `setup.bat` 输入 (或回车沿用上次的) blender.exe 路径, 找到 Blender 3.6 自带的 python;
- 再跑 `install/init_addon_config.py`, 把 `install_resources/` 里的插件 / pip 包 / 第三方 addon 复制进 Blender,
  并把 `resources/` 的路径写进 `hitori_addon/hitori_addon_config.json` (随插件复制进 Blender);
  `resources/` (mod 模板) 与 `external_resources/` (游戏衍生模板与数据表, 由 `project` 推出) 都是原地使用不复制,
  改 `resources/template/zipmod/manifest.xml` 或 `img/thumb.png` 立刻生效;
- 之后在 Blender 的 N 面板里用菜单一步步做 mod (服装 / 饰品 / 人物卡 / 头模)。

其他文档: 编码规则 / 当前阶段 / 硬约束 / 验证见仓库根 `AGENTS.md`; 人物卡格式见 `docs/card_format.md`;
本机路径与开发工具见 `docs/environment.md`; 自动化现状见 `docs/automation.md`; 性能决策见 `docs/performance.md`;
第三方许可见 `THIRD_PARTY_NOTICES.md` 与 `docs/licenses.md`; 外部资源出库见 `docs/external_resources.md`。

## 外部依赖 (用户自备, 仓库不随分发)

| 依赖 | 用途 | 说明 |
|---|---|---|
| `mmd_tools` (推荐 2.8.0, GPL-3.0) | pmx 模型导入 | 不在仓库; `import_pmx` 用时懒检查, 缺失就弹窗请用户自己安装并启用 |
| SB3Utility (推荐 v22.4.1, 无许可声明) | `addon_scripts/fbx_to_u3d.py` 调外部 exe 替换 u3d | 安装脚本询问路径并校验 `SB3UtilityScript.exe`, 存进 `hitori_addon_config.json` 的 `sb3u` 项 |

## 仓库状态

- 公开仓库是全新快照 (首次提交): 旧的本地开发历史含本机路径, 不沿用。
- 公开分发: 主仓库 MIT; `external_resources/` 已出库, 另行打包成带版本号的 zip。

## 已知取舍

- 初版保留旧菜单的标识方式: 非脚本按钮的 identifier 都是 `该按钮仅用于标识无法运行!`。
- `setup.bat` 只负责找到 Blender 并调起初始化脚本, 参数推断都在 python 侧。
- 安装是覆盖式复制: 只覆盖同名文件, 不删除目标里多余的文件, 失败不回滚。
- 插件热更新: 写完 u3d 的脚本调用 `hitori_addon/hotreload.py` 重建 zipmod (热重载期间不压缩, 发布前压回 deflate),
  再经端口 14145 通知游戏清缓存 (自研 `HitoriGui` 监听)。
- 开发热重载: `hitori_addon_config.json` 里写了 `"hotreload": "true"` 时, 每次点菜单按钮前比对
  `hitori_addon/**/*.py` 的 mtime + 大小, 变了就把整个包从 `sys.modules` 移除并重新 import (见
  `hitori_addon/autoreload.py`)。`hitori_addon_ui` (菜单) 不重载, 改菜单仍需重跑 `setup.bat`,
  菜单里 `from hitori_addon.* import` 来的成员要登到 `autoreload.UI_REBINDS`, 否则重载后仍指向旧模块;
  重跑 `setup.bat` 不会清掉这个手写的键。默认关闭, 每次检查约 0.5ms。
- 脚本出错: `ObjectError` / `OSError` / `ValueError`(`error.REPORTED_ERROR_TYPES`)是用户能看懂的错,
  在按钮里统一弹 `message_box` 报, 不打 traceback (`menu.report_errors` 装饰 operator 的 `execute`,
  模块级脚本由 `hitori_addon_ui` 的 `run_button` 兜底); 子脚本与无头导出照旧抛给调用方拿退出码。
- 导出走常驻无头子进程 (端口 14147), 机制与耗时见 `docs/performance.md`。
