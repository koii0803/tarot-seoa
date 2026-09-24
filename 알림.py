# -*- coding: utf-8 -*-
"""텔레그램으로 알린다 (2026-09-24 사장님 지시).

    python 알림.py --시험              한 줄 보내 본다
    python 알림.py --보내 "할 말"

밖에서 쓸 때
    from 알림 import 보내기
    보내기("서아 답글 3건 막혔다")

왜 필요한가
    지금까지는 답글이 막혀도 **조용히 멈췄다.** 며칠 뒤에나 안다.
    팔자오빠도 같은 이유로 텔레그램을 붙였다. 하루 한 번 요약이 오면 그것만 보면 된다.

토큰
    `~/.saju_meta_tokens.json` 의 telegram_bot_token · telegram_chat_id 를 **읽기만** 한다.
    (팔자오빠가 쓰는 것과 같은 봇이다. 알림 창구를 둘로 나눌 이유가 없다)
    환경변수 TELEGRAM_BOT_TOKEN · TELEGRAM_CHAT_ID 가 있으면 그걸 먼저 쓴다.
    **값은 화면에도 기록에도 안 찍는다.**

표준 라이브러리만 쓴다. 팔자오빠 것을 하나도 부르지 않는다.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

머리말 = "🔮 서아"          # 팔자오빠 알림과 섞이니 누구 것인지 앞에 붙인다
설정파일 = os.path.expanduser("~/.saju_meta_tokens.json")


def _열쇠():
    봇 = os.environ.get("TELEGRAM_BOT_TOKEN")
    방 = os.environ.get("TELEGRAM_CHAT_ID")
    if 봇 and 방:
        return 봇.strip(), 방.strip()
    try:
        d = json.loads(io.open(설정파일, encoding="utf-8").read())
        return (d.get("telegram_bot_token") or "").strip(), str(d.get("telegram_chat_id") or "").strip()
    except Exception:
        return "", ""


def 보내기(말, 조용히=True):
    """알림 한 줄. **실패해도 절대 터지지 않는다** — 알림 때문에 봇이 멈추면 안 된다."""
    봇, 방 = _열쇠()
    if not (봇 and 방):
        if not 조용히:
            print("텔레그램 열쇠가 없다 (환경변수나 설정 파일)")
        return False
    몸 = urllib.parse.urlencode({
        "chat_id": 방,
        "text": "%s %s" % (머리말, 말),
        "disable_web_page_preview": "true",
    }).encode("utf-8")
    try:
        요청 = urllib.request.Request(
            "https://api.telegram.org/bot%s/sendMessage" % 봇, data=몸, method="POST")
        with urllib.request.urlopen(요청, timeout=20) as r:
            return json.loads(r.read().decode("utf-8")).get("ok", False)
    except Exception as e:
        if not 조용히:
            print("못 보냈다: %s" % type(e).__name__)
        return False


def main():
    ap = argparse.ArgumentParser(description="텔레그램 알림")
    ap.add_argument("--시험", action="store_true")
    ap.add_argument("--보내", metavar="말")
    a = ap.parse_args()

    if a.시험:
        됨 = 보내기("알림 시험이야. 이게 오면 앞으로 막힌 답글도 여기로 온다", 조용히=False)
        print("보냈다" if 됨 else "못 보냈다")
        return 0 if 됨 else 1
    if a.보내:
        됨 = 보내기(a.보내, 조용히=False)
        print("보냈다" if 됨 else "못 보냈다")
        return 0 if 됨 else 1
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
