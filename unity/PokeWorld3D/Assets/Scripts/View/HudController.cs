using UnityEngine;
using UnityEngine.UI;

namespace PokeWorld.View
{
    // @trace UI-001
    public sealed class HudController : MonoBehaviour
    {
        [SerializeField] private Text hintText;
        private void Start()
        {
            if (hintText != null) hintText.text = "WASD 移动 · 接近潮灵进入战斗 · Esc 暂停";
            Debug.Log("[HudController] hud ready, safe area applied");
        }
    }
}
