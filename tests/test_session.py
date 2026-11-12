"""session 모듈 (WP8): 단계 감지기와 세션 저장소."""

import subprocess
import sys

import pytest

from clean_chat.core.config import FIXTURES, ROOT, resolve_repo_path
from clean_chat.core.schemas import GamePhase, GameSession, Player, ReportRequest
from clean_chat.core.stage import read_jsonl
from clean_chat.session.fake import FakePhaseDetector
from clean_chat.session.store import JsonlSessionRepository

SCENARIO = FIXTURES / "scenario"


def test_fake_detector_replays_scenario():
    d = FakePhaseDetector(SCENARIO / "phases.jsonl", SCENARIO / "players.jsonl")
    assert [e.phase for e in d.events()] == [GamePhase.IDLE, GamePhase.IN_GAME, GamePhase.POST_GAME]
    assert d.players() == read_jsonl(SCENARIO / "players.jsonl", Player)


def test_fake_detector_without_players_file():
    assert FakePhaseDetector(SCENARIO / "phases.jsonl").players() == []


def test_fake_detector_stop_ends_stream():
    d = FakePhaseDetector(SCENARIO / "phases.jsonl", delay_sec=60)
    d.stop()
    assert list(d.events()) == []  # 기다리지 않고 바로 끝남


def test_session_runner_prints_events():
    out = subprocess.run(
        [sys.executable, "-m", "clean_chat.session"], capture_output=True, text=True, encoding="utf-8", timeout=60
    )
    assert out.returncode == 0
    assert '"phase":"post_game"' in out.stdout


def test_jsonl_repository_round_trip(tmp_path):
    """구현되면 자동으로 검사 시작 (미구현이면 skip)"""
    session: GameSession = read_jsonl(FIXTURES / "report" / "input.jsonl", ReportRequest)[0].session
    repo = JsonlSessionRepository(tmp_path)
    try:
        repo.save(session)
        assert repo.load(session.id) == session
        assert repo.list_ids() == [session.id]
    except NotImplementedError:
        pytest.skip("session: 저장소 미구현")


def test_relative_output_paths_resolve_from_repo_root():
    assert resolve_repo_path(".clean-chat/complaints") == ROOT / ".clean-chat" / "complaints"
    assert resolve_repo_path(ROOT / "x") == ROOT / "x"
