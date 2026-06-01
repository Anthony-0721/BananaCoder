import pytest
from banana.skills.loader import SkillsLoader


@pytest.fixture
def skill_dirs(temp_home):
    ws = temp_home / "workspace"
    ws.mkdir()
    skill_dir = ws / ".banana" / "skills" / "my-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("""---
name: my-skill
description: Does X when user needs it
always: true
---
# My Skill
Do the thing.
""")
    return ws


class TestSkillsLoader:
    def test_list_skills(self, skill_dirs):
        loader = SkillsLoader(skill_dirs)
        skills = loader.list_skills(filter_unavailable=False)
        assert len(skills) == 1
        assert skills[0]["name"] == "my-skill"

    def test_load_skill(self, skill_dirs):
        loader = SkillsLoader(skill_dirs)
        content = loader.load_skill("my-skill")
        assert "# My Skill" in content
        assert "---" not in content

    def test_get_always_skills(self, skill_dirs):
        loader = SkillsLoader(skill_dirs)
        always = loader.get_always_skills()
        assert "my-skill" in always

    def test_build_summary(self, skill_dirs):
        loader = SkillsLoader(skill_dirs)
        summary = loader.build_skills_summary()
        assert "my-skill" in summary
        assert "Does X" in summary

    def test_load_nonexistent(self, skill_dirs):
        loader = SkillsLoader(skill_dirs)
        assert loader.load_skill("nope") is None
