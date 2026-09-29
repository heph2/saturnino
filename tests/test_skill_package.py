import subprocess
from pathlib import Path

SKILL_DIR = Path(__file__).parents[1] / "skills" / "saturnino-download"


def test_skill_has_harness_neutral_frontmatter() -> None:
    text = (SKILL_DIR / "SKILL.md").read_text()
    assert text.startswith("---\n")
    assert "name: saturnino-download" in text
    assert "description:" in text


def test_installer_places_skill_in_each_project_harness(tmp_path: Path) -> None:
    installer = SKILL_DIR / "install.sh"
    subprocess.run(
        [str(installer), "--target", "all", "--scope", "project"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )

    for relative in (".agents/skills", ".claude/skills", ".pi/skills"):
        installed = tmp_path / relative / "saturnino-download" / "SKILL.md"
        assert installed.read_text() == (SKILL_DIR / "SKILL.md").read_text()
