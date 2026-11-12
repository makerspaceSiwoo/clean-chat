# training/ — 분류 모델 학습 (classify 담당)

Mac에서는 GPU 학습이 어렵기 때문에 **Google Colab(무료 T4 GPU)** 에서 학습합니다.

## 순서
1. `download_data.py`: 외부 공개 데이터 → `data/raw/` (라이선스는 docs/DATA.md에 기록)
2. `train.ipynb`: KcBERT/KcELECTRA 계열 → 다중 라벨(유해 유형) + 등급 + 피드백 포함 여부
   - 1단계: 공개 데이터로 학습한 모델을 그대로 써서 기준 성능 측정
   - 2단계: `data/labeled/`(롤 말투)로 추가 학습
3. `evaluate.py`: `data/eval/test.csv` 기준 정확도, 유형별 점수, 틀린 예시 리포트 → `training/reports/`
4. 모델 → Hugging Face 비공개 저장소 업로드 → `classify/__init__.py`의 `MODEL_VERSION` 갱신

## 규칙
- 입력은 반드시 `normalize`를 거친 `text_norm`으로 학습합니다(실행 시와 똑같은 전처리).
- `data/eval/`은 학습에 절대 넣지 않습니다.
- 노트북에 토큰이나 키를 남기지 않습니다.
