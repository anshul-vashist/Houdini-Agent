import os
import sys
import unittest
from unittest.mock import MagicMock

# Setup path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(ROOT, "src"))

# Mock hou before imports
sys.modules["hou"] = MagicMock()
import hou

hou.parmTemplateType = MagicMock()
hou.parmTemplateType.Int = 1
hou.parmTemplateType.Float = 2
hou.parmTemplateType.Toggle = 3
hou.parmTemplateType.Menu = 4

import houdinimind.agent.scene_observer as scene_observer_mod
from houdinimind.agent.scene_observer import SceneObserver
from houdinimind.agent.tool_selection import select_relevant_tool_schemas
from houdinimind.agent.tools import _core as core
from houdinimind.agent.tools import _scene_tools as scene_tools


class TestIntelligence(unittest.TestCase):
    def test_parameter_aliases(self):
        print("\nTesting Parameter Aliases...")
        # Verify new aliases are present
        self.assertEqual(core._PARM_BASE_ALIASES.get("dimensions"), "size")
        self.assertEqual(core._PARM_BASE_ALIASES.get("resolution"), "divs")
        self.assertEqual(core._PARM_COMPONENT_ALIASES.get("red"), "x")
        print("✓ New aliases verified.")

    def test_fuzzy_matching_logic(self):
        print("\nTesting Fuzzy Matching Logic...")
        # Mock LLM chat function
        mock_chat = MagicMock(return_value="size")
        core._shared_chat_simple_fn = mock_chat

        pool = ["size", "t", "r"]
        labels = {"size": "Dimensions"}

        # Test deterministic resolution still works
        res = core._resolve_parameter_name("dimensions", pool, labels_by_name=labels)
        self.assertEqual(res["resolved"], "size")
        self.assertEqual(res["reason"], "alias")

        # Ambiguous fuzzy resolution must not call the LLM from parameter
        # resolution. This path runs inside Houdini tool execution, often on
        # the main thread.
        res = core._resolve_parameter_name("scale it up", pool, labels_by_name=labels)
        self.assertEqual(res["status"], "unresolved")
        self.assertEqual(res["resolved"], "")
        mock_chat.assert_not_called()
        print("✓ Fuzzy matching logic verified.")

    def test_scene_observer_bypass(self):
        print("\nTesting SceneObserver Bypass Detection...")
        obs = SceneObserver()

        # Mock a node
        mock_node = MagicMock()
        mock_node.path.return_value = "/obj/test"
        mock_node.type().name.return_value = "box"
        mock_node.inputs.return_value = []
        mock_node.isDisplayFlagSet.return_value = True
        mock_node.isRenderFlagSet.return_value = True
        mock_node.isBypassed.return_value = True

        mock_parent = MagicMock()
        mock_parent.children.return_value = [mock_node]
        hou.node.return_value = mock_parent

        # This will use the mock
        graph = obs._build_scene_graph()
        self.assertTrue(graph[0].get("bypass"))
        print("✓ Bypass detection in SceneObserver verified.")

    def test_scene_observer_skips_dirty_geometry_empty_check(self):
        obs = SceneObserver()
        mock_node = MagicMock()
        mock_node.path.return_value = "/obj/test/dirty_sop"
        mock_node.type().name.return_value = "attribwrangle"
        mock_node.type().category().name.return_value = "Sop"
        mock_node.type().minInConnectors.return_value = 0
        mock_node.inputs.return_value = []
        mock_node.errors.return_value = []
        mock_node.warnings.return_value = []
        mock_node.isDirty.return_value = True
        mock_node.geometry.side_effect = AssertionError("dirty geometry would force a cook")

        issues = obs._detect_scene_issues(
            [
                {
                    "path": "/obj/test/dirty_sop",
                    "type": "attribwrangle",
                    "bypass": False,
                    "_ref": mock_node,
                }
            ]
        )

        self.assertEqual(issues, [])
        mock_node.geometry.assert_not_called()

    def test_vex_structured_error(self):
        print("\nTesting VEX Structured Error Return...")
        # Mock node
        mock_node = MagicMock()
        hou.node.return_value = mock_node

        # Mock checker to return failure
        import houdinimind.agent.tools._node_tools as nt

        original_hou = getattr(nt, "hou", None)
        original_available = nt.HOU_AVAILABLE
        original_core_available = core.HOU_AVAILABLE
        original_validator = nt._validate_vex_with_checker
        try:
            nt.hou = hou
            nt.HOU_AVAILABLE = True
            core.HOU_AVAILABLE = True
            nt._validate_vex_with_checker = MagicMock(
                return_value={
                    "success": False,
                    "errors": ["Syntax error at line 1"],
                    "warnings": [],
                }
            )
            res = nt.write_vex_code("/obj/wrangle", "@P.y += 1")
        finally:
            nt.hou = original_hou
            nt.HOU_AVAILABLE = original_available
            core.HOU_AVAILABLE = original_core_available
            nt._validate_vex_with_checker = original_validator

        self.assertEqual(res["status"], "error")
        self.assertEqual(res["data"]["status"], "validation_failed")
        self.assertIn("Syntax error", res["data"]["errors"][0])
        print("✓ VEX structured error return verified.")

    def test_vex_checker_destroys_temp_container(self):
        class FakeParm:
            def set(self, value):
                self.value = value

        class FakeWrangle:
            def parm(self, name):
                return FakeParm() if name == "snippet" else None

            def cook(self, force=False):
                return None

            def errors(self):
                return ()

            def warnings(self):
                return ()

        class FakeTempGeo:
            def __init__(self):
                self.destroyed = False

            def hide(self, flag):
                self.hidden = flag

            def createNode(self, node_type, name=None):
                self.created = (node_type, name)
                return FakeWrangle()

            def destroy(self, disable_safety_checks=False):
                self.destroyed = True
                self.disable_safety_checks = disable_safety_checks

        class FakeObj:
            def __init__(self):
                self.temp_geo = None

            def node(self, name):
                return self.temp_geo if name == "__HOUDINIMIND_TEMP_GEO__" else None

            def createNode(self, node_type, name=None):
                self.created = (node_type, name)
                self.temp_geo = FakeTempGeo()
                return self.temp_geo

        class FakeHou:
            def __init__(self):
                self.obj = FakeObj()

            def node(self, path):
                return self.obj if path == "/obj" else None

        original_hou = core.hou
        original_available = core.HOU_AVAILABLE
        original_vcc = core._validate_vex_with_vcc
        fake_hou = FakeHou()
        try:
            core.hou = fake_hou
            core.HOU_AVAILABLE = True
            core._validate_vex_with_vcc = MagicMock(return_value={"status": "compiler_not_found"})
            res = core._validate_vex_with_checker("int i = 1;")
        finally:
            core.hou = original_hou
            core.HOU_AVAILABLE = original_available
            core._validate_vex_with_vcc = original_vcc

        self.assertTrue(res["success"])
        self.assertTrue(fake_hou.obj.temp_geo.destroyed)
        self.assertTrue(fake_hou.obj.temp_geo.disable_safety_checks)

    def test_get_all_errors_filters_houdinimind_scratch_nodes(self):
        class FakeObserver:
            def observe(self):
                return {
                    "issues": [
                        {
                            "path": "/obj/__HOUDINIMIND_TEMP_GEO__/__HOUDINIMIND_VEX_CHECKER__1",
                            "severity": "error",
                            "messages": ["internal checker error"],
                        },
                        {
                            "path": "/obj/geo1/wrangle1",
                            "severity": "error",
                            "messages": ["real error"],
                        },
                    ]
                }

        original_observer = scene_observer_mod.SceneObserver
        original_available = core.HOU_AVAILABLE
        try:
            scene_observer_mod.SceneObserver = FakeObserver
            core.HOU_AVAILABLE = True
            res = scene_tools.get_all_errors()
        finally:
            scene_observer_mod.SceneObserver = original_observer
            core.HOU_AVAILABLE = original_available

        self.assertEqual(res["status"], "ok")
        nodes = res["data"]["nodes"]
        self.assertEqual([node["path"] for node in nodes], ["/obj/geo1/wrangle1"])

    def test_pyro_tool_selection_prefers_sop_diagnostics(self):
        schemas = [
            {"function": {"name": name, "description": name, "parameters": {"type": "object"}}}
            for name in (
                "get_scene_summary",
                "create_node",
                "safe_set_parameter",
                "connect_nodes",
                "verify_node_type",
                "layout_network",
                "get_node_parameters",
                "get_all_errors",
                "search_knowledge",
                "audit_spatial_layout",
                "batch_set_parameters",
                "create_node_chain",
                "set_display_flag",
                "finalize_sop_network",
                "save_hip",
                "get_simulation_diagnostic",
                "get_sim_stats",
                "get_dop_objects",
            )
        ]

        selected = select_relevant_tool_schemas(
            "create sop level pyro smoke fx",
            schemas,
            top_n=len(schemas),
        )
        names = [schema["function"]["name"] for schema in selected]

        self.assertIn("get_simulation_diagnostic", names)
        self.assertIn("search_knowledge", names)
        self.assertNotIn("get_dop_objects", names[: names.index("get_simulation_diagnostic") + 1])
        print("✓ Pyro tool selection prefers SOP diagnostics.")

    def test_particle_sim_tool_selection_uses_diagnostics_and_rag(self):
        schemas = [
            {"function": {"name": name, "description": name, "parameters": {"type": "object"}}}
            for name in (
                "get_scene_summary",
                "create_node",
                "safe_set_parameter",
                "connect_nodes",
                "search_knowledge",
                "get_sim_stats",
                "get_dop_objects",
                "bake_simulation",
            )
        ]

        selected = select_relevant_tool_schemas(
            "create a particle simulation with pop forces",
            schemas,
            top_n=len(schemas),
        )
        names = [schema["function"]["name"] for schema in selected]

        self.assertIn("search_knowledge", names)
        self.assertIn("get_sim_stats", names)
        self.assertIn("get_dop_objects", names)


if __name__ == "__main__":
    unittest.main()
