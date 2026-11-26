"""실제 초안 한 건을 편집하고 화면과 동일한 문서를 PDF로 저장한다."""

from datetime import datetime
from html import escape
from pathlib import Path

from PySide6.QtCore import QIODevice, QSaveFile, Qt, Signal
from PySide6.QtGui import QPageSize, QPdfWriter
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from clean_chat.core.charges import CHARGE_CATALOG
from clean_chat.core.game import KST
from clean_chat.core.schemas import ChatMessage, ReportDraft
from clean_chat.ui.client_widgets import card, info_button, label


def quote(msg: ChatMessage) -> str:
    stamp = datetime.fromtimestamp(msg.ts, KST).strftime("%Y-%m-%d %H:%M:%S")
    channel = {"team": "팀", "all": "전체", "unknown": "채널 미상"}[msg.channel]
    return f"[{stamp}] [{channel}] {msg.speaker}: {msg.text}"


class ComplaintEditor(QWidget):
    notice = Signal(str)
    saved = Signal(str)

    def __init__(self, draft: ReportDraft | None = None) -> None:
        super().__init__()
        self.draft = draft
        self.evidence_checks = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.download = QPushButton("고소장 PDF 다운로드")
        self.download.setObjectName("primary")
        self.download.clicked.connect(self.download_pdf)
        actions = QHBoxLayout()
        actions.addWidget(self.download)
        self.reason = label("", "muted")
        actions.addWidget(self.reason, 1)
        layout.addLayout(actions)

        columns = QHBoxLayout()
        layout.addLayout(columns)
        form = QVBoxLayout()
        columns.addLayout(form, 3)
        identity, fields = card("고소인과 상대 계정")
        form.addWidget(identity)
        inputs = QGridLayout()
        fields.addLayout(inputs)
        self.name, self.contact, self.target, self.tag = (QLineEdit() for _ in range(4))
        self.name.setPlaceholderText("내 이름 입력")
        self.contact.setPlaceholderText("선택 사항")
        self.tag.setPlaceholderText("예: KR1")
        for i, (title, field) in enumerate(
            [
                ("내 이름 (고소인)", self.name),
                ("연락처", self.contact),
                ("상대 닉네임", self.target),
                ("태그 (#)", self.tag),
            ]
        ):
            field.setMaxLength(100)
            caption = label(title)
            caption.setBuddy(field)
            inputs.addWidget(caption, 2 * (i // 2), i % 2)
            inputs.addWidget(field, 2 * (i // 2) + 1, i % 2)
        if draft:
            nick, sep, tag = draft.speaker.rpartition("#")
            self.target.setText(nick if sep else draft.speaker)
            self.tag.setText(tag if sep else "")

        choice, choices = card("고소 내용 선택")
        form.addWidget(choice)
        choices.addWidget(label("첨부할 채팅 원문을 선택하세요.", "muted"))
        for msg in draft.evidence if draft else ():
            check = QCheckBox()
            check.setAccessibleName(quote(msg))
            check.setChecked(True)
            row = QHBoxLayout()
            row.addWidget(check)
            row.addWidget(label(quote(msg)), 1)
            choices.addLayout(row)
            self.evidence_checks.append((msg, check))
            check.toggled.connect(self.refresh)
        if not self.evidence_checks:
            choices.addWidget(label("첨부 가능한 채팅 원문이 없습니다.", "muted"))
        choices.addWidget(label("적용된 혐의", "section"))
        for code in draft.applied_charge_ids if draft else ():
            info = CHARGE_CATALOG[code]
            row = QHBoxLayout()
            row.addWidget(label(info.name, "charge"))
            row.addWidget(info_button(info.name, info.description))
            row.addStretch()
            choices.addLayout(row)
        if not draft or not draft.applied_charge_ids:
            choices.addWidget(label("적용된 혐의 없음", "muted"))

        warning, notes = card("고소장 제출 시 주의사항", "warning")
        form.addWidget(warning)
        for title, detail in [
            ("대상 계정 확인", "게임 기록의 닉네임과 Riot ID 태그를 함께 확인하세요."),
            ("당시 대화와 시각 확인", "발언 전후의 맥락과 인용한 원문을 확인하세요."),
            ("직접 경험한 내용 구분", "기억에 따른 설명과 기록으로 확인한 사실을 구분하세요."),
            ("개인정보 확인", "첨부 자료에 불필요한 개인정보가 있는지 살펴보세요."),
            ("제출 전 검토", "이 문서는 고소장 초안입니다. 대상, 일시, 내용이 정확한지 확인하세요."),
        ]:
            row = QHBoxLayout()
            row.addWidget(label(title), 1)
            row.addWidget(info_button(title, detail))
            notes.addLayout(row)
        self.ack = QCheckBox("주의사항과 선택한 원문을 확인했습니다.")
        notes.addWidget(self.ack)
        form.addStretch()

        preview, panel = card("고소장 미리보기", "preview")
        columns.addWidget(preview, 2, Qt.AlignTop)
        self.paper = QTextBrowser()
        self.paper.setObjectName("paper")
        self.paper.setMinimumSize(210, 475)
        self.paper.setOpenLinks(False)
        panel.addWidget(self.paper)
        panel.addWidget(label("입력한 내용이 문서에 바로 반영됩니다.", "muted"))
        for field in (self.name, self.contact, self.target, self.tag):
            field.textChanged.connect(self.refresh)
        self.ack.toggled.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        selected = [msg for msg, check in self.evidence_checks if check.isChecked()]
        name, contact, nick, tag = [escape(w.text().strip()) for w in (self.name, self.contact, self.target, self.tag)]
        tag = tag.lstrip("#").strip()
        charges = ", ".join(CHARGE_CATALOG[c].name for c in self.draft.applied_charge_ids) if self.draft else ""
        account = f"{nick or '[닉네임]'}#{tag or '[태그]'}"
        body = "".join(f"<p>{escape(quote(msg))}</p>" for msg in selected)
        facts = self.draft.text if self.draft else "초안 대기 중"
        if self.draft and len(selected) != len(self.evidence_checks):
            facts = (
                f"첨부한 채팅 {len(selected)}건을 고소 내용에 포함합니다." if selected else "첨부할 채팅을 선택하세요."
            )
        self.paper.setHtml(
            "<small>CLEAN CHAT　·　고소장 초안</small><hr><h1 align='center'>고 소 장</h1><hr>"
            f"<p><b>고소인</b>　{name or '[이름]'}　{contact}</p><p><b>피고소인</b>　{account}</p>"
            f"<p><b>적용된 혐의</b>　{escape(charges) or '없음'}</p><hr>"
            f"<h3>고소 내용</h3><p>{escape(facts).replace(chr(10), '<br>')}</p>"
            f"<h3>첨부 채팅 원문 {len(selected)}건</h3>{body}<p align='right'>고소인　{name or '[이름]'} (인)</p>"
            "<small>법률 자문이 아닌 작성용 초안입니다.</small>"
        )
        reason = next(
            (
                message
                for ok, message in [
                    (self.draft, "경기 종료 후 생성된 초안이 여기에 표시됩니다."),
                    (name, "내 이름을 입력하세요."),
                    (nick and tag, "상대 닉네임과 태그를 입력하세요."),
                    (selected, "첨부할 원문을 선택하세요."),
                    (self.ack.isChecked(), "제출 시 주의사항을 확인하세요."),
                ]
                if not ok
            ),
            "",
        )
        self.reason.setText(reason)
        self.download.setEnabled(not reason)

    def download_pdf(self) -> None:
        if not self.download.isEnabled():
            return
        path, _ = QFileDialog.getSaveFileName(self, "고소장 PDF 다운로드", "고소장-초안.pdf", "PDF (*.pdf)")
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        try:
            self.save_pdf(Path(path))
        except OSError as exc:
            self.notice.emit(f"PDF 저장 실패 · {exc}")
            return
        self.saved.emit(path)
        self.notice.emit(f"PDF 저장 완료 · {Path(path).name}")

    def save_pdf(self, path: Path) -> None:
        target = QSaveFile(str(path))
        if not target.open(QIODevice.WriteOnly):
            raise OSError(target.errorString())
        writer = QPdfWriter(target)
        writer.setPageSize(QPageSize(QPageSize.A4))
        writer.setTitle("고소장 초안")
        self.paper.document().print_(writer)
        del writer
        if target.size() == 0 or not target.commit():
            raise OSError(target.errorString() or "빈 PDF 파일")
