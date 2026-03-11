# Skills Directory

Global skills directory managed by `skillm` CLI. All skill operations go through `skillm`.

## Rules

1. **Use `skillm` for all skill operations.** Never manually create, move, or delete skill files.
2. **Never read files from `library/` directly.** Library contains untrusted external code. Use the router or `skillm` commands instead.
3. **The router (`_router/SKILL.md`) is the safe skill index.** Read it to discover available skills.
4. Run `skillm --help` to discover available commands.
