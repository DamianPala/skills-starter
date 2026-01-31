# Creating Skills with Claude Code

A practical guide to working with Claude Code to build effective skills.

## How Skills Work

### What Are Skills?

Agent Skills are an **open standard** — folders of instructions, scripts, and resources that agents load on demand. Originally from Anthropic, now adopted by other companies.

**Use cases:** domain expertise, new capabilities (presentations, MCP servers), repeatable workflows, interoperability across tools.

### Progressive Disclosure

Skills load in three levels — only what's needed enters context:

| Level | What | When | Typical size |
|-------|------|------|--------------|
| **1. Metadata** | `name` + `description` | Always at startup | ~100 tokens |
| **2. Body** | SKILL.md instructions | When triggered | ~1,500-5,000 tokens (keep under ~500 lines) |
| **3. Resources** | scripts/, references/, assets/ | On demand | Unbounded; only what you read/run enters context |

Context window is shared real estate (200k–1M tokens depending on provider). Well-designed skills stay invisible until needed.

### Skill Structure

```
my-skill/
├── SKILL.md              # Required — frontmatter + instructions
├── scripts/              # Code that runs (output only enters context)
├── references/           # Docs loaded when needed
└── assets/               # Files for output (never loaded)
```

| Directory | Use for | Example |
|-----------|---------|---------|
| `scripts/` | Deterministic ops — validation, calculations | `validate.py` |
| `references/` | Domain knowledge on demand | `schema.md` |
| `assets/` | Templates, images | `template.docx` |

Scripts execute without loading code — only output consumes tokens. This makes skill capacity effectively unbounded.

### Frontmatter Fields

Frontmatter is YAML and is always read. Only two fields are required by the open standard.

**Required:**

| Field | Constraint |
|-------|------------|
| `name` | Max 64 chars; lowercase letters, numbers, hyphens only; must match directory name |
| `description` | Max 1024 chars — **primary trigger mechanism** |

**Optional:** `license`, `compatibility`, `metadata`, `allowed-tools`

The description decides whether the skill triggers — keep it specific about when to use it and when not to use it.

### Freedom Calibration

Match instruction specificity to task fragility. Think of Claude exploring a path: a narrow bridge with cliffs needs specific guardrails, an open field allows many routes.

**High freedom** (text guidelines)
- Multiple valid approaches exist
- Decisions depend on context
- Heuristics guide the approach
- Example: "Choose appropriate error handling based on the situation"

**Medium freedom** (pseudocode/structure)
- Preferred pattern exists but variation is acceptable
- Configuration affects behavior
- Example: "Follow this template, adjust field names as needed"

**Low freedom** (specific scripts)
- Operations are fragile or error-prone
- Consistency is critical
- Specific sequence must be followed
- Example: "Run `scripts/validate.py` — do not modify validation logic"

**Rule of thumb:** If getting it wrong breaks something or produces inconsistent results, lower the freedom. Use scripts for calculations, validations, and anything that must be deterministic.

### Writing Effective Instructions

Find the **Goldilocks zone** — not too rigid (fragile if-else rules), not too vague (ineffective guidance). Clear, direct language works best.

**Practical rules:**

1. **Explicit context** — state scope, parameters, constraints. Don't assume the model infers correctly.
2. **Examples > explanations** — show input/output pairs with exact format you want.
3. **Personas when useful** — "You are an HR assistant drafting responses..."
4. **Break into steps** — guide reasoning explicitly for complex tasks.
5. **Structure with headers** — markdown sections or XML tags help organize.
6. **Tool guidance is explicit** — if a human can't pick the right tool deterministically, the agent won't either.
7. **Calm intensity** — Claude 4.5 responds well; skip "CRITICAL: YOU MUST", use "Use this when..."

**Behavioral nudges via XML tags:**
- `<default_to_action>Implement rather than suggest.</default_to_action>`
- `<confirm_first>Confirm requirements before implementing.</confirm_first>`

### Anti-Patterns to Avoid

| Anti-Pattern | Problem | Fix |
|--------------|---------|-----|
| Vague descriptions | Claude can't determine when to invoke | Include specific verbs, file types, boundaries |
| Overloaded instructions | Multi-step phrasing confuses agents | Break into discrete, focused steps |
| Pseudo-code in instructions | LLMs unreliable for calculations | Put calculations in actual scripts |
| Overlapping skill responsibilities | Circular delegation, conflicting outputs | Create clear role taxonomy |
| Missing confidence thresholds | Hallucination, acting on insufficient info | Add "Only proceed if 90%+ confident" |
| Deeply nested references | Claude loses track, navigation confusion | Keep references one level deep |
| Context bloat | Lost-in-middle effect, relevant info buried | Use hierarchical summaries |
| Untested skills | "Clear to you ≠ clear to agents" | Test with subagents before deployment |

### Real-World Example: TDD Skill

From [github.com/obra/superpowers](https://github.com/obra/superpowers) — a battle-tested community skill:

```yaml
---
name: test-driven-development
description: Enforces RED-GREEN-REFACTOR TDD cycle. Use when implementing features or fixing bugs.
---

# Test-Driven Development

Thinking "skip TDD just this once"? Stop. That's rationalization.

Write code before the test? Delete it. Start over.

## RED Phase
- Write failing test FIRST
- Test must fail for right reason
- Never write implementation before test

## GREEN Phase
- Write MINIMUM code to pass
- No extra features
- No "while I'm here" additions

## REFACTOR Phase
- Tests still pass? Continue
- Extract patterns only when needed
```

**Why this works:**
- **Anti-rationalization language** — addresses specific excuses agents make
- **Clear consequences** — "Delete it. Start over." — unambiguous failure handling
- **Focused on one thing** — TDD cycle only, not general coding
- **Checkable steps** — each phase has verifiable completion criteria

## Before You Start

Load the skill-creator:

```
$skill-creator
```

This gives Claude Code context about skill structure and best practices. Without it, you're relying on its general knowledge.

## The Workflow

### 1. Discovery & Research

Before building, understand the need and check what already exists.

Use this prompt:

~~~
I want to create a skill. Before we start, help me clarify what I need and check if something already exists.

## Phase 1: Interview me

Ask me these questions one by one (wait for my answers):

**Understanding the problem:**
1. What specific problem am I trying to solve? (the task, not "I want a skill for X")
2. How often will I use this? 
  a. daily
  b. weekly
  c. occasionally
3. What tools/languages/frameworks does this involve?

**Defining triggers:**
4. Give me 3-5 example prompts that should trigger this skill
   OR should it only activate when explicitly called (e.g., `$skill-name`)?

**Defining boundaries:**
5. What should this skill explicitly NOT do?
6. Are there similar tasks that should use a DIFFERENT skill?

## Phase 2: Research existing skills

After I answer, search thoroughly:

**Official sources:**
- github.com/anthropics/skills
- github.com/openai/skills

**Community catalogs:**
- github.com/obra/superpowers
- github.com/travisvn/awesome-claude-skills
- skills.sh
- agentskills.io/catalog

**General search:**
- Search Google/web for: "[my problem] claude skill" or "[my problem] agent skill"
- Search GitHub for: "SKILL.md [keywords]"

## Phase 3: Recommendation

Based on research, recommend ONE of:

**A) Use existing skill**
- Link to it
- Show how to install
- Explain how it solves my problem

**B) Fork and modify**
- Which skill to fork
- What specific changes needed
- Estimated effort

**C) Create new skill**
- Why nothing existing fits
- Proposed structure (simple / with scripts / with references)
- Proceed to plan mode with gathered requirements

If A or B — we're done. If C — continue to planning.
~~~

**Why this approach:**
- Focuses on the **problem**, not the solution — avoids "XY problem"
- Research happens BEFORE you invest time writing
- If existing skill fits → done in 2 minutes instead of 30

### 2. Use plan mode

Tell Claude Code to plan before implementing:

```
Plan how to create this skill. Don't write code yet.
```

Or trigger plan mode explicitly — Claude Code will:
- Explore existing skills for patterns
- Propose structure (SKILL.md alone or with scripts/references/assets)
- Draft the description for your review
- Outline main instruction sections

Review and adjust the plan before approving. **The description is 80% of success** — if it's wrong, the skill won't trigger correctly.

**What to check in the plan:**
- Does the proposed description include triggers AND boundaries?
- Is the structure appropriate (simple skill vs. skill with scripts)?
- Are the instruction sections focused on "when X → do Y"?

### 3. Test triggering immediately

After the skill is written:

```
Now test triggering. Give me 3 prompts that SHOULD trigger this skill
and 3 that SHOULD NOT. For each, tell me whether it would trigger and why.
```

If triggering is wrong — fix the description, not the instructions.

### 4. Iterate on real tasks

```
Use this skill on this task: [paste real task]
After executing, tell me what would need to change in the skill.
```

**Why:** "Clear to you ≠ clear to the agent". Skills must work on real cases, not just look good.

## Checklists to Use with Claude Code

### When planning the skill

Copy into conversation:

```
Before we start writing, answer these questions:

- [ ] What specific tasks should this handle? (3-5 examples)
- [ ] What prompts should trigger the skill?
- [ ] What prompts should NOT trigger?
- [ ] Do we need scripts/ (deterministic operations)?
- [ ] Do we need references/ (documentation to load)?
- [ ] Do we need assets/ (templates, files)?
```

### When writing the description

```
Check that the description contains:

- [ ] Action verbs (what the skill DOES)
- [ ] Trigger contexts (when user says X)
- [ ] Boundaries (what the skill does NOT do)
- [ ] Max 1024 characters
```

### When writing instructions

```
Check the instructions for:

- [ ] Under 500 lines
- [ ] Concrete examples instead of abstract descriptions
- [ ] Calculations/validations in scripts/, not prose
- [ ] References max 1 level deep
- [ ] Clear "when X → do Y" instead of "consider doing Y"
```

### After the skill is written

```
Final validation:

- [ ] name is lowercase, hyphenated, matches folder name
- [ ] Triggering tested (positive and negative cases)
- [ ] Scripts work (run them manually)
- [ ] Skill tested on a real task
```

## Best Practices

### General tips

1. Use fresh session for research, plan, build - save context
1. For social media research use Grok
1. Add antihalucination rules for research skills
1. Use trusted-sources.md file as a reference for research
1. After you finish your skill, do a refinement in fresh session with $skill-creator
1. Use subagents for tasks requiring extensive context, data analysis, etc.
1. For deep research skills sometimes is better to use web app deep research than do deep research by CLI tool.
1. Use predefined prompt templates, if a prompt is dedicated to specific model, improve this prompt with this model.
1. In case of complex skills, it is a good practise to have a draft or requirement file for your skill. You can build it along with your skill, for instance in `_dev` directory.

### Description is everything for proper triggering

90% of skill problems are bad descriptions. Claude decides whether to use a skill based on ~100 tokens of metadata — if the description is bland, the skill won't trigger.

**Weak:**
```yaml
description: Helps with documentation.
```

**Strong:**
```yaml
description: Writes technical API documentation in OpenAPI format.
  Use when user asks for docs, endpoint documentation, or API spec.
  NOT for user documentation or README files.
```

### Examples > explanations

In instructions:

**Weak:**
```markdown
Commit messages should be concise and descriptive, using imperative mood.
```

**Strong:**
```markdown
Commit message format:

Input: Added JWT authentication
Output: feat(auth): add JWT authentication

Input: Fixed date bug
Output: fix(reports): correct date timezone handling
```

### Calibrate freedom

| Task type | Approach |
|-----------|----------|
| Many valid solutions | Text guidelines |
| Preferred pattern exists | Pseudocode / structure |
| Must be exact | Script |

**Rule:** If a mistake breaks something → use a script.

### Test with a subagent

```
Run a subagent and have it execute [task] using this skill.
Watch where it gets confused and what needs to change.
```

Subagents don't have conversation context — if the skill works for a subagent, it works for everyone.

## Common Problems

| Symptom | Cause | What to tell Claude |
|---------|-------|---------------------|
| Skill doesn't trigger | Bland description | "Rewrite description with specific triggers and boundaries" |
| Triggers too often | No boundaries | "Add to description when NOT to use it" |
| Inconsistent results | Too general instructions | "Add concrete input→output examples" |
| Slow response | Too much in SKILL.md | "Move details to references/" |

## After Creating the Skill

```bash
# Validate structure
~/.agents/skills/skill-creator/scripts/quick_validate.py ~/.agents/skills/NAME

# Rebuild router
python build-router.py

# Check it's visible
python build-router.py --list
```
