"""실제 모듈 호출 경계에서 화자별 원문과 고소장 혐의의 일관성을 검사한다."""

import pytest

from clean_chat.core.charges import CHARGE_CATALOG, ChargeId
from clean_chat.core.game import PostGameBatch
from clean_chat.core.modules import ModuleSet
from clean_chat.core.schemas import HarmType, ReportDraft, ReportKind, ReportRequest, Source
from helpers import fixture_pairs


def test_catalog_includes_unapplied_charges():
    assert set(CHARGE_CATALOG) == set(ChargeId)
    assert len(CHARGE_CATALOG) == 7
    assert all(info.name and info.description for info in CHARGE_CATALOG.values())


def test_batch_uses_same_charges_and_original_evidence_for_generator_and_reader():
    req, _ = fixture_pairs("report")[-1]
    seen = {}

    def generate(item):
        seen[item.kind, item.speaker] = (item.applied_charge_ids, item.evidence)
        return ReportDraft(
            kind=item.kind, speaker=item.speaker, text="예시", incident_ids=[m.id for m in item.evidence]
        )

    result = PostGameBatch(ModuleSet({"report": generate})).run(req.session)
    for draft in [*result.reports, *result.complaints]:
        assert seen[draft.kind, draft.speaker] == (draft.applied_charge_ids, draft.evidence)
        assert all(msg.speaker == draft.speaker for msg in draft.evidence)
        assert [msg.id for msg in draft.evidence] == draft.incident_ids
        if draft.kind == ReportKind.REPORT:
            assert draft.applied_charge_ids == ()
    complaint = result.complaints[0]
    assert complaint.applied_charge_ids == (ChargeId.INSULT,)
    assert complaint.evidence[0].text != complaint.evidence[0].text_norm
    assert complaint.evidence[0].raw == next(i.msg.raw for i in req.session.incidents if i.msg.id == "L5")
    assert ReportDraft.model_validate_json(complaint.model_dump_json()) == complaint


def test_evidence_selection_does_not_set_charges_or_allow_other_speakers():
    req, _ = fixture_pairs("report")[-1]
    inc = next(i for i in req.session.incidents if i.msg.id == "L5")
    older = inc.model_copy(deep=True)
    older.msg.id = older.analysis.msg_id = older.decision.msg_id = "earlier"
    older.msg.ts -= 1
    older.analysis.harm_types = [HarmType.THREAT, HarmType.THREAT, HarmType.SEXUAL_HARASSMENT]
    req.session.incidents.append(older)
    for unwanted in ("self", "other", "not-candidate"):
        extra = inc.model_copy(deep=True)
        extra.msg.id = extra.analysis.msg_id = extra.decision.msg_id = unwanted
        if unwanted == "self":
            extra.msg.source = Source.SELF_INPUT
        elif unwanted == "other":
            extra.msg.speaker = "별도 화자"
        else:
            extra.decision.complaint_candidate = False
        req.session.incidents.append(extra)
    assert [m.id for m in req.evidence] == ["earlier", "L5"]
    expected = (ChargeId.SEXUAL_MESSAGE, ChargeId.THREAT, ChargeId.INSULT)
    assert req.applied_charge_ids == expected
    req.evidence_ids = ("L5",)
    assert [m.id for m in req.evidence] == ["L5"]
    assert req.applied_charge_ids == expected
    req.evidence_ids = ()
    assert req.evidence == () and req.applied_charge_ids == expected
    assert (
        ReportRequest.model_validate(req.model_dump() | {"applied_charge_ids": ["privacy"]}).applied_charge_ids
        == expected
    )


def test_no_matching_harm_and_legacy_draft_have_no_charges():
    req, legacy = fixture_pairs("report")[-1]
    for inc in req.session.incidents:
        inc.analysis.harm_types = [HarmType.BLAME, HarmType.PROFANITY]
    assert req.applied_charge_ids == ()
    old = ReportDraft.model_validate(legacy.model_dump(exclude={"applied_charge_ids", "evidence"}))
    assert old.evidence == old.applied_charge_ids == ()


def test_module_cannot_attach_an_unselected_incident():
    req, draft = fixture_pairs("report")[-1]
    req.evidence_ids = ()
    with pytest.raises(ValueError, match="첨부 대상"):
        ModuleSet({"report": lambda item: draft}).run("report", req)
