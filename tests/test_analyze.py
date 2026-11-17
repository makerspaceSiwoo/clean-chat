"""③ analyze 모듈 (담당자 소유). AI 모듈이라 출력 형식만 자동 검사하고, 정확도는 training/ 평가로 본다."""

import pytest

from clean_chat.core.schemas import AnalyzeRequest, ChatMessage, Level, Player
from clean_chat.modules.analyze import evaluate, impl
from helpers import check_module, fixture_pairs


def _req(text: str, text_norm: str | None = None, hints: tuple[str, ...] = (), **kwargs) -> AnalyzeRequest:
    msg = ChatMessage(
        id="T1",
        ts=0.0,
        source="ocr",
        channel="team",
        speaker="화자",
        text=text,
        text_norm=text_norm or text,
        hints=list(hints),
        raw=text,
    )
    return AnalyzeRequest(message=msg, **kwargs)


def test_analyze_fixtures():
    check_module("analyze", strict=False)


def test_rule_matches_fixture_expected():
    """규칙 구현은 fixtures 기대값과 같아야 한다 (model_version 만 다름)."""
    for req, expected in fixture_pairs("analyze"):
        out = impl.run(req)
        assert out == expected.model_copy(update={"model_version": out.model_version}), req.message.text


@pytest.mark.parametrize(
    ("text", "level", "types"),
    [  # docs/LABELING_GUIDE.md "헷갈리는 예"
        ("미드 갱 ㄱㄱ", 0, []),
        ("아 ㅈㄴ 아프네", 1, ["profanity"]),
        ("원딜 개못하네 트롤이냐", 2, ["blame"]),
        ("다들 정글 탓인 거 알지? 정글 신고 ㄱ", 2, ["blame", "instigation"]),
        ("내가 못했네 미안", 0, []),
    ],
)
def test_labeling_guide_examples(text, level, types):
    out = impl.run(_req(text))
    assert (int(out.level), [t.value for t in out.harm_types]) == (level, types)


def test_feedback_keeps_second_position_word():
    """부른 대상(첫 포지션 단어)만 빼고, 가야 할 곳("탑")은 피드백에 남긴다."""
    out = impl.run(_req("정글 탑 좀 와 ㅂㅅ아", "정글 탑 좀 와 병신아", ("lexicon:ㅂㅅ",)))
    assert (out.target, out.profanity_spans, out.feedback_spans) == (
        "정글",
        ["ㅂㅅ"],
        ["탑 좀 와"],
    )  # 명단 없음 → 단어 그대로


def test_spans_are_substrings_of_original_text():
    req = _req("서폿 ㅅ1ㅂ 와드 좀 박아 tlqkf", "서폿 시발 와드 좀 박아 시발", ("lexicon:tlqkf",))
    out = impl.run(req)
    assert out.profanity_spans and out.feedback_spans == ["와드 좀 박아"]
    assert all(span in req.message.text for span in out.profanity_spans + out.feedback_spans)


def test_target_from_roster_and_history():
    players = [Player(name="화자", champion="아리"), Player(name="불주먹", champion="리신")]
    assert impl.run(_req("리신 ㅂㅅ", "리신 병신", players=players)).target == "불주먹"  # 챔피언으로 불러도 닉네임
    prev = _req("ㅈㅅ").message.model_copy(update={"speaker": "불주먹"})
    assert impl.run(_req("야 너 ㅂㅅ이냐", "야 너 병신이냐", history=[prev])).target == "불주먹"


def _said(speaker: str, champion: str) -> ChatMessage:
    return _req("ㅎㅇ").message.model_copy(update={"speaker": speaker, "champion": champion})


def test_position_word_resolves_to_nickname_by_champion():
    """채팅에는 `닉네임 (챔피언)` 만 있다 → "정글" 은 정글을 주로 가는 챔피언을 고른 사람."""
    history = [_said("초코우유", "리 신"), _said("달빛고양이", "제드")]  # 명단 없이 앞 대화만으로
    assert impl.run(_req("정글 개새끼", history=history)).target == "초코우유"
    assert impl.run(_req("미드 개새끼", history=history)).target == "달빛고양이"
    assert impl.run(_req("서폿 개새끼", history=history)).target == "서폿"  # 해당하는 사람이 없으면 단어 그대로


def test_position_word_uses_whole_lineup_when_ambiguous():
    """그라가스·리신 둘 다 정글을 갈 수 있다 → 5명 전체 배치로 보면 그라가스가 탑, 리신이 정글."""
    team = [("화자", "징크스"), ("술통", "그라가스"), ("불주먹", "리신"), ("여우", "아리"), ("등불", "쓰레쉬")]
    players = [Player(name=n, champion=c, team="ORDER") for n, c in team]
    assert impl.run(_req("정글 개새끼", players=players)).target == "불주먹"
    assert impl.run(_req("탑 개새끼", players=players)).target == "술통"
    two = [Player(name=n, champion=c, team="ORDER") for n, c in team[:1] + [("술통", "리신"), ("불주먹", "녹턴")]]
    assert impl.run(_req("정글 개새끼", players=two)).target == "정글"  # 정글 챔피언이 둘 → 좁히지 못함


def test_position_word_prefers_roster_position_and_side():
    players = [
        Player(name="화자", champion="징크스", team="ORDER"),
        Player(name="우리탑", champion="리신", team="ORDER", position="TOP"),  # 명단에 포지션이 있으면 그것이 우선
        Player(name="상대편", champion="가렌", team="CHAOS"),
    ]
    assert impl.run(_req("탑 개새끼", players=players)).target == "우리탑"
    assert impl.run(_req("상대 탑 개새끼", players=players)).target == "상대편"


def test_failure_returns_safe_value(monkeypatch):
    def boom(_text: str) -> dict[str, float]:
        raise RuntimeError("모델 로딩 실패")

    monkeypatch.setattr(impl, "_predict_harm", boom)
    out = impl.run(_req("정글 개새끼"))
    assert (out.level, out.profanity_spans) == (Level.L0_CLEAN, [])


def test_evaluate_reports_metrics(tmp_path):
    path = tmp_path / "eval.csv"
    path.write_text(
        "text,level,harm_types,has_feedback,feedback,target,writer,note\n"
        "다들 화이팅,0,,0,,none,T,\n"
        "아 ㅅㅂ 내가 실수함,1,profanity,0,,none,T,\n"
        "서폿 와드 좀 박아 ㅂㅅ아,2,profanity|blame,1,시야 좀 잡아 주세요,team,T,\n"
        "원딜 실력이 왜 그러냐,2,blame,0,,team,T,\n",  # 규칙이 놓치는 문장 (L0 으로 예측)
        encoding="utf-8",
    )
    result = evaluate.evaluate(evaluate.load_rows(path))
    assert result["n"] == 4
    assert result["level_accuracy"] == 0.75
    assert result["severe_recall"] == 0.5
    assert result["clean_false_positive_rate"] == 0.0
    assert result["harm_types"]["profanity"]["f1"] == 1.0
    assert [e["text"] for e in result["errors"]] == ["원딜 실력이 왜 그러냐"]
    assert "등급 일치율" in evaluate.format_report(result)
