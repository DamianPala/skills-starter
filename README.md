# skills-starter

A template for organizing AI agent skills with a lightweight routing system. Skills let you define reusable behavioral instructions that agents load on-demand, keeping your context window clean until you actually need them.

Tested with Claude Code and Codex.

## What are Skills?

Skills are markdown files (`SKILL.md`) with instructions that shape how an AI agent handles specific tasks — writing styles, coding guidelines, domain workflows. You invoke them by name, and the agent applies those rules to the current conversation.

## Features

- **Single location** — all skills in `~/.agents/skills/`, accessible from any project
- **Agent-agnostic** — works with Claude Code, Codex, and other markdown-aware agents
- **Lazy loading** — skills enter context only when invoked, keeping overhead minimal
- **Flexible structure** — add single skills or clone entire repos as subfolders (private, company, community)
- **Compatible with [skills.sh](https://skills.sh)** — install community skills via `npx skills add`
- **Plain markdown** — no build step; edit `.md` files directly

## How It Works

```
~/.claude/CLAUDE.md           # trigger instructions (points to router)
         ↓
~/.agents/skills/_router/     # routing table: skill-name → path
         ↓
~/.agents/skills/<folder>/    # actual SKILL.md files
```

When you say `$my-skill` or `skill: my-skill`, the agent:
1. Reads the router to find the skill path
2. Loads that `SKILL.md` into context
3. Applies those instructions to your task

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

Clone this repo directly to `~/.agents/skills/`:

```bash
git clone https://github.com/DamianPala/skills-starter ~/.agents/skills
cd ~/.agents/skills
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

```bash
python build-router.py              # build router
python build-router.py --list       # list skills with descriptions
python build-router.py --validate   # check skills without building
python build-router.py --dry-run    # preview router content
python build-router.py --backup     # backup before overwriting
python build-router.py -v           # verbose output
```

## Usage

```
$technical-blog           # trigger syntax
skill: python-app         # alternative
load skill my-skill       # verbose
list skills               # show available
```
