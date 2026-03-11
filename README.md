# skills-starter

A template for organizing AI agent skills with a CLI manager, routing system, and native agent integration. Skills are reusable behavioral instructions that agents load on-demand, keeping your context window clean until you actually need them.

Tested with Claude Code and Codex.

## What are Skills?

Skills are markdown files (`SKILL.md`) with instructions that shape how an AI agent handles specific tasks: writing styles, coding guidelines, domain workflows. You invoke them by name, and the agent applies those rules to the current conversation.

## Features

- **`skillm` CLI** — list, install, uninstall, scan, and manage skills from the terminal
- **Library system** — add community repos, clone skill collections, deduplicate across sources
- **Native agent install** — symlinks skills into agent directories for native discovery and auto-triggering
- **Router fallback** — `_router/SKILL.md` routing table for agents without native skill directories
- **Agent auto-detection** — only installs into agents you actually have installed
- **Security scanning** — scan skills for prompt injection, data exfiltration, and other risks before installing
- **Compatible with [skills.sh](https://skills.sh)** — add community skills via `skillm add --npx <package>`
- **Plain markdown** — no build step; edit `.md` files directly

## How It Works

Two modes, use either or both:

**Native install** (recommended) — skills are symlinked into each agent's skills directory:

```
~/.agents/skills/my-repo/my-skill/    # source (single location)
         symlink
~/.claude/skills/my-skill/            # Claude Code picks it up natively
~/.codex/skills/my-skill/             # Codex picks it up natively
```

Skills appear in `/skill-name` menu, auto-trigger based on description, and support all native features (frontmatter, `context: fork`, etc.).

**Router** (lazy-loading) — skills are loaded on-demand via trigger syntax, so they don't consume context until invoked:

```
user: "$my-skill" or "skill: my-skill"
         |
~/.agents/skills/_router/     # routing table: skill-name -> path
         |
~/.agents/skills/<folder>/    # actual SKILL.md loaded into context
```

## Directory Structure

```
~/.agents/skills/
├── skillm.py                 # CLI manager
├── _router/
│   └── SKILL.md              # routing table (auto-generated)
├── library/                  # cloned skill repos (via skillm add)
│   ├── anthropics-skills/
│   └── vercel-labs-agent-skills/
├── my-skills/                # your own skills
│   └── technical-blog/
│       └── SKILL.md
└── company-skills/           # team/company skills
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

```bash
# Create your own
mkdir -p my-skills/my-skill
# edit my-skills/my-skill/SKILL.md

# Add a community repo to the library
skillm add owner/repo
skillm add https://github.com/someone/skills.git

# Or add from skills.sh
skillm add --npx <package>
```

### Install skills into agents

```bash
skillm install my-skill            # install into all detected agents (project scope)
skillm install -g my-skill         # install globally
skillm install --from repo my-skill  # pick specific repo when name exists in multiple
skillm uninstall my-skill          # remove from agents
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

## skillm CLI

```bash
# Discovery
skillm list                    # list all available skills
skillm list --installed        # show installed skills with token counts
skillm list react              # filter by name or description
skillm info my-skill           # show skill details
skillm info my-skill --from repo  # show specific repo version

# Library
skillm add owner/repo          # clone skill repo into library
skillm add --npx package       # add from skills.sh
skillm remove repo-name        # remove from library
skillm update                  # git pull all library repos

# Security
skillm scan my-skill           # scan for security issues
skillm scan --all              # scan everything

# Infrastructure
skillm router                  # rebuild the routing table
skillm doctor                  # diagnose broken symlinks, missing frontmatter, etc.
```

## Usage

After install, skills work natively in each agent:

```
/my-skill                 # slash command (Claude Code, Codex)
```

With the router (fallback):

```
$technical-blog           # trigger syntax
skill: python-app         # alternative
load skill my-skill       # verbose
list skills               # show available
```

## Creating Skills

See [creating-skills.md](creating-skills.md) for a guide on writing effective skills.
