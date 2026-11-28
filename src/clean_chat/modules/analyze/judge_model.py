"""대화 판단(judge) 전용 모델 — 유저 한 명의 전체 채팅을 그 판의 대화 흐름과 함께 읽고 신고 권고 · 고소 후보 점수를 낸다.

실시간 필터의 모델(model.py)과 과제가 달라 모델도 따로 둔다.
  impl 모델   문장 1개(64토큰)        → 유형 5개 점수            `models/analyze-classifier/`
  judge 모델  게임 1판 문서(512토큰)   → report · complaint 점수   `models/analyze-judge/`   (환경 변수 CLEAN_CHAT_JUDGE_MODEL)

입력 문서는 유저마다 하나씩 만든다. 두 가지 방식이 있고 학습할 때 고른다(`--scope`, meta.json 의 `doc_scope`):
  context  그 판의 대화 전체에 대상의 말을 표시한다 (아래 예)
  own      대상 유저가 쓴 채팅만 모은다 — 문서가 짧아 적은 데이터로도 배우기 쉽지만, 맞장구("ㅇㅈ")가 무엇에 대한 것인지는 모른다
 같은 판이라도 "누구를 판단하는가"에 따라 표시가 달라진다.
    나: 나미 서폿 | 대상: 드레이븐 원딜 우리팀
    · 세트(우리): ㅎㅇ 즐겜합시다
    ▶ 드레이븐: 서폿 뭐 하냐                  ← 판단 대상이 한 말
    나(나미): 미안 와드 박을게                 ← 내가 한 말
    · 럭스(상대/전체): ez
킬뎃을 들먹이는 조롱, 맞장구, 반복처럼 한 문장으로는 알 수 없는 것을 흐름에서 배우게 하려는 것이다.

    uv run python -m clean_chat.modules.analyze.judge_model --data fixtures/analyze/judge_games.jsonl --version judge-kcelectra-0.1

학습 데이터가 게임 36판(유저 약 300명)뿐이라 규칙 판단(judge.py)을 대신하지 않고 **보완**한다. 모델이 없으면 규칙만으로 돈다.
torch · transformers 는 함수 안에서만 import 한다.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from clean_chat.core.config import resolve_repo_path
from clean_chat.core.schemas import ChatMessage, Player
from clean_chat.modules.analyze import model as base_model
from clean_chat.modules.analyze.champions import roles_of

logger = logging.getLogger(__name__)

DEFAULT_DIR = "models/analyze-judge"
ENV_VAR = "CLEAN_CHAT_JUDGE_MODEL"
LABELS = ["report", "complaint"]
MAX_LENGTH = 512
MAX_CHARS = 740  # 문서 글자 수 상한. KcELECTRA 토크나이저로 512토큰 안에 들어오게 잡은 값 (1자 ≈ 0.63토큰)
_ROLE_KO = {"TOP": "탑", "JUNGLE": "정글", "MIDDLE": "미드", "BOTTOM": "원딜", "UTILITY": "서폿"}


def model_dir() -> Path:
    return resolve_repo_path(os.environ.get(ENV_VAR) or DEFAULT_DIR)


def version() -> str | None:
    loaded = base_model._load(model_dir())
    return str(loaded["meta"].get("version", "unknown")) if loaded else None


def build_document(
    messages: list[ChatMessage],
    players: list[Player],
    my_name: str,
    user: str,
    max_chars: int = MAX_CHARS,
    scope: str = "context",
) -> str:
    """게임 1판의 채팅을 `user` 를 판단하기 위한 문서 하나로 만든다 (위 docstring 의 형식)."""
    by_name = {p.name: p for p in players}
    me, target = by_name.get(my_name), by_name.get(user)

    def who(name: str, champion: str | None = None) -> str:
        p = by_name.get(name)
        champ = ((p.champion if p else None) or champion or "?").replace(" ", "")
        role = (p.position if p else None) or next(iter(roles_of(champ)), "")
        return f"{champ} {_ROLE_KO.get(role, '')}".strip()

    def side(name: str) -> str:
        p = by_name.get(name)
        if me is None or p is None or not me.team or not p.team:
            return ""
        return "우리" if p.team == me.team else "상대"

    side_of_target = {"우리": " 우리팀", "상대": " 상대팀"}.get(side(user), "")
    header = f"나: {who(my_name)} | 대상: {who(user, target.champion if target else None)}{side_of_target}"
    if scope == "own":  # 대상 유저가 쓴 채팅만 (다른 사람의 말은 넣지 않는다). 전체 채팅이면 표시한다
        own = [
            f"▶{'(전체)' if m.channel == 'all' else ''} {m.text_norm or m.text}" for m in messages if m.speaker == user
        ]
        return "\n".join([header, *own])[: max_chars * 2]
    lines: list[tuple[bool, str]] = []  # (꼭 남길 줄인가, 내용)
    for m in messages:
        text = m.text_norm or m.text
        if m.speaker == user:
            lines.append((True, f"▶ {who(user, m.champion).split(' ')[0]}: {text}"))
        elif m.is_me or m.speaker == my_name:
            lines.append((True, f"나({who(my_name).split(' ')[0]}): {text}"))
        else:
            tag = "/".join(x for x in (side(m.speaker), "전체" if m.channel == "all" else "") if x)
            lines.append((False, f"· {who(m.speaker, m.champion).split(' ')[0]}{f'({tag})' if tag else ''}: {text}"))
    return "\n".join([header, *_fit(lines, max_chars)])


def _fit(lines: list[tuple[bool, str]], max_chars: int) -> list[str]:
    """문서가 모델 입력 길이를 넘지 않게 줄인다. 대상·나의 말은 남기고, 대상의 말에서 먼 다른 사람의 말부터 뺀다."""
    keep = [True] * len(lines)
    anchors = [i for i, (must, text) in enumerate(lines) if must and text.startswith("▶")] or [len(lines) - 1]
    order = sorted(
        (i for i, (must, _) in enumerate(lines) if not must),
        key=lambda i: -min(abs(i - a) for a in anchors),
    )
    size = sum(len(text) + 1 for _, text in lines)
    for i in order:
        if size <= max_chars:
            break
        keep[i] = False
        size -= len(lines[i][1]) + 1
    return [text for (_, text), k in zip(lines, keep, strict=True) if k]


def speakers(messages: list[ChatMessage], my_name: str) -> list[str]:
    """판단할 유저들: 한 번이라도 말한 사람(나 제외), 처음 말한 순서."""
    seen: list[str] = []
    for m in messages:
        if not m.is_me and m.speaker != my_name and m.speaker not in seen:
            seen.append(m.speaker)
    return seen


def predict(messages: list[ChatMessage], players: list[Player], my_name: str) -> dict[str, dict[str, float]]:
    """유저별 점수. 예) {"불꽃남자": {"report": 0.93, "complaint": 0.08}}. 모델이 없거나 실패하면 빈 dict."""
    loaded = base_model._load(model_dir())
    users = speakers(messages, my_name)
    if loaded is None or not users:
        return {}
    try:
        torch, meta = loaded["torch"], loaded["meta"]
        scope = str(meta.get("doc_scope", "context"))
        docs = [build_document(messages, players, my_name, u, scope=scope) for u in users]
        scores: dict[str, dict[str, float]] = {}
        with torch.no_grad():
            for i in range(0, len(docs), 4):  # 한 판에 최대 9명 → 3번에 나눠 돌린다
                batch = loaded["tokenizer"](
                    docs[i : i + 4],
                    padding=True,
                    truncation=True,
                    max_length=int(meta.get("max_length", MAX_LENGTH)),
                    return_tensors="pt",
                )
                probs = torch.sigmoid(loaded["net"](**batch).logits).tolist()
                for user, row in zip(users[i : i + 4], probs, strict=True):
                    scores[user] = {label: round(float(p), 4) for label, p in zip(meta["labels"], row, strict=True)}
        return scores
    except Exception:
        logger.exception("judge 모델 실행 실패 → 이 판은 규칙만 사용")
        return {}


def examples_from_games(games: list[dict], scope: str = "context") -> list[tuple[str, list[float]]]:
    """게임 데이터(judge_games.jsonl 의 한 줄씩) → (유저별 문서, [report, complaint]). 말한 적 없는 유저는 뺀다.

    scope="context" 는 그 판의 대화 전체에 대상의 말을 표시한 문서, "own" 은 대상 유저가 쓴 채팅만 모은 문서.
    """
    from clean_chat.modules.analyze.judge_evaluate import to_request  # 순환 import 를 피하려고 함수 안에서

    out: list[tuple[str, list[float]]] = []
    for game in games:
        req = to_request(game)
        for user in speakers(req.messages, req.my_name):
            gold = game.get("labels", {}).get(user, {})
            doc = build_document(req.messages, req.players, req.my_name, user, scope=scope)
            out.append((doc, [1.0 if gold.get(label) else 0.0 for label in LABELS]))
    return out


def main(argv: list[str] | None = None) -> int:
    from clean_chat.modules.analyze import train
    from clean_chat.modules.analyze.judge_evaluate import load_games

    ap = argparse.ArgumentParser(description="judge 모델 파인튜닝 (게임 단위 대화 데이터의 train 게임만 사용)")
    ap.add_argument("--data", type=Path, required=True, help="fixtures/analyze/judge_games.jsonl")
    ap.add_argument("--base", default="beomi/KcELECTRA-base")
    ap.add_argument("--out", type=Path, default=Path(DEFAULT_DIR))
    ap.add_argument("--version", required=True)
    ap.add_argument("--epochs", type=int, default=15)
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--lr", type=float, default=3e-5)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--patience", type=int, default=5)
    ap.add_argument(
        "--scope", choices=["context", "own"], default="context", help="입력 문서: 대화 전체 / 대상 유저의 채팅만"
    )
    args = ap.parse_args(argv)
    examples = examples_from_games(load_games(args.data, "train"), args.scope)
    train.train(
        [args.data],
        args.base,
        args.out,
        args.version,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        max_length=MAX_LENGTH,
        seed=args.seed,
        patience=args.patience,
        labels=LABELS,
        examples=examples,
        extra_meta={"doc_scope": args.scope},
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
