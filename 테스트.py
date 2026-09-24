# -*- coding: utf-8 -*-
"""타로봇 점검. 엔진 자가진단 + "팔자오빠와 안 엮였나" 검사.

    python 테스트.py

두 번째가 핵심이다. 사장님 지시: 단 한 줄도 엮이면 안 된다.
"""
import io
import re
import sys
import subprocess
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = Path(__file__).resolve().parent

# 여기 있는 이름이 코드에 나오면 엮인 것이다
금지된_이웃 = [
    "스레드자동답글", "스레드글", "답글창고", "금고", "토큰갱신", "쇼츠발행", "일진글", "스레드하루치",
    "유튜브업로더", "쇼츠저장소", "saju-arcade", "dump-saju", "config",
]


def 분리검사():
    """타로봇 폴더 안의 .py 가 바깥을 부르지 않는지 본다."""
    bad = []
    for p in sorted(HERE.rglob("*.py")):
        if p.name == "테스트.py":
            continue          # 이 파일은 이름 목록을 갖고 있으니 건너뛴다
        src = io.open(p, encoding="utf-8").read()
        코드 = []
        for line in src.splitlines():
            s = line.strip()
            if s.startswith("#"):
                continue
            코드.append(line)
        코드 = "\n".join(코드)
        for name in 금지된_이웃:
            # 낱말 단위로만 본다. reconfigure 안의 config 같은 것에 안 걸리게
            if re.search(r"(?<![0-9A-Za-z_가-힣])%s(?![0-9A-Za-z_가-힣])" % re.escape(name), 코드):
                bad.append("%s 에 '%s' 가 있다" % (p.name, name))
        for m in re.finditer(r"^\s*(?:from|import)\s+([^\s,]+)", 코드, re.M):
            mod = m.group(1)
            if mod.startswith("."):
                continue
            뿌리 = mod.split(".")[0]
            표준 = ("io", "os", "re", "sys", "json", "time", "random", "hashlib", "argparse",
                    "datetime", "pathlib", "subprocess", "urllib", "typing", "__future__",
                    "collections", "itertools", "textwrap", "unicodedata", "math",
                    "csv", "base64", "hmac", "http", "socket", "threading", "uuid")
            # pip 로 까는 꾸러미. 팔자오빠 폴더가 아니라 남의 라이브러리라 엮임이 아니다.
            # 여기에 이름을 더할 때는 "이게 이웃 폴더가 아닌가" 를 꼭 보고 더한다
            꾸러미 = ("boto3", "botocore", "PIL", "nacl")
            # **그 파일이 있는 폴더도 본다** (2026-09-24 고침).
            #   전에는 타로봇 루트만 봤다. 그래서 카톡/부르기.py 의 `import 엔진` 이
            #   루트에 엔진.py 가 없다고 "바깥 것" 으로 잘못 잡혔다.
            #   카톡은 제 폴더 안의 엔진.py 를 부르는 게 맞다 (카톡 인수인계 0절).
            안쪽 = (HERE / (뿌리 + ".py")).exists() or (p.parent / (뿌리 + ".py")).exists()
            if 뿌리 not in 표준 and 뿌리 not in 꾸러미 and not 안쪽:
                bad.append("%s 가 바깥 것을 부른다: %s" % (p.name, mod))
    return bad


def 기록파일검사():
    """루트 .py 가 `기록/` 폴더에 쓰는 코드가 남았나. 창고.py(옮기기용)만 예외.
    웹/·카톡/ 은 PC 서버라 제 기록을 PC 에 둔다 — 그건 여기서 안 본다."""
    남은것 = []
    for p in sorted(HERE.glob("*.py")):
        if p.name in ("테스트.py", "창고.py"):
            continue
        src = io.open(p, encoding="utf-8").read()
        코드 = chr(10).join(l for l in src.splitlines() if not l.strip().startswith("#"))
        for 표시 in ('/ "기록"', "기록방", '"기록/', "'기록/", "기록/토큰", "기록/성적"):
            if 표시 in 코드:
                남은것.append("%s 에 %r" % (p.name, 표시))
    return 남은것


def main():
    print("1) 엔진 자가진단")
    r = subprocess.run([sys.executable, str(HERE / "타로엔진.py"), "--selftest"],
                       capture_output=True, encoding="utf-8", errors="replace")
    print("   " + (r.stdout or "").strip().replace("\n", "\n   "))
    엔진ok = r.returncode == 0

    print("2) 글 간격 규칙")
    import importlib
    sys.path.insert(0, str(HERE))
    발행 = importlib.import_module("발행기록")
    됨, 남은, 마지막 = 발행.올릴수있나()
    print("   최소 %d시간 · %s" % (발행.최소간격시간, 발행.사람말(남은)))
    # 2026-09-24 사장님 지시로 바닥이 4시간 → **3시간**이 됐다.
    # 실제 하루치는 4~5시간으로 짠다(하루치.py). 3시간은 넘지 말라는 선이다
    간격ok = 발행.최소간격시간 >= 3

    print("3) 팔자오빠와 분리됐나")
    bad = 분리검사()
    if bad:
        for x in bad:
            print("   엮임 → %s" % x)
    else:
        print("   깨끗하다. 바깥 것을 하나도 안 부른다")

    print("4) 기록을 PC 파일에 쓰는 데가 남았나 (2026-09-25: 기록은 전부 R2 창고)")
    남은것 = 기록파일검사()
    if 남은것:
        for x in 남은것:
            print("   PC 파일 → %s" % x)
    else:
        print("   없다. 전부 창고를 쓴다")

    print("5) R2 창고에 닿나")
    창고ok = True
    try:
        import 창고
        c = 창고.열기()
        hb = c.심장박동_지난분()
        print("   닿는다 (버킷 %s · PC 심장박동 %s)" % (c.bucket, "없음" if hb > 10 ** 5 else "%.0f분 전" % hb))
    except Exception as e:
        창고ok = False
        print("   못 닿는다: %s: %s" % (type(e).__name__, str(e)[:100]))

    print()
    if 엔진ok and not bad and 간격ok and not 남은것 and 창고ok:
        print("전부 통과")
        return 0
    print("실패")
    return 1


if __name__ == "__main__":
    sys.exit(main())
