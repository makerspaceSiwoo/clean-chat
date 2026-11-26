"""고소장 초안의 혐의 ID와 클라이언트가 표시할 이름·도움말."""

from enum import StrEnum
from typing import NamedTuple


class ChargeId(StrEnum):
    SEXUAL_MESSAGE = "tme"
    THREAT = "threat"
    COERCION = "coerce"
    EXTORTION = "extort"
    PRIVACY = "privacy"
    INSULT = "insult"
    DEFAMATION = "defame"


class ChargeInfo(NamedTuple):
    name: str
    description: str


CHARGE_CATALOG = {
    ChargeId.SEXUAL_MESSAGE: ChargeInfo(
        "통신매체이용음란죄", "성적인 표현을 누구에게 보냈는지 앞뒤 대화와 함께 확인하세요."
    ),
    ChargeId.THREAT: ChargeInfo("협박죄", "상대에게 해를 가하겠다고 한 발언의 시각과 원문을 확인하세요."),
    ChargeId.COERCION: ChargeInfo("강요죄", "요구한 행동과 그 전후에 주고받은 말을 확인하세요."),
    ChargeId.EXTORTION: ChargeInfo("공갈죄", "금품을 요구한 표현과 당시 대화를 함께 확인하세요."),
    ChargeId.PRIVACY: ChargeInfo("개인정보보호법 위반", "어떤 정보가 누구에게 공개되었는지 확인하세요."),
    ChargeId.INSULT: ChargeInfo("모욕죄", "비하 표현이 누구를 지칭했는지, 어느 채팅 채널이었는지 확인하세요."),
    ChargeId.DEFAMATION: ChargeInfo("명예훼손", "다른 사람에 관한 주장과 직접 확인한 사실을 구분해 기록하세요."),
}
