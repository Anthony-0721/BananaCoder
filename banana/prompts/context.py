"""Prompts used during context compression."""

SUMMARY_SYSTEM_PROMPT = (
    "Extract key information from this conversation. "
    "Only output items matching these categories, skip everything else:\n"
    "- Decisions: choices made, conclusions reached, approaches selected\n"
    "- Files: files created, modified, or discussed (with purpose)\n"
    "- Errors: bugs encountered, root causes, fixes applied\n"
    "- State: current task progress, pending items, what's left to do\n"
    "- Preferences: user's stated preferences about code style, tools, workflows\n\n"
    "Priority: user corrections and preferences > errors > decisions > files > state.\n"
    "The most valuable information prevents the user from having to repeat themselves.\n\n"
    "Output as concise bullet points. No preamble, no commentary.\n"
    "If nothing noteworthy happened, output: (nothing)"
)

CONTEXT_COMPRESSED_PREFIX = (
    "[Context compressed — key information preserved below]"
)
HARD_RESET_PREFIX = (
    "[Hard reset — conversation history summarized below]"
)

CONTEXT_ACK = (
    "Got it. I have the preserved context (decisions, files, errors, progress)."
)
HARD_RESET_ACK = (
    "Context restored. Continuing with the preserved information."
)
