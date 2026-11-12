# 데이터와 모델 공유 방법

## 원칙
1. **git에는 작고 우리가 직접 만든 텍스트만** 올립니다(라벨 CSV, 우회어 사전, 데모 시나리오).
2. **크거나 민감한 것은 git 밖**에 둡니다(모델, 스크린샷, 영상, 외부 데이터셋, 실행 기록).
3. **실제 다른 유저의 채팅과 닉네임은 어디에도 모으지 않습니다.** 학습과 데모 예문은 모두 팀이 직접 쓴 가상 문장입니다.

## 어디에 무엇을 두나

| 데이터 | 만드는 곳 | 공유 위치 | git |
|---|---|---|---|
| 라벨 데이터 (학습용) | 구글 시트 (팀 공용) | CSV로 내보내 `data/labeled/batch_<이름>_<번호>.csv` | ✅ |
| 테스트셋 (시험 문제) | 라벨 데이터에서 **먼저** 200문장 분리 | `data/eval/test.csv` | ✅ |
| 우회어 사전 | 누구나 | `data/lexicon/bypass.csv` | ✅ |
| 데모 시나리오 | 발표 대본에 맞춰 작성 | `data/demo/*.jsonl` | ✅ |
| 외부 공개 데이터셋 | 다운로드 | `data/raw/` (로컬) | ❌ |
| OCR 샘플 스크린샷·녹화 | **팀원끼리 한 사용자 설정 게임**에서 캡처 | 구글 드라이브 `LoLGuard/ocr_samples/` → `data/ocr_samples/` | ❌ |
| 학습된 분류 모델 | Colab에서 학습 | **Hugging Face 비공개 저장소** → `models/` | ❌ |
| 로컬 LLM | Ollama 등 | 각자 PC에서 내려받기 (OPEN-04) | ❌ |
| 처리 내역, 고소장 PDF | 앱 실행 중 생성 | 사용자 PC `.lolguard/` | ❌ (절대 금지) |

## 라벨링 흐름 (비개발자 포함 전원)
1. 구글 시트 탭 하나를 1인 1탭으로 씁니다. 열 규칙은 `docs/LABELING_GUIDE.md`를 따릅니다.
2. 100문장을 채우면 담당(개발자 B)이 CSV로 내보내 `data/<주제>` 브랜치로 PR합니다.
3. **테스트셋은 처음 모인 데이터에서 먼저 떼어 고정합니다.** 이후 학습에 절대 섞지 않습니다.

## 외부 데이터셋 후보 (classify 담당이 확인)
| 이름 | 내용 | 확인할 것 |
|---|---|---|
| Korean UnSmile (스마일게이트) | 혐오·악플 다중 라벨 | 라이선스(비상업 조건 여부), 공개 모델 존재 여부 |
| Korean Hate Speech (kocohub) | 연예 뉴스 댓글 혐오·편견 | 라이선스 |
| K-MHaS | 다중 라벨 혐오 표현 | 라이선스 |

→ 사용하기로 한 데이터는 이 표에 **라이선스와 다운로드 방법**을 적고, `training/download_data.py`로 받을 수 있게 합니다.
→ 공개 데이터는 게임 채팅이 아니므로 **롤 말투(포지션, 챔피언, 줄임말)는 우리 라벨 데이터로 보완**해야 합니다.

## 모델 공유 (Hugging Face 비공개 저장소)
```bash
# 올리기 (classify 담당)
huggingface-cli login
huggingface-cli upload <팀계정>/lolguard-classifier ./models/classifier --private

# 받기 (모두) — scripts/download_models.py 로 자동화 예정
huggingface-cli download <팀계정>/lolguard-classifier --local-dir models/classifier
```
- 팀원은 Hugging Face 조직(Organization)에 초대해서 비공개 저장소를 같이 씁니다.
- 모델을 바꾸면 `classify/__init__.py`의 `MODEL_VERSION`을 올립니다.
