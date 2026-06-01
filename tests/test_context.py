from banana.agent.context import ContextManager, estimate_tokens


class TestEstimateTokens:
    def test_empty(self):
        assert estimate_tokens([]) == 0

    def test_simple(self):
        msgs = [{"role": "user", "content": "hello world" * 100}]
        assert estimate_tokens(msgs) > 0


class TestContextManager:
    def test_snip_tool_outputs(self):
        msgs = [
            {"role": "tool", "content": "short"},
            {"role": "tool", "content": "\n".join(f"line{i}" for i in range(8)) + "\n" + ("x" * 2000)},
        ]
        changed = ContextManager._snip_tool_outputs(msgs)
        assert changed is True
        assert "snipped" in msgs[1]["content"]

    def test_no_snip_short(self):
        msgs = [{"role": "tool", "content": "short"}]
        changed = ContextManager._snip_tool_outputs(msgs)
        assert changed is False
