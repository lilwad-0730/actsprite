using System;
using System.IO;
using System.Linq;
using System.Text;
using ActSprite;
using ActSprite.EditorTools;
using UnityEditor;
using UnityEditor.Animations;
using UnityEditor.SceneManagement;
using UnityEngine;

// Batch check of the importer, not part of the package (see scripts/unity_smoke/README.md).
// Run with -executeMethod ActSpriteSmokeTest.Run. Repo below must point at this repository.
public static class ActSpriteSmokeTest
{
    const string Repo = "C:/Users/andyw/Desktop/processing project/Meta/actsprite";
    static readonly StringBuilder Log = new StringBuilder();

    static void W(string s) { Log.AppendLine(s); Debug.Log("SMOKE " + s); }

    public static void Run()
    {
        int failures = 0;
        SimulationMode2D simulationMode = Physics2D.simulationMode;
        try
        {
            string[] zips =
            {
                Repo + "/out/knight/actsprite_knight.zip",
                Repo + "/examples/actsprite_hound.zip",
                Repo + "/examples/actsprite_lineman.zip",
            };
            foreach (string z in zips)
            {
                string prefabPath = ActSpriteImporter.ImportZip(z);
                failures += CheckPrefab(prefabPath);
            }

            string demoMeta = ActSpriteImporter.CharactersRoot + "/demo_knight/demo_knight_meta.json";
            if (File.Exists(demoMeta)) ActSpriteImporter.Build(demoMeta);
            string scene = ActSpriteDemoSceneBuilder.Build();
            EditorSceneManager.OpenScene(scene);
            failures += CheckRun();
            failures += CheckLanding();
            failures += CheckDoubleJump();
            Screenshot(Path.GetFullPath("demo_shot.png"));
        }
        catch (Exception e) { W("EXCEPTION " + e); failures++; }
        finally
        {
            Physics2D.simulationMode = simulationMode;
            W($"physics simulation restored: {simulationMode}");
        }
        W(failures == 0 ? "RESULT PASS" : $"RESULT FAIL ({failures})");
        File.WriteAllText("smoke_result.txt", Log.ToString());
        EditorApplication.Exit(failures == 0 ? 0 : 1);
    }

    static int CheckPrefab(string path)
    {
        int bad = 0;
        var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(path);
        var anim = prefab.GetComponent<Animator>();
        var ctrl = (AnimatorController)anim.runtimeAnimatorController;
        var sr = prefab.GetComponent<SpriteRenderer>();
        var col = prefab.GetComponent<CapsuleCollider2D>();
        var ch = prefab.GetComponent<ActSpriteCharacter>();
        string sheet = AssetDatabase.GetAssetPath(sr.sprite.texture);
        var imp = (TextureImporter)AssetImporter.GetAtPath(sheet);
        int spriteCount = AssetDatabase.LoadAllAssetsAtPath(sheet).OfType<Sprite>().Count();
        W($"{prefab.name}: sheet {sheet} sprites={spriteCount} ppu={imp.spritePixelsPerUnit} filter={imp.filterMode} " +
          $"pivot={sr.sprite.pivot / sr.sprite.rect.size} collider size={col.size} offset={col.offset} dir={col.direction}");
        W($"  params: {string.Join(", ", ctrl.parameters.Select(p => p.name + ":" + p.type))}");
        W($"  extra keys: {string.Join(", ", ch.extraActions)}");
        foreach (ChildAnimatorState s in ctrl.layers[0].stateMachine.states)
        {
            var clip = (AnimationClip)s.state.motion;
            var binding = AnimationUtility.GetObjectReferenceCurveBindings(clip).Single();
            var keys = AnimationUtility.GetObjectReferenceCurve(clip, binding);
            bool loop = AnimationUtility.GetAnimationClipSettings(clip).loopTime;
            string names = string.Join(" ", keys.Select(k => k.value.name));
            W($"  state {s.state.name}: clip {clip.name} len={clip.length:0.000}s fps={clip.frameRate} loop={loop} keys={keys.Length} " +
              $"transitions=[{string.Join("; ", s.state.transitions.Select(t => t.destinationState.name + " if " + string.Join("&", t.conditions.Select(c => c.parameter + " " + c.mode + " " + c.threshold)) + (t.hasExitTime ? " exit" : "")))}]");
            // Keys must be in frame order and evenly spaced at 1/fps.
            for (int i = 1; i < keys.Length; i++)
            {
                float dt = keys[i].time - keys[i - 1].time;
                if (Mathf.Abs(dt - 1f / clip.frameRate) > 1e-4f) { W($"  BAD spacing in {clip.name} at key {i}: {dt}"); bad++; }
            }
            float expectedLength = keys.Length / clip.frameRate;
            if (Mathf.Abs(clip.length - expectedLength) > 1e-4f)
            {
                W($"  BAD duration in {clip.name}: {clip.length} instead of {expectedLength}");
                bad++;
            }
            if (keys.Select(k => k.value).Distinct().Count() != keys.Length)
            {
                W($"  BAD duplicate sprite key in {clip.name}");
                bad++;
            }
            if (keys.Length > 2 && !names.StartsWith(keys[0].value.name)) bad++;
        }
        W($"  any-state: {string.Join("; ", ctrl.layers[0].stateMachine.anyStateTransitions.Select(t => t.destinationState.name))} default={ctrl.layers[0].stateMachine.defaultState.name}");
        return bad;
    }

    // The demo scene must start with the bundled knight, and Speed > 0.1 must play its run frames in order.
    static int CheckRun()
    {
        int bad = 0;
        var switcher = UnityEngine.Object.FindAnyObjectByType<ActSpriteDemoSwitcher>();
        GameObject first = switcher.characters[0];
        W($"first demo character: {first.name}");
        if (first.name != "demo_knight") bad++;
        failuresFromPrefab = CheckPrefab(AssetDatabase.GetAssetPath(first));
        bad += failuresFromPrefab;

        var go = (GameObject)PrefabUtility.InstantiatePrefab(first);
        var anim = go.GetComponent<Animator>();
        var sr = go.GetComponent<SpriteRenderer>();
        anim.Rebind();
        anim.Update(0f);
        anim.Update(0.5f);
        string idleSprite = sr.sprite.name;
        bool idleState = anim.GetCurrentAnimatorStateInfo(0).IsName("idle");
        anim.SetFloat(ActSpriteCharacter.SpeedParam, 3f);
        var seen = new System.Collections.Generic.List<string>();
        for (int i = 0; i < 40; i++)
        {
            anim.Update(1f / 60f);
            if (anim.GetCurrentAnimatorStateInfo(0).IsName("run") && (seen.Count == 0 || seen[seen.Count - 1] != sr.sprite.name))
                seen.Add(sr.sprite.name);
        }
        bool runState = anim.GetCurrentAnimatorStateInfo(0).IsName("run");
        var distinct = seen.Where(n => n.StartsWith("run_")).Distinct().Count();
        bool ok = idleState && idleSprite.StartsWith("idle_") && runState && distinct >= 6;
        W($"  run check: idle state={idleState} sprite={idleSprite}; after Speed=3 run state={runState}, frames seen: {string.Join(" ", seen)} {(ok ? "OK" : "BAD")}");
        if (!ok) bad++;

        UnityEngine.Object.DestroyImmediate(go);
        return bad;
    }

    static int failuresFromPrefab;

    // Jump again while the last jump's landing frames play: the new jump must restart the clip, not hold its end.
    static int CheckDoubleJump()
    {
        Physics2D.simulationMode = SimulationMode2D.Script;
        var switcher = UnityEngine.Object.FindAnyObjectByType<ActSpriteDemoSwitcher>();
        var go = (GameObject)PrefabUtility.InstantiatePrefab(switcher.characters[0]);
        go.transform.position = new Vector3(-6f, 0.6f, 0f);
        Physics2D.SyncTransforms();
        var c = go.GetComponent<ActSpriteCharacter>();
        c.readKeyboard = false;
        var anim = go.GetComponent<Animator>();
        var sr = go.GetComponent<SpriteRenderer>();
        var flags = System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic;
        var awake = typeof(ActSpriteCharacter).GetMethod("Awake", flags);
        var fixedUpdate = typeof(ActSpriteCharacter).GetMethod("FixedUpdate", flags);
        var update = typeof(ActSpriteCharacter).GetMethod("Update", flags);
        awake.Invoke(c, null);
        anim.Rebind();
        void Step() { fixedUpdate.Invoke(c, null); Physics2D.Simulate(0.02f); update.Invoke(c, null); anim.Update(0.02f); }
        for (int i = 0; i < 100; i++) Step();                  // stand on the ground
        c.SetInput(0f, true);
        bool left = false; int t = 0;
        while (t++ < 300)                                       // first jump: up, then land
        {
            Step();
            if (!c.IsGrounded) left = true;
            if (left && c.IsGrounded) break;
        }
        for (int i = 0; i < 5; i++) Step();                     // a few landing frames
        string landing = sr.sprite.name;
        c.SetInput(0f, true);                                   // second jump during the landing
        var air = new System.Collections.Generic.List<string>();
        for (int i = 0; i < 25; i++)
        {
            Step();
            if (!c.IsGrounded && (air.Count == 0 || air[air.Count - 1] != sr.sprite.name)) air.Add(sr.sprite.name);
        }
        int last = anim.GetCurrentAnimatorClipInfo(0)[0].clip.length > 0 ? 11 : 0;
        bool ok = air.Count >= 3 && !air.Contains($"jump_{last:00}") && air[0].CompareTo("jump_04") <= 0;
        W($"  double jump: landing sprite {landing}; second jump in the air shows {string.Join(" ", air)} {(ok ? "OK" : "BAD")}");
        UnityEngine.Object.DestroyImmediate(go);
        return ok ? 0 : 1;
    }

    static int CheckLanding()
    {
        int bad = 0;
        Physics2D.simulationMode = SimulationMode2D.Script;
        var switcher = UnityEngine.Object.FindAnyObjectByType<ActSpriteDemoSwitcher>();
        W($"demo scene characters: {string.Join(", ", switcher.characters.Select(c => c.name))}");
        float[] spawnX = { -3.5f, -1.5f, 0.5f, 2.5f };
        (string where, float x, float y, float top)[] tests = { ("ground", 0f, 0.6f, 0f), ("platform 1", 5f, 2.5f, 1.1f), ("platform 2", 9.5f, 3.5f, 2.2f) };
        foreach (GameObject p in switcher.characters)
        {
            foreach (var t in tests)
            {
                GameObject go = (GameObject)PrefabUtility.InstantiatePrefab(p);
                go.transform.position = new Vector3(t.x, t.y, 0f);
                Physics2D.SyncTransforms();
                for (int i = 0; i < 200; i++) Physics2D.Simulate(0.02f);
                var body = go.GetComponent<Rigidbody2D>();
                var sr = go.GetComponent<SpriteRenderer>();
                float feet = go.transform.position.y + LowestOpaque(sr.sprite) / sr.sprite.pixelsPerUnit;
                float gapPx = (feet - t.top) * sr.sprite.pixelsPerUnit;
                bool ok = Mathf.Abs(gapPx) <= 1.5f && body.linearVelocity.magnitude < 0.01f;
                W($"  landing {p.name} on {t.where}: body y={go.transform.position.y:0.0000} feet gap={gapPx:+0.00;-0.00} px vel={body.linearVelocity.magnitude:0.0000} {(ok ? "OK" : "BAD")}");
                if (!ok) bad++;
                UnityEngine.Object.DestroyImmediate(go);
            }
        }
        // Leave one of each standing on the ground for the screenshot.
        for (int i = 0; i < switcher.characters.Length; i++)
        {
            var go = (GameObject)PrefabUtility.InstantiatePrefab(switcher.characters[i]);
            go.transform.position = new Vector3(spawnX[i % spawnX.Length], 0.6f, 0f);
        }
        Physics2D.SyncTransforms();
        for (int i = 0; i < 200; i++) Physics2D.Simulate(0.02f);
        return bad;
    }

    // Lowest opaque row of a sprite, in pixels above its pivot (reads the PNG directly).
    static float LowestOpaque(Sprite s)
    {
        var tex = new Texture2D(2, 2, TextureFormat.RGBA32, false);
        tex.LoadImage(File.ReadAllBytes(AssetDatabase.GetAssetPath(s.texture)));
        Rect r = s.rect;
        for (int y = 0; y < (int)r.height; y++)
            for (int x = 0; x < (int)r.width; x++)
                if (tex.GetPixel((int)r.x + x, (int)r.y + y).a * 255f >= 16f)
                    return y - s.pivot.y;
        return 0f;
    }

    static void Screenshot(string file)
    {
        var cam = Camera.main;
        cam.transform.position = new Vector3(1.5f, 1.2f, -10f);
        var rt = new RenderTexture(1280, 720, 24);
        cam.targetTexture = rt;
        cam.Render();
        RenderTexture.active = rt;
        var tex = new Texture2D(1280, 720, TextureFormat.RGB24, false);
        tex.ReadPixels(new Rect(0, 0, 1280, 720), 0, 0);
        tex.Apply();
        File.WriteAllBytes(file, tex.EncodeToPNG());
        cam.targetTexture = null;
        RenderTexture.active = null;
        W("screenshot " + file);
    }
}
