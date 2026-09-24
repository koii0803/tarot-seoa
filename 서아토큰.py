# -*- coding: utf-8 -*-
"""서아(@eslyn_yes) 스레드 토큰 받기. **팔자오빠 것은 건드리지 않는다.**

    python 서아토큰.py            새로 받는다
    python 서아토큰.py --확인      지금 가진 토큰이 사는지만 본다

사장님이 하는 일은 **복사 두 번**이다. 나머지는 이 스크립트가 한다.
    1) 메타 앱 화면에서 Threads 앱 시크릿 "보기" → 복사
    2) 브라우저에서 "허용" 누른 뒤 주소창 통째로 복사 (Ctrl+L, Ctrl+C)

⚠️ 브라우저가 **서아 계정으로 로그인돼 있어야 한다.**
   팔자오빠로 로그인돼 있으면 팔자오빠 토큰이 나온다.
   그래서 마지막에 계정 이름을 보고 @eslyn_yes 가 아니면 **저장하지 않고 멈춘다.**

못 박은 것
- 받은 토큰은 `~/.seoa_threads_token.json` 에만 넣는다.
  팔자오빠 쪽 저장소에는 **아무것도 쓰지 않는다.** 거기 값을 덮어쓰면 그쪽 봇이 죽는다
- 토큰·시크릿 값은 화면에도 파일 로그에도 **안 찍는다.** 길이만 말한다
- 장기 전환 주소는 `https://graph.threads.net/access_token` 이다. `v1.0/` 밑이 아니다
  (2026-09-23 여기서 한 번 막혔었다)

표준 라이브러리만 쓴다. 팔자오빠 것을 하나도 부르지 않는다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

앱아이디 = "1073964422275182"                              # Threads 앱. 팔자오빠와 같은 앱이다 (앱만 공용)
돌아올주소 = "https://sajuarcade.com/threads-callback"      # 없는 페이지라 404 떠도 맞다
권한 = ("threads_basic,threads_content_publish,threads_manage_replies,"
        "threads_read_replies,threads_manage_insights,threads_keyword_search")
시크릿화면 = ("https://developers.facebook.com/apps/1731062281302338/use_cases/customize/"
              "settings/?use_case_enum=THREADS_API&selected_tab=settings&product_route=threads-api")
허용주소 = ("https://threads.net/oauth/authorize?client_id=%s&redirect_uri=%s&scope=%s&response_type=code"
            % (앱아이디, urllib.parse.quote(돌아올주소, safe=""), 권한))

우리계정 = "eslyn_yes"                                      # 이 계정이 아니면 저장하지 않는다
토큰파일 = os.path.expanduser("~/.seoa_threads_token.json")


def 멈춤(말):
    sys.exit("[중단] " + 말)


# ── 클립보드 (값은 안 찍는다) ──────────────────────────────────────────
def 클립보드():
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
                           capture_output=True, text=True, timeout=10)
        return (r.stdout or "").strip()
    except Exception:
        return ""


def 클립보드비우기():
    subprocess.run(["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value ' '"],
                   capture_output=True, timeout=10)


def 복사받기(이름, 맞나, 안내):
    v = 클립보드()
    while not 맞나(v):
        print("\n[%s] %s" % (이름, 안내))
        input("복사했으면 엔터 → ")
        v = 클립보드()
        if not 맞나(v):
            print("  클립보드가 %s 모양이 아니다 (%d자). 다시." % (이름, len(v)))
    print("[%s] 받음" % 이름)
    클립보드비우기()
    return v


def 코드뽑기(v):
    """주소를 통째로 복사했든 code 만 복사했든 받아준다."""
    if "code=" in v:
        v = urllib.parse.parse_qs(urllib.parse.urlparse(v.strip()).query).get("code", [""])[0]
    return v.strip().split("#")[0]


# ── 스레드 부르기 ──────────────────────────────────────────────────────
def 스레드(방법, 길, **값):
    url = "https://graph.threads.net/" + 길
    몸 = None
    if 방법 == "GET":
        url += "?" + urllib.parse.urlencode(값)
    else:
        몸 = urllib.parse.urlencode(값).encode("utf-8")
    요청 = urllib.request.Request(url, data=몸, method=방법)
    try:
        with urllib.request.urlopen(요청, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        원문 = e.read().decode("utf-8", "replace")
        try:
            메시지 = json.loads(원문).get("error", {}).get("message", 원문)
        except Exception:
            메시지 = 원문
        멈춤("스레드 %s → %s %s" % (길, e.code, str(메시지)[:200]))
    except Exception as e:
        멈춤("스레드 %s → %s" % (길, type(e).__name__))


# ── 저장 (여기 말고는 아무 데도 안 쓴다) ───────────────────────────────
def 저장(토큰, 만료, 아이디, 이름):
    적을것 = {"설명": "서아(@%s) 스레드 토큰. 팔자오빠 것과 별개다" % 우리계정,
              "user_id": 아이디, "username": 이름,
              "access_token": 토큰, "expires_at": 만료,
              "받은때": dt.datetime.now().strftime("%Y-%m-%d %H:%M")}
    io.open(토큰파일, "w", encoding="utf-8").write(
        json.dumps(적을것, ensure_ascii=False, indent=2) + "\n")
    print("넣었다: %s" % 토큰파일)


def 불러오기():
    if not os.path.exists(토큰파일):
        return None
    try:
        return json.loads(io.open(토큰파일, encoding="utf-8").read())
    except Exception:
        return None


창고이름 = "토큰.json"       # R2 창고(잠겨서 올라간다). PC 와 깃허브가 같은 토큰을 본다 (2026-09-25)
갱신남은날 = 20              # 만료까지 이만큼 남으면 갱신한다
갱신간격시 = 24              # 갱신 시도는 하루 한 번만


def _창고에서():
    try:
        import 창고
        return 창고.열기().읽기(창고이름) or {}
    except Exception:
        return {}


def _창고에(적을것):
    import 창고
    창고.열기().쓰기(창고이름, 적을것)


def 토큰있나():
    """밖에서 쓴다. (토큰, 사용자아이디) 또는 (None, None).

    보는 순서 (2026-09-25)
        1. R2 창고 `토큰.json` — 갱신된 최신 토큰. PC 와 깃허브가 같은 걸 본다
        2. 환경변수 SEOA_THREADS_TOKEN · SEOA_USER_ID — 깃허브 Secrets (첫 씨앗)
        3. PC 파일 ~/.seoa_threads_token.json — 서아토큰.py 가 저장한 것
    팔자오빠 IG_ACCESS_TOKEN 과는 이름부터 다르다. 섞일 자리가 없다.
    """
    v = _창고에서()
    if v.get("access_token"):
        return v["access_token"], v.get("user_id")
    환경토큰 = (os.environ.get("SEOA_THREADS_TOKEN") or "").strip()
    if 환경토큰:
        return 환경토큰, (os.environ.get("SEOA_USER_ID") or "").strip() or None
    v = 불러오기()
    if not v or not v.get("access_token"):
        return None, None
    return v["access_token"], v.get("user_id")


def 갱신(강제=False):
    """60일 토큰을 **스스로 늘린다** (2026-09-25 사장님 지시 "토큰 자동으로 갱신").

    스레드가 주는 길: GET graph.threads.net/refresh_access_token?grant_type=th_refresh_token
    받은 지 24시간 지난, 아직 안 죽은 장기 토큰이면 새 60일 토큰을 준다.
    만료 20일 전부터 하루 한 번 시도한다. 자동.py 바퀴가 부른다.
    새 토큰은 창고 토큰.json 에 (잠겨서) 넣고, PC 면 파일에도 같이 적는다.
    (됐나, 말) 을 준다. 실패는 부르는 쪽이 알린다 — 조용히 넘기지 않는다.
    """
    v = _창고에서()
    if not v.get("access_token"):
        # 창고에 아직 없다 → 지금 가진 걸 씨앗으로 넣는다 (환경변수·파일)
        토큰, 아이디 = 토큰있나()
        if not 토큰:
            return False, "토큰이 아무 데도 없다"
        파일것 = 불러오기() or {}
        v = {"access_token": 토큰, "user_id": 아이디 or 파일것.get("user_id"),
             "username": 파일것.get("username", 우리계정),
             "expires_at": int(파일것.get("expires_at") or (time.time() + 50 * 86400)),
             "받은때": 파일것.get("받은때", "")}
        _창고에(v)
    남은일 = (int(v.get("expires_at") or 0) - int(time.time())) // 86400
    마지막시도 = v.get("갱신시도") or ""
    if not 강제:
        if 남은일 > 갱신남은날:
            return True, "아직 %d일 남았다" % 남은일
        try:
            if 마지막시도 and (time.time() - dt.datetime.fromisoformat(마지막시도).timestamp()) < 갱신간격시 * 3600:
                return True, "오늘 이미 시도했다"
        except Exception:
            pass
    v["갱신시도"] = dt.datetime.now().isoformat(timespec="minutes")
    url = "https://graph.threads.net/refresh_access_token?" + urllib.parse.urlencode(
        {"grant_type": "th_refresh_token", "access_token": v["access_token"]})
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=30) as r:
            j = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        원문 = e.read().decode("utf-8", "replace")
        try:
            메시지 = json.loads(원문).get("error", {}).get("message", 원문)
        except Exception:
            메시지 = 원문
        _창고에(v)
        return False, "갱신 실패 %s %s (만료까지 %d일)" % (e.code, str(메시지)[:120], 남은일)
    except Exception as e:
        _창고에(v)
        return False, "갱신 실패 %s (만료까지 %d일)" % (type(e).__name__, 남은일)
    새것 = j.get("access_token")
    if not 새것:
        _창고에(v)
        return False, "갱신 응답에 토큰이 없다 (만료까지 %d일)" % 남은일
    v.update({"access_token": 새것, "expires_at": int(time.time()) + int(j.get("expires_in") or 60 * 86400),
              "받은때": dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "갱신됨": v["갱신시도"]})
    _창고에(v)
    if os.path.exists(토큰파일):
        try:
            저장(새것, v["expires_at"], v.get("user_id"), v.get("username", 우리계정))
        except Exception:
            pass
    return True, "토큰을 새로 받았다. 만료 %s" % dt.datetime.fromtimestamp(v["expires_at"]).strftime("%Y-%m-%d")


def 확인():
    v = _창고에서() or 불러오기()
    if not v:
        print("아직 토큰이 없다. python 서아토큰.py 로 받는다")
        return 1
    남은 = int(v.get("expires_at", 0)) - int(time.time())
    print("계정 @%s (%s)" % (v.get("username"), v.get("user_id")))
    print("토큰 %d자 · 만료까지 %d일" % (len(v.get("access_token") or ""), 남은 // 86400))
    me = 스레드("GET", "v1.0/me", fields="id,username", access_token=v["access_token"])
    print("살아 있다 → @%s" % me.get("username"))
    return 0


def 받기():
    print("서아(@%s) 스레드 토큰을 받는다. 팔자오빠 것은 안 건드린다.\n" % 우리계정)

    # 1) 앱 시크릿 — 32자리 16진수
    print("① 이 화면에서 'Threads 앱 시크릿 코드' 보기 → 복사")
    print("   %s\n" % 시크릿화면)
    시크릿 = 복사받기("앱 시크릿",
                      lambda v: bool(re.fullmatch(r"[0-9a-f]{32}", (v or "").strip())),
                      "시크릿을 복사해라 (32자리)")
    시크릿 = 시크릿.strip()

    # 2) 허용 → 돌아온 주소
    print("\n② 이 주소를 **서아 계정으로 로그인된 브라우저**에서 열고 '허용'을 눌러라")
    print("   %s" % 허용주소)
    print("   404 페이지가 떠도 맞다. 그 주소창을 통째로 복사해라 (Ctrl+L, Ctrl+C)\n")
    주소 = 복사받기("돌아온 주소",
                    lambda v: "code=" in (v or ""),
                    "허용 누른 뒤 주소창을 복사해라")
    코드 = 코드뽑기(주소)
    if not 코드:
        멈춤("주소에서 code 를 못 찾았다")

    # 3) 단기 → 장기
    print("\n③ 토큰 바꾸는 중…")
    j = 스레드("POST", "oauth/access_token", client_id=앱아이디, client_secret=시크릿,
               grant_type="authorization_code", redirect_uri=돌아올주소, code=코드)
    단기 = j.get("access_token")
    if not 단기:
        멈춤("단기 토큰이 안 왔다")
    print("   단기 토큰 받음 (%d자)" % len(단기))

    j = 스레드("GET", "access_token", grant_type="th_exchange_token",
               client_secret=시크릿, access_token=단기)
    장기 = j.get("access_token")
    if not 장기:
        멈춤("장기 토큰이 안 왔다")
    만료 = int(time.time()) + int(j.get("expires_in", 0))
    print("   장기 토큰 받음 (%d자, 만료 %s)"
          % (len(장기), dt.datetime.fromtimestamp(만료).strftime("%Y-%m-%d")))

    # 4) 누구 토큰인지 확인 — 여기서 걸러야 사고가 안 난다
    me = 스레드("GET", "v1.0/me", fields="id,username,name", access_token=장기)
    이름 = (me.get("username") or "").lstrip("@").lower()
    print("\n④ 누구 토큰인가 → @%s" % 이름)
    if 이름 != 우리계정:
        멈춤("서아 계정이 아니다(@%s). 저장하지 않았다.\n"
             "       브라우저에서 서아로 로그인하고 다시 해라.\n"
             "       그대로 저장했으면 팔자오빠 것과 섞였을 뻔했다." % 이름)

    저장(장기, 만료, me.get("id"), 이름)
    print("\n끝. 이제 python 서아토큰.py --확인 으로 언제든 살았는지 본다")
    return 0


def 넣기():
    """메타 화면의 **사용자 토큰 생성기**로 받은 장기 토큰을 클립보드에서 받아 넣는다.

    메타 앱 → 이용 사례 → Threads API → 설정 → 맨 아래 "사용자 토큰 생성기"
    → `eslyn_yes` 줄의 [액세스 토큰 생성하기] → 나온 토큰 복사.

    이 길이 제일 짧다. 허용 화면도, 앱 시크릿도, 브라우저 계정 바꾸기도 필요 없다.
    """
    print("메타 '사용자 토큰 생성기'에서 eslyn_yes 토큰을 만들어 복사해라.\n")
    토큰 = 복사받기("토큰",
                    lambda v: len((v or "").strip()) > 40 and " " not in (v or "").strip(),
                    "생성된 토큰을 복사해라")
    토큰 = 토큰.strip()
    print("   토큰 받음 (%d자)" % len(토큰))

    me = 스레드("GET", "v1.0/me", fields="id,username,name", access_token=토큰)
    이름 = (me.get("username") or "").lstrip("@").lower()
    print("\n누구 토큰인가 → @%s" % 이름)
    if 이름 != 우리계정:
        멈춤("서아 계정이 아니다(@%s). 저장하지 않았다.\n"
             "       생성기에서 eslyn_yes 줄의 버튼을 눌렀는지 봐라." % 이름)

    # 생성기 토큰은 60일짜리다. 만료 시각을 안 주므로 60일 뒤로 적어 둔다(추정)
    만료 = int(time.time()) + 60 * 86400
    저장(토큰, 만료, me.get("id"), 이름)
    print("만료는 60일 뒤로 적었다(추정). 실제로는 생성기 화면 기준이다")
    print("\n끝. python 서아토큰.py --확인 으로 언제든 살았는지 본다")
    return 0


def main():
    ap = argparse.ArgumentParser(description="서아 스레드 토큰 받기")
    ap.add_argument("--확인", action="store_true", help="가진 토큰이 사는지만 본다")
    ap.add_argument("--넣기", action="store_true",
                    help="메타 '사용자 토큰 생성기'로 받은 토큰을 클립보드에서 넣는다 (제일 짧은 길)")
    ap.add_argument("--갱신", action="store_true", help="지금 당장 갱신해 본다 (바퀴는 만료 20일 전부터 알아서 한다)")
    a = ap.parse_args()
    if a.확인:
        return 확인()
    if a.갱신:
        됨, 말 = 갱신(강제=True)
        print(말)
        return 0 if 됨 else 1
    if a.넣기:
        return 넣기()
    return 받기()


if __name__ == "__main__":
    sys.exit(main())
