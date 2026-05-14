# ==============================================================================
# Creator: Anshul Vashist
# Email: vashistanshul.7@gmail.com
# LinkedIn: https://www.linkedin.com/in/av-0001/
# ==============================================================================
"""Agentic execution policy for normal HoudiniMind turns.

This module keeps the high-risk AgentLoop from accumulating more planning
heuristics inline. It does not execute tools directly; it decides when the
tool loop is allowed to finish and when the model must continue with a
concrete next action.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AgenticPlanStep:
    step_id: str
    phase: str
    action: str
    node_type: str = ""
    node_name: str = ""
    node_path: str = ""
    validation: str = ""


@dataclass(frozen=True)
class AgenticDecision:
    should_continue: bool
    reason: str
    message: str = ""
    next_step: AgenticPlanStep | None = None


class AgenticController:
    """Small policy layer for plan-act-observe-reflect execution."""

    def __init__(self, read_only_tools: set[str] | frozenset[str]):
        self._read_only_tools = frozenset(read_only_tools)

    @staticmethod
    def format_operating_contract(request_mode: str) -> str:
        if request_mode not in {"build", "debug"}:
            return ""
        return (
            "[AGENTIC OPERATING CONTRACT]\n"
            "Run as a goal-directed Houdini agent, not a chat assistant.\n"
            "Cycle: observe the scene, plan the next concrete step, act with tools, "
            "inspect results, repair failures, then continue.\n"
            "Do not produce a final answer until the requested scene change is actually "
            "applied and verified, or until a real blocker requires user input.\n"
            "For build/debug turns, a text-only answer is not completion unless the user "
            "explicitly asked for advice only."
        )

    @staticmethod
    def flatten_plan(plan_data: dict | None) -> list[AgenticPlanStep]:
        if not isinstance(plan_data, dict):
            return []
        steps: list[AgenticPlanStep] = []
        for phase in plan_data.get("phases", []) or []:
            if not isinstance(phase, dict):
                continue
            phase_name = str(phase.get("phase") or "Execution")
            for raw_step in phase.get("steps", []) or []:
                if not isinstance(raw_step, dict):
                    continue
                step_id = str(raw_step.get("step") or len(steps) + 1)
                action = str(raw_step.get("action") or "").strip()
                if not action:
                    continue
                steps.append(
                    AgenticPlanStep(
                        step_id=step_id,
                        phase=phase_name,
                        action=action,
                        node_type=str(raw_step.get("node_type") or "").strip(),
                        node_name=str(raw_step.get("node_name") or "").strip(),
                        node_path=str(raw_step.get("node_path") or "").strip(),
                        validation=str(raw_step.get("validation") or "").strip(),
                    )
                )
        return steps

    def decide_after_text(
        self,
        *,
        request_mode: str,
        dry_run: bool,
        round_num: int,
        max_tool_rounds: int,
        plan_data: dict | None,
        tool_history: list[str],
        write_tools: list[str],
        assistant_response: str,
        enforce_plan_completion: bool = False,
        has_unresolved_tool_failures: bool = False,
    ) -> AgenticDecision:
        if request_mode not in {"build", "debug"}:
            return AgenticDecision(False, "non_agentic_mode")
        if dry_run:
            return AgenticDecision(False, "dry_run_allows_text_plan")
        if round_num >= max_tool_rounds - 1:
            return AgenticDecision(False, "round_limit")

        plan_steps = self.flatten_plan(plan_data)
        has_plan = bool(plan_steps)
        text = (assistant_response or "").strip()
        if self._is_user_input_blocker(text):
            return AgenticDecision(False, "awaiting_user_input")
        if has_unresolved_tool_failures:
            return AgenticDecision(False, "tool_failure_recovery_in_progress")

        if not write_tools:
            next_step = self._first_executable_step(plan_steps)
            return AgenticDecision(
                True,
                "premature_text_without_scene_write",
                self._build_continue_message(
                    reason=(
                        "You tried to answer before applying any scene-changing tool. "
                        "This is a build/debug turn, so text alone is not completion."
                    ),
                    next_step=next_step,
                    tool_history=tool_history,
                    write_tools=write_tools,
                    has_plan=has_plan,
                ),
                next_step,
            )

        if has_plan and enforce_plan_completion:
            next_step = self._next_uncovered_plan_step(plan_steps, tool_history, write_tools, text)
            if next_step:
                return AgenticDecision(
                    True,
                    "plan_step_uncovered",
                    self._build_continue_message(
                        reason="The plan still has an uncovered execution/verification step.",
                        next_step=next_step,
                        tool_history=tool_history,
                        write_tools=write_tools,
                        has_plan=True,
                    ),
                    next_step,
                )

        if self._read_only_tail_is_stalled(tool_history):
            next_step = self._first_executable_step(plan_steps)
            return AgenticDecision(
                True,
                "read_only_stall",
                self._build_continue_message(
                    reason=(
                        "Recent rounds only inspected the scene. You have enough context; "
                        "make the smallest concrete write-tool change now."
                    ),
                    next_step=next_step,
                    tool_history=tool_history,
                    write_tools=write_tools,
                    has_plan=has_plan,
                ),
                next_step,
            )

        return AgenticDecision(False, "completion_allowed")

    @staticmethod
    def _is_user_input_blocker(text: str) -> bool:
        if "?" not in text:
            return False
        lower = text.lower()
        return any(
            marker in lower
            for marker in (
                "which",
                "what",
                "confirm",
                "clarify",
                "need you",
                "need the",
                "do you want",
                "would you like",
            )
        )

    def _next_uncovered_plan_step(
        self,
        plan_steps: list[AgenticPlanStep],
        tool_history: list[str],
        write_tools: list[str],
        assistant_response: str,
    ) -> AgenticPlanStep | None:
        evidence = " ".join([*tool_history, *write_tools, assistant_response]).lower()
        for step in plan_steps:
            phase = step.phase.lower()
            if "inspect" in phase and tool_history:
                continue
            if "verify" in phase and any(
                tool in evidence
                for tool in (
                    "finalize_sop_network",
                    "inspect_display_output",
                    "get_bounding_box",
                    "analyze_geometry",
                    "capture_pane",
                )
            ):
                continue
            markers = [
                step.node_path.lower(),
                step.node_name.lower(),
                step.node_type.lower(),
            ]
            markers = [m for m in markers if m and m not in {"none", "n/a", "-"}]
            if markers and any(marker in evidence for marker in markers):
                continue
            if not markers and write_tools:
                continue
            return step
        return None

    @staticmethod
    def _first_executable_step(plan_steps: list[AgenticPlanStep]) -> AgenticPlanStep | None:
        for step in plan_steps:
            phase = step.phase.lower()
            if "inspect" not in phase:
                return step
        return plan_steps[0] if plan_steps else None

    def _read_only_tail_is_stalled(self, tool_history: list[str]) -> bool:
        if len(tool_history) < 4:
            return False
        tail = tool_history[-4:]
        return all(tool in self._read_only_tools for tool in tail)

    @staticmethod
    def _build_continue_message(
        *,
        reason: str,
        next_step: AgenticPlanStep | None,
        tool_history: list[str],
        write_tools: list[str],
        has_plan: bool,
    ) -> str:
        lines = [
            "[AGENTIC CONTINUE]",
            reason,
            "",
            "You cannot finish yet.",
            "Do not summarize yet. Continue the plan-act-observe loop now.",
        ]
        if next_step:
            lines.extend(
                [
                    "",
                    "NEXT REQUIRED STEP:",
                    f"- Phase: {next_step.phase}",
                    f"- Step: {next_step.step_id}",
                    f"- Action: {next_step.action}",
                ]
            )
            if next_step.node_type:
                lines.append(f"- Node type: {next_step.node_type}")
            if next_step.node_name:
                lines.append(f"- Node name: {next_step.node_name}")
            if next_step.node_path:
                lines.append(f"- Expected path: {next_step.node_path}")
            if next_step.validation:
                lines.append(f"- Validation: {next_step.validation}")
        elif has_plan:
            lines.append("- Re-read the plan above and execute the first unfinished write step.")
        else:
            lines.append("- Choose the smallest safe tool action that advances the user's goal.")

        if tool_history:
            lines.append("")
            lines.append("Recent tools: " + ", ".join(tool_history[-10:]))
        if write_tools:
            lines.append("Write tools already used: " + ", ".join(write_tools[-10:]))

        lines.extend(
            [
                "",
                "Rules:",
                "1. Use write tools for actual scene changes; read tools alone are not progress.",
                "2. Do not restart completed work.",
                "3. If a required detail is unknown, inspect only that detail, then act.",
                "4. Stop only after the scene satisfies the request or a real blocker remains.",
            ]
        )
        return "\n".join(lines)


def summarize_agentic_plan(plan_data: dict | None) -> dict[str, Any]:
    steps = AgenticController.flatten_plan(plan_data)
    return {
        "step_count": len(steps),
        "phases": sorted({step.phase for step in steps}),
        "has_build_steps": any("inspect" not in step.phase.lower() for step in steps),
    }
