"""[구현 · WP8] 세션 저장소: 게임 1판 기록을 .clean-chat/sessions/<id>.jsonl 로 저장·조회 (로컬 전용, git 제외).

core/game.py 의 SessionRepository 포트를 따른다. 구현 전까지 앱은 MemorySessionRepository 를 쓴다.
"""

from __future__ import annotations

from pathlib import Path

from clean_chat.core.schemas import GameSession


class JsonlSessionRepository:
    """[구현 · WP8] SessionRepository 어댑터 (파일 1개 = 세션 1개)"""

    def __init__(self, root: Path) -> None:
        """root: 저장 폴더 (settings.sessions_dir). 없으면 save 때 만든다."""
        self.root = Path(root)

    def save(self, session: GameSession) -> None:
        """세션 전체를 <root>/<id>.jsonl 에 저장 (덮어쓰기).

        입력: GameSession → 출력: 없음 (파일)
        예) id="20251112-125820" → .clean-chat/sessions/20251112-125820.jsonl
        형식: 1줄 = 세션 머리말(id, started_at, ended_at, players), 다음 줄부터 Incident 1개씩 (사람이 읽고 고칠 수 있게)
        주의: 쓰는 도중 앱이 꺼져도 파일이 깨지지 않게 임시 파일에 쓰고 이름을 바꾼다. 실제 채팅 원문이 들어가므로 git 금지.
        관련: HANDOFF 5-2, docs/DATA.md
        """
        raise NotImplementedError("session 담당: save")

    def load(self, session_id: str) -> GameSession:
        """<root>/<id>.jsonl → GameSession. 없으면 KeyError."""
        raise NotImplementedError("session 담당: load")

    def list_ids(self) -> list[str]:
        """저장된 세션 id 목록 (오래된 순). 클라이언트의 '지난 처리 내역' 화면이 쓴다."""
        raise NotImplementedError("session 담당: list_ids")

    def _path(self, session_id: str) -> Path:
        """세션 id → 파일 경로. id 에 경로 문자(/, ..)가 있으면 거부."""
        raise NotImplementedError
