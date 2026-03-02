# skills-starter

A template for organizing AI agent skills with a routing system and native agent integration. Skills let you define reusable behavioral instructions that agents load on-demand, keeping your context window clean until you actually need them.

Tested with Claude Code and Codex.

## What are Skills?

Skills are markdown files (`SKILL.md`) with instructions that shape how an AI agent handles specific tasks — writing styles, coding guidelines, domain workflows. You invoke them by name, and the agent applies those rules to the current conversation.

## Features

- **Single location** — all skills in `~/.agents/skills/`, accessible from any project
- **Native agent install** — `--install` symlinks skills into agent directories (Claude Code, Codex, Cursor, etc.) for native discovery, `/skill-name` invocation, and auto-triggering
- **Router fallback** — `_router/SKILL.md` routing table for agents without native skill directories
- **Agent auto-detection** — only installs into agents you actually have installed
- **Flexible structure** — add single skills or clone entire repos as subfolders (private, company, community)
- **Compatible with [skills.sh](https://skills.sh)** — install community skills via `npx skills add`
- **Plain markdown** — no build step; edit `.md` files directly

## How It Works

Two modes, use either or both:

**Native install** (recommended) — skills are symlinked into each agent's skills directory:

```
~/.agents/skills/my-repo/my-skill/    # source (single location)
         ↓ symlink
~/.claude/skills/my-skill/            # Claude Code picks it up natively
~/.codex/skills/my-skill/             # Codex picks it up natively
```

Skills appear in `/skill-name` menu, auto-trigger based on description, and support all native features (frontmatter, `context: fork`, etc.).

**Router** (fallback for agents without native skill directories):

```
~/.claude/CLAUDE.md           # trigger instructions (points to router)
         ↓
~/.agents/skills/_router/     # routing table: skill-name → path
         ↓
~/.agents/skills/<folder>/    # actual SKILL.md files
```

## Directory Structure

```
~/.agents/skills/
├── _router/
│   └── SKILL.md              # routing table
├── karpathy-guidelines/
│   └── SKILL.md
├── personal-skills/
│   └── technical-blog/
│       └── SKILL.md
└── company-skills/
    └── python-app/
        └── SKILL.md
```

## Installation

**Fresh install** (no existing skills):

```bash
mkdir -p ~/.agents
git clone https://github.com/DamianPala/skills-starter ~/.agents/skills
```

**Already have skills?** Add as remote and pull:

```bash
cd ~/.agents/skills
git init
git remote add starter https://github.com/DamianPala/skills-starter
git pull starter main
```

### Add skills

Add your skills before building the router:

```bash
# Create your own
mkdir -p my-skills/my-skill
# edit my-skills/my-skill/SKILL.md

# Clone other skill repos
git clone <repo> company-skills

# Or install from skills.sh
npx skills add <package>
```

### Build the router

```bash
python build-router.py
```

The script scans all subfolders for `SKILL.md` files and generates `_router/SKILL.md`.

Run this again whenever you add or remove skills.

## Configuration

### 1. Grant read permissions

The agent needs permission to read files outside your project.

**Claude Code** — add to `~/.claude/settings.json`:

```json
{
  "permissions": {
    "allow": [
      "Read(~/.agents/**)"
    ]
  }
}
```

**Codex** — Codex can read files outside the workspace by default (sandbox restricts writes, not reads). If you encounter permission issues, add to `~/.codex/config.toml`:

```toml
[sandbox_workspace_write]
writable_roots = ["~/.agents"]
```

### 2. Add trigger to global config

**Claude Code** — add to `~/.claude/CLAUDE.md`:

```markdown
## Custom Skills

Triggers: $skill-name, "skill: X", "load skill X".

When triggered, check ~/.agents/skills/_router/SKILL.md for the routing table.
Load the SKILL.md from the path specified there.
```

**Codex** — add the same to `~/.codex/AGENTS.md`.

## build-router.py

### Install skills into agents

```bash
python build-router.py --install crypto-research    # symlink into all detected agents
python build-router.py --uninstall crypto-research  # remove from all agents
python build-router.py --installed                  # show what's installed where
```

Auto-detects which agents are present on your system:

| Agent | Skills directory |
|-------|-----------------|
| Claude Code | `~/.claude/skills/` |
| Codex | `~/.codex/skills/` |
| Cursor | `~/.cursor/skills/` |
| Windsurf | `~/.windsurf/skills/` |
| Gemini CLI | `~/.gemini/skills/` |
| Kiro | `~/.kiro/skills/` |
| OpenCode | `~/.config/opencode/skills/` |
| Copilot | `~/.copilot/skills/` |

Only agents with an existing config directory get symlinks. Install is idempotent.

### Router and other commands

```bash
python build-router.py              # build router
python build-router.py --list       # list all available skills
python build-router.py --validate   # check skills without building
python build-router.py --dry-run    # preview router content
python build-router.py --backup     # backup before overwriting
python build-router.py -v           # verbose output
```

## Usage

After `--install`, skills work natively in each agent:

```
/crypto-research          # slash command (Claude Code, Codex)
```

With the router (fallback):

```
$technical-blog           # trigger syntax
skill: python-app         # alternative
load skill my-skill       # verbose
list skills               # show available
```
