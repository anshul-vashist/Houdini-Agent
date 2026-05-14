# ==============================================================================
# Creator: Anshul Vashist
# Email: vashistanshul.7@gmail.com
# LinkedIn: https://www.linkedin.com/in/av-0001/
# ==============================================================================
"""Component boundaries for AgentLoop phases.

These classes are intentionally thin adapters for now: they establish explicit
phase interfaces without forcing a high-risk rewrite of the existing loop in
one patch. New behavior should land here first and then shrink AgentLoop over
time.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class PhaseContext:
    user_message: str
    request_mode: str
    before_snapshot: dict | None = None
    after_snapshot: dict | None = None
    plan_data: dict | None = None


class PlanningPhase:
    def __init__(self, planner: Any | None):
        self.planner = planner

    def build_plan(self, user_goal: str, scene_context: str = "") -> dict | None:
        if self.planner is None:
            return None
        return self.planner.generate_plan(user_goal, scene_context=scene_context)

    def build_replan(
        self,
        user_goal: str,
        verification_report: dict,
        scene_context: str = "",
        previous_plan: dict | None = None,
    ) -> dict | None:
        if self.planner is None:
            return None
        if hasattr(self.planner, "generate_repair_plan"):
            return self.planner.generate_repair_plan(
                user_goal,
                verification_report=verification_report,
                scene_context=scene_context,
                previous_plan=previous_plan,
            )
        return self.planner.generate_plan(user_goal, scene_context=scene_context)


class VerificationPhase:
    def __init__(self, runner: Callable[..., dict | None]):
        self._runner = runner

    def run(
        self,
        user_message: str,
        before_snapshot: dict | None,
        after_snapshot: dict | None,
        request_mode: str,
        stream_callback: Callable | None = None,
        verification_profile: str = "full",
    ) -> dict | None:
        return self._runner(
            user_message,
            before_snapshot,
            after_snapshot,
            request_mode,
            stream_callback=stream_callback,
            verification_profile=verification_profile,
        )


class ToolExecutionPhase:
    def __init__(self, executor: Callable[..., dict]):
        self._executor = executor

    def run(self, tool_name: str, args: dict, **kwargs) -> dict:
        return self._executor(tool_name, args, **kwargs)


class VisionPhase:
    def __init__(self, screenshot_fn: Callable[..., str | None]):
        self._screenshot_fn = screenshot_fn

    def capture_final(self, label: str = "Final Verification", pane_type: str = "viewport"):
        return self._screenshot_fn(label, pane_type=pane_type, force_refresh=True)


class RepairPhase:
    def __init__(self, message_builder: Callable[..., str]):
        self._message_builder = message_builder

    def build_message(
        self,
        user_message: str,
        verification_report: dict,
        replan: dict | None = None,
    ) -> str:
        base = self._message_builder(user_message, verification_report)
        if not replan:
            return base
        return (
            "[REPLAN REQUIRED]\n"
            "The previous approach failed validation. Stop patching from the same mental model; "
            "use this new targeted plan before making more edits.\n\n"
            f"TARGETED REPLAN:\n{replan}\n\n"
            f"{base}"
        )


class HistoryManager:
    def __init__(self, compress_fn: Callable[[], None]):
        self._compress_fn = compress_fn

    def compress_if_needed(self) -> None:
        self._compress_fn()


class SceneStateManager:
    def __init__(
        self,
        snapshot_fn: Callable[[], dict | None],
        update_world_model_fn: Callable[[dict | None], None],
    ):
        self._snapshot_fn = snapshot_fn
        self._update_world_model_fn = update_world_model_fn

    def refresh_after_write(self) -> dict | None:
        snapshot = self._snapshot_fn()
        self._update_world_model_fn(snapshot)
        return snapshot


class SimulationHealthPhase:
    def __init__(self, diagnostic_runner: Callable[[dict, list[str], Callable | None], list[dict]]):
        self._diagnostic_runner = diagnostic_runner

    def run(
        self,
        after_snapshot: dict,
        parent_paths: list[str],
        stream_callback: Callable | None = None,
    ) -> list[dict]:
        return self._diagnostic_runner(after_snapshot, parent_paths, stream_callback)
