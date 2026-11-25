"""[구성 · 리드] 클라이언트 창 (SPEC 3-1). 게임 단계마다 다른 화면을 보여 준다 (HANDOFF 5-2).

| 단계        | 화면                                              |
|------------|---------------------------------------------------|
| IDLE       | 지난 처리 내역, 설정, 사용법                          |
| IN_GAME    | "게임 중" 안내 (채팅은 오버레이에서)                   |
| POST_GAME  | "이번 게임 결과": 신고 문구 복사, 고소장 PDF, 닫기      |
판단하지 않고 Decision / PostGameResult 를 그대로 보여 주기만 한다.
"""

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTime, QUrl, Slot
from PySide6.QtGui import QDesktopServices, QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from clean_chat.core.config import resolve_repo_path
from clean_chat.core.schemas import GamePhase, GameSession, Incident, PostGameResult


class ClientWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Clean Chat")
        tools = self.addToolBar("오버레이")
        tools.setMovable(False)
        self.btn_start = QPushButton("Clean Chat 시작")
        self.btn_lock = QPushButton("위치 잠금")
        self.btn_lock.setEnabled(False)
        for button in (self.btn_start, self.btn_lock):
            tools.addWidget(button)
        self.permission_settings = tools.addAction("화면 기록 설정")
        self.permission_settings.setVisible(False)
        self.permission_settings.setToolTip(f"현재 실행 파일 · {sys.executable}")
        self.permission_settings.triggered.connect(self.open_capture_settings)
        self.reveal_app = tools.addAction("Finder에서 앱 보기")
        self.reveal_app.setVisible(False)
        self.reveal_app.triggered.connect(self.reveal_capture_app)
        self.pages = QStackedWidget()
        self.setCentralWidget(self.pages)
        self.preview_only = QCheckBox("오버레이 아래 화면 미리보기 (OCR 끔)")
        self.preview_only.setChecked(True)
        tools.addWidget(self.preview_only)
        self.preview_page = QWidget()
        preview_layout = QVBoxLayout(self.preview_page)
        self.preview_info = QLabel("캡처 미리보기")
        self.preview_image = QLabel("캡처 대기 중")
        self.preview_image.setAlignment(Qt.AlignCenter)
        self.preview_image.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        self.preview_image.setMinimumSize(300, 140)
        preview_layout.addWidget(self.preview_info)
        preview_layout.addWidget(self.preview_image)
        self.pages.addWidget(self.preview_page)
        self.preview_count = 0

        # IDLE: 대기 화면
        idle = QWidget()
        lay = QVBoxLayout(idle)
        lay.addWidget(QLabel("시작을 누르고 오버레이를 게임 채팅창 전체에 맞추세요."))
        self.my_name = QLineEdit()
        self.my_name.setPlaceholderText("내 소환사명")
        lay.addWidget(self.my_name)
        self.history = QListWidget()  # 지난 처리 내역 (세션 저장소에서 불러옴). TODO: 표(QTableWidget)
        lay.addWidget(self.history)

        # IN_GAME: 게임 중 화면
        in_game = QWidget()
        lay = QVBoxLayout(in_game)
        self.game_label = QLabel("게임 중 — 채팅은 오버레이에서 확인하세요")
        self.live = QListWidget()  # 이번 게임 처리 내역 (실시간)
        lay.addWidget(self.game_label)
        lay.addWidget(self.live)

        # POST_GAME: 이번 게임 결과 화면
        post = QWidget()
        lay = QVBoxLayout(post)
        lay.addWidget(QLabel("이번 게임 결과"))
        self.reports = QListWidget()  # 화자별 신고 문구
        self.complaints = QListWidget()  # 화자별 고소장 초안
        self.btn_copy_report = QPushButton("선택한 신고 문구 복사")
        self.btn_open_complaint = QPushButton("선택한 고소장 PDF 열기")
        self.btn_close_result = QPushButton("닫기")  # → 대기(IDLE)
        lay.addWidget(QLabel("신고 문구 (복사해서 게임 신고창에 붙여넣기, 자동 신고 안 함)"))
        lay.addWidget(self.reports)
        lay.addWidget(QLabel("고소장 초안 (법률 자문이 아닙니다)"))
        lay.addWidget(self.complaints)
        for b in (self.btn_copy_report, self.btn_open_complaint, self.btn_close_result):
            lay.addWidget(b)

        self._page_for = {GamePhase.IDLE: idle, GamePhase.IN_GAME: in_game, GamePhase.POST_GAME: post}
        for page in self._page_for.values():
            self.pages.addWidget(page)

    @Slot(bool)
    def show_capture_settings(self, needed: bool) -> None:
        self.permission_settings.setVisible(needed)
        self.reveal_app.setVisible(needed and sys.platform == "darwin" and getattr(sys, "frozen", False))

    @Slot()
    def reveal_capture_app(self) -> None:
        bundle = Path(sys.executable).parents[2]
        subprocess.Popen(["/usr/bin/open", "-R", str(bundle)])

    @Slot()
    def open_capture_settings(self) -> None:
        url = QUrl("x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture")
        QDesktopServices.openUrl(url)

    @Slot(QImage)
    def show_preview(self, image: QImage) -> None:
        if image.isNull():
            self.preview_count = 0
            self.preview_info.setText("캡처 미리보기")
            self.preview_image.setText("캡처 대기 중")
            return
        self.preview_count += 1
        stamp = QTime.currentTime().toString("HH:mm:ss.zzz")
        self.preview_info.setText(f"캡처 {self.preview_count} · {stamp} · {image.width()} × {image.height()} px")
        size = image.size().boundedTo(self.preview_image.contentsRect().size())
        pixmap = QPixmap.fromImage(image).scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.preview_image.setPixmap(pixmap)

    def show_phase(self, phase: GamePhase, session: GameSession | None) -> None:
        """단계에 맞는 화면으로 바꾼다 (동작함). 세부 표시는 아래 스텁들이 채운다."""
        self.pages.setCurrentWidget(self._page_for[phase])

    def add_incident(self, inc: Incident) -> None:
        """게임 중 화면의 실시간 내역에 1건 추가: 시각 · 화자 · 원문 · 등급 · 처리 결과.

        예) "13:00:04 불꽃남자 | 미드 시1발 개못하네 | L2 | 숨김·신고"
        주의: 판단하지 말고 Decision 을 그대로 보여 주기만. 원문 표시는 클라이언트에서만(오버레이에는 표시 금지).
        """
        self.live.addItem(f"{inc.msg.speaker} · {inc.decision.display_text or '숨김'}")
        if self.live.count() > 200:
            self.live.takeItem(0)

    def show_result(self, result: PostGameResult) -> None:
        """'이번 게임 결과' 화면 채우기: reports 목록(화자 + 문구 앞부분), complaints 목록(화자 + PDF 경로).

        예) 신고 2건(불꽃남자, 얼음땡), 고소장 1건(얼음땡)
        """
        for widget, drafts in ((self.reports, result.reports), (self.complaints, result.complaints)):
            widget.clear()
            for draft in drafts:
                widget.addItem(draft.speaker)
                widget.item(widget.count() - 1).setData(Qt.UserRole, draft)
            if drafts:
                widget.setCurrentRow(0)

    def copy_selected_report(self) -> None:
        """선택한 신고 문구 전체를 클립보드로 (ADR-0007: 복사만, 자동 신고 금지)."""
        if item := self.reports.currentItem():
            QApplication.clipboard().setText(item.data(Qt.UserRole).text)

    def open_selected_complaint(self) -> None:
        """선택한 고소장 PDF 를 기본 프로그램으로 열기 (또는 저장 위치 선택)."""
        if (item := self.complaints.currentItem()) and (path := item.data(Qt.UserRole).pdf_path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(resolve_repo_path(path))))

    def show_engine_error(self, message: str) -> None:
        """엔진이 멈췄다는 안내 (예: "모듈 'parse' 구현이 아직 없습니다 ..."). 상태 표시줄과 게임 중 화면에 보여 준다."""
        self.statusBar().showMessage(f"⏳ {message}")
        self.game_label.setText(f"멈춤 — {message}")

    def load_history(self, session_ids: list[str]) -> None:
        """대기 화면에 지난 게임 목록 표시 (세션 저장소 list_ids)."""
        self.history.clear()
        self.history.addItems(session_ids)
