# -*- coding: utf-8 -*-
"""버려진 댓글 중 **진짜 손님**을 다시 줍는다 (2026-09-24).

    python 줍기.py                 주울 게 있나 보기만 (안 올림)
    python 줍기.py --진짜          대기표에 다시 올린다
    python 줍기.py --며칠 3        며칠 전 것까지 볼까 (기본 2일)

왜
    거르는 기준은 세게 잡아야 한다. 스팸에 답글을 달면 계정이 위험하다.
    그런데 세게 잡으면 **진짜 손님이 같이 걸린다.** 실제로 이런 게 버려져 있었다.

        @zghj14l  스하리 완 다음주에 전남친이 있는 술자리에 가면 재회가 가능할까요?
                  → 버림: 품앗이·영업 댓글이다(스하리)

    앞에 인사만 붙였을 뿐 진짜 손님인데 통째로 버렸다.
    기준 자체는 `분류.볼만한가()` 에서 고쳤고, **이미 버려진 것**은 이 파일이 줍는다.

어떻게
    대기표에서 상태가 "안함"(기준에 걸려 버림) · "실패"(검사를 세 번 다 못 넘음) 인 줄을 다시 본다.
    지금 기준으로 볼만하면 답글을 만들어 다시 대기에 넣는다.
    **한 번 주운 것은 표시해 둬서 또 안 줍는다.**

팔자오빠 것을 하나도 부르지 않는다. 이 폴더 것만 쓴다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import random
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

여기 = Path(__file__).resolve().parent
sys.path.insert(0, str(여기))
import 분류
import 풀이
import 발행
import 대기표 as 대기목록

며칠전까지 = 2          # 이보다 오래된 것은 안 줍는다. 손님이 이미 잊었다
한번에최대 = 6          # 한 바퀴에 이만큼만. 한꺼번에 우르르 달리면 봇 티가 난다
늦출분 = (2, 14)        # 줍는 답글도 바로 안 보낸다


def _읽기():
    return 대기목록.읽기()      # 고치는 건 대기표.합치기() 로만 한다


def 주울것(줄들, 며칠=며칠전까지):
    """버려진 줄 중 지금 기준으로 답할 만한 것.

    **이미 주운 것은 건너뛴다.** 안 그러면 바퀴마다 같은 걸 또 줍는다.
    """
    언제까지 = dt.datetime.now() - dt.timedelta(days=며칠)
    나온것 = []
    for 줄 in 줄들:
        # "안함" = 기준에 걸려 버린 것 · "실패" = 답을 썼는데 검사를 세 번 다 못 넘은 것
        # **실패는 아무도 안 주웠다.** 채널관리는 인사 계열만 보고 여기는 안함만 봤다
        if 줄.get("상태") not in ("안함", "실패"):
            continue
        if 줄.get("주웠나"):
            continue
        if str(줄.get("까닭") or "").startswith("함정"):     # 떠보는 사람 — 절대 무시 (2026-09-26)
            continue
        if str(줄.get("까닭") or "").startswith("조용히"):   # 글마다 다는 사람 세 번째 글 — 일부러 둔 것 (2026-09-27)
            continue
        적은때 = 줄.get("적은때") or ""
        try:
            if dt.datetime.fromisoformat(적은때) < 언제까지:
                continue
        except Exception:
            pass
        댓글 = 줄.get("댓글") or ""
        본다, 까닭 = 분류.볼만한가(댓글)
        if not 본다:
            continue
        if 분류.인사냐(댓글):
            continue
        나온것.append(줄)
    return 나온것


def 줍기(진짜=False, 며칠=며칠전까지, 몇개=한번에최대):
    줄들 = _읽기()
    것들 = 주울것(줄들, 며칠)
    if not 것들:
        버린수 = sum(1 for x in 줄들 if x.get("상태") in ("안함", "실패"))
        print("주울 게 없다 (버려진·실패한 %d건 확인)" % 버린수)
        return 0

    print("주울 것 %d건 (최대 %d건 처리)\n" % (len(것들), 몇개))
    주운수 = 0
    지금 = dt.datetime.now()
    새줄들, 바뀐것 = [], {}
    for 줄 in 것들[:몇개]:
        손님 = 줄.get("손님") or "모름"
        댓글 = 줄.get("댓글") or ""
        print("=" * 52)
        print("@%s: %s" % (손님, 댓글[:70]))
        print("  전에 [%s] 된 까닭: %s" % (줄.get("상태"), 줄.get("까닭") or "-"))

        답 = 풀이.한판(손님, 댓글, 조용히=True, 글아이디=줄.get("내글", ""))
        if not 답["답할까"] or not 답["통과"]:
            print("  → 지금도 답 안 됨: %s" % " / ".join(답["문제"]))
            바뀐것[줄.get("댓글아이디")] = {"주웠나": "안됨"}
            continue

        for 한줄 in (답.get("글") or "").splitlines():
            print("  | %s" % 한줄)

        if not 진짜:
            print("  (보기만. 안 올렸다)")
            continue

        나갈때 = 지금 + dt.timedelta(minutes=random.randint(*늦출분))
        if 답.get("딴글나갈때"):          # 저쪽 글 답보다 늦게 (발행.답글만들기 와 같은 까닭)
            try:
                나갈때 = max(나갈때, dt.datetime.fromisoformat(답["딴글나갈때"])
                          + dt.timedelta(minutes=random.randint(3, 8)))
            except ValueError:
                pass
        새줄들.append({
            "댓글아이디": 줄.get("댓글아이디"),
            "손님": 손님, "댓글": 댓글,
            "턴": 답.get("턴", 1), "글": 답.get("글", ""),
            "그림주소": 답.get("그림주소"), "그림종류": 답.get("그림종류"),
            "카드": 답.get("카드", ""), "방향": 답.get("방향", ""),
            "종류": 답.get("종류") or "타로",
            "내글": 줄.get("내글", ""),
            "상태": "대기",
            "적은때": 지금.isoformat(timespec="minutes"),
            "나갈때": 나갈때.isoformat(timespec="minutes"),
            "주워온것": True,
        })
        바뀐것[줄.get("댓글아이디")] = {"주웠나": 나갈때.isoformat(timespec="minutes")}
        주운수 += 1
        print("  → 대기표에 올림 (%s 에 나감)" % 나갈때.strftime("%H:%M"))

    if 진짜:
        대기목록.합치기(새줄들, 바뀐것)
        print("\n%d건 주웠다" % 주운수)
    else:
        print("\n보기만 했다. 올리려면 python 줍기.py --진짜")
    return 주운수


def main():
    ap = argparse.ArgumentParser(description="버려진 댓글 중 진짜 손님을 다시 줍는다")
    ap.add_argument("--진짜", action="store_true", help="대기표에 실제로 올린다")
    ap.add_argument("--며칠", type=int, default=며칠전까지, help="며칠 전 것까지 볼까")
    ap.add_argument("--몇개", type=int, default=한번에최대)
    a = ap.parse_args()
    return 0 if 줍기(a.진짜, a.며칠, a.몇개) >= 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
