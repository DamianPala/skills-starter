#!/usr/bin/env python
"""Skill manager for AI coding agents.

Manages per-project and global skill installation, library, and router generation.

Discovery:    list, info
Install:      install [-g], uninstall [-g], status
Library:      add, remove, update
Infra:        router, doctor
"""
# PYTHON_ARGCOMPLETE_OK

import argparse
import logging
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

try:
    import argcomplete
except ImportError:
    argcomplete = None

SKILLS_DIR: Path = Path.home() / ".agents" / "skills"
LIBRARY_DIR: Path = SKILLS_DIR / "library"
ROUTER_DIR: Path = SKILLS_DIR / "_router"
ROUTER_FILE: Path = ROUTER_DIR / "SKILL.md"

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

# Relative paths from a base dir (home for global, project root for local).
AGENT_CONFIGS: dict[str, Path] = {
    "claude-code": Path(".claude") / "skills",
    "codex": Path(".codex") / "skills",
    "cursor": Path(".cursor") / "skills",
    "windsurf": Path(".windsurf") / "skills",
    "gemini-cli": Path(".gemini") / "skills",
    "kiro": Path(".kiro") / "skills",
    "opencode": Path(".config") / "opencode" / "skills",
    "copilot": Path(".copilot") / "skills",
}

log = logging.getLogger(__name__)


# --- Data ---


@dataclass
class Skill:
    name: str
    path: Path
    description: str | None = None
    source: str = "local"
    helpers: list[str] = field(default_factory=list)


# --- Core ---


def parse_frontmatter(content: str) -> dict[str, str]:
    match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return {}
    fm: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            fm[key.strip()] = value.strip()
    return fm


def find_skill(dir_path: Path) -> Skill | None:
    skill_file = dir_path / "SKILL.md"
    if not skill_file.is_file():
        return None
    fm = parse_frontmatter(skill_file.read_text(encoding="utf-8"))
    name = fm.get("name") or dir_path.name
    desc = fm.get("description")
    if desc and desc.startswith('"') and desc.endswith('"'):
        desc = desc[1:-1]
    try:
        dir_path.resolve().relative_to(LIBRARY_DIR.resolve())
        source = "library"
    except ValueError:
        source = "local"
    helpers = sorted(h for h in HELPER_DIRS if (dir_path / h).is_dir())
    return Skill(name=name, path=dir_path, description=desc, source=source, helpers=helpers)


def scan_tree(base: Path, skills: list[Skill], depth: int = 0, max_depth: int = 2) -> None:
    if depth > max_depth or not base.is_dir():
        return
    for item in sorted(base.iterdir()):
        if not item.is_dir() or item.name in IGNORED_DIRS or item.name.startswith("."):
            continue
        skill = find_skill(item)
        if skill:
            skills.append(skill)
        else:
            scan_tree(item, skills, depth + 1, max_depth)


def scan_all() -> list[Skill]:
    raw: list[Skill] = []
    scan_tree(SKILLS_DIR, raw)
    seen: dict[str, Path] = {}
    unique: list[Skill] = []
    for s in raw:
        if s.name in seen:
            log.warning(f"Duplicate '{s.name}' at {s.path}, already at {seen[s.name]}")
            continue
        seen[s.name] = s.path
        unique.append(s)
    return unique


# --- Utilities ---


def find_project_root() -> Path | None:
    cwd = Path.cwd()
    home = Path.home()
    for parent in [cwd, *cwd.parents]:
        if parent == home:
            return None
        if (parent / ".git").exists():
            return parent
    return None


def detect_agents(base: Path) -> dict[str, Path]:
    """Detect agents with config dirs under base."""
    found: dict[str, Path] = {}
    for agent, rel_path in AGENT_CONFIGS.items():
        config_root = base / rel_path.parent
        if config_root.is_dir():
            found[agent] = base / rel_path
    return found


def symlink_skill(link: Path, target: Path) -> bool:
    if link.is_symlink():
        if link.resolve() == target:
            return False
        link.unlink()
    if link.exists():
        log.warning(f"  {link} exists and is not a symlink, skipping")
        return False
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(target)
    return True


def home_short(p: Path) -> str:
    return str(p).replace(str(Path.home()), "~")


def classify_source(source: str) -> tuple[str, str]:
    """Classify add source as git URL, GitHub shorthand, or local path."""
    if "://" in source or source.endswith(".git"):
        return "git", source
    if source.startswith(("/", ".", "~")):
        return "local", source
    if re.match(r"^[a-zA-Z0-9_-][a-zA-Z0-9_.-]*/[a-zA-Z0-9_-][a-zA-Z0-9_.-]*$", source):
        return "github", f"https://github.com/{source}.git"
    return "local", source


def repo_name_from_url(url: str) -> str:
    name = url.rstrip("/").rsplit("/", 1)[-1]
    if name.endswith(".git"):
        name = name[:-4]
    return name


# --- Commands: Discovery ---


def cmd_list(args: argparse.Namespace) -> int:
    skills = scan_all()
    if not skills:
        print("No skills found.")
        return 0

    if args.query:
        q = args.query.lower()
        skills = [
            s for s in skills
            if q in s.name.lower() or (s.description and q in s.description.lower())
        ]
        if not skills:
            print(f"No skills matching '{args.query}'.")
            return 0

    w = max(max(len(s.name) for s in skills), 5)
    print(f"\n{'SKILL':<{w}}  {'SOURCE':<8}  DESCRIPTION")
    print(f"{'-' * w}  {'-' * 8}  {'-' * 50}")

    for s in sorted(skills, key=lambda s: s.name):
        desc = s.description or "(no description)"
        if len(desc) > 55:
            desc = desc[:52] + "..."
        print(f"{s.name:<{w}}  {s.source:<8}  {desc}")

    print(f"\nTotal: {len(skills)} skill(s)")
    return 0


def cmd_info(args: argparse.Namespace) -> int:
    skill_map = {s.name: s for s in scan_all()}
    if args.skill not in skill_map:
        log.error(f"'{args.skill}' not found")
        return 1

    s = skill_map[args.skill]
    print(f"\nName:        {s.name}")
    print(f"Path:        {home_short(s.path)}")
    print(f"Source:      {s.source}")
    print(f"Description: {s.description or '(none)'}")
    if s.helpers:
        print(f"Helpers:     {', '.join(s.helpers)}")

    fm = parse_frontmatter((s.path / "SKILL.md").read_text(encoding="utf-8"))
    extra = {k: v for k, v in fm.items() if k not in ("name", "description")}
    if extra:
        print("\nFrontmatter:")
        for k, v in extra.items():
            print(f"  {k}: {v}")
    print()
    return 0


# --- Commands: Install / Uninstall ---


def cmd_install(args: argparse.Namespace) -> int:
    skill_map = {s.name: s for s in scan_all()}

    if args.is_global:
        agents = detect_agents(Path.home())
        if not agents:
            log.error("No agents detected")
            return 1
        scope_label = "globally"
    else:
        root = find_project_root()
        if not root:
            log.error("No project root found (no .git above CWD, or CWD is home)")
            return 1
        agents = detect_agents(root)
        if not agents:
            agents = {"claude-code": root / AGENT_CONFIGS["claude-code"]}
        scope_label = f"in {home_short(root)}"

    total = 0
    errors = 0
    for name in args.skills:
        if name not in skill_map:
            log.error(f"  '{name}' not found. Run 'skillm list' to see available.")
            errors += 1
            continue
        target = skill_map[name].path.resolve()
        for agent, sdir in sorted(agents.items()):
            link = sdir / name
            if symlink_skill(link, target):
                log.info(f"  {name}: {agent} installed")
                total += 1
            elif link.is_symlink() and link.resolve() == target:
                log.info(f"  {name}: {agent} already installed")

    if total:
        log.info(f"Installed {total} symlink(s) {scope_label}")
    return 1 if errors and not total else 0


def cmd_uninstall(args: argparse.Namespace) -> int:
    if args.is_global:
        agents = detect_agents(Path.home())
        if not agents:
            log.error("No agents detected")
            return 1
        scope_label = "globally"
    else:
        root = find_project_root()
        if not root:
            log.error("No project root found")
            return 1
        agents = detect_agents(root)
        scope_label = f"from {home_short(root)}"

    total = 0
    for name in args.skills:
        for agent, sdir in sorted(agents.items()):
            link = sdir / name
            if link.is_symlink():
                link.unlink()
                log.info(f"  {name}: {agent} removed")
                total += 1
            elif link.exists():
                log.warning(f"  {name}: {agent} not a symlink, skipping")

    if total:
        log.info(f"Removed {total} symlink(s) {scope_label}")
    else:
        log.warning("Nothing to uninstall")
    return 0


def cmd_status(_args: argparse.Namespace) -> int:
    root = find_project_root()

    if root:
        print(f"\nProject: {root}")
        local_agents = detect_agents(root)
        any_local = False
        for agent, sdir in sorted(local_agents.items()):
            if not sdir.is_dir():
                continue
            links = sorted(p for p in sdir.iterdir() if p.is_symlink())
            if not links:
                continue
            any_local = True
            print(f"\n  {agent}:")
            for link in links:
                broken = " [broken]" if not link.exists() else ""
                print(f"    {link.name} -> {home_short(link.resolve())}{broken}")
        if not any_local:
            print("  No skills installed locally.")
    else:
        print("\nNo project root found.")

    print("\nGlobal:")
    global_agents = detect_agents(Path.home())
    any_global = False
    for agent, sdir in sorted(global_agents.items()):
        if not sdir.is_dir():
            continue
        links = sorted(p for p in sdir.iterdir() if p.is_symlink())
        if not links:
            continue
        any_global = True
        print(f"\n  {agent} ({len(links)} skills):")
        for link in links:
            broken = " [broken]" if not link.exists() else ""
            print(f"    {link.name}{broken}")

    if not any_global:
        print("  No skills installed globally.")

    print()
    return 0


# --- Commands: Library ---


def cmd_add(args: argparse.Namespace) -> int:
    if args.npx:
        return _add_npx(args.source)

    source_type, url = classify_source(args.source)
    if source_type in ("git", "github"):
        return _add_git(url, args.force)
    return _add_local(args.source, args.force)


def _add_npx(source: str) -> int:
    if not shutil.which("npx"):
        log.error("npx not found. Install Node.js or use native: skillm add <source>")
        return 1
    cmd = ["npx", "skills", "add", source]
    log.info(f"Delegating: {' '.join(cmd)}")
    return subprocess.run(cmd, check=False).returncode


def _add_git(url: str, force: bool = False) -> int:
    name = repo_name_from_url(url)
    target = LIBRARY_DIR / name

    if target.exists():
        if not force:
            log.error(f"'{name}' already exists in library/. Use --force to overwrite.")
            return 1
        log.info(f"Removing existing '{name}'...")
        if shutil.which("trash-put"):
            subprocess.run(["trash-put", str(target)], check=False)
        else:
            shutil.rmtree(target)

    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    log.info(f"Cloning {url} -> library/{name}/")
    result = subprocess.run(
        ["git", "clone", "--depth", "1", url, str(target)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        log.error(f"git clone failed: {result.stderr.strip()}")
        return 1

    skills: list[Skill] = []
    scan_tree(target, skills, max_depth=2)
    if skills:
        log.info(f"Found {len(skills)} skill(s): {', '.join(s.name for s in skills)}")
    else:
        log.warning(f"No SKILL.md files found in {name}")

    return 0


def _add_local(path_str: str, force: bool = False) -> int:
    source = Path(path_str).resolve()
    if not source.is_dir():
        log.error(f"'{path_str}' is not a directory")
        return 1

    name = source.name
    link = LIBRARY_DIR / name

    if link.exists() or link.is_symlink():
        if not force:
            log.error(f"'{name}' already exists in library/. Use --force to overwrite.")
            return 1
        if link.is_symlink():
            link.unlink()
        else:
            shutil.rmtree(link)

    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    link.symlink_to(source)
    log.info(f"Linked library/{name} -> {home_short(source)}")
    return 0


def cmd_remove(args: argparse.Namespace) -> int:
    target = LIBRARY_DIR / args.name
    if not target.exists() and not target.is_symlink():
        log.error(f"'{args.name}' not found in library/")
        return 1

    # Warn if skills from this repo are installed somewhere
    if target.is_dir():
        repo_skills: list[Skill] = []
        scan_tree(target, repo_skills, max_depth=2)
        for s in repo_skills:
            resolved = s.path.resolve()
            for agent, sdir in detect_agents(Path.home()).items():
                link = sdir / s.name
                if link.is_symlink() and link.resolve() == resolved:
                    log.warning(f"  '{s.name}' is installed globally in {agent}")
            root = find_project_root()
            if root:
                for agent, sdir in detect_agents(root).items():
                    link = sdir / s.name
                    if link.is_symlink() and link.resolve() == resolved:
                        log.warning(f"  '{s.name}' is installed locally in {agent}")

    if not shutil.which("trash-put"):
        log.error("trash-put not found. Install: pip install trash-cli")
        return 1

    result = subprocess.run(["trash-put", str(target)], check=False)
    if result.returncode != 0:
        log.error(f"trash-put failed for '{args.name}'")
        return 1
    log.info(f"Removed '{args.name}' from library")
    return 0


def cmd_update(args: argparse.Namespace) -> int:
    if args.name:
        target = LIBRARY_DIR / args.name
        if not target.is_dir():
            log.error(f"'{args.name}' not found in library/")
            return 1
        if not (target / ".git").is_dir():
            log.error(f"'{args.name}' is not a git repo")
            return 1
        dirs = [target]
    else:
        if not LIBRARY_DIR.is_dir():
            log.info("Library is empty")
            return 0
        dirs = sorted(
            d for d in LIBRARY_DIR.iterdir()
            if d.is_dir() and not d.is_symlink() and (d / ".git").is_dir()
        )
        if not dirs:
            log.info("No git-based skills in library")
            return 0

    for d in dirs:
        before: list[Skill] = []
        scan_tree(d, before, max_depth=2)
        before_names = {s.name for s in before}

        log.info(f"Updating {d.name}...")
        result = subprocess.run(
            ["git", "-C", str(d), "pull"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            log.error(f"  {d.name}: {result.stderr.strip()}")
            continue
        if "Already up to date" in result.stdout:
            log.info(f"  {d.name}: up to date")
            continue

        after: list[Skill] = []
        scan_tree(d, after, max_depth=2)
        after_names = {s.name for s in after}

        added = after_names - before_names
        removed = before_names - after_names
        log.info(f"  {d.name}: updated")
        if added:
            log.info(f"    new: {', '.join(sorted(added))}")
        if removed:
            log.info(f"    removed: {', '.join(sorted(removed))}")

    return 0


# --- Commands: Infra ---


def cmd_router(args: argparse.Namespace) -> int:
    skills = scan_all()
    if not skills:
        log.warning("No skills found")
        return 1

    lines = [
        "---",
        "name: router",
        'description: "Skill routing table - maps skill names to paths."',
        "---",
        "",
        "# Skill Router",
        "",
    ]
    for s in sorted(skills, key=lambda s: s.name):
        lines.append(f"{s.name}: {home_short(s.path)}/")
    lines.append("")
    content = "\n".join(lines)

    if args.dry_run:
        print(content)
        return 0

    ROUTER_DIR.mkdir(parents=True, exist_ok=True)
    ROUTER_FILE.write_text(content, encoding="utf-8")
    log.info(f"Router: {ROUTER_FILE} ({len(skills)} skills)")
    return 0


def cmd_doctor(_args: argparse.Namespace) -> int:
    issues: list[str] = []

    # 1. Frontmatter checks + duplicates
    raw: list[Skill] = []
    scan_tree(SKILLS_DIR, raw)
    seen_names: dict[str, Path] = {}
    skills: list[Skill] = []
    for s in raw:
        if s.name in seen_names:
            issues.append(
                f"duplicate name '{s.name}': {home_short(s.path)}"
                f" conflicts with {home_short(seen_names[s.name])}"
            )
            continue
        seen_names[s.name] = s.path
        skills.append(s)

    for s in skills:
        fm = parse_frontmatter((s.path / "SKILL.md").read_text(encoding="utf-8"))
        if not fm.get("name"):
            issues.append(f"missing name in frontmatter: {home_short(s.path)}/SKILL.md")
        if not s.description:
            issues.append(f"missing description: {home_short(s.path)}/SKILL.md")

    # 2. Broken symlinks in global agent dirs
    for agent, sdir in sorted(detect_agents(Path.home()).items()):
        if not sdir.is_dir():
            continue
        for link in sorted(sdir.iterdir()):
            if link.is_symlink() and not link.exists():
                issues.append(
                    f"broken global symlink: {agent}/{link.name}"
                    f" -> {home_short(link.resolve())}"
                    f"\n    fix: skillm uninstall -g {link.name}"
                )

    # 3. Broken symlinks in project
    root = find_project_root()
    if root:
        for agent, sdir in sorted(detect_agents(root).items()):
            if not sdir.is_dir():
                continue
            for link in sorted(sdir.iterdir()):
                if link.is_symlink() and not link.exists():
                    issues.append(
                        f"broken local symlink: {agent}/{link.name}"
                        f" -> {home_short(link.resolve())}"
                        f"\n    fix: skillm uninstall {link.name}"
                    )

    # 4. Library dirs with no skills
    if LIBRARY_DIR.is_dir():
        for d in sorted(LIBRARY_DIR.iterdir()):
            if not d.is_dir():
                continue
            sub: list[Skill] = []
            scan_tree(d, sub, max_depth=2)
            if not sub:
                issues.append(
                    f"library entry has no skills: library/{d.name}"
                    f"\n    fix: skillm remove {d.name}"
                )

    if issues:
        print(f"\n{len(issues)} issue(s):\n")
        for issue in issues:
            print(f"  {issue}")
    else:
        print("\nNo issues found.")

    print()
    return 1 if issues else 0


# --- Main ---


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Skill manager for AI coding agents.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Discovery:
  list [QUERY]              List available skills, optionally filter
  info SKILL                Show skill details

Install (default: local, -g for global):
  install [-g] SKILL [...]  Install skills
  uninstall [-g] SKILL [..] Uninstall skills
  status                    Show installed skills (local + global)

Library:
  add SOURCE [--npx]        Add skill repo to library (git URL, owner/repo, local path)
  remove NAME               Remove repo from library
  update [NAME]             Update git-based library repos

Infrastructure:
  router [--dry-run]        Rebuild skill router
  doctor                    Diagnose issues""",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="verbose output")
    parser.add_argument(
        "--skills-dir", type=Path, default=None,
        help="override SKILLS_DIR (default: ~/.agents/skills)",
    )

    sub = parser.add_subparsers(dest="command")

    # Discovery
    p_list = sub.add_parser("list", aliases=["ls"], help="list available skills")
    p_list.add_argument("query", nargs="?", help="filter by name or description")

    p_info = sub.add_parser("info", help="show skill details")
    p_info.add_argument("skill", help="skill name")

    # Install / Uninstall
    p_install = sub.add_parser("install", aliases=["i"], help="install skills")
    p_install.add_argument(
        "-g", "--global", action="store_true", dest="is_global", help="install globally",
    )
    p_install.add_argument("skills", nargs="+", help="skill name(s)")

    p_uninstall = sub.add_parser("uninstall", aliases=["un"], help="uninstall skills")
    p_uninstall.add_argument(
        "-g", "--global", action="store_true", dest="is_global", help="uninstall globally",
    )
    p_uninstall.add_argument("skills", nargs="+", help="skill name(s)")

    sub.add_parser("status", aliases=["st"], help="show installed skills")

    # Library
    p_add = sub.add_parser("add", help="add skill repo to library")
    p_add.add_argument("source", help="git URL, owner/repo, or local path")
    p_add.add_argument("--npx", action="store_true", help="delegate to npx skills add")
    p_add.add_argument("--force", action="store_true", help="overwrite existing")

    p_remove = sub.add_parser("remove", aliases=["rm"], help="remove from library")
    p_remove.add_argument("name", help="repo/folder name in library/")

    p_update = sub.add_parser("update", help="update library repos")
    p_update.add_argument("name", nargs="?", help="specific repo (default: all)")

    # Infra
    p_router = sub.add_parser("router", help="rebuild skill router")
    p_router.add_argument("--dry-run", action="store_true")

    sub.add_parser("doctor", help="diagnose issues")

    if argcomplete:
        argcomplete.autocomplete(parser)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    if args.skills_dir:
        global SKILLS_DIR, LIBRARY_DIR, ROUTER_DIR, ROUTER_FILE
        SKILLS_DIR = args.skills_dir.resolve()
        LIBRARY_DIR = SKILLS_DIR / "library"
        ROUTER_DIR = SKILLS_DIR / "_router"
        ROUTER_FILE = ROUTER_DIR / "SKILL.md"

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    cmds = {
        "list": cmd_list, "ls": cmd_list,
        "info": cmd_info,
        "install": cmd_install, "i": cmd_install,
        "uninstall": cmd_uninstall, "un": cmd_uninstall,
        "status": cmd_status, "st": cmd_status,
        "add": cmd_add,
        "remove": cmd_remove, "rm": cmd_remove,
        "update": cmd_update,
        "router": cmd_router,
        "doctor": cmd_doctor,
    }

    return cmds[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
