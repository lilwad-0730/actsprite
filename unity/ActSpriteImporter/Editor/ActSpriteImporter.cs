using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Linq;
using UnityEditor;
using UnityEditor.Animations;
using UnityEditor.U2D.Sprites;
using UnityEngine;

namespace ActSprite.EditorTools
{
    // <name>_meta.json, the contract shared with the Python pipeline (docs/02_product_spec.md 4.3).
    [Serializable] internal class MetaCell { public int width; public int height; }
    [Serializable] internal class MetaPivot { public float x = 0.5f; public float y; }
    [Serializable] internal class MetaAction { public string name; public int row; public int frames; public float fps; public bool loop; }
    [Serializable]
    internal class SpriteMeta
    {
        public string character;
        public string style;
        public MetaCell cell;
        public MetaPivot pivot;
        public MetaAction[] actions;
    }

    /// <summary>
    /// ActSprite ZIP -> sliced sprites, one AnimationClip per action, an Animator Controller and a character prefab.
    /// Menu: ActSprite > Import ZIP... An unzipped folder dropped into Assets is picked up automatically.
    /// </summary>
    public static class ActSpriteImporter
    {
        public const string CharactersRoot = "Assets/ActSprite/Characters";
        const string MetaSuffix = "_meta.json";
        const string SheetSuffix = "_sheet.png";
        const byte AlphaCutoff = 16;

        // Folders being written by ImportZip, so the auto-import hook leaves them alone.
        internal static readonly HashSet<string> Busy = new HashSet<string>();

        [MenuItem("ActSprite/Import ZIP...", priority = 0)]
        static void ImportZipMenu()
        {
            string zip = EditorUtility.OpenFilePanel("Import an ActSprite ZIP", "", "zip");
            if (string.IsNullOrEmpty(zip)) return;
            try
            {
                string prefab = ImportZip(zip);
                var asset = AssetDatabase.LoadAssetAtPath<GameObject>(prefab);
                Selection.activeObject = asset;
                EditorGUIUtility.PingObject(asset);
            }
            catch (Exception e)
            {
                EditorUtility.DisplayDialog("ActSprite import failed", e.Message, "OK");
                Debug.LogException(e);
            }
        }

        [MenuItem("ActSprite/Rebuild Selected Character", priority = 1)]
        static void RebuildSelectedMenu()
        {
            string path = AssetDatabase.GetAssetPath(Selection.activeObject);
            if (AssetDatabase.IsValidFolder(path))
                path = Directory.GetFiles(path, "*" + MetaSuffix).Select(p => p.Replace('\\', '/')).FirstOrDefault();
            if (string.IsNullOrEmpty(path) || !path.EndsWith(MetaSuffix, StringComparison.Ordinal))
            {
                EditorUtility.DisplayDialog("ActSprite", "Select a <name>_meta.json file or the folder that holds it.", "OK");
                return;
            }
            try { Build(path); }
            catch (Exception e)
            {
                EditorUtility.DisplayDialog("ActSprite rebuild failed", e.Message, "OK");
                Debug.LogException(e);
            }
        }

        /// <summary>Unpack the sheet and meta JSON from an ActSprite ZIP into Assets and build everything. Returns the prefab path.</summary>
        public static string ImportZip(string zipPath)
        {
            string folder, metaPath;
            using (ZipArchive zip = new ZipArchive(File.OpenRead(zipPath), ZipArchiveMode.Read))
            {
                ZipArchiveEntry metaEntry = zip.Entries
                    .Where(e => e.Name.EndsWith(MetaSuffix, StringComparison.Ordinal))
                    .OrderBy(e => e.FullName.Count(c => c == '/'))
                    .FirstOrDefault();
                if (metaEntry == null)
                    throw new InvalidDataException($"{Path.GetFileName(zipPath)} has no <name>{MetaSuffix}. Use a ZIP made by `python -m actsprite` or the ActSprite web app.");
                string baseName = metaEntry.Name.Substring(0, metaEntry.Name.Length - MetaSuffix.Length);
                string dir = metaEntry.FullName.Substring(0, metaEntry.FullName.Length - metaEntry.Name.Length);
                ZipArchiveEntry sheetEntry = zip.GetEntry(dir + baseName + SheetSuffix);
                if (sheetEntry == null)
                    throw new InvalidDataException($"{Path.GetFileName(zipPath)} has {metaEntry.FullName} but no {dir}{baseName}{SheetSuffix} next to it.");

                folder = $"{CharactersRoot}/{baseName}";
                Directory.CreateDirectory(folder);
                metaPath = $"{folder}/{baseName}{MetaSuffix}";
                Extract(metaEntry, metaPath);
                Extract(sheetEntry, $"{folder}/{baseName}{SheetSuffix}");
            }

            Busy.Add(folder);
            try
            {
                AssetDatabase.Refresh(ImportAssetOptions.ForceSynchronousImport);
                return Build(metaPath);
            }
            finally { Busy.Remove(folder); }
        }

        static void Extract(ZipArchiveEntry entry, string dest)
        {
            using (Stream src = entry.Open())
            using (FileStream dst = File.Create(dest))
                src.CopyTo(dst);
        }

        /// <summary>Build sprites, clips, controller and prefab from a <name>_meta.json inside Assets. Returns the prefab path.</summary>
        public static string Build(string metaPath)
        {
            metaPath = metaPath.Replace('\\', '/');
            string folder = Path.GetDirectoryName(metaPath).Replace('\\', '/');
            string fileName = Path.GetFileName(metaPath);
            string baseName = fileName.Substring(0, fileName.Length - MetaSuffix.Length);
            string sheetPath = $"{folder}/{baseName}{SheetSuffix}";

            SpriteMeta meta = ReadMeta(metaPath);
            Dictionary<string, Sprite> sprites = SliceSheet(sheetPath, meta);

            string outDir = $"{folder}/Generated";
            if (!AssetDatabase.IsValidFolder(outDir)) AssetDatabase.CreateFolder(folder, "Generated");

            var clips = new Dictionary<string, AnimationClip>();
            foreach (MetaAction a in meta.actions)
                clips[a.name] = WriteClip($"{outDir}/{baseName}_{a.name}.anim", Frames(sprites, a), a.fps, a.loop);

            MetaAction idle = Find(meta, "idle");
            MetaAction run = Find(meta, "run") ?? Find(meta, "walk");
            MetaAction jump = Find(meta, "jump");
            MetaAction[] extras = meta.actions.Where(a => a != idle && a != run && a != jump).ToArray();

            // No idle in the sheet: stand still on the first frame of the first action.
            AnimationClip idleClip = idle != null
                ? clips[idle.name]
                : WriteClip($"{outDir}/{baseName}_pose.anim", new[] { Frames(sprites, meta.actions[0])[0] }, 1f, true);

            string controllerPath = $"{outDir}/{baseName}.controller";
            AnimatorController controller = WriteController(controllerPath, idle?.name ?? "pose", idleClip,
                run, run != null ? clips[run.name] : null, jump, jump != null ? clips[jump.name] : null,
                extras.Select(a => (a.name, clips[a.name])).ToArray());

            MetaAction body = idle ?? run ?? meta.actions[0];
            string prefabPath = WritePrefab($"{folder}/{baseName}.prefab", outDir, baseName, meta, sheetPath,
                body, Frames(sprites, body)[0], controller, extras.Select(a => a.name).ToArray());

            AssetDatabase.SaveAssets();
            Debug.Log($"ActSprite: imported {baseName} - {sprites.Count} sprites, actions " +
                      string.Join(", ", meta.actions.Select(a => $"{a.name} ({a.frames} frames, {a.fps} fps{(a.loop ? ", loop" : "")})")) +
                      $". Prefab: {prefabPath}");
            return prefabPath;
        }

        // ---------- meta ----------

        static SpriteMeta ReadMeta(string metaPath)
        {
            SpriteMeta m;
            try { m = JsonUtility.FromJson<SpriteMeta>(File.ReadAllText(metaPath)); }
            catch (Exception e) { throw new InvalidDataException($"{metaPath} is not valid JSON: {e.Message}"); }
            string fix = " Re-export the character with `python -m actsprite`.";
            if (m == null || m.cell == null || m.cell.width <= 0 || m.cell.height <= 0)
                throw new InvalidDataException($"{metaPath}: \"cell\" needs a positive width and height.{fix}");
            if (m.actions == null || m.actions.Length == 0)
                throw new InvalidDataException($"{metaPath}: \"actions\" is empty.{fix}");
            if (m.pivot == null) m.pivot = new MetaPivot();
            var seen = new HashSet<string>();
            foreach (MetaAction a in m.actions)
            {
                if (string.IsNullOrWhiteSpace(a.name))
                    throw new InvalidDataException($"{metaPath}: every action needs a name.{fix}");
                if (!seen.Add(a.name))
                    throw new InvalidDataException($"{metaPath}: action \"{a.name}\" appears twice.{fix}");
                if (a.name == ActSpriteCharacter.SpeedParam || a.name == ActSpriteCharacter.GroundedParam)
                    throw new InvalidDataException($"{metaPath}: \"{a.name}\" is reserved for the Animator; rename the action.");
                if (a.frames <= 0 || a.fps <= 0 || a.row < 0)
                    throw new InvalidDataException($"{metaPath}: action \"{a.name}\" needs frames > 0, fps > 0 and row >= 0.{fix}");
            }
            return m;
        }

        static MetaAction Find(SpriteMeta m, string name) => m.actions.FirstOrDefault(a => a.name == name);

        static Sprite[] Frames(Dictionary<string, Sprite> sprites, MetaAction a) =>
            Enumerable.Range(0, a.frames).Select(i => sprites[FrameName(a.name, i)]).ToArray();

        static string FrameName(string action, int i) => $"{action}_{i:00}";

        // ---------- texture and slicing ----------

        static Dictionary<string, Sprite> SliceSheet(string sheetPath, SpriteMeta meta)
        {
            var importer = AssetImporter.GetAtPath(sheetPath) as TextureImporter;
            if (importer == null)
                throw new FileNotFoundException($"{sheetPath} is missing or is not an image. Keep <name>{SheetSuffix} next to the meta JSON.");
            importer.GetSourceTextureWidthAndHeight(out int texW, out int texH);
            int cw = meta.cell.width, ch = meta.cell.height;
            foreach (MetaAction a in meta.actions)
                if (a.frames * cw > texW || (a.row + 1) * ch > texH)
                    throw new InvalidDataException(
                        $"{sheetPath} is {texW}x{texH}, too small for \"{a.name}\" (row {a.row}, {a.frames} frames of {cw}x{ch}). The sheet and meta JSON do not match.");

            bool pixel = string.Equals(meta.style, "pixel", StringComparison.OrdinalIgnoreCase);
            importer.textureType = TextureImporterType.Sprite;
            importer.spriteImportMode = SpriteImportMode.Multiple;
            importer.spritePixelsPerUnit = ch;                // one cell = one unit tall
            importer.filterMode = pixel ? FilterMode.Point : FilterMode.Bilinear;
            importer.textureCompression = TextureImporterCompression.Uncompressed;
            importer.mipmapEnabled = false;
            importer.alphaIsTransparency = true;
            importer.wrapMode = TextureWrapMode.Clamp;
            importer.npotScale = TextureImporterNPOTScale.None;
            importer.maxTextureSize = Mathf.Clamp(Mathf.NextPowerOfTwo(Mathf.Max(texW, texH)), 2048, 16384);
            var settings = new TextureImporterSettings();
            importer.ReadTextureSettings(settings);
            settings.spriteMeshType = SpriteMeshType.FullRect;
            settings.spriteExtrude = 0;
            settings.spriteGenerateFallbackPhysicsShape = false;
            importer.SetTextureSettings(settings);
            importer.SaveAndReimport();

            var factories = new SpriteDataProviderFactories();
            factories.Init();
            ISpriteEditorDataProvider provider = factories.GetSpriteEditorDataProviderFromObject(importer);
            provider.InitSpriteEditorDataProvider();
            // Keep sprite IDs on a rebuild so scenes and clips that point at them stay connected.
            Dictionary<string, GUID> oldIds = provider.GetSpriteRects()
                .GroupBy(r => r.name).ToDictionary(g => g.Key, g => g.First().spriteID);

            var rects = new List<SpriteRect>();
            var pivot = new Vector2(meta.pivot.x, meta.pivot.y);
            foreach (MetaAction a in meta.actions)
            {
                for (int i = 0; i < a.frames; i++)
                {
                    string name = FrameName(a.name, i);
                    rects.Add(new SpriteRect
                    {
                        name = name,
                        rect = new Rect(i * cw, texH - (a.row + 1) * ch, cw, ch),   // row 0 is the top row
                        alignment = SpriteAlignment.Custom,
                        pivot = pivot,
                        spriteID = oldIds.TryGetValue(name, out GUID id) ? id : GUID.Generate(),
                    });
                }
            }
            provider.SetSpriteRects(rects.ToArray());
            var nameIds = provider.GetDataProvider<ISpriteNameFileIdDataProvider>();
            nameIds?.SetNameFileIdPairs(rects.Select(r => new SpriteNameFileIdPair(r.name, r.spriteID)));
            provider.Apply();
            importer.SaveAndReimport();

            Dictionary<string, Sprite> sprites = AssetDatabase.LoadAllAssetsAtPath(sheetPath).OfType<Sprite>()
                .GroupBy(s => s.name).ToDictionary(g => g.Key, g => g.First());
            string missing = rects.Select(r => r.name).FirstOrDefault(n => !sprites.ContainsKey(n));
            if (missing != null)
                throw new InvalidOperationException($"Unity did not create sprite {missing} from {sheetPath}. Try ActSprite > Rebuild Selected Character.");
            return sprites;
        }

        // ---------- animation ----------

        static AnimationClip WriteClip(string path, Sprite[] frames, float fps, bool loop)
        {
            var clip = AssetDatabase.LoadAssetAtPath<AnimationClip>(path);
            bool isNew = clip == null;
            if (isNew) clip = new AnimationClip();
            clip.frameRate = fps;

            // One key per frame, plus a closing key so the last frame is shown for a full 1/fps.
            var keys = new ObjectReferenceKeyframe[frames.Length + 1];
            for (int i = 0; i < frames.Length; i++)
                keys[i] = new ObjectReferenceKeyframe { time = i / fps, value = frames[i] };
            keys[frames.Length] = new ObjectReferenceKeyframe { time = frames.Length / fps, value = frames[frames.Length - 1] };
            var binding = EditorCurveBinding.PPtrCurve("", typeof(SpriteRenderer), "m_Sprite");
            AnimationUtility.SetObjectReferenceCurve(clip, binding, keys);

            AnimationClipSettings s = AnimationUtility.GetAnimationClipSettings(clip);
            s.loopTime = loop;
            AnimationUtility.SetAnimationClipSettings(clip, s);

            if (isNew) AssetDatabase.CreateAsset(clip, path);
            else EditorUtility.SetDirty(clip);
            return clip;
        }

        static AnimatorController WriteController(string path, string idleName, AnimationClip idleClip,
            MetaAction run, AnimationClip runClip, MetaAction jump, AnimationClip jumpClip,
            (string name, AnimationClip clip)[] extras)
        {
            if (AssetDatabase.LoadAssetAtPath<AnimatorController>(path) != null) AssetDatabase.DeleteAsset(path);
            AnimatorController c = AnimatorController.CreateAnimatorControllerAtPath(path);
            c.AddParameter(ActSpriteCharacter.SpeedParam, AnimatorControllerParameterType.Float);
            c.AddParameter(ActSpriteCharacter.GroundedParam, AnimatorControllerParameterType.Bool);
            AnimatorControllerParameter[] ps = c.parameters;
            ps[1].defaultBool = true;
            c.parameters = ps;
            foreach (var e in extras) c.AddParameter(e.name, AnimatorControllerParameterType.Trigger);

            AnimatorStateMachine sm = c.layers[0].stateMachine;
            AnimatorState idle = sm.AddState(idleName, new Vector3(300, 0));
            idle.motion = idleClip;
            sm.defaultState = idle;

            var grounded = new List<AnimatorState> { idle };
            if (run != null)
            {
                AnimatorState s = sm.AddState(run.name, new Vector3(300, 100));
                s.motion = runClip;
                Link(idle, s).AddCondition(AnimatorConditionMode.Greater, 0.1f, ActSpriteCharacter.SpeedParam);
                Link(s, idle).AddCondition(AnimatorConditionMode.Less, 0.1f, ActSpriteCharacter.SpeedParam);
                grounded.Add(s);
            }
            if (jump != null)
            {
                AnimatorState s = sm.AddState(jump.name, new Vector3(560, 50));
                s.motion = jumpClip;
                foreach (AnimatorState g in grounded)
                    Link(g, s).AddCondition(AnimatorConditionMode.IfNot, 0f, ActSpriteCharacter.GroundedParam);
                AnimatorStateTransition land = Link(s, idle);   // after landing, finish the clip (the landing crouch)
                land.hasExitTime = true;
                land.exitTime = 1f;
                land.AddCondition(AnimatorConditionMode.If, 0f, ActSpriteCharacter.GroundedParam);
            }
            for (int i = 0; i < extras.Length; i++)
            {
                AnimatorState s = sm.AddState(extras[i].name, new Vector3(40, 200 + 70 * i));
                s.motion = extras[i].clip;
                AnimatorStateTransition enter = sm.AddAnyStateTransition(s);
                enter.hasExitTime = false;
                enter.duration = 0f;
                enter.canTransitionToSelf = false;
                enter.AddCondition(AnimatorConditionMode.If, 0f, extras[i].name);
                AnimatorStateTransition back = s.AddTransition(idle);   // play once, then back to idle
                back.hasExitTime = true;
                back.exitTime = 1f;
                back.duration = 0f;
            }
            EditorUtility.SetDirty(c);
            return c;
        }

        static AnimatorStateTransition Link(AnimatorState from, AnimatorState to)
        {
            AnimatorStateTransition t = from.AddTransition(to);
            t.hasExitTime = false;
            t.duration = 0f;
            return t;
        }

        // ---------- prefab ----------

        static string WritePrefab(string prefabPath, string outDir, string baseName, SpriteMeta meta, string sheetPath,
            MetaAction bodyAction, Sprite firstFrame, AnimatorController controller, string[] extras)
        {
            var go = new GameObject(baseName);
            try
            {
                var sr = go.AddComponent<SpriteRenderer>();
                sr.sprite = firstFrame;
                sr.sortingOrder = 10;

                var animator = go.AddComponent<Animator>();
                animator.runtimeAnimatorController = controller;
                animator.cullingMode = AnimatorCullingMode.AlwaysAnimate;

                var rb = go.AddComponent<Rigidbody2D>();
                rb.gravityScale = 3f;
                rb.freezeRotation = true;
                rb.interpolation = RigidbodyInterpolation2D.Interpolate;
                rb.collisionDetectionMode = CollisionDetectionMode2D.Continuous;
                rb.sharedMaterial = NoFriction(outDir);

                var col = go.AddComponent<CapsuleCollider2D>();
                FitCollider(col, meta, sheetPath, bodyAction);

                var character = go.AddComponent<ActSpriteCharacter>();
                character.extraActions = extras;

                // A rebuild keeps what the user tuned on the old prefab: size and movement.
                var old = AssetDatabase.LoadAssetAtPath<GameObject>(prefabPath);
                if (old != null)
                {
                    go.transform.localScale = old.transform.localScale;
                    var was = old.GetComponent<ActSpriteCharacter>();
                    if (was != null)
                    {
                        character.moveSpeed = was.moveSpeed;
                        character.jumpSpeed = was.jumpSpeed;
                        character.readKeyboard = was.readKeyboard;
                    }
                }

                return PrefabUtility.SaveAsPrefabAsset(go, prefabPath) != null
                    ? prefabPath
                    : throw new InvalidOperationException($"Could not save {prefabPath}.");
            }
            finally { UnityEngine.Object.DestroyImmediate(go); }
        }

        static PhysicsMaterial2D NoFriction(string outDir)
        {
            string path = $"{outDir}/NoFriction.physicsMaterial2D";
            var m = AssetDatabase.LoadAssetAtPath<PhysicsMaterial2D>(path);
            if (m != null) return m;
            m = new PhysicsMaterial2D("NoFriction") { friction = 0f, bounciness = 0f };
            AssetDatabase.CreateAsset(m, path);
            return m;
        }

        /// <summary>
        /// Capsule around the opaque pixels of one action (all its frames), half as wide so arms and weapons
        /// do not snag. Its bottom sits on the lowest opaque pixel, so the feet touch the ground.
        /// </summary>
        static void FitCollider(CapsuleCollider2D col, SpriteMeta meta, string sheetPath, MetaAction a)
        {
            int cw = meta.cell.width, ch = meta.cell.height;
            float ppu = ch;
            var tex = new Texture2D(2, 2, TextureFormat.RGBA32, false);
            int minX = cw, maxX = -1, minY = ch, maxY = -1;
            try
            {
                if (!tex.LoadImage(File.ReadAllBytes(sheetPath)))
                    throw new InvalidDataException($"Could not read {sheetPath} as a PNG.");
                Color32[] px = tex.GetPixels32();
                int w = tex.width, y0 = tex.height - (a.row + 1) * ch;   // LoadImage rows run bottom-up
                for (int f = 0; f < a.frames; f++)
                    for (int y = 0; y < ch; y++)
                        for (int x = 0; x < cw; x++)
                        {
                            if (px[(y0 + y) * w + f * cw + x].a < AlphaCutoff) continue;
                            if (x < minX) minX = x;
                            if (x > maxX) maxX = x;
                            if (y < minY) minY = y;
                            if (y > maxY) maxY = y;
                        }
            }
            finally { UnityEngine.Object.DestroyImmediate(tex); }

            if (maxX < 0) { minX = 0; maxX = cw - 1; minY = 0; maxY = ch - 1; }   // empty frames: use the whole cell
            float height = (maxY - minY + 1) / ppu;
            float width = Mathf.Max(0.15f, 0.5f * (maxX - minX + 1) / ppu);
            // Box2D keeps resting bodies about half the contact offset apart; sink the collider by that much.
            float skin = Physics2D.defaultContactOffset * 0.5f;
            col.direction = height >= width ? CapsuleDirection2D.Vertical : CapsuleDirection2D.Horizontal;
            col.size = new Vector2(width, height);
            col.offset = new Vector2(((minX + maxX + 1) * 0.5f - meta.pivot.x * cw) / ppu,
                                     (minY - meta.pivot.y * ch) / ppu + height * 0.5f + skin);
        }
    }

    /// <summary>Builds a character when an unzipped ActSprite folder (sheet + meta JSON) lands in Assets.</summary>
    internal class ActSpriteAutoImport : AssetPostprocessor
    {
        static void OnPostprocessAllAssets(string[] imported, string[] deleted, string[] moved, string[] movedFrom)
        {
            foreach (string p in imported.Concat(moved))
            {
                if (!p.StartsWith("Assets/", StringComparison.Ordinal) || !p.EndsWith("_meta.json", StringComparison.Ordinal)) continue;
                string folder = Path.GetDirectoryName(p).Replace('\\', '/');
                if (ActSpriteImporter.Busy.Contains(folder)) continue;
                string baseName = Path.GetFileName(p);
                baseName = baseName.Substring(0, baseName.Length - "_meta.json".Length);
                if (!File.Exists($"{folder}/{baseName}_sheet.png")) continue;
                // Already built from this JSON (e.g. a fresh clone importing everything): skip.
                string prefab = $"{folder}/{baseName}.prefab";
                if (File.Exists(prefab) && File.GetLastWriteTimeUtc(prefab) >= File.GetLastWriteTimeUtc(p)) continue;

                string path = p;
                EditorApplication.delayCall += () =>
                {
                    try { ActSpriteImporter.Build(path); }
                    catch (Exception e) { Debug.LogError($"ActSprite: could not import {path}: {e.Message}"); }
                };
            }
        }
    }
}
