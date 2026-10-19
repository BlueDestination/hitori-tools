# 自动化

菜单里绑定脚本的一键按钮 53 个, 纯手动 7 个 (其中 1 个是图例行 `▲符号需自己操作`), 机械操作 (导入、改名、建组、建骨架、
导出、写卡、热重载、烘焙) 已经全在脚本里, 人工残留集中在**判定与微调**。本文记录现状 / 已实现的自动化 / 未实现项的难点;
规则见仓库根 `AGENTS.md`, 性能结论见 `docs/performance.md`, 零散想法见 `docs/todo.md`。

## 现状

```
[装]   setup.bat -> install/init_addon_config.py -> hitori_addon_config.json
[素材] 导入外部模型(pmx/fbx/vrm)
       ├─ 备份删除无用mmd材质网格                一键
       ├─ 命名服装(服装+饰品关键词)                一键
       └─ (重命名服装+分割合并)                  手动
[对齐官模]
       ├─ 追加官模头模眼线                        一键(读 official_template.blend)
       ├─ (对齐 侧视:胸围,胯围 上视:手部)         手动
       ├─ 对齐官方骨架                            一键(X 居中 + 脚点 Y/Z + 大臂高度 + 大臂水平化)
       ├─ 合并重合顶点并勾选锐边选项                 一键
       ├─ 归一化权重                              一键(游戏端按权重和蒙皮, 不到 1 会塌缩; 改原权重)
       ├─ 构建user_edit_key                        一键
       ├─ 构建skip_transfer_group (导出前必做)     一键
       ├─ (服装贴合)                             手动(服装工具: 衣物形变(需身体缩裹) / 衣物缩裹 / 自动缩裹烘焙)
       ├─ (制作服装第二状态)                     手动(服装工具: 拆分上下双状态网格)
       └─ (动骨接骨)                             手动(移植步骤: 生成动骨骨架 / 动骨骨架接骨)
[注册导出]
       ├─ 初始化mod                              一键(zipmod/人物卡/u3d + 可选启动游戏)
       ├─ (构建skip_transfer_group)               一键(导出前必做: 没标记的网格会整片传权重)
       ├─ ★更新服装mod                           一键(无头子进程: 贴图文件名合法化 -> 服装导出 -> fbx更新u3d -> SB3U)
       ├─ 注册服装动骨接骨 + 热重载               一键(端口 14145)
       └─ 饰品链路(更新饰品mod / 注册饰品动骨接骨)  一键(都走无头子进程)
[卡面] 写入瞳孔贴图 -> 写入眼线贴图                一键
       └─ (游戏内眼线->瞳孔->脸型的捏脸)           手动
[发布] 发布人物卡和mod                            一键
[支线] 头模: 追加头模眼线 -> (对齐脖子接缝) -> 头模初始化 -> (编辑neck材质面积)
       -> 构建表情布局 -> 形态键添加序号 -> 渲染形态键截图 -> ★头模更新mod (无头子进程)
       -> 生成眼睛表情e22-27 / 嘴巴表情m25-36 / mc25-36     (中间 2 处手动, 其余一键)
[底层] 常用(重复·备份·显示穿模·显示官方身体) / 服装工具 / 材质 / 开发调试 / 顶点组 / 骨骼
```

## 手动残留的 8 个步骤

| 步骤 | 手动的那部分是什么 | 已有的"机械那半" |
|---|---|---|
| 重命名服装+分割合并 | 同目标多网格的合并、上下状态拆分, 以及名称里没关键词的网格(饰品已自动命名) | `命名服装` |
| 服装贴合 | 离身体远近的微调、穿模取舍 | `衣物形变(需身体缩裹)` / `衣物缩裹`(自动加修改器链) |
| 制作服装第二状态 | 第二状态的形态本身 | `split_upper_lower_meshes.py`(全穿 / 半脱各拆上下两块) |
| 动骨接骨 | 骨架对接与微调 | `生成动骨骨架` / `动骨骨架接骨` / `注册服装动骨接骨` |
| 游戏内设置饰品父级并对齐 | 挂点选错的微调 (前胸 / 背部 / 腰部之间取舍) | `饰品导出`(写 csv 父级 + 烘焙挂点逆变换) |
| 游戏内眼线->瞳孔->脸型捏脸 | 审美 | 无 |
| 对齐头模脖子接缝 | 接缝顶点对齐 | `headmod_init.py`、official_template.blend |
| 编辑生成的 neck 材质面积 | 面积/UV 取舍 | `material.py` / `image.py` |

## 已实现 (2026-10, 全部是新增脚本 + 新增按钮, 原脚本未改)

### 饰品挂点对齐: `hitori_addon/acc.py` + `addon_scripts/acc_export.py`

- 游戏把饰品挂在 `a_n_*` 节点下 (`ChaControl.ChangeAccessoryParent` -> `SetParent(锚点, false)`), 位置旋转缩放
  完整继承锚点, 卡片里的饰品位移 / 旋转写在 `N_move` / `N_move2` 上, 不是饰品根节点。
- 锚点真值取自游戏 `abdata/chara/oo_base.unity3d` (角色 body 预制体, 就是 `ChaReference.CreateReferenceInfo(1, ChaPreparationBodyBone.BoneInfos)`
  查的那套 `a_n_*`) 的世界变换, `co_bra_01.unity3d` 里同一批节点数值完全一致:

| 名称 | 锚点 | 位置 (Blender) | 旋转 (Unity 四元数) |
|---|---|---|---|
| head | `a_n_headside` | (0, 0.020762, 1.580417) | identity |
| neck | `a_n_neck` | (0, 0.024762, 1.488417) | 12° X |
| back | `a_n_back` | (0, 0.086762, 1.3825) | 180° Y |
| waist | `a_n_waist` | (0, 0, 1.1385) | identity |
| chest | `a_n_bust` | (0, 0.029262, 1.4485) | identity |

- 导出时按根骨世界位置选最近的锚点 (`KK_ACC_POSITIONS_ARR`), 再 `obj.set_acc_matrix` 施加逆变换
  `顶点 <- R⁻¹·(v - p)` (网格和骨架同一个矩阵, 绑定关系不变), 之后照旧 `set_unity_matrix`。
  identity 旋转的锚点 (head / waist / chest) 退化成旧版的 `-pos` 平移。
- `template.update_acc_csv_parents` 把 zipmod 里对应 `9.acc*.csv` 的 `Parent` 列改成实际锚点名,
  只在内容真的变了时才重建 zipmod; csv 只在游戏读列表时生效, **重启游戏后父级才变**。
- 与旧数据的差异 (旧 `KK_ACCS` 的 `pos`: head 1.58092 / neck 1.48876 / back 1.38305 / waist 1.11547 / chest 1.38406):
  waist 与 chest 的 `pos` 本来就不是锚点真值 (`chest` 的旧 `offset` 恰好 `= -a_n_bust`, 说明本意就是它);
  head 旧 `offset` 被手工微调过 (前移 2.7cm / 上移 7mm), 现在按锚点真值走, 头部饰品会比以前靠后一点。
- 官方美术确实按锚点旋转做了补偿, 不是我们凭空补的: 父级 `a_n_back` 的 `p_acs_yousei_wing_R` 根节点自带
  q=(0,1,0,0) (180° Y), 正好抵消 `a_n_back` 的 180°。
- 离线验证: 每个锚点取 4 个局部点 (含左右和斜向偏移) 做 "锚点正向变换 -> 逆变换" 往返, 误差 < 1e-6;
  另用真实立方体跑 `set_acc_matrix` + `apply_transform`, 顶点坐标与 `R⁻¹·(v - p)` 手算值逐位相同。
  游戏内仍需肉眼确认 (尤其背部饰品的朝向与前胸挂点的取舍)。

### 动骨剪枝: `hitori_addon/dynbone.py` + `addon_scripts/dynbone_cleanup.py`

判据是四条并集 (完整说明在 `dynbone.py` 的模块 docstring, 改动前先读), 四条算完后再做第 5 步把身体骨清干净:

1. **权重不可达**: 一根骨骼和它所有子孙在任何网格顶点组里权重都为 0 -> 删;
2. **人形骨子树**: 命中标准人形骨, 且整棵子树里没有任何非人形骨 (动骨) 时才删;
3. **臀 / 尾词缀**: 名字首词是 `hip(s)` / `tail(s)` 的骨骼连同子树删 (服装几乎不挂这两处; 只认首词, `Shirt_tail` 不受影响);
4. **脖子以上**: 头或尾高于颈部高度、且不是标准人形骨 -> 整枝删 (头发 / 发饰); 四条算完再清掉只剩人形骨的空枝 (`Neck -> Head`)。
5. **身体骨全删**: `find_body_bone_names` 把剩下的标准人形骨 (`Spine` / `Chest` / `Upper_leg.L` 等) 一起删,
   动骨骨架只留动骨链与接骨 (链根骨); 第 2 条为动骨链保住的祖先骨到这一步才清掉,
   `edit_bones.remove` 会把子骨挂到被删骨骼的父级上, 所以链根骨随即各自成为根骨。

- 流程: 复制成 `<名>-db` 后清理, 被删骨骼另存 `<名>-deleted`, 原骨架不动; 结束后藏原骨架与 `-deleted`, 只留 `-db` 并进编辑模式;
  两个骨架的骨骼分归骨骼组 `db`(绿) / `deleted`(红)。
- 复制后先 `arm.freeze_pose` 把**可视状态固化成静置骨架** (`bpy.ops.pose.armature_apply` 把姿态写进 rest 并把姿态通道归零,
  `-deleted` 一起固化, 两副骨架位置才能对上): 外部骨架多半带着姿态, 不固化的话后面接骨 / 合并回 `Armature` / `rest_arm` 导出
  时骨骼会跳回外部骨架的原始静置位置 (T 姿), 与可视状态对不上。
  骨架显示为静置 (`pose_position` 是 `REST`) 时姿态本来不可见, 此时只清姿态通道、rest 保持原样。实测 `Processed/test.blend` 的 **269 骨原始骨架 -> 94 骨** (删 175), 只剩 3 条服装动骨链待接;
  94 是加第 5 条之前的值, 现在这 94 骨里残留的身体骨也会删掉。
- 实测补上的规则: 该模型用 `Upper_arm.L` / `Hand_twist.L` / `Breast.1_L` / `Hoppe2.L` 这类简写, 不在 `VRC_MMD_BONES_SET` 里,
  有人形权重又删不掉, 必须靠第 2 条"子树里没有动骨"才删; 纯按名字删会删错 (`Upper_leg.L` 是腿飘带链的祖先, 靠这条保住)。
- 第 4 条的边界: 侧发链挂在 `Chest` 上, `Hair_Side_root` 头在 z=1.028 (低于颈部 1.061), 只有尾 (1.078) 伸进头部,
  所以判据必须是"头**或尾**高于颈部"; 胸前飘带 `Root_Ribbon` (1.023 / 1.036) 低于颈部, 被正确保留。
- 已知边界: `Hips_L` / `Hips_R` 是短裤动骨链起点, 名字算人形骨但首词命中 hips, 被第 3 条整枝删除 (这两根带小权重,
  单顶点均值约 0.06, 删后只受 `Hips` 影响)。某件衣服确实要用就给第 3 条加白名单。
- 人形骨判定走 `bonenames.is_humanoid_bone_name`: 先按原文小写比对 (认 PMX 的 `左腕` / `右肩C` 前缀写法与日文骨名),
  再按归一化名比对 (认 `Upper_leg.L` / `Upper Leg.L` / `upper_leg_L` 这类分隔符差异)。归一化会丢字的条目
  (`上半身1` -> `"1"`、`腕.L` -> `"l"`) 不进归一化集合, 否则任何带 `.L`/`.R` 或纯 CJK 的骨骼都会被误判成人形骨。
- 接骨 (`dynbone_join_bones.py`): 把 `<名>-db` 合并回 `Armature`, 每根根骨骼挂到 12 个 KK 关节骨之一 (`dynbone.find_kk_joint_bone_names`)。
  判据不是单一的距离: 腿 / 手臂按"区域"算 —— `thigh00`(髖) -> `leg01`(膝) -> `leg03`(踝)、
  `arm00`(肩) -> `forearm01`(肘) -> `hand`(腕), 整段 (含关节头) 都算**近端**关节的地盘 (就上),
  所以大腿中段的飘带根骨挂 `cf_j_thigh00_L` 而不是膝; 躯干 / 其它关节算到关节头距离。
  不能用骨骼 `tail` 划线 (模板里 `cf_j_thigh00_L` 的 tail 反而朝上), 只能用关节头连线; 平手时取近端关节。
  实测 (Mayo 大腿飘带): `Root_LegRibbon` 头在髖 0.978 / 膝 0.518 之间 (y=0.731), 旧规则到膝 0.215 < 到髖 0.249
  → 误接 `cf_j_leg01_L`; 按区域算 `thigh00=0.029` vs `leg01=0.215` → `cf_j_thigh00_L`, 同一骨架的
  `Root_Ribbon` / `Panty_Ribbon_Root` / `Root_Skirt` 结果不变。躯干关节头间距只有 7~9cm 且没有跨段长骨, 不受影响。
  第 5 条删完身体骨后根骨不再只有 `Hips` 一根, 而是每条动骨链的接骨各算一根; 下面的 `db_root(1)` 实测是加第 5 条之前的状态。
  join 是按组索引合并的, 所以合并前先快照 `-db` 的骨骼组与颜色、合并后还原, 否则 `db` 组的骨会落进 `Armature` 自带的 `j` 组。
  实测接骨后 `Armature` 271 骨, 根骨只剩 `cf_j_root`, `j` 组恢复成官方 69 根, 新骨留在 `db`(93) + `db_root`(1, 橙)。
  接骨完直接进姿态模式 (接骨的那几根骨保持选中), 方便当场试动骨。
- 注册 (`register_cloth_dynbones.py` / `register_acc_dynbones.py`): 服装不看骨名, 按**权重反推**类型 (`dynbone.find_cloth_root_bone_types`):
  候选根骨 = 接骨标的 `db_root` 骨骼组, 每根根骨的 `children_recursive` 子树 ∩ 有权重的服装网格 -> 网格名 ->
  `sb3u.get_cloth_type` (经 `MESH_ANIMATOR_MAP` + `CLOTH_TYPE_ANIMATOR_NAME_MAP` 反查, 不另维护映射), 所以
  `cloth_top` / 半脱 `cloth_top.001` / 连体 `cloth_top_bot` 都算 top。服装经 `u3d.register_u3d_root_bones`
  把动骨 (根骨的每个子骨) 与接骨 (根骨 -> 父骨) 写进 animator 的 `db_mono` / `bi_mono`, 再热重载。
  服装不需要饰品那套锤点规则: 根骨本身就是接骨固定住的刚性锤点, 底座权重挂在它身上就该是刚性的,
  而子骨全是链起点 (Mayo 实测 4 条链: `Root_Ribbon` -> 4 根 `*_RibbonTie` + `Root_Skirt` -> 14 根 `*_Skirt`,
  `Root_LegRibbon` / `Panty_Ribbon_Root` 各 3 根, 根骨名以 `Root` 开头/结尾都不影响)。
- 饰品 (`register_acc_dynbones.py`) 没有接骨: 饰品挂在游戏槽位上, 不需要把自己接回身体骨。
  动骨取链起点本身 (`dynbone.find_acc_dynbone_bone_names`: 从骨架根骨往下, 跳过人形骨/根骨后踩到的第一根就是链起点,
  命中后不再往下, 免得把一条链拆成多份注册), 经 `u3d.register_u3d_dynbones` 写进 `acc<N>_db_mono_NN` 的 `m_Root`。
  依据是官方饰品 mod (实测 `ao_hair_00` / `bo_hair_b_00` 等): `m_Root` 写的就是链起点 (`joint1` / `cf_J_hairB_00` /
  `j_ribon_02`), 它的父骨 (`N_move` / `cf_J_hairB_top` / `j_ribon_01` 这类 holder) 不注册; 甚至只有一根骨的链
  (`j_ribon_02`、`cf_J_hairBCL_00` 子骨 0) 也会注册, 所以 `m_Root` 自身是参与物理的, 不能把身体骨写进去。
  旧写法取"根骨的所有子骨", 导出骨架里 `Head` 恰好是合成根 (`arm_acc_root`) 的子骨 -> 整顶头发从身体头骨开始摆动。
  导出时会删掉无权重骨 (mod 自己的 `Hair_root` / `Hair_Side_root` / `Kemomimi_root` 这类 holder),
  子骨被抬到祖父下, 所以结构性判据只能靠"第一根非人形骨"; 只有身体骨的饰品 (无可动物件) 得到空列表, 不注册。
- 名字以 `root` 结尾的骨是锤点 (`dynbone.is_dynbone_holder_name`): 不注册, 注册它下面的子骨。
  这类骨的权重是跟着头皮 / 身体不动的底座, 注册了会整块抽起来。Mayo 头发饰品 (17787 顶点) 实测
  `Side_root` 3391 顶点 (z 1.442~1.775) / `Back_root` 1307 (z 1.329~1.771) / `Front_root` 825 (z 1.572~1.755) /
  `Ahoge_root` 12 (z 1.756~1.763) 全是包着 `Head` 权重点 (727 顶点, z 1.506~1.750) 的发根底座,
  注册后在游戏里就是后脑勺连头皮一起摆。改成注册子骨后 acc 的动骨从 6 根 (`Back_root` / `Front_root` /
  `Side_root` / `Ahoge_root` / `R_Side` / `L_Side`) 变成 32 根 (`Back` + `Front_*` 8 根 + `Side_*` 20 根 +
  `Ahoge_1` + `R_Side` / `L_Side`), `acc2` (兽耳) / `acc3` (尾巴) 结果不变 (尾巴的 `Tail_root` 本来就是骨架根骨, 一直被跳过)。
  `Root_` 前缀是动骨链的根骨 (`Root_Skirt` 那类), 不算锤点; 21 个 PMX 语料里没有骨名以 `root` 结尾, 所以语料结果逐字不变。
  数量还要过 `validate_dynbones` 的槽位校验 (`acc<N>_db_mono_` 有 50 个)。
- 人形骨判定的补充 (`dynbone.HUMANOID_KEYWORDS`): KK 骨架全靠 `cf_` 前缀命中 (`cf_J_Mouth*` / `cf_J_Tang*` / `cf_J_Hair*`),
  但 MMD 骨架的面部骨 (`Bn_m_jaw_001` / `Bon_yachi_*` / `Bon_zuiba_L` / `*UpLips*`) 以前会被当成饰品动骨链起点。
  用 21 个 PMX (异环, 103 个饰品材质单元 / 251 个注册骨名) 实测: 唯一的身体骨泄漏就是 `Bn_m_jaw_001` (面罩),
  补 `jaw` / `lip` / `tooth` / `teeth` / `tongue` / `cheek` / `brow` / `yachi`(歯) / `zuiba`(嘴) 后归零, 其余 102 个单元结果不变。
  `cf_` 前缀先行返回, 所以 KK 骨架分类不受影响。
  同一批语料里注册出来的骨都是链起点本身 (父骨是 `頭` / `上半身*` 这类人形骨, 自己带子骨), 与官方 `m_Root` 语义一致。
  判据拆成不依赖 bpy 的 `find_acc_dynbone_names` (骨名 -> 父骨名) 与骨架版 `find_acc_dynbone_bone_names`,
  语料冻在 `tests/data/acc_dynbone_hierarchies.json` (83 个饰品单元 / 80 份剪枝后的层级),
  回归在 `tests/test_acc_dynbone_names.py`: 改判据后跑它就能看出是改进还是回归
  (`<Blender>/blender.exe -b --factory-startup --python tests/test_acc_dynbone_names.py`)。
  其中 3 个单元是 Mayo 工程的真实饰品网格 (`acc` / `acc2` / `acc3`, 由 `test_plugin.blend` 按
  `acc_export` 的口径剪骨架后写入), 专用来守发根底座规则: 把锤点规则去掉, `Mayo/acc` 立即从 32 根
  回退成 `Ahoge_root` / `Back_root` / `Front_root` / `Side_root` / `R_Side` / `L_Side` 6 根。
- 类型判定的边界: 一条链同时挂在多种服装的网格上 -> 报错且不写入 (游戏里会跟错衣服, 要拆权重);
  一根根骨都没命中 (只挂在饰品 / 非法网格名如 `_pants` 上) -> 跳过, 弹窗里每行都带上命中的网格名
  (`Panty_Ribbon_Root -> _pants`, 没权重写 `-> 没有任何权重`);
  一个类型都没剩下时同样报错不写入。实测 Mayo 的 4 条链: `Root_Ribbon` -> top (`cloth_top`)、`Root_Skirt` -> top (`cloth_top`)、
  `Root_LegRibbon` -> sock (`sock`)、`Panty_Ribbon_Root` -> 空 (`_pants`, 跳过), 扫描全部网格耗时 0.1s。
  以前靠骨名包含 `<type>_root` 找根骨的做法已删 (`top_root_glove_root_1_L` 那种跨类型命名不再需要)。
- 写之前的全量校验 (服装 `u3d.validate_root_bones`, 饰品 `u3d.validate_dynbones`): 找不到骨骼的 Transform /
  动骨数超过 `db_mono` 槽位 / 接骨没有父骨 / 接骨数超过 `bi_mono` 槽位, 任何一条命中就整体报错且不保存 (u3d 文件不动),
  不会写到一半才炸; 一个 mono 都没填时不重建 zipmod。
- 注册完成的弹窗 (`u3d.format_root_bones_report`): 每类先标出来源网格 (`top: 动骨 2 根, 接骨 2 根 (网格 cloth_top, cloth_top.001)`,
  服装按自动分类结果汇总, 超过 6 个截断; 饰品的骨架导出时就是按网格名建的 `arm_<网格名>`, 所以来源就是同名网格),
  再列接骨 (根骨 -> 父骨) 与动骨名 (顺序即 `db_mono` 编号);
  饰品的写入在无头子进程里 (弹窗只会在控制台打印), 所以主进程等子进程跑完后用 `u3d.read_u3d_root_bones` 从 u3d 反读。

### 目标网格与重烘焙: `hitori_addon/baketarget.py` + `addon_scripts/auto_shrinkwrap_bake.py`

- 覆盖判定: `bodytight` 面中心到源网格表面距离 < 阈值, **或** 源网格顶点/面中心最近投影落在该面上 (间隙 ≤ `MAX_PROJECTION_GAP` 0.1m)。
  只用前者时, 与 bodytight 有明显间隙的宽松服装 (过膝袜等) 只能选出零星的面, 目标网格会破碎。
- 补网格内部空洞 (`fill_holes`, 默认开): 覆盖后源网格自身围成一圈、圈内 bodytight 面距离又超过阈值时 (内裤裆部),
  产物中间会缺一块, 展开 UV 也会在凹陷处折叠重叠 (实测裆部缺 54 条边的洞 + 44 对面 UV 重叠)。
  所以把“被围住的未选面连通块”补回来, 条件是整块离源网格都不超过 `MAX_PROJECTION_GAP`, 且不与 bodytight 自身边界
  (脖子开口) 相连; 腿 / 躯干那种外部区域总有很远的面, 不会被补 (实测裆部 292 面全在 48mm 内, 小腿 1360 面最远 818mm)。
  补后同件内裤 1184 -> 1476 面, 内部洞与 UV 重叠都消失。
- 取面子集后向外扩 `grow` 圈 (沿公共顶点) -> 只留用到的顶点 -> 按官方缝合边 `uv.unwrap` + `pack_islands` (铺满 0-1) -> 可选沿法线外扩 cage。
  `smart_project` 不认缝合边, 会切出一堆小岛, 所以改用平展; 缝合边 (`use_seam`) 从 bodytight 逐边复制过来。
- 目标网格坐标直接取世界坐标 (物体矩阵为单位阵): `bodytight` 自带 -90 度 X 旋转, 直接复制局部坐标会横躺。
- 着色: 复制 `use_smooth` / `use_auto_smooth` / 自定义拆边法线, 否则取子网格后全是平面, 材质模式下棱角分明。
- 材质: 目标网格用自己的新材质 (名字 = 目标网格名, 只有 BSDF + 材质输出), 不引用官方材质; `auto_shrinkwrap_bake.py` 会按物体名换成贴图材质。
- 父级: 目标网格挂到源网格的父级下 (用 `matrix_parent_inverse` 抵消, 世界矩阵仍为单位阵)。
- 权重: 复制 `bodytight` 的顶点组与权重 (仅保留用到的顶点), 然后删掉变空的顶点组,
  并把全部顶点写进 `skip_transfer_group` (整片不传权重: 产物自带官方权重), 见 `cloth_export.py` 的 `transfer_weight` 掩码。
- 实测官模模板里的手工基准 `kk_leg` / `kk_arm`: `distance=0.001, grow=0` 得 1466 / 2236 面, 比手工版 (1447 / 2234) 多一行边界余量。
- 实测过膝袜 (`test-bake.blend`, 袜面到 bodytight 中位间隙 1.4cm): 修复前 988 面 + 10 个碎片, 修复后 2698 面、左右腿各一个连通块;
  `_Stocking_L` 1351 面 -> 5 个 UV 岛、利用率 0.446, 密度极差 3.1 倍 (官方 bodytight 自身 UV 同区域约 6 倍)。
- 产物命名: 源网格名带 `_bake` / `-bake` 后缀或 `bake_` / `bake-` 前缀、且去掉后是 `CLOTH_MESH_NAMES`
  里的合法服装名 (如 `cloth_top_bake` / `bake-cloth_top`) 时, 产物直接用该合法名 (`cloth_top`); 否则 `<源名>_target`。
  产物名同时是烘熔材质 / 贴图名 (`<产物名>.png`), 所以“改名成合法名 + 加 bake 前后缀”就能直接烘出合法贴图名。
  名字在生成时固定, 改源网格名要删掉产物重跑 (和改生成参数一样)。
- 幂等: 目标网格打 `hitori_bake_source` 属性 (存指向源物体的 ID 指针, 随 blend 保存, 改名不丢) 与
  `hitori_bake_source_hash` (源网格世界坐标 + 缩裹修改器参数与顶点组权重 + 生成参数的指纹)。指纹一致就复用 (保留手动微调的顶点),
  不一致就删掉重建; 兼容早期只按 `<源名>_target` 名字记录的旧产物。指纹只看基础网格, 不看求值结果, 所以摆姿势不触发重建。
  实测重建本身只要 0.15s (过膝袜 1370 面, 大头是覆盖判定), 但无条件重建会丢掉手动微调的顶点, 所以还是先比指纹。
- 生成参数 (距离 `hitori_bake_distance` / 扩圈 `hitori_bake_grow` / 罩体 `hitori_bake_cage` / 补洞 `hitori_bake_fill_holes`) 也记在产物上:
  产物记过参数就沿用产物的值 (`need_bake_params`), 想改参数就删掉产物。
  `get_or_generate_target` 里产物记过参数就以产物为准 (弹窗输入的默认值不会把已有产物重建掉)。罩体不是产物,
  `make_cage` 会清掉复制过来的 `hitori_bake_*` 属性, 否则产物删掉后罩体会被误认成产物。
- `auto_shrinkwrap_bake.py` (`hitori_addon_ui` 服装工具按钮): 先 `ensure_shrinkwrap` 给源网格配三个顶点组限定的缩裹修改器
  (`TARGET_PROJECT` / `ABOVE_SURFACE`, 修改器与顶点组同名): `bake-inner` 0mm / `bake-middle` 1mm / `bake-outer` 2mm。
  三个顶点组构成全集且互斥, `bake-middle` 恒等于"除 inner / outer 之外的全部顶点", 每次运行重新对齐
  (只增删归属, 保留 middle 里已有的权重); 用户把顶点放进 `bake-inner` / `bake-outer` 就会自动从 middle 移除,
  想贴身 / 宽松只改这两个组即可。修改器只补缺失的, 已存在的参数一律不动 (保留用户调过的偏移)。
  然后对每个选中网格 `ensure_bodytight` -> `get_or_generate_target` -> 烘焙, 结束后弹窗列出每个网格的面数与注意事项。
- 弹窗 (`need_input()` 为真才出现, 即选中的物体里有产物还没记全参数) 四项: 贴图分辨率 `SIZE_PROPERTY`
  (默认 1024, 必须 2 的 n 次方且在 64~8192 之间) / 距离阈值 `DISTANCE_PROPERTY` (按 mm 输入, 默认 10mm, `parse_distance` 换算成米后内部照旧用米) / 罩体 `CAGE_PROPERTY` / 补洞 `FILL_HOLES_PROPERTY` (默认开)。
  分辨率存 `hitori_bake_size`, 距离与罩体/补洞存 `hitori_bake_distance` / `hitori_bake_cage` / `hitori_bake_fill_holes`。
  源网格改过导致产物重建时, 分辨率在重建前读出来、重建后写回新产物。
  想换分辨率 / 参数就删掉产物再运行。
  `get_script_run_menu` 因此多了 `string_property_2` / `bool_property_2` (参数顺序固定为 enum, string, string2, bool, enum2, bool2)。
  烘焙光线距离 (`max_ray_distance`): 补洞时用 `MAX_PROJECTION_GAP` (光线要够长才能烘到 100mm 外的源网格), 没补时仍旧 20mm。
  眼线 / 瞳孔贴图不走这里: 它们默认 512 且优先沿用官方模板贴图的尺寸 (UV 展得比较开, 512 够用)。
- 注意: 重展 UV 后旧贴图对不上, 必须重新烘焙; 不能拿正交投影 (`projection.py`) 替代 (只对正视图平面特征成立, 服装是闭合曲面)。
  烘焙材质走 `material.ensure_alpha_clip` (贴图 alpha 接 BSDF Alpha + `blend_method=CLIP`), 贴图里没烘到的透明像素
  在材质预览里能直接看到, 用户自己用画笔补 (没有做自动填充: 扫描慢, 且会把本来就该透明的地方填错)。

### 骨架对齐: `hitori_addon/align.py` + `addon_scripts/align_official_armature.py`

预处理 + 三步, 前三步只改骨架物体的位置与缩放 (骨骼 / 旋转不动):
0. 预处理: 骨架沿 X 平移, 物体原点回到世界 x=0;
1. 右脚起点 (`Foot.R` / `足首D.R` 及衍生命名) 的世界 Y/Z 对齐官方 `cf_j_leg03_R` (X 不动);
2. 以脚点所在高度 (Y/Z) 为锚点、在 x=0 轴上整体缩放, 让右大臂 (`Upper_arm.R` / `腕.R`) 的世界 Z
   对齐官方 `cf_j_arm00_R` (锚点带上脚点 X 会把第 0 步的居中带偏, 脚点 X 会随缩放小幅内收, 不参与对齐);
3. 第三步改内部姿态数据, 左右大臂绕骨骼头部旋转到水平 (两端世界 Z 相同), 已水平的不动。

骨骼名匹配按候选名优先级: 精确名 -> 去掉大小写与分隔符的归一化名 -> 唯一数字后缀的衍生命名
(例: `foot_R` / `UpperArm-R` / `腕.R.001`)。

### 网格命名: `hitori_addon/naming.py` + `addon_scripts/name_clothes.py`

- 匹配顺序: 服装类 (`cloth_top` / `cloth_bra` / `pants` / `panty` / `sock` / `shoe` / `glove` /
  `cloth_bot`) -> 饰品 (头发 -> 尾巴 -> 翅膀 -> 其它配件) -> 身体类。关键词表在 `naming.py` 顶部的配置区。
- 身体类是 `body` / `body-head` / `body-neck` / `body-hitomi` / `body-eye` / `body-eye-hi` /
  `body-eye-shadow` / `body-eyebrow` / `body-eyeline` / `body-mouth` / `body-nail` / `body-hand` /
  `body-leg` / `body-ear`, 只用来把身体和头部零件归到一起方便批量处理,
  不参与导出 (名字不合法, 导出时会拦下)。放在最后匹配, 所以 `头发` / `头饰` / `猫耳` / `耳环` 仍然归 acc,
  普通 `耳` / `ear` 才归 `body-ear`。
- 忽略表 (`SKIP_KEYWORDS`) 排在最前: `表情` / `Emotion` / `exp` / `まばたき` / `blink` / `口パク` 这类网格
  完全不动, 连 `_` 前缀都不加 (否则 `面 表情` 会被 `面` 抢成 `body-head`)。
- 同一服装目标有多个网格时第一个用本名, 后面的加 `_2` / `_3` (等用户合并); 饰品头部优先占前面的 acc 槽位,
  超出 acc9 继续编号并加 `_` 前缀 (`_acc10`); 无法归类的网格同样加 `_` 前缀。
- 英文关键词按整词比对 (去数字后缀 + 去复数), 中日文按子串; 服装词表按越具体越靠前的顺序匹配
  (袜 / 鞋先于裤, 上衣先于胸罩), 否则 `连裤袜` / `靴下` / `ブラウス` 会被抢走。
- 饰品只收基本不连在服装上的配件, 能贴合身体 / 很像服装 (丝带、蝴蝶结、腰带、围巾) 的不收, 它们要自己传权重。
- 连衣裙 (`Dress` / `ワンピース` / `衣服`) 按上衣命名, 裙子部分自己归 `cloth_bot`; 真正跨语义的
  (`连体衣` / `泳装`) 不自动命名, 直接加 `_` 前缀等人划分割线。
- 服装材质常按编号 / 部件命名 (`服1` / `服2` / `衣袖` / `衣领1` / `领带` / `衣饰` / `Cloth1`), 分不清上装下装,
  统一先归 `cloth_top` (`腰布` 归 `cloth_bot`), 出 `cloth_top_2` / `_3` 后自己合并或改 `cloth_bot`。
- 跳过已是合法名 / `cloth_top_2` 这类重名后缀的网格 (重跑幂等)。`.001` 只在基名是合法名时才算半脱
  (如 `cloth_top.001`), Blender 复制产生的 `名字.001` 照样命名。
  槽位只取场景里没人用的 (含未选中的物体), 改名走两段临时名, 避免 Blender 自动补 `.001`。

### 骨骼工具: `hitori_addon/arm.py` / `hitori_addon/pose.py`

三个按钮 (`add_leaf_bones` / `pose_horizontal` / `pose_mirror`) 都是多骨架多骨骼: 叶骨完成后列出新增的骨骼名,
其余正常完成不弹窗, 只在出错 / 找不到镜像骨骼时弹窗。

- **叶骨** (`add_leaf_bones.py`): 给每根叶子骨骼挤出一根末端骨, 名字 `原骨名_end`, 长度 0.005。
  原叶骨**保持原名** (改了就与网格顶点组对不上), 所以看到的 `_end` 一定是新加的那根。已带 `_end` 的跳过 (重跑幂等)。
  挤出后只选中新骨的**尾点** (关节), 不选整骨也不选头点, 方便接着调姿势; 没活干时不进编辑模式 (不动原有选择)。
- **隐藏层坑**: 骨架层 (32 位 `bone.layers`) 里关掉的骨骼在编辑模式里选不中, 就挤不出末端骨。
  所以 `add_leaf_bones` 进编辑模式后临时全开所有层, `finally` 里恢复原状——隐藏层里的叶骨也能加上。
- **水平化** (`pose_horizontal.py`): 只改姿态不动网格; 绕**骨骼头部**把骨骼转到水平 (两端世界 Z 相同),
  角度收到 `[-90°, 90°]` (朝 -X 的骨骼转到 +X 侧算同样水平, 少转 180 度); 沿世界 Y 的骨骼跳过不报错;
  同一棵树上的父子骨骼同时选中会报错 (父级转动会把子级带偏)。
- **镜像** (`pose_mirror.py`): 按骨架局部 X=0 平面镜像, 命名规则见 `pose.py` 的 `MIRROR_MARKERS`; 顺序即优先级
  (`.L`/`.R` -> `_L`/`_R` -> `-L`/`-R` -> ` L`/` R` -> `L_`/`R_` -> `Left`/`Right` -> `左`/`右`)。
  同一标记可能在名字里出现多次 (`Bon_Lolip01_L` 里的 `Bon_L` 也含 `_L`), 所以 `find_mirror_bone` 逐个出现位置换名再判存在
  (只换第一处会换错位置, 表现为单向配对)。不做父子树检查, 只查"多个源指向同一根目标"; 左右 roll 约定不一致
  (mmd 左右差 180°) 时用 `get_roll_fix` 自动补偿扭转。
- **镜像命名体检** (`scripts/check_mirror_names.py`, 一次性脚本, 不进菜单):
  `<Blender>/blender.exe -b <模型.blend> --python scripts/check_mirror_names.py [-- <骨架名关键词>]`,
  统计每个骨架的命名命中率 (找到镜像伙伴 / 带左右标记), 列出漏配 (带标记但找不到伙伴, 附按 X=0 镜像位置猜的伙伴名)、
  单向配对 (A 认 B, B 不认 A)、命名缺口 (名字像左右骨但标记不在 `MIRROR_MARKERS` 里)。
  实测官方骨架 100% (154/154), 阿德勒 87.2%、黑羽 89.1% (漏的都是仅单侧存在的裙摆 / 头发骨)。
- **弹窗名单截断**: 骨骼名动辄上百个, `menu.format_name_list` 只列前 24 个, 后面写 `... 共 N 个`;
  总行数还有 `format_popup_lines` 的 40 行上限兜底。

## 外部模型导入 (`scripts/view_model.py`)

支持的格式只在 `hitori_addon/importer.py` 的 `MODEL_IMPORTERS` 里列一次 (现为 `.fbx` / `.vrm` / `.pmx`),
文件选择框的过滤器 (`get_model_filter_glob`) 与弹窗里的格式清单 (`get_supported_model_hint`) 都由它生成,
加格式只需加一条映射。

部分格式导入后还要再处理 (需排在骨架清理之后, 所以不能揉进导入函数): 现只有 `.pmx` 走
`MODEL_POST_PROCESSORS` 里的 `split_pmx_by_material` (按材质拆网格 + 去掉 mmd_tools 加的前缀)。
后缀不认识时报 `不支持预览的模型类型: .xxx, 支持: .fbx / .vrm / .pmx`, 弹窗提示。

## 素材导入侧的两个自动修正

- **PMX 贴图路径**: PMX 里的路径常带手误 (`xxx_d..png` 多一个点 / 扩展名大小写不一致 / 文件名带空格),
  Blender 按原样拼路径读不到图, 材质就成空白。`import_pmx` 导入后调 `image.fix_missing_image_paths`:
  折叠贴图名 (小写 + 空格/点/下划线/连字符归一) 后在同目录里找**唯一**同名文件, 命中就把图片路径改指过去
  (`image.reload()`), 并弹窗列出改了哪几条; 折叠后对上多个文件算歧义, 不动。只改内存里的路径, 不拷贝也不改名磁盘文件,
  所以导出的贴图名仍是 PMX 里那个错名 (要合法名另见 `legalize_texture_names.py`)。
  实测 `达芙蒂尔` 的 `T_player_054_daffodill_eyes_d..png` 已自动指向真实文件。
- **权重合并表**: `addon_scripts/merge_vrc_mmd_weights_to_kk.py` 的 `kk_bone_to_vrc_bones_map_left` 覆盖 KK 骨 32 个
  (镜像后 57), 含腿链 (`足.L` / `ひざ.L` / `足首.L` / `足先EX.L` / `つま先.L` 及 D 版)、`頭`、`上半身1`;
  实测 MMD 样本顶点覆盖率 23%~71% (补表前 14%~47%)。

## 未实现

### 服装拆分 / 合并 / 命名

- 合法名在 `hitori_addon/sb3u.py` 的 `MESH_ANIMATOR_MAP` (`hair` / `cloth_top` / `cloth_bot` / `cloth_bra` / `pants` /
  `glove` / `panty` / `sock` / `shoe` / `acc`…), 导出前不合法会被 `ObjectError` 拦下并弹窗提示。
- 自动命名已完成 (见上面“网格命名”); 仍靠人的部分: 同目标多网格的合并与上下状态拆分,
  以及名称里没关键词的网格 (`_` 前缀)。
- 极靠形状的判定 (bbox 高度带 / 是否过裆 / 材质与贴图 / 权重重心) 没做: 需要回归样本 (源模型 + 正确成品 blend)
  才能定阈值, 默认不自动 (静默错了只有进游戏才看出来)。

### 游戏内写饰品卡数据

- `hitori_addon/card.py` 不解析 Coordinate / 饰品数据, "写卡方案"等于新写一段二进制解析 + 回写, 风险最高 (写错会让卡加载异常)。
  现在走的是 csv 父级 + 烘焙到顶点两条, 不动卡片; 要把 `N_move` 的位移也自动写进卡, 才需要解析卡里的饰品块。
- 参照卡 (maker 里手工设好父级 + 对齐并存出的人物卡) 还没拿到: 拿到后可以反查现有锚点数值与官方的偏差,
  也能验证挂点分类 (前胸 / 背部 / 腰部) 的取舍规则。

## 验收要求

任何自动化都必须同时给出两样, 缺一不可:

1. **离线证据**: 可复现脚本输出 (`<Blender>/blender.exe -b --factory-startup --python <脚本>`), 有数字对比;
2. **游戏内肉眼验收**: 导出成功不等于模型是好的 (权重错 -> 变形穿模, 切线错 -> 光影歪, 材质槽错 -> 贴图错位, 包围盒错 -> 部件消失)。

参照实现做等价性对比是唯一低风险的接法 (SB3U vs 自研产物逐字段比对), 见 `docs/performance.md`。

## 优先级

- **近期** (零算法风险, 全落在"用得了"): 9 个手动按钮点击时弹"该做什么"的说明; 自动缩裹烘焙 / 导出的进度条 + 长任务日志;
  权重映射的未归组顶点提醒与骨骼名正则匹配。共同点是不碰任何既有算法。
- **后续** (按用户反馈): 贴合参数自动优化 + 动骨接骨自动匹配 (判定客观, 但要用真实模型库调, 否则规则必然过拟合) ->
  服装语义分类 + 脖子接缝对齐 -> 贴图链 / 卡数据小补全 -> 第二状态半自动 + 饰品写卡 -> SB3U 替代 (最后, 收益只有 1.9s, 见 `docs/performance.md`)。
- 瓶颈不是"写不出算法", 而是**没有验收样本**: 贴合 / 分类 / 接骨的正确性只能在游戏里肉眼看, 离线测不出来。
