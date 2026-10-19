# hitori-tools 开发规则 (给编码助手)

项目背景见 `docs/project.md`, 人物卡格式见 `docs/card_format.md`, 其余文档索引在 `docs/project.md` 开头。
本文是唯一的编码规则源, 动手前先读一遍。

## 当前阶段: 功能迭代

- 初版已经发布, 用户已在自己机器上完整跑通 `setup.bat`; 现在要装得上 + 用得了, 也可以改原有逻辑与已有行为。
- 用户说"只是介绍 / 先别改"时, 立刻还原改动, 只做讲解。
- 死代码 / 旧代码 / 过时注释可以指出, 但只列出来等你点头, 不顺手删。
- 改完把可选的后续项列出来等用户点头, 不顺手扩大改动范围, 不要改错文件。
- 所有要用户输入的提示都要支持"直接回车用上次的值 / 示例路径", 且提示不能撒谎 (没有默认值就写"必须输入")。
- 公开后新用户直接装最新版: 不需要为"老用户升级"做向后兼容 / 清理改动 (例如安装脚本主动删旧插件)。

## 硬性约束

1. `resources/**` 与 `install_resources/**` 字节保真: `.gitattributes` 里都标了 `-text`, 任何整理都不能让它们被 CRLF/LF 归一化。改名用"先改 .gitattributes -> 同卷 mv -> git add -A", 改完按 blob sha1 逐文件比对。`external_resources/**` 同理, 但它 2026-10 已出库 (见 `.gitignore`, 本地磁盘保留, 发布时用 `scripts/pack_external_resources.py` 打包成带版本号的 zip)。
2. `setup.bat` 必须是 GBK(cp936) + CRLF + 无 BOM, 改它要用字节级替换: `assert count == 1`, 再断言没有孤立 LF。
3. 移动 / 改名目录要一起改: `.gitattributes`, 代码引用, `docs/`, 示例路径, `hitori_addon_config.json` 里的路径 (重跑 `setup.bat`; 悬空路径会让插件一打开就报错)。
4. `hitori_addon_ui/` 的改动必须重跑 `setup.bat` 才会进 Blender; `hitori_addon/` 的改动不需要 (改了配置项名要重跑安装)。
5. `hitori_gui/` (游戏内自研插件) 的改动: `python hitori_gui/build.py` 只把新 DLL 复制进 `install_resources/` (入库); 还要把该 DLL 拷进游戏 `BepInEx/plugins/@MyPlugins/hitori_plugin/core/HitoriGui.dll` (或重跑 `setup.bat`), 否则游戏里跑的还是旧版 (游戏运行中 DLL 会被占用, 先关游戏)。
6. 不把 `output/`, `*.log`, `__pycache__` 等产物入库, 提交前扫一遍隐私信息。
7. 发布时按全新快照新建公开仓库 (旧历史含本机路径, 不沿用); 提交信息沿用现有风格 (英文短句)。

## 验证要求

- 每个改动都要有可复现的证据, 把结论先摆出来; 提交后工作区保持干净。
- 改完跑 `ruff check`(配置在 `pyproject.toml`, 已排除 `install_resources` / `resources` / `external_resources` / `*.md`); 提交前必须是 `All checks passed!`, 不能为了过检查去改第三方资源。
- 不用主动跑 `ruff format`: 格式化不影响安全性, 只在明确要求时执行, 以免拖慢开发。
- 能用真机就跑真机: `<Blender>/blender.exe -b --factory-startup --python <脚本>`。
- Blender 的 UI 枚举要走 `bpy.ops.<idname>.get_rna_type()`, 从 `bl_rna.properties` 取不到自定义属性。
- 测试脚手架放 `%TEMP%`, 不进仓库; 运行必须带 timeout, 不能卡住。`%TEMP%` 下的临时文件 (脚手架 / 调试产物 / 备份) 不用问用户删不删, 按需留或自己清。
- 测试不要真写用户的 `hitori_addon_config.json` (用临时目录 + 替身脚本; 可 `hitori_addon.config.set_config_path()` 指向临时文件)。
- 不要在 bash heredoc 里写含 Windows 路径 / 引号 / `%` 的脚本, 先用 write 落成文件再执行; 中文输出交给 python 并加 `PYTHONIOENCODING=utf-8`。

## 性能

- 批量读写 Blender 数据 (坐标 / 法线 / 面中心 / 边 / 缝合边) 用 `foreach_get` / `foreach_set` + numpy,
  不写逐元素列表推导 (实测 bodytight 21133 条边的缝合边映射 46.8ms -> 8.3ms, 结果逐位一致)。
- 导出链路的耗时实测与已判定不做的优化 (SB3U / UnityPy) 见 `docs/performance.md`, 改前先读。

## 工具使用

- 不要在项目里跑 `grep` / `find` 递归全库搜索: 文件太多, 慢且容易卡死。
  要定位内容就列明确目录 (`ls`), 或用 `git` / `python` 定向读取单个文件。或者用 `rg` / `fd` 会更快。

## BepInEx 插件

- 同一个插件在多个目录各有一份 DLL 时, BepInEx 按 DLL 里的程序集版本号取最高的加载, 不看目录顺序。
- 自修改的 DLL 常被抬高版本号来盖过官方原版; 删掉这些"高版本自修改 DLL"后, 游戏里原有的低版本插件会被 BepInEx 自动接管, 插件并没有真的从游戏消失。
  所以不能因为"仓库里没有这个插件了"就顺手清 `BepInEx/config/<guid>.cfg`: 配置可能仍被回退加载的原版使用 (如 `MarC0.FPSCounter.cfg`、`keelhauled.draganddrop.cfg`)。
- 仓库 `plugins/@MyPlugins/hitori_plugin/` 只登记自研 / 可再分发的那部分; 游戏里还可能有本仓库不记录的官方原版插件, 不要照仓库清单去删游戏目录, 也不要按"仓库删除"推断游戏里已删除。

## 调试用户正在运行的 Blender 进程

- **只读探查随时可用**, 不必等用户开口 (看数据、算尺寸、验行为都行); 但任何会改数据 / 要调 `bpy.ops` 的操作必须用户明确要求, 否则自己起后台 Blender (`-b --factory-startup --python <脚本>`) 或把脚本交给用户跑。
- 机制: `hitori_addon/debugger.py` 在进程内起 TCP 监听 `127.0.0.1:61001`, 收到代码就 exec 并回传 stdout; 外部用 `hitori_addon/debug.py` 的 `send_code` 或裸 socket 发。
  起监听要用户手动一次 (文本编辑器 -> 文本块 `debugger_script` -> Alt+P), 外部没法注入; 查是否在听: `netstat -ano | findstr 61001` (只有 TIME_WAIT = 没在听)。
- **只能做只读探查**: exec 跑在监听线程而非主线程。`bpy.ops` 一律不要调 (尤其渲染 / 烘焙), 也不要增删 scene / collection / 物体 / world / 材质或改可见性,
  实测会让整个进程闪退 (`EXCEPTION_ACCESS_VIOLATION`), 用户未保存的改动全丢。
- `bpy.context` 受限: 没有 `active_object` / `selected_objects` / `window` / `area` / `screen`; 读 `bpy.data` 与 `bpy.context.view_layer.objects` 没问题。
- 单请求 4096 / 回包 8192 字节: 只发一行引导语句, 真代码写 `%TEMP%` 下的文件再 exec (路径必须绝对, 中文路径放进文件内容):

```python
exec(compile(open(r'<绝对路径>', 'rb').read(), r'<绝对路径>', 'exec'),
     {'__name__': '__main__', '__file__': r'<绝对路径>'})
```

- 必须给独立命名空间 (否则 exec 落在 `start_listener` 作用域, 推导式 / `def` 里会 NameError); 变量不跨次保留, 跨次共享用 `bpy.app.driver_namespace`。
- 真要改数据 / 渲染: 用 `bpy.app.timers.register` 排到主线程再做, 结果写进 `driver_namespace` / 临时文件供外部轮询; 更稳的是只读探查, 改动写成脚本让用户跑或拷 .blend 到 `%TEMP%` 离线验证。
- exec 期间 `sys.stdout` 被换成 StringIO (主线程的 print 也会被吞), 输出大就让脚本写日志文件; 改动是内存级的 (`is_dirty` 可能仍 False), 要保留得用户自己 Ctrl+S, 还原用 `文件 > 恢复 > 恢复到上次保存`。
- 改用户 .blend 前先说明"不保存就不落盘"并拿到同意; 当前文件是 `external_resources/**` 里的 blend 时保存会改动受保护资源, 必须先提醒。客户端脚手架放 `%TEMP%`, 不进仓库。

## 无头导出 (常驻子进程)

- 导出 (`cloth_export_update_mod.py` / `acc_export_update_mod.py` / `headmod_export_update_mod.py` → `bg_export` → `bg_worker`)
  默认发给一个常驻的无头 Blender, 它带一个独立控制台窗口, 端口 `14147`。`14145` 是游戏端口, 两个别混。
- `register_acc_dynbones.py` 也走同一条: 它要先在子进程里补跑一次饰品导出才能拿到动骨根骨, 而这些改动不能落在当前工程上。
- 常驻进程没启动 / 被用户关掉 / 半路断了, 主进程自动退回原来的一次性子进程 (最坏就是原来的表现), 下次导出重开。
- 改了 `bg_worker.py` 后主进程会按文件修改时间自动重启常驻进程; 常驻进程的配置路径走进程内部环境变量
  `hitori_child_config` (不是用户环境变量), 因此测试沙箱配置也能跑常驻进程。
- 离线测导出要用随机空闲端口 (`bind(('127.0.0.1', 0))`), 不要占用户的 `14147`。

## cmd / bat 坑位

- `set /p` 从重定向的 stdin 读一行后会把剩余输入吞掉 (真实控制台正常), 所以"bat 问一轮 + 子脚本再问一轮"没法用管道模拟。
- `if defined X (A) else B` 这种一行写法会让整个 bat 静默结束 (退出码 255), 要拆成两条单行 `if`。
- 输入重试循环必须有次数上限; 杀进程只能按 PID。
- 子进程输出按 GBK 解码, 别把 `PYTHONIOENCODING` 传给它。

## 项目结构

- `install/init_addon_config.py`: 安装脚本, 复制资源 + 写 `hitori_addon_config.json`, 参数自动推断, 兜底手动输入。
- `hitori_addon/`: 插件逻辑 (没有 `__init__.py`, 是 namespace package)。
- `hitori_addon_ui/`: Blender 菜单 (改动要重装才生效)。
- `hitori_gui/`: 游戏内自研 BepInEx 插件 (HitoriGui); `build.py` 构建后还要把 DLL 同步进游戏 (见硬性约束)。
- `addon_scripts/`: 菜单按钮调用的脚本。
- `install_resources/`: 要复制进 Blender / KKS 的第三方资源 (pip 包, addons_contrib, 自研 BepInEx 插件, 配置; 字节保真)。
- `resources/`: mod 模板资源 (`template/zipmod/` 只剩 manifest.xml 纯文本, `img/` 默认空目录由用户自放; 占位贴图与缩略图都改成运行时生成; 字节保真)。
- `external_resources/`: 游戏衍生的模板与数据 (`kk_blend/` 的官模模板 (含手工烘焙基准 kk_arm / kk_leg), `u3d/` 的 .unity3d, `card/` 的人物卡, `data/` 的脖颈坐标 / 形态键名 / 表情名 / KKLUT 曲线; 最受限不与主仓库一起公开; **已出库**, 见 `.gitignore`)。磁盘上仍是原文件, 发布时用 `python scripts/pack_external_resources.py` 打包成带版本号的 zip 让用户自己解压到项目根 (压缩包里的中英日 `README.txt` 的唯一出处就是该脚本); `setup.bat` 会强制检查它是否齐全, 插件在用到模板时也会查一次 (`const.require_external_resources`, 缺失就弹窗)。
- `scripts/`: 辅助脚本 (`pack_external_resources.py` 是外部资源压缩包与压缩包里说明文件的唯一出处); `docs/`, `tests/`, `README.md` (给用户看的自述, 第 2 行让人运行 `setup.bat`), `setup.bat` (安装入口)。
- 人物卡格式 / 元数据解析(顶层布局, lstInfo, KKEx/KSOX, 官方瞳孔 ID)见 `docs/card_format.md`。
- 外部工具 / 插件由用户自备, 仓库不随分发: `mmd_tools` (推荐 2.8.0, pmx 导入; 缺失时 `importer.require_mmd_tools` 弹窗) 与 SB3Utility (推荐 v22.4.1, 路径存 `hitori_addon_config.json` 的 `sb3u`)。
- 语言: 优先 Python; 文档和注释用中文且精简; 代码内标点用英文标点。

## 开发工具
- 缺失重要工具时, 提醒用户安装
- `fd`, `rg` 遵循 gitignore 和更快速的 `find`, `grep` 搜索工具替代
- `ast-grep` 语法树搜索, 比 `rg` 更精确
- `gh` Github-Cli 工具
- `ruff` 运行 `ruff check` 排查常见问题
- `fake-bpy-module-3.6`: 外部编辑器的 `bpy` / `bmesh` / `mathutils` 补全, 由 `pyproject.toml` 的 `dev` 依赖组经 `uv sync` 装进 `.venv`
  (只在写代码时用, 插件跑在 Blender 自带 python 里; stub 含 Blender GPL 源码的 docstring, 不许随仓库分发, 见 `docs/environment.md`)

## 脚本按钮反馈

- 判据: 需要反馈 + 非高频运行 (高频容易遮挡鼠标) + 结果非显而易见 -> 用 `hitori_addon.menu.message_box` 弹窗报结果; 缺一项就不加。
- 脚本自己已经弹过结果 / 报错 / 对话框时, 不再叠加 `hitori_addon_ui` 的"运行完成"弹窗 (按 `message_box` 计数自动去重)。
- 高频切换 / 纯显示类按钮 (显示官方身体 / 显示穿模顶点组 / 重复上次操作等) 保持 `Button(..., feedback=False)`。

## 常用身体骨骼名称
游戏官方骨骼: 详见 `addon_scripts\merge_vrc_mmd_weights_to_kk.py`
vrc/mmd常用骨骼: 详见 `hitori_addon\bonenames.py`

## 开发环境

- 真机路径, 配置, Blender / KKS 的位置见 `docs/environment.md`。
