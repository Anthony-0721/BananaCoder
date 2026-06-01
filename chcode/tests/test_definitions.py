from chcode.agents.definitions import AgentDefinition, BUILT_IN_AGENTS


def test_agent_definition_defaults():
    ad = AgentDefinition(
        agent_type="test",
        when_to_use="testing",
        system_prompt="prompt",
    )
    assert ad.tools is None
    assert ad.disallowed_tools == []
    assert ad.model is None
    assert ad.read_only is False
    assert ad.source == "built-in"


def test_built_in_agents_keys():
    assert set(BUILT_IN_AGENTS.keys()) == {"general-purpose", "Explore", "Plan"}


def test_built_in_agents_read_only():
    assert BUILT_IN_AGENTS["general-purpose"].read_only is False
    assert BUILT_IN_AGENTS["Explore"].read_only is True
    assert BUILT_IN_AGENTS["Plan"].read_only is True


def test_explore_disallows_write():
    assert "write_file" in BUILT_IN_AGENTS["Explore"].disallowed_tools
    assert "edit" in BUILT_IN_AGENTS["Explore"].disallowed_tools
