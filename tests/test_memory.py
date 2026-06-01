"""Test the memory store."""
from banana.memory.store import MemoryStore


class TestMemoryStore:
    def test_empty(self, temp_home):
        store = MemoryStore(temp_home / ".bananacoder")
        assert store.get_context() == ""

    def test_add_and_read(self, temp_home):
        store = MemoryStore(temp_home / ".bananacoder")
        store.add("Preferences", "User likes pytest")
        assert "pytest" in store.read_all()

    def test_get_context(self, temp_home):
        store = MemoryStore(temp_home / ".bananacoder")
        store.add("Project", "Uses Python 3.12")
        store.add("Preferences", "Reply in Chinese")
        ctx = store.get_context()
        assert "Python 3.12" in ctx
        assert "Reply in Chinese" in ctx
        assert "## Long-term Memory" in ctx

    def test_search(self, temp_home):
        store = MemoryStore(temp_home / ".bananacoder")
        store.add("Project", "Uses PostgreSQL")
        store.add("Project", "Uses Redis for caching")
        results = store.search("Redis")
        assert len(results) == 1
        assert "Redis" in results[0]

    def test_search_no_match(self, temp_home):
        store = MemoryStore(temp_home / ".bananacoder")
        store.add("Project", "Uses PostgreSQL")
        results = store.search("MongoDB")
        assert len(results) == 0

    def test_remove(self, temp_home):
        store = MemoryStore(temp_home / ".bananacoder")
        store.add("Project", "Uses PostgreSQL")
        store.add("Project", "Uses Redis")
        removed = store.remove(None, "Redis")
        assert removed == 1
        assert "Redis" not in store.read_all()
        assert "PostgreSQL" in store.read_all()

    def test_get_sections(self, temp_home):
        store = MemoryStore(temp_home / ".bananacoder")
        store.add("Preferences", "Dark mode")
        store.add("Project", "Python 3.12")
        sections = store.get_sections()
        assert "Preferences" in sections
        assert "Project" in sections
        assert sections["Preferences"] == ["Dark mode"]
        assert sections["Project"] == ["Python 3.12"]

    def test_persistence(self, temp_home):
        store1 = MemoryStore(temp_home / ".bananacoder")
        store1.add("Project", "Uses pytest")
        # Re-read from disk
        store2 = MemoryStore(temp_home / ".bananacoder")
        assert "pytest" in store2.read_all()
