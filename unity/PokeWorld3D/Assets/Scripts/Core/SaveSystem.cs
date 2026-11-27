using System;
using System.Collections.Generic;

namespace PokeWorld.Core
{
    // @trace MECH-006
    [Serializable]
    public sealed class SaveData
    {
        public string worldSeed;
        public List<string> flags;
        public List<string> party;
    }

    public static class SaveSystem
    {
        public static string Encode(SaveData data)
        {
            if (data == null) throw new ArgumentNullException(nameof(data));
            return JsonUtilityShim.ToJson(data);
        }

        public static SaveData Decode(string text)
        {
            if (string.IsNullOrEmpty(text)) throw new ArgumentException("存档文本为空", nameof(text));
            return JsonUtilityShim.FromJson<SaveData>(text);
        }
    }

    // 纯 JSON 适配器：核心层不直接依赖 UnityEngine。
    internal static class JsonUtilityShim
    {
        internal static string ToJson(object value) { return UnityEngine.JsonUtility.ToJson(value); }
        internal static T FromJson<T>(string text) { return UnityEngine.JsonUtility.FromJson<T>(text); }
    }
}
