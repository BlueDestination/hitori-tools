# 人物卡格式与元数据

解析代码在 `hitori_addon/card.py`, msgpack 用自带的纯 python 实现 `hitori_addon/msgpack.py`
(Blender 自带的 python 3.10 没有 msgpack 库, 不能 `import msgpack`)。

## 自带 msgpack 的限制

- `packb` 一律用最短编码 / float64 / str 与 bytes 分开: 能逐字节复刻游戏写出的条目(游戏也是最短编码),
  但**重 pack 旧数据一定会改字节**。所以只对自己负责的条目重新 pack, 其他插件 / 其他子块一律原样搬。
- `unpackb` 只解第一个对象, 忽略末尾多余字节 - UAR 的 `info` 就是把连续字节逐条拆开用的;
  也意味着不能靠它判断"后面还有没有多余数据"。
- dict 保留插入顺序, 想复刻字段顺序就按声明顺序构造 dict(游戏写出的 `ResolveInfo` 就是靠这个一比一复刻的)。
- 没有 ext / timestamp, float 只会写成 float64; 卡里用不到, 遇到会 `raise ValueError`。

## 顶层布局

KKS 人物卡 = 缩略图 PNG + 小端二进制尾巴:

```
[PNG 分块 ... IEND + 4B CRC]
[int32 productNo = 100]
[u8 长度 + 【KoiKatuCharaSun】(UTF-8, 21 字节)]
[u8 长度 + 版本串 "0.0.0"]
[int32 block0 长度 + block0 = 240x320 缩略图 PNG]
[int32 block1 长度 + block1 = lstInfo]
[int32 block2 长度 + block2 = 全部角色数据 + KKEx]
```

- `skip_thumbnail_png(card)` 跳过缩略图, 返回 IEND + CRC 之后的偏移。
- `parse_card_offsets(card)` 返回 `(block1 起点, block1 终点, block2 长度前缀偏移, block2 内容起点)`。
- 块长度都是 int32 小端。
- 官方 KK (非 Sunshine) 卡与 KKS 卡只差三处: 标记少一个 `Sun` (7bit 长度前缀 21 -> 18), lstInfo 里 `Parameter` 条目的版本号,
  以及 Parameter 数据块自己的版本号 (都是 0.0.6 -> 0.0.5); 转换入口 `convert_kks_card_to_kk(card) -> bytes`。

## block1 = lstInfo

msgpack `{"lstInfo": [{name, version, pos, size}, ...]}`, 6 条(顺序不固定):
`Custom / Coordinate / Parameter / Status / About / KKEx`。
每条 `pos` 以 **block2 内容起点 + 4** 为原点, `size` 是子块字节数。

## block2 = 角色数据本体

```
block2 = [4 字节 00 00 00 00] + Custom + Coordinate + Parameter + Status + About + KKEx
```

- **记录长度 = 物理长度 - 4** (少算开头 4 个 0); 也就是 `recorded == KKEx.pos + KKEx.size`,
  KKEx 物理起点 = `block2 内容起点 + 4 + KKEx.pos` = `文件长度 - KKEx.size`, 一直延伸到文件末尾。
- `Custom` = `[int32 Face 长度 + Face msgpack] + [int32 Body 长度 + Body] + [int32 Hair 长度 + Hair]`,
  Face 数据起点 = `block2 内容起点 + 8`。
- Face 里是脸的形状和五官 ID(见下), 是角色卡最常改的部分。

## KKEx = 插件数据

msgpack map `{插件 GUID: [版本, 数据]}`。用 `find_kkex_entry` 定位, 增改只动这一层, 其他插件的字节原样保留。

- **新增条目必须重写 map header**: header 里记着键值对数量, 做法是
  `msgpack.pack_map_header(n + 1) + kkex[map_header_end:] + packb(GUID) + packb(值)`; 直接 append 会解析失败。
  `find_kkex_entry` 返回的 `entry_count` / `map_header_end` 就是给这个用的。
- 条目的**值只能整块重建**(msgpack 不支持就地增长): 统一走 `write_kkex_entry(card_path, guid, build_value)`,
  传 `build_value(原值) -> 新值` 的回调, 长度字段由它一处同步。

## KSOX (Skin Overlay Mod)

- `KSOX = [版本=2, {"_TextureID_<id>": 图片字节(PNG), "Lookup": bin(msgpack {服装号: {类型: 贴图 ID}})}]`
- `TexType` 常用值: BodyOver=1, FaceOver=2, BodyUnder=3, FaceUnder=4, EyeUnder=5, EyeOver=6,
  EyeUnderL=7, **EyeOverL=8**, EyeUnderR=9, **EyeOverR=10** (瞳孔 / 虹膜 = EyeOverL / EyeOverR)。
- 写入口: `set_pupil_overlay(card_path, image, right_image=None, texture_id=8172635, coordinates=None)`;
  右眼单独贴图用 `texture_id + 1`, 已存在的 KSOX 会合并而不是覆盖。

## UAR (Sideloader 自动解析信息)

- KKEx 里的 GUID 是 `com.bepis.sideloader.universalautoresolver`, 结构是
  `[版本=0, {"info": [每条 ResolveInfo 的 msgpack 字节]}]`。
- 一条 `ResolveInfo` = `{ModID: zipmod GUID, Slot: zipmod 里的 ID, LocalSlot: 本机解析 ID,
  Property: StructReference 里的属性名, CategoryNo: 列表号, Author / Website / Name: manifest 里的值}`。
- **用 zipmod 物品时 id 和解析信息要一起写**: 卡里存的是 `Slot`(zipmod 自己的 ID), 加载时按
  `ModID + Slot + Property + CategoryNo` 查本机的 `LocalSlot` 再替换; `LocalSlot` 只在解析不到时回退, 各家不同。
- 写入口: `set_pupil_resolve_info()` 把左右眼瞳孔指向 No Iris, 属性名是 `ChaFileFace.Pupil1` / `Pupil2`
  (categoryNo 408); 每张卡只留一份, 已有的其它瞳孔解析信息会被替换掉。
- `info` 里的每一条是**已经序列化好的 msgpack 字节**, 不是嵌套结构: 读取时逐条 `unpackb` 判断,
  写回时没动的条目**原字节照搬**, 只重新 pack 要替换的那两条; 判定同一个字段用 `Property`,
  同属性可能有多条(不同 zipmod / 换过 mod 的卡), 去重后再写。
- `LocalSlot` 因机而异, 不许照抄别人卡里的值; 卡里只有 `Slot`(zipmod 自己的 ID) 是有意义的。
- 参考: `IllusionMods/BepisPlugins` 的 `Core.UAR.cs`(`ResolveStructure`) 和 `Core.UAR.Hooks.cs`(`ExtendedCardSave`)。

## zipmod 里查信息

- `.zipmod` 就是普通 zip: `manifest.xml`(GUID / Name / Version / Author)、
  `abdata/list/characustom/<作者>/*.csv`(第一行是 categoryNo, 之后每行 `ID,0,1,名称,assetbundle,资源名,...`)、
  `abdata/chara/<作者>/*.unity3d`(贴图 / 模型)。
- 光看 ID 分不出物品来自基础表还是 mod: `[DeathWeasel] No Iris` 的 1 和基础表 `タイプ２` 同为 1,
  只有 UAR 解析信息能区分, 这就是上一条"id 和解析信息要一起写"的原因。
- 别对整个 `mods/` 目录 grep(本机 5000+ 个 zipmod, 会卡死), 按作者目录定位。

## Face 里的重要元数据(官方五官 ID)

`pupil` = `PupilInfo[2]`(左/右), 每项 `{id, baseColor, subColor, gradMaskId, gradBlend, gradOffsetY, gradScale}`。
这些 ID 都指向 `abdata/list/characustom/*.unity3d` 里的列表(categoryNo 见下), maker 里就是对应的下拉框:

| 字段 | categoryNo | 列表 |
|---|---|---|
| `pupil[].id` | 408 | mt_eye (瞳孔) |
| `pupil[].gradMaskId` | 409 | mt_eye_gradation |
| `hlUpId` / `hlDownId` | 410 / 411 | mt_eye_hi_up / mt_eye_hi_down (高光) |
| `whiteId` | 407 | mt_eye_white (眼白) |
| `eyelineUpId` / `eyelineDownId` | 412 / 413 | mt_eyeline_up / mt_eyeline_down (眼线) |
| `eyebrowId` | 406 | mt_eyebrow (眉毛) |

其余: mt_face_detail=400, mt_eyeshadow=401, mt_cheek=402, mt_lip=403, mt_lipline=404,
mt_face_paint=405, mt_nose=414, mt_mole=415, face_preset=416。

- 列表不是 CSV, 是 `*.unity3d` 里的 TextAsset, 用 Blender 环境里的 UnityPy 读;
  翻译在 `BepInEx/translation/zh-CN/...`。
- **「官方瞳孔 = 无」= `[DeathWeasel] No Iris` zipmod**(`com.DeathWeasel.NoIris`) 的 `None`:
  `pupil[].id = 1`(zipmod 的 `abdata/list/characustom/deathweasel/no_iris.csv` 里的 ID) +
  KKEx 里对应的 UAR 解析信息, 两者缺一不可 - 没有解析信息时 id 1 会被基础表 mt_eye 的 `タイプ２` 占住。
  `NO_IRIS_*` 常量, `set_official_pupil_no_iris(card_path)` 改写左右眼并同步长度字段。
- moderchan 的 `なし`(id 1919) 和 `[RM50] None`(id 5055001) 都不能直接用: 前者要装 moderchan 的插件,
  后者没汉化。排查别人的卡时记得区分。
- Face 里的字段是**用固定字节模式定位**的, 不是按 key 名走 msgpack: `\xa5pupil\x92`(键 `pupil` + fixarray(2)),
  `\x88\xa2id`(8 键 map 的第一个键)。它们写死了键数 / 数组长度 / 字段顺序, 换插件或换版本就可能匹配不到 -
  匹配失败必须报错, 不能"差不多"地写; 要更稳就得老老实实按 msgpack 结构走一遍。

## 改卡的规则

1. **优先不改数据长度**: 能就地改就就地改 - msgpack 允许非最短编码, `encode_int_like` 把新值写成和旧值同样字节数
   (1 可以写成 `01` / `cc01` / `cd0001` / `ce00000001`), 这样不用动任何 pos / size。
2. 值放不进原宽度时(如 `pupil.id` 从 10 改成 1919, 每个 +2 字节)必须同步全部长度字段:
   `set_pupil_ids` 的做法是把 Custom 里 Face 的长度前缀、lstInfo 里 Custom 的 size 和
   Coordinate/Parameter/Status/About/KKEx 的 pos、block2 的长度前缀, 一起加上 delta
   (delta 为负时同样适用, 例如 1919 → 1 每个缩 2 字节)。
3. **幂等 + 最小改动**: 先比对, 没变就不写回(返回 False); 每个 `set_*` 都重新解析整卡, 别跨步骤复用偏移。
4. 改完用游戏自己的 `ChaFile.LoadFile` 验收(pythonnet 反射 `Assembly-CSharp.dll`): 先挂
   `AppDomain.AssemblyResolve`(搜 `<游戏>_Data/Managed` 和 `BepInEx/plugins`), 再 `Assembly.LoadFrom`,
   重载卡用 3 参数的 `ChaFile.LoadFile(路径, false, false)`; 别只看自己的解析。
5. 更强的验收是**拿游戏写出的卡当基准**: 在 maker 里手动选一次并存卡, 把差异 blob dump 出来和自己写的
   逐字节比对 - 我们写出的应该和游戏写出的**完全一样**(含字段顺序 / 键数), 只验"能 LoadFile"太弱。
6. **别用图片库重存人物卡**: 开头的 PNG 只是缩略图壳子, 数据在 IEND + CRC 之后, PIL 重存会丢尾巴;
   一律 `read_bytes()` / `write_bytes()` 整块处理。
7. 先在 `%TEMP%` 的副本上改, 别直接动用户的人物卡; 提交前跑一遍上面的验收。
8. 游戏重载往 `127.0.0.1:14145` 发指令 (自研 `HitoriGui` 监听), 发送成功会 beep:
   - 只重读人物卡(只写卡不写 mod 的操作)用 `reload_kk_card(card_path)`, 发 `ReadCard <路径>`, 快;
   - 更新完 mod 用 `update_and_refresh_mod(u3d_path)`: 先发 `ClearCacheOne <zipmod路径>` 只卸这一个 mod 再替换 zipmod,
     最后发 `ReadCard <路径>` 重读卡(不再发 `ClearCacheReadCard`, 那会再全量清一次);
     全量 `ClearCache` 会卸掉 100+ 个 bundle(含游戏本体), 只用于手动 "Release Mods" 按钮和旧版插件回退。
