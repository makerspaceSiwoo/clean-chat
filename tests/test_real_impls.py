"""실제 구현(impl.py) 테스트. 아직 미구현이면 skip → 구현하는 순간 자동으로 검사가 시작됨.

- 모든 모듈: 출력이 스키마에 맞는지
- STRICT 모듈: expected.jsonl 과 정확히 같아야 함 (규칙 기반이라 결과가 정해진 모듈)
- AI 모듈(classify/rewrite 등)은 정확도를 training/evaluate 로 따로 측정
"""

import pytest

from clean_chat.core import registry
from clean_chat.core.config import FIXTURES, STAGE_NAMES
from clean_chat.core.platform import PlatformNotSupported
from clean_chat.core.stage import read_jsonl

STRICT = {"parse", "policy"}
SKIP_FIXTURE_MISSING = {"ocr"}  # 이미지 파일이 들어오기 전까지


@pytest.mark.parametrize("name", STAGE_NAMES)
def test_real_impl(name):
    iface = registry.interface(name)
    ins = read_jsonl(FIXTURES / name / "input.jsonl", iface.input_model)
    exp = read_jsonl(FIXTURES / name / "expected.jsonl", iface.output_model)
    if name in SKIP_FIXTURE_MISSING and not (FIXTURES / "ocr" / "images" / "sample_01.png").exists():
        pytest.skip("OCR 테스트 이미지 없음")
    stage = registry.create(name, "real")
    try:
        stage.setup()
        outs = [stage.run(x) for x in ins]
    except NotImplementedError:
        pytest.skip(f"{name}: 아직 미구현")
    except PlatformNotSupported:
        pytest.skip(f"{name}: Windows 전용")
    for o in outs:
        assert isinstance(o, iface.output_model)
    if name in STRICT:
        assert outs == exp
