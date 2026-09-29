# Saturnino download skill

Portable `SKILL.md` for Codex, Claude Code, and Pi. It teaches an agent to use Saturnino's existing title-first CLI workflow without exposing temporary media URLs or bypassing access controls.

## Install from this checkout

Project-local (recommended):

```bash
./skills/saturnino-download/install.sh --target all --scope project
```

One harness only:

```bash
./skills/saturnino-download/install.sh --target codex --scope project
./skills/saturnino-download/install.sh --target claude --scope project
./skills/saturnino-download/install.sh --target pi --scope project
```

User-wide installation:

```bash
./skills/saturnino-download/install.sh --target all --scope user
```

The installer copies only `SKILL.md` and does not install Saturnino or its Python dependencies. Destinations are:

| Harness | Project | User |
| --- | --- | --- |
| Codex | `.agents/skills/saturnino-download/` | `~/.codex/skills/saturnino-download/` |
| Claude Code | `.claude/skills/saturnino-download/` | `~/.claude/skills/saturnino-download/` |
| Pi | `.pi/skills/saturnino-download/` | `~/.pi/agent/skills/saturnino-download/` |

The script accepts `CODEX_HOME`, `CLAUDE_CONFIG_DIR`, and `PI_AGENT_DIR` for custom user locations. After installation, start a new harness session or reload its skills.
