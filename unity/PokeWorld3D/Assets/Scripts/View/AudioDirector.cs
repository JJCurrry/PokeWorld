using UnityEngine;

namespace PokeWorld.View
{
    // @trace AUD-001
    public sealed class AudioDirector : MonoBehaviour
    {
        [SerializeField] private AudioSource exploreTheme;
        [SerializeField] private AudioSource battleTheme;
        public float crossfadeSeconds = 0.5f;

        public void EnterBattle()
        {
            if (exploreTheme != null) exploreTheme.volume = 0f;
            if (battleTheme != null) battleTheme.volume = 1f;
            Debug.Log("[AudioDirector] enter battle, fade=" + crossfadeSeconds.ToString("F1"));
        }
    }
}
