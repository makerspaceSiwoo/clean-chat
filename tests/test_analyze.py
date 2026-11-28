"""③ analyze 모듈 (담당자 소유). AI 모듈이라 출력 형식만 자동 검사하고, 정확도는 training/ 평가로 본다."""

import json

import pytest

from clean_chat.core.config import FIXTURES
from clean_chat.core.jsonl import read_jsonl
from clean_chat.core.schemas import Analysis, AnalyzeRequest, ChatMessage, Level, Player, ReportRequest
from clean_chat.modules.analyze import evaluate, impl, judge, judge_evaluate, judge_model, model, precedents, train
from helpers import check_module, fixture_pairs


@pytest.fixture(autouse=True)
def _rules_only(monkeypatch, tmp_path):
    """테스트는 규칙만으로 돈다. 개발 PC 의 `models/analyze-classifier/` 에 모델이 있어도 결과가 달라지지 않게 한다."""
    monkeypatch.setenv(model.ENV_VAR, str(tmp_path / "no-model"))
    monkeypatch.setenv(judge_model.ENV_VAR, str(tmp_path / "no-judge-model"))


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
    assert model.version() == "tiny-0.1" and model.backend() == "torch"

    # ONNX 로 내보내면 같은 점수를 ONNX 로 낸다 (앱은 torch 없이 이 경로만 쓴다)
    pytest.importorskip("onnx")
    pytest.importorskip("onnxruntime")
    from clean_chat.modules.analyze import export_onnx

    export_onnx.export(out)
    result = export_onnx.compare(out, ["정글 못하네", "용 먼저 치자", "미드 왜 안 와", "처음 보는 말"])
    assert result["flips"] == 0 and result["max_diff"] < export_onnx.MAX_DIFF
    model._load_once.cache_clear()
    assert model.backend() == "onnx"
    onnx_scores = model.predict("정글 못하네")
    assert all(abs(onnx_scores[k] - scores[k]) < 1e-4 for k in scores)

    # 다시 학습하면 예전 ONNX 는 지운다 (새 가중치보다 먼저 쓰이지 않게)
    train.train(data, str(base), out, "tiny-0.2", epochs=1, batch_size=2)
    assert not (out / "model.onnx").exists()


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


def test_judge_runs_in_simulator():
    """시뮬레이터에서 대화 판단을 간단 입력(여러 줄 대화)으로 돌릴 수 있다."""
    from clean_chat.sim import inputs
    from clean_chat.sim.server import run_module

    events: list[dict] = []
    simple = {f["key"]: f["default"] for f in inputs.FORMS["judge"]}
    run_module("judge", {"simple": simple}, events.append)
    result = events[-1]
    assert result["status"] == "ok", result["error"]
    speakers = {s["speaker"]: s for s in result["output"]["speakers"]}
    assert speakers["얼음땡"]["complaint_candidate"] and speakers["얼음땡"]["legal"][0]["charge"] == "모욕"
    assert speakers["불꽃남자"]["toward_me"] and speakers["달빛고양이"]["evidence"][0]["kind"] == "agree"


def test_train_validation_split_and_multiple_files(tmp_path):
    """학습 CSV 여러 개를 합치고(같은 문장은 한 번), test 행은 빼고, 유형 조합별로 검증용을 뗀다."""
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    a.write_text("text,harm_types,split\n" + "".join(f"정글 못하네 {i},blame,train\n" for i in range(20)), "utf-8")
    b.write_text(
        "text,harm_types,split\n정글 못하네 0,blame,train\n시험 문장,blame,test\n"
        + "".join(f"용 치자 {i},,train\n" for i in range(20)),
        "utf-8",
    )
    examples = train.load_examples([a, b])
    assert len(examples) == 40
    train_part, val_part = train.split_validation(examples, 0.2, seed=1)
    assert (
        len(train_part) == 32 and len(val_part) == 8 and sum(y[train.LABELS.index("blame")] for _, y in val_part) == 4
    )
    assert train.split_validation(examples[:4], 0.2, seed=1) == (examples[:4], [])  # 너무 적으면 떼지 않는다
    labels = ["profanity", "family_insult", "sexual_harassment", "blame", "instigation"]
    score, per = train.macro_f1(
        [[0, 0, 0, 1, 0], [0, 0, 0, 0, 0]], [[0, 0, 0, 0.9, 0], [0, 0, 0, 0.8, 0.1]], labels=labels
    )
    assert per == {"blame": pytest.approx(2 / 3)} and score == pytest.approx(2 / 3)  # 정답 없는 유형은 평균에서 제외


def test_public_data_kmhas_keeps_only_profanity_label(tmp_path):
    from clean_chat.modules.analyze import public_data

    src, out = tmp_path / "kmhas.txt", tmp_path / "stage1.csv"
    src.write_text(
        'document\tlabel\n욕설 댓글\t3\n"욕설 + 정치"\t2,3\n정치 댓글\t2\n평범한 댓글\t8\n', encoding="utf-8"
    )
    assert public_data.convert_kmhas(src, out, limit=4) == 4
    labels = dict(train.load_examples(out))
    profanity = train.LABELS.index("profanity")
    assert labels["욕설 + 정치"][profanity] == 1.0 and sum(labels["정치 댓글"]) == 0.0


def test_augmented_train_rows_do_not_leak_into_test():
    """보강 문장(train_aug.csv)은 모두 train 이고, 시험 문장과 겹치지 않는다."""
    base = evaluate.load_rows(FIXTURES / "analyze" / "labeled_parsed.csv", "test")
    aug = evaluate.load_rows(FIXTURES / "analyze" / "train_aug.csv")
    assert aug and {r["split"] for r in aug} == {"train"}
    assert not {r["text_norm"] for r in base} & {r["text_norm"] for r in aug}
    assert all(set(r["harm_types"].split("|")) - {""} <= set(train.LABELS) for r in aug)


def test_model_profanity_score_is_ignored(monkeypatch):
    """욕설은 규칙만 쓴다: 모델만 욕설이라고 한 문장은 정상, 규칙이 잡은 욕설은 그대로."""
    monkeypatch.setattr(model, "predict", lambda _t: {"profanity": 0.99, "blame": 0.1})
    monkeypatch.setattr(model, "version", lambda: "fake-ft-0.1")
    assert int(impl.run(_req("나이스 갱")).level) == 0
    out = impl.run(_req("아 시발 내가 실수함"))
    assert (int(out.level), out.scores) == (1, {"profanity": 0.9})


def test_champion_table_covers_official_list():
    """챔피언 표는 라이엇 공식 목록(Data Dragon 16.23.1 한국어, 173명 — 2026년 로크까지)과 개수가 같다."""
    from clean_chat.modules.analyze import champions

    official = set(champions.CHAMPION_ROLES) - set(champions._CANONICAL)  # 줄임말을 뺀 정식 이름
    assert len(official) == 173 and {"로크", "자헨", "유나라", "멜", "암베사"} <= official
    assert champions.roles_of("로크") == ("MIDDLE",) and champions.roles_of("자헨") == ("TOP", "JUNGLE")
    assert all(name in official for name in champions.ALIASES)  # 줄임말의 원형은 모두 표에 있다
    aliases = [a for names in champions.ALIASES.values() for a in names]
    assert len(aliases) == len(set(aliases)) and not set(aliases) & official  # 줄임말은 한 챔피언만 가리킨다


def test_champion_alias_is_resolved():
    from clean_chat.modules.analyze import champions

    assert champions.canonical("이즈") == "이즈리얼" and champions.canonical("카사") == "카이사"
    assert champions.names_of("케틀") == ("케이틀린", "케틀", "케이틀") and champions.roles_of("블츠") == ("UTILITY",)
    players = [Player(name="화자", champion="아리"), Player(name="불주먹", champion="이즈리얼")]
    assert impl.run(_req("이즈 트롤이냐", players=players)).target == "불주먹"  # 줄임말로 불러도 닉네임을 찾는다
    assert impl.run(_req("이즈를 왜 못 잡냐 정글", players=players)).target != "불주먹"  # "이즈를" 은 잡을 상대(목적어)


def test_champion_name_is_target_without_roster():
    """명단(players)을 모르면 문장에서 부른 챔피언의 정식 이름을 대상으로 둔다. 일상 낱말과 겹치는 이름은 보지 않는다."""
    out = impl.run(_req("블츠 트롤이냐"))
    assert (out.target, int(out.level)) == ("블리츠크랭크", 2)
    assert impl.run(_req("자헨 트롤이냐")).target == "자헨"
    assert impl.run(_req("진 거 같다 트롤 때문에")).target is None  # "진" 은 챔피언 이름이기도 하다
    assert int(impl.run(_req("이즈 궁 좋았어")).level) == 0


def test_champion_eval_draft_does_not_overlap_train():
    """챔피언 이름 시험 초안은 모두 test 이고, 학습 문장과 겹치지 않는다."""
    draft = evaluate.load_rows(FIXTURES / "analyze" / "champion_eval_draft.csv")
    assert draft and {r["split"] for r in draft} == {"test"}
    train_texts = {
        text
        for text, _ in train.load_examples([FIXTURES / "analyze" / n for n in ("labeled_parsed.csv", "train_aug.csv")])
    }
    assert not {r["text_norm"] for r in draft} & train_texts


def test_champion_mentioned_mid_sentence_is_not_target():
    """명단이 없을 때 문장 중간의 챔피언은 부른 것이 아니다 → 대상 없는 욕설은 L1 에 머문다."""
    out = impl.run(_req("아 시발 리신 발차기에 또 맞았네"))
    assert (out.target, int(out.level)) == (None, 1)
    assert impl.run(_req("상대 리신 트롤이냐")).target == "리신"
    assert impl.run(_req("다들 리신 신고해")).target == "리신"  # 몰이는 "다들"·"얘들아" 뒤에 이름이 온다


def test_train_skips_abusive_rows_without_type(tmp_path):
    """악성(L2 이상)인데 유형 코드가 없는 행(협박 등)은 "정상"으로 배우지 않게 학습에서 뺀다."""
    path = tmp_path / "t.csv"
    path.write_text(
        "text,level,harm_types,split\n너 집 주소 안다,3,,train\n용 치자,0,,train\n정글 못하네,2,blame,train\n", "utf-8"
    )
    assert [t for t, _ in train.load_examples(path)] == ["용 치자", "정글 못하네"]


def test_judge_games_are_well_formed():
    """게임 단위 대화 데이터: 10명(5:5), 상대 팀은 전체 채팅만, 정답은 명단 안의 유저, 고소 후보는 나를 향한 것."""
    games = judge_evaluate.load_games(FIXTURES / "analyze" / "judge_games.jsonl")
    assert len(games) >= 50 and {g["split"] for g in games} == {"train", "test"}
    for g in games:
        team = {p["name"]: p["team"] for p in g["players"]}
        assert len(team) == 10 and sum(t == "ORDER" for t in team.values()) == 5, g["id"]
        assert [p["name"] for p in g["players"] if p["is_me"]] == [g["my_name"]], g["id"]
        assert all(m["speaker"] in team for m in g["messages"]), g["id"]
        assert all(m["channel"] == "all" for m in g["messages"] if team[m["speaker"]] == "CHAOS"), g["id"]
        for name, label in g["labels"].items():
            assert name in team and name != g["my_name"], g["id"]
            assert not label.get("complaint") or (label["report"] and label["toward_me"]), g["id"]
    assert sum(len(judge_evaluate.transcripts(g)) for g in games) == 9 * len(games)  # 유저별로 모으면 한 판에 9명


def test_judge_report_needs_more_than_one_rough_remark():
    """욕설 없는 거친 말 한 번은 신고 권고가 아니다. 반복되거나 욕설이 섞이면 권고한다."""
    once = judge.judge(
        judge.JudgeRequest(messages=[_chat(0, 0, "불꽃남자", "정글 뭐하냐")], players=ROSTER, my_name="나")
    )
    assert [(s.speaker, s.report) for s in once.speakers] == [("불꽃남자", False)]
    twice = [_chat(0, 0, "불꽃남자", "정글 뭐하냐"), _chat(1, 600, "불꽃남자", "정글 트롤이냐")]
    assert judge.judge(judge.JudgeRequest(messages=twice, players=ROSTER, my_name="나")).speakers[0].report
    swear = [_chat(0, 0, "불꽃남자", "정글 개새끼")]
    assert judge.judge(judge.JudgeRequest(messages=swear, players=ROSTER, my_name="나")).speakers[0].report


def test_judge_context_agreement_with_words_and_defender():
    """ "ㅇㅈ 정글 차이 심하네" 처럼 말이 붙은 맞장구는 가담, 공격하던 사람에게 하는 "그만해라" 는 가해가 아니다."""
    messages = [
        _chat(0, 0, "불꽃남자", "정글 트롤이냐"),
        _chat(1, 5, "달빛고양이", "ㅇㅈ 정글 차이 심하네"),
        _chat(2, 9, "밤하늘별", "징크스 그만해라 트롤 아니야"),
    ]
    result = judge.judge(judge.JudgeRequest(messages=messages, players=ROSTER, my_name="나"))
    by_name = {s.speaker: s for s in result.speakers}
    assert by_name["달빛고양이"].report and by_name["달빛고양이"].evidence[0].kind == "agree"
    assert "밤하늘별" not in by_name
    assert by_name["불꽃남자"].total_messages == 1


def test_judge_model_document_marks_target_and_me():
    """judge 모델 입력: 판단 대상의 말은 ▶, 내 말은 나(...), 길면 대상에서 먼 다른 사람의 말부터 뺀다."""
    messages = [
        _chat(0, 0, "밤하늘별", "다들 화이팅"),
        _chat(1, 5, "불꽃남자", "서폿 뭐하냐"),
        _chat(2, 9, "나", "미안 와드 박을게"),
        _chat(3, 12, "얼음땡", "ez", channel="all"),
    ]
    doc = judge_model.build_document(messages, ROSTER, "나", "불꽃남자")
    assert "▶ 징크스: 서폿 뭐하냐" in doc and "나(쓰레쉬): 미안 와드 박을게" in doc and "· 가렌" in doc
    short = judge_model.build_document(messages, ROSTER, "나", "불꽃남자", max_chars=40)
    assert "▶ 징크스" in short and "나(쓰레쉬)" in short and "다들 화이팅" not in short
    assert judge_model.speakers(messages, "나") == ["밤하늘별", "불꽃남자", "얼음땡"]
    assert judge_model.predict(messages, ROSTER, "나") == {}  # 모델이 없으면 빈 값 → 규칙만


def test_judge_merges_model_scores(monkeypatch):
    """hybrid: 규칙으로는 근거가 없어도 모델이 신고 권고라고 하면 권고한다. rules 는 모델을 쓰지 않는다."""
    messages = [_chat(0, 0, "불꽃남자", "탑 0/6/0 ㅋㅋ"), _chat(1, 30, "밤하늘별", "다들 화이팅")]
    fake = {"불꽃남자": {"report": 0.91, "complaint": 0.02}, "밤하늘별": {"report": 0.03, "complaint": 0.01}}
    monkeypatch.setattr(judge_model, "predict", lambda *_a: fake)
    monkeypatch.setattr(judge_model, "version", lambda: "fake-judge-0.1")
    req = judge.JudgeRequest(messages=messages, players=ROSTER, my_name="나")
    hybrid = judge.judge(req)  # 기본 = hybrid
    assert [(s.speaker, s.report, s.complaint_candidate) for s in hybrid.speakers] == [("불꽃남자", True, False)]
    assert hybrid.speakers[0].model_scores["report"] == 0.91 and hybrid.version.endswith("+fake-judge-0.1")
    assert judge.judge(req, mode="rules").speakers == []


def test_judge_evaluate_counts_users(tmp_path):
    game = {
        "id": "T1", "split": "test", "my_name": "나",
        "players": [p.model_dump() for p in ROSTER],
        "messages": [{"t": 0, "channel": "team", "speaker": "불꽃남자", "text": "서폿 개새끼", "text_norm": "서폿 개새끼"}],
        "labels": {"불꽃남자": {"report": True, "complaint": False, "toward_me": True, "targets": ["나"]}},
    }  # fmt: skip
    result = judge_evaluate.evaluate([game])
    assert (result["users"], result["report"]["accuracy"], result["report"]["recall"]) == (len(ROSTER) - 1, 1.0, 1.0)
    assert result["latency_sec"]["mean"] >= 0 and not result["errors"]


def test_judge_follow_up_threat_and_untargeted_swearing():
    """흐름으로 이어지는 말: 나를 공격하던 사람의 협박은 고소 후보, 대상을 생략한 욕설도 같은 대상으로 쌓인다."""
    threat = [_chat(0, 0, "불꽃남자", "서폿 뭐하냐"), _chat(1, 60, "불꽃남자", "끝나고 보자 어디 사는지 찾아낸다")]
    who = judge.judge(judge.JudgeRequest(messages=threat, players=ROSTER, my_name="나")).speakers[0]
    assert who.complaint_candidate and who.evidence[1].level == 3 and who.evidence[1].toward_me
    swearing = [
        _chat(0, 0, "불꽃남자", "서폿 개새끼"),
        _chat(1, 100, "불꽃남자", "꺼져 그냥"),
        _chat(2, 200, "불꽃남자", "존나 답답하네"),
        _chat(4, 260, "불꽃남자", "병신같네 진짜"),
        _chat(3, 5000, "불꽃남자", "아 시발 내 실수"),  # 자책이고 한참 뒤 → 쌓이지 않는다
    ]
    who = judge.judge(judge.JudgeRequest(messages=swearing, players=ROSTER, my_name="나")).speakers[0]
    assert len(who.evidence) == 4 and who.complaint_candidate
    alone = [_chat(0, 0, "밤하늘별", "아 시발 렉"), _chat(1, 9, "밤하늘별", "바론 죽인다 가자")]
    assert judge.judge(judge.JudgeRequest(messages=alone, players=ROSTER, my_name="나")).speakers == []


def test_threat_is_l3_and_game_talk_is_not(monkeypatch):
    """협박(ADR-0021): 게임 밖 현실의 해악을 말하면 threat · L3. 게임 안의 "죽인다"·"찾아가서 잡자" 는 아니다."""
    out = impl.run(_req("정글 너 집 주소 안다 찾아간다"))
    assert (int(out.level), [t.value for t in out.harm_types]) == (3, ["threat"])
    assert int(impl.run(_req("끝나고 보자 어디 사는지 알아낸다")).level) == 3  # 대상 낱말이 없어도 L3
    for clean in ("바론 죽인다 다 와", "상대 정글 찾아가서 잡자", "원딜 먼저 죽여 그럼 이긴다"):
        assert int(impl.run(_req(clean)).level) == 0, clean
    monkeypatch.setattr(model, "predict", lambda _t: {"threat": 0.93})  # 사전에 없는 협박은 모델 점수로
    monkeypatch.setattr(model, "version", lambda: "fake-ft")
    out = impl.run(_req("미드 만나면 반 죽여놓는다"))
    assert (int(out.level), out.scores) == (3, {"threat": 0.93})


def test_threat_gets_its_own_legal_review():
    """나를 향한 협박 → 고소 후보, 죄목은 협박(형법 제283조)으로 따로 점검한다."""
    messages = [_chat(0, 0, "불꽃남자", "서폿 뭐하냐"), _chat(1, 60, "불꽃남자", "끝나고 보자 집 주소 안다")]
    who = judge.judge(judge.JudgeRequest(messages=messages, players=ROSTER, my_name="나")).speakers[0]
    assert who.complaint_candidate and "threat" in [t.value for t in who.harm_types]
    charges = {r.charge: r for r in who.legal}
    assert charges["협박"].statute == "형법 제283조"
    assert [(r.name, r.status) for r in charges["협박"].requirements] == [
        ("해악의 고지", "충족"),
        ("상대방에게 도달", "충족"),
        ("공포심을 일으킬 정도", "불명"),
    ]


def test_no_abusive_row_is_left_without_type():
    """협박 유형이 생겼으니 악성(L2 이상)인데 유형이 빈 학습·시험 행은 없어야 한다."""
    for name in ("labeled_parsed.csv", "train_aug.csv", "champion_eval_draft.csv"):
        rows = evaluate.load_rows(FIXTURES / "analyze" / name)
        assert not [r["text"] for r in rows if r["level"] in ("2", "3") and not r["harm_types"].strip()], name


def test_threat_criteria_three_tiers(monkeypatch):
    """협박 기준: ① 명시적(현실 표지) = 문장만으로 L3 · ② 모델 = 게임 표지가 없을 때만 · ③ 암시적 = 흐름(judge)에서만."""
    monkeypatch.setattr(model, "predict", lambda _t: {"threat": 0.97})  # 모델이 무엇이든 협박이라고 하는 상황
    monkeypatch.setattr(model, "version", lambda: "fake-ft")
    for game_call in (
        "다음 용 때 다 죽인다 모여",
        "상대 원딜 찾아가서 죽이자 혼자 있음",
        "제드 보이면 바로 물어서 죽여",
    ):
        assert int(impl.run(_req(game_call)).level) == 0, game_call  # ② 게임 표지가 있으면 모델 점수를 받지 않는다
    assert int(impl.run(_req("미드 니 인스타 찾았다 다 뿌려줄게")).level) == 3  # ② 게임 표지 없음 → 모델 점수로 협박
    assert int(impl.run(_req("다음에 오프라인에서 보면 진짜 때린다")).level) == 3  # "오프라인"은 게임의 "라인"이 아니다
    assert (
        int(impl.run(_req("용 한타 지면 집 주소 안다 찾아간다")).level) == 3
    )  # ① 명시적 협박은 게임 낱말이 섞여도 협박


def test_veiled_threat_needs_context():
    """③ "끝나고 보자"·"각오해라" 는 문장만으로는 협박이 아니고, 그 사람을 공격하던 유저가 이어서 했을 때만 협박이다."""
    assert int(impl.run(_req("끝나고 보자 누가 딜량 높은지 ㅋㅋ")).level) == 0
    assert "threat" not in [t.value for t in impl.run(_req("서폿 끝나고 보자")).harm_types]
    alone = [_chat(0, 0, "밤하늘별", "끝나고 보자 ㅋㅋ 한 판 더")]
    assert judge.judge(judge.JudgeRequest(messages=alone, players=ROSTER, my_name="나")).speakers == []
    after_abuse = [_chat(0, 0, "불꽃남자", "서폿 개새끼"), _chat(1, 120, "불꽃남자", "끝나고 보자 각오해라")]
    who = judge.judge(judge.JudgeRequest(messages=after_abuse, players=ROSTER, my_name="나")).speakers[0]
    assert who.complaint_candidate and who.evidence[1].level == 3 and "threat" in [t.value for t in who.harm_types]
    assert "threat" in [t.value for t in who.evidence[1].harm_types] and who.evidence[1].toward_me


def test_threat_eval_draft_does_not_overlap_train():
    draft = evaluate.load_rows(FIXTURES / "analyze" / "threat_eval_draft.csv")
    assert len(draft) >= 40 and {r["split"] for r in draft} == {"test"}
    train_texts = {
        t for t, _ in train.load_examples([FIXTURES / "analyze" / n for n in ("labeled_parsed.csv", "train_aug.csv")])
    }
    assert not {r["text_norm"] for r in draft} & train_texts


def test_named_person_beats_lane_word():
    """이름으로 부른 사람이 대상이다. 문장 속 포지션 낱말이 라인 이름일 뿐일 때(말한 사람 자신의 라인 등)."""
    team = [("화자", "티모"), ("불주먹", "세주아니"), ("가운데", "아리"), ("아래", "징크스"), ("도우미", "쓰레쉬")]
    players = [Player(name=n, champion=c, team="ORDER") for n, c in team]
    assert impl.run(_req("세주 너 일부러 탑 안 오지 트롤이냐", players=players)).target == "불주먹"
    assert impl.run(_req("정글 트롤이냐", players=players)).target == "불주먹"  # 포지션 낱말만 있으면 그대로 포지션으로
    assert impl.run(_req("정글 트롤이냐 아리 좀 봐줘라", players=players)).target == "불주먹"  # 먼저 나온 쪽이 대상


def test_eval_sets_do_not_overlap_training_sentences():
    """시험·검증 세트(기존 60, 챔피언, 협박, 조정용, 봉인)는 서로 다른 파일의 학습 문장과 겹치지 않는다."""
    folder = FIXTURES / "analyze"
    train_texts = {
        t
        for t, _ in train.load_examples(
            [folder / n for n in ("labeled_parsed.csv", "train_aug.csv", "train_indep.csv")]
        )
    }
    assert len(train_texts) >= 2300
    for name in ("champion_eval_draft.csv", "threat_eval_draft.csv", "dev_eval.csv", "blind_eval.csv"):
        rows = evaluate.load_rows(folder / name)
        assert rows and {r["split"] for r in rows} == {"test"}, name
        assert not {r["text_norm"].strip() for r in rows} & train_texts, name
    held_out = evaluate.load_rows(folder / "labeled_parsed.csv", "test")
    assert not {r["text_norm"].strip() for r in held_out} & train_texts


def test_judge_blind_games_are_separate_from_training_games():
    train_games = judge_evaluate.load_games(FIXTURES / "analyze" / "judge_games.jsonl")
    blind = judge_evaluate.load_games(FIXTURES / "analyze" / "judge_blind_games.jsonl")
    assert len(blind) >= 150 and {g["split"] for g in blind} == {"blind"}
    assert not {g["id"] for g in blind} & {g["id"] for g in train_games}
    seen = {m["text"] for g in train_games for m in g["messages"] if len(m["text"]) >= 12}
    overlap = [m["text"] for g in blind for m in g["messages"] if m["text"] in seen]
    lines = sum(len(g["messages"]) for g in blind)
    assert len(overlap) <= lines * 0.005, len(overlap)  # 같은 문장은 0.5% 이하 (흔한 콜이 우연히 겹치는 정도)


def test_implied_target_for_champion_mid_sentence_and_second_person():
    """명단이 없을 때: 문장 중간·끝의 챔피언은 비난이거나 사람을 가리키는 욕설이 붙었을 때만 대상, "너/니" 는 사람을 향한 말."""
    out = impl.run(_req("ㅂㅅ 티모 꺼져", "병신 티모 꺼져", ("lexicon:ㅂㅅ",)))
    assert (out.target, int(out.level)) == ("티모", 2)
    assert int(impl.run(_req("다같이 리신 신고 ㄱ")).level) == 2  # 정치질 + 문장 중간의 챔피언
    assert (lambda o: (o.target, int(o.level)))(impl.run(_req("아 시발 블츠 그랩에 또 끌렸네"))) == (None, 1)  # 혼잣말
    out = impl.run(_req("너 진짜 트롤이냐"))
    assert (out.target, int(out.level)) == (None, 2)  # 누구인지는 모르지만 사람을 향한 말
    assert int(impl.run(_req("너 덕분에 살았다")).level) == 0


def test_weights_repo_ids_and_missing_owner(monkeypatch):
    """가중치 저장소 이름: 계정/clean-chat-analyze-<모델>. 계정을 모르면 알기 쉬운 오류."""
    from clean_chat.modules.analyze import weights

    assert weights.repo_id("classifier", "someone") == "someone/clean-chat-analyze-classifier"
    monkeypatch.setenv(weights.OWNER_ENV, "team")
    assert weights.repo_id("judge") == "team/clean-chat-analyze-judge"
    monkeypatch.delenv(weights.OWNER_ENV)
    monkeypatch.setattr(weights, "DEFAULT_OWNER", "")
    with pytest.raises(ValueError):
        weights.repo_id("judge")
    assert set(weights.MODELS) == {"classifier", "judge"}
    # 앱은 분류 모델을 ONNX 로만 돌린다 (torch 가중치는 받지 않는다). judge 는 시뮬레이터 전용 torch.
    assert "model.onnx" in weights.FILES and "model.safetensors" not in weights.FILES
    assert "model.safetensors" in weights.RUN_FILES["judge"]


@pytest.mark.parametrize(
    ("text", "level", "harm"),
    [
        # 실제 게임 테스트에서 놓친 말 (2026-11-28). 이름이 없어도 사람에게 하는 말은 L2 이상으로 본다.
        ("볍신련아", 2, "profanity"),
        ("법신련아", 2, "profanity"),  # 화면에서 볍신을 법신으로 읽음
        ("개색기야", 2, "profanity"),
        ("멍청아", 2, "profanity"),
        ("접어라", 2, "blame"),
        ("겜 접어라", 2, "blame"),
        ("tlgkf", 1, "profanity"),  # 화면에서 tlqkf 를 tlgkf 로 읽음 (대상 없는 욕설)
        ("니엄마창년", 3, "family_insult"),
        ("니엄마보지", 3, "sexual_harassment"),
        ("니애미", 3, "family_insult"),
    ],
)
def test_slang_and_addressed_insults_from_real_game(text, level, harm):
    from clean_chat.core.schemas import AnalyzeRequest, ChatMessage
    from clean_chat.modules.analyze import impl
    from clean_chat.modules.parse.normalization import normalize

    norm, hints = normalize(text)
    message = ChatMessage(
        id="m",
        ts=0,
        source="ocr",
        channel="all",
        speaker="얼음땡",
        champion="멜",
        text=text,
        text_norm=norm,
        hints=hints,
        raw=text,
    )
    analysis = impl.run(AnalyzeRequest(message=message, history=[], players=[]))
    assert int(analysis.level) == level and harm in [h.value for h in analysis.harm_types]


@pytest.mark.parametrize(
    "text", ["접어둔 종이", "멍청하게 죽었네 내가", "새끼 고양이 귀엽다", "훈련아 가자", "바론 가자 바론"]
)
def test_ordinary_sentences_are_not_treated_as_addressed_insults(text):
    from clean_chat.core.schemas import AnalyzeRequest, ChatMessage
    from clean_chat.modules.analyze import impl
    from clean_chat.modules.parse.normalization import normalize

    norm, hints = normalize(text)
    message = ChatMessage(
        id="m",
        ts=0,
        source="ocr",
        channel="all",
        speaker="얼음땡",
        champion="멜",
        text=text,
        text_norm=norm,
        hints=hints,
        raw=text,
    )
    assert int(impl.run(AnalyzeRequest(message=message, history=[], players=[])).level) <= 1


@pytest.mark.parametrize(
    ("text", "level", "spans"),
    [
        ("숟가락아 와드 좀 박아", 1, ["숟가락"]),  # 얕잡아 부르는 말만 → 약한 욕설 (그 낱말만 지운다)
        ("도구야 궁 체크", 1, ["도구"]),
        ("백정 뭐하냐", 2, ["백정"]),  # 비난과 함께면 그 포지션 사람을 향한 말
        ("탑신병자 또 죽네 뭐하냐", 2, ["탑신병자"]),
        ("개못하쥬", 2, []),  # 이름이 없어도 남을 깎아내리는 말
        ("죽인다", 2, []),
        ("상체 뭐하냐", 2, []),
    ],
)
def test_position_slurs_and_untargeted_insults(text, level, spans):
    out = impl.run(_req(text))
    assert int(out.level) == level and out.profanity_spans == spans


@pytest.mark.parametrize(
    "text", ["내가 개못하네", "바론 죽인다 다 와", "레벨 차이 나네", "상체 운동 해야지 ㅋㅋ", "서폿 와드 좀 박아줘"]
)
def test_self_talk_game_talk_and_plain_references_stay_clean(text):
    assert int(impl.run(_req(text)).level) == 0, text


@pytest.mark.parametrize(
    ("text", "feedback"),
    [
        # 욕설에 섞인 게임 지시는 피드백 조각으로 뽑는다 (욕설·부른 대상·군말은 뺀다).
        ("서폿 병신아 시야 좀 잡아라", "시야 좀 잡아라"),
        ("원딜 병신아 cs 먹지마", "cs 먹지마"),
        ("탑 병신아 라인 밀지마", "라인 밀지마"),
        ("미드 병신아 타워 치지마", "타워 치지마"),
        ("정글 병신아 장로 쳐", "장로 쳐"),
        ("정글 병신아 유충 쳐", "유충 쳐"),
        ("서폿 병신아 스펠 체크 좀", "스펠 체크 좀"),
        ("미드 병신아 궁 체크해", "궁 체크해"),
        ("정글 병신아 바위게 잡자", "바위게 잡자"),
        ("탑 병신아 라인 프리징 해", "라인 프리징 해"),
        ("백정 병신아 바론 잡자", "바론 잡자"),
    ],
)
def test_feedback_is_extracted_from_abusive_instructions(text, feedback):
    out = impl.run(_req(text))
    assert int(out.level) >= 2 and out.feedback_spans == [feedback]
    assert "병신" in out.profanity_spans


# ── 게임 안의 "죽인다" 와 실제 협박 구분 (실측 점검 2026-11-28) ─────────────────────────
def _fake_threat_model(monkeypatch, score: float = 0.97) -> None:
    """모델이 "죽인다" 가 든 문장을 모두 협박이라고 하는 상황 (실측에서 "탑 내가 죽인다 ㄱㄱ" 가 그랬다)."""
    monkeypatch.setattr(model, "predict", lambda t: {"threat": score} if "죽" in t else {})
    monkeypatch.setattr(model, "version", lambda: "fake-ft")


def _analyze(messages: list[ChatMessage]) -> Analysis:
    """마지막 메시지를 앞 대화와 함께 분석한다 (실시간 파이프라인처럼)."""
    return impl.run(AnalyzeRequest(message=messages[-1], history=messages[:-1], players=ROSTER))


@pytest.mark.parametrize("text", ["탑 내가 죽인다 ㄱㄱ", "미드 죽인다 고고", "바텀 둘 다 죽인다 가자"])
def test_game_call_with_kill_word_is_clean(monkeypatch, text):
    _fake_threat_model(monkeypatch)
    assert int(_analyze([_chat(0, 0, "얼음땡", text, channel="all")]).level) == 0, text


def test_kill_word_alone_is_blame_not_threat(monkeypatch):
    """문장 하나로는 게임 안의 말일 수 있다 → 비난(L2)까지만. 협박(L3)·고소 후보로 올리지 않는다."""
    _fake_threat_model(monkeypatch)
    out = _analyze([_chat(0, 0, "얼음땡", "너 진짜 죽인다", channel="all")])
    assert int(out.level) == 2 and "threat" not in [t.value for t in out.harm_types]


@pytest.mark.parametrize(
    "text", ["실제로 찾아가서 죽인다", "겜 끝나면 찾아가서 죽인다", "학교 앞에서 패 버린다", "주소 땄다 기다려"]
)
def test_real_world_marker_makes_it_a_threat_alone(text):
    out = _analyze([_chat(0, 0, "얼음땡", text, channel="all")])
    assert int(out.level) == 3 and "threat" in [t.value for t in out.harm_types], text


@pytest.mark.parametrize("text", ["너 진짜 죽인다", "찾아가서 죽여버린다", "끝나고 보자"])
def test_kill_word_after_attacking_someone_is_a_threat(text):
    """같은 화자가 바로 앞에서 누군가를 공격하고 있었으면 협박. 대상은 그 공격의 대상."""
    talk = [
        _chat(0, 0, "불꽃남자", "서폿 병신아 뭐하냐"),
        _chat(1, 5, "달빛고양이", "그만해"),
        _chat(2, 10, "불꽃남자", text),
    ]
    out = _analyze(talk)
    assert int(out.level) == 3 and "threat" in [t.value for t in out.harm_types], text
    # 대상: "너" 는 바로 앞에 말한 사람(달빛고양이)으로 본다. 부른 사람이 없으면 앞선 공격의 대상(서폿 = 나)
    assert out.target in {"달빛고양이", "나"}
    assert _analyze([talk[0], talk[2]]).target == "나"
    # 공격 전에 다른 사람이 말했어도, 공격 뒤에 끼어든 사람이 없으면 공격받던 사람이 대상
    earlier = [_chat(9, -5, "달빛고양이", "용 먹자"), talk[0], talk[2]]
    assert _analyze(earlier).target == "나"


def test_kill_word_after_someone_else_attacked_is_not_a_threat():
    talk = [_chat(0, 0, "불꽃남자", "서폿 병신아 뭐하냐"), _chat(1, 10, "달빛고양이", "너 진짜 죽인다")]
    assert int(_analyze(talk).level) == 2


def test_kill_word_long_after_the_attack_is_not_a_threat():
    talk = [_chat(0, 0, "불꽃남자", "서폿 병신아 뭐하냐"), _chat(1, 1000, "불꽃남자", "너 진짜 죽인다")]
    assert int(_analyze(talk).level) == 2


def test_game_call_after_attacking_is_still_game_talk():
    talk = [_chat(0, 0, "불꽃남자", "서폿 병신아 뭐하냐"), _chat(1, 10, "불꽃남자", "바론 죽인다 다 와")]
    assert int(_analyze(talk).level) == 0


def test_judge_kill_word_needs_earlier_attack(monkeypatch):
    """judge (끝난 게임 전체): "죽인다" 만으로는 고소 후보가 아니고, 공격하던 사람이 이어서 하면 협박."""
    _fake_threat_model(monkeypatch)
    alone = [_chat(0, 0, "얼음땡", "탑 내가 죽인다 ㄱㄱ", channel="all"), _chat(1, 9, "얼음땡", "너 진짜 죽인다")]
    for who in judge.judge(judge.JudgeRequest(messages=alone, players=ROSTER, my_name="나")).speakers:
        assert not who.complaint_candidate
    after = [_chat(0, 0, "불꽃남자", "서폿 병신아 뭐하냐"), _chat(1, 30, "불꽃남자", "너 진짜 죽인다")]
    who = judge.judge(judge.JudgeRequest(messages=after, players=ROSTER, my_name="나")).speakers[0]
    assert who.complaint_candidate and "threat" in [t.value for t in who.harm_types]
