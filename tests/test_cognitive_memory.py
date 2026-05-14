from houdinimind.agent.workflow_state import WorkflowStateStore
from houdinimind.memory.cognitive_memory import CognitiveMemoryStore
from houdinimind.memory.memory_manager import MemoryManager


def test_cognitive_memory_ranks_failure_context(tmp_path):
    store = CognitiveMemoryStore(str(tmp_path / "memory.db"))
    store.store_memory(
        kind="failure",
        content=(
            "Request: build a table\n"
            "Tool: safe_set_parameter\n"
            "Message: parm height does not exist on box; use sizey"
        ),
        summary="safe_set_parameter failed because height is not a box parm",
        tags=["tool:safe_set_parameter", "box", "parm"],
        importance=0.9,
        confidence=0.95,
    )
    store.store_memory(
        kind="semantic",
        content="Generic note about Houdini viewport navigation.",
        summary="viewport navigation",
        tags=["viewport"],
        importance=0.3,
        confidence=0.8,
    )

    hits = store.retrieve("fix box height parameter with safe_set_parameter", limit=2)

    assert hits
    assert hits[0].kind == "failure"
    assert "height" in hits[0].summary


def test_cognitive_memory_deduplicates_and_reinforces(tmp_path):
    store = CognitiveMemoryStore(str(tmp_path / "memory.db"))
    first = store.store_memory(
        kind="reflection",
        content="Use finalize_sop_network after creating loose SOP branches.",
        tags=["finalize", "sop"],
    )
    second = store.store_memory(
        kind="reflection",
        content="Use finalize_sop_network after creating loose SOP branches.",
        tags=["sop", "finalize"],
    )

    assert first == second
    stats = store.stats()
    assert stats["total_memories"] == 1
    assert store.retrieve("loose SOP branches finalize", limit=1)[0].score > 0


def test_memory_manager_records_tool_failures_into_retrievable_context(tmp_path):
    manager = MemoryManager(str(tmp_path))
    manager.start_interaction("Build a table with box legs")
    manager.log_tool_call(
        "safe_set_parameter",
        {"node_path": "/obj/table/leg", "parm_name": "height", "value": 4},
        {
            "status": "error",
            "message": "Parameter height does not exist. Did you mean sizey?",
            "_correction_hint": "Use sizey for box height.",
        },
    )

    context = manager.retrieve_agent_context("box height parameter table leg", limit=4)

    assert "[AGENT MEMORY CONTEXT]" in context
    assert "safe_set_parameter" in context
    assert "sizey" in context


def test_workflow_state_store_persists_plan_events_and_status(tmp_path):
    store = WorkflowStateStore(str(tmp_path / "workflow.db"))
    run_id = store.start_run(user_goal="Build a chair", request_mode="build")
    store.update_plan(run_id, {"mission": "Build a chair", "phases": []})
    store.append_event(
        run_id,
        "tool_result",
        {"tool": "create_node", "status": "ok", "message": "Created /obj/chair"},
    )
    store.update_checkpoint(run_id, "/tmp/chair_backup.hip")
    store.finish_run(run_id, status="completed", summary="Chair built")

    run = store.load_run(run_id)

    assert run is not None
    assert run["status"] == "completed"
    assert run["checkpoint_path"] == "/tmp/chair_backup.hip"
    assert run["events"][0]["event_type"] == "run_started"
    assert any(event["event_type"] == "tool_result" for event in run["events"])
