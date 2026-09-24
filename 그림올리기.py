# -*- coding: utf-8 -*-
"""카드 그림을 R2(공개 버킷)에 올린다. 스레드 답글에 사진을 붙이려면 이게 먼저다.

스레드는 파일을 직접 못 받는다. "이 주소의 사진을 올려줘" 방식이라
그림이 인터넷 주소를 갖고 있어야 한다. 그 주소를 만드는 자리다.

    python 그림올리기.py --확인             R2 연결 시험 (작은 파일 올리고 읽고 지움)
    python 그림올리기.py --올리기            뒷면 + 앞면 22장 올리고 주소표 저장
    python 그림올리기.py --올리기 --뒷면만    뒷면 한 장만
    python 그림올리기.py --목록             지금 올라가 있는 것
    python 그림올리기.py --주소 13-death    한 장 주소만 보기
    python 그림올리기.py --지우기            우리 접두어 아래 것만 지운다 (되묻고 지운다)

밖에서 쓸 때:
    from 그림올리기 import 뒷면주소, 앞면주소
    뒷면주소()             # 뒷면 공개 주소 (주소표에서 읽는다. 없으면 None)
    앞면주소("13-death")   # 앞면 공개 주소

못 박은 것
- **PNG 로 올린다.** 스레드가 받는 그림은 JPEG · PNG 뿐이다. webp 는 안 받는다
- 홈페이지 때 쓰던 공개 버킷을 같이 쓰되 **접두어 `tarot/` 아래만** 건드린다.
  올리기도 지우기도 이 접두어 밖으로는 절대 안 나간다 (팔자오빠 것과 안 겹친다)
- 올린 뒤 **공개 주소로 실제로 읽어 본다.** 200 이 아니면 실패로 친다
- 접근값은 윈도 사용자 환경변수를 읽기만 한다. 파일에 적지 않는다
"""
import argparse
import io
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
IMG_DIR = HERE.parent / "카드이미지" / "타로22장"
REV_DIR = HERE.parent / "카드이미지" / "타로22장_역방향"   # 180도 돌린 것. --역방향 이 만든다
BACK_PNG = HERE.parent / "카드이미지" / "타로-카드뒷면.png"
카드표 = HERE / "데이터" / "카드22.json"
주소표 = HERE / "데이터" / "그림주소.json"

접두어 = "tarot/"          # 이 밑에서만 논다
필요한값 = ("R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET",
            "R2_PUBLIC_URL", "CLOUDFLARE_ACCOUNT_ID_2")


# ── 접근값 ────────────────────────────────────────────────────────────
def 사용자환경변수(이름):
    """윈도 사용자 환경변수. 프로세스에 없으면 레지스트리에서 읽는다."""
    v = os.environ.get(이름)
    if v:
        return v.strip()
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             '[Environment]::GetEnvironmentVariable("%s","User")' % 이름],
            capture_output=True, text=True, timeout=10)
        return ((r.stdout or "").strip()) or None
    except Exception:
        return None


def 접근값():
    v = {k: 사용자환경변수(k) for k in 필요한값}
    없는것 = [k for k, x in v.items() if not x]
    if 없는것:
        sys.exit("R2 접근값이 없다: %s (윈도 사용자 환경변수)" % ", ".join(없는것))
    return v


def 창구():
    import boto3          # 이웃 폴더가 아니라 파이썬 꾸러미다
    v = 접근값()
    return boto3.client(
        "s3",
        endpoint_url="https://%s.r2.cloudflarestorage.com" % v["CLOUDFLARE_ACCOUNT_ID_2"],
        aws_access_key_id=v["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=v["R2_SECRET_ACCESS_KEY"],
        region_name="auto")


def 공개주소(열쇠):
    return (사용자환경변수("R2_PUBLIC_URL") or "").rstrip("/") + "/" + 열쇠


# r2.dev 앞에 클라우드플레어가 있어서 파이썬 기본 이름표로 부르면 403 이 온다.
# 브라우저인 척해야 읽힌다 (2026-09-23 확인). 사람이 보는 것과 같은 값이 나오게 하려는 것뿐이다.
브라우저이름표 = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def 읽어보기(url, 기다림=20):
    """공개 주소로 실제로 읽히는지(200) 본다."""
    try:
        req = urllib.request.Request(url, method="GET",
                                     headers={"User-Agent": 브라우저이름표})
        with urllib.request.urlopen(req, timeout=기다림) as r:
            r.read(1)
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return 0


# ── 올릴 것 고르기 ────────────────────────────────────────────────────
def 카드목록():
    """카드22.json 에서 슬러그와 PNG 파일 이름을 가져온다. 파일 이름을 여기서 지어내지 않는다."""
    데이터 = json.loads(io.open(카드표, encoding="utf-8").read())
    카드들 = 데이터.get("cards", 데이터) if isinstance(데이터, dict) else 데이터
    나온것 = []
    for c in 카드들:
        png = c.get("imgPng") or ""
        슬러그 = c.get("slug") or Path(png).stem
        if png:
            나온것.append((슬러그, IMG_DIR / png))
    return 나온것


def 역방향만들기(다시=False):
    """정방향 그림을 180도 돌려 역방향 그림을 만든다.

    역방향으로 나온 카드는 그림도 거꾸로여야 말이 된다. 손으로 뽑을 때와 같다.
    이미 있으면 건너뛴다 (--역방향 --다시 면 새로 만든다).
    """
    from PIL import Image          # 이웃 폴더가 아니라 파이썬 꾸러미다
    REV_DIR.mkdir(parents=True, exist_ok=True)
    만듦, 건너뜀 = 0, 0
    for 슬러그, 경로 in 카드목록():
        나갈곳 = REV_DIR / (경로.stem + "-rev.png")
        if 나갈곳.exists() and not 다시:
            건너뜀 += 1
            continue
        with Image.open(경로) as im:
            im.rotate(180, expand=True).save(나갈곳, format="PNG", optimize=True)
        만듦 += 1
    print("역방향 그림: 새로 %d장, 그대로 둔 것 %d장 → %s" % (만듦, 건너뜀, REV_DIR.name))
    return 0


def 올릴것(뒷면만=False):
    목록 = [("뒷면", BACK_PNG, 접두어 + "card-back.png")]
    if not 뒷면만:
        for 슬러그, 경로 in 카드목록():
            목록.append((슬러그, 경로, 접두어 + 경로.name))
            거꾸로 = REV_DIR / (경로.stem + "-rev.png")
            if 거꾸로.exists():
                목록.append((슬러그 + "-역", 거꾸로, 접두어 + 거꾸로.name))
    return 목록


# ── 일 ────────────────────────────────────────────────────────────────
def 올리기(뒷면만=False):
    목록 = 올릴것(뒷면만)
    없는파일 = [str(p) for _, p, _ in 목록 if not p.exists()]
    if 없는파일:
        sys.exit("그림 파일이 없다:\n  " + "\n  ".join(없는파일))

    s3 = 창구()
    통 = 접근값()["R2_BUCKET"]
    결과, 실패 = {}, []
    for 이름, 경로, 열쇠 in 목록:
        s3.upload_file(str(경로), 통, 열쇠,
                       ExtraArgs={"ContentType": "image/png",
                                  "CacheControl": "public, max-age=31536000"})
        url = 공개주소(열쇠)
        코드 = 읽어보기(url)
        print("  %-20s %8.1fKB  %s" % (이름, 경로.stat().st_size / 1024.0,
                                       "OK" if 코드 == 200 else "읽기 %s" % 코드))
        if 코드 != 200:
            실패.append(이름)
        결과[이름] = url

    if 실패:
        print("\n올렸는데 공개 주소로 안 읽히는 것: %s" % ", ".join(실패))
        print("버킷 공개(r2.dev)가 꺼져 있는지 본다. 스레드는 읽히는 주소만 받는다")

    기존 = _주소표()
    기존.update(결과)
    적을것 = {
        "설명": "카드 그림의 공개 주소. 스레드 답글에 사진 붙일 때 이 주소를 넘긴다 (PNG 만)",
        "접두어": 접두어,
        "올린때": time.strftime("%Y-%m-%d %H:%M:%S"),
        "주소": 기존,
    }
    주소표.parent.mkdir(parents=True, exist_ok=True)
    io.open(주소표, "w", encoding="utf-8").write(
        json.dumps(적을것, ensure_ascii=False, indent=2) + "\n")
    print("\n주소표 저장: %s (%d개)" % (주소표.name, len(기존)))
    return 0 if not 실패 else 1


def 목록보기():
    s3 = 창구()
    통 = 접근값()["R2_BUCKET"]
    다음 = None
    개수, 바이트 = 0, 0
    while True:
        kw = {"Bucket": 통, "Prefix": 접두어}
        if 다음:
            kw["ContinuationToken"] = 다음
        r = s3.list_objects_v2(**kw)
        for o in r.get("Contents", []):
            print("  %-32s %8.1fKB" % (o["Key"], o["Size"] / 1024.0))
            개수 += 1
            바이트 += o["Size"]
        if not r.get("IsTruncated"):
            break
        다음 = r.get("NextContinuationToken")
    print("  모두 %d개, %.1fMB" % (개수, 바이트 / 1024.0 / 1024.0))
    return 0


def 연결시험():
    s3 = 창구()
    통 = 접근값()["R2_BUCKET"]
    열쇠 = 접두어 + "_check.txt"      # 열쇠는 영문만. 주소에 한글이 들어가면 깨진다
    s3.put_object(Bucket=통, Key=열쇠, Body=b"ok", ContentType="text/plain")
    앞 = 읽어보기(공개주소(열쇠))
    s3.delete_object(Bucket=통, Key=열쇠)
    뒤 = 읽어보기(공개주소(열쇠))
    print("올리기 OK · 공개읽기 %s · 지운 뒤 %s (버킷 %s, 접두어 %s)" % (앞, 뒤, 통, 접두어))
    print("공개 주소 앞자리: %s" % 공개주소(""))
    return 0 if 앞 == 200 else 1


def 지우기():
    s3 = 창구()
    통 = 접근값()["R2_BUCKET"]
    r = s3.list_objects_v2(Bucket=통, Prefix=접두어)
    열쇠들 = [o["Key"] for o in r.get("Contents", []) if o["Key"].startswith(접두어)]
    if not 열쇠들:
        print("지울 게 없다")
        return 0
    print("%d개를 지운다:" % len(열쇠들))
    for k in 열쇠들[:5]:
        print("  " + k)
    if len(열쇠들) > 5:
        print("  … 외 %d개" % (len(열쇠들) - 5))
    if input("정말 지울까? (지운다 라고 쳐야 지움) ").strip() != "지운다":
        print("안 지웠다")
        return 0
    for k in 열쇠들:
        s3.delete_object(Bucket=통, Key=k)
    print("지웠다")
    return 0


# ── 밖에서 쓰는 것 ────────────────────────────────────────────────────
def _주소표():
    if not 주소표.exists():
        return {}
    try:
        return json.loads(io.open(주소표, encoding="utf-8").read()).get("주소", {})
    except Exception:
        return {}


def 뒷면주소():
    return _주소표().get("뒷면")


# 스레드에는 **항상 정방향 그림**을 올린다 (2026-09-24 사장님 지적).
#
# 처음엔 역방향이면 180도 돌린 그림을 올렸다. 손으로 뽑을 때와 같으니 맞다고 봤는데,
# 실제로 올려 보니 **제목 글씨(THE HANGED MAN)와 로마숫자까지 뒤집혀서** 업로드 사고로 보였다.
# 게다가 매달린 사람은 원래 거꾸로 매달린 그림이라 뒤집으니 똑바로 서 버렸다.
# 역방향은 글로 말한다. 그림은 똑바로 보여준다.
#
# 돌린 그림 22장은 R2 에 그대로 둔다 (사이트 도감·공유 이미지에 쓸 자리가 있다).
# 다시 쓰려면 이 값만 True 로 바꾸면 된다.
역방향그림쓰기 = False


def 앞면주소(슬러그, 방향="정방향"):
    """엔진의 `슬러그`(fool)로 찾는다. 파일 이름 꼴(00-fool)로 물어도 찾아준다.

    `역방향그림쓰기` 가 켜져 있을 때만 돌린 그림을 준다. 기본은 늘 정방향이다.
    """
    표 = _주소표()
    이름 = str(슬러그)
    if 이름 and 이름[:1].isdigit():
        이름 = 이름.split("-", 1)[-1]
    if 역방향그림쓰기 and ("역" in str(방향) or "revers" in str(방향).lower()):
        거꾸로 = 표.get(이름 + "-역")
        if 거꾸로:
            return 거꾸로
    return 표.get(이름)


def main():
    p = argparse.ArgumentParser(description="카드 그림을 R2 에 올린다")
    p.add_argument("--확인", action="store_true", help="연결 시험")
    p.add_argument("--역방향", action="store_true", help="정방향을 180도 돌려 역방향 그림 만들기")
    p.add_argument("--다시", action="store_true", help="이미 있어도 새로 만들기")
    p.add_argument("--올리기", action="store_true", help="그림 올리기")
    p.add_argument("--뒷면만", action="store_true", help="뒷면 한 장만")
    p.add_argument("--목록", action="store_true", help="올라가 있는 것 보기")
    p.add_argument("--주소", metavar="슬러그", help="한 장 주소 보기")
    p.add_argument("--지우기", action="store_true", help="우리 접두어 아래 것 지우기")
    a = p.parse_args()

    if a.확인:
        return 연결시험()
    if a.역방향:
        return 역방향만들기(다시=a.다시)
    if a.올리기:
        return 올리기(뒷면만=a.뒷면만)
    if a.목록:
        return 목록보기()
    if a.주소:
        url = 뒷면주소() if a.주소 in ("뒷면", "back") else 앞면주소(a.주소)
        print(url or "주소표에 없다. 먼저 --올리기")
        return 0 if url else 1
    if a.지우기:
        return 지우기()
    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
