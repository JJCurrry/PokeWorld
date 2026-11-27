using UnityEngine;

namespace PokeWorld.Core
{
    // @trace MECH-003
    public sealed class EncounterSystem : MonoBehaviour
    {
        public const float AlertRadius = 8f;
        public const float DisengageRadius = 20f;

        [SerializeField] private Transform wildCreature;
        private bool inBattle;

        private void Update()
        {
            if (wildCreature == null) return;
            float distance = Vector3.Distance(transform.position, wildCreature.position);
            if (!inBattle && distance <= AlertRadius)
            {
                inBattle = true;
                Debug.Log("[EncounterSystem] battle start, distance=" + distance.ToString("F2"));
            }
            else if (inBattle && distance >= DisengageRadius)
            {
                inBattle = false;
                Debug.Log("[EncounterSystem] disengage, distance=" + distance.ToString("F2"));
            }
        }
    }
}
