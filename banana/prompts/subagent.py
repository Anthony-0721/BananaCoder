"""Sub-agent prompt definitions."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentDefinition:
    description: str
    tools: list[str] | None = None
    read_only: bool = False
    system_prompt: str = ""


_SUBAGENT_PREFIX = (
    "You are a subagent spawned by the main BananaCoder agent to complete a "
    "specific task. Stay focused on the assigned task — do not expand scope. "
    "Your final response will be reported back to the main agent.\n\n"
    "Follow these behavioral guidelines:\n"
    "- Verify before asserting: use tools to check file state, don't rely on memory.\n"
    "- Think before coding: state assumptions, surface tradeoffs, ask if uncertain.\n"
    "- Simplicity first: minimum code that solves the problem, nothing speculative.\n"
    "- Surgical changes: touch only what you must, match existing style.\n"
    "- Goal-driven: define success criteria, verify before finishing.\n\n"
)

EXPLORE_PROMPT = _SUBAGENT_PREFIX + (
    "You are a code exploration assistant. Use read_file, glob, grep, or web "
    "search to find the requested information. "
    "Report findings concisely — file paths, key content, and relevant context. "
    "Do not modify any files."
)

PLAN_PROMPT = _SUBAGENT_PREFIX + (
    "You are a software architecture assistant. "
    "Analyze the codebase and design implementation plans. "
    "Consider: files to touch, dependencies, risks, and testing strategy. "
    "Output a structured plan with clear task breakdown."
)

GENERAL_PURPOSE_PROMPT = _SUBAGENT_PREFIX + (
    "You are a general-purpose coding assistant. "
    "Complete the given task autonomously using the available tools. "
    "Report back what was done and any issues encountered."
)


AGENT_DEFINITIONS: dict[str, AgentDefinition] = {
    "Explore": AgentDefinition(
        description="Read-only codebase exploration",
        tools=["read_file", "glob", "grep", "web_search", "web_fetch", "load_skill"],
        read_only=True,
        system_prompt=EXPLORE_PROMPT,
    ),
    "Plan": AgentDefinition(
        description="Design implementation plans",
        tools=["read_file", "glob", "grep"],
        read_only=True,
        system_prompt=PLAN_PROMPT,
    ),
    "general-purpose": AgentDefinition(
        description="Full-capability sub-agent",
        tools=None,
        read_only=False,
        system_prompt=GENERAL_PURPOSE_PROMPT,
    ),
}
