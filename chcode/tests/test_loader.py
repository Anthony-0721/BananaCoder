import os
from pathlib import Path

from chcode.agents.loader import _parse_agent_md, load_agents


def _write_agent_md(directory: Path, filename: str, frontmatter: str, body: str):
    path = directory / filename
    path.write_text(f"---\n{frontmatter}\n---\n{body}", encoding="utf-8")
    return path


class TestParseAgentMd:
    def test_valid_loader(self, tmp_path: Path):
        path = _write_agent_md(
            tmp_path,
            "test.md",
            "name: my-agent\ndescription: A test agent",
            "You are a test agent.",
        )
        result = _parse_agent_md(path)
        assert result is not None
        assert result.agent_type == "my-agent"
        assert result.source == "custom"
        assert result.read_only is False

    def test_with_tools(self, tmp_path: Path):
        path = _write_agent_md(
            tmp_path,
            "tools.md",
            "name: tool-agent\ndescription: desc\ntools: bash,read_file",
            "prompt",
        )
        result = _parse_agent_md(path)
        assert result.tools == ["bash", "read_file"]

    def test_with_disallowed(self, tmp_path: Path):
        path = _write_agent_md(
            tmp_path,
            "dis.md",
            "name: dis-agent\ndescription: desc\ndisallowed_tools: write_file,edit",
            "prompt",
        )
        result = _parse_agent_md(path)
        assert result.disallowed_tools == ["write_file", "edit"]

    def test_read_only(self, tmp_path: Path):
        path = _write_agent_md(
            tmp_path,
            "ro.md",
            "name: ro-agent\ndescription: desc\nread_only: true",
            "prompt",
        )
        result = _parse_agent_md(path)
        assert result.read_only is True

    def test_no_frontmatter(self, tmp_path: Path):
        path = tmp_path / "bad.md"
        path.write_text("Just content, no frontmatter", encoding="utf-8")
        assert _parse_agent_md(path) is None

    def test_empty_name(self, tmp_path: Path):
        path = _write_agent_md(
            tmp_path, "bad.md", "description: desc\nname: ''", "prompt"
        )
        assert _parse_agent_md(path) is None

    def test_empty_body(self, tmp_path: Path):
        path = _write_agent_md(
            tmp_path, "empty.md", "name: agent\ndescription: desc", "  "
        )
        assert _parse_agent_md(path) is None

    def test_nonexistent_file(self, tmp_path: Path):
        assert _parse_agent_md(tmp_path / "nofile.md") is None


class TestLoadAgents:
    def test_returns_builtins(self):
        import chcode.agents.loader as loader_mod

        loader_mod._agents_cache = None
        agents = load_agents()
        assert "general-purpose" in agents
        assert "Explore" in agents
        assert "Plan" in agents

    def test_caches_result(self):
        import chcode.agents.loader as loader_mod

        loader_mod._agents_cache = None
        a1 = load_agents()
        a2 = load_agents()
        assert loader_mod._agents_cache is not None

    def test_extra_paths_not_cached(self, tmp_path: Path):
        import chcode.agents.loader as loader_mod

        loader_mod._agents_cache = None
        agents = load_agents(extra_paths=[tmp_path])
        assert loader_mod._agents_cache is None

    def test_loads_custom_agent(self, tmp_path: Path):
        import chcode.agents.loader as loader_mod

        loader_mod._agents_cache = None
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        _write_agent_md(
            agents_dir,
            "custom.md",
            "name: custom-agent\ndescription: A custom agent",
            "You are custom.",
        )
        agents = load_agents(extra_paths=[agents_dir])
        assert "custom-agent" in agents

    def test_custom_does_not_override_builtin(self, tmp_path: Path):
        import chcode.agents.loader as loader_mod

        loader_mod._agents_cache = None
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        _write_agent_md(
            agents_dir,
            "override.md",
            "name: Explore\ndescription: Override attempt",
            "Override prompt",
        )
        agents = load_agents(extra_paths=[agents_dir])
        assert agents["Explore"].source == "built-in"
