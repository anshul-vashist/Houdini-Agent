import json
import os
import shutil


def _workspace_case_dir(name: str):
    path = os.path.join(os.getcwd(), "tests", "scratch", name)
    shutil.rmtree(path, ignore_errors=True)
    os.makedirs(path, exist_ok=True)
    return path


def test_agentic_controller_forces_tool_action_before_text_completion():
    from houdinimind.agent.agentic_controller import AgenticController

    controller = AgenticController(read_only_tools={"get_scene_summary"})
    plan = {
        "phases": [
            {
                "phase": "2_Build",
                "steps": [
                    {
                        "step": 1,
                        "action": "Create the tabletop box",
                        "node_type": "box",
                        "node_name": "tabletop",
                        "node_path": "/obj/table/tabletop",
                    }
                ],
            }
        ]
    }

    decision = controller.decide_after_text(
        request_mode="build",
        dry_run=False,
        round_num=0,
        max_tool_rounds=8,
        plan_data=plan,
        tool_history=[],
        write_tools=[],
        assistant_response="Done.",
    )

    assert decision.should_continue
    assert decision.reason == "premature_text_without_scene_write"
    assert "You cannot finish yet" in decision.message
    assert "Create the tabletop box" in decision.message


def test_agentic_controller_allows_real_blocking_question():
    from houdinimind.agent.agentic_controller import AgenticController

    controller = AgenticController(read_only_tools=set())
    decision = controller.decide_after_text(
        request_mode="build",
        dry_run=False,
        round_num=0,
        max_tool_rounds=8,
        plan_data=None,
        tool_history=[],
        write_tools=[],
        assistant_response="Which fracture method do you want?",
    )

    assert not decision.should_continue
    assert decision.reason == "awaiting_user_input"


def test_run_loop_uses_agentic_continue_after_premature_text():
    import houdinimind.agent.loop as loop_mod
    from houdinimind.agent.loop import AgentLoop

    tmp = _workspace_case_dir("agentic_continue")
    loop = AgentLoop(
        {
            "data_dir": tmp,
            "ollama_url": "http://localhost:11434",
            "embed_tools_at_startup": False,
            "max_tool_rounds": 4,
        }
    )
    loop._fast_skip_validator = True
    original_tool = loop_mod.TOOL_FUNCTIONS["create_node"]
    calls = {"llm": 0, "tool": 0}
    seen_agentic_continue = {"value": False}
    plan = {
        "phases": [
            {
                "phase": "2_Build",
                "steps": [
                    {
                        "step": 1,
                        "action": "Create a box",
                        "node_type": "box",
                        "node_name": "box1",
                        "node_path": "/obj/geo1/box1",
                    }
                ],
            }
        ]
    }

    def fake_create_node(**_kwargs):
        calls["tool"] += 1
        return {
            "status": "ok",
            "message": "UNDO_TRACK: Created /obj/geo1/box1",
            "data": {"path": "/obj/geo1/box1"},
        }

    def fake_chat(messages, *_args, **_kwargs):
        if calls["llm"] == 0:
            calls["llm"] += 1
            return {"content": "Done without tools.", "tool_calls": []}
        if calls["llm"] == 1:
            seen_agentic_continue["value"] = any(
                "[AGENTIC CONTINUE]" in str(message.get("content", "")) for message in messages
            )
            calls["llm"] += 1
            return {
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "create_node",
                            "arguments": json.dumps(
                                {
                                    "parent_path": "/obj/geo1",
                                    "node_type": "box",
                                    "name": "box1",
                                }
                            ),
                        }
                    }
                ],
            }
        calls["llm"] += 1
        return {"content": "Created the box.", "tool_calls": []}

    try:
        loop_mod.TOOL_FUNCTIONS["create_node"] = fake_create_node
        loop.llm.chat = fake_chat
        result = loop._run_loop(
            [{"role": "user", "content": "Build a box"}],
            request_mode="build",
            plan_data=plan,
        )
    finally:
        loop_mod.TOOL_FUNCTIONS["create_node"] = original_tool
        shutil.rmtree(tmp, ignore_errors=True)

    assert result == "Created the box."
    assert seen_agentic_continue["value"]
    assert calls["tool"] == 1
