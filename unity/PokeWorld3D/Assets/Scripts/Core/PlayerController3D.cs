using UnityEngine;

namespace PokeWorld.Core
{
    // @trace MECH-001
    // @trace AUD-001
    [RequireComponent(typeof(CharacterController))]
    public sealed class PlayerController3D : MonoBehaviour
    {
        public float speed = 6f;
        public float turnSpeed = 12f;
        private CharacterController controller;

        private void Awake()
        {
            controller = GetComponent<CharacterController>();
        }

        private void Update()
        {
            float horizontal = Input.GetAxisRaw("Horizontal");
            float vertical = Input.GetAxisRaw("Vertical");
            if (Mathf.Abs(horizontal) < 0.01f && Mathf.Abs(vertical) < 0.01f) return;

            Vector3 direction = new Vector3(horizontal, 0f, vertical).normalized;
            controller.Move(direction * speed * Time.deltaTime);
            Quaternion target = Quaternion.LookRotation(direction);
            transform.rotation = Quaternion.Slerp(transform.rotation, target, turnSpeed * Time.deltaTime);
            Debug.Log("[PlayerController3D] move input=" + horizontal.ToString("F1") + "," + vertical.ToString("F1"));
        }
    }
}
