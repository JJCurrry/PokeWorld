using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace PokeWorld.Editor
{
    // @trace PLAT-002
    public static class SceneBootstrapBuilder
    {
        [MenuItem("Tools/PokeWorld/Build Bootstrap Scene")]
        public static void Build()
        {
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            var root = new GameObject("GameRoot");
            root.AddComponent<PokeWorld.Core.GameBootstrap>();
            const string path = "Assets/Scenes/Main.unity";
            EditorSceneManager.SaveScene(scene, path);
            EditorBuildSettings.scenes = new[] { new EditorBuildSettingsScene(path, true) };
            AssetDatabase.Refresh();
            Debug.Log("[SceneBootstrapBuilder] scene built and added to build settings: " + path);
        }
    }
}
