"""모듈 단독 실행기 (`clean-chat module <이름>`): Mock 없이 실제 함수만 실행한다."""

import pytest

from clean_chat.core import modules
from clean_chat.core.modules import MODULE_NAMES
from clean_chat.core.runner import run_module
from helpers import fixture_pairs


@pytest.mark.parametrize("name", MODULE_NAMES)
def test_unimplemented_module_exits_2(name, monkeypatch, capsys):
    def not_yet(_item):
        raise NotImplementedError(f"{name} 담당: run")

    monkeypatch.setattr(modules, "load", lambda _n: not_yet)
    assert run_module(name) == 2
    assert "구현이 아직 없습니다" in capsys.readouterr().err


def test_implemented_module_is_checked_against_expected(monkeypatch, capsys):
    expected = {i.line.id: o for i, o in fixture_pairs("parse")}
    monkeypatch.setattr(modules, "load", lambda _n: lambda req: expected[req.line.id])
    assert run_module("parse", check=True) == 0
    assert "expected 일치: 10/10" in capsys.readouterr().err


def test_wrong_output_fails_check(monkeypatch):
    out = fixture_pairs("parse")[1][1]  # 항상 같은 값 → 기대값과 다름
    monkeypatch.setattr(modules, "load", lambda _n: lambda _req: out)
    assert run_module("parse", check=True) == 1
