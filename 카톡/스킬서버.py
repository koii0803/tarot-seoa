# -*- coding: utf-8 -*-
"""카카오톡 챗봇(오픈빌더)이 부르는 자리.

**이 폴더 하나로 끝난다** (2026-09-24 사장님 지시).
전에는 스레드 쪽(타로엔진·조립·분류·풀이·그림올리기)을 그대로 불러 썼다.
그러면 스레드를 고칠 때 카톡이 같이 부서진다. 인수인계 0절의 분리를 어긴 것이었다.
지금은 위 폴더를 한 줄도 안 본다.

    python 스킬서버.py                          열기 (http://localhost:8767/skill)
    python 스킬서버.py --길 skill/abc123        주소를 남이 못 찍게 숨긴다
    python 스킬서버.py --시험 "재회될까"          서버 안 열고 답만 찍어본다

⚠️ 답글 품질로 한 번 크게 혼났다 (2026-09-24). 까닭은 전부 **스레드에 있는 걸 안 가져온 것**이었다.
    이 파일을 처음 만들 때 웹 채팅(웹/서버.py)을 베꼈는데, 웹 채팅은 검사가 얇다.
    댓글 답글을 실제로 내보내는 건 스레드 쪽 `풀이.py 문맥답글()` 이고 거기는 다섯 겹이다.
        빠졌던 것 1  check_output  재료에 없는 말을 지어냈나  ← 제일 큰 구멍
        빠졌던 것 2  말투검사      존댓말·애교가 섞였나
        빠졌던 것 3  재시도        걸리면 다시 시키기 (한 번 걸리면 조립글로 떨어졌다)
        빠졌던 것 4  줄 수         스레드 기준 3줄을 그대로 써서 한 줄이 35자를 넘겼다

스레드 발행.py 와 뭐가 다른가 — **방향이 반대다**
    발행.py   우리가 글을 올린다 → 10분마다 댓글을 긁으러 간다 → 3~15분 뒤로 미뤄 답한다
    여기      손님이 먼저 말을 건다 → 카카오가 찔러 준다 → 그 자리에서 답해야 한다

    그래서 발행.py 의 미루기(사람처럼 보이려고 늦게 답하기)를 여기선 못 쓴다.
    대신 **최소 몇 초**는 채운다 — 0.04초에 답하면 기계라고 광고하는 꼴이라서다.

카카오가 정한 시간 (오픈빌더 화면에 적힌 그대로)
    첫 답    skill timeout: 5sec
    콜백     최대 5분, 1회
    그래서 **모든 답을 콜백으로 보낸다.** 즉답 자리에서는 "잠깐만" 만 내보낸다.

흐름
    손님 첫 말  →  카드부터 뽑지 않는다. **누가 뽑을지부터 묻는다** (버튼 두 개)
        ├ 내가 뽑을래  →  사이트 주소를 준다 → 손님이 뽑아 온 이름으로 푼다
        └ 네가 뽑아줘  →  기계가 뽑아서 푼다
    그 뒤  →  이어지는 대화. 첫 풀이는 조립(토큰 0), 그다음부터 AI 가 앞 대화를 받아 쓴다
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import re
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import 말투                 # 카톡 말투 (스레드 서아 것과 다르다)
import 말종류               # 손님 말이 어떤 종류인지 (카드를 또 뽑을지 여기서 갈린다)
import 엔진
import 조립
import 분류
import 부르기 as 풀이
import 그림 as 그림올리기

기록방 = HERE / "기록"
손님파일 = 기록방 / "손님.jsonl"

무료턴 = 0              # 0 이면 안 막는다. **값을 아직 안 정했다** (사장님 정할 것)
시킬횟수 = 3            # AI 글이 검사에 걸리면 이만큼 다시 시킨다 (스레드와 같은 수)
최소기다림 = 5          # **이보다 빨리 답하지 않는다** (2026-09-24 사장님 지시)
콜백한계 = 45           # 카카오는 5분까지 봐준다. 45초에 끊고 조립글로 보낸다
즉답한계 = 15           # 콜백이 꺼져 있을 때만 쓴다
기다리는말 = "...."     # 사람이 치고 있는 것처럼 보이는 게 낫다 (2026-09-24 사장님 지시)
새대화 = 3 * 3600       # 이만큼 비었다 오면 **새 상담으로 보고 갈림길을 다시 묻는다**.
                        # 처음엔 "생전 처음 온 손님" 일 때만 물었는데, 그러면 한 번 본 손님은
                        # 다음에 새 고민을 들고 와도 영영 못 고른다


def 지금():
    return dt.datetime.now()


# ── 손님 기록 (스레드 것과 따로) ──────────────────────────────────────
def _읽기():
    if not 손님파일.exists():
        return []
    줄들 = []
    with io.open(손님파일, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    줄들.append(json.loads(line))
                except Exception:
                    pass
    return 줄들


def 적기(손님, 말, 답, 카드="", 방향="", 만든법="", 라인="", 질문="",
         씨앗="", 슬러그=""):
    """`라인` 은 이 손님이 어느 길로 가는지다 — 직접 / 맡김.

    **한 번 정해지면 그 상담 내내 유지된다** (2026-09-24 사장님 지시: 파이프라인을 둘로).
    라인 없이 분기만 뒀더니 손님이 "운명의 수레바퀴 정방향" 이라고 적었는데
    엉뚱하게 악마 정방향이 나갔다. 지정한 카드가 통째로 무시된 것이다.
    `질문` 은 직접 라인에서 카드를 기다리는 동안 붙들고 있는 고민이다.
    """
    기록방.mkdir(exist_ok=True)
    줄 = {"때": 지금().isoformat(timespec="seconds"), "손님": 손님,
          "말": 말, "답": 답, "카드": 카드, "방향": 방향, "만든법": 만든법,
          "라인": 라인, "질문": 질문, "씨앗": 씨앗, "슬러그": 슬러그}
    with io.open(손님파일, "a", encoding="utf-8") as f:
        f.write(json.dumps(줄, ensure_ascii=False) + "\n")


def 지난대화(손님, 몇턴=12):
    오간말 = []
    for x in [r for r in _읽기() if r.get("손님") == 손님][-몇턴:]:
        if x.get("말"):
            오간말.append(("손님", x["말"]))
        if x.get("답"):
            오간말.append(("나", x["답"]))
    return 오간말


def 지난턴(손님):
    return sum(1 for x in _읽기() if x.get("손님") == 손님)


# ── 카카오가 알아먹는 꼴로 싸기 ───────────────────────────────────────
def 말풍선(글, 그림=None, 버튼=()):
    """simpleText 하나 + (있으면) 카드 그림 + (있으면) 고르는 버튼."""
    칸 = [{"simpleText": {"text": 글[:1000]}}]
    if 그림:
        칸.append({"simpleImage": {"imageUrl": 그림, "altText": "뽑은 카드"}})
    틀 = {"outputs": 칸}
    if 버튼:
        # 버튼을 누르면 그 글자가 손님 말로 다시 들어온다. 블록을 더 안 만들어도 된다
        틀["quickReplies"] = [{"label": b, "action": "message", "messageText": b}
                              for b in 버튼]
    return {"version": "2.0", "template": 틀}


def 기다리라고():
    """5초 안에 내보내는 답. 이걸 보내야 카카오가 콜백을 받아준다."""
    return {"version": "2.0", "useCallback": True, "data": {"text": 기다리는말}}


def 콜백으로보내기(주소, 몸):
    몸통 = json.dumps(몸, ensure_ascii=False).encode("utf-8")
    청 = urllib.request.Request(주소, data=몸통, method="POST",
                                headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(청, timeout=15) as r:
            return r.status
    except Exception as e:
        print("콜백 실패: %s" % e)
        return 0


# ── 손님이 뽑아 온 카드 알아듣기 ──────────────────────────────────────
def 카드알아듣기(말):
    """사이트에서 뽑고 적어 보낸 이름을 카드로 바꾼다. 못 찾으면 (None, None).

    사이트가 `죽음 역방향` 꼴로 내준다. 그래도 손님은 띄어쓰기를 틀리고 방향을 빼먹는다.
    """
    t = re.sub(r"\s", "", 말 or "")
    if not t:
        return None, None
    방향 = "역방향" if ("역" in t and "정" not in t) else "정방향"
    찾은것 = None
    for c in 엔진.CARDS:
        이름 = re.sub(r"\s", "", c.get("ko") or "")
        if 이름 and 이름 in t:
            # 더 긴 이름이 이기게 둔다 (여사제가 사제보다 먼저)
            if 찾은것 is None or len(이름) > len(re.sub(r"\s", "", 찾은것.get("ko") or "")):
                찾은것 = c
    return (찾은것, 방향) if 찾은것 else (None, None)


def 첫질문(앞선것):
    """갈림길을 물었던 그 순간 손님이 했던 말. 그게 진짜 고민이다."""
    for x in reversed(앞선것):
        if x.get("만든법") == "갈림길" and x.get("말"):
            return x["말"]
    return (앞선것[0].get("말") if 앞선것 else "") or ""


def 지금라인(앞선것):
    """이 손님이 타고 있는 라인. 직접 / 맡김 / 아직 안 정함."""
    for x in reversed(앞선것):
        if x.get("라인"):
            return x["라인"]
    return ""


def 붙든질문(앞선것):
    """직접 라인에서 카드를 기다리는 동안 붙들고 있던 고민."""
    for x in reversed(앞선것):
        if x.get("질문"):
            return x["질문"]
    return 첫질문(앞선것)


def 새상담인가(앞선것):
    """갈림길을 물어야 하나. 처음 왔거나, 마지막 대화 뒤로 한참 비었으면 새 상담이다."""
    if not 앞선것:
        return True
    try:
        마지막 = dt.datetime.fromisoformat(앞선것[-1]["때"])
    except Exception:
        return False
    return (지금() - 마지막).total_seconds() > 새대화


def 풀이턴(앞선것):
    """카드까지 나간 게 몇 번째인가. 갈림길·사이트안내는 안 센다."""
    return sum(1 for x in 앞선것 if x.get("카드"))


# ── AI 글 — **스레드 틀을 그대로 쓴다** ───────────────────────────────
def AI글(씨앗, 말, 오간말, 유형, 시제, 카드, 방향, 한계):
    """글은 `부르기.문맥답글()` 이 만든다. 스레드가 댓글에 답글 달 때 쓰는 바로 그 틀이다.

    **여기서 새로 만드는 게 없다.** 프롬프트도 검사 다섯 겹도 세 번 다시 시키는 것도
    전부 스레드 것 그대로다. 바뀐 건 말투(`말투.SYS`)와 줄 수(`말투.줄수`)뿐이다.
    이 함수가 하는 일은 하나 — **시간을 지키는 것.**
    스레드는 늦어도 되지만 카톡은 콜백 시간을 넘기면 손님 화면에 아무것도 안 뜬다.
    """
    담을것 = {}

    def 부르기():
        try:
            글, 됐나, 문제, _ = 풀이.문맥답글(
                씨앗, 말, 유형, 시제, 오간말=오간말,
                고른카드=카드, 고른방향=방향)
            if 됐나:
                담을것["글"] = 글
            else:
                print("     세 번 다시 시켜도 안 됨: %s" % " / ".join(문제))
        except Exception as e:
            print("     AI 부르다 터짐: %s: %s" % (type(e).__name__, e))

    일꾼 = threading.Thread(target=부르기, daemon=True)
    일꾼.start()
    일꾼.join(한계)
    return 담을것.get("글") or ""


# ── 답 만들기 ──────────────────────────────────────────────────────────
def 풀기(손님, 질문, 앞선것, 카드=None, 방향=None, 한계=콜백한계):
    """카드를 놓고 푼다. `카드` 가 오면 손님이 사이트에서 뽑아 온 것이다."""
    본것 = 분류.분류(질문, haiku써도되나=True)
    유형 = 본것["유형"] if 본것["볼까"] else "결정"
    시제 = 본것["시제"] if 본것["볼까"] else "지금"

    몇번째 = 풀이턴(앞선것) + 1
    씨앗 = 손님 if 몇번째 == 1 else "%s#%d" % (손님, 몇번째)
    fact = 엔진.digest(씨앗, 질문, 유형, 시제, tone="반말",
                       고른카드=카드, 고른방향=방향)
    if fact["중지"]:
        return {"글": fact["중지문구"], "만든법": "중지"}

    조립글 = 조립.조립(fact, 질문)
    그림 = 그림올리기.앞면주소(fact["슬러그"], fact["방향"])

    if 몇번째 == 1:
        글, 만든법 = 조립글, "조립"            # 첫 풀이는 토큰 0
    else:
        글 = AI글(씨앗, 질문, 지난대화(손님), 유형, 시제, 카드, 방향, 한계)
        만든법 = "AI(문맥)" if 글 else "조립(늦어서)"
        글 = 글 or 조립글

    return {"글": 글, "그림": 그림, "카드": fact["카드"], "방향": fact["방향"],
            "만든법": 만든법, "씨앗": 씨앗, "슬러그": fact["슬러그"]}


def 쥔카드(앞선것):
    """지금 들고 있는 카드 줄. 없으면 None."""
    for x in reversed(앞선것):
        if x.get("슬러그"):
            return x
    return None


def 들고가기(손님, 말, 앞선것, 한계):
    """**앞에 뽑은 그 카드로 계속 얘기한다.** 새로 안 뽑는다.

    사장님: "기존 주제 대화가 10턴이 될 수도 있고 20턴이 될 수도 있어"
    그래서 턴으로 자르지 않는다. 손님이 딴 얘기를 꺼낼 때까지 이 카드로 간다.
    그림은 처음 한 번만 보여준다. 같은 카드를 매번 다시 띄우면 지저분하다.
    """
    줄 = 쥔카드(앞선것)
    카드 = next((c for c in 엔진.CARDS if c.get("slug") == 줄["슬러그"]), None)
    if not 카드:
        return None
    질문 = 줄.get("질문") or 붙든질문(앞선것)
    본것 = 분류.분류(질문, haiku써도되나=False)
    유형 = 본것["유형"] if 본것["볼까"] else "결정"
    시제 = 본것["시제"] if 본것["볼까"] else "지금"
    씨앗 = 줄.get("씨앗") or 손님
    글 = AI글(씨앗, 말, 지난대화(손님), 유형, 시제, 카드, 줄["방향"], 한계)
    if not 글:
        # AI 가 빈손이면 조립으로라도 내보낸다. 카드는 그대로
        fact = 엔진.digest(씨앗, 말, 유형, 시제, tone="반말",
                           고른카드=카드, 고른방향=줄["방향"])
        글 = 조립.조립(fact, 말)
    return {"글": 글, "카드": 줄["카드"], "방향": 줄["방향"], "만든법": "이어감",
            "씨앗": 씨앗, "슬러그": 줄["슬러그"], "라인": 줄.get("라인", ""),
            "질문": 질문}


def 새로뽑기(손님, 질문, 앞선것, 라인, 한계):
    """새 주제다. 직접 라인이면 사이트로 보내고, 맡김이면 여기서 뽑는다."""
    if 라인 == "직접":
        return {"글": 말투.또뽑기, "만든법": "또뽑기", "라인": "직접", "질문": 질문}
    답 = 풀기(손님, 질문, 앞선것, 한계=한계)
    답["라인"] = 라인 or "맡김"
    답["질문"] = 질문
    return 답


def 만들기(손님, 말, 한계=콜백한계):
    """이 손님한테 지금 뭘 내줄지 전부 여기서 가른다.

    **카드 한 장 = 주제 하나 = 무제한 대화** (2026-09-24 사장님 지시).
    전에는 한 마디마다 새로 뽑아서 한 상담에 카드가 스무 장씩 나왔다.
    이제 카드를 새로 뽑는 건 셋뿐이다 — 첫 질문 / 새 주제(물어본 뒤) / 다시 뽑아달라.
    """
    앞선것 = [x for x in _읽기() if x.get("손님") == 손님]
    말 = (말 or "").strip()
    직접, 맡김 = 말투.갈림길버튼
    더뽑자, 더얘기 = 말투.새로뽑기버튼, 말투.돌아가기버튼
    버튼말 = (직접, 맡김, 더뽑자, 더얘기)
    라인 = 지금라인(앞선것)

    # 직접 라인이면 **카드 이름부터 본다.** "탑 정방향" 이 껍데기 그물에 걸리면 안 된다
    if 라인 == "직접" and 말 not in 버튼말:
        카드, 방향 = 카드알아듣기(말)
        if 카드:
            답 = 풀기(손님, 붙든질문(앞선것), 앞선것, 카드, 방향, 한계)
            답["라인"] = "직접"
            답["질문"] = 붙든질문(앞선것)
            return 답

    # 껍데기 말로 들어오면 그 자리에서 새 상담이다 (채널 나갔다 다시 온 경우 포함)
    if 말 not in 버튼말 and not 분류.볼만한가(말)[0]:
        return {"글": 말투.인사받기, "만든법": "인사", "라인": ""}

    # 새 상담 — 카드부터 뽑지 않는다. **누가 뽑을지부터 묻는다**
    if 새상담인가(앞선것) or 앞선것[-1].get("만든법") == "인사":
        return {"글": 말투.갈림길, "버튼": 말투.갈림길버튼, "만든법": "갈림길"}

    # 갈림길에서 고른 그 순간 — 여기서 라인이 정해진다
    if 말 == 직접:
        return {"글": 말투.내가뽑기, "만든법": "사이트안내",
                "라인": "직접", "질문": 첫질문(앞선것)}
    if 말 == 맡김:
        답 = 풀기(손님, 첫질문(앞선것), 앞선것, 한계=한계)
        답["라인"] = "맡김"
        답["질문"] = 첫질문(앞선것)
        return 답

    # 되돌릴 버튼 두 개
    if 말 == 더뽑자:                              # "새로 한 장 뽑아줘"
        물어본줄 = next((x for x in reversed(앞선것) if x.get("질문")), {})
        return 새로뽑기(손님, 물어본줄.get("질문") or 붙든질문(앞선것),
                        앞선것, 라인, 한계)
    if 말 == 더얘기:                              # "아까 그 카드로 돌아가"
        # 새 카드를 뽑기 전에 쥐고 있던 카드로 되돌린다
        앞카드 = [x for x in 앞선것 if x.get("슬러그")]
        되돌릴것 = 앞카드[-2] if len(앞카드) >= 2 else (앞카드[-1] if 앞카드 else None)
        if 되돌릴것:
            답 = 들고가기(손님, 되돌릴것.get("질문") or 붙든질문(앞선것),
                          앞선것 + [되돌릴것], 한계)
            if 답:
                return 답

    쥔것 = 쥔카드(앞선것)

    # 아직 카드가 없다 (직접 라인에서 기다리는 중 등)
    if not 쥔것:
        if 라인 == "직접":
            return {"글": 말투.못알아들음, "만든법": "못알아들음",
                    "라인": "직접", "질문": 붙든질문(앞선것)}
        답 = 풀기(손님, 말, 앞선것, 한계=한계)
        답["라인"] = 라인 or "맡김"
        답["질문"] = 말
        return 답

    # ── 카드를 들고 있다. **이 말이 그 카드 얘기인지 가른다** ──────────
    종류, 어떻게 = 말종류.가르기(
        chr(10).join("    %s: %s" % (누가, 글) for 누가, 글 in 지난대화(손님, 6)), 말)
    print("  말종류: %s (%s)" % (종류, 어떻게))

    if 종류 == "값질문":
        return {"글": 말투.값답, "만든법": "값질문", "라인": 라인}
    if 종류 == "봇질문":
        return {"글": 말투.봇답, "만든법": "봇질문", "라인": 라인}
    if 종류 == "마무리":
        return {"글": 말투.마무리답, "만든법": "마무리", "라인": 라인}
    if 종류 == "잡담":
        return {"글": 말투.인사받기, "만든법": "잡담", "라인": 라인}

    if 종류 in 말종류.새카드:                    # 다시뽑기 · 제3자
        return 새로뽑기(손님, 말 if 종류 == "제3자" else 붙든질문(앞선것),
                        앞선것, 라인, 한계)

    if 종류 == "새주제":
        # ⚠️ **되묻지 않는다** (팔자오빠 경험 1-②: "손님이 적은 걸 다시 묻기").
        # 손님이 "회사도 다니기 싫어" 라고 했으면 그건 이미 말한 것이다.
        # 바로 뽑아 주고, 되돌릴 길은 버튼으로만 열어 둔다. 안 누르면 그만이다
        답 = 새로뽑기(손님, 말, 앞선것, 라인, 한계)
        답.setdefault("버튼", (말투.돌아가기버튼,))
        return 답

    if 종류 == "애매":
        # 알 수 없을 때는 **카드를 쥔 쪽으로 기운다.**
        # 유지하면 최소한 대화는 이어지지만, 잘못 뽑으면 앞 얘기가 통째로 끊긴다
        답 = 들고가기(손님, 말, 앞선것, 한계)
        if 답:
            답["버튼"] = (말투.새로뽑기버튼,)
            return 답

    # 카드유지 — 이어묻기·카드질문·불신·시기·감정·예아니오
    답 = 들고가기(손님, 말, 앞선것, 한계)
    if 답:
        return 답
    답 = 풀기(손님, 말, 앞선것, 한계=한계)
    답["라인"] = 라인 or "맡김"
    return 답


def 뒤에서(손님, 말, 콜백주소):
    """"잠깐만" 을 이미 보낸 뒤 돌아가는 자리. **최소 시간을 채우고** 밀어넣는다."""
    시작 = time.time()
    try:
        답 = 만들기(손님, 말)
    except Exception as e:
        print("  만들다 터짐: %s: %s" % (type(e).__name__, e))
        답 = {"글": "지금 카드가 안 뽑히네 조금 뒤에 다시 물어봐줘", "만든법": "터짐"}

    남은 = 최소기다림 - (time.time() - 시작)
    if 남은 > 0:
        time.sleep(남은)

    적기(손님, 말, 답["글"], 답.get("카드", ""), 답.get("방향", ""), 답["만든법"],
         답.get("라인", ""), 답.get("질문", ""), 답.get("씨앗", ""), 답.get("슬러그", ""))
    코드 = 콜백으로보내기(콜백주소,
                          말풍선(답["글"], 답.get("그림"), 답.get("버튼", ())))
    print("  %s %.1f초 → 콜백 %s" % (답["만든법"], time.time() - 시작, 코드 or "실패"))


# ── 서버 ───────────────────────────────────────────────────────────────
길 = "/skill"           # --길 로 바꾼다


class 손(BaseHTTPRequestHandler):
    def _보냄(self, 몸, 코드=200):
        if not isinstance(몸, (str, bytes)):
            몸 = json.dumps(몸, ensure_ascii=False)
        if isinstance(몸, str):
            몸 = 몸.encode("utf-8")
        self.send_response(코드)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(몸)))
        self.end_headers()
        self.wfile.write(몸)

    def log_message(self, *a):
        pass                    # 요청마다 찍히면 화면이 지저분해진다

    def _몸읽기(self):
        """요청 몸통을 읽는다. chunked 로 와도 읽히게 해 둔다."""
        if "chunked" in (self.headers.get("Transfer-Encoding") or "").lower():
            덩어리 = []
            while True:
                줄 = self.rfile.readline().strip()
                if not 줄:
                    break
                try:
                    크기 = int(줄.split(b";")[0], 16)
                except ValueError:
                    break
                if 크기 == 0:
                    self.rfile.readline()
                    break
                덩어리.append(self.rfile.read(크기))
                self.rfile.readline()
            return b"".join(덩어리)
        길이 = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(길이) if 길이 else b""

    def do_GET(self):
        self._보냄({"산다": True, "길": 길})

    def do_POST(self):
        if self.path.split("?")[0] != 길:
            self._보냄({}, 코드=404)
            return
        try:
            원본 = self._몸읽기()
            # 카카오는 UTF-8 로 보낸다. 윈도 도구는 CP949 로 보내기도 한다
            try:
                글자 = 원본.decode("utf-8")
            except UnicodeDecodeError:
                글자 = 원본.decode("cp949")
            받은것 = json.loads(글자)
        except Exception as e:
            print("  몸통 못 읽음: %s | 헤더 %s" % (e, dict(self.headers)))
            self._보냄(말풍선("잠깐 문제가 있었어 다시 한 번 물어봐줘"))
            return

        온것 = 받은것.get("userRequest") or {}
        손님 = re.sub(r"[^0-9a-zA-Z\-_]", "",
                      str((온것.get("user") or {}).get("id") or ""))[:64]
        말 = (온것.get("utterance") or "").strip()[:500]
        콜백주소 = 온것.get("callbackUrl") or ""

        if not 손님 or not 말:
            self._보냄(말풍선("뭐가 궁금한지 한 줄만 적어줘"))
            return

        if 무료턴 and 지난턴(손님) + 1 > 무료턴:
            self._보냄(말풍선("여기까지가 무료야\n더 깊게 보려면 아래에서 열어줘"))
            return

        # **여기서 아무 일도 하지 않고** 바로 답한다.
        # 카드 뽑기·분류를 여기서 하면 그만큼 손님이 기다린다 (즉답 11.76초 나왔던 자리다)
        if 콜백주소:
            threading.Thread(target=뒤에서, args=(손님, 말, 콜백주소),
                             daemon=True).start()
            self._보냄(기다리라고())
            return

        # 콜백이 꺼져 있다 — 5초를 넘기면 카카오가 끊는다. 최소 기다림도 못 지킨다
        print("  callbackUrl 이 없다. 오픈빌더 블록에서 Callback 을 켜라")
        답 = 만들기(손님, 말, 한계=즉답한계)
        적기(손님, 말, 답["글"], 답.get("카드", ""), 답.get("방향", ""), 답["만든법"],
             답.get("라인", ""), 답.get("질문", ""), 답.get("씨앗", ""), 답.get("슬러그", ""))
        self._보냄(말풍선(답["글"], 답.get("그림"), 답.get("버튼", ())))


def 열기(포트=8767):
    서버 = HTTPServer(("0.0.0.0", 포트), 손)
    print("카톡 스킬 서버 열림 → http://localhost:%d%s" % (포트, 길))
    print("오픈빌더 스킬 주소칸에는 **밖에서 닿는 https 주소**를 넣어야 한다")
    print("무료 %s · 첫 턴은 갈림길 · 최소 %d초 · 검사 다섯 겹 · 콜백 %d초"
          % ("안 막음" if not 무료턴 else "%d턴" % 무료턴, 최소기다림, 콜백한계))
    print("끄려면 Ctrl+C")
    try:
        서버.serve_forever()
    except KeyboardInterrupt:
        print("\n닫음")
    return 0


def 시험(말, 손님="시험손님"):
    답 = 만들기(손님, 말, 한계=즉답한계)
    print("만든법  %s" % 답["만든법"])
    print("카드    %s %s" % (답.get("카드", ""), 답.get("방향", "")))
    print("버튼    %s" % (" / ".join(답.get("버튼", ())) or "없음"))
    print("-" * 40)
    print(답["글"])
    print("-" * 40)
    return 0


def main():
    global 길, 무료턴
    ap = argparse.ArgumentParser(description="카카오 오픈빌더 스킬 서버")
    ap.add_argument("--포트", type=int, default=8767)
    ap.add_argument("--길", default="/skill", help="주소를 숨기려면 skill/아무말")
    ap.add_argument("--시험", help="서버 안 열고 이 말로 답만 만들어 본다")
    ap.add_argument("--손님", default="시험손님", help="--시험 때 쓸 손님 아이디")
    ap.add_argument("--무료턴", type=int, default=무료턴, help="0 이면 안 막는다")
    a = ap.parse_args()
    무료턴 = a.무료턴
    길 = a.길 if a.길.startswith("/") else "/" + a.길
    if a.시험:
        return 시험(a.시험, a.손님)
    return 열기(a.포트)


if __name__ == "__main__":
    sys.exit(main())
