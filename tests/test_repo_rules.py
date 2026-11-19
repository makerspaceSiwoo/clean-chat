"""모듈 범위 검사 (CI module-scope, ADR-0018): <모듈>/<작업 내용> 브랜치는 모듈 범위 밖 파일을 바꾸면 실패."""

import subprocess
import sys

import pytest

from clean_chat.core.config import ROOT
from clean_chat.core.modules import MODULE_NAMES

sys.path.insert(0, str(ROOT / "scripts"))
import repo_rules  # noqa: E402


def test_modules_match_core():
    assert repo_rules.MODULES == MODULE_NAMES


@pytest.mark.parametrize(
    ("branch", "module"),
    [("parse/colon-fix", "parse"), ("analyze/모델-교체", "analyze"), ("report/a/b", "report")],
)
def test_module_branch(branch, module):
    assert repo_rules.module_of(branch) == module


@pytest.mark.parametrize("branch", ["main", "develop", "chore/ci", "parse", "parse/", "mod/parse", "parser/x"])
def test_not_module_branch(branch):
    assert repo_rules.module_of(branch) is None


def test_scope():
    files = [
        "src/clean_chat/modules/parse/impl.py",
        "src/clean_chat/modules/parse/lexicon.py",
        "tests/test_parse.py",
        "fixtures/parse/input.jsonl",
        "src/clean_chat/modules/analyze/impl.py",
        "src/clean_chat/core/schemas.py",
        "tests/test_parser.py",
    ]
    assert repo_rules.out_of_scope("parse", files) == [
        "src/clean_chat/modules/analyze/impl.py",
        "src/clean_chat/core/schemas.py",
        "tests/test_parser.py",
    ]


@pytest.mark.parametrize("module", MODULE_NAMES)
def test_scope_paths_exist(module):
    folder, test_file, fixtures = repo_rules.module_scope(module)
    assert (ROOT / folder / "impl.py").exists()
    assert (ROOT / test_file).exists()
    assert (ROOT / fixtures).is_dir()


def _check(branch: str, *files: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "check_module_boundary.py", branch, *files],
        cwd=ROOT / "scripts",
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_script_fails_outside_scope_and_passes_otherwise():
    assert _check("parse/x", "src/clean_chat/modules/parse/impl.py").returncode == 0
    bad = _check("parse/x", "src/clean_chat/modules/parse/impl.py", "src/clean_chat/core/schemas.py")
    assert bad.returncode == 1 and "src/clean_chat/core/schemas.py" in bad.stdout
    assert _check("chore/anything", "src/clean_chat/core/schemas.py").returncode == 0
