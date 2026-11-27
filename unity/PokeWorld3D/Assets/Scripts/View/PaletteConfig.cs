using UnityEngine;

namespace PokeWorld.View
{
    // @trace ART-001
    // @trace ART-002
    // @trace ART-003
    public sealed class PaletteConfig : ScriptableObject
    {
        public Color primary = new Color32(0x4A, 0x9E, 0xA8, 0xFF);   // #4A9EA8 主色
        public Color secondary = new Color32(0xE8, 0xC8, 0x8A, 0xFF); // #E8C88A 辅色
        public Color danger = new Color32(0xD9, 0x53, 0x4F, 0xFF);    // #D9534F 危险
        public Color background = new Color32(0xE6, 0xEE, 0xF2, 0xFF);// #E6EEF2 背景
        public Color uiBase = new Color32(0x22, 0x38, 0x4A, 0xFF);    // #22384A UI 底

        // 明度阶梯：背景 90-96% / 地形 62-70% / 角色 35-45% / 特效 75-82%
        public float backgroundLightMin = 0.90f;
        public float terrainLightMin = 0.62f;
        public float characterLightMin = 0.35f;
        public float effectLightMin = 0.75f;
    }
}
