"""Test the hook system."""
import pytest
from banana.hook import AgentHook, HookContext, HookManager


class BlockBashHook(AgentHook):
    """Blocks bash commands containing 'rm'."""
    async def before_tool_execute(self, ctx: HookContext) -> bool:
        if ctx.tool_name == "bash" and "rm" in str(ctx.tool_args.get("command", "")):
            ctx.tool_result = "BLOCKED by hook"
            return False
        return True


class LoggingHook(AgentHook):
    """Records all tool calls."""
    def __init__(self):
        self.calls = []

    async def before_tool_execute(self, ctx: HookContext) -> bool:
        self.calls.append(("before", ctx.tool_name, ctx.tool_args))
        return True

    async def after_tool_execute(self, ctx: HookContext):
        self.calls.append(("after", ctx.tool_name))


class TestHookManager:
    def test_registration(self):
        mgr = HookManager()
        hook = LoggingHook()
        mgr.register(hook)
        assert hook in mgr._hooks
        mgr.unregister(hook)
        assert hook not in mgr._hooks

    @pytest.mark.asyncio
    async def test_block_bash_rm(self):
        mgr = HookManager([BlockBashHook()])
        ctx = HookContext(tool_name="bash", tool_args={"command": "rm -rf /tmp/test"})
        result = await mgr.before_tool_execute(ctx)
        assert result is False

    @pytest.mark.asyncio
    async def test_allow_safe_bash(self):
        mgr = HookManager([BlockBashHook()])
        ctx = HookContext(tool_name="bash", tool_args={"command": "ls -la"})
        result = await mgr.before_tool_execute(ctx)
        assert result is True

    @pytest.mark.asyncio
    async def test_logging_hook(self):
        hook = LoggingHook()
        mgr = HookManager([hook])
        ctx = HookContext(tool_name="glob", tool_args={"pattern": "*.py"})
        await mgr.before_tool_execute(ctx)
        ctx.tool_result = "file1.py\nfile2.py"
        await mgr.after_tool_execute(ctx)
        assert len(hook.calls) == 2
        assert hook.calls[0] == ("before", "glob", {"pattern": "*.py"})
        assert hook.calls[1] == ("after", "glob")

    @pytest.mark.asyncio
    async def test_hook_error_isolation(self):
        """Hook that raises shouldn't break the manager."""
        class BrokenHook(AgentHook):
            async def before_tool_execute(self, ctx: HookContext) -> bool:
                raise RuntimeError("oops")

        mgr = HookManager([BrokenHook(), LoggingHook()])
        ctx = HookContext(tool_name="bash", tool_args={})
        result = await mgr.before_tool_execute(ctx)
        assert result is True  # BrokenHook's error is swallowed

    @pytest.mark.asyncio
    async def test_on_turn_start_end(self):
        hook = LoggingHook()
        mgr = HookManager([hook])
        ctx = HookContext()
        await mgr.on_turn_start(ctx)
        await mgr.on_turn_end(ctx)
