"""챔피언 → 주로 가는 라인 (대상 추정용).

채팅은 `닉네임 (챔피언): 내용` 으로만 들어와서 누가 정글인지 알 수 없다. "정글 ㅂㅅ아" 의 정글이 누구인지는
그 판의 챔피언들 중 누가 주로 정글을 가는지로 추정한다. 라인은 자주 가는 순서로 적는다(첫 글자가 주 라인).
  T 탑 · J 정글 · M 미드 · B 원딜 · S 서폿
메타가 바뀌면 이 표만 고친다. 표에 없는 챔피언은 "모름"으로 처리된다.

챔피언 목록은 라이엇 Data Dragon 16.23.1 한국어 목록(173명, 2026-11 기준 최신 — 2025-11 자헨, 2026-06 로크까지)과
대조했다(tests/test_analyze.py 의 개수 검사). 새 챔피언이 나오면 `_TABLE` 에 한 줄 추가하고 그 숫자를 올린다.
  https://ddragon.leagueoflegends.com/cdn/<버전>/data/ko_KR/champion.json
"""

from __future__ import annotations

_ROLE = {"T": "TOP", "J": "JUNGLE", "M": "MIDDLE", "B": "BOTTOM", "S": "UTILITY"}

_TABLE = """
가렌 T|갈리오 MS|갱플랭크 T|그라가스 JTM|그레이브즈 J|그웬 TJ|나르 T|나미 S|나서스 T|나피리 JM|노틸러스 S|녹턴 J
누누와윌럼프 J|누누 J|니달리 J|니코 SM|닐라 B|다리우스 T|다이애나 JM|드레이븐 B|라이즈 MT|라칸 S|람머스 J|럭스 SM
럼블 TJM|레나타글라스크 S|레나타 S|레넥톤 T|레오나 S|렉사이 J|렐 S|렝가 J|로크 M|루시안 BM|룰루 S|르블랑 M|리신 J|리븐 T
리산드라 M|릴리아 J|마스터이 J|마이 J|마오카이 SJT|말자하 M|말파이트 T|멜 M|모데카이저 T|모르가나 S|문도박사 TJ|문도 TJ
미스포츈 B|미포 B|밀리오 S|바드 S|바루스 B|바이 J|베이가 MB|베인 BT|벡스 M|벨베스 J|벨코즈 SM|볼리베어 TJ|브라움 S
브라이어 J|브랜드 SJM|블라디미르 MT|블리츠크랭크 S|블츠 S|비에고 J|빅토르 M|뽀삐 JTS|사미라 B|사이온 T|사일러스 MJ
샤코 J|세나 SB|세라핀 SB|세주아니 J|세트 T|소나 S|소라카 S|쉔 TS|쉬바나 J|스몰더 B|스웨인 SM|스카너 J|시비르 B
신짜오 J|신드라 M|신지드 T|쓰레쉬 S|아리 M|아무무 JS|아우렐리온솔 M|아이번 J|아지르 M|아칼리 MT|아크샨 M|아트록스 T
아펠리오스 B|알리스타 S|암베사 TJ|애니 M|애니비아 M|애쉬 BS|야스오 MTB|에코 JM|엘리스 J|오공 JT|오로라 MT|오른 T
오리아나 M|올라프 TJ|요네 MT|요릭 T|우디르 JT|우르곳 T|워윅 JT|유나라 B|유미 S|이렐리아 TM|이블린 J|이즈리얼 B
일라오이 T|자르반4세 J|자르반 J|자야 B|자이라 SJ|자크 J|자헨 TJ|잔나 S|잭스 TJ|제드 MJ|제라스 SM|제리 B|제이스 TM|조이 M
직스 BM|진 B|질리언 SM|징크스 B|초가스 T|카르마 S|카밀 T|카사딘 M|카서스 J|카시오페아 M|카이사 B|카직스 J
카타리나 M|칼리스타 B|케넨 T|케이틀린 B|케인 J|케일 T|코그모 B|코르키 MB|퀸 T|크산테 T|클레드 T|키아나 JM
킨드레드 J|타릭 S|탈론 MJ|탈리야 JM|탐켄치 TS|트런들 JT|트리스타나 BM|트린다미어 T|트위스티드페이트 M|트페 M
트위치 B|티모 T|파이크 S|판테온 STJM|피들스틱 J|피오라 T|피즈 M|하이머딩거 TMS|헤카림 J|흐웨이 M
"""

CHAMPION_ROLES: dict[str, tuple[str, ...]] = {
    name: tuple(_ROLE[c] for c in codes)
    for name, codes in (entry.split() for entry in _TABLE.replace("\n", "|").split("|") if entry.strip())
}

# 정식 이름 → 채팅에서 줄여 부르는 말. AI 가 쓴 초안이라 롤을 하는 팀원의 검수가 필요하다.
# 일상 낱말과 겹치는 줄임말(다리·모르·말자·오리·트리·나서·알리·올라·소라·그라)은 오탐이 커서 넣지 않았다.
# "카사" 는 보통 카이사를 가리킨다(카사딘은 줄이지 않고 부른다).
_ALIAS_TABLE = """
갱플랭크 갱플|그레이브즈 그브|노틸러스 노틸|니달리 니달|다이애나 다이아나|드레이븐 드븐|레넥톤 레넥|루시안 루샨
르블랑 블랑|리산드라 리산|마스터이 마이|마오카이 마오|말파이트 말파|모데카이저 모데|문도박사 문도|미스포츈 미포
벨코즈 벨코|볼리베어 볼베 볼리|블라디미르 블라디|블리츠크랭크 블츠 블리츠 블크|사일러스 사일|세주아니 세주
신짜오 짜오|쓰레쉬 쓰레|아무무 무무|아우렐리온솔 아솔 아우솔|아트록스 아트|아펠리오스 아펠|야스오 야스
이렐리아 이렐|이즈리얼 이즈|일라오이 일라|자르반4세 자르반 잘반|초가스 초가|카이사 카사|카시오페아 카시
카타리나 카타|칼리스타 칼리|케이틀린 케틀 케이틀|크산테 크산|킨드레드 킨드|탐켄치 탐켄|트리스타나 트타
트린다미어 트린 트린다|트위스티드페이트 트페|판테온 판테|피들스틱 피들|하이머딩거 하이머 딩거|헤카림 헤카
누누와윌럼프 누누|레나타글라스크 레나타|람머스 람머|아칼리 아칼|카직스 카직|피오라 피오|이블린 이블
우르곳 울곳|쉬바나 쉬바|모르가나 모르가|세라핀 세라|스몰더 스몰|암베사 암베|우디르 우디|트런들 트런
신드라 신드|빅토르 빅토|애니비아 애니비|카서스 카서|그라가스 그라가
"""
ALIASES: dict[str, tuple[str, ...]] = {
    names[0]: tuple(names[1:])
    for names in (entry.split() for entry in _ALIAS_TABLE.replace("\n", "|").split("|") if entry.strip())
}
_CANONICAL: dict[str, str] = {alias: name for name, aliases in ALIASES.items() for alias in aliases}
for _alias, _name in _CANONICAL.items():  # 줄임말도 같은 라인으로 찾을 수 있게
    CHAMPION_ROLES.setdefault(_alias, CHAMPION_ROLES.get(_name, ()))
# 명단 없이 문장만 보고 챔피언으로 보기에는 일상 낱말과 겹치는 이름 ("진 거 같다", "세트 맞추자", "오른 쪽")
AMBIGUOUS: frozenset[str] = frozenset(
    {"진", "바이", "애니", "세트", "오른", "퀸", "멜", "렐", "소나", "케일", "자크", "나르"}
)


def canonical(name: str | None) -> str:
    """줄임말 → 정식 이름. 모르는 이름은 그대로. 예) "이즈" → "이즈리얼", "리 신" → "리신\""""
    word = (name or "").replace(" ", "")
    return _CANONICAL.get(word, word)


def names_of(champion: str | None) -> tuple[str, ...]:
    """챔피언을 가리키는 모든 말 (정식 이름 + 줄임말). 예) "케이틀린" → ("케이틀린", "케틀", "케이틀")"""
    name = canonical(champion)
    return (name, *ALIASES.get(name, ())) if name else ()


def roles_of(champion: str | None) -> tuple[str, ...]:
    """챔피언이 주로 가는 라인 (자주 가는 순서). 모르면 빈 튜플. 예) "리 신" → ("JUNGLE",)"""
    return CHAMPION_ROLES.get((champion or "").replace(" ", ""), ())
