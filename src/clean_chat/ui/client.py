"""[구성 · 리드] 클라이언트 창 (SPEC 3-1). 게임 단계마다 다른 화면을 보여 준다 (HANDOFF 5-2).

| 단계        | 화면                                              |
|------------|---------------------------------------------------|
| IDLE       | 지난 처리 내역, 설정, 사용법                          |
| IN_GAME    | "게임 중" 안내 (채팅은 오버레이에서)                   |
| POST_GAME  | "이번 게임 결과": 신고 문구 복사, 고소장 PDF, 닫기      |
판단하지 않고 Decision / PostGameResult 를 그대로 보여 주기만 한다.
"""

from PySide6.QtWidgets import (
    QLabel,
    QListWidget,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from clean_chat.core.schemas import GamePhase, GameSession, Incident, PostGameResult


class ClientWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Clean Chat")
        self.pages = QStackedWidget()
        self.setCentralWidget(self.pages)

        # IDLE: 대기 화면
        idle = QWidget()
        lay = QVBoxLayout(idle)
        lay.addWidget(QLabel("Clean Chat — 게임을 시작하면 자동으로 감시합니다"))
        self.history = QListWidget()  # 지난 처리 내역 (세션 저장소에서 불러옴). TODO: 표(QTableWidget)
        lay.addWidget(self.history)
        self.btn_settings = QPushButton("설정 (내 소환사명, 오버레이 위치)")
        self.btn_guide = QPushButton("사용법 (테두리 없는 창 모드, 채팅 색)")
        lay.addWidget(self.btn_settings)
        lay.addWidget(self.btn_guide)

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

    def show_phase(self, phase: GamePhase, session: GameSession | None) -> None:
        """단계에 맞는 화면으로 바꾼다 (동작함). 세부 표시는 아래 스텁들이 채운다."""
        self.pages.setCurrentWidget(self._page_for[phase])

    def add_incident(self, inc: Incident) -> None:
        """게임 중 화면의 실시간 내역에 1건 추가: 시각 · 화자 · 원문 · 등급 · 처리 결과.

        예) "13:00:04 원딜러 | 미드 시1발 개못하네 | L2 | 숨김·신고"
        주의: 판단하지 말고 Decision 을 그대로 보여 주기만. 원문 표시는 클라이언트에서만(오버레이에는 표시 금지).
        """
        raise NotImplementedError("ui 담당: add_incident")

    def show_result(self, result: PostGameResult) -> None:
        """'이번 게임 결과' 화면 채우기: reports 목록(화자 + 문구 앞부분), complaints 목록(화자 + PDF 경로).

        예) 신고 2건(원딜러, 상대탑), 고소장 1건(상대탑)
        """
        raise NotImplementedError("ui 담당: show_result")

    def copy_selected_report(self) -> None:
        """선택한 신고 문구 전체를 클립보드로 (ADR-0007: 복사만, 자동 신고 금지)."""
        raise NotImplementedError("ui 담당: copy_selected_report")

    def open_selected_complaint(self) -> None:
        """선택한 고소장 PDF 를 기본 프로그램으로 열기 (또는 저장 위치 선택)."""
        raise NotImplementedError("ui 담당: open_selected_complaint")

    def show_engine_error(self, message: str) -> None:
        """엔진이 멈췄다는 안내 (예: "모듈 'parse' 구현이 아직 없습니다 ..."). 상태 표시줄과 게임 중 화면에 보여 준다."""
        self.statusBar().showMessage(f"⏳ {message}")
        self.game_label.setText(f"멈춤 — {message}")

    def load_history(self, session_ids: list[str]) -> None:
        """대기 화면에 지난 게임 목록 표시 (세션 저장소 list_ids)."""
        raise NotImplementedError("ui 담당: load_history")
