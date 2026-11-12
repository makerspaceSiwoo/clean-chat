# 아직 정해지지 않은 것 / 실측이 필요한 것

> 결정되면 `docs/DECISIONS.md`에 ADR로 옮기고, 여기에는 "→ ADR-00xx"라고 표시합니다.

| ID | 질문 | 선택지 | 누가 | 언제까지 |
|---|---|---|---|---|
| OPEN-01 | OCR이 막히면 대안은? | (a) Overwolf `chat` 이벤트(기록 금지 조건 확인) (b) 데모는 녹화 영상 OCR | 리드 | OCR 실측 직후 |
| OPEN-02 | 오버레이가 캡처에서 빠지는가? (ADR-0003) | (a) `WDA_EXCLUDEFROMCAPTURE` (b) 게임 창만 캡처(Windows Graphics Capture) | capture + ui | **주말 #2 전** |
| OPEN-03 | OCR 엔진 | (a) Windows 내장 OCR(한국어, 빠름) (b) PaddleOCR (c) EasyOCR → 정확도와 속도로 비교 | capture | 주말 #2 전 |
| OPEN-04 | LLM(리라이트, 고소장 요약)을 어디서 돌리나 | (a) 로컬(Ollama + 한국어 소형 모델) (b) 외부 API (c) 데모는 API, 기본은 rule | 리드 + rewrite | 주말 #2 전 |
| OPEN-05 | 클립보드 붙여넣기 대신 자동 입력이 가능한가 | 실측 전까지 클립보드 고정 (ADR-0006) | ui | 여유 있을 때 |
| OPEN-06 | 롤 채팅 설정(색, 배경, 크기)으로 OCR 정확도를 얼마나 올릴 수 있나 | 설정 조합별 스크린샷 비교 | capture | 주말 #2 |
| OPEN-07 | L1(경미)은 마스킹해서 보여 줄까, 그대로 보여 줄까 | 현재 가정: 마스킹 | 팀 | 주말 #2 |
| OPEN-08 | 고소장의 법적 요건(피해자 특정성 등)을 데모에서 어떻게 설명하나 | 발표 Q&A용 정리 | report | 주말 #3 |
| OPEN-09 | "핑"은 어디까지 다루나 | 채팅창에 **글자로** 찍히는 핑과 스펠 체크만 (지도 위 핑은 범위 밖) | parse | 주말 #2 |
| OPEN-10 | 발표용 PC에서 롤 + 분류 모델 + LLM을 동시에 돌릴 수 있나 | 사양 확인 후 OPEN-04 결정에 반영 | 리드 | 주말 #2 |
| OPEN-11 | 대상 추정에 쓸 플레이어 명단 | Live Client Data API `playerlist` (게임 중에만, 로컬) | 리드 | 주말 #2 |
| OPEN-12 | LCU 게임 진행 단계 이름과 전환 시점 | `InProgress`/`EndOfGame` 외 `Reconnect`, `WaitingForStats`, `PreEndOfGame` 등이 언제 오는지 실측 → `session/windows.py: _to_game_phase` 표, 튕김 시 처리(지금 가정: 게임 중 대기가 10초 이상 계속되면 게임 종료, `settings.idle_grace_sec`) | session(WP8) | 주말 #2 전 |
| OPEN-13 | 내가 보낸 채팅이 OCR로 다시 읽혔다는 판단 기준 | 지금 가정: 내 채팅이고 60초 안에 보낸 문장과 본문이 같으면 건너뜀(`core/pipeline.py: SentLog`). OCR 오타·잘림을 고려해 유사도로 바꿀지 | 리드 + capture | 주말 #2 |
