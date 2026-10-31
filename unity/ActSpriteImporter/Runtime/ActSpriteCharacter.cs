using UnityEngine;
#if ACTSPRITE_INPUT_SYSTEM && ENABLE_INPUT_SYSTEM
using UnityEngine.InputSystem;
#endif

namespace ActSprite
{
    /// <summary>
    /// Simple side-scroller control for an imported ActSprite character.
    /// A/D or arrows move, Space or W jumps, keys 1-9 play the extra actions (attack, dance, ...).
    /// Drives the Animator parameters the importer creates: Speed, IsGrounded and one trigger per extra action.
    /// </summary>
    [RequireComponent(typeof(Rigidbody2D))]
    public class ActSpriteCharacter : MonoBehaviour
    {
        public const string SpeedParam = "Speed";
        public const string GroundedParam = "IsGrounded";

        [Tooltip("Horizontal speed in units per second (one sprite cell is one unit tall).")]
        public float moveSpeed = 3f;
        [Tooltip("Upward speed when a jump starts.")]
        public float jumpSpeed = 9f;
        [Tooltip("Read the keyboard. Turn off to drive the character from your own script with SetInput.")]
        public bool readKeyboard = true;
        [Tooltip("Animator triggers for keys 1-9, filled in by the importer.")]
        public string[] extraActions = new string[0];

        public bool IsGrounded { get; private set; }

        private Rigidbody2D _body;
        private Animator _animator;
        private SpriteRenderer _renderer;
        private ContactFilter2D _groundFilter;
        private float _move;
        private bool _jumpQueued;
        private bool _hasSpeed, _hasGrounded;

        private void Awake()
        {
            _body = GetComponent<Rigidbody2D>();
            _animator = GetComponent<Animator>();
            _renderer = GetComponent<SpriteRenderer>();
            _groundFilter = new ContactFilter2D { useTriggers = false };
            _groundFilter.SetNormalAngle(45f, 135f); // only surfaces below the feet count as ground
            if (_animator != null)
            {
                foreach (AnimatorControllerParameter p in _animator.parameters)
                {
                    if (p.name == SpeedParam) _hasSpeed = true;
                    if (p.name == GroundedParam) _hasGrounded = true;
                }
            }
        }

        /// <summary>Drive the character without the keyboard (AI, tests, replays).</summary>
        public void SetInput(float move, bool jump)
        {
            _move = Mathf.Clamp(move, -1f, 1f);
            _jumpQueued |= jump;
        }

        /// <summary>Play one of the extra actions by name, e.g. "attack" or "dance".</summary>
        public void PlayAction(string actionName)
        {
            if (_animator != null && !string.IsNullOrEmpty(actionName)) _animator.SetTrigger(actionName);
        }

        private void Update()
        {
            if (readKeyboard) ReadKeyboard();

            if (_renderer != null)
            {
                if (_move > 0.01f) _renderer.flipX = false;      // sheets face right
                else if (_move < -0.01f) _renderer.flipX = true;
            }

            if (_animator != null)
            {
                if (_hasSpeed) _animator.SetFloat(SpeedParam, Mathf.Abs(_body.linearVelocity.x));
                if (_hasGrounded) _animator.SetBool(GroundedParam, IsGrounded);
            }
        }

        private void FixedUpdate()
        {
            IsGrounded = _body.IsTouching(_groundFilter);
            Vector2 v = _body.linearVelocity;
            v.x = _move * moveSpeed;
            if (_jumpQueued && IsGrounded) v.y = jumpSpeed;
            _jumpQueued = false;
            _body.linearVelocity = v;
        }

        private void ReadKeyboard()
        {
            int action = -1;
#if ACTSPRITE_INPUT_SYSTEM && ENABLE_INPUT_SYSTEM
            Keyboard k = Keyboard.current;
            if (k == null) return;
            float right = (k.dKey.isPressed || k.rightArrowKey.isPressed) ? 1f : 0f;
            float left = (k.aKey.isPressed || k.leftArrowKey.isPressed) ? 1f : 0f;
            _move = right - left;
            if (k.spaceKey.wasPressedThisFrame || k.wKey.wasPressedThisFrame || k.upArrowKey.wasPressedThisFrame)
                _jumpQueued = true;
            for (int i = 0; i < 9; i++)
                if (k[Key.Digit1 + i].wasPressedThisFrame) action = i;
#elif ENABLE_LEGACY_INPUT_MANAGER
            _move = Input.GetAxisRaw("Horizontal");
            if (Input.GetKeyDown(KeyCode.Space) || Input.GetKeyDown(KeyCode.W) || Input.GetKeyDown(KeyCode.UpArrow))
                _jumpQueued = true;
            for (int i = 0; i < 9; i++)
                if (Input.GetKeyDown(KeyCode.Alpha1 + i)) action = i;
#endif
            if (action >= 0 && action < extraActions.Length) PlayAction(extraActions[action]);
        }
    }
}
