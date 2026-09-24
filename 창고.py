# -*- coding: utf-8 -*-
"""서아 기록 창고 — **전부 R2 에 둔다** (2026-09-25 사장님 지시).

    python 창고.py --확인          R2 에 닿나 · 뭐가 들어 있나
    python 창고.py --옮기기        PC 의 기록/ 파일을 R2 로 올린다 (한 번만. 올린 뒤 읽어서 대조한다)
    python 창고.py --목록          창고 안 파일 목록 (잠겼나까지)
    python 창고.py --보기 이름      파일 하나 내용
    python 창고.py --잠그기        안 잠긴 파일을 전부 잠근다 (옮긴 직후 한 번)

왜 R2 인가
    PC 와 깃허브 대타가 **같은 것을 봐야** 같은 댓글에 두 번 답하지 않는다.
    깃허브 저장소에 두면 매 바퀴 커밋이 필요하고, 기록은 계속 자라서 저장소가 찬다 (사장님 지시: 기록은 깃허브에 안 올린다).
    팔자오빠도 같은 이유로 R2 를 쓴다. **창고는 따로다** — 팔자오빠는 `threads-reply/`, 서아는 `seoa/`.
    (서아 접두어 밖은 읽지도 쓰지도 않는다. 사장님 지시: 다른 폴더와 합치지 않는다)

창고 안 (전부 seoa/ 아래)
    답글대기.json     발행을 기다리는 답글 (대기표.py 가 고친다)
    손님기록.jsonl    누구에게 몇 턴째 답했나 + 오간 말
    발행기록.jsonl    언제 뭘 올렸나 (글 간격)
    하루치.json       오늘 예약표
    글창고.json       미리 만들어 둔 글
    상태.json         채널관리 마지막 시각 같은 자잘한 것
    잠금.json         지금 누가 바퀴를 돌리고 있나
    심장박동.json     PC 가 마지막으로 돈 시각 — 깃허브는 이걸 보고 물러난다
    자동기록.txt      바퀴가 남기는 한 줄들 (뒤 400줄만)
    토큰.log          AI 부를 때마다 토큰·값 (뒤 2000줄만)
    성적.csv          글 성적

R2 는 파일마다 '마지막에 쓴 사람이 이긴다'. 진짜 잠금은 없지만 잠금을 쓰고 잠깐 뒤 **다시 읽어
내 것인지 확인**하면 실용적으로 충분하다 (팔자오빠도 이렇게 한다). 심장박동 20분 여유까지 있으니
PC 와 깃허브가 같은 순간에 시작할 일은 사실상 없다.

**R2 가 안 되면 아무것도 안 한다.** 로컬로 대충 돌리면 PC 와 깃허브가 어긋나 중복이 난다.
열기() 가 던지는 오류를 자동.py 가 받아 텔레그램으로 알린다. 조용히 넘어가지 않는다.

한 프로세스 안에서는 읽은 것을 **캐시**한다. 손님기록을 바퀴마다 수십 번 읽는데
그때마다 R2 를 부르면 느리다. 쓰면 캐시도 같이 바뀐다. 바퀴는 한 번에 하나만 돌기 때문에(잠금) 안전하다.

boto3 는 이웃 폴더가 아니라 파이썬 꾸러미다. 그 밖은 표준 라이브러리만 쓴다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
기록방 = HERE / "기록"                      # 옛 자리. --옮기기 때만 읽는다

접두어 = "seoa/"                             # 이 밑에서만 논다. 팔자오빠 threads-reply/ 와 안 겹친다
필요한값 = ("CLOUDFLARE_ACCOUNT_ID_2", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET")

줄수한도 = {"자동기록.txt": 400, "토큰.log": 2000}     # 계속 자라는 것은 뒤만 남긴다
옮길것 = ("답글대기.json", "손님기록.jsonl", "발행기록.jsonl", "하루치.json",
          "글창고.json", "성적.csv", "토큰.log", "자동기록.txt")

# ── 잠그기 (2026-09-25 사장님 지시 "구멍 막아") ─────────────────────────
# 이 버킷은 r2.dev 공개 버킷이다. 주소만 알면 누구나 읽는다.
# 그래서 손님 얘기가 든 파일은 **암호로 잠가서** 올린다. 열쇠는 R2 비밀 열쇠에서 뽑는다
# (PC 도 깃허브도 이미 갖고 있는 값이라 새 비밀값이 안 생긴다).
# 잠긴 파일은 "enc1:" 로 시작한다. 안 잠긴 옛 파일도 읽힌다 (읽을 땐 둘 다, 쓸 땐 늘 잠근다).
# 심장박동·잠금·상태는 안 잠근다 — 개인정보가 없고, 깨우기 워커가 심장박동을 읽어야 한다.
암호화안함 = ("심장박동.json", "잠금.json", "상태.json")
잠금표시 = "enc1:"


def _열쇠():
    import hashlib
    비밀 = _값("R2_SECRET_ACCESS_KEY")
    if not 비밀:
        raise RuntimeError("R2_SECRET_ACCESS_KEY 가 없어서 창고 열쇠를 못 만든다")
    return hashlib.sha256(("seoa|" + 비밀).encode("utf-8")).digest()


def 잠그기(글):
    import base64
    from nacl.secret import SecretBox          # 파이썬 꾸러미 pynacl
    from nacl.utils import random as 난수
    상자 = SecretBox(_열쇠())
    암호 = 상자.encrypt(글.encode("utf-8"), 난수(SecretBox.NONCE_SIZE))
    return 잠금표시 + base64.b64encode(bytes(암호)).decode("ascii")


def 풀기(본문):
    import base64
    from nacl.secret import SecretBox
    상자 = SecretBox(_열쇠())
    return 상자.decrypt(base64.b64decode(본문[len(잠금표시):].strip())).decode("utf-8")


def _값(이름):
    """환경변수 → 없으면 윈도 사용자 환경변수(레지스트리). 값은 어디에도 안 찍는다."""
    v = os.environ.get(이름, "").strip()
    if v:
        return v
    if os.name != "nt":
        return ""
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             '[Environment]::GetEnvironmentVariable("%s","User")' % 이름],
            capture_output=True, text=True, timeout=10)
        return (r.stdout or "").strip()
    except Exception:
        return ""


class 창고:
    def __init__(self):
        v = {k: _값(k) for k in 필요한값}
        없는것 = [k for k, x in v.items() if not x]
        if 없는것:
            raise RuntimeError("R2 접근값이 없다: %s" % ", ".join(없는것))
        import boto3                      # 파이썬 꾸러미
        from botocore.exceptions import ClientError
        self._ClientError = ClientError
        self.bucket = v["R2_BUCKET"]
        self.s3 = boto3.client(
            "s3", endpoint_url="https://%s.r2.cloudflarestorage.com" % v["CLOUDFLARE_ACCOUNT_ID_2"],
            aws_access_key_id=v["R2_ACCESS_KEY_ID"], aws_secret_access_key=v["R2_SECRET_ACCESS_KEY"],
            region_name="auto")
        self._캐시 = {}

    # ── 글(텍스트) 읽기·쓰기 ─────────────────────────────────────
    def 글읽기(self, 이름, 기본=None, 캐시=True):
        """없으면 기본. 있으면 문자열."""
        if 캐시 and 이름 in self._캐시:
            return self._캐시[이름]
        try:
            몸 = self.s3.get_object(Bucket=self.bucket, Key=접두어 + 이름)["Body"].read()
        except self._ClientError as e:
            if e.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
                self._캐시[이름] = 기본
                return 기본
            raise
        글 = 몸.decode("utf-8")
        if 글.startswith(잠금표시):
            글 = 풀기(글)                    # 열쇠가 다르면 여기서 터진다. 조용히 빈 것으로 안 넘긴다
        self._캐시[이름] = 글
        return 글

    def 글쓰기(self, 이름, 글):
        올릴것 = 글 if 이름 in 암호화안함 else 잠그기(글)
        self.s3.put_object(Bucket=self.bucket, Key=접두어 + 이름,
                           Body=올릴것.encode("utf-8"),
                           ContentType="text/plain; charset=utf-8")
        self._캐시[이름] = 글

    def 잠겼나(self, 이름):
        """공개 주소로 봤을 때 잠겨 있나. (잠김, 없음, 열림) 중 하나."""
        try:
            몸 = self.s3.get_object(Bucket=self.bucket, Key=접두어 + 이름)["Body"].read(16)
        except self._ClientError:
            return "없음"
        return "잠김" if 몸.startswith(잠금표시.encode()) else "열림"

    def 붙이기(self, 이름, 줄):
        """한 줄 뒤에 붙인다 (jsonl · log). 한도가 있는 파일은 뒤만 남긴다."""
        글 = self.글읽기(이름, "") or ""
        if 글 and not 글.endswith("\n"):
            글 += "\n"
        글 += 줄.rstrip("\n") + "\n"
        한도 = 줄수한도.get(이름)
        if 한도:
            줄들 = 글.splitlines()
            if len(줄들) > 한도:
                글 = "\n".join(줄들[-한도:]) + "\n"
        self.글쓰기(이름, 글)

    # ── JSON ─────────────────────────────────────────────────────
    def 읽기(self, 이름, 기본=None):
        """깨진 JSON 이면 예외를 던진다. 조용히 빈 것으로 넘기면 대기표가 통째로 사라진다."""
        글 = self.글읽기(이름)
        if 글 is None or not 글.strip():
            return 기본
        return json.loads(글)

    def 쓰기(self, 이름, 자료):
        self.글쓰기(이름, json.dumps(자료, ensure_ascii=False, indent=1) + "\n")

    def 줄들(self, 이름):
        """jsonl → dict 목록. 깨진 줄은 건너뛴다 (한 줄 때문에 전체를 못 읽으면 안 된다)."""
        나온것 = []
        for line in (self.글읽기(이름, "") or "").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                나온것.append(json.loads(line))
            except Exception:
                pass
        return 나온것

    def 지우기(self, 이름):
        try:
            self.s3.delete_object(Bucket=self.bucket, Key=접두어 + 이름)
        except self._ClientError:
            pass
        self._캐시.pop(이름, None)

    def 목록(self):
        나온것, 다음 = [], None
        while True:
            kw = {"Bucket": self.bucket, "Prefix": 접두어}
            if 다음:
                kw["ContinuationToken"] = 다음
            r = self.s3.list_objects_v2(**kw)
            나온것 += [(o["Key"][len(접두어):], o["Size"]) for o in r.get("Contents", [])]
            if not r.get("IsTruncated"):
                return 나온것
            다음 = r.get("NextContinuationToken")

    def 캐시비우기(self):
        self._캐시 = {}

    # ── 잠금 (바퀴 한 번에 하나만) ────────────────────────────────
    def 잠금_잡기(self, 누구, 죽은분=30):
        """(잡았나, 누가 잡고 있나). 쓰고 나서 다시 읽어 내 것인지 확인한다."""
        지금 = dt.datetime.now()
        현재 = self.읽기("잠금.json")
        if 현재:
            try:
                시작 = dt.datetime.strptime(현재["시작"], "%Y-%m-%d %H:%M:%S")
                if (지금 - 시작).total_seconds() < 죽은분 * 60:
                    return False, 현재
            except Exception:
                pass                                  # 깨진 잠금은 가져간다
        내것 = {"누구": 누구, "pid": os.getpid(), "시작": 지금.strftime("%Y-%m-%d %H:%M:%S"),
                "표": "%d-%d" % (os.getpid(), int(time.time() * 1000))}
        self.쓰기("잠금.json", 내것)
        time.sleep(1.5)
        되읽음 = self.읽기("잠금.json") or {}
        if 되읽음.get("표") != 내것["표"]:
            return False, 되읽음                      # 같은 순간에 누가 덮어씀 → 양보
        return True, None

    def 잠금_풀기(self):
        self.지우기("잠금.json")

    # ── 심장박동 (PC 가 살아 있다는 표시) ──────────────────────────
    def 심장박동_찍기(self, 누구="PC"):
        self.쓰기("심장박동.json", {"누구": 누구, "때": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")})

    def 심장박동_지난분(self):
        """마지막 심장박동이 몇 분 전인가. 한 번도 없으면 아주 큰 수."""
        hb = self.읽기("심장박동.json")
        if not hb:
            return 10 ** 6
        try:
            때 = dt.datetime.strptime(hb["때"], "%Y-%m-%d %H:%M:%S")
            return (dt.datetime.now() - 때).total_seconds() / 60
        except Exception:
            return 10 ** 6

    # ── 상태 (자잘한 시각들) ──────────────────────────────────────
    def 상태(self, 키, 기본=None):
        return (self.읽기("상태.json") or {}).get(키, 기본)

    def 상태쓰기(self, 키, 값):
        d = self.읽기("상태.json") or {}
        d[키] = 값
        self.쓰기("상태.json", d)


# ── 한 프로세스에 하나 ────────────────────────────────────────────
_열린것 = None


def 열기():
    """창고 하나를 돌려준다. R2 에 못 닿으면 RuntimeError — 부르는 쪽이 알리고 멈춘다."""
    global _열린것
    if _열린것 is None:
        _열린것 = 창고()
    return _열린것


# ── 명령줄 ────────────────────────────────────────────────────────
def 확인():
    c = 열기()
    표 = "seoa-check"
    c.글쓰기(표 + ".txt", "ok")
    되읽음 = c.글읽기(표 + ".txt", 캐시=False)
    c.지우기(표 + ".txt")
    print("쓰기·읽기 %s (버킷 %s, 접두어 %s)" % ("OK" if 되읽음 == "ok" else "실패", c.bucket, 접두어))
    hb = c.심장박동_지난분()
    print("PC 심장박동: %s" % ("없음" if hb > 10 ** 5 else "%.0f분 전" % hb))
    print("잠금: %s" % (c.읽기("잠금.json") or "없음"))
    return 목록() if 되읽음 == "ok" else 1


def 목록():
    c = 열기()
    것들 = c.목록()
    if not 것들:
        print("창고가 비었다")
        return 0
    열린것 = 0
    for 이름, 크기 in 것들:
        상태 = "공개(개인정보 없음)" if 이름 in 암호화안함 else c.잠겼나(이름)
        if 상태 == "열림":
            열린것 += 1
        print("  %-20s %8.1fKB  %s" % (이름, 크기 / 1024.0, 상태))
    if 열린것:
        print("\n⚠️ 안 잠긴 파일 %d개. python 창고.py --잠그기" % 열린것)
    return 1 if 열린것 else 0


def 전부잠그기():
    """안 잠긴 파일을 전부 잠근다. 바퀴 잠금을 잡고 한다 (도는 중에 덮어쓰지 않게)."""
    c = 열기()
    잡았나, 누구 = c.잠금_잡기("잠그기", 죽은분=30)
    if not 잡았나:
        print("지금 %s 가 돌고 있다. 잠시 뒤 다시" % (누구 or {}).get("누구"))
        return 1
    try:
        잠근수 = 0
        for 이름, _ in c.목록():
            if 이름 in 암호화안함 or c.잠겼나(이름) != "열림":
                continue
            글 = c.글읽기(이름, 캐시=False)
            c.글쓰기(이름, 글)
            되읽음 = c.글읽기(이름, 캐시=False)
            print("  %-20s %s" % (이름, "잠금 OK" if 되읽음 == 글 and c.잠겼나(이름) == "잠김" else "!! 되읽은 게 다르다"))
            잠근수 += 1
        print("\n%d개 잠갔다" % 잠근수)
    finally:
        c.잠금_풀기()
    return 목록()


def 보기(이름):
    글 = 열기().글읽기(이름)
    if 글 is None:
        print("없다: %s" % 이름)
        return 1
    print(글)
    return 0


def 옮기기():
    """PC 기록/ → R2. 이미 R2 에 있으면 안 덮어쓴다 (두 번 돌려도 안전). 올린 뒤 읽어서 대조한다."""
    c = 열기()
    올림, 건너뜀, 실패 = 0, 0, []
    for 이름 in 옮길것:
        p = 기록방 / 이름
        if not p.exists():
            continue
        if c.글읽기(이름, 캐시=False) is not None:
            print("  %-16s R2 에 이미 있다. 안 덮어쓴다" % 이름)
            건너뜀 += 1
            continue
        글 = io.open(p, encoding="utf-8").read()
        한도 = 줄수한도.get(이름)
        if 한도:
            글 = "\n".join(글.splitlines()[-한도:]) + "\n"
        c.글쓰기(이름, 글)
        되읽음 = c.글읽기(이름, 캐시=False)
        if 되읽음 == 글:
            print("  %-16s 올림 %6.1fKB · 대조 OK" % (이름, len(글.encode("utf-8")) / 1024.0))
            올림 += 1
        else:
            print("  %-16s 올렸는데 되읽은 게 다르다!" % 이름)
            실패.append(이름)
    print("\n올림 %d · 건너뜀 %d · 실패 %d" % (올림, 건너뜀, len(실패)))
    return 1 if 실패 else 0


def main():
    ap = argparse.ArgumentParser(description="서아 기록 창고 (R2)")
    ap.add_argument("--확인", action="store_true")
    ap.add_argument("--옮기기", action="store_true", help="PC 기록/ 을 R2 로 (한 번만)")
    ap.add_argument("--목록", action="store_true")
    ap.add_argument("--보기", metavar="이름")
    ap.add_argument("--잠그기", action="store_true", help="안 잠긴 파일을 전부 잠근다")
    a = ap.parse_args()
    if a.확인:
        return 확인()
    if a.옮기기:
        return 옮기기()
    if a.목록:
        return 목록()
    if a.잠그기:
        return 전부잠그기()
    if a.보기:
        return 보기(a.보기)
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
