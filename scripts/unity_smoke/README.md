# Unity importer smoke test (batch mode)

`ActSpriteSmokeTest.cs` imports three ZIPs with the importer package, builds the demo scene and checks it
without opening the Editor window. It is not part of the package.

What it checks:
- every imported prefab: sprite count, pixels per unit, point filter, pivot at the feet, collider, Animator
  states and transitions (with exit times), one key per sprite, clip duration of frames / fps and key spacing;
- the first demo character is `demo_knight`; idle switches to run at `Speed` 3 and plays `run_00`-`run_07`;
- double jump: a jump started during the last jump's landing frames restarts the jump clip;
- every demo character dropped on the floor and two platforms rests with its lowest foot pixel on the surface
  (within 1.5 px);
- a screenshot of the scene (`demo_shot.png`).

The check restores the project's physics simulation mode when it finishes, including when a check throws.

Setup, once:
1. Create an empty Unity 6000.5.5f1 project (2D).
2. In `Packages/manifest.json` add
   `"com.actsprite.importer": "file:<repo>/unity/ActSpriteImporter"` and, to test the Input System path,
   `"com.unity.inputsystem": "1.19.0"`.
3. Copy `ActSpriteSmokeTest.cs` to `Assets/Editor/` and set `Repo` at its top to this repository.
4. `out/knight/actsprite_knight.zip` must exist (the knight with idle, run, jump, attack; it is git-ignored).

Run (from the folder where `smoke_result.txt` should go):

```bash
"/c/Program Files/Unity/Hub/Editor/6000.5.5f1/Editor/Unity.exe" -batchmode -projectPath <project> -executeMethod ActSpriteSmokeTest.Run -logFile smoke.log
grep -E "^SMOKE" smoke.log
```

The last line is `SMOKE RESULT PASS` or `SMOKE RESULT FAIL (n)`. The Unity project must not be open in the
Editor at the same time. `demo_knight` is imported only once: delete `Assets/ActSprite/Characters/demo_knight`
in the test project to re-import a changed `DemoCharacter/` sheet.
