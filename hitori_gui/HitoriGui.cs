using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Sockets;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using BepInEx;
using BepInEx.Configuration;
using ChaCustom;
using Illusion.Game;
using KKAPI.Maker;
using KKAPI.Maker.UI.Sidebar;
using Manager;
using UnityEngine;

namespace HitoriGui
{
    /// <summary>捏人界面按钮组 + 读卡热重载</summary>
    [BepInPlugin(Guid, "Hitori GUI", Version)]
    [BepInProcess("KoikatsuSunshine")]
    [BepInDependency("marco.kkapi", BepInDependency.DependencyFlags.SoftDependency)]
    public class HitoriGui : BaseUnityPlugin
    {
        public const string Guid = "hitori.gui";
        public const string Version = "1.5.1";

        private const int WindowId = 0x48695447;
        private const int ButtonCount = 3;
        private const float ButtonWidth = 110f;
        private const float ButtonHeight = 26f;
        private const float ButtonGap = 3f;
        private const float ButtonStep = ButtonHeight + ButtonGap;
        private const float Pad = 10f;
        private const float DragBarHeight = 18f;
        private const float PanelWidth = ButtonWidth + Pad * 2f;
        private const float PanelHeight = DragBarHeight + Pad * 2f + ButtonHeight + ButtonStep * (ButtonCount - 1);
        private const float AutoMarginX = 320f;
        private const float AutoMarginY = 80f;

        /// <summary>Blender 侧发读卡指令的端口, 与 hitori_addon/card.py 保持一致</summary>
        private const int ReloadPort = 14145;

        /// <summary>ClearCache 指令等主线程卸载 mod 的超时, 毫秒</summary>
        private const int ClearTimeoutMs = 5000;

        private ConfigEntry<bool> _enabled;
        private ConfigEntry<string> _cardFolder;
        private ConfigEntry<float> _windowX;
        private ConfigEntry<float> _windowY;

        private SidebarToggle _toggle;
        private bool _windowPlaced;
        private Rect _windowRect;

        private TcpListener _listener;
        private volatile string _pendingCard;

        /// <summary>由监听线程置位, 主线程 Update 里执行: AssetBundle.Unload 属主线程操作</summary>
        private volatile bool _pendingClear;

        /// <summary>本次要定向释放的 zipmod 全路径, null/空 = 全量(手动按钮 / ClearCache 指令)</summary>
        private volatile string _pendingClearPath;

        /// <summary>主线程卸完 mod 后置位, 让还在等的 ClearCache 指令回包</summary>
        private readonly ManualResetEventSlim _clearDone = new ManualResetEventSlim(false);

        /// <summary>懒解析 Sideloader ZipmodInfo 的 _zipFile 字段, 避免每个 zipmod 都 GetField 一次</summary>
        private static FieldInfo _zipFileField;

        private void Awake()
        {
            _enabled = Config.Bind("General", "Enabled", true, "移植功能默认启用");
            _cardFolder = Config.Bind("General", "Card folder", "chara/female", "相对 UserData 的卡目录");
            _windowX = Config.Bind("UI", "Window X", -1f, "面板左上角 X, -1 = 自动放右下角; 拖动面板后自动写回这里");
            _windowY = Config.Bind("UI", "Window Y", -1f, "面板左上角 Y, -1 = 自动放右下角; 拖动面板后自动写回这里");

            try
            {
                MakerAPI.MakerBaseLoaded += OnMakerBaseLoaded;
            }
            catch (Exception e)
            {
                Logger.LogError("需要 KKSAPI, 侧边栏开关无法创建: " + e.Message);
            }

            StartReloadListener();
            Logger.LogInfo("Hitori GUI " + Version + " loaded");
        }

        private void OnDestroy()
        {
            try
            {
                _listener?.Stop();
            }
            catch (Exception)
            {
                // 监听线程退出时会抛异常, 忽略
            }
        }

        private void Update()
        {
            if (_pendingClear)
            {
                var clearPath = _pendingClearPath;
                _pendingClearPath = null;
                _pendingClear = false;
                ClearModCache(clearPath);
                _clearDone.Set();
            }

            ConsumePendingCard();
        }

        private void OnGUI()
        {
            if (_toggle == null || !_toggle.Value || !InMaker()) return;

            if (!_windowPlaced)
            {
                _windowRect = new Rect(
                    _windowX.Value >= 0f ? _windowX.Value : Screen.width - PanelWidth - AutoMarginX,
                    _windowY.Value >= 0f ? _windowY.Value : Screen.height - PanelHeight - AutoMarginY,
                    PanelWidth,
                    PanelHeight);
                ClampToScreen();
                _windowPlaced = true;
            }

            _windowRect = GUI.Window(WindowId, _windowRect, DrawPanel, GUIContent.none, GUI.skin.window);

            // 拖动结束后把位置写回配置
            if ((_windowRect.x != _windowX.Value || _windowRect.y != _windowY.Value) && !Input.GetMouseButton(0))
            {
                _windowX.Value = _windowRect.x;
                _windowY.Value = _windowRect.y;
                Config.Save();
            }
        }

        private void OnMakerBaseLoaded(object sender, RegisterCustomControlsEvent e)
        {
            _toggle = e.AddSidebarControl(new SidebarToggle("移植功能", _enabled.Value, this));
        }

        private void ClampToScreen()
        {
            _windowRect.x = Mathf.Clamp(_windowRect.x, 0f, Mathf.Max(0f, Screen.width - PanelWidth));
            _windowRect.y = Mathf.Clamp(_windowRect.y, 0f, Mathf.Max(0f, Screen.height - PanelHeight));
        }

        private void DrawPanel(int id)
        {
            var y = Pad + DragBarHeight;
            if (GUI.Button(new Rect(Pad, y, ButtonWidth, ButtonHeight), "Load Newest"))
                LoadNewestCard();
            y += ButtonStep;
            if (GUI.Button(new Rect(Pad, y, ButtonWidth, ButtonHeight), "Save Newest"))
                WriteNewestCard();
            y += ButtonStep;
            if (GUI.Button(new Rect(Pad, y, ButtonWidth, ButtonHeight), "Release Mods"))
                ReleaseMods();

            GUI.DragWindow(new Rect(0f, 0f, PanelWidth, Pad + DragBarHeight));
        }

        /// <summary>读取卡目录里最新修改的一张卡</summary>
        private void LoadNewestCard()
        {
            try
            {
                var dir = GetCardDir();
                var newest = GetNewestCard(dir);
                if (newest == null)
                {
                    Logger.LogWarning("卡目录里没有卡: " + dir.FullName);
                    return;
                }

                Utils.Sound.Play(SystemSE.ok_s);
                _pendingCard = newest.FullName;
                Logger.LogInfo("读取最新卡: " + newest.Name);
            }
            catch (Exception e)
            {
                Logger.LogError("读取最新卡失败: " + e);
            }
        }

        /// <summary>把当前捏人角色写进最新的那张卡, 旧卡移入回收站</summary>
        private void WriteNewestCard()
        {
            try
            {
                var dir = GetCardDir();
                var newest = GetNewestCard(dir);
                if (newest == null)
                {
                    Logger.LogWarning("卡目录里没有卡, 无法写入: " + dir.FullName);
                    return;
                }

                var chaCtrl = Singleton<CustomBase>.Instance.chaCtrl;
                if (chaCtrl == null || chaCtrl.chaFile == null)
                {
                    Logger.LogWarning("拿不到当前捏人角色");
                    return;
                }

                // pngData 为空时 SaveFile 不写 png 段, 出来的文件头直接是数据段, 系统和游戏都当它不是图片;
                // 读卡不带卡面的插件(CharacterReplacer 等)会留下这种角色
                if (chaCtrl.chaFile.pngData == null || chaCtrl.chaFile.pngData.Length == 0)
                {
                    Utils.Sound.Play(SystemSE.cancel);
                    Logger.LogMessage("No card image, save cancelled. Take a photo first.");
                    return;
                }

                // 旧卡先进回收站; 失败就放弃, 不能直接覆盖把旧卡弄丢
                var error = Recycle(newest.FullName);
                if (error != 0)
                {
                    Utils.Sound.Play(SystemSE.cancel);
                    Logger.LogError(string.Format("旧卡移入回收站失败(0x{0:X}), 已取消写入: {1}", error, newest.FullName));
                    return;
                }

                if (chaCtrl.chaFile.SaveCharaFile(newest.FullName, byte.MaxValue, false))
                {
                    Utils.Sound.Play(SystemSE.ok_s);
                    Logger.LogInfo("写入最新卡片: " + newest.Name);
                }
                else
                {
                    Utils.Sound.Play(SystemSE.cancel);
                    Logger.LogError("写入最新卡片失败: " + newest.FullName);
                }
            }
            catch (Exception e)
            {
                Logger.LogError("写入最新卡片失败: " + e);
            }
        }

        private DirectoryInfo GetCardDir()
        {
            return new DirectoryInfo(Path.Combine(UserData.Path, _cardFolder.Value));
        }

        private FileInfo GetNewestCard(DirectoryInfo dir)
        {
            if (dir == null || !dir.Exists) return null;
            return dir.GetFiles("*.png").OrderByDescending(f => f.LastWriteTimeUtc).FirstOrDefault();
        }

        private static bool InMaker()
        {
            var names = Scene.NowSceneNames;
            return names != null && names.Any(x => x == "CustomScene");
        }

        /// <summary>起一个后台线程收 Blender 的指令("ReadCard 路径" / "ClearCacheReadCard 路径" / "ClearCache" / "ClearCacheOne 路径")</summary>
        private void StartReloadListener()
        {
            try
            {
                _listener = new TcpListener(IPAddress.Loopback, ReloadPort);
                _listener.Start();
            }
            catch (Exception e)
            {
                Logger.LogError("读卡监听启动失败(端口 " + ReloadPort + "): " + e.Message);
                return;
            }

            var thread = new Thread(ReloadLoop) { IsBackground = true, Name = "HitoriReload" };
            thread.Start();
        }

        private void ReloadLoop()
        {
            while (true)
            {
                try
                {
                    using (var client = _listener.AcceptTcpClient())
                    {
                        try
                        {
                            var buffer = new byte[4096];
                            var stream = client.GetStream();
                            stream.ReadTimeout = 2000;
                            var count = stream.Read(buffer, 0, buffer.Length);
                            if (count <= 0) continue;

                            var reply = ProcessReloadMessage(Encoding.UTF8.GetString(buffer, 0, count));
                            var data = Encoding.UTF8.GetBytes(reply);
                            stream.Write(data, 0, data.Length);
                        }
                        catch (Exception e)
                        {
                            Logger.LogWarning("处理读卡指令失败: " + e.Message);
                        }
                    }
                }
                catch (Exception)
                {
                    // listener.Stop() 会让 AcceptTcpClient 抛异常, 到这里就结束线程
                    return;
                }
            }
        }

        private string ProcessReloadMessage(string message)
        {
            var parts = message.Split(new[] { ' ' }, 2);
            var command = parts[0];
            var path = parts.Length > 1 ? parts[1] : string.Empty;

            if (command == "ClearCacheReadCard")
            {
                // 清缓存要回主线程做, 不在这里直接调
                _pendingClearPath = null;
                _pendingClear = true;
                _pendingCard = path;
            }
            else if (command == "ReadCard")
            {
                _pendingCard = path;
            }
            else if (command == "ClearCache")
            {
                // 等主线程真卸完再回包: Blender 拿到回包才去替换 zipmod 文件
                _clearDone.Reset();
                _pendingClearPath = null;
                _pendingClear = true;
                return _clearDone.Wait(ClearTimeoutMs) ? "ClearCache ok" : "ClearCache timeout";
            }
            else if (command == "ClearCacheOne")
            {
                // 定向: 只卸这一个 zipmod 提供的 bundle + 只关它自己的 zip 句柄
                _clearDone.Reset();
                _pendingClearPath = path;
                _pendingClear = true;
                return _clearDone.Wait(ClearTimeoutMs) ? "ClearCacheOne ok" : "ClearCacheOne timeout";
            }

            return message;
        }

        /// <summary>手动释放 mod: 清 AssetBundle 缓存 + 关 zipmod 文件句柄, 之后就能替换 zipmod 文件, 不必等 Blender 侧发 ClearCache</summary>
        private void ReleaseMods()
        {
            ClearModCache();
            Utils.Sound.Play(SystemSE.ok_s);
            Logger.LogMessage("已手动释放 mod, 现在可以替换 zipmod 文件");
        }

        /// <summary>主线程执行: 清 AssetBundle 缓存 + 关掉 zipmod 文件句柄; AssetBundle 卸载后 Unity 才放开流式加载的 zipmod, Sideloader 的 zip 句柄也得自己关
        /// zipmodPath 为空 = 全量(手动按钮 / ClearCache 指令), 非空 = 只放这一个 mod(热重载用)</summary>
        private void ClearModCache(string zipmodPath = null)
        {
            var stopwatch = Stopwatch.StartNew();

            if (!string.IsNullOrEmpty(zipmodPath))
            {
                var zipmodInfo = FindZipmodEntry(FindZipmodDictionary(), zipmodPath);
                if (zipmodInfo == null)
                {
                    Logger.LogWarning("定向清缓存没匹配到 zipmod, 退全量: " + zipmodPath);
                }
                else
                {
                    var bundlePaths = GetZipmodBundlePaths(zipmodInfo);
                    var unloadedOne = UnloadBundles(bundlePaths);
                    var hadHandle = HasZipmodHandle(zipmodInfo);
                    (zipmodInfo as IDisposable)?.Dispose();
                    Logger.LogMessage(string.Format(
                        "定向清缓存: {0}, bundles={1}, unloaded={2}, handle={3}, elapsed={4}ms",
                        zipmodPath, bundlePaths.Count, unloadedOne, hadHandle ? 1 : 0, stopwatch.ElapsedMilliseconds));
                    return;
                }
            }

            var unloaded = UnloadBundles(null);
            DisposeZipmodHandles();
            Logger.LogMessage(string.Format("Mod 已重载: {0}, elapsed={1}ms", unloaded, stopwatch.ElapsedMilliseconds));
        }

        /// <summary>卸掉 manifest 里这些名字对应的 AssetBundle, bundlePaths 为 null 表示全部; 返回卸载个数</summary>
        private int UnloadBundles(ICollection<string> bundlePaths)
        {
            var unloaded = 0;
            try
            {
                foreach (var pack in AssetBundleManager.ManifestBundlePack)
                {
                    // 快照 keys: UnloadAssetBundle 会边遍历边从字典里删
                    foreach (var bundleName in pack.Value.LoadedAssetBundles.Keys.ToList())
                    {
                        if (bundlePaths != null && !bundlePaths.Contains(bundleName)) continue;
                        AssetBundleManager.UnloadAssetBundle(bundleName, true, pack.Key, false);
                        unloaded++;
                    }
                }
            }
            catch (Exception e)
            {
                Logger.LogError("重载 mod 失败: " + e);
            }

            return unloaded;
        }

        /// <summary>从 Sideloader 的 Zipmods 里按全路径找 zipmod(大小写不敏感), 找不到返回 null</summary>
        private static object FindZipmodEntry(IDictionary zipmods, string zipmodPath)
        {
            if (zipmods == null) return null;

            var fullPath = zipmodPath;
            try
            {
                fullPath = Path.GetFullPath(zipmodPath);
            }
            catch (Exception)
            {
                // 路径不合法就只按原样比
            }

            foreach (DictionaryEntry entry in zipmods)
            {
                var key = entry.Key as string;
                if (key == null) continue;
                if (string.Equals(key, zipmodPath, StringComparison.OrdinalIgnoreCase)
                    || string.Equals(key, fullPath, StringComparison.OrdinalIgnoreCase))
                {
                    return entry.Value;
                }
            }

            return null;
        }

        /// <summary>反射取这个 zipmod 提供的 bundle 名(BundleTrimmedPath), 正好是 AssetBundleManager 里 LoadedAssetBundles 的 key</summary>
        private static HashSet<string> GetZipmodBundlePaths(object zipmodInfo)
        {
            var bundlePaths = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            var field = zipmodInfo.GetType().GetField("BundleInfos", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
            var bundleInfos = field?.GetValue(zipmodInfo) as IEnumerable;
            if (bundleInfos == null) return bundlePaths;

            foreach (var info in bundleInfos)
            {
                var property = info.GetType().GetProperty("BundleTrimmedPath", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                var path = property?.GetValue(info) as string;
                if (!string.IsNullOrEmpty(path)) bundlePaths.Add(path);
            }

            return bundlePaths;
        }

        /// <summary>关掉 Sideloader 打开的 zipmod 文件句柄; 它把压缩过的 zipmod 读进内存后不关句柄, 游戏跑着时就替换不掉这个文件, 只能反射它的 Zipmods</summary>
        private void DisposeZipmodHandles()
        {
            try
            {
                var zipmods = FindZipmodDictionary();
                if (zipmods == null) return;

                var closed = 0;
                foreach (DictionaryEntry entry in zipmods)
                {
                    var disposable = entry.Value as IDisposable;
                    if (disposable == null) continue;
                    // 大多数 ZipmodInfo 的 _zipFile 是 null(没被用到过), Dispose 是空操作, 不能都算成关了一个
                    if (!HasZipmodHandle(entry.Value)) continue;
                    disposable.Dispose();
                    closed++;
                }

                Logger.LogMessage("已关闭 zipmod 句柄: " + closed);
            }
            catch (Exception e)
            {
                Logger.LogWarning("关闭 zipmod 句柄失败: " + e.Message);
            }
        }

        /// <summary>ZipmodInfo 的 _zipFile 非 null 才说明真占着这个 zipmod 的文件句柄</summary>
        private static bool HasZipmodHandle(object zipmodInfo)
        {
            if (_zipFileField == null)
            {
                _zipFileField = zipmodInfo.GetType().GetField("_zipFile", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                if (_zipFileField == null) return false;
            }

            return _zipFileField.GetValue(zipmodInfo) != null;
        }

        /// <summary>反射取 Sideloader 的 Zipmods 字典, 取不到(没装)返回 null</summary>
        private static IDictionary FindZipmodDictionary()
        {
            foreach (var assembly in AppDomain.CurrentDomain.GetAssemblies())
            {
                try
                {
                    var sideloader = assembly.GetType("Sideloader.Sideloader", false);
                    var field = sideloader?.GetField("Zipmods", BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic);
                    var zipmods = field?.GetValue(null) as IDictionary;
                    if (zipmods != null) return zipmods;
                }
                catch (Exception)
                {
                    // 个别程序集取类型会抛异常, 跳过继续找
                }
            }

            return null;
        }

        /// <summary>主线程消费待读卡路径, 用游戏原生的读卡接口把卡载进当前捏人角色</summary>
        private void ConsumePendingCard()
        {
            var path = _pendingCard;
            if (path == null) return;
            _pendingCard = null;

            if (!InMaker())
            {
                Logger.LogWarning("不在捏人界面, 忽略读卡: " + path);
                return;
            }

            try
            {
                var chaCtrl = Singleton<CustomBase>.Instance.chaCtrl;
                if (chaCtrl == null || chaCtrl.chaFile == null)
                {
                    Logger.LogWarning("拿不到当前捏人角色, 忽略读卡: " + path);
                    return;
                }

                var sex = chaCtrl.sex;
                if (!LoadCardFile(chaCtrl.chaFile, path, sex))
                {
                    Logger.LogError("读卡失败(错误码 " + chaCtrl.chaFile.GetLastErrorCode() + "): " + path);
                    return;
                }

                // 性别不符时按当前编辑模式强制改回, 否则角色会重建
                if (chaCtrl.chaFile.parameter.sex != sex) chaCtrl.chaFile.parameter.sex = sex;

                chaCtrl.ChangeCoordinateType(true);
                chaCtrl.Reload(false, false, false, false);
                Singleton<CustomBase>.Instance.updateCustomUI = true;
                Logger.LogInfo("已重载人物卡: " + path);
            }
            catch (Exception e)
            {
                Logger.LogError("重载人物卡失败: " + e);
            }
        }

        /// <summary>把 KKS 人物卡读进 ChaFileControl, 成功返回 true</summary>
        private bool LoadCardFile(ChaFileControl chaFile, string path, byte sex)
        {
            var before = chaFile.pngData;
            chaFile.LoadFileLimited(path, sex, true, true, true, true, true, true);
            return chaFile.pngData != before;
        }

        /// <summary>SHFileOperation: 删除到回收站, 返回 0 表示成功</summary>
        private static int Recycle(string path)
        {
            var op = new SHFILEOPSTRUCT
            {
                wFunc = FO_DELETE,
                pFrom = path + "\0",
                fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI,
            };
            return SHFileOperation(ref op);
        }

        private const uint FO_DELETE = 0x0003;
        private const ushort FOF_SILENT = 0x0004;
        private const ushort FOF_NOCONFIRMATION = 0x0010;
        private const ushort FOF_ALLOWUNDO = 0x0040;
        private const ushort FOF_NOERRORUI = 0x0400;

        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
        private struct SHFILEOPSTRUCT
        {
            public IntPtr hwnd;
            public uint wFunc;
            [MarshalAs(UnmanagedType.LPWStr)] public string pFrom;
            [MarshalAs(UnmanagedType.LPWStr)] public string pTo;
            public ushort fFlags;
            [MarshalAs(UnmanagedType.Bool)] public bool fAnyOperationsAborted;
            public IntPtr hNameMappings;
            [MarshalAs(UnmanagedType.LPWStr)] public string lpszProgressTitle;
        }

        [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
        private static extern int SHFileOperation(ref SHFILEOPSTRUCT lpFileOp);
    }
}
