"""③ analyze 모듈 (담당자 소유). AI 모듈이라 출력 형식만 자동 검사하고, 정확도는 training/ 평가로 본다."""

import json

import pytest

from clean_chat.core.config import FIXTURES
from clean_chat.core.jsonl import read_jsonl
from clean_chat.core.schemas import AnalyzeRequest, ChatMessage, Level, Player, ReportRequest
from clean_chat.modules.analyze import evaluate, impl, judge, model, precedents, train
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


# ── 챔피언 이름이 나와도 대상이 아닌 경우 ─────────────────────
def test_enemy_champion_in_call_is_not_target():
    players = [
        Player(name="화자", champion="징크스", team="ORDER"),
        Player(name="불주먹", champion="리 신", team="ORDER"),
        Player(name="검은별", champion="마이", team="CHAOS"),
    ]
    out = impl.run(_req("아 ㅅㅂ 마이부터 잡으라고", "아 시발 마이부터 잡으라고", ("lexicon:ㅅㅂ",), players=players))
    assert (out.target, int(out.level)) == (None, 1)  # 마이는 잡을 상대이지 욕하는 대상이 아니다
    out = impl.run(_req("리신 갱 좀 와라 ㅅㅂ", "리신 갱 좀 와라 시발", ("lexicon:ㅅㅂ",), players=players))
    assert (out.target, int(out.level)) == ("불주먹", 2)  # 같은 팀을 챔피언 이름으로 부름


# ── 파인튜닝 모델 연결 ───────────────────────────────────────
def test_model_scores_are_merged_with_rules(monkeypatch):
    """규칙이 놓치는 비난을 모델 점수가 채운다. 모델이 없으면 규칙만."""
    text = "원딜 실력이 왜 그러냐"
    assert int(impl.run(_req(text)).level) == 0
    monkeypatch.setattr(model, "predict", lambda _t: {"blame": 0.83, "profanity": 0.02})
    monkeypatch.setattr(model, "version", lambda: "fake-ft-0.1")
    out = impl.run(_req(text))
    assert (int(out.level), [t.value for t in out.harm_types], out.scores) == (2, ["blame"], {"blame": 0.83})
    assert out.model_version == f"{impl.MODEL_VERSION}+fake-ft-0.1"


def test_train_then_load_tiny_model(tmp_path, monkeypatch):
    """train.py 가 저장한 폴더를 model.py 가 읽는다 (인터넷 없이, 아주 작은 무작위 모델로 경로만 확인)."""
    pytest.importorskip("torch")
    transformers = pytest.importorskip("transformers")
    base = tmp_path / "base"
    base.mkdir()
    vocab = ["[PAD]", "[UNK]", "[CLS]", "[SEP]", "[MASK]", *"정글미드원딜탑서폿용먼저치라고못하네왜안와개"]
    (base / "vocab.txt").write_text("\n".join(vocab), encoding="utf-8")
    transformers.BertTokenizer(str(base / "vocab.txt")).save_pretrained(base)
    config = transformers.ElectraConfig(
        vocab_size=len(vocab), embedding_size=16, hidden_size=16, num_hidden_layers=1, num_attention_heads=2,
        intermediate_size=32, max_position_embeddings=64,
    )  # fmt: skip
    transformers.ElectraForSequenceClassification(config).save_pretrained(base)
    data = tmp_path / "train.csv"
    data.write_text(
        "text,text_norm,harm_types,split\n정글 못하네,정글 못하네,blame,train\n용 먼저 치자,용 먼저 치자,,train\n"
        "미드 왜 안 와,미드 왜 안 와,blame,test\n",
        encoding="utf-8",
    )
    out = train.train(data, str(base), tmp_path / "out", "tiny-0.1", epochs=1, batch_size=2)
    assert json.loads((out / "meta.json").read_text(encoding="utf-8"))["train_rows"] == 2  # test 행은 학습에서 제외
    monkeypatch.setenv(model.ENV_VAR, str(out))
    scores = model.predict("정글 못하네")
    assert set(scores) == set(train.LABELS) and all(0.0 <= v <= 1.0 for v in scores.values())
    assert model.version() == "tiny-0.1"


def test_model_missing_falls_back_to_rules(tmp_path, monkeypatch):
    monkeypatch.setenv(model.ENV_VAR, str(tmp_path / "nothing"))
    assert model.predict("정글 개새끼") == {} and model.version() is None
    assert impl.run(_req("정글 개새끼")).model_version == impl.MODEL_VERSION


# ── 대화 판단 ────────────────────────────────────────────────
ROSTER = [
    Player(name="나", champion="쓰레쉬", team="ORDER", is_me=True),
    Player(name="불꽃남자", champion="징크스", team="ORDER"),
    Player(name="초코우유", champion="리 신", team="ORDER"),
    Player(name="달빛고양이", champion="제드", team="ORDER"),
    Player(name="밤하늘별", champion="가렌", team="ORDER"),
    Player(name="얼음땡", champion="다리우스", team="CHAOS"),
]


def _chat(i: int, ts: float, speaker: str, text: str, norm: str | None = None, channel: str = "team") -> ChatMessage:
    champion = next((p.champion for p in ROSTER if p.name == speaker), None)
    return ChatMessage(
        id=f"C{i}", ts=ts, source="ocr", channel=channel, speaker=speaker, champion=champion,
        text=text, text_norm=norm or text, raw=text, is_me=speaker == "나",
    )  # fmt: skip


def test_judge_sees_agreement_and_pile_on():
    """한 문장으로는 정상인 "ㅇㅈ" 도 흐름에서는 몰이 가담이다. 대상 없는 욕설(L1)은 신고 대상이 아니다."""
    messages = [
        _chat(0, 0, "밤하늘별", "아 ㅅㅂ 내가 실수함", "아 시발 내가 실수함"),
        _chat(1, 10, "불꽃남자", "정글 개못하네 다들 정글 신고해"),
        _chat(2, 14, "달빛고양이", "ㅇㅈ"),
        _chat(3, 500, "달빛고양이", "ㅇㅈ"),  # 한참 뒤의 맞장구는 무관
    ]
    result = judge.judge(judge.JudgeRequest(messages=messages, players=ROSTER, my_name="나"))
    assert [s.speaker for s in result.speakers] == ["불꽃남자", "달빛고양이"]
    first, second = result.speakers
    assert (first.targets, first.report, first.complaint_candidate, first.toward_me) == (
        ["초코우유"],
        True,
        False,
        False,
    )
    assert [(e.msg_id, e.kind) for e in second.evidence] == [("C2", "agree")]
    assert any("여러 명" in r for r in first.reasons)


def test_judge_marks_complaint_candidate_with_legal_review():
    """나(서폿)를 향한 패드립 → 고소 후보 + 요건 점검표. 판례 색인이 있으면 비슷한 판례도 붙는다."""
    messages = [_chat(0, 0, "얼음땡", "서폿 니애미 ㅅㅂ", "서폿 니애미 시발", channel="all")]
    index = precedents.PrecedentIndex(
        [  # 테스트용 가상 요지 (실제 판례 아님)
            precedents.Precedent(
                id="T1", charge="모욕", summary="온라인 게임 채팅에서 니애미 등 욕설을 하여 모욕한 사안"
            ),
            precedents.Precedent(id="T2", charge="모욕", summary="인터넷 게시판에 허위 사실을 올린 사안"),
            precedents.Precedent(id="T3", charge="통신매체이용음란", summary="메신저로 음란한 글을 보낸 사안"),
        ]
    )
    result = judge.judge(judge.JudgeRequest(messages=messages, players=ROSTER, my_name="나"), index)
    (who,) = result.speakers
    assert (who.speaker, who.toward_me, who.complaint_candidate) == ("얼음땡", True, True)
    (legal,) = who.legal
    assert (legal.charge, [(r.name, r.status) for r in legal.requirements]) == (
        "모욕",
        [("공연성", "충족"), ("특정성", "불명"), ("모욕적 표현", "충족")],
    )
    assert [s.precedent.id for s in legal.similar][0] == "T1" and "법률 자문이 아닙니다" in legal.notice


def test_judge_repeated_abuse_toward_me_becomes_candidate():
    """L2 한 번은 신고 권고까지. 짧은 시간에 반복되면 누적 점수로 고소 후보가 된다."""
    once = [_chat(0, 0, "불꽃남자", "서폿 개새끼")]
    again = [_chat(i, i * 20, "불꽃남자", "서폿 개새끼") for i in range(4)]
    one = judge.judge(judge.JudgeRequest(messages=once, players=ROSTER, my_name="나")).speakers[0]
    many = judge.judge(judge.JudgeRequest(messages=again, players=ROSTER, my_name="나")).speakers[0]
    assert (one.report, one.complaint_candidate) == (True, False)
    assert many.complaint_candidate and many.score_toward_me >= judge.COMPLAINT_SCORE


def test_judge_session_uses_recorded_analyses():
    """세션 기록을 그대로 넣으면 실시간 필터 결과(Analysis)를 다시 계산하지 않고 쓴다."""
    session = read_jsonl(FIXTURES / "report" / "input.jsonl", ReportRequest)[0].session
    result = judge.judge_session(session)
    assert {s.speaker: s.report for s in result.speakers} == {"불꽃남자": True, "얼음땡": True}
    assert all(not s.toward_me for s in result.speakers)  # 시나리오의 대상은 정글·미드·탑이고 나는 서폿


def test_precedent_index_empty_and_search(tmp_path):
    assert len(precedents.load_index(tmp_path / "none.jsonl")) == 0
    path = tmp_path / "p.jsonl"
    rows = [
        precedents.Precedent(id="A", charge="모욕", summary="게임 채팅에서 욕설로 모욕"),
        precedents.Precedent(id="B", charge="모욕", summary="회의 자리에서 한 발언"),
    ]
    path.write_text("".join(r.model_dump_json() + "\n" for r in rows), encoding="utf-8")
    index = precedents.load_index(path)
    assert [s.precedent.id for s in index.search("게임 채팅 욕설", "모욕", k=1)] == ["A"]
    assert index.search("게임 채팅 욕설", "통신매체이용음란") == []


def test_evaluate_scores_spans_and_split(tmp_path):
    path = tmp_path / "eval.csv"
    path.write_text(
        "text,text_norm,hints,level,harm_types,profanity_spans,split\n"
        "아 ㅅㅂ 실수,아 시발 실수,lexicon:ㅅㅂ,1,profanity,ㅅㅂ,test\n"
        "정글 개새끼,정글 개새끼,,2,profanity,개새,test\n"  # 정답 조각이 다름 → 조각 불일치
        "다들 화이팅,다들 화이팅,,0,,,train\n",
        encoding="utf-8",
    )
    result = evaluate.evaluate(evaluate.load_rows(path, "test"))
    assert (result["n"], result["level_accuracy"], result["span_accuracy"]) == (2, 1.0, 0.5)
