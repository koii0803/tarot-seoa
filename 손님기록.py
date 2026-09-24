# -*- coding: utf-8 -*-
"""손님과 몇 번째 주고받기인지 센다 (2026-09-23 사장님 확정: 3턴 규칙).

    1턴 · 2턴 → 앞면 그림. 카드 보여주고 풀이 + 되물음
    3턴      → 뒷면 그림. "마지막 한 장" 이라고 하고 프로필로 안내
    4턴 이상 → 답하지 않는다 (사람에게 넘긴다)

    python 손님기록.py --볼것 eslyn_yes          이 손님은 지금 몇 턴인가
    python 손님기록.py --기록 eslyn_yes --카드 "죽음 역방향"
    python 손님기록.py --목록                    지금까지 답해준 손님들
    python 손님기록.py --목록 --손님 eslyn_yes    한 사람 것만

밖에서 쓸 때
    from 손님기록 import 이번턴, 기록하기
    계획 = 이번턴("손님아이디")
    계획["턴"]        1 · 2 · 3 · 4…
    계획["그림"]      "앞면" · "뒷면" · None
    계획["답할까"]    False 면 답하지 않는다
    계획["마지막"]    True 면 이번이 마지막 카드다 (프로필 안내를 넣는다)

왜 필요한가
    3턴째에 뒷면을 주려면 **지금이 몇 턴인지 알아야 한다.** 기록이 없으면 영원히 1턴이다.
    답글을 내보낸 **뒤에** 반드시 기록한다. 안 적으면 다음이 어긋난다.

표준 라이브러리만 쓴다. 팔자오빠 것을 하나도 부르지 않는다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import 창고

기록이름 = "손님기록.jsonl"        # R2 창고 seoa/ 아래 (2026-09-25 PC 파일에서 옮김)

# 2026-09-24 사장님 지시로 바꿨다. **대화가 길수록 스레드가 더 퍼뜨린다.**
# 3턴에서 자르면 알고리즘이 밀어줄 대화를 우리 손으로 끊는 꼴이다.
# 팔자오빠도 같은 이유로 한 사람 최대를 3 → 10 으로 늘렸다.
안내턴 = 3             # 이 턴에 뒷면 + 프로필 안내. **한 대화에 딱 한 번만**
최대턴 = 10            # 여기까지 답한다. 넘으면 사람이 본다
앞면턴 = (1, 2)        # 안내턴 앞. 그 뒤(4턴~)도 앞면으로 계속 답한다


def 지금():
    """서울 시각."""
    return dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=9)


def _읽기():
    return 창고.열기().줄들(기록이름)


def _손님키(손님):
    """@ 붙여 쓰든 안 붙이든, 대문자로 쓰든 같은 사람으로 본다."""
    return str(손님 or "").strip().lstrip("@").lower()


def _같은자리(줄, 키, 글아이디):
    """이 줄이 같은 손님·같은 글인가.

    **글이 다르면 다른 대화다** (2026-09-24). 예전 기록엔 글아이디가 없어서
    그때 것은 글을 안 따진다 — 안 그러면 옛 손님이 전부 1턴으로 돌아간다.
    """
    if 줄.get("손님") != 키 or 줄.get("종류", "타로") == "인사":
        return False
    적힌글 = 줄.get("글아이디")
    if not 적힌글 or not 글아이디:
        return True                      # 예전 기록이거나 글을 안 넘겨준 자리
    return 적힌글 == 글아이디


def 지난턴(손님, 글아이디=""):
    """이 손님에게 **이 글에서** 지금까지 타로로 답해준 횟수.

    칭찬·인사 답글은 안 센다 (2026-09-24). 3턴 규칙은 진짜 질문에만 건다.
    글이 다르면 처음부터 다시 센다 — 그 글타래엔 앞 카드가 없기 때문이다.
    """
    키 = _손님키(손님)
    return sum(1 for x in _읽기() if _같은자리(x, 키, 글아이디))


def 이번턴(손님, 글아이디=""):
    """이번에 답하면 몇 턴이고 그림은 뭘 보내야 하나.

        1·2턴   앞면. 그냥 풀어준다
        3턴     뒷면 + 프로필 안내. **딱 한 번만** 한다
        4~10턴  다시 앞면. 안내는 반복하지 않는다 (두 번 하면 영업이 된다)
        11턴~   답하지 않는다. 사람이 본다
    """
    턴 = 지난턴(손님, 글아이디) + 1
    if 턴 == 안내턴:
        그림, 답할까, 마지막 = "뒷면", True, True
    elif 턴 <= 최대턴:
        그림, 답할까, 마지막 = "앞면", True, False
    else:
        그림, 답할까, 마지막 = None, False, False
    return {"손님": _손님키(손님), "턴": 턴, "그림": 그림,
            "답할까": 답할까, "마지막": 마지막}


def 기록하기(손님, 카드="", 방향="", 그림="", 댓글="", 글="", 때=None, 종류="타로",
             글아이디=""):
    """답글을 **내보낸 뒤** 적는다. 이걸 적어야 다음 턴이 맞는다."""
    키 = _손님키(손님)
    턴 = 지난턴(키, 글아이디) + 1
    줄 = {"때": (때 or 지금()).isoformat(timespec="minutes"),
          "손님": 키, "턴": 턴, "종류": 종류, "카드": 카드, "방향": 방향, "그림": 그림,
          # **어느 글에서 오간 말인지.** 이게 있어야 턴을 글 단위로 센다 (2026-09-24)
          "글아이디": 글아이디,
          # 2026-09-24: 대화를 **통째로** 남긴다. 2턴부터 AI 에게 넘겨야 해서 잘라두면 못 쓴다
          "댓글": (댓글 or "").strip(),
          "글": (글 or "").strip(),
          "첫줄": (글 or "").strip().splitlines()[0][:40] if 글 else ""}
    창고.열기().붙이기(기록이름, json.dumps(줄, ensure_ascii=False))
    return 줄


def 지난대화(손님, 몇턴=12, 글아이디=""):
    """이 손님과 오간 말 전부. **2턴부터 이걸 AI 에게 통째로 넘긴다.**

    앞에 무슨 말이 오갔는지 모르면 매번 처음 만난 사람처럼 답한다.
    사람처럼 보이는 건 카드 지식이 아니라 **앞에 한 말을 기억하는 것**이다.
    """
    키 = _손님키(손님)
    줄들 = [x for x in _읽기() if _같은자리(x, 키, 글아이디)][-몇턴:]
    오간말 = []
    for x in 줄들:
        if x.get("댓글"):
            오간말.append(("손님", x["댓글"]))
        if x.get("글"):
            오간말.append(("나", x["글"]))
    return 오간말


def 오늘답한수(날=None):
    """오늘 내보낸 답글 수. 하루 상한을 여기서 센다 (2026-09-24 사장님 지시: 998건)."""
    날 = 날 or 지금().strftime("%Y-%m-%d")
    return sum(1 for x in _읽기() if (x.get("때") or "").startswith(날))


def 손님들():
    """손님별 턴 수. 많이 온 사람 먼저."""
    셈 = {}
    for x in _읽기():
        셈[x.get("손님", "")] = 셈.get(x.get("손님", ""), 0) + 1
    return sorted(셈.items(), key=lambda kv: -kv[1])


def 사람말(계획):
    if not 계획["답할까"]:
        return "%d턴째다. 3턴에서 끝났으니 답하지 않는다 (사람이 볼 것)" % 계획["턴"]
    if 계획["마지막"]:
        return "%d턴째 — **마지막 카드**. 뒷면을 보내고 프로필로 안내한다" % 계획["턴"]
    return "%d턴째 — 앞면을 보내고 풀이 + 되물음으로 끝낸다" % 계획["턴"]


def main():
    ap = argparse.ArgumentParser(description="손님과 몇 번째 주고받기인지 센다")
    ap.add_argument("--볼것", metavar="손님", help="이 손님은 지금 몇 턴인가")
    ap.add_argument("--기록", metavar="손님", help="답글 내보낸 뒤 적는다")
    ap.add_argument("--카드", default="")
    ap.add_argument("--방향", default="")
    ap.add_argument("--그림", default="")
    ap.add_argument("--댓글", default="")
    ap.add_argument("--목록", action="store_true")
    ap.add_argument("--손님", metavar="손님", help="--목록 을 한 사람 것만")
    a = ap.parse_args()

    if a.목록:
        줄들 = _읽기()
        if a.손님:
            줄들 = [x for x in 줄들 if x.get("손님") == _손님키(a.손님)]
        if not 줄들:
            print("아직 답해준 게 없다")
            return 0
        for x in 줄들:
            print("%s  %-18s %d턴  %-14s %-4s %s" % (
                x["때"], x.get("손님", ""), x.get("턴", 0),
                x.get("카드", ""), x.get("그림", ""), x.get("댓글", "")))
        print("—")
        for 이름, 수 in 손님들():
            print("  %-18s %d턴" % (이름, 수))
        return 0

    if a.기록:
        줄 = 기록하기(a.기록, 카드=a.카드, 방향=a.방향, 그림=a.그림, 댓글=a.댓글)
        print("적었다: %s %d턴 (%s %s)" % (줄["손님"], 줄["턴"], 줄["카드"], 줄["그림"]))
        return 0

    if a.볼것:
        계획 = 이번턴(a.볼것)
        print("손님 %s" % 계획["손님"])
        print("→ " + 사람말(계획))
        print("   그림: %s" % (계획["그림"] or "없음"))
        return 0 if 계획["답할까"] else 1

    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
