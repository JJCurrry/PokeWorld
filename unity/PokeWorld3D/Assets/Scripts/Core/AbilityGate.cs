using System;
using System.Collections.Generic;
using UnityEngine;

namespace PokeWorld.Core
{
    // @trace MECH-004
    public sealed class AbilityGate : MonoBehaviour
    {
        [Serializable]
        private class GateRow
        {
            public string region;
            public int atlasRequired;
        }

        [Serializable]
        private class GateTable
        {
            public List<GateRow> gates;
        }

        [SerializeField] private TextAsset regionsConfig;
        private GateTable table;

        private void Awake()
        {
            if (regionsConfig == null)
            {
                Debug.LogWarning("[AbilityGate] config missing, gate stays closed");
                return;
            }
            table = JsonUtility.FromJson<GateTable>(regionsConfig.text);
            Debug.Log("[AbilityGate] loaded gates=" + (table == null ? 0 : table.gates.Count));
        }

        // 只读数据判定，不在代码里写死任何能力名。
        public bool IsOpen(string region, int atlasCount)
        {
            if (table == null || table.gates == null) return false;
            foreach (GateRow row in table.gates)
            {
                if (string.Equals(row.region, region, StringComparison.Ordinal))
                    return atlasCount >= row.atlasRequired;
            }
            return false;
        }
    }
}
