using UnityEngine;

namespace ActSprite
{
    /// <summary>Smoothly follows a target on x and y, never dropping below minY.</summary>
    public class ActSpriteCameraFollow : MonoBehaviour
    {
        public Transform target;
        public Vector2 offset = new Vector2(0f, 1.5f);
        public float minY = 1.5f;
        [Tooltip("Seconds to roughly catch up with the target.")]
        public float smoothTime = 0.15f;

        private Vector3 _velocity;

        public void SnapToTarget()
        {
            if (target == null) return;
            transform.position = Goal();
            _velocity = Vector3.zero;
        }

        private void LateUpdate()
        {
            if (target == null) return;
            transform.position = Vector3.SmoothDamp(transform.position, Goal(), ref _velocity, smoothTime);
        }

        private Vector3 Goal()
        {
            Vector3 p = target.position;
            return new Vector3(p.x + offset.x, Mathf.Max(minY, p.y + offset.y), transform.position.z);
        }
    }
}
