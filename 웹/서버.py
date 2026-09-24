# -*- coding: utf-8 -*-
"""웹 채팅 서버. 손님과 클로드 사이에서 파이썬이 와리가리 한다 (2026-09-24 사장님 지시).

    python 웹/서버.py                 열기 (http://localhost:8765)
    python 웹/서버.py --포트 9000

흐름
    손님이 채팅창에 씀
       ↓
    이 서버가 받음
       ↓
    1턴이면 조립(0초) · 2턴부터 지난 대화 통째로 넘겨 클로드 호출(15초)
       ↓
    검사 (껍데기·부호·줄수·금지어)
       ↓
    채팅창에 답 + 카드 그림
       ↓
    손님이 또 쓰면 대화 전체를 다시 넘긴다

못 박은 것
- **20초 넘으면 조립글로 대체한다.** 손님을 기다리게 두지 않는다. 조립은 0.1초라 절대 안 늦는다
- 손님은 브라우저가 만든 아이디로 구분한다. 로그인 없음
- 무료 턴이 끝나면 결제 자리로 넘긴다 (값은 아직 안 정함)
- 스레드 쪽 기록과 **섞지 않는다.** 여기는 `기록/웹손님.jsonl`

표준 라이브러리만 쓴다. 팔자오빠 것을 하나도 부르지 않는다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import re
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
뿌리 = HERE.parent
sys.path.insert(0, str(뿌리))
import 타로엔진 as 엔진
import 조립
import 분류
import 풀이
import 그림올리기
import 말투               # **웹·스레드 공용** (2026-09-24. 타로봇/말투.py 하나로 모았다)

기록방 = 뿌리 / "기록"
손님파일 = 기록방 / "웹손님.jsonl"

무료턴 = 3              # 여기까지 공짜. 그 뒤는 결제 자리 (2026-09-24 사장님 지시 5→3)
기다림한계 = 20         # 이 초를 넘기면 조립글로 대체한다


def 지금():
    return dt.datetime.now()


# ── 손님 기록 (스레드 것과 따로) ───────────────────────────────────────
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


def 적기(손님, 말, 답, 카드="", 방향="", 만든법=""):
    기록방.mkdir(exist_ok=True)
    줄 = {"때": 지금().isoformat(timespec="seconds"), "손님": 손님,
          "말": 말, "답": 답, "카드": 카드, "방향": 방향, "만든법": 만든법}
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


# ── 답 만들기 ──────────────────────────────────────────────────────────
def 답만들기(손님, 말):
    """1턴은 조립, 2턴부터 클로드. **20초 넘으면 조립으로 대체한다.**"""
    턴 = 지난턴(손님) + 1

    본것 = 분류.분류(말)
    if not 본것["볼까"]:
        return {"글": "뭐가 궁금한지 한 줄만 적어줘", "카드": "", "방향": "",
                "그림": None, "턴": 턴, "만든법": "거름"}

    유형, 시제 = 본것["유형"], 본것["시제"]
    # **웹은 카드 한 장으로 끝까지 간다** (2026-09-24). 씨앗을 손님으로 고정해서
    # 턴이 바뀌어도 같은 카드가 나온다. 턴마다 새로 뽑으면 "아까 그거 아니었어?" 가 된다
    씨앗 = 손님
    fact = 엔진.digest(씨앗, 말, 유형, 시제, tone="반말")

    if fact["중지"]:
        return {"글": fact["중지문구"], "카드": "", "방향": "",
                "그림": None, "턴": 턴, "만든법": "중지"}

    조립글 = 조립.조립(fact, 말, 턴)
    그림 = 그림올리기.앞면주소(fact["슬러그"], fact["방향"])

    # **무료 구간은 클로드를 아예 안 부른다** (2026-09-24 사장님 지시).
    #   무료는 파이썬만. 그래야 원가가 0 이고, 법으로도 AI 고지가 안 걸린다.
    #   끝맺는 법(되물음·남겨두기·단정)을 조립에도 이식해서 세 번 다 물음표로 끝나지 않는다.
    if 턴 <= 무료턴:
        return {"글": 조립글, "카드": fact["카드"], "방향": fact["방향"],
                "그림": 그림, "턴": 턴, "만든법": "조립"}

    # 결제한 뒤부터 — 클로드한테 대화 전체를 넘긴다. 늦으면 조립으로 간다
    담을것 = {}

    def 부르기():
        try:
            오간말 = 지난대화(손님)
            p = 풀이.문맥프롬프트(fact, 오간말, 말)
            # 톤(1~2 누른다 / 3~4 풀어준다 / 5~ 사람 대 사람) + 끝맺는 법(남겨두기·단정·되물음)
            턴수 = max(1, len(오간말) // 2 + 1)
            시킬말 = (말투.SYS + chr(10)*2 + 말투.톤(턴수)
                      + chr(10)*2 + 말투.끝맺기(턴수))
            out = 풀이.claude(p, 시킬말)
            글 = 풀이.다듬기(out.get("reply") or "")
            문제 = (풀이.사람글인가(글) + 풀이.부호검사(글)
                    + 풀이.줄수검사(글, 말투.줄수)
                    + 말투.글자수검사(글)
                    + ["법으로 막힌 말: " + 막 for 막 in 말투.막힌말 if 막 in 글.lower()])
            if not 문제:
                담을것["글"] = 글
        except Exception:
            pass

    일꾼 = threading.Thread(target=부르기, daemon=True)
    일꾼.start()
    일꾼.join(기다림한계)

    글 = 담을것.get("글") or 조립글
    return {"글": 글, "카드": fact["카드"], "방향": fact["방향"], "그림": 그림,
            "턴": 턴, "만든법": "AI(문맥)" if 담을것.get("글") else "조립(늦어서)"}


# ── 서버 ───────────────────────────────────────────────────────────────
class 손(BaseHTTPRequestHandler):
    def _보냄(self, 몸, 종류="application/json; charset=utf-8", 코드=200):
        if isinstance(몸, str):
            몸 = 몸.encode("utf-8")
        self.send_response(코드)
        self.send_header("Content-Type", 종류)
        self.send_header("Content-Length", str(len(몸)))
        self.end_headers()
        self.wfile.write(몸)

    def log_message(self, *a):
        pass                    # 요청마다 찍히면 화면이 지저분해진다

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            쪽 = HERE / "채팅.html"
            self._보냄(io.open(쪽, encoding="utf-8").read(), "text/html; charset=utf-8")
            return
        self._보냄("{}", 코드=404)

    def do_POST(self):
        # 주소에는 한글을 쓰지 않는다. R2 열쇠 때 한 번 겪었다 (2026-09-24)
        if self.path != "/ask":
            self._보냄("{}", 코드=404)
            return
        길이 = int(self.headers.get("Content-Length") or 0)
        try:
            받은것 = json.loads(self.rfile.read(길이).decode("utf-8"))
        except Exception:
            self._보냄(json.dumps({"오류": "못 읽음"}, ensure_ascii=False), 코드=400)
            return

        손님 = re.sub(r"[^0-9a-zA-Z\-]", "", str(받은것.get("손님") or ""))[:40] or str(uuid.uuid4())
        말 = (받은것.get("말") or "").strip()[:500]
        if not 말:
            self._보냄(json.dumps({"오류": "빈 말"}, ensure_ascii=False), 코드=400)
            return

        턴 = 지난턴(손님) + 1
        if 턴 > 무료턴:
            self._보냄(json.dumps({
                "막힘": True, "턴": 턴,
                "글": "여기까지가 무료야\n더 깊게 보려면 아래에서 열어줘",
            }, ensure_ascii=False))
            return

        답 = 답만들기(손님, 말)
        적기(손님, 말, 답["글"], 답.get("카드", ""), 답.get("방향", ""), 답.get("만든법", ""))
        답["남은무료"] = max(0, 무료턴 - 답["턴"])
        답["손님"] = 손님
        self._보냄(json.dumps(답, ensure_ascii=False))


def 열기(포트=8765):
    서버 = HTTPServer(("0.0.0.0", 포트), 손)
    print("웹 채팅 열림 → http://localhost:%d" % 포트)
    print("무료 %d턴, %d초 넘으면 조립글로 대체" % (무료턴, 기다림한계))
    print("끄려면 Ctrl+C")
    try:
        서버.serve_forever()
    except KeyboardInterrupt:
        print("\n닫음")
    return 0


def main():
    ap = argparse.ArgumentParser(description="웹 채팅 서버")
    ap.add_argument("--포트", type=int, default=8765)
    a = ap.parse_args()
    return 열기(a.포트)


if __name__ == "__main__":
    sys.exit(main())
