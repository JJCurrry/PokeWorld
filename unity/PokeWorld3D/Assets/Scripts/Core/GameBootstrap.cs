using UnityEngine;

namespace PokeWorld.Core
{
    // @trace MECH-001
    // @trace PLAT-002
    public sealed class GameBootstrap : MonoBehaviour
    {
        private void Start()
        {
            Debug.Log("[GameBootstrap] start, scene=" + gameObject.scene.name);

            // 最小可见对象：绿色地面 + 胶囊玩家，不依赖任何手写场景 YAML。
            GameObject ground = GameObject.CreatePrimitive(PrimitiveType.Plane);
            ground.name = "Ground";
            ground.transform.localScale = new Vector3(4f, 1f, 4f);
            Renderer groundRenderer = ground.GetComponent<Renderer>();
            if (groundRenderer != null && groundRenderer.material != null)
                groundRenderer.material.color = new Color(0.58f, 0.78f, 0.56f);

            GameObject player = GameObject.CreatePrimitive(PrimitiveType.Capsule);
            player.name = "Player";
            player.transform.position = new Vector3(0f, 1f, 0f);
            if (player.GetComponent<Collider>() == null) player.AddComponent<CapsuleCollider>();
            player.AddComponent<PlayerController3D>();
            player.AddComponent<EncounterSystem>();

            GameObject wild = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            wild.name = "WildCreature";
            wild.transform.position = new Vector3(6f, 0.6f, 0f);

            GameObject cameraObject = new GameObject("MainCamera");
            cameraObject.tag = "MainCamera";
            Camera camera = cameraObject.AddComponent<Camera>();
            camera.clearFlags = CameraClearFlags.SolidColor;
            camera.backgroundColor = new Color(0.90f, 0.93f, 0.95f);
            cameraObject.transform.position = new Vector3(0f, 9f, -12f);
            cameraObject.transform.rotation = Quaternion.Euler(38f, 0f, 0f);
            FollowCamera follow = cameraObject.AddComponent<FollowCamera>();
            follow.target = player.transform;

            EncounterSystem encounter = player.GetComponent<EncounterSystem>();
            SerializedFieldSetter.SetWildCreature(encounter, wild.transform);

            Debug.Log("[GameBootstrap] ready: ground + player + wild creature + camera");
        }
    }
}
