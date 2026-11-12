import pytest

from lolguard.core.config import STAGE_NAMES
from lolguard.core.runner import run_module


@pytest.mark.parametrize("name", STAGE_NAMES)
def test_module_runs_standalone_with_mock(name, capsys):
    assert run_module(name, ["--impl", "mock", "--check"]) == 0
    assert "형식 OK" in capsys.readouterr().err
