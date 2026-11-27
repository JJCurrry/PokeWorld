using System;
using System.Collections.Generic;

namespace PokeWorld.Core
{
    // @trace MECH-005
    public sealed class AtlasEntry
    {
        public readonly string CreatureId;
        public readonly string Region;
        public readonly string Terrain;
        public readonly string Phase;
        public AtlasEntry(string creatureId, string region, string terrain, string phase)
        {
            CreatureId = creatureId; Region = region; Terrain = terrain; Phase = phase;
        }
    }

    public sealed class AtlasSystem
    {
        private readonly Dictionary<string, AtlasEntry> entries = new Dictionary<string, AtlasEntry>();

        public int Count { get { return entries.Count; } }

        // 唯一登记入口：重复登记只覆盖，不增殖。
        public void Observe(AtlasEntry entry)
        {
            if (entry == null) throw new ArgumentNullException(nameof(entry));
            entries[entry.CreatureId] = entry;
        }

        public bool Contains(string creatureId) { return entries.ContainsKey(creatureId); }
    }
}
