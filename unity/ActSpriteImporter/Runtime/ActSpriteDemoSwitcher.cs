using UnityEngine;
#if ACTSPRITE_INPUT_SYSTEM && ENABLE_INPUT_SYSTEM
using UnityEngine.InputSystem;
#endif

namespace ActSprite
{
    /// <summary>
    /// Demo scene helper: spawns the first character prefab and swaps to the next one with Tab,
    /// keeping position, velocity and facing. Shows the controls in the corner.
    /// </summary>
    public class ActSpriteDemoSwitcher : MonoBehaviour
    {
        public GameObject[] characters = new GameObject[0];
        public ActSpriteCameraFollow cameraFollow;
        public Vector2 spawnPoint = new Vector2(0f, 0.5f);

        public GameObject Current { get; private set; }
        private int _index;
        private GUIStyle _style;

        private void Start()
        {
            if (characters.Length > 0) Spawn(0, spawnPoint, Vector2.zero, false);
        }

        private void Update()
        {
            bool next = false;
#if ACTSPRITE_INPUT_SYSTEM && ENABLE_INPUT_SYSTEM
            next = Keyboard.current != null && Keyboard.current.tabKey.wasPressedThisFrame;
#elif ENABLE_LEGACY_INPUT_MANAGER
            next = Input.GetKeyDown(KeyCode.Tab);
#endif
            if (next) Next();
        }

        /// <summary>Swap to the next character in the list.</summary>
        public void Next()
        {
            if (characters.Length == 0) return;
            Vector2 pos = spawnPoint, vel = Vector2.zero;
            bool flip = false;
            if (Current != null)
            {
                pos = Current.transform.position;
                var body = Current.GetComponent<Rigidbody2D>();
                if (body != null) vel = body.linearVelocity;
                var sr = Current.GetComponent<SpriteRenderer>();
                if (sr != null) flip = sr.flipX;
                Destroy(Current);
            }
            Spawn((_index + 1) % characters.Length, pos, vel, flip);
        }

        private void Spawn(int index, Vector2 pos, Vector2 vel, bool flip)
        {
            _index = index;
            if (characters[index] == null) return;
            Current = Instantiate(characters[index], pos, Quaternion.identity);
            Current.name = characters[index].name;
            var body = Current.GetComponent<Rigidbody2D>();
            if (body != null) body.linearVelocity = vel;
            var sr = Current.GetComponent<SpriteRenderer>();
            if (sr != null) sr.flipX = flip;
            if (cameraFollow != null)
            {
                cameraFollow.target = Current.transform;
                if (Time.timeSinceLevelLoad < 0.1f) cameraFollow.SnapToTarget();
            }
        }

        private void OnGUI()
        {
            if (Current == null) return;
            if (_style == null) _style = new GUIStyle(GUI.skin.label) { fontSize = 16 };
            string actions = "";
            var c = Current.GetComponent<ActSpriteCharacter>();
            if (c != null)
                for (int i = 0; i < c.extraActions.Length && i < 9; i++)
                    actions += $"   {i + 1}: {c.extraActions[i]}";
            GUI.Label(new Rect(12, 8, 900, 60),
                $"{Current.name}   (Tab: next character)\nA/D move   Space jump{actions}", _style);
        }
    }
}
