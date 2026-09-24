# -*- coding: utf-8 -*-
"""글과 글 사이 간격을 지킨다 (2026-09-23 사장님 지시: 최소 4시간).

    python 발행기록.py --확인                지금 올려도 되나
    python 발행기록.py --기록 한장            방금 올린 것을 적는다
    python 발행기록.py --기록 한장 --때 "2026-09-23 20:40"
    python 발행기록.py --목록                지금까지 올린 것

밖에서 쓸 때
    from 발행기록 import 올릴수있나, 기록하기

왜 필요한가
    스레드는 같은 계정이 짧은 간격으로 글을 쏟으면 노출을 깎는다.
    그리고 팔자오빠 봇도 4~37분 지연을 두고 답한다. 봇 티가 나면 안 된다.
    이 파일은 규칙을 글로만 적어두지 않고 기계가 막게 한다.

표준 라이브러리만 쓴다. 팔자오빠 것을 하나도 부르지 않는다.
"""
from __future__ import annotations

import io
import sys
import json
import argparse
import datetime as dt
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
기록방 = HERE / "기록"
기록파일 = 기록방 / "발행기록.jsonl"

최소간격시간 = 3          # 사장님 지시 2026-09-24: **최소 3시간**. 보통은 4~5시간으로 짠다


def 지금():
    """서울 시각."""
    return dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=9)


def _읽기():
    if not 기록파일.exists():
        return []
    줄들 = []
    with io.open(기록파일, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    줄들.append(json.loads(line))
                except Exception:
                    pass
    return 줄들


def 마지막발행():
    """마지막으로 올린 것. 없으면 None."""
    줄들 = _읽기()
    return 줄들[-1] if 줄들 else None


def 올릴수있나(기준=None):
    """(올려도되나, 남은분, 마지막것) 을 준다."""
    기준 = 기준 or 지금()
    마지막 = 마지막발행()
    if not 마지막:
        return True, 0, None
    지난때 = dt.datetime.fromisoformat(마지막["때"])
    if 지난때.tzinfo is None:
        지난때 = 지난때.replace(tzinfo=기준.tzinfo)
    지난분 = (기준 - 지난때).total_seconds() / 60
    남은 = int(최소간격시간 * 60 - 지난분)
    return (남은 <= 0), max(0, 남은), 마지막


def 기록하기(종류, 글="", 카드="", 때=None, 소재=""):
    """올린 것을 적는다. 이걸 안 적으면 다음 글이 언제 되는지 모른다.

    소재 = 일상글일 때 어느 축을 썼나. 최근에 쓴 축을 다시 안 뽑으려고 적어 둔다.
    """
    기록방.mkdir(exist_ok=True)
    줄 = {"때": (때 or 지금()).isoformat(timespec="minutes"),
          "종류": 종류, "카드": 카드, "소재": 소재,
          "첫줄": (글 or "").strip().splitlines()[0][:40] if 글 else ""}
    with io.open(기록파일, "a", encoding="utf-8") as f:
        f.write(json.dumps(줄, ensure_ascii=False) + "\n")
    return 줄


def 최근소재(몇개=6):
    """최근에 쓴 일상글 축들. 이 안에 있는 축은 다시 안 뽑는다."""
    쓴것 = [x.get("소재") for x in _읽기() if x.get("소재")]
    return [x for x in 쓴것[-몇개:]]


def 사람말(남은분):
    if 남은분 <= 0:
        return "지금 올려도 된다"
    시 = 남은분 // 60
    분 = 남은분 % 60
    return "%d시간 %d분 뒤에 올릴 수 있다" % (시, 분) if 시 else "%d분 뒤에 올릴 수 있다" % 분


def main():
    ap = argparse.ArgumentParser(description="글 간격 지키기")
    ap.add_argument("--확인", action="store_true")
    ap.add_argument("--기록", metavar="종류")
    ap.add_argument("--카드", default="")
    ap.add_argument("--때", metavar="YYYY-MM-DD HH:MM")
    ap.add_argument("--목록", action="store_true")
    a = ap.parse_args()

    if getattr(a, "목록"):
        줄들 = _읽기()
        if not 줄들:
            print("아직 올린 게 없다")
        for x in 줄들:
            print("%s  %-4s %-8s %s" % (x["때"], x.get("종류", ""), x.get("카드", ""), x.get("첫줄", "")))
        return

    if getattr(a, "기록"):
        때 = None
        if getattr(a, "때"):
            때 = dt.datetime.fromisoformat(getattr(a, "때")).replace(tzinfo=지금().tzinfo)
        줄 = 기록하기(getattr(a, "기록"), 카드=a.카드, 때=때)
        print("적었다:", 줄["때"], 줄["종류"])
        return

    됨, 남은, 마지막 = 올릴수있나()
    if 마지막:
        print("마지막 글: %s (%s)" % (마지막["때"], 마지막.get("종류", "")))
    else:
        print("마지막 글: 없음")
    print("간격 규칙: 최소 %d시간" % 최소간격시간)
    print("→ " + 사람말(남은))
    sys.exit(0 if 됨 else 1)


if __name__ == "__main__":
    main()
