# -*- coding: utf-8 -*-
"""올린 글이 실제로 몇 번 보였고 댓글이 몇 개 붙었나 모은다 (2026-09-24).

    python 성적.py --재기        스레드에서 숫자를 받아 기록에 쌓는다
    python 성적.py --본다        쌓인 것 보기 (조회 많은 순)
    python 성적.py --본다 --글감 무료    한 글감만

왜 필요한가
    지금까지는 감으로 골랐다. 팔자오빠는 성적표가 있어서
    "나 돌려 말 안 해 개띠부터 본다" 조회 1,921 vs "나 오늘 양띠 하나만 짚고 갈게" 조회 19
    를 숫자로 알고 있었다. 100배 차이를 감으로는 못 잡는다.

    우리도 같은 걸 쌓는다. 훅 첫 줄과 글틀을 같이 적어 두니
    **어떤 틀이 먹히는지** 나중에 갈라 볼 수 있다.

기록 자리: R2 창고 `seoa/성적.csv` (2026-09-25)
표준 라이브러리만 쓴다. 팔자오빠 것을 하나도 부르지 않는다.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
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
import 서아토큰
import 발행기록
import 창고

성적표 = "성적.csv"              # R2 창고 seoa/ 아래 (2026-09-25)
칸 = ["잰날", "올린때", "글id", "글감", "틀", "카드", "훅", "조회", "좋아요", "댓글", "리포스트", "인용"]
밑주소 = "https://graph.threads.net/v1.0/"


def 부르기(길, **값):
    url = 밑주소 + 길 + "?" + urllib.parse.urlencode(값)
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            메시지 = json.loads(e.read().decode("utf-8")).get("error", {}).get("message", "")
        except Exception:
            메시지 = ""
        return {"__오류__": "%s %s" % (e.code, str(메시지)[:120])}
    except Exception as e:
        return {"__오류__": type(e).__name__}


def 내글들(개수=25):
    t, 나 = 서아토큰.토큰있나()
    if not t:
        sys.exit("토큰이 없다. python 서아토큰.py --넣기")
    j = 부르기("%s/threads" % 나, fields="id,text,timestamp", limit=개수, access_token=t)
    if "__오류__" in j:
        sys.exit("내 글을 못 받았다: %s" % j["__오류__"])
    return j.get("data", [])


def 숫자받기(글id):
    """그 글의 조회·좋아요·댓글·리포스트·인용."""
    t, _ = 서아토큰.토큰있나()
    j = 부르기("%s/insights" % 글id,
               metric="views,likes,replies,reposts,quotes", access_token=t)
    if "__오류__" in j:
        return {}
    나온것 = {}
    for x in j.get("data", []):
        이름 = x.get("name")
        값 = x.get("values") or [{}]
        나온것[이름] = 값[0].get("value", 0)
    return 나온것


def _발행기록보기():
    """글감·틀·카드는 스레드가 모른다. 우리 발행기록에서 시각으로 맞춰 온다."""
    붙임 = []
    for x in 발행기록._읽기():
        try:
            때 = dt.datetime.fromisoformat(x["때"])
        except Exception:
            continue
        붙임.append((때, x))
    return 붙임


def _맞는것(올린때, 붙임, 봐줄분=90):
    """올린 시각이 제일 가까운 발행기록 줄. 몇 분 어긋나는 건 봐준다."""
    제일가까운, 차이 = None, None
    for 때, x in 붙임:
        재 = abs((때.replace(tzinfo=None) - 올린때).total_seconds()) / 60
        if 차이 is None or 재 < 차이:
            제일가까운, 차이 = x, 재
    return 제일가까운 if (차이 is not None and 차이 <= 봐줄분) else {}


def 재기():
    붙임 = _발행기록보기()
    오늘 = dt.datetime.now().strftime("%Y-%m-%d")
    줄들 = []
    for 글 in 내글들():
        올린때 = dt.datetime.fromisoformat((글.get("timestamp") or "").replace("Z", "+00:00"))
        올린때 = (올린때 + dt.timedelta(hours=9)).replace(tzinfo=None)      # 서울 시각
        수 = 숫자받기(글["id"])
        본문 = (글.get("text") or "").strip()
        맞는 = _맞는것(올린때, 붙임)
        줄들.append({
            "잰날": 오늘,
            "올린때": 올린때.strftime("%Y-%m-%d %H:%M"),
            "글id": 글["id"],
            "글감": 맞는.get("종류", ""),
            "틀": 맞는.get("소재", ""),
            "카드": 맞는.get("카드", ""),
            "훅": 본문.splitlines()[0][:44] if 본문 else "",
            "조회": 수.get("views", 0),
            "좋아요": 수.get("likes", 0),
            "댓글": 수.get("replies", 0),
            "리포스트": 수.get("reposts", 0),
            "인용": 수.get("quotes", 0),
        })

    c = 창고.열기()
    있던것 = c.글읽기(성적표, "") or ""
    통 = io.StringIO()
    w = csv.DictWriter(통, fieldnames=칸)
    if not 있던것.strip():
        w.writeheader()
    for 줄 in 줄들:
        w.writerow(줄)
    c.글쓰기(성적표, 있던것 + 통.getvalue())
    print("%d개 쟀다 → 창고 %s" % (len(줄들), 성적표))
    for 줄 in sorted(줄들, key=lambda x: -x["조회"])[:5]:
        print("  조회 %-5s 댓글 %-3s %-6s %s" % (줄["조회"], 줄["댓글"], 줄["글감"], 줄["훅"][:34]))
    return 0


def 본다(글감=None):
    있던것 = 창고.열기().글읽기(성적표, "") or ""
    if not 있던것.strip():
        print("아직 잰 게 없다. python 성적.py --재기")
        return 1
    쌓인것 = list(csv.DictReader(io.StringIO(있던것)))
    # 같은 글을 여러 번 쟀으면 마지막 것만 본다
    마지막 = {}
    for 줄 in 쌓인것:
        마지막[줄["글id"]] = 줄
    줄들 = list(마지막.values())
    if 글감:
        줄들 = [x for x in 줄들 if x.get("글감") == 글감]
    if not 줄들:
        print("해당하는 게 없다")
        return 1

    def 수(x, k):
        try:
            return int(x.get(k) or 0)
        except Exception:
            return 0

    줄들.sort(key=lambda x: -수(x, "조회"))
    print("%-6s %-5s %-4s %-4s %-6s %-10s %s" % ("조회", "좋아요", "댓글", "리포", "글감", "틀", "훅"))
    for x in 줄들:
        print("%-6s %-5s %-4s %-4s %-6s %-10s %s" % (
            x["조회"], x["좋아요"], x["댓글"], x["리포스트"],
            x.get("글감", ""), (x.get("틀") or "")[:10], x["훅"][:36]))

    # 글감별 평균 — 뭐가 먹히는지 여기서 갈린다
    묶음 = {}
    for x in 줄들:
        묶음.setdefault(x.get("글감") or "모름", []).append(x)
    print("\n글감별 평균")
    for 이름, 것들 in sorted(묶음.items(), key=lambda kv: -sum(수(x, "댓글") for x in kv[1]) / len(kv[1])):
        print("  %-6s 글 %-3d 조회 %-6.0f 댓글 %-5.1f" % (
            이름, len(것들),
            sum(수(x, "조회") for x in 것들) / len(것들),
            sum(수(x, "댓글") for x in 것들) / len(것들)))
    return 0


def main():
    ap = argparse.ArgumentParser(description="글 성적 재기")
    ap.add_argument("--재기", action="store_true")
    ap.add_argument("--본다", action="store_true")
    ap.add_argument("--글감", metavar="이름")
    a = ap.parse_args()
    if a.재기:
        return 재기()
    if a.본다:
        return 본다(a.글감)
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
