# -*- coding: utf-8 -*-
"""카드 뜻 44개를 **반말 한 줄로 미리 써서 파일에 굳힌다** (2026-09-24 사장님 지시).

    python 반말뜻만들기.py --한장 death     한 장만 만들어 본다 (저장 안 함)
    python 반말뜻만들기.py --전부           78장 x 정역 = 156줄
    python 반말뜻만들기.py --전부 --이어서   이미 있는 건 건너뛴다
    python 반말뜻만들기.py --본다           몇 줄 채워졌나

왜
    카드 뜻(`카드78.json` 의 upright_summary·reversed_summary)은 **사이트용 존댓말**이다.
    1턴 조립글에 그대로 박으면 "균형이 무너진 채 달리고 있습니다" 처럼 말투가 섞인다.

    그래서 44줄을 **한 번만** AI 로 반말 한 줄씩 만들어 `데이터/반말뜻.json` 에 굳힌다.
    그 뒤로 1턴 조립은 **영원히 토큰이 0** 이다.

표준 라이브러리만 쓴다. 팔자오빠 것을 하나도 부르지 않는다.
"""
from __future__ import annotations

import argparse
import io
import json
import re
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import 타로엔진 as 엔진

나갈곳 = HERE / "데이터" / "반말뜻.json"
MODEL = "sonnet"

SCHEMA = {
    "type": "object",
    "properties": {"upright": {"type": "string"}, "reversed": {"type": "string"}},
    "required": ["upright", "reversed"],
}

SYS = """너는 타로 스레드 계정(서른한 살 여자)의 말투로 카드 뜻을 한 줄로 줄이는 사람이다.

반드시
1. **반말.** "입니다" "습니다" "세요" 전부 금지.
2. **한 줄. 25자 안쪽.** 길면 못 쓴다.
3. **부호를 쓰지 않는다.** 마침표 쉼표 물음표 전부 없이 끝낸다.
4. 해설서 말투 금지. "의미해" "상징해" "나타낸다" 금지.
5. 단정 금지. "된다" "온다" 대신 "~자리" "~때" "~쪽" 같은 결로.
6. 카드 이름을 문장 안에 넣지 마라. 뜻만 쓴다.

좋은 예
    시간으로 이기는 판이야
    버티는 게 아니라 그냥 멈춰 있는 때
    답은 이미 안에 있는데 소리를 안 낸 자리

나쁜 예
    균형이 무너진 채 달리고 있습니다   (존댓말)
    이 카드는 인내를 의미해              (해설서 + 카드 언급)
    곧 좋은 소식이 옵니다                (단정)"""


def _토큰기록(out, 모델=""):
    """claude 응답에 실려 오는 토큰·값을 창고 토큰.log 에 한 줄 남긴다 (2026-09-24 사장님 지시 · 2026-09-25 R2 로).

    여기서 뭐가 터져도 본 흐름은 안 멈춘다. 통째로 try 로 감싸 놨다."""
    try:
        import datetime, os as _os
        u = (out or {}).get("usage") or {}
        줄 = "%s %s 입력%s 생성%s 읽기%s 출력%s $%.4f" % (
            datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 모델 or "?",
            u.get("input_tokens", 0),
            u.get("cache_creation_input_tokens", 0),
            u.get("cache_read_input_tokens", 0),
            u.get("output_tokens", 0),
            float((out or {}).get("total_cost_usd") or 0))
        import 창고                     # R2 창고 seoa/토큰.log (2026-09-25)
        창고.열기().붙이기("토큰.log", 줄)
    except Exception as e:
        print("   (토큰 기록 못 남김: %s)" % type(e).__name__)


def claude(prompt, timeout=180):
    cmd = ["claude", "-p", prompt, "--output-format", "json",
           "--json-schema", json.dumps(SCHEMA, ensure_ascii=False),
           "--model", MODEL, "--safe-mode", "--system-prompt", SYS,
           "--tools", "Read", "--disallowedTools", "Read"]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout,
                           encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL)
        if r.returncode != 0:
            return None
        out = json.loads(r.stdout)
        _토큰기록(out, MODEL)
        본문 = out.get("result", out)
        if isinstance(본문, str):
            본문 = json.loads(본문)
        return 본문
    except Exception:
        return None


def 검사(줄):
    t = (줄 or "").strip()
    if not t or len(t) > 30:
        return False
    for w in ("입니다", "습니다", "세요", "의미", "상징해", "나타낸", "."):
        if w in t:
            return False
    return True


def 한장만들기(card):
    p = """카드: %s %s
정방향 뜻: %s
역방향 뜻: %s

이 두 뜻을 각각 **반말 한 줄**로 줄여라.
upright 에 정방향, reversed 에 역방향을 넣어라. 설명하지 마라.""" % (
        card.get("roman", ""), card.get("ko", ""),
        (card.get("upright_summary") or "")[:300],
        (card.get("reversed_summary") or "")[:300])
    out = claude(p)
    if not out:
        return None
    바름 = (out.get("upright") or "").strip()
    거꾸로 = (out.get("reversed") or "").strip()
    if not (검사(바름) and 검사(거꾸로)):
        return None
    return {"정방향": 바름, "역방향": 거꾸로}


def 읽기():
    if not 나갈곳.exists():
        return {"_설명": "카드 뜻 반말 한 줄. 1턴 조립글이 쓴다 (조립.py). 토큰 아끼려고 미리 굳혀 둔 것"}
    return json.loads(io.open(나갈곳, encoding="utf-8").read())


def 쓰기(d):
    io.open(나갈곳, "w", encoding="utf-8").write(
        json.dumps(d, ensure_ascii=False, indent=2) + "\n")


def 전부(이어서=False):
    d = 읽기()
    for i, card in enumerate(엔진.CARDS, 1):
        슬러그 = card["slug"]
        if 이어서 and isinstance(d.get(슬러그), dict):
            print("[%2d/78] %-16s 있음" % (i, 슬러그))
            continue
        나온것 = None
        for _ in range(3):
            나온것 = 한장만들기(card)
            if 나온것:
                break
        if not 나온것:
            print("[%2d/78] %-16s 실패" % (i, 슬러그))
            continue
        d[슬러그] = 나온것
        쓰기(d)
        print("[%2d/78] %-16s 정 %s / 역 %s" % (i, 슬러그, 나온것["정방향"], 나온것["역방향"]))
    수 = sum(1 for k, v in d.items() if not k.startswith("_") and isinstance(v, dict))
    print("\n%d장 채움 → %s" % (수, 나갈곳.name))
    return 0


def main():
    ap = argparse.ArgumentParser(description="카드 뜻 반말로 굳히기")
    ap.add_argument("--한장", metavar="슬러그")
    ap.add_argument("--전부", action="store_true")
    ap.add_argument("--이어서", action="store_true")
    ap.add_argument("--본다", action="store_true")
    a = ap.parse_args()

    if a.본다:
        d = 읽기()
        수 = sum(1 for k, v in d.items() if not k.startswith("_") and isinstance(v, dict))
        print("%d장 채워짐" % 수)
        for k, v in d.items():
            if not k.startswith("_") and isinstance(v, dict):
                print("  %-16s 정 %-26s 역 %s" % (k, v["정방향"], v["역방향"]))
        return 0
    if a.한장:
        card = next((c for c in 엔진.CARDS if c["slug"] == a.한장), None)
        if not card:
            print("그런 카드가 없다")
            return 1
        나온것 = 한장만들기(card)
        print(나온것 or "실패")
        return 0
    if a.전부:
        return 전부(이어서=a.이어서)
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
