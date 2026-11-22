"""Windows 내장 OCR 브리지. 별도 패키지 없이 PowerShell 프로세스를 재사용한다."""

from __future__ import annotations

import atexit
import base64
import io
import json
import queue
import subprocess
import threading
from pathlib import Path


class WindowsOcr:
    """PNG를 메모리로 전달한다. 이미지나 원문을 파일에 저장하지 않는다."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._responses: queue.Queue[str | None] = queue.Queue()
        command = base64.b64encode(
            Path(__file__).with_suffix(".ps1").read_text(encoding="utf-8").encode("utf-16-le")
        ).decode("ascii")
        self._process = subprocess.Popen(
            ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-EncodedCommand", command],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        threading.Thread(target=self._receive, daemon=True).start()
        atexit.register(self.close)

    def _receive(self) -> None:
        for line in self._process.stdout:
            self._responses.put(line)
        self._responses.put(None)

    def read(self, image: object) -> list[tuple[str, None]]:
        """위→아래로 정렬한 줄을 반환한다. 내장 엔진은 신뢰도를 제공하지 않는다."""
        return [(line["text"], None) for line in self.read_blocks(image)]

    def read_blocks(self, image: object) -> list[dict]:
        """이미지 내 좌표도 반환해 보조 인식에서 기존 줄과 반복 자모 줄을 구분한다."""
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        request = json.dumps({"image": base64.b64encode(buffer.getvalue()).decode("ascii")})
        with self._lock:
            if self._process.poll() is not None:
                raise RuntimeError("Windows OCR 프로세스가 종료됐습니다. 앱을 다시 시작하세요.")
            try:
                self._process.stdin.write(request + "\n")
                self._process.stdin.flush()
                response = self._responses.get(timeout=20)
            except (OSError, queue.Empty) as exc:
                self.close()
                raise RuntimeError("Windows OCR 응답 실패 또는 시간 초과") from exc
            if response is None:
                raise RuntimeError("Windows OCR 시작 실패: Windows PowerShell과 한국어 OCR 언어 팩을 확인하세요.")
            payload = json.loads(response)
            if "error" in payload:
                raise RuntimeError(f"Windows OCR: {payload['error']}")
            return sorted(payload["lines"], key=lambda line: (line["y"], line["x"]))

    def close(self) -> None:
        """종료·오류 때 백그라운드 프로세스와 파이프를 회수한다."""
        if self._process.poll() is None:
            self._process.terminate()
            self._process.wait()
        for stream in (self._process.stdin, self._process.stdout):
            if stream is not None:
                stream.close()
