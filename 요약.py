# -*- coding: utf-8 -*-
"""6시간마다 텔레그램 한눈 요약 (2026-09-25 사장님 지시: "팔자오빠 것처럼 서아도").

    python 요약.py            요약을 화면에만 찍는다 (안 보냄)
    python 요약.py --보내      지금 바로 텔레그램으로 보낸다

자동.py 바퀴가 00·06·12·18시가 지난 첫 바퀴에 한 번 보낸다 (창고 상태.json 의 요약보낸칸).

무시 = 대기표 '안함' (기준에 걸려 답 안 한 댓글)
보류 = 대기표 '실패' (답을 썼는데 검사를 못 넘은 댓글)
나중에 줍기·채널관리가 같은 댓글에 답을 달았으면 무시·보류에서 뺀다.
무시·보류 링크는 **지난 요약 뒤에 생긴 것만** 붙인다 (같은 링크가 6시간마다 또 오지 않게).

표준 라이브러리만 쓴다. 팔자오빠 것을 하나도 부르지 않는다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import 창고
import 대기표 as 대기목록
import 발행기록
import 손님기록

몇시간마다 = 6                # 00·06·12·18시
링크최대 = 10                 # 무시·보류 각각 이만큼까지만 링크를 붙인다 (텔레그램 한 통 4,000자)
밑주소 = "https://graph.threads.net/v1.0/"


def 지금():
    return dt.datetime.now()


def 지금칸():
    n = 지금()
    return "%s-%02d" % (n.strftime("%Y-%m-%d"), n.hour // 몇시간마다 * 몇시간마다)


def _부르기(길, **값):
    """실패해도 요약은 나가야 하니 예외를 안 던진다. 못 받으면 {}."""
    import 서아토큰
    t, _ = 서아토큰.토큰있나()
    if not t:
        return {}
    값["access_token"] = t
    try:
        with urllib.request.urlopen(밑주소 + 길 + "?" + urllib.parse.urlencode(값), timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return {}


def _링크(줄):
    """댓글 링크. 대기표에 없으면(예전 줄) 스레드에 물어본다."""
    if 줄.get("링크"):
        return 줄["링크"]
    return _부르기(줄.get("댓글아이디") or "", fields="permalink").get("permalink") or ""


def 걸린것들(줄들):
    """(무시, 보류) — 아직 아무도 답 안 단 것만."""
    답한것 = {x.get("댓글아이디") for x in 줄들 if x.get("상태") in ("대기", "나감")}
    무시 = [x for x in 줄들 if x.get("상태") == "안함" and x.get("댓글아이디") not in 답한것]
    보류 = [x for x in 줄들 if x.get("상태") == "실패" and x.get("댓글아이디") not in 답한것]
    return 무시, 보류


def 계정():
    import 서아토큰
    _, 나 = 서아토큰.토큰있나()
    if not 나:
        return {}
    j = _부르기("%s/threads_insights" % 나, metric="views,likes,replies,reposts,quotes,followers_count")
    나온것 = {}
    for d in j.get("data", []):
        tv = d.get("total_value") or {}
        나온것[d.get("name")] = tv.get("value") if tv else (d.get("values") or [{}])[-1].get("value")
    return 나온것


def 일주일글():
    """최근 7일 내 글과 그 글의 조회·답글."""
    import 서아토큰
    _, 나 = 서아토큰.토큰있나()
    if not 나:
        return []
    선 = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=7)
    나온것 = []
    for 글 in _부르기("%s/threads" % 나, fields="id,text,timestamp,is_reply", limit=50).get("data", []):
        if 글.get("is_reply"):
            continue
        try:
            올린때 = dt.datetime.fromisoformat((글.get("timestamp") or "").replace("+0000", "+00:00").replace("Z", "+00:00"))
        except Exception:
            continue
        if 올린때 < 선:
            continue
        수 = {d.get("name"): (d.get("values") or [{}])[0].get("value")
             for d in _부르기("%s/insights" % 글["id"], metric="views,replies").get("data", [])}
        서울 = 올린때 + dt.timedelta(hours=9)
        나온것.append({"때": 서울.strftime("%m-%d %H:%M"), "조회": 수.get("views"), "답글": 수.get("replies"),
                     "훅": ((글.get("text") or "").strip().splitlines() or [""])[0][:22]})
    return 나온것


def _한줄(줄):
    말 = (줄.get("댓글") or "").replace("\n", " ")[:20]
    까닭 = (줄.get("까닭") or "")[:30]
    return "@%s 「%s」 %s\n%s" % (줄.get("손님") or "?", 말, 까닭, _링크(줄) or "(링크 못 받음)")


def 글짓기(지난요약=None):
    오늘 = 지금().strftime("%Y-%m-%d")
    지난요약 = 지난요약 or (지금() - dt.timedelta(hours=몇시간마다)).isoformat(timespec="minutes")
    줄들 = 대기목록.읽기()
    무시, 보류 = 걸린것들(줄들)

    글들 = [x for x in 발행기록._읽기() if (x.get("때") or "").startswith(오늘)]
    종류 = {}
    for x in 글들:
        종류[x.get("종류") or "?"] = 종류.get(x.get("종류") or "?", 0) + 1

    오늘것 = lambda xs: [x for x in xs if (x.get("적은때") or "").startswith(오늘)]
    out = ["📊 %s %02d시" % (지금().strftime("%m/%d"), 지금().hour),
           "",
           "── 오늘 (자정부터)",
           "글 %d개%s" % (len(글들), (" (" + " · ".join("%s %d" % kv for kv in 종류.items()) + ")") if 종류 else ""),
           "답글 %d개" % 손님기록.오늘답한수(),
           "무시 %d · 보류 %d" % (len(오늘것(무시)), len(오늘것(보류)))]

    대기 = sorted([x for x in 줄들 if x.get("상태") == "대기"], key=lambda x: x.get("나갈때") or "")
    if 대기:
        out += ["", "── 지금",
                "올라갈 차례 %d건 (%s)" % (len(대기), ", ".join((x.get("나갈때") or "")[11:16] for x in 대기[:4]))]

    acc = 계정()
    if acc:
        앞 = 창고.열기().상태("요약팔로워")
        차 = ("  (%+d)" % (acc["followers_count"] - 앞)) if 앞 is not None and acc.get("followers_count") is not None else ""
        out += ["", "── 계정",
                "팔로워 %s%s" % (acc.get("followers_count", "?"), 차),
                "조회 %s · 좋아요 %s · 답글 %s · 리포스트 %s"
                % (acc.get("views", "?"), acc.get("likes", "?"), acc.get("replies", "?"), acc.get("reposts", "?"))]
    글성적 = 일주일글()
    if 글성적:
        out += ["", "── 일주일 중 답글 많은 글"]
        out += ["%s 답글%s 조회%s  %s" % (p["때"], p.get("답글", "?"), p.get("조회", "?"), p["훅"])
                for p in sorted(글성적, key=lambda p: -(p.get("답글") or 0))[:3]]

    for 이름, 것들 in (("무시", 무시), ("보류", 보류)):
        새것 = sorted([x for x in 것들 if (x.get("적은때") or "") >= 지난요약],
                    key=lambda x: x.get("적은때") or "", reverse=True)
        if not 새것:
            continue
        out += ["", "── %s %d건 (지난 요약 뒤)" % (이름, len(새것))]
        out += [_한줄(x) for x in 새것[:링크최대]]
        if len(새것) > 링크최대:
            out.append("… 외 %d건" % (len(새것) - 링크최대))
    return "\n".join(out), acc.get("followers_count")


def 챙기기():
    """자동.py 바퀴가 부른다. 이번 칸에 아직 안 보냈으면 보낸다."""
    c = 창고.열기()
    칸 = 지금칸()
    if c.상태("요약보낸칸") == 칸:
        return False
    return 보내기()


def 보내기():
    import 알림
    c = 창고.열기()
    글, 팔로워 = 글짓기(c.상태("요약보낸때"))
    알림.보내기(글)
    c.상태쓰기("요약보낸칸", 지금칸())
    c.상태쓰기("요약보낸때", 지금().isoformat(timespec="minutes"))
    if 팔로워 is not None:
        c.상태쓰기("요약팔로워", 팔로워)
    return True


def main():
    ap = argparse.ArgumentParser(description="6시간마다 텔레그램 한눈 요약")
    ap.add_argument("--보내", action="store_true", help="지금 바로 텔레그램으로 보낸다")
    a = ap.parse_args()
    if a.보내:
        보내기()
        print("보냈다")
        return 0
    글, _ = 글짓기(창고.열기().상태("요약보낸때"))
    print(글)
    return 0


if __name__ == "__main__":
    sys.exit(main())
