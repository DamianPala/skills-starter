#!/usr/bin/env python
"""Build the skill router and install skills into AI coding agents."""
# PYTHON_ARGCOMPLETE_OK

import argparse
import logging
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

try:
    import argcomplete
except ImportError:
    argcomplete = None

SKILLS_DIR = Path.home() / ".agents" / "skills"
ROUTER_DIR = SKILLS_DIR / "_router"
ROUTER_FILE = ROUTER_DIR / "SKILL.md"

IGNORED_DIRS = {
    "_router",
    "_dev",
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    ".hatch",
}

HELPER_DIRS = {"scripts", "references", "assets"}

# Agent skills directories (global/personal scope).
# Auto-detected: only agents with existing config dirs get symlinks.
AGENT_SKILLS_DIRS: dict[str, Path] = {
    "claude-code": Path.home() / ".claude" / "skills",
    "codex": Path.home() / ".codex" / "skills",
    "cursor": Path.home() / ".cursor" / "skills",
    "windsurf": Path.home() / ".windsurf" / "skills",
    "gemini-cli": Path.home() / ".gemini" / "skills",
    "kiro": Path.home() / ".kiro" / "skills",
    "opencode": Path.home() / ".config" / "opencode" / "skills",
    "copilot": Path.home() / ".copilot" / "skills",
}

log = logging.getLogger(__name__)


@dataclass
class Skill:
    """Represents a discovered skill."""

    name: str
    path: Path
    description: str | None = None
    helpers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def parse_frontmatter(content: str) -> dict[str, str]:
    """Extract YAML frontmatter from markdown content.

    Parses the frontmatter block between --- markers at the start of the file.
    Only handles simple key: value pairs (no nested structures).
    """
    match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return {}

    frontmatter = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            frontmatter[key.strip()] = value.strip()

    return frontmatter


def should_ignore(path: Path) -> bool:
    """Check if a directory should be ignored during scanning."""
    return path.name in IGNORED_DIRS or path.name.startswith(".")


def find_helper_dirs(skill_path: Path) -> list[str]:
    """Find helper directories (scripts/, references/, assets/) in a skill folder."""
    found = []
    for helper in HELPER_DIRS:
        if (skill_path / helper).is_dir():
            found.append(helper)
    return sorted(found)


def find_skill_in_dir(dir_path: Path) -> Skill | None:
    """Check if a directory contains a SKILL.md and return Skill if valid.

    A valid skill must have a SKILL.md file with a 'name' field in frontmatter.
    If name is missing, the directory name is used as fallback.
    """
    skill_file = dir_path / "SKILL.md"
    if not skill_file.is_file():
        return None

    content = skill_file.read_text(encoding="utf-8")
    frontmatter = parse_frontmatter(content)
    warnings = []

    name = frontmatter.get("name")
    if not name:
        name = dir_path.name
        warnings.append(f"Missing 'name' in frontmatter, using folder name: {name}")

    description = frontmatter.get("description")
    if not description:
        warnings.append("Missing 'description' in frontmatter")

    helpers = find_helper_dirs(dir_path)

    return Skill(
        name=name,
        path=dir_path,
        description=description,
        helpers=helpers,
        warnings=warnings,
    )


def scan_skills(skills_dir: Path) -> list[Skill]:
    """Scan skills directory and return all discovered skills.

    Handles three cases:
    1. Skills directly in skills_dir (e.g., ~/.agents/skills/my-skill/)
    2. Skill groups/repos with nested skills (e.g., ~/.agents/skills/company-skills/app/)
    3. Ignores special directories (_router, .git, etc.)
    """
    skills: list[Skill] = []

    if not skills_dir.is_dir():
        log.error(f"Skills directory does not exist: {skills_dir}")
        return skills

    for item in sorted(skills_dir.iterdir()):
        if not item.is_dir() or should_ignore(item):
            continue

        # Check if this directory itself is a skill
        skill = find_skill_in_dir(item)
        if skill:
            log.debug(f"Found skill: {skill.name} at {item}")
            skills.append(skill)
            continue

        # Otherwise, scan subdirectories (skill group/repo)
        log.debug(f"Scanning skill group: {item.name}")
        for subitem in sorted(item.iterdir()):
            if not subitem.is_dir() or should_ignore(subitem):
                continue

            skill = find_skill_in_dir(subitem)
            if skill:
                log.debug(f"Found skill: {skill.name} at {subitem}")
                skills.append(skill)

    return skills


def validate_skills(skills: list[Skill]) -> int:
    """Validate skills and log warnings. Returns count of warnings."""
    warning_count = 0
    for skill in skills:
        for warning in skill.warnings:
            log.warning(f"{skill.name}: {warning}")
            warning_count += 1
    return warning_count


def check_conflicts(skills: list[Skill]) -> list[Skill]:
    """Check for duplicate skill names and return deduplicated list.

    When conflicts occur, keeps the first occurrence and warns about duplicates.
    """
    seen: dict[str, Path] = {}
    unique: list[Skill] = []

    for skill in skills:
        if skill.name in seen:
            log.warning(
                f"Conflict: skill '{skill.name}' found at {skill.path} "
                f"but already registered from {seen[skill.name]} — skipping"
            )
            continue
        seen[skill.name] = skill.path
        unique.append(skill)

    return unique


def generate_router_content(skills: list[Skill]) -> str:
    """Generate the router SKILL.md content."""
    lines = [
        "---",
        "name: router",
        'description: "Skill routing table - maps skill names to paths."',
        "---",
        "",
        "# Skill Router",
        "",
    ]

    for skill in sorted(skills, key=lambda s: s.name):
        # Use ~ shorthand for home directory
        path_str = str(skill.path).replace(str(Path.home()), "~")
        lines.append(f"{skill.name}: {path_str}/")

    lines.append("")
    return "\n".join(lines)


def list_skills(skills: list[Skill]) -> None:
    """Print a formatted list of skills with descriptions."""
    if not skills:
        print("No skills found.")
        return

    # Calculate column width
    max_name = max(len(s.name) for s in skills)

    print(f"\n{'SKILL':<{max_name}}  DESCRIPTION")
    print(f"{'-' * max_name}  {'-' * 50}")

    for skill in sorted(skills, key=lambda s: s.name):
        desc = skill.description or "(no description)"
        # Truncate long descriptions
        if len(desc) > 60:
            desc = desc[:57] + "..."

        helpers_str = ""
        if skill.helpers:
            helpers_str = f" [{', '.join(skill.helpers)}]"

        print(f"{skill.name:<{max_name}}  {desc}{helpers_str}")

    print(f"\nTotal: {len(skills)} skill(s)")


def backup_router(router_file: Path) -> Path | None:
    """Create a timestamped backup of the existing router file."""
    if not router_file.is_file():
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = router_file.with_suffix(f".{timestamp}.bak")
    shutil.copy2(router_file, backup_path)
    log.info(f"Backed up existing router to {backup_path}")
    return backup_path


def detect_agents() -> dict[str, Path]:
    """Return agent skills dirs for agents that have a config directory on disk."""
    found: dict[str, Path] = {}
    for agent, skills_dir in AGENT_SKILLS_DIRS.items():
        # Check if the agent's config root exists (parent of skills/)
        config_root = skills_dir.parent
        if config_root.is_dir():
            found[agent] = skills_dir
    return found


def install_skill(skill: Skill, agents: dict[str, Path]) -> int:
    """Create symlinks for a skill in all detected agent skills directories."""
    installed = 0
    for agent, skills_dir in sorted(agents.items()):
        link = skills_dir / skill.name
        target = skill.path.resolve()

        if link.is_symlink():
            if link.resolve() == target:
                log.info(f"  {agent}: already installed")
                continue
            link.unlink()

        if link.exists():
            log.warning(f"  {agent}: {link} exists and is not a symlink, skipping")
            continue

        skills_dir.mkdir(parents=True, exist_ok=True)
        link.symlink_to(target)
        log.info(f"  {agent}: installed -> {target}")
        installed += 1

    return installed


def uninstall_skill(name: str, agents: dict[str, Path]) -> int:
    """Remove symlinks for a skill from all detected agent skills directories."""
    removed = 0
    for agent, skills_dir in sorted(agents.items()):
        link = skills_dir / name
        if link.is_symlink():
            link.unlink()
            log.info(f"  {agent}: removed")
            removed += 1
        elif link.exists():
            log.warning(f"  {agent}: {link} is not a symlink, skipping")
        else:
            log.debug(f"  {agent}: not installed")
    return removed


def list_installed(agents: dict[str, Path]) -> None:
    """List skills installed (symlinked) in each detected agent."""
    for agent, skills_dir in sorted(agents.items()):
        if not skills_dir.is_dir():
            continue

        links = sorted(
            p
            for p in skills_dir.iterdir()
            if p.is_symlink() and ((p / "SKILL.md").is_file() or not p.exists())
        )
        if not links:
            continue

        print(f"\n{agent} ({skills_dir}):")
        for link in links:
            target = link.resolve()
            status = "" if link.exists() else " [broken]"
            print(f"  {link.name} -> {target}{status}")

    print()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the skill router and install skills into AI coding agents.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Build router
  %(prog)s --list                   # List all available skills
  %(prog)s --install crypto-research  # Symlink skill into detected agents
  %(prog)s --uninstall crypto-research
  %(prog)s --installed              # Show what's installed where
  %(prog)s --dry-run                # Preview without writing
  %(prog)s --validate               # Check skills without building
  %(prog)s -v                       # Verbose output
        """,
    )
    parser.add_argument(
        "--skills-dir",
        type=Path,
        default=SKILLS_DIR,
        help=f"Skills directory to scan (default: {SKILLS_DIR})",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_skills",
        help="List all skills with descriptions (does not build router)",
    )
    parser.add_argument(
        "--install",
        metavar="SKILL",
        help="Install a skill into all detected agents (creates symlinks)",
    )
    parser.add_argument(
        "--uninstall",
        metavar="SKILL",
        help="Remove a skill from all detected agents",
    )
    parser.add_argument(
        "--installed",
        action="store_true",
        help="List skills installed in each detected agent",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate skills without building router",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the router content without writing to file",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Create a backup of the existing router before overwriting",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose output",
    )

    if argcomplete:
        argcomplete.autocomplete(parser)

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    skills_dir: Path = args.skills_dir.expanduser()
    router_dir = skills_dir / "_router"
    router_file = router_dir / "SKILL.md"

    # --installed: list what's symlinked, no scan needed
    if args.installed:
        agents = detect_agents()
        if not agents:
            log.warning("No agents detected")
            return 1
        list_installed(agents)
        return 0

    # --uninstall: remove symlinks, no scan needed
    if args.uninstall:
        agents = detect_agents()
        if not agents:
            log.warning("No agents detected")
            return 1
        log.info(f"Uninstalling: {args.uninstall}")
        removed = uninstall_skill(args.uninstall, agents)
        if removed:
            log.info(f"Removed from {removed} agent(s)")
        else:
            log.warning("Skill was not installed in any agent")
        return 0

    log.info(f"Scanning: {skills_dir}")

    skills = scan_skills(skills_dir)
    if not skills:
        log.warning("No skills found")
        return 1

    skills = check_conflicts(skills)
    warning_count = validate_skills(skills)

    log.info(f"Found {len(skills)} skill(s)")
    if warning_count:
        log.info(f"Validation: {warning_count} warning(s)")

    # --install: symlink a specific skill into detected agents
    if args.install:
        skill_map = {s.name: s for s in skills}
        if args.install not in skill_map:
            log.error(
                f"Skill '{args.install}' not found. Available: {', '.join(sorted(skill_map))}"
            )
            return 1

        agents = detect_agents()
        if not agents:
            log.warning("No agents detected")
            return 1

        skill = skill_map[args.install]
        log.info(f"Installing: {skill.name} ({skill.path})")
        log.info(f"Detected agents: {', '.join(sorted(agents))}")
        installed = install_skill(skill, agents)
        log.info(f"Installed in {installed} agent(s)")
        return 0

    # --list: just print skills and exit
    if args.list_skills:
        list_skills(skills)
        return 0

    # --validate: just validate and exit
    if args.validate:
        if warning_count:
            print(f"\nValidation completed with {warning_count} warning(s)")
            return 1
        print("\nAll skills valid")
        return 0

    content = generate_router_content(skills)

    if args.dry_run:
        print("\n--- Router content (dry run) ---")
        print(content)
        print("--- End ---")
        return 0

    if args.backup:
        backup_router(router_file)

    router_dir.mkdir(parents=True, exist_ok=True)
    router_file.write_text(content, encoding="utf-8")
    log.info(f"Router written to {router_file}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
