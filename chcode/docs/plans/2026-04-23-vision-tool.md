# Vision Understanding Tool Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a vision understanding tool that integrates ModelScope vision models, allowing users to paste image paths in chat and have the AI analyze them via tool calling.

**Architecture:** Add a new `analyze_image` tool to the existing tools system. Create a vision model config file at `~/.chat/vision_model.json`. The tool sends the image (base64) + user prompt to the ModelScope OpenAI-compatible vision API with fallback support.

**Tech Stack:** httpx (async HTTP), base64 (image encoding), LangChain @tool, OpenAI-compatible chat completions API

---

### Task 1: Create Vision Model Config Module

**Files:**
- Create: `chcode/vision_config.py`

**Step 1:** Create `chcode/vision_config.py` with:
- Vision model presets (default: Kimi-K2.5, backups: Qwen3-VL series, Intern-S1)
- Load/save vision config from `~/.chat/vision_model.json`
- Auto-detect ModelScope token from env var or existing model config
- Default vision config generation

### Task 2: Add `analyze_image` Tool

**Files:**
- Modify: `chcode/utils/tools.py` — add `analyze_image` tool + register in `ALL_TOOLS`

**Step 1:** Add `analyze_image` async tool that:
- Accepts `image_path` and `prompt` params
- Validates the image file exists and is a supported format (png/jpg/jpeg/gif/bmp/webp)
- Reads the image file, base64-encodes it
- Calls the ModelScope vision API (OpenAI-compatible chat completions with image content)
- Falls back through backup vision models on failure
- Returns the model's analysis text

### Task 3: Update System Prompt

**Files:**
- Modify: `chcode/agent_setup.py` — update `load_skills` middleware to mention `analyze_image`

**Step 1:** Add `analyze_image` to the system prompt tool list so the LLM knows to use it when users provide image paths.

### Task 4: Update `/tools` Command Display

**Files:**
- Modify: `chcode/chat.py` — no changes needed (it reads from `ALL_TOOLS` dynamically)

### Task 5: Add Vision Config Slash Command

**Files:**
- Modify: `chcode/chat.py` — add `/vision` command to configure vision models
- Modify: `chcode/prompts.py` — add vision model configuration prompt

**Step 1:** Add `/vision` slash command that lets users:
- View current vision model config
- Reconfigure vision models (pick default, set API key)
- Test vision model connection

---

## Verification

1. Run `chcode` and type `/tools` — `analyze_image` should appear in the list
2. Type `/vision` — should show current vision config
3. In chat, paste an image path like `./test.png` with a question — the LLM should call `analyze_image`
