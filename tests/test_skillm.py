"""Tests for skillm.py."""

import argparse
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import skillm


# --- Helpers ---


def make_skill(
    path: Path,
    name: str | None = None,
    description: str | None = None,
    extras: dict[str, str] | None = None,
) -> Path:
    """Create a skill dir with SKILL.md."""
    path.mkdir(parents=True, exist_ok=True)
    lines = ["---"]
    if name:
        lines.append(f"name: {name}")
    if description:
        lines.append(f'description: "{description}"')
    if extras:
        for k, v in extras.items():
            lines.append(f"{k}: {v}")
    lines.append("---")
    lines.append("")
    lines.append(f"# {name or path.name}")
    (path / "SKILL.md").write_text("\n".join(lines), encoding="utf-8")
    return path


@pytest.fixture
def skills_env(tmp_path):
    """Temporary skills environment with patched module globals."""
    skills_dir = tmp_path / "skills"
    library_dir = skills_dir / "library"
    router_dir = skills_dir / "_router"
    router_file = router_dir / "SKILL.md"
    skills_dir.mkdir()

    with patch.multiple(
        skillm,
        SKILLS_DIR=skills_dir,
        LIBRARY_DIR=library_dir,
        ROUTER_DIR=router_dir,
        ROUTER_FILE=router_file,
    ):
        yield {
            "root": tmp_path,
            "skills_dir": skills_dir,
            "library_dir": library_dir,
            "router_dir": router_dir,
            "router_file": router_file,
        }


# ============================================================
# Unit tests: pure functions
# ============================================================


class TestParseFrontmatter:
    def test_valid(self):
        content = "---\nname: my-skill\ndescription: A skill\n---\n# Content"
        fm = skillm.parse_frontmatter(content)
        assert fm == {"name": "my-skill", "description": "A skill"}

    def test_no_frontmatter(self):
        assert skillm.parse_frontmatter("# Just a heading") == {}

    def test_empty_string(self):
        assert skillm.parse_frontmatter("") == {}

    def test_value_with_colon(self):
        content = "---\nurl: https://example.com\n---\n"
        fm = skillm.parse_frontmatter(content)
        assert fm["url"] == "https://example.com"

    def test_extra_whitespace(self):
        content = "---  \n  name  :  spaced  \n---\n"
        fm = skillm.parse_frontmatter(content)
        assert fm["name"] == "spaced"

    def test_empty_value(self):
        content = "---\nname:\n---\n"
        fm = skillm.parse_frontmatter(content)
        assert fm["name"] == ""

    def test_multiple_colons_in_value(self):
        content = '---\ndescription: "foo: bar: baz"\n---\n'
        fm = skillm.parse_frontmatter(content)
        assert fm["description"] == '"foo: bar: baz"'

    def test_multiline_content_after(self):
        content = "---\nname: x\n---\nBody line 1\nBody line 2"
        fm = skillm.parse_frontmatter(content)
        assert fm == {"name": "x"}


class TestClassifySource:
    def test_https_url(self):
        assert skillm.classify_source("https://github.com/user/repo.git") == (
            "git",
            "https://github.com/user/repo.git",
        )

    def test_git_protocol(self):
        assert skillm.classify_source("git://example.com/repo") == (
            "git",
            "git://example.com/repo",
        )

    def test_ssh_url(self):
        assert skillm.classify_source("ssh://git@github.com/user/repo") == (
            "git",
            "ssh://git@github.com/user/repo",
        )

    def test_dot_git_suffix_without_protocol(self):
        # "user/repo.git" ends with .git -> classified as git, not github
        assert skillm.classify_source("user/repo.git") == ("git", "user/repo.git")

    def test_github_shorthand(self):
        assert skillm.classify_source("vercel-labs/agent-skills") == (
            "github",
            "https://github.com/vercel-labs/agent-skills.git",
        )

    def test_github_shorthand_with_dots(self):
        assert skillm.classify_source("owner/my.repo") == (
            "github",
            "https://github.com/owner/my.repo.git",
        )

    def test_local_relative_path(self):
        assert skillm.classify_source("./my-skill") == ("local", "./my-skill")

    def test_local_absolute_path(self):
        assert skillm.classify_source("/home/user/skills") == (
            "local",
            "/home/user/skills",
        )

    def test_single_name_is_local(self):
        assert skillm.classify_source("my-skill") == ("local", "my-skill")

    def test_deep_path_is_local(self):
        assert skillm.classify_source("a/b/c") == ("local", "a/b/c")


class TestRepoNameFromUrl:
    def test_https_with_git(self):
        assert skillm.repo_name_from_url("https://github.com/user/repo.git") == "repo"

    def test_https_without_git(self):
        assert skillm.repo_name_from_url("https://github.com/user/repo") == "repo"

    def test_trailing_slash(self):
        assert skillm.repo_name_from_url("https://github.com/user/repo/") == "repo"

    def test_trailing_slash_with_git(self):
        assert skillm.repo_name_from_url("https://github.com/user/repo.git/") == "repo"

    def test_bare_name(self):
        assert skillm.repo_name_from_url("repo.git") == "repo"


class TestHomeShort:
    def test_replaces_home(self):
        result = skillm.home_short(Path.home() / "foo" / "bar")
        assert result == "~/foo/bar"

    def test_no_home_prefix(self):
        result = skillm.home_short(Path("/tmp/foo"))
        assert result == "/tmp/foo"


# ============================================================
# Unit tests: filesystem functions
# ============================================================


class TestEstimateTokens:
    def test_basic(self, tmp_path, skills_env):
        skill_dir = make_skill(
            tmp_path / "t", name="test-skill", description="A short description"
        )
        s = skillm.find_skill(skill_dir)
        assert s is not None
        idle, active = skillm.estimate_tokens(s)
        assert idle > 0
        assert active > idle

    def test_no_skill_md(self, tmp_path):
        d = tmp_path / "empty"
        d.mkdir()
        s = skillm.Skill(name="empty", path=d)
        idle, active = skillm.estimate_tokens(s)
        assert idle == 0
        assert active == 0

    def test_longer_content_more_tokens(self, tmp_path, skills_env):
        short = make_skill(tmp_path / "short", name="short", description="x")
        long_dir = tmp_path / "long"
        long_dir.mkdir()
        (long_dir / "SKILL.md").write_text(
            f"---\nname: long\ndescription: {'a' * 200}\n---\n{'content ' * 500}",
            encoding="utf-8",
        )
        s_short = skillm.find_skill(short)
        s_long = skillm.find_skill(long_dir)
        assert s_short is not None and s_long is not None
        _, active_short = skillm.estimate_tokens(s_short)
        _, active_long = skillm.estimate_tokens(s_long)
        assert active_long > active_short


class TestFindSkill:
    def test_with_full_frontmatter(self, tmp_path, skills_env):
        skill_dir = make_skill(
            tmp_path / "test-skill", name="test-skill", description="A test skill"
        )
        s = skillm.find_skill(skill_dir)
        assert s is not None
        assert s.name == "test-skill"
        assert s.description == "A test skill"
        assert s.source == "local"

    def test_no_skill_md(self, tmp_path):
        d = tmp_path / "empty"
        d.mkdir()
        assert skillm.find_skill(d) is None

    def test_name_falls_back_to_dirname(self, tmp_path, skills_env):
        skill_dir = tmp_path / "dirname-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            '---\ndescription: "test"\n---\n', encoding="utf-8"
        )
        s = skillm.find_skill(skill_dir)
        assert s is not None
        assert s.name == "dirname-skill"

    def test_strips_quoted_description(self, tmp_path, skills_env):
        skill_dir = make_skill(tmp_path / "q", name="q", description="quoted desc")
        s = skillm.find_skill(skill_dir)
        assert s is not None
        assert s.description == "quoted desc"

    def test_detects_helpers(self, tmp_path, skills_env):
        skill_dir = make_skill(tmp_path / "h", name="h", description="h")
        (skill_dir / "scripts").mkdir()
        (skill_dir / "references").mkdir()
        s = skillm.find_skill(skill_dir)
        assert s is not None
        assert s.helpers == ["references", "scripts"]

    def test_no_helpers(self, tmp_path, skills_env):
        skill_dir = make_skill(tmp_path / "h", name="h", description="h")
        s = skillm.find_skill(skill_dir)
        assert s is not None
        assert s.helpers == []

    def test_library_source(self, skills_env):
        lib = skills_env["library_dir"]
        skill_dir = make_skill(lib / "ext-skill", name="ext-skill", description="ext")
        s = skillm.find_skill(skill_dir)
        assert s is not None
        assert s.source == "library"


class TestScanTree:
    def test_finds_flat_skills(self, skills_env):
        sd = skills_env["skills_dir"]
        make_skill(sd / "a", name="a", description="skill a")
        make_skill(sd / "b", name="b", description="skill b")

        result = skillm.scan_tree(sd)
        assert {s.name for s in result} == {"a", "b"}

    def test_finds_nested_skills(self, skills_env):
        sd = skills_env["skills_dir"]
        pack = sd / "my-pack"
        pack.mkdir()
        make_skill(pack / "s1", name="s1", description="s1")
        make_skill(pack / "s2", name="s2", description="s2")

        result = skillm.scan_tree(sd)
        assert {s.name for s in result} == {"s1", "s2"}

    def test_stops_at_skill_md(self, skills_env):
        """When a dir has SKILL.md, don't recurse into subdirs."""
        sd = skills_env["skills_dir"]
        parent = make_skill(sd / "parent", name="parent", description="parent")
        make_skill(parent / "child", name="child", description="child")

        result = skillm.scan_tree(sd)
        # Only parent found, child not scanned
        assert {s.name for s in result} == {"parent"}

    def test_ignores_dotdirs(self, skills_env):
        sd = skills_env["skills_dir"]
        make_skill(sd / ".hidden", name="hidden", description="hidden")

        result = skillm.scan_tree(sd)
        assert len(result) == 0

    def test_ignores_known_dirs(self, skills_env):
        sd = skills_env["skills_dir"]
        for name in ("__pycache__", "node_modules", ".venv", "_router", "_dev"):
            make_skill(sd / name, name=name, description=name)

        result = skillm.scan_tree(sd)
        assert len(result) == 0

    def test_respects_max_depth(self, skills_env):
        sd = skills_env["skills_dir"]
        # 3 levels deep: l1/l2/l3/SKILL.md
        deep = sd / "l1" / "l2" / "l3"
        make_skill(deep, name="deep", description="deep")

        # max_depth=2: sd -> l1(0) -> l2(1) -> l3(2) -> SKILL.md found
        result2 = skillm.scan_tree(sd, max_depth=2)
        assert len(result2) == 1

        # max_depth=1: sd -> l1(0) -> l2(1) -> stop
        result1 = skillm.scan_tree(sd, max_depth=1)
        assert len(result1) == 0

    def test_nonexistent_dir(self):
        result = skillm.scan_tree(Path("/nonexistent"))
        assert result == []

    def test_sorted_output(self, skills_env):
        sd = skills_env["skills_dir"]
        make_skill(sd / "z-skill", name="z-skill", description="z")
        make_skill(sd / "a-skill", name="a-skill", description="a")

        result = skillm.scan_tree(sd)
        # scan_tree iterates sorted(base.iterdir()), so dirs are alphabetical
        assert result[0].name == "a-skill"
        assert result[1].name == "z-skill"


class TestScanAll:
    def test_deduplicates(self, skills_env):
        sd = skills_env["skills_dir"]
        make_skill(sd / "pack1" / "dupe", name="dupe", description="short")
        # pack2 has a longer SKILL.md so it wins
        p2 = sd / "pack2" / "dupe"
        p2.mkdir(parents=True)
        (p2 / "SKILL.md").write_text('---\nname: dupe\ndescription: "longer"\n---\n' + "A" * 500)

        result = skillm.scan_all()
        dupes = [s for s in result if s.name == "dupe"]
        assert len(dupes) == 1
        assert dupes[0].description == "longer"

    def test_no_duplicates(self, skills_env):
        sd = skills_env["skills_dir"]
        make_skill(sd / "a", name="a", description="a")
        make_skill(sd / "b", name="b", description="b")

        result = skillm.scan_all()
        assert len(result) == 2


class TestDetectAgents:
    def test_detects_existing(self, tmp_path):
        (tmp_path / ".claude").mkdir()
        (tmp_path / ".codex").mkdir()

        agents = skillm.detect_agents(tmp_path)
        assert "claude-code" in agents
        assert "codex" in agents
        assert agents["claude-code"] == tmp_path / ".claude" / "skills"
        assert agents["codex"] == tmp_path / ".codex" / "skills"

    def test_ignores_missing(self, tmp_path):
        assert skillm.detect_agents(tmp_path) == {}

    def test_partial(self, tmp_path):
        (tmp_path / ".claude").mkdir()
        agents = skillm.detect_agents(tmp_path)
        assert set(agents.keys()) == {"claude-code"}

    def test_nested_config(self, tmp_path):
        """opencode uses .config/opencode/skills (2-level nesting)."""
        (tmp_path / ".config" / "opencode").mkdir(parents=True)
        agents = skillm.detect_agents(tmp_path)
        assert "opencode" in agents
        assert agents["opencode"] == tmp_path / ".config" / "opencode" / "skills"


class TestSymlinkSkill:
    def test_creates_new(self, tmp_path):
        target = tmp_path / "target"
        target.mkdir()
        link = tmp_path / "links" / "my-skill"

        assert skillm.symlink_skill(link, target) is True
        assert link.is_symlink()
        assert link.resolve() == target

    def test_creates_parent_dirs(self, tmp_path):
        target = tmp_path / "target"
        target.mkdir()
        link = tmp_path / "a" / "b" / "c" / "skill"

        assert skillm.symlink_skill(link, target) is True
        assert link.is_symlink()

    def test_already_same_target(self, tmp_path):
        target = tmp_path / "target"
        target.mkdir()
        link = tmp_path / "link"
        link.symlink_to(target)

        assert skillm.symlink_skill(link, target) is False

    def test_replaces_different_target(self, tmp_path):
        old = tmp_path / "old"
        old.mkdir()
        new = tmp_path / "new"
        new.mkdir()
        link = tmp_path / "link"
        link.symlink_to(old)

        assert skillm.symlink_skill(link, new) is True
        assert link.resolve() == new

    def test_skips_real_dir(self, tmp_path):
        target = tmp_path / "target"
        target.mkdir()
        link = tmp_path / "link"
        link.mkdir()

        assert skillm.symlink_skill(link, target) is False
        assert link.is_dir()
        assert not link.is_symlink()


class TestFindProjectRoot:
    def test_finds_git_dir(self, tmp_path, monkeypatch):
        project = tmp_path / "sub" / "deep"
        project.mkdir(parents=True)
        (tmp_path / "sub" / ".git").mkdir()
        monkeypatch.chdir(project)

        assert skillm.find_project_root() == tmp_path / "sub"

    def test_returns_none_at_home(self, monkeypatch):
        monkeypatch.chdir(Path.home())
        assert skillm.find_project_root() is None

    def test_finds_nearest_git(self, tmp_path, monkeypatch):
        (tmp_path / "outer" / ".git").mkdir(parents=True)
        (tmp_path / "outer" / "inner" / ".git").mkdir(parents=True)
        cwd = tmp_path / "outer" / "inner" / "deep"
        cwd.mkdir(parents=True)
        monkeypatch.chdir(cwd)

        assert skillm.find_project_root() == tmp_path / "outer" / "inner"


# ============================================================
# Integration tests: commands
# ============================================================


class TestCmdList:
    def test_empty(self, skills_env, capsys):
        args = argparse.Namespace(command="list", query=None, installed=False, verbose=False)
        ret = skillm.cmd_list(args)
        assert ret == 0
        assert "No skills found" in capsys.readouterr().out

    def test_lists_skills(self, skills_env, capsys):
        sd = skills_env["skills_dir"]
        make_skill(sd / "alpha", name="alpha", description="Alpha skill")
        make_skill(sd / "beta", name="beta", description="Beta skill")

        args = argparse.Namespace(command="list", query=None, installed=False, verbose=False)
        ret = skillm.cmd_list(args)
        assert ret == 0
        out = capsys.readouterr().out
        assert "alpha" in out
        assert "beta" in out
        assert "Total: 2" in out

    def test_no_token_totals(self, skills_env, capsys):
        sd = skills_env["skills_dir"]
        make_skill(sd / "alpha", name="alpha", description="Alpha skill")

        args = argparse.Namespace(command="list", query=None, installed=False, verbose=False)
        skillm.cmd_list(args)
        out = capsys.readouterr().out
        assert "idle" not in out.split("Total:")[1]
        assert "active" not in out.split("Total:")[1]

    def test_query_filter_by_name(self, skills_env, capsys):
        sd = skills_env["skills_dir"]
        make_skill(sd / "alpha", name="alpha", description="Alpha skill")
        make_skill(sd / "beta", name="beta", description="Beta skill")

        args = argparse.Namespace(command="list", query="alpha", installed=False, verbose=False)
        ret = skillm.cmd_list(args)
        assert ret == 0
        out = capsys.readouterr().out
        assert "alpha" in out
        assert "beta" not in out
        assert "Total: 1" in out

    def test_query_filter_by_description(self, skills_env, capsys):
        sd = skills_env["skills_dir"]
        make_skill(sd / "x", name="x", description="Uses tailwind CSS")

        args = argparse.Namespace(command="list", query="tailwind", installed=False, verbose=False)
        skillm.cmd_list(args)
        out = capsys.readouterr().out
        assert "x" in out
        assert "Total: 1" in out

    def test_query_no_match(self, skills_env, capsys):
        sd = skills_env["skills_dir"]
        make_skill(sd / "alpha", name="alpha", description="Alpha skill")

        args = argparse.Namespace(command="list", query="zzz", installed=False, verbose=False)
        ret = skillm.cmd_list(args)
        assert ret == 0
        assert "No skills matching" in capsys.readouterr().out

    def test_long_description_truncated(self, skills_env, capsys):
        sd = skills_env["skills_dir"]
        make_skill(sd / "x", name="x", description="A" * 100)

        args = argparse.Namespace(command="list", query=None, installed=False, verbose=False)
        skillm.cmd_list(args)
        out = capsys.readouterr().out
        assert "..." in out

    def test_query_case_insensitive(self, skills_env, capsys):
        sd = skills_env["skills_dir"]
        make_skill(sd / "TailWind", name="TailWind", description="CSS framework")

        args = argparse.Namespace(command="list", query="tailwind", installed=False, verbose=False)
        skillm.cmd_list(args)
        assert "TailWind" in capsys.readouterr().out

    def test_installed_shows_global(self, skills_env, tmp_path, capsys):
        sd = skills_env["skills_dir"]
        skill = make_skill(sd / "my-skill", name="my-skill", description="desc")

        home = tmp_path / "fakehome"
        global_dir = home / ".claude" / "skills"
        global_dir.mkdir(parents=True)
        (global_dir / "my-skill").symlink_to(skill)

        with (
            patch.object(skillm, "find_project_root", return_value=None),
            patch("pathlib.Path.home", return_value=home),
        ):
            args = argparse.Namespace(command="list", query=None, installed=True, verbose=False)
            ret = skillm.cmd_list(args)

        assert ret == 0
        out = capsys.readouterr().out
        assert "Global" in out
        assert "claude-code" in out
        assert "my-skill" in out

    def test_installed_shows_local_and_global(self, skills_env, tmp_path, capsys):
        sd = skills_env["skills_dir"]
        skill = make_skill(sd / "my-skill", name="my-skill", description="desc")

        project = tmp_path / "proj"
        local_dir = project / ".claude" / "skills"
        local_dir.mkdir(parents=True)
        (local_dir / "my-skill").symlink_to(skill)

        home = tmp_path / "fakehome"
        global_dir = home / ".claude" / "skills"
        global_dir.mkdir(parents=True)
        (global_dir / "my-skill").symlink_to(skill)

        with (
            patch.object(skillm, "find_project_root", return_value=project),
            patch("pathlib.Path.home", return_value=home),
        ):
            args = argparse.Namespace(command="list", query=None, installed=True, verbose=False)
            ret = skillm.cmd_list(args)

        assert ret == 0
        out = capsys.readouterr().out
        assert "Project" in out
        assert "claude-code" in out
        assert "Global" in out

    def test_installed_broken_symlink(self, skills_env, tmp_path, capsys):
        project = tmp_path / "proj"
        link_dir = project / ".claude" / "skills"
        link_dir.mkdir(parents=True)
        (link_dir / "broken").symlink_to("/nonexistent")

        home = tmp_path / "fakehome"
        home.mkdir()

        with (
            patch.object(skillm, "find_project_root", return_value=project),
            patch("pathlib.Path.home", return_value=home),
        ):
            args = argparse.Namespace(command="list", query=None, installed=True, verbose=False)
            skillm.cmd_list(args)

        out = capsys.readouterr().out
        assert "[broken]" in out


class TestSkillPriority:
    def test_owned_beats_library(self, skills_env):
        sd = skills_env["skills_dir"]
        lib = skills_env["library_dir"]
        lib.mkdir(parents=True)
        owned = make_skill(sd / "x", name="x", description="owned")
        library = make_skill(lib / "repo" / "x", name="x", description="library")
        owned_skill = skillm.find_skill(owned)
        lib_skill = skillm.find_skill(library)
        assert skillm._skill_priority(owned_skill) < skillm._skill_priority(lib_skill)

    def test_longer_skill_wins_within_library(self, skills_env):
        lib = skills_env["library_dir"]
        lib.mkdir(parents=True)
        short = make_skill(lib / "repo-a" / "x", name="x", description="short")
        long_path = lib / "repo-b" / "x"
        long_path.mkdir(parents=True)
        (long_path / "SKILL.md").write_text("---\nname: x\n---\n" + "A" * 1000)
        short_skill = skillm.find_skill(short)
        long_skill = skillm.find_skill(long_path)
        assert skillm._skill_priority(long_skill) < skillm._skill_priority(short_skill)


class TestFindAllByName:
    def test_finds_all_duplicates(self, skills_env):
        sd = skills_env["skills_dir"]
        lib = skills_env["library_dir"]
        lib.mkdir(parents=True)
        make_skill(sd / "x", name="x", description="owned")
        make_skill(lib / "repo-a" / "x", name="x", description="lib-a")
        make_skill(lib / "repo-b" / "x", name="x", description="lib-b")
        results = skillm.find_all_by_name("x")
        assert len(results) == 3

    def test_returns_empty_for_missing(self, skills_env):
        assert skillm.find_all_by_name("nope") == []


class TestScanAllPriority:
    def test_owned_shadows_library(self, skills_env):
        sd = skills_env["skills_dir"]
        lib = skills_env["library_dir"]
        lib.mkdir(parents=True)
        make_skill(sd / "x", name="x", description="owned")
        make_skill(lib / "repo" / "x", name="x", description="library")
        results = skillm.scan_all()
        matched = [s for s in results if s.name == "x"]
        assert len(matched) == 1
        assert matched[0].source == "local"

    def test_longer_library_skill_wins(self, skills_env):
        lib = skills_env["library_dir"]
        lib.mkdir(parents=True)
        make_skill(lib / "repo-a" / "x", name="x", description="short")
        long_path = lib / "repo-b" / "x"
        long_path.mkdir(parents=True)
        (long_path / "SKILL.md").write_text("---\nname: x\n---\n" + "A" * 1000)
        results = skillm.scan_all()
        matched = [s for s in results if s.name == "x"]
        assert len(matched) == 1
        assert "repo-b" in str(matched[0].path)


class TestCmdInfo:
    def test_existing_skill(self, skills_env, capsys):
        sd = skills_env["skills_dir"]
        make_skill(
            sd / "my-skill",
            name="my-skill",
            description="desc",
            extras={"license": "MIT"},
        )

        args = argparse.Namespace(command="info", skill="my-skill", from_repo=None, verbose=False)
        ret = skillm.cmd_info(args)
        assert ret == 0
        out = capsys.readouterr().out
        assert "my-skill" in out
        assert "desc" in out
        assert "license" in out
        assert "MIT" in out
        assert "Installed:" in out

    def test_not_found(self, skills_env):
        args = argparse.Namespace(command="info", skill="nope", from_repo=None, verbose=False)
        assert skillm.cmd_info(args) == 1

    def test_with_helpers(self, skills_env, capsys):
        sd = skills_env["skills_dir"]
        s = make_skill(sd / "h", name="h", description="h")
        (s / "scripts").mkdir()
        (s / "assets").mkdir()

        args = argparse.Namespace(command="info", skill="h", from_repo=None, verbose=False)
        skillm.cmd_info(args)
        out = capsys.readouterr().out
        assert "assets" in out
        assert "scripts" in out

    def test_source_shown(self, skills_env, capsys):
        sd = skills_env["skills_dir"]
        make_skill(sd / "loc", name="loc", description="local skill")

        args = argparse.Namespace(command="info", skill="loc", from_repo=None, verbose=False)
        skillm.cmd_info(args)
        out = capsys.readouterr().out
        assert "local" in out

    def test_shows_all_duplicates(self, skills_env, capsys):
        lib = skills_env["library_dir"]
        lib.mkdir(parents=True)
        make_skill(lib / "repo-a" / "x", name="x", description="short")
        long_path = lib / "repo-b" / "x"
        long_path.mkdir(parents=True)
        (long_path / "SKILL.md").write_text("---\nname: x\n---\n" + "A" * 1000)

        args = argparse.Namespace(command="info", skill="x", from_repo=None, verbose=False)
        ret = skillm.cmd_info(args)
        assert ret == 0
        out = capsys.readouterr().out
        assert "Installed:" in out
        assert "repo-b" in out
        assert "repo-a" in out

    def test_owned_shown_first(self, skills_env, capsys):
        sd = skills_env["skills_dir"]
        lib = skills_env["library_dir"]
        lib.mkdir(parents=True)
        make_skill(sd / "x", name="x", description="owned version")
        make_skill(lib / "repo" / "x", name="x", description="library version")

        args = argparse.Namespace(command="info", skill="x", from_repo=None, verbose=False)
        skillm.cmd_info(args)
        out = capsys.readouterr().out
        assert "Installed:" in out
        assert "Also available" in out


    def test_from_repo_shows_specific(self, skills_env, capsys):
        lib = skills_env["library_dir"]
        lib.mkdir(parents=True)
        make_skill(lib / "repo-a" / "x", name="x", description="version A")
        make_skill(lib / "repo-b" / "x", name="x", description="version B")

        args = argparse.Namespace(command="info", skill="x", from_repo="repo-a", verbose=False)
        ret = skillm.cmd_info(args)
        assert ret == 0
        out = capsys.readouterr().out
        assert "[repo-a]" in out
        assert "version A" in out
        assert "repo-b" not in out

    def test_from_repo_not_found(self, skills_env):
        lib = skills_env["library_dir"]
        lib.mkdir(parents=True)
        make_skill(lib / "repo-a" / "x", name="x", description="version A")

        args = argparse.Namespace(command="info", skill="x", from_repo="nope", verbose=False)
        assert skillm.cmd_info(args) == 1


class TestResolveSkill:
    def test_unique_skill_resolves(self, skills_env):
        sd = skills_env["skills_dir"]
        make_skill(sd / "x", name="x", description="only one")
        result = skillm._resolve_skill("x", None)
        assert result is not None
        assert result.name == "x"

    def test_not_found(self, skills_env):
        result = skillm._resolve_skill("nope", None)
        assert result is None

    def test_ambiguous_returns_none(self, skills_env):
        lib = skills_env["library_dir"]
        lib.mkdir(parents=True)
        make_skill(lib / "repo-a" / "x", name="x", description="a")
        make_skill(lib / "repo-b" / "x", name="x", description="b")
        result = skillm._resolve_skill("x", None)
        assert result is None

    def test_from_repo_disambiguates(self, skills_env):
        lib = skills_env["library_dir"]
        lib.mkdir(parents=True)
        make_skill(lib / "repo-a" / "x", name="x", description="a")
        make_skill(lib / "repo-b" / "x", name="x", description="b")
        result = skillm._resolve_skill("x", "repo-b")
        assert result is not None
        assert "repo-b" in str(result.path)

    def test_from_repo_wrong_name(self, skills_env):
        lib = skills_env["library_dir"]
        lib.mkdir(parents=True)
        make_skill(lib / "repo-a" / "x", name="x", description="a")
        result = skillm._resolve_skill("x", "nonexistent-repo")
        assert result is None

    def test_owned_not_ambiguous_with_library(self, skills_env):
        sd = skills_env["skills_dir"]
        lib = skills_env["library_dir"]
        lib.mkdir(parents=True)
        make_skill(sd / "x", name="x", description="owned")
        make_skill(lib / "repo" / "x", name="x", description="lib")
        # owned + library = 2 matches, still ambiguous
        result = skillm._resolve_skill("x", None)
        assert result is None


class TestCmdInstall:
    def _make_project(self, tmp_path: Path) -> Path:
        project = tmp_path / "proj"
        (project / ".git").mkdir(parents=True)
        (project / ".claude").mkdir()
        return project

    def test_local_install(self, skills_env, tmp_path):
        sd = skills_env["skills_dir"]
        make_skill(sd / "my-skill", name="my-skill", description="desc")
        project = self._make_project(tmp_path)

        args = argparse.Namespace(
            command="install", skills=["my-skill"], is_global=False, force=False, from_repo=None, verbose=False
        )
        with patch.object(skillm, "find_project_root", return_value=project):
            ret = skillm.cmd_install(args)

        assert ret == 0
        link = project / ".claude" / "skills" / "my-skill"
        assert link.is_symlink()
        assert link.resolve() == (sd / "my-skill").resolve()

    def test_local_install_multi_agent(self, skills_env, tmp_path):
        sd = skills_env["skills_dir"]
        make_skill(sd / "my-skill", name="my-skill", description="desc")
        project = self._make_project(tmp_path)
        (project / ".codex").mkdir()

        args = argparse.Namespace(
            command="install", skills=["my-skill"], is_global=False, force=False, from_repo=None, verbose=False
        )
        with patch.object(skillm, "find_project_root", return_value=project):
            ret = skillm.cmd_install(args)

        assert ret == 0
        assert (project / ".claude" / "skills" / "my-skill").is_symlink()
        assert (project / ".codex" / "skills" / "my-skill").is_symlink()

    def test_global_install(self, skills_env, tmp_path):
        sd = skills_env["skills_dir"]
        make_skill(sd / "my-skill", name="my-skill", description="desc")
        home = tmp_path / "fakehome"
        (home / ".claude").mkdir(parents=True)
        (home / ".codex").mkdir()

        args = argparse.Namespace(
            command="install", skills=["my-skill"], is_global=True, force=False, from_repo=None, verbose=False
        )
        with patch("pathlib.Path.home", return_value=home):
            ret = skillm.cmd_install(args)

        assert ret == 0
        assert (home / ".claude" / "skills" / "my-skill").is_symlink()
        assert (home / ".codex" / "skills" / "my-skill").is_symlink()

    def test_nonexistent_skill(self, skills_env, tmp_path):
        project = self._make_project(tmp_path)

        args = argparse.Namespace(
            command="install", skills=["nope"], is_global=False, force=False, from_repo=None, verbose=False
        )
        with patch.object(skillm, "find_project_root", return_value=project):
            ret = skillm.cmd_install(args)
        assert ret == 1

    def test_multi_skill_partial_fail(self, skills_env, tmp_path):
        sd = skills_env["skills_dir"]
        make_skill(sd / "good", name="good", description="good")
        project = self._make_project(tmp_path)

        args = argparse.Namespace(
            command="install", skills=["good", "bad"], is_global=False, force=False, from_repo=None, verbose=False
        )
        with patch.object(skillm, "find_project_root", return_value=project):
            ret = skillm.cmd_install(args)

        assert ret == 0  # partial success
        assert (project / ".claude" / "skills" / "good").is_symlink()

    def test_multi_skill_all_fail(self, skills_env, tmp_path):
        project = self._make_project(tmp_path)

        args = argparse.Namespace(
            command="install", skills=["bad1", "bad2"], is_global=False, force=False, from_repo=None, verbose=False
        )
        with patch.object(skillm, "find_project_root", return_value=project):
            ret = skillm.cmd_install(args)
        assert ret == 1

    def test_idempotent(self, skills_env, tmp_path):
        sd = skills_env["skills_dir"]
        make_skill(sd / "my-skill", name="my-skill", description="desc")
        project = self._make_project(tmp_path)

        args = argparse.Namespace(
            command="install", skills=["my-skill"], is_global=False, force=False, from_repo=None, verbose=False
        )
        with patch.object(skillm, "find_project_root", return_value=project):
            skillm.cmd_install(args)
            ret = skillm.cmd_install(args)

        assert ret == 0
        assert (project / ".claude" / "skills" / "my-skill").is_symlink()

    def test_no_project_root(self, skills_env):
        args = argparse.Namespace(
            command="install", skills=["x"], is_global=False, force=False, from_repo=None, verbose=False
        )
        with patch.object(skillm, "find_project_root", return_value=None):
            assert skillm.cmd_install(args) == 1

    def test_fallback_to_claude_code(self, skills_env, tmp_path):
        """No agent dirs detected -> defaults to claude-code."""
        sd = skills_env["skills_dir"]
        make_skill(sd / "my-skill", name="my-skill", description="desc")
        project = tmp_path / "bare-proj"
        (project / ".git").mkdir(parents=True)
        # No .claude/ or other agent dirs

        args = argparse.Namespace(
            command="install", skills=["my-skill"], is_global=False, force=False, from_repo=None, verbose=False
        )
        with patch.object(skillm, "find_project_root", return_value=project):
            ret = skillm.cmd_install(args)

        assert ret == 0
        assert (project / ".claude" / "skills" / "my-skill").is_symlink()

    def test_creates_skills_subdir(self, skills_env, tmp_path):
        """Install creates .claude/skills/ when only .claude/ exists."""
        sd = skills_env["skills_dir"]
        make_skill(sd / "my-skill", name="my-skill", description="desc")
        project = self._make_project(tmp_path)

        args = argparse.Namespace(
            command="install", skills=["my-skill"], is_global=False, force=False, from_repo=None, verbose=False
        )
        with patch.object(skillm, "find_project_root", return_value=project):
            skillm.cmd_install(args)

        assert (project / ".claude" / "skills").is_dir()
        assert (project / ".claude" / "skills" / "my-skill").is_symlink()


    def test_scan_blocks_library_skill(self, skills_env, tmp_path):
        """Library skill with MEDIUM+ findings is blocked."""
        lib = skills_env["library_dir"]
        make_skill(lib / "repo" / "risky", name="risky", description="risky")
        project = self._make_project(tmp_path)

        args = argparse.Namespace(
            command="install", skills=["risky"], is_global=False, force=False, from_repo=None, verbose=False
        )
        with (
            patch.object(skillm, "find_project_root", return_value=project),
            patch.object(skillm, "run_security_scan", return_value=(False, "MEDIUM issue")),
        ):
            ret = skillm.cmd_install(args)

        assert ret == 1
        assert not (project / ".claude" / "skills" / "risky").exists()

    def test_scan_passes_library_skill(self, skills_env, tmp_path):
        """Library skill passing scan gets installed."""
        lib = skills_env["library_dir"]
        make_skill(lib / "repo" / "safe", name="safe", description="safe")
        project = self._make_project(tmp_path)

        args = argparse.Namespace(
            command="install", skills=["safe"], is_global=False, force=False, from_repo=None, verbose=False
        )
        with (
            patch.object(skillm, "find_project_root", return_value=project),
            patch.object(skillm, "run_security_scan", return_value=(True, "")),
        ):
            ret = skillm.cmd_install(args)

        assert ret == 0
        assert (project / ".claude" / "skills" / "safe").is_symlink()

    def test_force_skips_scan(self, skills_env, tmp_path):
        """--force bypasses security scan."""
        lib = skills_env["library_dir"]
        make_skill(lib / "repo" / "risky", name="risky", description="risky")
        project = self._make_project(tmp_path)

        args = argparse.Namespace(
            command="install", skills=["risky"], is_global=False, force=True, from_repo=None, verbose=False
        )
        with (
            patch.object(skillm, "find_project_root", return_value=project),
            patch.object(skillm, "run_security_scan") as mock_scan,
        ):
            ret = skillm.cmd_install(args)

        mock_scan.assert_not_called()
        assert ret == 0
        assert (project / ".claude" / "skills" / "risky").is_symlink()

    def test_local_skill_not_scanned(self, skills_env, tmp_path):
        """Local (non-library) skills skip scan."""
        sd = skills_env["skills_dir"]
        make_skill(sd / "local-skill", name="local-skill", description="local")
        project = self._make_project(tmp_path)

        args = argparse.Namespace(
            command="install", skills=["local-skill"], is_global=False, force=False, from_repo=None, verbose=False
        )
        with (
            patch.object(skillm, "find_project_root", return_value=project),
            patch.object(skillm, "run_security_scan") as mock_scan,
        ):
            ret = skillm.cmd_install(args)

        mock_scan.assert_not_called()
        assert ret == 0
        assert (project / ".claude" / "skills" / "local-skill").is_symlink()

    def test_ambiguous_skill_blocked(self, skills_env, tmp_path):
        """Install fails when skill exists in multiple repos without --from."""
        lib = skills_env["library_dir"]
        lib.mkdir(parents=True)
        make_skill(lib / "repo-a" / "dup", name="dup", description="a")
        make_skill(lib / "repo-b" / "dup", name="dup", description="b")
        project = self._make_project(tmp_path)

        args = argparse.Namespace(
            command="install", skills=["dup"], is_global=False, force=False, from_repo=None, verbose=False
        )
        with patch.object(skillm, "find_project_root", return_value=project):
            ret = skillm.cmd_install(args)

        assert ret == 1
        assert not (project / ".claude" / "skills" / "dup").exists()

    def test_from_repo_resolves_ambiguity(self, skills_env, tmp_path):
        """--from REPO picks the right skill from duplicates."""
        lib = skills_env["library_dir"]
        lib.mkdir(parents=True)
        make_skill(lib / "repo-a" / "dup", name="dup", description="a")
        make_skill(lib / "repo-b" / "dup", name="dup", description="b")
        project = self._make_project(tmp_path)

        args = argparse.Namespace(
            command="install", skills=["dup"], is_global=False, force=False, from_repo="repo-b", verbose=False
        )
        with (
            patch.object(skillm, "find_project_root", return_value=project),
            patch.object(skillm, "run_security_scan", return_value=(True, "")),
        ):
            ret = skillm.cmd_install(args)

        assert ret == 0
        link = project / ".claude" / "skills" / "dup"
        assert link.is_symlink()
        assert "repo-b" in str(link.resolve())


class TestCmdUninstall:
    def test_local_uninstall(self, skills_env, tmp_path):
        sd = skills_env["skills_dir"]
        skill = make_skill(sd / "my-skill", name="my-skill", description="desc")

        project = tmp_path / "proj"
        link_dir = project / ".claude" / "skills"
        link_dir.mkdir(parents=True)
        (link_dir / "my-skill").symlink_to(skill)

        args = argparse.Namespace(
            command="uninstall", skills=["my-skill"], is_global=False, verbose=False
        )
        with patch.object(skillm, "find_project_root", return_value=project):
            ret = skillm.cmd_uninstall(args)

        assert ret == 0
        assert not (link_dir / "my-skill").exists()

    def test_global_uninstall(self, skills_env, tmp_path):
        sd = skills_env["skills_dir"]
        skill = make_skill(sd / "my-skill", name="my-skill", description="desc")

        home = tmp_path / "fakehome"
        for agent_dir in (".claude", ".codex"):
            link_dir = home / agent_dir / "skills"
            link_dir.mkdir(parents=True)
            (link_dir / "my-skill").symlink_to(skill)

        args = argparse.Namespace(
            command="uninstall", skills=["my-skill"], is_global=True, verbose=False
        )
        with patch("pathlib.Path.home", return_value=home):
            ret = skillm.cmd_uninstall(args)

        assert ret == 0
        assert not (home / ".claude" / "skills" / "my-skill").exists()
        assert not (home / ".codex" / "skills" / "my-skill").exists()

    def test_uninstall_nothing(self, skills_env, tmp_path):
        project = tmp_path / "proj"
        (project / ".git").mkdir(parents=True)
        (project / ".claude").mkdir()

        args = argparse.Namespace(
            command="uninstall", skills=["nope"], is_global=False, verbose=False
        )
        with patch.object(skillm, "find_project_root", return_value=project):
            ret = skillm.cmd_uninstall(args)
        assert ret == 0  # returns 0 but warns

    def test_skips_real_dir(self, skills_env, tmp_path):
        """Doesn't delete a real directory, only symlinks."""
        project = tmp_path / "proj"
        link_dir = project / ".claude" / "skills"
        link_dir.mkdir(parents=True)
        real = link_dir / "my-skill"
        real.mkdir()  # not a symlink

        args = argparse.Namespace(
            command="uninstall", skills=["my-skill"], is_global=False, verbose=False
        )
        with patch.object(skillm, "find_project_root", return_value=project):
            skillm.cmd_uninstall(args)

        assert real.is_dir()  # still there

    def test_multi_uninstall(self, skills_env, tmp_path):
        sd = skills_env["skills_dir"]
        s1 = make_skill(sd / "s1", name="s1", description="s1")
        s2 = make_skill(sd / "s2", name="s2", description="s2")

        project = tmp_path / "proj"
        link_dir = project / ".claude" / "skills"
        link_dir.mkdir(parents=True)
        (link_dir / "s1").symlink_to(s1)
        (link_dir / "s2").symlink_to(s2)

        args = argparse.Namespace(
            command="uninstall", skills=["s1", "s2"], is_global=False, verbose=False
        )
        with patch.object(skillm, "find_project_root", return_value=project):
            ret = skillm.cmd_uninstall(args)

        assert ret == 0
        assert not (link_dir / "s1").exists()
        assert not (link_dir / "s2").exists()


class TestCmdStatus:
    """Status is an alias for 'list --installed'."""

    def test_delegates_to_list_installed(self, skills_env, tmp_path, capsys):
        home = tmp_path / "fakehome"
        home.mkdir()

        with (
            patch.object(skillm, "find_project_root", return_value=None),
            patch("pathlib.Path.home", return_value=home),
        ):
            ret = skillm.cmd_status(argparse.Namespace(command="status", verbose=False))

        assert ret == 0
        out = capsys.readouterr().out
        assert "No skills installed globally" in out


class TestCmdScan:
    def test_missing_skill_name_and_no_all(self, skills_env):
        args = argparse.Namespace(
            command="scan", skill=None, all=False, format="markdown", verbose=False
        )
        assert skillm.cmd_scan(args) == 1

    def test_skill_not_found(self, skills_env):
        args = argparse.Namespace(
            command="scan", skill="nonexistent", all=False, format="markdown", verbose=False
        )
        assert skillm.cmd_scan(args) == 1

    def test_no_uvx(self, skills_env):
        make_skill(skills_env["skills_dir"] / "s", name="s", description="s")
        args = argparse.Namespace(
            command="scan", skill="s", all=False, format="markdown", verbose=False
        )
        with patch("shutil.which", return_value=None):
            assert skillm.cmd_scan(args) == 1

    def test_single_skill_calls_scanner(self, skills_env):
        sd = skills_env["skills_dir"]
        make_skill(sd / "my-skill", name="my-skill", description="desc")
        args = argparse.Namespace(
            command="scan", skill="my-skill", all=False, format="json", verbose=False
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            ret = skillm.cmd_scan(args)

        assert ret == 0
        cmd = mock_run.call_args[0][0]
        assert "scan" in cmd
        assert "--format" in cmd
        assert "json" in cmd
        assert str(sd / "my-skill") in cmd

    def test_all_calls_scan_all(self, skills_env):
        args = argparse.Namespace(
            command="scan", skill=None, all=True, format="markdown", verbose=False
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            ret = skillm.cmd_scan(args)

        assert ret == 0
        cmd = mock_run.call_args[0][0]
        assert "scan-all" in cmd
        assert "--recursive" in cmd

    def test_verbose_flag(self, skills_env):
        sd = skills_env["skills_dir"]
        make_skill(sd / "v", name="v", description="v")
        args = argparse.Namespace(
            command="scan", skill="v", all=False, format="markdown", verbose=True
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            skillm.cmd_scan(args)

        cmd = mock_run.call_args[0][0]
        assert "--verbose" in cmd


class TestCmdRouter:
    def test_dry_run(self, skills_env, capsys):
        sd = skills_env["skills_dir"]
        make_skill(sd / "alpha", name="alpha", description="Alpha")
        make_skill(sd / "beta", name="beta", description="Beta")

        args = argparse.Namespace(command="router", dry_run=True, verbose=False)
        ret = skillm.cmd_router(args)
        assert ret == 0
        out = capsys.readouterr().out
        assert "# Skill Router" in out
        assert "alpha:" in out
        assert "beta:" in out

    def test_write(self, skills_env):
        sd = skills_env["skills_dir"]
        make_skill(sd / "alpha", name="alpha", description="Alpha")

        args = argparse.Namespace(command="router", dry_run=False, verbose=False)
        ret = skillm.cmd_router(args)
        assert ret == 0

        rf = skills_env["router_file"]
        assert rf.exists()
        content = rf.read_text()
        assert "alpha:" in content
        assert "name: router" in content

    def test_empty_skills(self, skills_env):
        args = argparse.Namespace(command="router", dry_run=False, verbose=False)
        ret = skillm.cmd_router(args)
        assert ret == 1

    def test_router_sorted(self, skills_env, capsys):
        sd = skills_env["skills_dir"]
        make_skill(sd / "z-skill", name="z-skill", description="z")
        make_skill(sd / "a-skill", name="a-skill", description="a")

        args = argparse.Namespace(command="router", dry_run=True, verbose=False)
        skillm.cmd_router(args)
        out = capsys.readouterr().out
        assert out.index("a-skill") < out.index("z-skill")


class TestCmdDoctor:
    def _run_doctor(self, skills_env, home=None, project=None):
        fake_home = home or (skills_env["root"] / "fakehome")
        fake_home.mkdir(exist_ok=True)
        with (
            patch("pathlib.Path.home", return_value=fake_home),
            patch.object(skillm, "find_project_root", return_value=project),
        ):
            return skillm.cmd_doctor(
                argparse.Namespace(command="doctor", verbose=False)
            )

    def test_clean(self, skills_env, capsys):
        sd = skills_env["skills_dir"]
        make_skill(sd / "good", name="good", description="desc")

        ret = self._run_doctor(skills_env)
        assert ret == 0
        assert "No issues found" in capsys.readouterr().out

    def test_missing_description(self, skills_env, capsys):
        sd = skills_env["skills_dir"]
        s = sd / "no-desc"
        s.mkdir()
        (s / "SKILL.md").write_text("---\nname: no-desc\n---\n", encoding="utf-8")

        ret = self._run_doctor(skills_env)
        assert ret == 1
        assert "missing description" in capsys.readouterr().out

    def test_missing_name(self, skills_env, capsys):
        sd = skills_env["skills_dir"]
        s = sd / "no-name"
        s.mkdir()
        (s / "SKILL.md").write_text(
            '---\ndescription: "has desc"\n---\n', encoding="utf-8"
        )

        ret = self._run_doctor(skills_env)
        assert ret == 1
        assert "missing name" in capsys.readouterr().out

    def test_duplicate_names_are_notes_not_issues(self, skills_env, capsys):
        sd = skills_env["skills_dir"]
        make_skill(sd / "pack1" / "dupe", name="dupe", description="first")
        make_skill(sd / "pack2" / "dupe", name="dupe", description="second")

        ret = self._run_doctor(skills_env)
        assert ret == 0
        out = capsys.readouterr().out
        assert "Duplicates" in out
        assert "dupe" in out
        assert "No issues found" in out

    def test_broken_global_symlink(self, skills_env, capsys):
        home = skills_env["root"] / "fakehome"
        link_dir = home / ".claude" / "skills"
        link_dir.mkdir(parents=True)
        (link_dir / "broken").symlink_to("/nonexistent/path")

        ret = self._run_doctor(skills_env, home=home)
        assert ret == 1
        out = capsys.readouterr().out
        assert "broken symlink" in out
        assert "global" in out
        assert "skillm uninstall -g broken" in out

    def test_broken_local_symlink(self, skills_env, capsys):
        project = skills_env["root"] / "project"
        link_dir = project / ".claude" / "skills"
        link_dir.mkdir(parents=True)
        (link_dir / "broken").symlink_to("/nonexistent/path")

        ret = self._run_doctor(skills_env, project=project)
        assert ret == 1
        out = capsys.readouterr().out
        assert "broken symlink" in out
        assert "project" in out
        assert "skillm uninstall broken" in out

    def test_empty_library_entry(self, skills_env, capsys):
        lib = skills_env["library_dir"]
        (lib / "empty-repo").mkdir(parents=True)

        ret = self._run_doctor(skills_env)
        assert ret == 1
        out = capsys.readouterr().out
        assert "empty library repo" in out
        assert "skillm remove empty-repo" in out

    def test_multiple_issues(self, skills_env, capsys):
        sd = skills_env["skills_dir"]
        s = sd / "no-desc"
        s.mkdir()
        (s / "SKILL.md").write_text("---\nname: no-desc\n---\n", encoding="utf-8")

        lib = skills_env["library_dir"]
        (lib / "empty").mkdir(parents=True)

        ret = self._run_doctor(skills_env)
        assert ret == 1
        out = capsys.readouterr().out
        assert "2 issue(s)" in out
