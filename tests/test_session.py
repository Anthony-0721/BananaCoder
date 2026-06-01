import pytest
from banana.session.manager import Session, SessionManager


class TestSession:
    def test_create(self):
        s = Session(id="test", project="myproj")
        assert s.id == "test"
        assert s.messages == []


class TestSessionManager:
    @pytest.fixture
    def mgr(self, temp_home):
        return SessionManager(temp_home / ".bananacoder", temp_home / "projects" / "test")

    @pytest.mark.asyncio
    async def test_load_creates_empty(self, mgr):
        s = await mgr.load()
        assert s.id == "default"
        assert s.messages == []

    @pytest.mark.asyncio
    async def test_save_and_reload(self, mgr):
        s = Session(id="default", project="test")
        s.messages = [{"role": "user", "content": "hello"}]
        await mgr.save(s)
        loaded = await mgr.load()
        assert loaded.messages == s.messages

    @pytest.mark.asyncio
    async def test_switch(self, mgr):
        await mgr.new("other")
        s1 = await mgr.load()
        assert s1.id == "other"

    @pytest.mark.asyncio
    async def test_delete(self, mgr):
        s = Session(id="todelete", project="test", messages=[{"role": "user", "content": "x"}])
        await mgr.save(s)
        await mgr.delete("todelete")
        loaded = await mgr.load("todelete")
        assert loaded.messages == []

    @pytest.mark.asyncio
    async def test_list(self, mgr):
        await mgr.new("a")
        await mgr.new("b")
        sessions = await mgr.list_sessions()
        ids = [s["id"] for s in sessions]
        assert "a" in ids
        assert "b" in ids
