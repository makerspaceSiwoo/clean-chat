"""첫 실행 준비 화면: Gemini API 키 입력(필수) + analyze 모델 내려받기. 둘 다 끝나야 앱을 시작한다.

준비 여부 판단과 내려받기는 core/setup.py 가 한다. 이 화면은 입력을 받고 진행 상황만 보여 준다.
"""

from __future__ import annotations

import threading
from types import ModuleType

from PySide6.QtCore import QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLineEdit, QProgressBar, QVBoxLayout, QWidget

from clean_chat.core import setup
from clean_chat.core.config import current_llm_key, save_llm_settings, settings
from clean_chat.ui.client_widgets import STYLE, button, card, label, restyle

KEY_URL = "https://aistudio.google.com/apikey"
MB = 1000 * 1000


class SetupDialog(QDialog):
    downloaded = Signal(str)  # 내려받기가 끝남. 실패하면 오류 문장, 성공이면 빈 문자열
    sized = Signal(int)  # 받을 전체 크기(바이트)를 알아냄

    def __init__(self, ops: ModuleType = setup, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ops = ops
        self.total = 0
        self.error = ""
        self.model_state = "ready"  # ready · downloading · failed · unavailable(패키지 없음)
        self.setWindowTitle("Clean Chat · 처음 설정")
        self.setStyleSheet(
            STYLE
            + "QDialog {background:#F7F8FA;} QProgressBar {border:0;background:#EEF0F3;border-radius:4px;}"
            + "QProgressBar::chunk {background:#2457D6;border-radius:4px;}"
        )
        self.setMinimumWidth(560)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 20)
        root.setSpacing(14)
        root.addWidget(label("처음 설정", "title"))
        root.addWidget(label("아래 두 가지가 준비되면 Clean Chat 을 시작합니다. 한 번만 하면 됩니다.", "muted"))
        self._build_key_card(root)
        self._build_model_card(root)
        actions = QHBoxLayout()
        self.btn_quit = button("종료")
        self.btn_start = button("시작하기", "primary")
        self.btn_start.setDefault(True)
        actions.addWidget(self.btn_quit)
        actions.addStretch(1)
        actions.addWidget(self.btn_start)
        root.addLayout(actions)
        self.btn_quit.clicked.connect(self.reject)
        self.btn_start.clicked.connect(self._finish)
        self.downloaded.connect(self._download_finished)
        self.sized.connect(self._set_total)
        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self._show_progress)
        self._start_models()
        self._refresh()

    # ── Gemini API 키 ─────────────────────────────────────────
    def _build_key_card(self, root: QVBoxLayout) -> None:
        box, body = card("1. Gemini API 키 (필수)")
        body.addWidget(
            label(
                "욕설에 섞인 게임 피드백을 공손한 문장으로 바꾸고 고소장 초안을 쓰는 데 씁니다. "
                "키는 이 PC에만 저장되고, 순화할 채팅 문장은 Google Gemini 로 전송됩니다.",
                "muted",
            )
        )
        self.saved_key = current_llm_key(settings.llm_env)
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.Password)
        self.key.setAccessibleName("Gemini API 키")
        self.key.setPlaceholderText(
            "저장된 키가 있습니다 · 바꾸려면 새 키 입력" if self.saved_key else "API 키 붙여넣기"
        )
        self.key.textChanged.connect(self._key_changed)
        body.addWidget(self.key)
        row = QHBoxLayout()
        self.key_status = label("", "caption")
        link = button("Google AI Studio 에서 키 발급", "link")
        link.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(KEY_URL)))
        row.addWidget(self.key_status, 1)
        row.addWidget(link)
        body.addLayout(row)
        root.addWidget(box)

    def _key_changed(self) -> None:
        restyle(self.key, invalid=False)
        self._refresh()

    # ── analyze 모델 ──────────────────────────────────────────
    def _build_model_card(self, root: QVBoxLayout) -> None:
        box, body = card("2. 채팅 분석 모델")
        body.addWidget(label("악성 채팅을 판단하는 모델입니다. 처음 한 번만 내려받습니다 (약 440MB).", "muted"))
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(8)
        body.addWidget(self.progress)
        row = QHBoxLayout()
        self.model_status = label("", "caption")
        self.btn_retry = button("다시 시도", "link")
        self.btn_retry.clicked.connect(self._start_models)
        row.addWidget(self.model_status, 1)
        row.addWidget(self.btn_retry)
        body.addLayout(row)
        root.addWidget(box)

    def _start_models(self) -> None:
        if not self.ops.runtime_ready():
            self.model_state = "unavailable"
        elif not self.ops.missing_models():
            self.model_state = "ready"
        else:
            self.model_state = "downloading"
            self.timer.start()
            threading.Thread(target=self._download, daemon=True, name="model-download").start()
        self._refresh()

    def _download(self) -> None:
        """작업 스레드. 화면은 Signal 로만 바꾼다."""
        try:
            self.sized.emit(self.ops.expected_bytes())
            self.ops.download_models()
            self.downloaded.emit("")
        except Exception as exc:  # 네트워크 끊김 등 → 화면에 알리고 다시 시도할 수 있게
            self.downloaded.emit(f"{type(exc).__name__}: {exc}"[:200])

    def _set_total(self, total: int) -> None:
        self.total = total

    def _show_progress(self) -> None:
        done = self.ops.downloaded_bytes()
        if self.total:
            self.progress.setRange(0, 1000)
            self.progress.setValue(min(1000, done * 1000 // self.total))
            self.model_status.setText(f"내려받는 중 · {done // MB} / {self.total // MB} MB")
        else:
            self.progress.setRange(0, 0)  # 전체 크기를 알기 전에는 움직이는 막대
            self.model_status.setText(f"내려받는 중 · {done // MB} MB")

    def _download_finished(self, error: str) -> None:
        self.timer.stop()
        self.model_state = "failed" if error or self.ops.missing_models() else "ready"
        self.error = error or "파일이 모두 받아지지 않았습니다."
        self._refresh()

    # ── 상태 표시 · 완료 ──────────────────────────────────────
    def _refresh(self) -> None:
        typed = self.key.text().strip()
        if typed:
            self.key_status.setText("시작하기를 누르면 저장합니다.")
        else:
            self.key_status.setText(
                "저장된 키를 사용합니다." if self.saved_key else "키를 입력해야 시작할 수 있습니다."
            )
        self.btn_retry.setVisible(self.model_state == "failed")
        if self.model_state == "ready":
            self.progress.setRange(0, 1000)
            self.progress.setValue(1000)
            self.model_status.setText("준비됨")
        elif self.model_state == "failed":
            self.progress.setRange(0, 1000)
            self.model_status.setText(f"내려받지 못했습니다 · {self.error} · 인터넷 연결을 확인하고 다시 시도하세요.")
        elif self.model_state == "unavailable":
            self.progress.setRange(0, 1000)
            self.progress.setValue(0)
            self.model_status.setText(
                f"모델 실행 패키지(analyze)가 없어 규칙만으로 판단합니다. 설치: {self.ops.INSTALL_HINT}"
            )
        else:
            self._show_progress()
        self.btn_start.setEnabled(bool(typed or self.saved_key) and self.model_state in ("ready", "unavailable"))

    def _finish(self) -> None:
        typed = self.key.text().strip()
        if typed:
            try:
                save_llm_settings(typed, settings.llm_env)
            except (OSError, ValueError) as exc:
                restyle(self.key, invalid=True)
                self.key_status.setText(f"저장하지 못했습니다 · {exc}")
                return
        self.accept()
