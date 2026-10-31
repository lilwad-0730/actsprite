using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEditor.U2D.Sprites;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace ActSprite.EditorTools
{
    /// <summary>
    /// ActSprite > Build Demo Scene: a dungeon floor, three platforms, a following camera, the bundled demo knight
    /// and every imported character, switchable with Tab. Art: DemoArt/ and DemoCharacter/ in this package
    /// (made for ActSprite during the hackathon).
    /// </summary>
    public static class ActSpriteDemoSceneBuilder
    {
        public const string DemoRoot = "Assets/ActSprite/Demo";
        public const string ScenePath = DemoRoot + "/ActSpriteDemo.unity";
        const string ArtDir = DemoRoot + "/Art";
        const string DemoCharacter = "demo_knight";
        const int ArtPpu = 128;
        const int GroundBlackTop = 291;    // rows of black above the floor surface in DungeonGround.png
        const int PlatformStrip = 96;      // the flagstone layer just under that, used for platforms

        const float LevelLeft = -8f, LevelRight = 40f;
        static readonly (float x, float top, float width)[] Platforms = { (5f, 1.1f, 3f), (9.5f, 2.2f, 3f), (14f, 1.1f, 3f) };

        [MenuItem("ActSprite/Build Demo Scene", priority = 20)]
        static void BuildMenu()
        {
            if (!EditorSceneManager.SaveCurrentModifiedScenesIfUserWantsTo()) return;
            try
            {
                Build();
                EditorSceneManager.OpenScene(ScenePath);
            }
            catch (Exception e)
            {
                EditorUtility.DisplayDialog("ActSprite demo scene", e.Message, "OK");
                Debug.LogException(e);
            }
        }

        /// <summary>
        /// Create (or overwrite) the demo scene with the bundled demo knight (idle, run, jump, attack) first,
        /// then every other character prefab under Assets/ActSprite/Characters.
        /// </summary>
        public static string Build()
        {
            (Sprite wall, Sprite ground, Sprite platform) = PrepareArt();
            EnsureDemoCharacter();
            GameObject[] characters = FindCharacters();

            Scene scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);

            var camGo = new GameObject("Main Camera") { tag = "MainCamera" };
            camGo.transform.position = new Vector3(0f, 1.5f, -10f);
            var cam = camGo.AddComponent<Camera>();
            cam.orthographic = true;
            cam.orthographicSize = 2.4f;
            cam.clearFlags = CameraClearFlags.SolidColor;
            cam.backgroundColor = new Color(0.035f, 0.045f, 0.075f);
            var follow = camGo.AddComponent<ActSpriteCameraFollow>();
            follow.offset = new Vector2(0f, 1f);
            follow.minY = 1.2f;
            AddGlobalLightIfUrp();

            float width = LevelRight - LevelLeft, mid = (LevelLeft + LevelRight) * 0.5f;
            float wallH = wall.rect.height / ArtPpu;
            Tiled("Wall", wall, new Vector2(mid, -1f + wallH * 0.5f), new Vector2(width + 20f, wallH), -20);

            float groundH = ground.rect.height / ArtPpu;
            GameObject floor = Tiled("Ground", ground, new Vector2(mid, 0f), new Vector2(width + 20f, groundH), 0);
            Box(floor, new Vector2(width + 20f, groundH));

            float platH = platform.rect.height / ArtPpu;
            for (int i = 0; i < Platforms.Length; i++)
            {
                var (x, top, w) = Platforms[i];
                Box(Tiled($"Platform {i + 1}", platform, new Vector2(x, top), new Vector2(w, platH), 0), new Vector2(w, platH));
            }

            foreach (float x in new[] { LevelLeft, LevelRight })   // invisible walls at both ends
            {
                var edge = new GameObject("Level Edge");
                edge.transform.position = new Vector3(x, 5f, 0f);
                edge.AddComponent<BoxCollider2D>().size = new Vector2(0.5f, 12f);
            }

            var switcherGo = new GameObject("Character Switcher");
            var switcher = switcherGo.AddComponent<ActSpriteDemoSwitcher>();
            switcher.characters = characters;
            switcher.cameraFollow = follow;
            switcher.spawnPoint = new Vector2(0f, 0.5f);

            Directory.CreateDirectory(DemoRoot);
            if (!EditorSceneManager.SaveScene(scene, ScenePath))
                throw new IOException($"Could not save {ScenePath}.");
            if (!EditorBuildSettings.scenes.Any(s => s.path == ScenePath))
                EditorBuildSettings.scenes = EditorBuildSettings.scenes.Append(new EditorBuildSettingsScene(ScenePath, true)).ToArray();
            Debug.Log($"ActSprite: demo scene saved to {ScenePath} with {characters.Length} character(s): " +
                      string.Join(", ", characters.Select(c => c.name)));
            return ScenePath;
        }

        static GameObject[] FindCharacters()
        {
            if (!AssetDatabase.IsValidFolder(ActSpriteImporter.CharactersRoot)) return new GameObject[0];
            return AssetDatabase.FindAssets("t:Prefab", new[] { ActSpriteImporter.CharactersRoot })
                .Select(g => AssetDatabase.LoadAssetAtPath<GameObject>(AssetDatabase.GUIDToAssetPath(g)))
                .Where(p => p != null && p.GetComponent<ActSpriteCharacter>() != null)
                .OrderBy(p => p.name == DemoCharacter ? 0 : 1)
                .ThenBy(p => p.name, StringComparer.Ordinal)
                .ToArray();
        }

        /// <summary>
        /// Import the knight shipped in DemoCharacter/ (made with ActSprite from the author's own clips) so the demo
        /// always has a character that runs, jumps and attacks. Skipped when it is already imported.
        /// </summary>
        static void EnsureDemoCharacter()
        {
            string folder = $"{ActSpriteImporter.CharactersRoot}/{DemoCharacter}";
            if (File.Exists($"{folder}/{DemoCharacter}.prefab")) return;
            string src = Path.Combine(PackageDir(), "DemoCharacter");
            Directory.CreateDirectory(folder);
            foreach (string suffix in new[] { "_meta.json", "_sheet.png" })
                File.Copy(Path.Combine(src, DemoCharacter + suffix), $"{folder}/{DemoCharacter}{suffix}", true);
            ActSpriteImporter.Busy.Add(folder);   // build here, not again from the auto-import hook
            try
            {
                AssetDatabase.Refresh(ImportAssetOptions.ForceSynchronousImport);
                ActSpriteImporter.Build($"{folder}/{DemoCharacter}_meta.json");
            }
            finally { ActSpriteImporter.Busy.Remove(folder); }
        }

        static GameObject Tiled(string name, Sprite sprite, Vector2 pos, Vector2 size, int order)
        {
            var go = new GameObject(name);
            go.transform.position = pos;
            var sr = go.AddComponent<SpriteRenderer>();
            sr.sprite = sprite;
            sr.drawMode = SpriteDrawMode.Tiled;
            sr.tileMode = SpriteTileMode.Continuous;
            sr.size = size;
            sr.sortingOrder = order;
            return go;
        }

        static void Box(GameObject go, Vector2 size)
        {
            // The ground and platform sprites hang from their top edge (pivot 0.5, 1).
            var box = go.AddComponent<BoxCollider2D>();
            box.size = size;
            box.offset = new Vector2(0f, -size.y * 0.5f);
        }

        static void AddGlobalLightIfUrp()
        {
            // URP's 2D renderer shows lit sprites black without a light; the built-in pipeline needs none.
            Type light2D = Type.GetType("UnityEngine.Rendering.Universal.Light2D, Unity.RenderPipelines.Universal.Runtime");
            if (light2D == null || UnityEngine.Rendering.GraphicsSettings.currentRenderPipeline == null) return;
            var go = new GameObject("Global Light 2D");
            Component light = go.AddComponent(light2D);
            var lightType = light2D.GetProperty("lightType");
            if (lightType != null) lightType.SetValue(light, Enum.Parse(lightType.PropertyType, "Global"));
        }

        // ---------- art ----------

        static (Sprite wall, Sprite ground, Sprite platform) PrepareArt()
        {
            string src = Path.Combine(PackageDir(), "DemoArt");
            Directory.CreateDirectory(ArtDir);
            foreach (string f in new[] { "DungeonWall.png", "DungeonGround.png" })
            {
                string dst = $"{ArtDir}/{f}";
                if (!File.Exists(dst)) File.Copy(Path.Combine(src, f), dst);
            }
            AssetDatabase.Refresh(ImportAssetOptions.ForceSynchronousImport);

            string wallPath = $"{ArtDir}/DungeonWall.png", groundPath = $"{ArtDir}/DungeonGround.png";
            Configure(wallPath, (w, h) => new[] { ("DungeonWall", new Rect(0, 0, w, h), new Vector2(0.5f, 0.5f)) });
            Configure(groundPath, (w, h) => new[]
            {
                ("DungeonGround", new Rect(0, 0, w, h - GroundBlackTop), new Vector2(0.5f, 1f)),
                ("DungeonPlatform", new Rect(0, h - GroundBlackTop - PlatformStrip, w, PlatformStrip), new Vector2(0.5f, 1f)),
            });
            return (Load(wallPath, "DungeonWall"), Load(groundPath, "DungeonGround"), Load(groundPath, "DungeonPlatform"));
        }

        static void Configure(string path, Func<int, int, (string name, Rect rect, Vector2 pivot)[]> layout)
        {
            var importer = (TextureImporter)AssetImporter.GetAtPath(path);
            importer.GetSourceTextureWidthAndHeight(out int w, out int h);
            importer.textureType = TextureImporterType.Sprite;
            importer.spriteImportMode = SpriteImportMode.Multiple;
            importer.spritePixelsPerUnit = ArtPpu;
            importer.filterMode = FilterMode.Point;
            importer.textureCompression = TextureImporterCompression.Uncompressed;
            importer.mipmapEnabled = false;
            importer.wrapMode = TextureWrapMode.Repeat;
            importer.npotScale = TextureImporterNPOTScale.None;
            var settings = new TextureImporterSettings();
            importer.ReadTextureSettings(settings);
            settings.spriteMeshType = SpriteMeshType.FullRect;   // needed for tiled drawing
            importer.SetTextureSettings(settings);
            importer.SaveAndReimport();

            var factories = new SpriteDataProviderFactories();
            factories.Init();
            ISpriteEditorDataProvider provider = factories.GetSpriteEditorDataProviderFromObject(importer);
            provider.InitSpriteEditorDataProvider();
            var old = provider.GetSpriteRects().GroupBy(r => r.name).ToDictionary(g => g.Key, g => g.First().spriteID);
            SpriteRect[] rects = layout(w, h).Select(l => new SpriteRect
            {
                name = l.name,
                rect = l.rect,
                alignment = SpriteAlignment.Custom,
                pivot = l.pivot,
                spriteID = old.TryGetValue(l.name, out GUID id) ? id : GUID.Generate(),
            }).ToArray();
            provider.SetSpriteRects(rects);
            provider.GetDataProvider<ISpriteNameFileIdDataProvider>()?
                .SetNameFileIdPairs(rects.Select(r => new SpriteNameFileIdPair(r.name, r.spriteID)));
            provider.Apply();
            importer.SaveAndReimport();
        }

        static Sprite Load(string path, string name) =>
            AssetDatabase.LoadAllAssetsAtPath(path).OfType<Sprite>().FirstOrDefault(s => s.name == name)
            ?? throw new InvalidOperationException($"Unity did not create sprite {name} from {path}.");

        static string PackageDir()
        {
            var info = UnityEditor.PackageManager.PackageInfo.FindForAssembly(typeof(ActSpriteDemoSceneBuilder).Assembly);
            if (info != null) return info.resolvedPath;
            // Copied into Assets instead of installed as a package: find this script and go up from Editor/.
            string script = AssetDatabase.FindAssets("ActSpriteDemoSceneBuilder t:MonoScript")
                .Select(AssetDatabase.GUIDToAssetPath).FirstOrDefault(p => p.EndsWith("/Editor/ActSpriteDemoSceneBuilder.cs"));
            if (script == null)
                throw new DirectoryNotFoundException("Could not find the ActSprite Importer folder. Reinstall it (see its README).");
            return Path.GetDirectoryName(Path.GetDirectoryName(Path.GetFullPath(script)));
        }
    }
}
