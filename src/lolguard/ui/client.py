"""[뼈대 · ui 담당] 클라이언트 창 (SPEC 3-1): 시작/중지, 사용법, 처리 내역, 신고 복사, 고소장 PDF"""

from PySide6.QtWidgets import QLabel, QListWidget, QMainWindow, QPushButton, QVBoxLayout, QWidget

from lolguard.core.schemas import Incident


class ClientWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("LoL Guard")
        root = QWidget()
        lay = QVBoxLayout(root)
        lay.addWidget(QLabel("LoL Guard — 처리 내역"))
        self.history = QListWidget()  # TODO: 표(QTableWidget)로 — 시간·화자·원문·등급·처리
        lay.addWidget(self.history)
        self.btn_start = QPushButton("감시 시작")  # TODO: Engine 시작/중지 연결
        self.btn_report = QPushButton("신고 문구 복사")  # TODO: report Stage 호출 → 클립보드
        self.btn_complaint = QPushButton("고소장 PDF 저장")  # TODO: complaint Stage 호출 → 저장 위치 선택
        for b in (self.btn_start, self.btn_report, self.btn_complaint):
            lay.addWidget(b)
        self.setCentralWidget(root)
        # TODO: 사용법 안내 탭 (테두리 없는 창 모드, 채팅 색 설정, 오버레이 위치 맞추기)

    def add_incident(self, inc: Incident) -> None:
        # TODO: 판단하지 말고 Decision 을 그대로 보여 주기만
        self.history.addItem(f"[{inc.decision.action}] {inc.msg.speaker}: {inc.msg.raw}")
