using UnityEngine;

namespace PokeWorld.Core
{
    // @trace MECH-001
    public sealed class FollowCamera : MonoBehaviour
    {
        public Transform target;
        public Vector3 offset = new Vector3(0f, 9f, -12f);
        public float damping = 0.15f;
        private Vector3 velocity;

        private void LateUpdate()
        {
            if (target == null)
            {
                Debug.LogWarning("[FollowCamera] target missing, skip update");
                return;
            }
            Vector3 desired = target.position + offset;
            transform.position = Vector3.SmoothDamp(transform.position, desired, ref velocity, damping);
        }
    }
}
