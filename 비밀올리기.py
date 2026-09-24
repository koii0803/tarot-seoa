# -*- coding: utf-8 -*-
"""깃허브 대타가 쓸 비밀값을 tarot-seoa 저장소 Secrets 에 넣는다 (2026-09-25).

    python 비밀올리기.py              PC 에 있는 값을 전부 올린다 (R2 · 텔레그램 · 서아 토큰)
    python 비밀올리기.py --클로드     클립보드의 클로드 토큰을 올린다 (`claude setup-token` 으로 받은 것)
    python 비밀올리기.py --워커       워커 seoa-wake 에 깃허브 열쇠를 넣는다 (gh 토큰을 파이프로)
    python 비밀올리기.py --공개       깃 역사를 한 커밋으로 밀고 저장소를 공개로 (액션 시간 무제한)
    python 비밀올리기.py --목록       지금 저장소에 뭐가 들어 있나 (이름만)

**값은 화면에도 파일에도 안 찍는다.** gh 에 표준입력으로만 넘긴다.
팔자오빠 저장소(insta-shots2)는 건드리지 않는다. 이름부터 다르다 (SEOA_*).

어디서 가져오나
    R2 넷 + R2_PUBLIC_URL    윈도 사용자 환경변수 (그림올리기.py 가 쓰는 것과 같은 값)
    텔레그램 둘             ~/.saju_meta_tokens.json (알림.py 가 읽는 것과 같은 봇)
    서아 스레드 토큰·아이디   ~/.seoa_threads_token.json (서아토큰.py 가 저장한 것)
    클로드 토큰             PC 에 없다. `claude setup-token` 을 사장님이 한 번 돌려서 나온 값을 클립보드에 두고 --클로드

토큰이 60일마다 바뀌면(서아토큰.py 다시 받으면) 이 파일을 다시 돌린다. 안 그러면 깃허브 대타만 옛 토큰으로 돈다.

표준 라이브러리만 쓴다.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

저장소 = "koii0803/tarot-seoa"
GH = r"C:\Program Files\GitHub CLI\gh.exe" if os.path.exists(r"C:\Program Files\GitHub CLI\gh.exe") else "gh"


def _환경(이름):
    v = os.environ.get(이름, "").strip()
    if v:
        return v
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command",
                            '[Environment]::GetEnvironmentVariable("%s","User")' % 이름],
                           capture_output=True, text=True, timeout=10)
        return (r.stdout or "").strip()
    except Exception:
        return ""


def _파일(경로):
    try:
        return json.loads(io.open(os.path.expanduser(경로), encoding="utf-8").read())
    except Exception:
        return {}


def 넣기(이름, 값):
    if not 값:
        print("  %-24s 값이 없다 → 건너뜀" % 이름)
        return False
    r = subprocess.run([GH, "secret", "set", 이름, "-R", 저장소], input=값, text=True,
                       capture_output=True, encoding="utf-8")
    print("  %-24s %s" % (이름, "넣음 (%d자)" % len(값) if r.returncode == 0
                          else "실패: " + (r.stderr or r.stdout).strip()[:100]))
    return r.returncode == 0


def 전부():
    print("tarot-seoa Secrets 에 넣는다 (값은 안 찍는다)")
    값들 = {k: _환경(k) for k in ("CLOUDFLARE_ACCOUNT_ID_2", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY",
                                  "R2_BUCKET", "R2_PUBLIC_URL")}
    메타 = _파일("~/.saju_meta_tokens.json")
    값들["TELEGRAM_BOT_TOKEN"] = (메타.get("telegram_bot_token") or "").strip()
    값들["TELEGRAM_CHAT_ID"] = str(메타.get("telegram_chat_id") or "").strip()
    서아 = _파일("~/.seoa_threads_token.json")
    if 서아 and (서아.get("username") or "").lower() != "eslyn_yes":
        sys.exit("서아 토큰 파일이 서아 계정이 아니다 (@%s). 안 올린다" % 서아.get("username"))
    값들["SEOA_THREADS_TOKEN"] = (서아.get("access_token") or "").strip()
    값들["SEOA_USER_ID"] = str(서아.get("user_id") or "").strip()
    됨 = sum(넣기(k, v) for k, v in 값들.items())
    print("\n%d / %d 넣었다" % (됨, len(값들)))
    if not _환경("CLAUDE_CODE_OAUTH_TOKEN"):
        print("CLAUDE_CODE_OAUTH_TOKEN 은 PC 에 없다. `claude setup-token` 돌려서 나온 값 복사 → python 비밀올리기.py --클로드")
    return 0 if 됨 == len(값들) else 1


def 클로드():
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
                           capture_output=True, text=True, timeout=10)
        값 = (r.stdout or "").strip()
    except Exception:
        값 = ""
    import re
    m = re.search(r"sk-ant-[A-Za-z0-9_\-]{20,}", 값)      # 앞뒤에 딴 글이 붙어 있어도 토큰만 뽑는다
    값 = m.group(0) if m else ""
    if not 값:
        print("클립보드에 클로드 토큰(sk-ant-…)이 없다. `claude setup-token` 결과를 복사하고 다시")
        return 1
    ok = 넣기("CLAUDE_CODE_OAUTH_TOKEN", 값)
    subprocess.run(["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value ' '"], capture_output=True)
    return 0 if ok else 1


def 워커():
    """워커 seoa-wake 에 깃허브 열쇠(gh 의 토큰)를 넣는다.

    파워셸에 CLOUDFLARE_API_TOKEN 이 잡혀 있으면 wrangler 가 그걸 먼저 써서 권한 오류가 난다 (2026-09-24 실제로 났다).
    그래서 여기서 그 둘을 빼고 부른다. 값은 파이프로만 넘긴다.
    """
    r = subprocess.run([GH, "auth", "token"], capture_output=True, text=True, encoding="utf-8")
    토큰 = (r.stdout or "").strip()
    if not 토큰:
        print("gh 토큰이 없다. `gh auth login` 먼저")
        return 1
    환경 = dict(os.environ)
    환경.pop("CLOUDFLARE_API_TOKEN", None)
    환경.pop("CLOUDFLARE_ACCOUNT_ID", None)
    워커방 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "워커")
    npx = r"C:\Program Files\nodejs\npx.cmd" if os.path.exists(r"C:\Program Files\nodejs\npx.cmd") else "npx"
    # wrangler 는 npx 가 그때그때 받아 쓴다 (다른 폴더 것을 안 빌린다 — 분리 규칙). 로그인은 사용자 설정에 있어서 그대로 된다
    r = subprocess.run([npx, "-y", "wrangler@4", "secret", "put", "GITHUB_TOKEN"],
                       input=토큰, text=True, capture_output=True, encoding="utf-8", cwd=워커방, env=환경)
    끝 = (r.stdout + r.stderr).strip().splitlines()[-3:]
    print(chr(10).join("  " + x for x in 끝))
    if r.returncode != 0:
        print("실패했다. 위 줄을 보여줘")
        return 1
    import urllib.request, json as _j
    try:
        요청 = urllib.request.Request("https://seoa-wake.bobomusic83.workers.dev",
                                      headers={"User-Agent": "Mozilla/5.0"})     # 클라우드플레어가 파이썬 이름표를 막는다
        with urllib.request.urlopen(요청, timeout=20) as f:
            상태 = _j.loads(f.read().decode("utf-8"))
        print("워커 상태: token=%s → %s" % (상태.get("token"), "됐다" if 상태.get("token") else "아직 안 들어갔다"))
    except Exception as e:
        print("워커 상태를 못 읽었다: %s" % type(e).__name__)
    return 0


def 공개():
    """저장소를 공개로 바꾼다 (액션 무료 시간 무제한). 그 전에 **깃 역사를 한 커밋으로 민다** —
    옛 커밋에 카톡 비밀 경로가 적힌 문서가 있어서다. AI 는 이 작업(force push)이 막혀 있어 사장님이 돌린다."""
    여기 = os.path.dirname(os.path.abspath(__file__))
    def git(*args):
        r = subprocess.run(["git", *args], cwd=여기, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            print("git %s 실패: %s" % (" ".join(args[:2]), (r.stderr or r.stdout).strip()[:200]))
            raise SystemExit(1)
        return (r.stdout or "").strip()
    if git("status", "--porcelain"):
        print("커밋 안 된 변경이 있다. 먼저 정리한다")
        git("add", "-A")
        git("-c", "user.name=seoa", "-c", "user.email=jmj0803@gmail.com", "commit", "-q", "-m", "공개 전 정리")
    git("checkout", "-q", "--orphan", "새출발")
    git("add", "-A")
    git("-c", "user.name=seoa", "-c", "user.email=jmj0803@gmail.com", "commit", "-q", "-m",
        "서아 타로봇 — 기록은 R2 창고(잠금), PC 5분 · 깃허브 대타 · seoa-wake 워커, 토큰 자동 갱신" + chr(10) * 2 +
        "역사를 한 커밋으로 밀었다 (공개 전환 전, 문서의 옛 비밀 경로 제거).")
    git("branch", "-D", "master")
    git("branch", "-m", "master")
    git("push", "-f", "-q", "origin", "master")
    print("깃 역사 정리 → 한 커밋으로 올렸다")
    r = subprocess.run([GH, "repo", "edit", 저장소, "--visibility", "public", "--accept-visibility-change-consequences"],
                       capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print("공개 전환 실패: " + (r.stderr or r.stdout).strip()[:200])
        return 1
    print("저장소를 공개로 바꿨다: https://github.com/%s" % 저장소)
    return 0


def 목록():
    r = subprocess.run([GH, "secret", "list", "-R", 저장소], capture_output=True, text=True, encoding="utf-8")
    print(r.stdout or r.stderr)
    return r.returncode


def main():
    ap = argparse.ArgumentParser(description="깃허브 Secrets 넣기")
    ap.add_argument("--클로드", action="store_true")
    ap.add_argument("--워커", action="store_true", help="워커 seoa-wake 에 깃허브 열쇠 넣기")
    ap.add_argument("--공개", action="store_true", help="깃 역사를 한 커밋으로 밀고 저장소를 공개로 (사장님이 돌린다)")
    ap.add_argument("--목록", action="store_true")
    a = ap.parse_args()
    if a.클로드:
        return 클로드()
    if a.워커:
        return 워커()
    if a.공개:
        return 공개()
    if a.목록:
        return 목록()
    return 전부()


if __name__ == "__main__":
    sys.exit(main())
