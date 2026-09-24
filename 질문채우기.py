# -*- coding: utf-8 -*-
"""카드별 되물음을 채운다 — 경우의 수를 확 늘리는 자리 (2026-09-24 사장님 지시).

    지금까지: 유형 8 x 시제 3 x 3벌 = **72줄**. 카드가 뭐든 같은 되물음이 나왔다.
    채우고 나면: 카드 78 x 유형 8 x 2개 = **352줄**. 카드마다 결이 갈린다.

    python 질문채우기.py --한장 death      한 장만 만들어 본다 (저장 안 함)
    python 질문채우기.py --전부            78장 전부 채운다 (오래 걸린다)
    python 질문채우기.py --전부 --이어서    이미 채운 카드는 건너뛴다
    python 질문채우기.py --본다            지금 몇 줄 채워졌나

채운 것은 `데이터/카드별질문.json` 에 들어가고, 엔진이 **카드 고유를 먼저** 쓴다.
없는 칸은 예전처럼 유형x시제로 내려간다. 그래서 중간에 끊겨도 돈다.

표준 라이브러리만 쓴다. 팔자오빠 것을 하나도 부르지 않는다.
"""
from __future__ import annotations

import argparse
import io
import json
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

질문파일 = HERE / "데이터" / "카드별질문.json"
MODEL = "sonnet"          # 되물음은 계정 목소리다. 싼 모델로 하면 티가 난다
한유형당 = 2

# 스키마 키는 영문이어야 한다. 한글 키를 쓰면 API 가 400 을 낸다
SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ask": {"type": "string"},
                    "qs": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["ask", "qs"],
            },
        }
    },
    "required": ["items"],
}

SYS = """너는 타로 스레드 계정의 되물음을 만드는 사람이다. 서른한 살 여자의 결로 쓴다.

되물음이란
    손님이 "될까요?" 하고 물으면, 답을 주는 대신 손님이 스스로 보게 만드는 한 줄 질문이다.
    답을 정해주지 않는다. 손님 쪽으로 공을 넘긴다.

반드시
1. 전부 물음표로 끝난다.
2. 반말. "입니다" "세요" "~나요?" 금지.
3. 한 줄. 30자 안쪽. 길면 안 읽는다.
4. 미래를 단정하지 않는다. 맞힌다는 말 금지.
5. 상담사 말투 금지. "그랬구나" "힘들었겠다" 금지.
6. 해설서 말투 금지. "의미해" "상징해" 금지.
7. 애교 금지. ㅎㅎ ㅋㅋ ㅠㅠ 이모지 금지. 줄표 금지.

말투
    약간의 여성미. 딱딱한 "뭐야?" 대신 "뭘까?". 군데군데 "혹시" "조금".

제일 중요한 것
    **그 카드에서만 나올 수 있는 질문이어야 한다.**
    아무 카드에나 붙는 일반적인 질문은 실패다.
    카드의 뜻과 방향을 질문 안에 녹여라. 단, 카드 이름은 질문에 쓰지 마라."""


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


def claude(prompt, timeout=240):
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


def 프롬프트(card, 방향):
    상징 = card.get("symbolPoints") or []
    상징글 = chr(10).join("    - %s : %s" % (x.get("part", ""), x.get("means", ""))[:120] for x in 상징[:4])
    요약 = card.get("upright_summary" if 방향 == "정방향" else "reversed_summary") or ""
    유형들 = " · ".join(엔진.ASK_TYPES)
    return """카드: %s %s (%s)
뜻: %s

그림 안에 있는 것
%s

이 카드가 **%s**으로 나왔을 때 쓸 되물음을 만들어라.
질문유형 %d가지 각각에 %d줄씩.

유형: %s

items 에 {"ask": 유형이름, "qs": [질문1, 질문2]} 를 유형 수만큼 넣어라.
ask 는 위 유형 이름을 그대로 쓴다. 설명하지 마라.""" % (
        card.get("roman", ""), card.get("ko", ""), 방향, 요약[:300],
        상징글, 방향, len(엔진.ASK_TYPES), 한유형당, 유형들)


def 검사(줄):
    t = (줄 or "").strip()
    if not t.endswith("?"):
        return False
    if len(t) > 40:
        return False
    for w in ("입니다", "세요", "나요?", "습니까", "—", "ㅎㅎ", "ㅋㅋ", "ㅠ"):
        if w in t:
            return False
    return True


def 한장만들기(슬러그):
    card = next((c for c in 엔진.CARDS if c["slug"] == 슬러그), None)
    if not card:
        return None
    나온것 = {}
    for 방향 in ("정방향", "역방향"):
        out = claude(프롬프트(card, 방향))
        if not out:
            print("    %s 실패" % 방향)
            continue
        for x in out.get("items", []):
            유형 = (x.get("ask") or "").strip()
            if 유형 not in 엔진.ASK_TYPES:
                continue
            좋은것 = [q.strip() for q in (x.get("qs") or []) if 검사(q)]
            if 좋은것:
                나온것.setdefault(유형, []).extend(좋은것)
    return 나온것


def 읽기():
    return json.loads(io.open(질문파일, encoding="utf-8").read())


def 쓰기(d):
    io.open(질문파일, "w", encoding="utf-8").write(
        json.dumps(d, ensure_ascii=False, indent=2) + "\n")


def 세기(d=None):
    d = d or 읽기()
    수 = 0
    카드수 = 0
    for k, v in d.items():
        if k.startswith("_") or not isinstance(v, dict):
            continue
        카드수 += 1
        for 줄들 in v.values():
            수 += len(줄들) if isinstance(줄들, list) else 0
    return 카드수, 수


def 전부(이어서=False):
    d = 읽기()
    d["_현재"] = "채우는 중 (질문채우기.py)"
    for i, card in enumerate(엔진.CARDS, 1):
        슬러그 = card["slug"]
        if 이어서 and isinstance(d.get(슬러그), dict) and d[슬러그]:
            print("[%2d/78] %-16s 이미 있음, 건너뜀" % (i, 슬러그))
            continue
        print("[%2d/78] %-16s 만드는 중…" % (i, 슬러그))
        나온것 = 한장만들기(슬러그)
        if not 나온것:
            print("        실패")
            continue
        d[슬러그] = 나온것
        쓰기(d)      # 한 장 끝날 때마다 저장. 중간에 끊겨도 남는다
        print("        %d유형 %d줄" % (len(나온것), sum(len(v) for v in 나온것.values())))
    카드수, 수 = 세기(d)
    d["_현재"] = "카드 %d장 · %d줄 채움 (질문채우기.py)" % (카드수, 수)
    쓰기(d)
    print("\n다 됐다: 카드 %d장 · 되물음 %d줄" % (카드수, 수))
    return 0


def main():
    ap = argparse.ArgumentParser(description="카드별 되물음 채우기")
    ap.add_argument("--한장", metavar="슬러그", help="한 장만 만들어 본다 (저장 안 함)")
    ap.add_argument("--전부", action="store_true")
    ap.add_argument("--이어서", action="store_true", help="이미 채운 카드는 건너뛴다")
    ap.add_argument("--본다", action="store_true")
    a = ap.parse_args()

    if a.본다:
        카드수, 수 = 세기()
        print("카드 %d장 · 되물음 %d줄" % (카드수, 수))
        return 0
    if a.한장:
        나온것 = 한장만들기(a.한장)
        if not 나온것:
            print("못 만들었다")
            return 1
        for 유형, 줄들 in 나온것.items():
            print("\n[%s]" % 유형)
            for q in 줄들:
                print("  " + q)
        return 0
    if a.전부:
        return 전부(이어서=a.이어서)
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
