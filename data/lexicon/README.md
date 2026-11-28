# 우회어 사전

- `bypass.csv`: `variant`(변형) → `canonical`(원형). parse 모듈의 정규화(`modules/parse/normalization.py`)가 사용합니다.
- 누구나 PR로 추가할 수 있습니다. 한 줄에 하나씩, `note`에 종류(영타/초성/변형/OCR오인식)를 적어 주세요.
- 원형(canonical)은 analyze 의 사전(`modules/analyze/lexicon.py`)에 있는 낱말로 맞춰야 합니다.
- 한글 변형은 문장 안 어디에 있어도 바뀝니다. 평범한 낱말에 들어 있을 수 있는 짧은 표기(예: `시바` → 시바견)는 넣지 않습니다.
- 글자 사이에 숫자·기호를 끼운 표기(`시1발`, `ㅅ1발`)는 끼운 것을 뺀 꼴(`시발`, `ㅅ발`)이 사전에 있으면 자동으로 찾습니다.
