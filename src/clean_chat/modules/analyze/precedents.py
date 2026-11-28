"""판례 대조 파이프라인 (대화 판단의 마지막 단계). 고소 후보 사건에 요건 점검표와 비슷한 판례를 붙인다.

**법률 자문이 아니다.** 요건의 충족 여부는 채팅에서 확인되는 사실만으로 한 자동 추정이고, 고소 여부는 사람이 정한다.

흐름
  1) 수집 (오프라인, 한 번):  uv run python -m clean_chat.modules.analyze.precedents fetch --query 모욕 --limit 50
     법제처 국가법령정보 Open API(open.law.go.kr 에서 신청한 OC 값을 환경 변수 LAW_OC 로) → 판례 JSONL
  2) 색인:  load_index() 가 JSONL 을 읽어 글자 n-gram TF-IDF 색인을 만든다 (표준 라이브러리만, 새 패키지 없음)
  3) 대조:  review(CaseFacts, index) → 죄목별 요건 점검표 + 비슷한 판례 k 건

판례 파일: 기본 `data/raw/precedents.jsonl` (git 제외), 환경 변수 CLEAN_CHAT_PRECEDENTS 로 변경.
파일이 없으면 색인은 비어 있고 요건 점검표만 나온다. 이 레포에는 판례 본문을 넣지 않는다.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import urllib.parse
import urllib.request
from collections import Counter
from functools import cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from clean_chat.core.config import resolve_repo_path
from clean_chat.core.schemas import HarmType

DEFAULT_PATH = "data/raw/precedents.jsonl"
ENV_VAR = "CLEAN_CHAT_PRECEDENTS"
NOTICE = "법률 자문이 아닙니다. 채팅에서 확인되는 사실만으로 한 자동 점검이며, 고소 여부는 전문가와 확인하세요."

Status = Literal["충족", "불명", "미충족"]


# ── 데이터 형식 ──────────────────────────────────────────────
class Precedent(BaseModel):
    """판례 1건. 수집 단계(fetch)가 이 형식의 JSONL 로 저장한다."""

    id: str  # 판례일련번호
    charge: str = ""  # 수집할 때 쓴 검색어(죄목). 예) "모욕"
    case_name: str = ""
    case_no: str = ""  # 사건번호
    court: str = ""
    date: str = ""  # 선고일자
    summary: str  # 판시사항 + 판결요지 (대조에 쓰는 본문)
    source: str = ""  # 출처 주소


class SimilarPrecedent(BaseModel):
    precedent: Precedent
    similarity: float  # 0~1 (글자 n-gram TF-IDF 코사인)


class Requirement(BaseModel):
    name: str  # 예) "공연성"
    status: Status
    reason: str  # 채팅에서 확인된 사실


class LegalReview(BaseModel):
    """죄목 하나에 대한 점검 결과."""

    charge: str  # 예) "모욕"
    statute: str  # 예) "형법 제311조"
    requirements: list[Requirement]
    similar: list[SimilarPrecedent] = Field(default_factory=list)
    notice: str = NOTICE


class CaseFacts(BaseModel):
    """대화 판단이 넘겨주는 사실. 한 화자가 한 게임에서 한 말을 묶은 것."""

    speaker: str
    toward_me: bool  # 나를 향한 표현이 있었나
    channels: list[str]  # 근거 메시지가 나온 채널 ("team", "all")
    harm_types: list[HarmType]
    max_level: int  # 근거 메시지 중 가장 높은 등급
    count: int  # 근거 메시지 수
    texts: list[str] = Field(default_factory=list)  # 근거 메시지 원문 (비슷한 판례 검색에 사용)


# ── 색인과 검색 ──────────────────────────────────────────────
def _grams(text: str) -> Counter[str]:
    compact = "".join(text.split())
    return Counter(compact[i : i + n] for n in (2, 3) for i in range(len(compact) - n + 1))


class PrecedentIndex:
    """판례 요지의 글자 n-gram TF-IDF 색인. 수백~수천 건 규모를 가정한다 (게임 후 1번 실행)."""

    def __init__(self, precedents: list[Precedent]) -> None:
        self.precedents = precedents
        counts = [_grams(p.summary) for p in precedents]
        df = Counter(g for c in counts for g in c)
        n = max(len(precedents), 1)
        self._idf = {g: math.log((1 + n) / (1 + d)) + 1 for g, d in df.items()}
        self._vectors = [self._weigh(c) for c in counts]

    def __len__(self) -> int:
        return len(self.precedents)

    def _weigh(self, counts: Counter[str]) -> dict[str, float]:
        vec = {g: tf * self._idf[g] for g, tf in counts.items() if g in self._idf}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        return {g: v / norm for g, v in vec.items()}

    def search(self, query: str, charge: str | None = None, k: int = 3) -> list[SimilarPrecedent]:
        """query 와 요지가 비슷한 판례 k 건 (charge 를 주면 그 죄목으로 수집한 판례만)."""
        q = self._weigh(_grams(query))
        scored = [
            SimilarPrecedent(precedent=p, similarity=round(sum(w * vec.get(g, 0.0) for g, w in q.items()), 4))
            for p, vec in zip(self.precedents, self._vectors, strict=True)
            if charge is None or p.charge == charge
        ]
        return sorted((s for s in scored if s.similarity > 0), key=lambda s: -s.similarity)[:k]


def index_path() -> Path:
    return resolve_repo_path(os.environ.get(ENV_VAR) or DEFAULT_PATH)


@cache
def _load_index(path: Path) -> PrecedentIndex:
    if not path.exists():
        return PrecedentIndex([])
    lines = path.read_text(encoding="utf-8").splitlines()
    return PrecedentIndex([Precedent.model_validate_json(line) for line in lines if line.strip()])


def load_index(path: Path | None = None) -> PrecedentIndex:
    """판례 JSONL → 색인 (한 번만 읽음). 파일이 없으면 빈 색인."""
    return _load_index(path or index_path())


# ── 요건 점검 ────────────────────────────────────────────────
def review(facts: CaseFacts, index: PrecedentIndex | None = None, k: int = 3) -> list[LegalReview]:
    """사건 사실 → 해당할 수 있는 죄목별 요건 점검표 + 비슷한 판례. 해당 죄목이 없으면 빈 목록.

    점검 항목은 사람이 정리해 고쳐 나가는 표다(_insult, _obscenity). 판결문을 규칙으로 자동 변환한 것이 아니다.
    사실 적시가 필요한 명예훼손은 채팅만으로 판단할 수 없어 자동 점검하지 않는다.
    """
    index = index if index is not None else load_index()
    query = " ".join(facts.texts)
    reviews = []
    types = set(facts.harm_types)
    if types & {HarmType.PROFANITY, HarmType.FAMILY_INSULT, HarmType.BLAME, HarmType.INSTIGATION}:
        reviews.append(
            LegalReview(
                charge="모욕",
                statute="형법 제311조",
                requirements=_insult(facts),
                similar=index.search(query, "모욕", k),
            )
        )
    if HarmType.SEXUAL_HARASSMENT in types:
        reviews.append(
            LegalReview(
                charge="통신매체이용음란",
                statute="성폭력범죄의 처벌 등에 관한 특례법 제13조",
                requirements=_obscenity(facts),
                similar=index.search(query, "통신매체이용음란", k),
            )
        )
    if HarmType.THREAT in types:
        reviews.append(
            LegalReview(
                charge="협박",
                statute="형법 제283조",
                requirements=_threat(facts),
                similar=index.search(query, "협박", k),
            )
        )
    return reviews


def _threat(f: CaseFacts) -> list[Requirement]:
    """협박 요건 점검 (ADR-0021). 초안이며 법률가 검토가 필요하다."""
    reach = (
        Requirement(name="상대방에게 도달", status="충족", reason="나를 향한 채팅으로 화면에 표시됨")
        if f.toward_me
        else Requirement(name="상대방에게 도달", status="미충족", reason="나를 향한 표현이 확인되지 않음")
    )
    return [
        Requirement(
            name="해악의 고지",
            status="충족",
            reason="현실의 해악(찾아감·신상 공개·신체 위협 등)을 알리는 표현이 감지됨",
        ),
        reach,
        Requirement(
            name="공포심을 일으킬 정도",
            status="불명",
            reason="게임 중 감정적인 욕설·과장인지, 실제로 실행할 것처럼 구체적인지(주소·신상을 아는지 등) 판단 필요",
        ),
    ]


def _insult(f: CaseFacts) -> list[Requirement]:
    if "all" in f.channels:
        public = Requirement(name="공연성", status="충족", reason="전체 채팅에서 한 말이라 양 팀 모두 볼 수 있었음")
    else:
        public = Requirement(
            name="공연성", status="불명", reason="팀 채팅에서만 한 말 (팀원 4명이 봄) → 전파 가능성 판단 필요"
        )
    if f.toward_me:
        who = Requirement(
            name="특정성",
            status="불명",
            reason="나를 향한 말이지만 닉네임·챔피언으로만 지목됨 → 현실의 누구인지 알 수 있었는지 판단 필요",
        )
    else:
        who = Requirement(name="특정성", status="미충족", reason="나를 향한 표현이 확인되지 않음")
    if HarmType.FAMILY_INSULT in f.harm_types or f.max_level >= 3:
        insult = Requirement(name="모욕적 표현", status="충족", reason=f"가족 모욕 등 고강도 표현 {f.count}건")
    elif HarmType.PROFANITY in f.harm_types:
        insult = Requirement(
            name="모욕적 표현", status="불명", reason=f"욕설 {f.count}건 → 단순 욕설인지 인격 비하인지 판단 필요"
        )
    else:
        insult = Requirement(name="모욕적 표현", status="불명", reason="욕설 없는 비난·몰이 → 표현 수위 판단 필요")
    return [public, who, insult]


def _obscenity(f: CaseFacts) -> list[Requirement]:
    reach = (
        Requirement(name="상대방에게 도달", status="충족", reason="나를 향한 채팅으로 화면에 표시됨")
        if f.toward_me
        else Requirement(name="상대방에게 도달", status="미충족", reason="나를 향한 표현이 확인되지 않음")
    )
    return [
        Requirement(name="성적 수치심·혐오감을 일으키는 표현", status="충족", reason="성희롱 표현이 감지됨"),
        reach,
        Requirement(name="성적 욕망 유발·만족 목적", status="불명", reason="채팅만으로는 목적을 알 수 없음"),
    ]


# ── 수집 (오프라인) ──────────────────────────────────────────
API = "https://www.law.go.kr/DRF"


def _get(endpoint: str, **params: Any) -> dict[str, Any]:
    url = f"{API}/{endpoint}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=30) as res:  # noqa: S310 (고정된 https 주소)
        return json.loads(res.read().decode("utf-8"))


def fetch(query: str, oc: str, limit: int = 50) -> list[Precedent]:
    """법제처 Open API 로 판례를 검색해 요지를 가져온다. 네트워크를 쓰므로 앱·테스트에서는 부르지 않는다.

    주의: 실제 OC 값으로 실행해 확인하지 못했다. 응답 필드 이름은 open.law.go.kr 의 판례 API 안내와 맞춰 볼 것.
    """
    found: list[Precedent] = []
    page = 1
    while len(found) < limit:
        body = _get("lawSearch.do", OC=oc, target="prec", type="JSON", query=query, display=20, page=page)
        rows = body.get("PrecSearch", {}).get("prec", [])
        rows = [rows] if isinstance(rows, dict) else rows
        if not rows:
            break
        for row in rows[: limit - len(found)]:
            pid = str(row.get("판례일련번호", ""))
            detail = _get("lawService.do", OC=oc, target="prec", type="JSON", ID=pid).get("PrecService", {})
            summary = " ".join(str(detail.get(key) or "") for key in ("판시사항", "판결요지")).strip()
            if pid and summary:
                found.append(
                    Precedent(
                        id=pid,
                        charge=query,
                        case_name=str(row.get("사건명", "")),
                        case_no=str(row.get("사건번호", "")),
                        court=str(row.get("법원명", "")),
                        date=str(row.get("선고일자", "")),
                        summary=summary,
                        source=f"https://www.law.go.kr/LSW/precInfoP.do?precSeq={pid}",
                    )
                )
        page += 1
    return found


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="판례 수집 (법제처 Open API) → JSONL")
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch", help="검색어(죄목)로 판례를 받아 JSONL 에 덧붙인다")
    f.add_argument("--query", required=True, help='죄목. review() 가 쓰는 값: "모욕", "통신매체이용음란"')
    f.add_argument("--limit", type=int, default=50)
    f.add_argument("--out", type=Path, default=None, help=f"기본 {DEFAULT_PATH} (git 제외)")
    args = ap.parse_args(argv)
    oc = os.environ.get("LAW_OC")
    if not oc:
        print("환경 변수 LAW_OC 가 필요합니다 (open.law.go.kr 에서 Open API 신청 후 받은 값).", file=sys.stderr)
        return 2
    out = args.out or index_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    seen = {json.loads(line)["id"] for line in out.read_text(encoding="utf-8").splitlines()} if out.exists() else set()
    new = [p for p in fetch(args.query, oc, args.limit) if p.id not in seen]
    with out.open("a", encoding="utf-8") as fp:
        fp.writelines(p.model_dump_json() + "\n" for p in new)
    print(f"{len(new)}건 추가 → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
