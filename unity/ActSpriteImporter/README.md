# ActSprite Importer (Unity 6)

Turns an ActSprite ZIP into a character you can play: sliced sprites, one animation clip per action,
an Animator Controller and a prefab with physics and keyboard control.

## Install

Pick one:

- **Package Manager, from GitHub:** Window > Package Manager > + > *Install package from git URL…*
  `https://github.com/lilwad-0730/actsprite.git?path=unity/ActSpriteImporter`
- **Package Manager, from disk:** + > *Install package from disk…* and pick `unity/ActSpriteImporter/package.json`
  in a clone of the repo.

It needs the 2D Sprite package (installed automatically). It works with the old Input Manager, the Input System
package, or both, and with the built-in render pipeline or URP.

## Use

1. **ActSprite > Import ZIP…** and pick a ZIP from `python -m actsprite` or the web app.
   You can also unzip it into `Assets/`: any `<name>_meta.json` with `<name>_sheet.png` next to it is built
   automatically.
2. It creates `Assets/ActSprite/Characters/<name>/`:
   - the sheet sliced into `run_00`, `run_01`, ... (pivot at the feet, one cell = one unit tall,
     point filtering for pixel art);
   - `Generated/<name>_<action>.anim` at the action's fps (loop as in the JSON);
   - `Generated/<name>.controller` with parameters `Speed`, `IsGrounded` and one trigger per extra action;
   - `<name>.prefab`: SpriteRenderer, Animator, Rigidbody2D, a capsule collider fitted to the opaque pixels
     (its bottom is the lowest foot pixel), and `ActSpriteCharacter`.
3. **ActSprite > Build Demo Scene** makes `Assets/ActSprite/Demo/ActSpriteDemo.unity`: a dungeon floor,
   three platforms, a following camera and every imported character. Press Play.
   The scene starts with `demo_knight`, a pixel knight shipped in `DemoCharacter/` with idle, run, jump and
   attack, so there is always a character that runs. It is imported to `Assets/ActSprite/Characters/demo_knight/`
   the first time you build the scene.

Controls: A/D or arrows move, Space jumps, 1–9 play the extra actions, Tab switches character.

How actions map to the Animator:

| In the JSON | State | Plays when |
| --- | --- | --- |
| `idle` | idle (default) | standing still. Without `idle`, the first frame of the first action is used |
| `run`, or `walk` if there is no `run` | run | `Speed` > 0.1 |
| `jump` | jump | it leaves the ground; after landing it plays to its last frame (the landing crouch), then idle |
| anything else (`attack`, `dance`, …) | same name | its trigger (keys 1–9); plays once, then back to idle |

Importing the same ZIP again updates everything in place. A rebuild keeps what you tuned on the prefab: its
Transform scale and the `ActSpriteCharacter` Move Speed, Jump Speed and Read Keyboard. To rebuild after editing the JSON or the sheet,
select the character folder and use **ActSprite > Rebuild Selected Character**.

The demo art in `DemoArt/` was made for ActSprite during the hackathon; the prompts are in
`DemoArt/GenerationPrompts.md`. The demo knight in `DemoCharacter/` is ActSprite's own output from the author's
clips (the same sheet as `out/knight`, renamed).
