"""시뮬레이터 테스트용 가짜 모듈 함수 (worker 가 CLEAN_CHAT_SIM_TARGET 으로 불러 씀)."""

import logging
import time

from clean_chat.core.schemas import ParseRequest, ParseResult


def ok(req: ParseRequest) -> ParseResult:
    print("디버그 출력: 줄 분해 시작")
    logging.getLogger("fake").info("로그도 콘솔로")
    return ParseResult(line_id=req.line.id, message=None)


def boom(req: ParseRequest) -> ParseResult:
    print("곧 터짐")
    raise ValueError("일부러 낸 오류")


def slow(req: ParseRequest) -> ParseResult:
    print("오래 걸림", flush=True)
    time.sleep(30)
    return ParseResult(line_id=req.line.id, message=None)


def wrong_type(req: ParseRequest) -> dict:
    return {"line_id": req.line.id}
