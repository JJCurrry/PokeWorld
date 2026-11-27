using UnityEngine;

namespace PokeWorld.Core
{
    // 仅用于在运行时给私有 SerializeField 赋值，避免在场景 YAML 里手写引用。
    internal static class SerializedFieldSetter
    {
        internal static void SetWildCreature(EncounterSystem system, Transform wild)
        {
            SerializedObject so = new SerializedObject(system);
            SerializedProperty property = so.FindProperty("wildCreature");
            if (property != null)
            {
                property.objectReferenceValue = wild;
                so.ApplyModifiedPropertiesWithoutUndo();
            }
        }
    }
}
