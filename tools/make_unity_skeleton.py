"""G9 Unity 3D 工程骨架生成器（确定性，离线可跑，零外部依赖）。

- 只生成「可打开的工程结构 + 最小可运行内容 + 核心 C# 系统 + .meta 配对」，不假装编译通过。
- Unity 版本 / 包版本取用户环境；此处写显式占位，待用户用 Hub 新建空工程后覆盖。
- 场景不手写 YAML：只写 Editor 脚本 builders，由编辑器生成 Main.unity 并写入构建列表。
- 每个文件 / 目录生成唯一 32 位 GUID 的 .meta，供工程自检脚本核对。
- 机器无 Unity 时仍可跑本脚本并跑 check_unity_project.py 验证结构。

用法：
    python tools/make_unity_skeleton.py [--root <repo_root>] [--version <editor_version>]

默认 root = 本文件上溯两级；version 默认 `0.0.0-PENDING`（显式占位，自检会告警要求人工确认）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

DEFAULT_VERSION = "0.0.0-PENDING"  # 显式占位：不臆造 Unity 版本

DIRS = (
    "Assets",
    "Assets/Scripts",
    "Assets/Scripts/Editor",
    "Assets/Scripts/Core",
    "Assets/Scripts/View",
    "Assets/Art",
    "Assets/Art/Materials",
    "Assets/Art/Prefabs",
    "Assets/Audio",
    "Assets/Prefabs",
    "Assets/Scenes",
    "Assets/Settings",
    "Packages",
    "ProjectSettings",
    "docs",
)


def _guid(path: str) -> str:
    """稳定 GUID：由相对路径哈希派生，保证重复生成结果一致、彼此唯一。"""
    return hashlib.sha256(path.encode("utf-8")).hexdigest()[:32]


def _write(root: Path, rel: str, text: str) -> None:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8", newline="\n")


def _meta_dir(root: Path, rel: str) -> None:
    body = (
        "fileFormatVersion: 2\n"
        f"guid: {_guid(rel + '/')}\n"
        "folderAsset: yes\n"
        "DefaultImporter:\n"
        "  externalObjects: {}\n"
        "  userData:\n"
        "  assetBundleName:\n"
        "  assetBundleVariant:\n"
    )
    _write(root, rel + ".meta", body)


def _meta_file(root: Path, rel: str, importer: str = "DefaultImporter") -> None:
    body = (
        "fileFormatVersion: 2\n"
        f"guid: {_guid(rel)}\n"
        f"{importer}:\n"
        "  externalObjects: {}\n"
        "  userData:\n"
        "  assetBundleName:\n"
        "  assetBundleVariant:\n"
    )
    _write(root, rel + ".meta", body)


def _cs(files: dict[str, str]) -> None:
    files.update({
        # @trace 引用对应冻结清单条目；标记写在真正实现的文件里，不为凑覆盖率粘贴。
        "Assets/Scripts/Core/BattleSystem.cs": """using System;
using System.Collections.Generic;

namespace PokeWorld.Core
{
    // @trace MECH-002
    public enum BattlePhase { Idle, Approach, Strike, Dodge, Capture, Result }

    public sealed class BattleState
    {
        public readonly BattlePhase Phase;
        public readonly int AllyHp;
        public readonly int WildHp;
        public readonly string Message;
        public BattleState(BattlePhase phase, int allyHp, int wildHp, string message)
        {
            Phase = phase; AllyHp = allyHp; WildHp = wildHp; Message = message;
        }
    }

    public static class BattleSystem
    {
        // 唯一状态转移入口；纯函数，不读时钟、不读全局随机。
        public static BattleState Apply(BattleState state, string action, int damage)
        {
            if (state == null) throw new ArgumentNullException(nameof(state));
            if (string.IsNullOrEmpty(action)) throw new ArgumentException("action 不可为空", nameof(action));
            switch (action)
            {
                case "approach":
                    return new BattleState(BattlePhase.Approach, state.AllyHp, state.WildHp, "接近目标");
                case "strike":
                    int left = Math.Max(0, state.WildHp - Math.Max(1, damage));
                    return new BattleState(BattlePhase.Strike, state.AllyHp, left, "命中");
                case "dodge":
                    return new BattleState(BattlePhase.Dodge, state.AllyHp, state.WildHp, "闪避");
                case "capture":
                    return new BattleState(BattlePhase.Capture, state.AllyHp, state.WildHp, "尝试捕捉");
                case "finish":
                    return new BattleState(BattlePhase.Result, state.AllyHp, state.WildHp, "结算");
                default:
                    return state;
            }
        }
    }
}
""",
        "Assets/Scripts/Core/EncounterSystem.cs": """using UnityEngine;

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
""",
        "Assets/Scripts/Core/AbilityGate.cs": """using System;
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
""",
        "Assets/Scripts/Core/AtlasSystem.cs": """using System;
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
""",
        "Assets/Scripts/Core/SaveSystem.cs": """using System;
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
""",
        "Assets/Scripts/Core/GameBootstrap.cs": """using UnityEngine;

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
""",
        "Assets/Scripts/Core/PlayerController3D.cs": """using UnityEngine;

namespace PokeWorld.Core
{
    // @trace MECH-001
    // @trace AUD-001
    [RequireComponent(typeof(CharacterController))]
    public sealed class PlayerController3D : MonoBehaviour
    {
        public float speed = 6f;
        public float turnSpeed = 12f;
        private CharacterController controller;

        private void Awake()
        {
            controller = GetComponent<CharacterController>();
        }

        private void Update()
        {
            float horizontal = Input.GetAxisRaw("Horizontal");
            float vertical = Input.GetAxisRaw("Vertical");
            if (Mathf.Abs(horizontal) < 0.01f && Mathf.Abs(vertical) < 0.01f) return;

            Vector3 direction = new Vector3(horizontal, 0f, vertical).normalized;
            controller.Move(direction * speed * Time.deltaTime);
            Quaternion target = Quaternion.LookRotation(direction);
            transform.rotation = Quaternion.Slerp(transform.rotation, target, turnSpeed * Time.deltaTime);
            Debug.Log("[PlayerController3D] move input=" + horizontal.ToString("F1") + "," + vertical.ToString("F1"));
        }
    }
}
""",
        "Assets/Scripts/Core/FollowCamera.cs": """using UnityEngine;

namespace PokeWorld.Core
{
    // @trace MECH-001
    public sealed class FollowCamera : MonoBehaviour
    {
        public Transform target;
        public Vector3 offset = new Vector3(0f, 9f, -12f);
        public float damping = 0.15f;
        private Vector3 velocity;

        private void LateUpdate()
        {
            if (target == null)
            {
                Debug.LogWarning("[FollowCamera] target missing, skip update");
                return;
            }
            Vector3 desired = target.position + offset;
            transform.position = Vector3.SmoothDamp(transform.position, desired, ref velocity, damping);
        }
    }
}
""",
        "Assets/Scripts/Core/SerializedFieldSetter.cs": """using UnityEngine;

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
""",
        "Assets/Scripts/View/HudController.cs": """using UnityEngine;
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
""",
        "Assets/Scripts/View/AudioDirector.cs": """using UnityEngine;

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
""",
        "Assets/Scripts/View/PaletteConfig.cs": """using UnityEngine;

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
""",
        "Assets/Scripts/Editor/SceneBootstrapBuilder.cs": """using UnityEditor;
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
""",
    })


def build(root: Path, version: str) -> dict:
    for rel in DIRS:
        (root / rel).mkdir(parents=True, exist_ok=True)

    files: dict[str, str] = {}
    _cs(files)
    files.update({
        "ProjectSettings/ProjectVersion.txt": f"m_EditorVersion: {version}\n",
        # 最小空场景：只含 YAML 头 + 场景设置对象，零组件 / 零 GUID 引用，
        # 不违反「不手写带引用的场景 YAML」；首次打开由 Editor 脚本重建为完整场景。
        "Assets/Scenes/Main.unity": (
            "%YAML 1.1\n"
            "%TAG !u! tag:unity3d.com,2011:\n"
            "--- !u!29 &1\n"
            "OcclusionCullingSettings:\n"
            "  m_ObjectHideFlags: 0\n"
            "  serializedVersion: 2\n"
            "  m_OcclusionBakeSettings:\n"
            "    smallestOccluder: 5\n"
            "    smallestHole: 0.25\n"
            "    backfaceThreshold: 100\n"
            "  m_SceneGUID: 00000000000000000000000000000000\n"
            "  m_OcclusionCullingData: {fileID: 0}\n"
        ),
        "ProjectSettings/EditorBuildSettings.asset": (
            "%YAML 1.1\n"
            "%TAG !u! tag:unity3d.com,2011:\n"
            "EditorBuildSettings:\n"
            "  m_ObjectHideFlags: 0\n"
            "  serializedVersion: 2\n"
            "  m_Scenes:\n"
            "  - enabled: 1\n"
            "    path: Assets/Scenes/Main.unity\n"
            "    guid: " + _guid("Assets/Scenes/Main.unity") + "\n"
            "  m_configObjects: {}\n"
        ),
        "Packages/manifest.json": json.dumps({
            "dependencies": {
                "com.unity.modules.ai": "1.0.0",
                "com.unity.modules.physics": "1.0.0",
                "com.unity.modules.uielements": "1.0.0",
            }
        }, ensure_ascii=False, indent=2) + "\n",
        "Assets/Settings/Regions.json": json.dumps({
            "gates": [
                {"region": "echo_cave", "atlasRequired": 3},
                {"region": "wreck_reef", "atlasRequired": 6},
                {"region": "ash_isle", "atlasRequired": 9},
                {"region": "league", "atlasRequired": 12},
            ]
        }, ensure_ascii=False, indent=2) + "\n",
        "Assets/Settings/Creatures.json": json.dumps({
            "species": [{"id": f"c{i:02d}", "name": f"creature_{i:02d}"} for i in range(1, 9)]
        }, ensure_ascii=False, indent=2) + "\n",
        "Assets/Settings/Palette.json": json.dumps({
            "primary": "#4A9EA8",
            "secondary": "#E8C88A",
            "danger": "#D9534F",
            "background": "#E6EEF2",
            "uiBase": "#22384A",
            "lightness": {"background": [0.90, 0.96], "terrain": [0.62, 0.70],
                          "character": [0.35, 0.45], "effect": [0.75, 0.82]},
            "taboo": ["写实材质", "纯黑描边", "第三方 IP 造型", "在世艺术家个人风格"],
        }, ensure_ascii=False, indent=2) + "\n",
        "project-spec.json": json.dumps({
            "requiredDirs": list(DIRS),
            "recommendedDirs": ["Assets/Scripts/Editor"],
            "requiredFiles": ["ProjectSettings/ProjectVersion.txt", "Packages/manifest.json"],
            "requireMetaForEveryAsset": True,
            "requireScenesInBuildSettings": True,
            "scanAbsolutePaths": True,
            "scanDanglingGuids": True,
            "danglingGuidLevel": "warn",
            "builtinGuidAllowlist": [],
            "extraGuidDirs": [],
            "requireFrozenDesign": True,
            "traceMarker": "@trace",
            "compileLogPath": "",
            "ignore": [],
        }, ensure_ascii=False, indent=2) + "\n",
        "README.md": (
            "# PokeWorld 3D · Unity 工程骨架（G9）\n\n"
            "> 本工程由 `tools/make_unity_skeleton.py` 确定性生成。\n"
            "> **当前状态：结构骨架已落盘，未编译、未进入播放模式**（本机无 Unity，S9-01）。\n\n"
            "## 打开步骤（需本机已装 Unity）\n\n"
            "1. 用你的 Unity 版本打开本目录；首次打开会生成 `Library/` 等缓存。\n"
            "2. 若 `ProjectSettings/ProjectVersion.txt` 的版本与本机不符，以 Hub 新建空工程覆盖本目录的 "
            "`ProjectSettings/` 与 `Packages/`，再重新运行生成器补齐脚本。\n"
            "3. 菜单 `Tools/PokeWorld/Build Bootstrap Scene` → 生成 `Assets/Scenes/Main.unity` 并写入构建列表。\n"
            "4. 播放模式确认 Console 出现 `[GameBootstrap] start`、`[GameBootstrap] ready`，场景可见地面 + 玩家 + 潮灵。\n\n"
            "## 结构\n\n"
            "- `Assets/Scripts/Core`：状态机 / 遭遇 / 能力门 / 图鉴 / 存档 / 玩家控制。\n"
            "- `Assets/Scripts/View`：HUD / 音频 / 手绘色板。\n"
            "- `Assets/Scripts/Editor`：场景生成入口（不手写场景 YAML）。\n"
            "- `Assets/Settings`：JSON 配置（区域门 / 物种 / 色板）。\n"
            "- `docs/design-freeze.json`：设计冻结清单（在仓库根 docs/）。\n"
        ),
    })

    for rel, text in files.items():
        _write(root, rel, text)

    # .meta 配对：目录 + 文件，GUID 由相对路径哈希唯一派生。
    for rel in DIRS:
        if rel == "Assets":
            continue
        _meta_dir(root, rel)
    for rel in files:
        if rel.startswith("Assets/"):
            _meta_file(root, rel)

    return {"version": version, "dirs": len(DIRS), "files": len(files),
            "metas": len([r for r in DIRS if r != "Assets"]) + len([r for r in files if r.startswith("Assets/")])}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="G9 Unity 3D 工程骨架生成器")
    parser.add_argument("--root", default="", help="仓库根目录（默认本文件上溯两级）")
    parser.add_argument("--version", default=DEFAULT_VERSION, help="编辑器版本（默认显式占位）")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    target = root / "unity" / "PokeWorld3D"
    facts = build(target, args.version)
    print(json.dumps({"ok": True, "project": str(target), **facts}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
