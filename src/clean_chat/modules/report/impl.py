"""게임 종료 후 신고 문구와 고소장 초안을 만든다 (ADR-0007, ADR-0008)."""

from __future__ import annotations

import logging
import os
from collections import Counter
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

from clean_chat.core.config import resolve_repo_path, settings
from clean_chat.core.schemas import Channel, HarmType, Incident, ReportDraft, ReportKind, ReportRequest

logger = logging.getLogger(__name__)
KST = timezone(timedelta(hours=9))
HARM_LABELS = {
    HarmType.PROFANITY: "욕설",
    HarmType.FAMILY_INSULT: "패드립",
    HarmType.SEXUAL_HARASSMENT: "성희롱",
    HarmType.BLAME: "비난",
    HarmType.INSTIGATION: "정치질",
    HarmType.THREAT: "협박",
}
COMPLAINT_DESCRIPTIONS = {
    HarmType.PROFANITY: "비속어를 사용한 표현",
    HarmType.FAMILY_INSULT: "가족을 언급한 비하 표현",
    HarmType.SEXUAL_HARASSMENT: "성적 발언으로 분류된 표현",
    HarmType.BLAME: "상대를 비난하거나 비하하는 표현",
    HarmType.INSTIGATION: "특정 참가자에 대한 비난을 유도하는 표현",
    HarmType.THREAT: "게임 밖에서 해악을 가하겠다고 고지하는 표현",
}
CHANNEL_LABELS = {Channel.ALL: "전체 채팅", Channel.TEAM: "팀 채팅", Channel.UNKNOWN: "채널 미확인 채팅"}


def run(req: ReportRequest) -> ReportDraft:
    """대상 화자의 정책 플래그에 따라 원문과 증거 ID를 시간순으로 모은다."""
    complaint = req.kind == ReportKind.COMPLAINT
    incidents = sorted(
        (
            incident
            for incident in req.session.incidents
            if incident.msg.speaker == req.speaker
            and (incident.decision.complaint_candidate if complaint else incident.decision.report)
        ),
        key=lambda incident: incident.msg.ts,
    )
    draft = ReportDraft(
        kind=req.kind, speaker=req.speaker, text="", incident_ids=[incident.msg.id for incident in incidents]
    )
    if not complaint:
        draft.text = "\n".join(
            [f"신고 대상: {req.speaker}", f"사유: 언어 폭력 {len(incidents)}건", *map(_format_line, incidents)]
        )
        return draft

    draft.text = _summarize(incidents)
    if incidents:
        try:
            draft.pdf_path = _render_pdf(
                _fill_template(req, incidents, draft.text), req.output_dir or settings.complaint_output_dir, req.speaker
            )
        except Exception:
            # PDF 저장에 실패해도 사건 경위와 증거 ID는 결과 화면에 돌려준다.
            logger.warning("고소장 PDF를 생성하지 못했습니다.")
    return draft


def _timestamp(ts: float) -> str:
    return datetime.fromtimestamp(ts, KST).strftime("%Y-%m-%d %H:%M:%S")


def _format_line(incident: Incident) -> str:
    labels = ", ".join(HARM_LABELS[harm] for harm in incident.analysis.harm_types)
    suffix = f" ({labels})" if labels else ""
    return f"[{_timestamp(incident.msg.ts)}] {incident.msg.text}{suffix}"


def _summarize(incidents: list[Incident]) -> str:
    if not incidents:
        return "고소장 초안에 포함할 채팅 기록이 없습니다."

    counts = Counter(
        (CHANNEL_LABELS[incident.msg.channel], tuple(sorted(set(incident.analysis.harm_types))))
        for incident in incidents
    )
    facts = []
    for (channel, harms), count in counts.items():
        labels = ", ".join(COMPLAINT_DESCRIPTIONS[harm] for harm in harms) or "구체적 분류 미확인"
        facts.append(f"{channel}에서 {labels}에 해당하는 것으로 분류된 메시지 {count}건")
    fallback = f"게임 중 피고소인이 작성한 기록 중 {' 및 '.join(facts)}이 확인됩니다."

    model = os.getenv("LLM_MODEL", "").strip()
    api_key = os.getenv("LLM_API_KEY", "").strip()
    if not model.startswith("gemini/") or not api_key:
        return fallback

    # 원문과 식별 정보는 로컬 양식에만 사용한다.
    try:
        from litellm import completion

        result = completion(
            model=model,
            api_key=api_key,
            timeout=10,
            num_retries=0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "게임 채팅 기록의 사건 경위를 한국어 한 문단으로 작성하세요. "
                        "제공된 채널, 표현의 성격, 건수만 사용하고, 수사기관에 제출하는 문체를 사용하세요. "
                        "은어, 원문 인용, 피해자 특정, 발언 목적 추정, 죄명과 범죄 성립 판단을 쓰지 마세요."
                    ),
                },
                {"role": "user", "content": "\n".join(facts)},
            ],
        )
        content = result.choices[0].message.content
        if content:
            summary = " ".join(content.split())
            if summary and not any(label in summary for label in ("욕설", "패드립", "정치질")):
                logger.info("Gemini 사건 경위 생성 성공")
                return summary
        logger.warning("Gemini 응답이 비어 있거나 사건 경위 형식에 맞지 않아 로컬 문장을 사용합니다.")
    except Exception as error:
        status = getattr(error, "status_code", None)
        logger.warning(
            "Gemini 사건 경위 생성에 실패해 로컬 문장을 사용합니다. (%s, HTTP %s)",
            type(error).__name__,
            status if isinstance(status, int) and 100 <= status <= 599 else "확인 불가",
        )
    return fallback


def _fill_template(req: ReportRequest, incidents: list[Incident], summary: str) -> list[tuple[str, str]]:
    my_id = next((player.name for player in req.session.players if player.is_me), "")
    start = _timestamp(incidents[0].msg.ts)
    end = _timestamp(incidents[-1].msg.ts)
    when = start if start == end else f"{start} ~ {end}"
    evidence = "\n".join(
        f"{index}. [{incident.msg.id}] {_timestamp(incident.msg.ts)} "
        f"({CHANNEL_LABELS[incident.msg.channel]}) {incident.msg.text}"
        for index, incident in enumerate(incidents, 1)
    )
    threat_ids = [incident.msg.id for incident in incidents if HarmType.THREAT in incident.analysis.harm_types]
    threat_sections = (
        [(f"협박 관련 기록 ({len(threat_ids)}건)", f"증거 ID: {', '.join(threat_ids)}")] if threat_ids else []
    )
    blank = "________________________________"
    return [
        (
            "고소인",
            f"성명: {req.complainant or blank}\n"
            f"게임 ID(닉네임): {my_id or blank}\n"
            f"주민등록번호: {blank}\n주소: {blank}\n연락처: {blank}",
        ),
        (
            "피고소인",
            f"성명: {blank}\n게임 ID(닉네임): {req.speaker}\n주소 또는 연락처(아는 경우): {blank}",
        ),
        (
            "고소취지",
            "고소인은 아래 채팅 발언에 관하여 고소하오니, 증거자료와 당시 대화의 전후 사정을 "
            "조사하여 관련 법령에 따라 조치하여 주시기 바랍니다.",
        ),
        (
            "범죄사실",
            f"1. 발생 일시(한국 시간): {when}\n"
            "2. 발생 장소: 온라인 게임 리그 오브 레전드 채팅\n"
            f"3. 사건 경위: {summary}\n4. 발언의 일시·채널·원문은 아래 증거자료에 기재하였습니다.",
        ),
        (
            "고소이유",
            f"{_investigation_points(incidents)}\n"
            f"당시 열람할 수 있었던 참가자 및 대상이 드러나는 정황: {blank}\n"
            f"구체적인 피해 내용 및 추가 경위: {blank}",
        ),
        *threat_sections,
        ("증거자료", f"채팅 기록 {len(incidents)}건\n{evidence}"),
        ("작성 및 제출", f"작성일: ______년 ____월 ____일\n고소인 서명: {blank}\n제출처: {blank}"),
        ("", "이 문서는 법률 자문이 아니며 실제 제출 전 전문가 검토가 필요합니다."),
    ]


def _investigation_points(incidents: list[Incident]) -> str:
    """게임 분류에 해당하는 확인 사항을 제시하고 죄명은 사실관계에 따라 검토하도록 한다."""
    harms = {harm for incident in incidents for harm in incident.analysis.harm_types}
    points = []
    if harms & {HarmType.PROFANITY, HarmType.FAMILY_INSULT, HarmType.BLAME, HarmType.INSTIGATION}:
        points.append(
            "형법 제311조(모욕) 관련: 발언의 대상이 당시 대화에서 드러났는지, "
            "제3자가 발언을 인식할 수 있었는지, 표현과 전후 맥락이 어떠했는지 확인하여 주시기 바랍니다."
        )
    if HarmType.INSTIGATION in harms:
        points.append(
            "비난을 유도하는 발언에 구체적인 사실의 적시가 포함되어 있는 경우, "
            "그 내용과 전파 범위를 확인하여 형법 제307조(명예훼손) 적용 여부를 검토하여 주시기 바랍니다."
        )
    if HarmType.SEXUAL_HARASSMENT in harms:
        points.append(
            "성폭력처벌법 제13조(통신매체를 이용한 음란행위) 관련: 발언의 내용과 경위, "
            "상대방에게 도달한 정황 및 발언 목적을 확인하여 적용 여부를 검토하여 주시기 바랍니다."
        )
    if HarmType.THREAT in harms:
        points.append(
            "형법 제283조 제1항(협박) 관련: 고지된 해악의 내용이 발언 당사자의 관계와 "
            "당시 대화의 전후 사정을 고려할 때 일반적으로 공포심을 일으키기에 충분하였는지, "
            "그 고지가 상대방에게 도달하여 상대방이 그 의미를 인식하였는지 확인하여 주시기 바랍니다."
        )
    return "\n".join(f"{index}. {point}" for index, point in enumerate(points, 1)) or (
        "채팅 원문, 발언의 대상 및 당시 대화의 전후 사정을 확인하여 주시기 바랍니다."
    )


def _render_pdf(sections: list[tuple[str, str]], output_dir: str, speaker: str) -> str:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen.canvas import Canvas

    font = "HYSMyeongJo-Medium"
    windows_fonts = Path(os.getenv("WINDIR", "C:/Windows")) / "Fonts"
    mac_fonts = Path("/System/Library/Fonts/Supplemental")
    font_candidates = (
        (windows_fonts / "batang.ttc", 2),  # Windows 바탕 글꼴 모음의 궁서
        (mac_fonts / "AppleMyungjo.ttf", 0),
        (windows_fonts / "malgun.ttf", 0),
        (mac_fonts / "AppleGothic.ttf", 0),
    )
    for font_path, subfont_index in font_candidates:
        if font_path.is_file():
            font = "CleanChatKorean"
            pdfmetrics.registerFont(TTFont(font, str(font_path), subfontIndex=subfont_index))
            break
    else:
        pdfmetrics.registerFont(UnicodeCIDFont(font))

    safe_speaker = "".join(char if char.isalnum() or char in "-_#" else "_" for char in speaker)[:60]
    relative_path = Path(output_dir) / f"complaint_{safe_speaker or 'player'}.pdf"
    path = resolve_repo_path(relative_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # 렌더링 완료 후 교체해 결과 화면에서 불완전한 PDF가 열리지 않게 한다.
    with NamedTemporaryFile(dir=path.parent, suffix=".pdf", delete=False) as handle:
        temporary_path = Path(handle.name)
    try:
        canvas = Canvas(str(temporary_path), pagesize=A4)
        canvas.setTitle("고소장 초안")
        width, height = A4
        margin, font_size, line_height = 60, 11, 17
        y = height - margin

        def draw_heading(label: str, x: float, baseline: float, size: int) -> None:
            # 명조·궁서처럼 굵은 파일이 없는 서체도 글자 외곽선을 더해 제목을 강조한다.
            canvas.saveState()
            canvas.setLineWidth(0.35)
            heading_text = canvas.beginText(x, baseline)
            heading_text.setFont(font, size)
            heading_text.setTextRenderMode(2)
            heading_text.textLine(label)
            canvas.drawText(heading_text)
            canvas.restoreState()

        title = "고소장"
        draw_heading(title, (width - pdfmetrics.stringWidth(title, font, 25)) / 2, y, 25)
        y -= 21
        canvas.setFont(font, 10)
        canvas.drawCentredString(width / 2, y, "초안")
        y -= 30

        for heading, body in sections:
            if y < margin + (3 * line_height if heading else 0):
                canvas.showPage()
                y = height - margin
            if heading:
                draw_heading(heading, margin, y, 14)
                y -= 22
            canvas.setFont(font, font_size)
            for line in body.splitlines():
                for row in _wrap_line(
                    line, width - 2 * margin, lambda text: pdfmetrics.stringWidth(text, font, font_size)
                ):
                    if y < margin:
                        canvas.showPage()
                        canvas.setFont(font, font_size)
                        y = height - margin
                    canvas.drawString(margin, y, row)
                    y -= line_height
            y -= 15
        canvas.save()
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return relative_path.as_posix()


def _wrap_line(line: str, max_width: float, measure: Callable[[str], float]) -> Iterator[str]:
    """공백 없는 한글 원문도 페이지 폭에 맞춰 줄바꿈한다."""
    start = 0
    width = 0.0
    for index, character in enumerate(line):
        character_width = measure(character)
        if width + character_width > max_width and index > start:
            yield line[start:index]
            start = index
            width = 0.0
        width += character_width
    yield line[start:]
