"""고소장 초안 한 건을 확인하고 화면과 같은 문서를 PDF로 저장한다 (클라이언트 목업 '고소장 PDF')."""

import re
from datetime import datetime
from html import escape, unescape
from pathlib import Path

from PySide6.QtCore import QIODevice, QSaveFile, Qt, Signal
from PySide6.QtGui import QPageSize, QPdfWriter
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from clean_chat.core.charges import CHARGE_CATALOG, ChargeId
from clean_chat.core.game import KST
from clean_chat.core.schemas import ChatMessage, ReportDraft
from clean_chat.ui.client_widgets import (
    FlowLayout,
    button,
    card,
    heading,
    info_button,
    label,
    pop_text,
    restyle,
    rich,
    warn_icon,
)

CHANNEL = {"team": "팀", "all": "전체", "unknown": "채널 미상"}
PDF_DPI = 72  # 미리보기 HTML 의 px 글자 크기를 그대로 pt 로 찍는 해상도 (본문 11px → 11pt)
PHONE_DIGITS = 11  # 휴대폰 010-1234-5678


def default_pdf_path(nickname: str = "", today: datetime | None = None) -> Path:
    """고소장 PDF 기본 저장 위치: 다운로드 폴더(없으면 홈)의 `고소장-초안-닉네임-날짜.pdf`."""
    folder = Path.home() / "Downloads"
    if not folder.is_dir():
        folder = Path.home()
    day = (today or datetime.now(KST)).strftime("%Y%m%d")
    safe = re.sub(r'[\\/:*?"<>|\s]+', "_", nickname).strip("_.")
    return folder / ("-".join(part for part in ("고소장-초안", safe, day) if part) + ".pdf")


def format_phone(text: str) -> str:
    """연락처 숫자에 하이픈을 넣어 보여 준다. 숫자가 아닌 글자는 버린다 (입력은 숫자만).

    예) "01012345678" → "010-1234-5678", "0212345678" → "02-1234-5678", "15881234" → "1588-1234"
    입력 중인 숫자도 그때그때 나눈다: "0101" → "010-1"
    """
    d = re.sub(r"\D", "", text)
    if d.startswith("02"):  # 서울 지역번호는 두 자리
        d = d[:10]
        if len(d) <= 2:
            return d
        if len(d) <= 5:
            return f"02-{d[2:]}"
        if len(d) <= 9:
            return f"02-{d[2:5]}-{d[5:]}"
        return f"02-{d[2:6]}-{d[6:]}"
    d = d[:PHONE_DIGITS]
    if len(d) == 8 and d[:2] in {"15", "16", "18"}:  # 대표번호 1588-1234
        return f"{d[:4]}-{d[4:]}"
    if len(d) <= 3:
        return d
    if len(d) <= 6:
        return f"{d[:3]}-{d[3:]}"
    if len(d) <= 10:
        return f"{d[:3]}-{d[3:6]}-{d[6:]}"
    return f"{d[:3]}-{d[3:7]}-{d[7:]}"


WARNINGS = [
    (
        "경찰서 직접 출석 · 진술 조사 최소 1회",
        "온라인(경찰청 사이버범죄 신고시스템 등)으로 접수해도, 최종 수리를 위해 관할 경찰서 사이버수사팀에 최소 한 번은 "
        "직접 출석해 고소인 진술 조서를 써야 합니다. 수사관 앞에서 당시 상황과 채팅 내용을 다시 설명해야 합니다.",
    ),
    (
        "수사 기간 보통 3~6개월 이상",
        "라이엇 게임즈에 압수수색 영장을 집행해 가해자 인적사항을 받고, 가해자 거주지 관할 경찰서로 사건을 옮겨 피의자 "
        "조사를 하기까지 보통 3개월, 길면 6개월 이상 걸립니다.",
    ),
    (
        "경미한 건은 접수 단계에서 반려·만류될 수 있음",
        '단순 욕설이나 특정성·공연성이 부족한 건은 수사관이 "이 정도로는 처벌이 어렵다"며 접수를 만류하거나 반려하는 '
        "경우가 많고, 이 과정에서 감정 소모가 큽니다.",
    ),
    (
        "조사 중 모욕적인 채팅 원문을 다시 마주해야 함",
        "특히 통매음(성희롱)이나 심한 패드립은 조사 과정에서 수사관 앞에서 가해자의 음란하고 모욕적인 원문을 그대로 "
        "읽거나 확인해야 해, 민망함과 정신적 스트레스가 따릅니다.",
    ),
    (
        "합의 연락 · 형사조정 등 추가 절차",
        "가해자가 특정되면 합의 연락이 오고, 형사조정위원회에 출석하거나 합의금을 조율하는 데 시간과 에너지가 듭니다. "
        "단, 가명조서 신청 등으로 고소인의 개인정보가 가해자에게 노출되지 않도록 보호받을 수 있습니다.",
    ),
]


def quote(msg: ChatMessage) -> str:
    """신고 화면 원문 기록 한 줄. 예) [21:14:02] 불꽃남자 (팀): 미드 시1발 개못하네"""
    stamp = datetime.fromtimestamp(msg.ts, KST).strftime("%H:%M:%S")
    return f"[{stamp}] {msg.speaker} ({CHANNEL[msg.channel]}): {msg.text}"


def quote_full(msg: ChatMessage) -> str:
    """고소장 증거 한 줄은 날짜까지 남긴다."""
    stamp = datetime.fromtimestamp(msg.ts, KST).strftime("%Y-%m-%d %H:%M:%S")
    return f"[{stamp}] [{CHANNEL[msg.channel]}] {msg.speaker}: {msg.text}"


def complaint_facts(text: str) -> str:
    """report 모듈이 HTML 고소장을 주면 '범죄사실' 절만 평문으로 꺼낸다. 평문이면 그대로 쓴다."""
    if not text.lstrip().startswith("<"):
        return text
    found = re.search(r">범죄사실</h2>\s*<p[^>]*>(.*?)</p>", text, re.S)
    return unescape(re.sub(r"<[^>]+>", "", found.group(1) if found else text)).strip()


def _charge_help(code: ChargeId) -> list:
    info = CHARGE_CATALOG[code]
    gold = "<b style='color:#FFD27A'>{}</b>&nbsp; {}"
    return [
        label(info.law, "popLaw"),
        pop_text(escape(info.description)),
        pop_text(gold.format("예시", escape(info.example))),
        pop_text(gold.format("처벌", escape(info.penalty))),
    ]


class ComplaintEditor(QWidget):
    notice = Signal(str)
    saved = Signal(str)
    back = Signal()
    open_pdf = Signal()

    def __init__(self, draft: ReportDraft | None = None, game: str = "") -> None:
        super().__init__()
        self.draft = draft
        self.done = False
        columns = QHBoxLayout(self)
        columns.setContentsMargins(0, 0, 0, 0)
        columns.setSpacing(28)
        form = QVBoxLayout()
        form.setSpacing(16)
        columns.addLayout(form, 1)

        form.addWidget(label("수위 ‘높음’ 유저만 생성 가능 · 드물게 사용하는 기능", "caption"))
        form.addWidget(label("고소장 만들기", "title"))
        form.addWidget(self._target_card(game))
        form.addLayout(self._charges())
        form.addWidget(self._warning())

        people = QGridLayout()
        people.setHorizontalSpacing(12)
        people.setVerticalSpacing(4)
        self.name, self.contact = QLineEdit(), QLineEdit()
        for i, (title, field, hint) in enumerate(
            [("고소인 이름", self.name, "[이름 입력]"), ("연락처", self.contact, "[연락처 입력]")]
        ):
            field.setPlaceholderText(hint)
            field.setMaxLength(100)
            caption = label(title, "caption")
            caption.setBuddy(field)
            people.addWidget(caption, 0, i)
            people.addWidget(field, 1, i)
        form.addLayout(people)
        # 연락처는 숫자만 받고 보기에는 하이픈을 넣는다 (01012345678 → 010-1234-5678)
        self.contact.setPlaceholderText("숫자만 입력 (예: 01012345678)")
        self.contact.setMaxLength(20)
        self.contact.setInputMethodHints(Qt.ImhDialableCharactersOnly)
        self._contact_shown = ""
        self.contact.textEdited.connect(self._format_contact)
        form.addWidget(
            label(
                "초안 양식이며 법률 자문이 아닙니다. 법정형은 참고용이고 사안·법 개정에 따라 다를 수 있으니, "
                "제출 전 법률 전문가와 상담하세요.",
                "caption",
            )
        )
        form.addStretch()

        actions = QHBoxLayout()
        actions.setSpacing(12)
        self.download = button("PDF 다운로드", "primary", large=True)
        self.download.clicked.connect(self.download_pdf)
        self.reason = label("", "caption")
        self.reason.setMinimumWidth(80)
        self.btn_open = button("PDF 열기")
        self.btn_open.clicked.connect(self.open_pdf)
        self.btn_open.setVisible(bool(draft and draft.pdf_path))
        back = button("← 신고 메시지로", "link")
        back.setStyleSheet("font-size:13px;")
        back.clicked.connect(self.back)
        actions.addWidget(self.download)
        actions.addWidget(self.reason, 1)
        actions.addWidget(self.btn_open)
        actions.addWidget(back)
        form.addLayout(actions)

        side = QVBoxLayout()
        side.setSpacing(8)
        side.addWidget(label("PDF 미리보기", "caption"))
        self.paper = QTextBrowser()
        self.paper.setObjectName("paper")
        self.paper.setFixedSize(360, 520)
        self.paper.setOpenLinks(False)
        side.addWidget(self.paper)
        side.addStretch()
        columns.addLayout(side)

        for field in (self.name, self.contact, self.target, self.tag):
            field.textChanged.connect(self._edited)
        self.ack.toggled.connect(self._edited)
        self.refresh()

    # ── 화면 조각 ─────────────────────────────────────────────
    def _target_card(self, game: str) -> QFrame:
        frame, box = card()
        box.setSpacing(10)
        head = QHBoxLayout()
        head.addWidget(label("피고소인 확인", "label"))
        head.addStretch()
        evidence = self.draft.evidence if self.draft else ()
        champion = next((m.champion for m in evidence if m.champion), "")
        meta = [part for part in (champion, game, f"원문 {len(evidence)}건 자동 첨부" if self.draft else "") if part]
        head.addWidget(label(" · ".join(meta), "caption"))
        box.addLayout(head)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.target, self.tag = QLineEdit(), QLineEdit()
        self.target.setPlaceholderText("닉네임")
        self.tag.setPlaceholderText("KR1")
        for title, field, width in [("닉네임", self.target, 0), ("태그", self.tag, 120)]:
            field.setMaxLength(100)
            col = QVBoxLayout()
            col.setSpacing(4)
            caption = rich(f"{title} <span style='color:#B4441A'>*</span>", "caption")
            caption.setBuddy(field)
            col.addWidget(caption)
            col.addWidget(field)
            if width:
                hash_mark = label("#", "hash")
                row.addWidget(hash_mark, 0, Qt.AlignBottom)
                holder = QWidget()
                holder.setFixedWidth(width)
                holder.setLayout(col)
                col.setContentsMargins(0, 0, 0, 0)
                row.addWidget(holder)
            else:
                row.addLayout(col, 1)
        box.addLayout(row)
        self.id_hint = label("", "caption")
        box.addWidget(self.id_hint)
        if self.draft:
            nick, sep, tag = self.draft.speaker.rpartition("#")
            self.target.setText(nick if sep else self.draft.speaker)
            self.tag.setText(tag if sep else "")
        return frame

    def _charges(self) -> QVBoxLayout:
        box = QVBoxLayout()
        box.setSpacing(8)
        box.addWidget(heading("적용 죄목", "채팅 분석 결과로 자동 적용"))
        if not self.selected_charges():
            box.addWidget(label("자동 적용된 죄목이 없습니다.", "caption"))
            return box
        chips = QWidget()
        flow = FlowLayout(chips)
        for code in self.selected_charges():
            info = CHARGE_CATALOG[code]
            chip = QFrame()
            chip.setObjectName("chip")
            chip.setProperty("on", "true")
            row = QHBoxLayout(chip)
            row.setContentsMargins(12, 4, 6, 4)
            row.setSpacing(4)
            row.addWidget(label(info.name))
            row.addWidget(info_button(info.name, _charge_help(code)))
            flow.addWidget(chip)
        box.addWidget(chips)
        return box

    def _warning(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("warning")
        box = QVBoxLayout(frame)
        box.setContentsMargins(18, 16, 18, 16)
        box.setSpacing(10)
        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(warn_icon())
        head.addWidget(label("고소는 신고와 다릅니다. 가볍게 결정하지 마세요.", "warnTitle"), 1)
        box.addLayout(head)
        box.addWidget(
            rich(
                "고소는 장난이나 홧김에 하는 일이 아니라, 수개월의 시간과 감정 소모를 감수하는 법적 절차입니다. "
                "사실과 다르거나 부풀린 내용으로 고소하면 오히려 무고죄로 처벌받을 수 있습니다. "
                "<b>통매음·구체적 협박처럼 처벌 가능성이 분명한 건만</b> 진행하는 것을 권장합니다.",
                "warnBody",
            )
        )
        items = QVBoxLayout()
        items.setSpacing(2)
        for no, (title, detail) in enumerate(WARNINGS, 1):
            row = QHBoxLayout()
            row.setSpacing(6)
            number = label(str(no), "warnNo")
            number.setFixedWidth(20)
            row.addWidget(number)
            row.addWidget(label(title, "warnItem"), 1)
            row.addWidget(info_button(title, detail, "#8F3412"))
            items.addLayout(row)
        box.addLayout(items)
        rule = QFrame()
        rule.setObjectName("warnRule")
        rule.setFixedHeight(1)
        box.addWidget(rule)
        self.ack = QCheckBox("위 내용을 이해했으며, 장난이 아닌 실제 피해에 대해 고소하려고 합니다.")
        self.ack.setStyleSheet("font-size:13px;font-weight:500;")
        box.addWidget(self.ack)
        return frame

    def _format_contact(self, text: str) -> None:
        """연락처 칸: 숫자가 아닌 글자는 지우고 하이픈은 자동으로 넣는다. 커서는 같은 숫자 뒤에 둔다."""
        pos = self.contact.cursorPosition()
        digits = re.sub(r"\D", "", text)
        before = len(re.sub(r"\D", "", text[:pos]))  # 커서 앞의 숫자 수
        shown = self._contact_shown
        if digits == re.sub(r"\D", "", shown) and len(text) < len(shown) and before:
            # 하이픈만 지웠다 → 그 앞 숫자를 지운다. 그러지 않으면 하이픈이 바로 다시 생겨 지워지지 않는 것처럼 보인다
            digits, before = digits[: before - 1] + digits[before:], before - 1
        formatted = format_phone(digits)
        self._contact_shown = formatted
        if formatted != text:
            self.contact.setText(formatted)
        seen, cursor = 0, len(formatted)
        for i, ch in enumerate(formatted):
            if seen == before:
                cursor = i
                break
            seen += ch.isdigit()
        self.contact.setCursorPosition(cursor)

    # ── 상태 ──────────────────────────────────────────────────
    def selected_charges(self) -> list[ChargeId]:
        """분석 결과로 자동 적용된 죄목 (사용자가 바꾸지 않는다)."""
        return list(self.draft.applied_charge_ids) if self.draft else []

    def _edited(self) -> None:
        self.done = False
        self.refresh()

    def refresh(self) -> None:
        name, contact, nick, tag = (w.text().strip() for w in (self.name, self.contact, self.target, self.tag))
        tag = tag.lstrip("#").strip()
        id_ok = bool(nick and tag)
        restyle(self.target, invalid="false" if nick else "true")
        restyle(self.tag, invalid="false" if tag else "true")
        self.id_hint.setText(
            "롤은 닉네임이 중복될 수 있어, 닉네임과 # 뒤 태그를 합쳐야 한 사람으로 특정돼요. 게임 기록의 계정과 같은지 확인하세요."
            if id_ok
            else "닉네임과 # 뒤 태그는 필수 입력이에요."
        )
        restyle(self.id_hint, "caption" if id_ok else "error")
        charges = [CHARGE_CATALOG[c].name for c in self.selected_charges()]
        evidence = self.draft.evidence if self.draft else ()
        facts = complaint_facts(self.draft.text) if self.draft else "경기 종료 후 생성된 초안이 여기에 표시됩니다."
        today = datetime.now(KST)
        writer = escape(name) or "[이름]"
        lines = "".join(f"<p style='margin:2px 0'>{escape(quote_full(m))}</p>" for m in evidence)
        self.paper.setHtml(
            "<div style='font-size:11px;line-height:150%'>"
            "<p align='center' style=\"font-family:'AppleMyungjo','Batang','Noto Serif KR',serif;"
            'font-size:24px;font-weight:700">고 소 장</p>'
            f"<p><b>고소인</b>　{writer} / {escape(contact) or '[연락처]'}</p>"
            f"<p><b>피고소인</b>　League of Legends 계정 {escape(nick) or '[닉네임]'}#{escape(tag) or '[태그]'}</p>"
            f"<p><b>죄명</b>　{escape(', '.join(charges)) or '[해당 없음]'}</p>"
            f"<p><b>고소 사실</b></p><p>{escape(facts).replace(chr(10), '<br>')}</p>"
            f"<p><b>증거 (채팅 원문 {len(evidence)}건)</b></p>{lines}"
            f"<p align='right' style='margin-top:16px'>{today.year}년 {today.month}월 {today.day}일 · "
            f"고소인 {writer} (인)</p>"
            "</div>"
        )
        reason = next(
            (
                message
                for ok, message in [
                    (self.draft, "경기 종료 후 생성된 초안이 여기에 표시됩니다."),
                    (id_ok, "피고소인 닉네임과 태그를 입력하세요"),
                    (self.ack.isChecked(), "주의사항 확인 후 다운로드할 수 있어요"),
                ]
                if not ok
            ),
            "",
        )
        self.reason.setText(reason)
        self.download.setEnabled(not reason)
        self.download.setText("PDF 저장됨 ✓" if self.done else "PDF 다운로드")

    # ── 저장 ──────────────────────────────────────────────────
    def download_pdf(self) -> None:
        if not self.download.isEnabled():
            return
        # 기본 위치는 절대 경로로 준다. 설치한 앱의 작업 폴더는 "/"(읽기 전용)라서 파일 이름만 주면 저장이 실패한다.
        default = default_pdf_path(self.target.text().strip())
        path, _ = QFileDialog.getSaveFileName(self, "고소장 PDF 다운로드", str(default), "PDF (*.pdf)")
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        try:
            self.save_pdf(Path(path))
        except OSError as exc:
            self.notice.emit(f"PDF 저장 실패 · {exc}")
            return
        self.done = True
        self.refresh()
        self.btn_open.show()
        self.saved.emit(path)
        self.notice.emit(f"PDF 저장 완료 · {Path(path).name}")

    def save_pdf(self, path: Path) -> None:
        target = QSaveFile(str(path))
        if not target.open(QIODevice.WriteOnly):
            raise OSError(target.errorString())
        writer = QPdfWriter(target)
        writer.setPageSize(QPageSize(QPageSize.A4))
        # 미리보기 HTML 의 글자 크기가 px 라서, 기본 해상도(1200dpi)로 찍으면 A4 에 글자가 아주 작게 나온다.
        writer.setResolution(PDF_DPI)
        writer.setTitle("고소장 초안")
        self.paper.document().print_(writer)
        del writer
        if target.size() == 0 or not target.commit():
            raise OSError(target.errorString() or "빈 PDF 파일")
