# -*- coding: utf-8 -*-
"""스레드에 실제로 올리고, 내 글에 달린 댓글을 긁어온다 (2026-09-24).

    python 발행.py --내글                       내 글 목록
    python 발행.py --댓글                       최근 내 글들에 달린 댓글 전부
    python 발행.py --올리기 일상 --시늉          글을 만들어 보여만 준다 (안 올림)
    python 발행.py --올리기 일상 --진짜          진짜 올린다
    python 발행.py --답글 --시늉                 댓글마다 답글을 만들어 보여준다 (안 올림)
    python 발행.py --답글 --진짜                 진짜 답글을 단다

**--진짜 를 안 붙이면 아무것도 안 올라간다.** 실수로 나가는 일이 없게 이렇게 뒀다.

스레드에 글이 올라가는 방식 (2단계)
    1) 상자를 만든다   POST {내아이디}/threads   (media_type, text, image_url, reply_to_id)
    2) 그 상자를 올린다 POST {내아이디}/threads_publish   (creation_id)
    사진은 메타가 그 주소로 직접 가지러 온다. 그래서 그림이 인터넷에 있어야 한다 (11절)

지키는 것
- 글과 글 사이 **4시간** (발행기록.py 가 막는다). 답글은 이 규칙에 안 걸린다
- 답글은 **4~37분 뒤 랜덤**으로 미룬다. 즉답은 봇 티가 난다
- 손님 한 명당 **3턴**까지만 (손님기록.py). 4턴부터는 답하지 않는다
- 내가 단 답글에는 다시 답하지 않는다. 무한 대화가 되면 안 된다

표준 라이브러리만 쓴다. 팔자오빠 것을 하나도 부르지 않는다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import random
import sys
import time
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
import 손님기록
import 대기표 as 대기목록
import 분류
import 풀이
import 알림
import 창고

우리계정 = "eslyn_yes"          # 서아. 이 계정 글은 답글 대상이 아니다
밑주소 = "https://graph.threads.net/v1.0/"
사진기다림 = 8          # 사진 상자는 메타가 받아가는 데 시간이 걸린다 (초)
# 2026-09-24: 4~37분 → **3~15분.** 댓글 달린 직후에 답해야 그 글이 다시 위로 올라간다
# (팔자오빠도 9/23 에 같은 이유로 줄였다)
늦출분 = (3, 15)
# 5턴부터는 더 오래 묵힌다. 풀이.AI안쓰는턴 다음 턴부터가 AI 자리다 (2026-09-24)
깊은턴 = 5
깊은대화늦출분 = (50, 70)
한바퀴최대 = 12         # 한 바퀴에 처리할 최대 건수. 1건당 45초쯤 걸린다


def 멈춤(말):
    sys.exit("[중단] " + 말)


def 토큰():
    t, 아이디 = 서아토큰.토큰있나()
    if not t:
        멈춤("토큰이 없다. python 서아토큰.py --넣기")
    return t, 아이디


# ── 스레드 부르기 ──────────────────────────────────────────────────────
# 스레드가 알려주는 사용률. 여기가 100 에 가까워지면 막힌다
사용률 = {"값": 0, "본때": ""}
재시도 = 3
쉬는초 = (2, 6, 18)          # 한 번 걸릴 때마다 더 오래 쉰다


def _사용률읽기(헤더):
    """응답 헤더 x-business-use-case-usage 에서 제일 큰 숫자를 꺼낸다."""
    try:
        raw = 헤더.get("x-business-use-case-usage")
        if not raw:
            return
        for 목록 in json.loads(raw).values():
            for x in 목록:
                가장 = max(int(x.get("call_count") or 0), int(x.get("total_cputime") or 0),
                           int(x.get("total_time") or 0))
                사용률["값"] = 가장
                사용률["본때"] = dt.datetime.now().isoformat(timespec="minutes")
    except Exception:
        pass


def _한번(방법, url, 몸):
    req = urllib.request.Request(url, data=몸, method=방법)
    with urllib.request.urlopen(req, timeout=40) as r:
        _사용률읽기(dict(r.headers))
        return json.loads(r.read().decode("utf-8"))


def _때려보기(방법, url, 몸=None, 길=""):
    """**삐끗해도 안 죽는다.** 429·5xx·끊김은 쉬었다 다시 한다 (2026-09-24).

    전에는 한 번 실패하면 sys.exit 라서 **바퀴가 통째로 죽었다.**
    스레드는 몰릴 때 순간적으로 5xx 를 뱉는데 그때마다 답글이 멈췄다.
    """
    마지막 = ""
    for 번째 in range(재시도):
        try:
            return _한번(방법, url, 몸)
        except urllib.error.HTTPError as e:
            원문 = e.read().decode("utf-8", "replace")
            try:
                마지막 = json.loads(원문).get("error", {}).get("message", 원문)
            except Exception:
                마지막 = 원문
            _사용률읽기(dict(e.headers or {}))
            다시할까 = e.code == 429 or 500 <= e.code < 600
            if not 다시할까:
                멈춤("스레드 %s → %s %s" % (길, e.code, str(마지막)[:200]))
            마지막 = "%s %s" % (e.code, str(마지막)[:120])
        except Exception as e:
            마지막 = type(e).__name__
        if 번째 < 재시도 - 1:
            time.sleep(쉬는초[번째])
    # 세 번 다 실패. **죽이지 않고 알린다.** 다음 바퀴가 다시 해 준다
    raise RuntimeError("스레드 %s 세 번 다 실패: %s" % (길, 마지막))


def 부르기(방법, 길, **값):
    url = 밑주소 + 길
    몸 = None
    if 방법 == "GET":
        url += "?" + urllib.parse.urlencode(값)
    else:
        몸 = urllib.parse.urlencode(값).encode("utf-8")
    return _때려보기(방법, url, 몸, 길)


def 끝까지(길, 쪽최대=10, **값):
    """페이지를 끝까지 따라가며 data 를 모은다 (2026-09-24).

    ** 는 기본 25개만 준다.** 그대로 쓰면 댓글이 몰리는 날
    최신 것이 밀려 나가서 "새 댓글 없음" 으로 보인다.
    팔자오빠 쪽에서 똑같이 겪고 고쳤던 버그인데 여기는 안 고쳐져 있었다.
    실측으로 한 시간에 38개가 들어온다 — 25개 벽에 바로 부딪힌다.
    """
    값.setdefault("limit", 100)
    url = 밑주소 + 길 + "?" + urllib.parse.urlencode(값)
    모음 = []
    for _ in range(쪽최대):
        j = _때려보기("GET", url, None, 길)
        모음.extend(j.get("data", []))
        url = (j.get("paging") or {}).get("next")
        if not url:
            break
    return 모음


# ── 읽기 ───────────────────────────────────────────────────────────────
def 내글들(개수=15):
    t, 나 = 토큰()
    j = 부르기("GET", "%s/threads" % 나, fields="id,text,timestamp,permalink",
               limit=개수, access_token=t)
    return j.get("data", [])


def 댓글들(글아이디):
    """그 글에 달린 답글. **대댓글까지 전부.** 내가 쓴 것과 이미 답한 것은 뺀다.

    전에는  를 썼는데 그건 **직계 댓글만** 준다 (2026-09-24 실측: 18개).
     은 대댓글까지 준다 (23개). 그 차이 5개가 하필
    **되묻거나 고쳐 말한 손님들**이었다 — 대화가 이어지려는 제일 아까운 자리다.
        "무슨뜻인지 이해가 잘 안가는데..온다는걸까?"
        "아 재회아니고 새로운 인연궁금했어"
    팔자오빠도 같은 이유로 /conversation 을 쓴다.
    """
    t, 나 = 토큰()
    대화 = 끝까지("%s/conversation" % 글아이디,
                  fields="id,text,username,timestamp,from,replied_to,is_reply_owned_by_me",
                  reverse="false", access_token=t)
    # 내가 이미 답한 댓글은 뺀다. 안 그러면 같은 사람에게 두 번 달린다
    내것 = {x["id"] for x in 대화
            if (x.get("username") or "").lower() == 우리계정 or x.get("is_reply_owned_by_me")}
    답한것 = {(x.get("replied_to") or {}).get("id") for x in 대화 if x["id"] in 내것}
    나온것 = []
    for x in 대화:
        if x["id"] in 내것 or x["id"] in 답한것:
            continue
        나온것.append(x)
    return 나온것


댓글붙는날 = 3          # 이 날짜가 지난 글은 댓글이 거의 안 붙는다 (읽기를 아낀다)


def 댓글모으기(글수=10):
    """최근 내 글들에 달린 댓글을 한 번에.

    **오래된 글은 건너뛴다** (2026-09-24). 5분마다 글 10개를 전부 읽으면
    하루 3,100번이 된다. 3일 지난 글엔 댓글이 거의 안 붙는데 계속 때리고 있었다.
    """
    모음 = []
    이제 = dt.datetime.now(dt.timezone.utc)
    for 글 in 내글들(글수):
        때 = 글.get("timestamp") or ""
        try:
            올린때 = dt.datetime.fromisoformat(때.replace("Z", "+00:00"))
            if (이제 - 올린때).days >= 댓글붙는날:
                continue
        except Exception:
            pass
        for c in 댓글들(글["id"]):
            c["내글"] = 글["id"]
            c["내글첫줄"] = (글.get("text") or "").splitlines()[0][:30]
            c["내글글"] = 글.get("text") or ""            # 번호 골라 글인지 보려고 (2026-09-25)
            모음.append(c)
    return 모음


# ── 올리기 ─────────────────────────────────────────────────────────────
def 스레드에올리기(글, 그림주소=None, 답할대상=None):
    """2단계로 올린다. 올라간 글의 아이디를 준다."""
    t, 나 = 토큰()
    값 = {"access_token": t, "text": 글}
    if 그림주소:
        값.update({"media_type": "IMAGE", "image_url": 그림주소})
    else:
        값["media_type"] = "TEXT"
    if 답할대상:
        값["reply_to_id"] = 답할대상

    상자 = 부르기("POST", "%s/threads" % 나, **값)
    상자아이디 = 상자.get("id")
    if not 상자아이디:
        멈춤("상자를 못 만들었다: %s" % 상자)
    if 그림주소:
        time.sleep(사진기다림)      # 메타가 사진을 받아갈 틈을 준다

    올린것 = 부르기("POST", "%s/threads_publish" % 나,
                    creation_id=상자아이디, access_token=t)
    if not 올린것.get("id"):
        멈춤("올리기 실패: %s" % 올린것)
    return 올린것["id"]


# ── 새 글 ──────────────────────────────────────────────────────────────
def 글올리기(글감="일상", 진짜=False):
    됨, 남은, 마지막 = 발행기록.올릴수있나()
    if not 됨:
        print("아직이다. %s" % 발행기록.사람말(남은))
        if 진짜:
            return 1
    print("글감: %s" % 글감)
    글, ok, 문제, _n, fact = 풀이.글쓰기("eslyn_yes", 글감)
    print("-" * 52)
    for line in (글 or "(없음)").splitlines():
        print(line)
    print("-" * 52)
    if not ok:
        print("검사 실패: %s" % " / ".join(문제))
        return 1

    그림 = None
    if 글감 != "일상" and fact.get("슬러그"):
        import 그림올리기
        그림 = 그림올리기.앞면주소(fact["슬러그"], fact.get("방향", "정방향"))
        print("그림: %s" % 그림)

    if not 진짜:
        print("\n시늉이다. 안 올렸다. 올리려면 --진짜")
        return 0

    아이디 = 스레드에올리기(글, 그림)
    발행기록.기록하기(글감, 글=글, 카드=fact.get("카드", ""), 소재=fact.get("축", ""))
    print("\n올렸다. 글 아이디 %s" % 아이디)
    return 0


# ── 답글 ───────────────────────────────────────────────────────────────
글창고 = "글창고.json"            # R2 창고 seoa/ 아래 (2026-09-25)


def _창고읽기():
    return 창고.열기().읽기(글창고, []) or []


def _창고쓰기(쌓인것):
    창고.열기().쓰기(글창고, 쌓인것)


def 쌓기(글감들):
    """글을 미리 만들어 창고에 넣어 둔다. 올릴 때 다시 만들 필요가 없다.

    새벽에 만들어 두고 사람 많은 시간에 올리는 용도다.
    """
    쌓인것 = _창고읽기()
    for 글감 in 글감들:
        print("\n[%s] 만드는 중…" % 글감)
        글, ok, 문제, _n, fact = 풀이.글쓰기("eslyn_yes", 글감)
        for line in (글 or "(없음)").splitlines():
            print("  | %s" % line)
        if not ok:
            print("  → 실패: %s" % " / ".join(문제))
            continue
        그림 = None
        if 글감 != "일상" and fact.get("슬러그"):
            import 그림올리기
            그림 = 그림올리기.앞면주소(fact["슬러그"], fact.get("방향", "정방향"))
        쌓인것.append({"글감": 글감, "글": 글, "그림주소": 그림,
                       "카드": fact.get("카드", ""), "방향": fact.get("방향", ""),
                       "축": fact.get("축", ""), "쓴때": dt.datetime.now().isoformat(timespec="minutes"),
                       "상태": "대기"})
        print("  → 창고에 넣음")
    _창고쓰기(쌓인것)
    print("\n창고: %d개 (%s)" % (sum(1 for x in 쌓인것 if x["상태"] == "대기"), 글창고))
    return 0


def 창고보기():
    쌓인것 = _창고읽기()
    대기 = [x for x in 쌓인것 if x["상태"] == "대기"]
    if not 대기:
        print("창고가 비었다. python 발행.py --쌓기 무료,한장,일상")
        return 0
    for i, x in enumerate(대기, 1):
        print("\n[%d] %s %s %s" % (i, x["글감"], x.get("카드", ""), x.get("방향", "")))
        for line in x["글"].splitlines():
            print("    | %s" % line)
        if x.get("그림주소"):
            print("    그림 %s" % x["그림주소"])
    print("\n올리려면: python 발행.py --창고올리기 1 --진짜")
    return 0


def 창고올리기(번호, 진짜=False, 간격무시=False):
    쌓인것 = _창고읽기()
    대기 = [x for x in 쌓인것 if x["상태"] == "대기"]
    if not 1 <= 번호 <= len(대기):
        print("창고에 %d번이 없다 (지금 %d개)" % (번호, len(대기)))
        return 1
    골라진것 = 대기[번호 - 1]
    됨, 남은, _ = 발행기록.올릴수있나()
    if not 됨 and not 간격무시:
        print("아직이다. %s (그래도 올리려면 --간격무시)" % 발행기록.사람말(남은))
        return 1
    for line in 골라진것["글"].splitlines():
        print(line)
    if not 진짜:
        print("\n시늉이다. 올리려면 --진짜")
        return 0
    아이디 = 스레드에올리기(골라진것["글"], 골라진것.get("그림주소"))
    골라진것["상태"] = "나감"
    골라진것["나간아이디"] = 아이디
    _창고쓰기(쌓인것)
    발행기록.기록하기(골라진것["글감"], 글=골라진것["글"],
                      카드=골라진것.get("카드", ""), 소재=골라진것.get("축", ""))
    print("\n올렸다. %s" % 아이디)
    return 0


# **대기표는 대기표.py 한 군데서만 고친다** (2026-09-24).
#   전에는 발행·줍기·채널관리 셋이 잠금 없이 통째로 덮어써서 서로 쓴 것을 날렸다.
#   실제로 채널관리가 올린 답글이 5분 뒤 바퀴에 지워졌다.
def _대기읽기():
    return 대기목록.읽기()


# 하루에 이만큼까지만 답한다 (2026-09-24 사장님 지시).
# 메타 답글 한도가 하루 1,000 이라 2건을 여유로 남겼다. 댓글이 터져도 폭주하지 않는다
하루상한 = 998


def 답글만들기(진짜=False, 몇개=한바퀴최대):
    """댓글을 긁어 답글을 만든다. 이미 답한 댓글은 건너뛴다."""
    오늘것 = 손님기록.오늘답한수()
    if 오늘것 >= 하루상한:
        말 = "오늘 답글이 하루 상한(%d건)에 닿았다. 더 안 단다" % 하루상한
        print(말)
        알림.보내기(말)
        return 0
    # 사용률이 높으면 이번 바퀴는 쉰다. 막히고 나면 몇 시간씩 못 쓴다
    if 사용률["값"] >= 80:
        말 = "스레드 사용률 %d%%. 이번 바퀴는 쉰다" % 사용률["값"]
        print(말)
        알림.보내기(말)
        return 0

    이미 = {x.get("댓글아이디") for x in _대기읽기()}
    try:
        댓글 = 댓글모으기()
    except Exception as e:
        # **세 번 다 실패해도 죽이지 않는다.** 다음 바퀴가 다시 해 준다
        말 = "댓글을 못 읽었다: %s" % str(e)[:150]
        print(말)
        알림.보내기(말)
        return 0
    새것 = [c for c in 댓글 if c["id"] not in 이미][:몇개]
    if not 새것:
        print("새 댓글이 없다 (긁은 댓글 %d개, 전부 처리됨)" % len(댓글))
        return 0

    새줄들 = []
    for c in 새것:
        손님 = c.get("username") or (c.get("from") or {}).get("username") or "모름"
        본문 = c.get("text") or ""
        print("\n" + "=" * 52)
        print("@%s: %s" % (손님, 본문[:60]))

        답 = 풀이.한판(손님, 본문, 조용히=True, 글아이디=c.get("내글", ""), 내글글=c.get("내글글", ""))
        if not 답["답할까"]:
            print("  → 답 안 함: %s" % " / ".join(답["문제"]))
            새줄들.append({"댓글아이디": c["id"], "손님": 손님, "댓글": 본문,
                         "상태": "안함", "까닭": " / ".join(답["문제"]),
                         "내글": c.get("내글", ""),
                         "적은때": dt.datetime.now().isoformat(timespec="minutes")})
            continue
        if not 답["통과"]:
            print("  → 검사 실패: %s" % " / ".join(답["문제"]))
            새줄들.append({"댓글아이디": c["id"], "손님": 손님, "댓글": 본문,
                         "상태": "실패", "까닭": " / ".join(답["문제"]),
                         "내글": c.get("내글", ""),
                         "적은때": dt.datetime.now().isoformat(timespec="minutes")})
            continue

        print("  %d턴 · %s · %s %s" % (답["턴"], 답["그림종류"], 답["카드"], 답["방향"]))
        for line in 답["글"].splitlines():
            print("  | %s" % line)

        줄 = {"댓글아이디": c["id"], "손님": 손님, "댓글": 본문, "턴": 답["턴"],
              "글": 답["글"], "그림주소": 답["그림주소"], "그림종류": 답["그림종류"],
              "카드": 답["카드"], "방향": 답["방향"],
              # **어느 글의 댓글인지.** 내보낼 때 손님기록에 같이 적어야 턴이 글 단위로 맞는다
              "내글": c.get("내글", ""),
              "상태": "대기", "적은때": dt.datetime.now().isoformat(timespec="minutes")}

        if 진짜:
            # **5턴부터는 한 시간 뒤에 내보낸다** (2026-09-24 사장님 지시).
            #   거기는 AI 가 쓰는 깊은 대화 자리다. 2분 만에 척 답하면 봇 티가 난다.
            #   바퀴를 따로 만드는 것보다 이게 안 복잡하고 터질 자리도 없다
            늦춤 = random.randint(*(깊은대화늦출분 if 답["턴"] >= 깊은턴 else 늦출분))
            print("  → %d분 뒤에 나간다" % 늦춤)
            줄["나갈때"] = (dt.datetime.now() + dt.timedelta(minutes=늦춤)).isoformat(timespec="minutes")
        새줄들.append(줄)

    대기목록.합치기(새줄들)

    # 막힌 게 있으면 알린다. 조용히 멈추면 며칠 뒤에나 안다 (팔자오빠에서 배운 것)
    막힌것 = [x for x in 새줄들 if x.get("상태") == "실패"]
    if 막힌것:
        알림.보내기("답글 %d건이 검사에 걸려 안 나갔어. 확인 필요\n%s"
                    % (len(막힌것),
                       "\n".join("@%s: %s" % (x["손님"], (x.get("까닭") or "")[:50])
                                 for x in 막힌것[:3])))

    print("\n대기표에 적었다 (창고 답글대기.json)")
    if not 진짜:
        print("시늉이다. 아무것도 안 나갔다. 내보내려면 python 발행.py --내보내기 --진짜")
    return 0


def 내보내기(진짜=False):
    """대기표에서 시각이 지난 것을 실제로 내보낸다."""
    줄들 = _대기읽기()
    지금 = dt.datetime.now()
    나간것 = 0
    바뀐것 = {}
    for 줄 in 줄들:
        if 줄.get("상태") != "대기":
            continue
        나갈때 = 줄.get("나갈때")
        if 나갈때 and dt.datetime.fromisoformat(나갈때) > 지금:
            print("아직: @%s (%s 에 나감)" % (줄["손님"], 나갈때))
            continue
        print("\n@%s %d턴 → %s" % (줄["손님"], 줄.get("턴", 0), 줄.get("그림종류")))
        for line in (줄.get("글") or "").splitlines():
            print("  | %s" % line)
        if not 진짜:
            print("  (시늉. 안 나갔다)")
            continue
        아이디 = 스레드에올리기(줄["글"], 줄.get("그림주소"), 답할대상=줄["댓글아이디"])
        try:
            대기목록.합치기(바뀐것={줄["댓글아이디"]: {"상태": "나감", "나간아이디": 아이디}})
            손님기록.기록하기(줄["손님"], 카드=줄.get("카드", ""), 방향=줄.get("방향", ""),
                              그림=줄.get("그림종류", ""), 댓글=줄.get("댓글", ""), 글=줄.get("글", ""),
                              글아이디=줄.get("내글", ""))
        except Exception as e:
            # 답은 이미 나갔는데 표시를 못 했다. 다음 바퀴가 또 보낼 수 있다 → 크게 알린다
            알림.보내기("답글은 나갔는데(@%s) 창고에 표시를 못 했어: %s. 같은 답이 또 나갈 수 있으니 봐줘"
                        % (줄["손님"], str(e)[:100]))
            raise
        바뀐것[줄["댓글아이디"]] = 아이디
        나간것 += 1
        print("  → 나갔다 (%s)" % 아이디)
    if 진짜:
        print("\n%d개 내보냈다" % 나간것)
    return 0


def main():
    ap = argparse.ArgumentParser(description="스레드에 올리고 댓글을 긁어온다")
    ap.add_argument("--내글", action="store_true")
    ap.add_argument("--댓글", action="store_true")
    ap.add_argument("--올리기", metavar="글감", help="한장·개업·무료·일상")
    ap.add_argument("--답글", action="store_true", help="댓글마다 답글을 만든다")
    ap.add_argument("--내보내기", action="store_true", help="대기표에서 시각 지난 것을 내보낸다")
    ap.add_argument("--쌓기", metavar="글감들", help="미리 만들어 창고에 넣는다 (쉼표로: 무료,한장,일상)")
    ap.add_argument("--창고", action="store_true", help="창고에 쌓인 글 보기")
    ap.add_argument("--창고올리기", type=int, metavar="번호", help="창고의 N번째 글을 올린다")
    ap.add_argument("--진짜", action="store_true", help="이게 없으면 아무것도 안 올라간다")
    ap.add_argument("--시늉", action="store_true", help="(기본값) 만들어 보여만 준다")
    a = ap.parse_args()

    if a.내글:
        for x in 내글들():
            print("%s  %s  %s" % (x.get("timestamp", "")[:16], x["id"],
                                  (x.get("text") or "").splitlines()[0][:40]))
        return 0
    if a.댓글:
        모음 = 댓글모으기()
        if not 모음:
            print("댓글이 하나도 없다")
        for c in 모음:
            print("@%-16s %s" % (c.get("username", "?"), (c.get("text") or "")[:60]))
        return 0
    if a.쌓기:
        return 쌓기([x.strip() for x in a.쌓기.split(",") if x.strip()])
    if a.창고:
        return 창고보기()
    if a.창고올리기:
        return 창고올리기(a.창고올리기, 진짜=a.진짜)
    if a.올리기:
        return 글올리기(a.올리기, 진짜=a.진짜)
    if a.답글:
        return 답글만들기(진짜=a.진짜)
    if a.내보내기:
        return 내보내기(진짜=a.진짜)
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
