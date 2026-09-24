# -*- coding: utf-8 -*-
"""스케줄러가 부르는 자리. 이것만 돌면 계정이 굴러간다 (2026-09-25 클라우드 대타 붙임).

    python 자동.py --바퀴            한 바퀴 (PC 스케줄러가 5분마다)
    python 자동.py --바퀴 --대타     깃허브가 부른다. **PC 심장박동이 20분 넘게 없을 때만** 돈다
    python 자동.py --심장박동        PC 가 몇 분 전에 살아 있었나 (숫자 하나)
    python 자동.py --붙이기          윈도 작업 스케줄러에 등록 (한 번만)
    python 자동.py --떼기 / --상태

바퀴 하나가 전부 한다 (아침·채널관리 일감을 따로 두지 않는다 — 셋이 겹쳐 돌다 표를 날린 적이 있다)
    0. R2 창고에 닿나. 못 닿으면 **아무것도 안 하고 알린다**
    1. 잠금. 이미 누가 돌고 있으면 물러난다 (PC 끼리도, PC·깃허브끼리도)
    2. PC 면 심장박동을 찍는다. 깃허브(대타)는 안 찍는다 — 찍으면 자기가 PC 인 줄 안다
    3. 오늘 하루치가 없고 04시가 지났으면 짠다
    4. 예약글 내보내기 → 새 댓글 답글 만들기 → 버려진 댓글 줍기 → 답글 내보내기
    5. 채널관리가 1시간 넘게 안 돌았으면 돌린다 (칭찬·감사·사과, AI 안 씀)
    6. 잠금 풀기

누가 도나 (사장님 지시 2026-09-25: "PC 켜져 있을 때는 PC, 꺼지면 클라우드 20분 텀")
    PC          작업 스케줄러 5분마다. 바퀴마다 심장박동을 찍는다
    깃허브 액션  Cloudflare 워커(워커/)가 20분마다 깨운다 (1번). 깃허브 자체 cron 은 2번(몇 시간씩 늦는다)
                심장박동이 20분 넘게 없을 때만 대신 돈다. 같은 R2 창고를 보니 중복이 안 난다

못 박은 것
- 한 단계가 터져도 다음 단계는 돈다. 터지면 스케줄러가 조용히 멈춰서 며칠 뒤에나 안다
- 오류는 텔레그램으로 알린다. **조용한 오류가 제일 무섭다** (사장님)
- 돌 때마다 창고 `자동기록.txt` 에 한 줄 남긴다 (뒤 400줄). `--상태` 로 본다
- 글 간격·턴 규칙·품앗이 거르기는 각자 파일이 이미 막고 있다. 여기서 또 안 막는다

표준 라이브러리만 쓴다. 팔자오빠 것을 하나도 부르지 않는다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

바퀴일감 = "타로봇_바퀴"      # 5분마다
옛일감들 = ("타로봇_아침", "타로봇_채널관리")     # 바퀴에 합쳤다. --붙이기 가 지운다
바퀴분 = 5
대타조용분 = int(os.environ.get("HEARTBEAT_MAX_MIN", "20"))   # PC 가 이만큼 조용하면 깃허브가 나선다
잠금죽은분 = 30               # 한 바퀴가 이보다 오래 걸리면 죽은 잠금으로 보고 뺏는다
아침시 = 4                    # 이 시각 지나서 오늘 하루치가 없으면 짠다
채널관리분 = 60               # 채널관리는 이 간격으로

_창고 = None
_어디 = "PC"


def 적기(말):
    줄 = "%s  %s  %s" % (dt.datetime.now().strftime("%m-%d %H:%M"), _어디, 말)
    print(줄)
    try:
        if _창고 is not None:
            _창고.붙이기("자동기록.txt", 줄)
    except Exception as e:
        print("  (기록 못 남김: %s)" % type(e).__name__)


def 알리기(말):
    try:
        import 알림
        알림.보내기(말)
    except Exception:
        pass


def 해보기(이름, 함수):
    """터져도 다음으로 넘어간다. 대신 **알린다.**"""
    try:
        함수()
    except SystemExit as e:
        if e.code:
            적기("%s → 멈춤(%s)" % (이름, e.code))
            알리기("%s 가 멈췄어: %s" % (이름, str(e.code)[:150]))
    except Exception as e:
        적기("%s → 오류 %s: %s" % (이름, type(e).__name__, str(e)[:120]))
        알리기("%s 에서 오류 %s: %s" % (이름, type(e).__name__, str(e)[:150]))


# ── 단계들 ─────────────────────────────────────────────────────────────
def 하루치챙기기():
    """오늘치가 없고 아침 시각이 지났으면 짠다. 있으면 아무것도 안 한다."""
    import 하루치
    지금 = dt.datetime.now()
    if 지금.hour < 아침시:
        return
    d = 하루치._읽기()
    if d.get("날") == 지금.strftime("%Y-%m-%d"):
        return
    적기("오늘 하루치가 없다. 짠다")
    하루치.짜기(다시=True)


def 토큰챙기기():
    """스레드 토큰을 스스로 늘린다 (만료 20일 전부터 하루 한 번). 실패하면 알린다."""
    import 서아토큰
    됨, 말 = 서아토큰.갱신()
    if not 됨:
        적기("토큰 갱신 → " + 말)
        알리기("스레드 토큰 갱신이 안 됐어: %s. python 서아토큰.py --넣기 로 새로 받아야 할 수도" % 말)
    elif "새로 받았다" in 말:
        적기("토큰 갱신 → " + 말)
        알리기("스레드 토큰을 새로 받았어. " + 말)


def 채널관리챙기기():
    마지막 = _창고.상태("채널관리마지막")
    if 마지막:
        try:
            if (dt.datetime.now() - dt.datetime.fromisoformat(마지막)).total_seconds() < 채널관리분 * 60:
                return
        except Exception:
            pass
    import 채널관리 as 관리
    관리.돌기(진짜=True)
    _창고.상태쓰기("채널관리마지막", dt.datetime.now().isoformat(timespec="minutes"))
    적기("채널관리 돎")


def 바퀴(대타=False):
    global _창고, _어디
    _어디 = "깃허브" if 대타 else "PC"
    import 창고
    try:
        _창고 = 창고.열기()
        _창고.캐시비우기()
    except Exception as e:
        print("R2 창고에 못 닿는다: %s: %s" % (type(e).__name__, str(e)[:150]))
        알리기("R2 창고에 못 닿아서 이번 바퀴를 건너뛰었어 (%s): %s" % (_어디, str(e)[:120]))
        return 1

    if 대타:
        조용 = _창고.심장박동_지난분()
        if 조용 < 대타조용분:
            print("PC 가 %.0f분 전에 살아 있었다 → 깃허브는 물러난다" % 조용)
            return 0
        적기("PC 심장박동 %s → 대신 돈다" % ("없음" if 조용 > 10 ** 5 else "%.0f분 전" % 조용))

    잡았나, 누구 = _창고.잠금_잡기(_어디, 죽은분=잠금죽은분)
    if not 잡았나:
        print("이미 %s 가 %s 부터 돌고 있다 → 물러난다" % ((누구 or {}).get("누구"), (누구 or {}).get("시작")))
        return 0
    try:
        if not 대타:
            _창고.심장박동_찍기("PC")
        import 하루치
        import 발행
        import 줍기
        해보기("하루치 짜기", 하루치챙기기)
        해보기("예약글 내보내기", lambda: 하루치.내보내기(진짜=True))
        해보기("댓글 답글 만들기", lambda: 발행.답글만들기(진짜=True))
        해보기("버려진 댓글 줍기", lambda: 줍기.줍기(진짜=True))
        해보기("답글 내보내기", lambda: 발행.내보내기(진짜=True))
        해보기("채널관리", 채널관리챙기기)
        해보기("토큰 갱신", 토큰챙기기)
        적기("바퀴 한 번 돎")
    finally:
        _창고.잠금_풀기()
    return 0


def 심장박동():
    """깃허브 워크플로가 먼저 본다. 숫자 하나만 찍는다 (분). 못 닿으면 -1."""
    try:
        import 창고
        m = 창고.열기().심장박동_지난분()
        print("%d" % min(m, 10 ** 6))
        return 0
    except Exception as e:
        print("-1")
        print("R2: %s" % type(e).__name__, file=sys.stderr)
        return 0


# ── 스케줄러에 붙이기 ──────────────────────────────────────────────────
def _명령(무엇):
    파이썬 = sys.executable.replace("python.exe", "pythonw.exe")
    if not Path(파이썬).exists():
        파이썬 = sys.executable
    return '"%s" "%s" %s' % (파이썬, HERE / "자동.py", 무엇)


def 붙이기():
    for 이름 in 옛일감들:
        subprocess.run(["schtasks", "/Delete", "/TN", 이름, "/F"], capture_output=True)
    r = subprocess.run(["schtasks", "/Create", "/TN", 바퀴일감, "/TR", _명령("--바퀴"),
                        "/SC", "MINUTE", "/MO", str(바퀴분), "/F"], capture_output=True, text=True)
    print("%-14s %s" % (바퀴일감, "등록됨" if r.returncode == 0
                        else "실패: " + (r.stdout or r.stderr).strip()[:120]))
    print("\n%d분마다 한 바퀴 (하루치·답글·줍기·채널관리 전부 이 안에서)" % 바퀴분)
    print("PC 가 꺼지면 깃허브 대타가 20분마다 대신 돈다 (심장박동 %d분 기준)" % 대타조용분)
    return 0 if r.returncode == 0 else 1


def 떼기():
    for 이름 in (바퀴일감,) + 옛일감들:
        r = subprocess.run(["schtasks", "/Delete", "/TN", 이름, "/F"], capture_output=True, text=True)
        print("%-14s %s" % (이름, "지움" if r.returncode == 0 else "없음"))
    return 0


def 상태():
    for 이름 in (바퀴일감,) + 옛일감들:
        r = subprocess.run(["schtasks", "/Query", "/TN", 이름, "/FO", "LIST"],
                           capture_output=True, text=True, encoding="cp949", errors="replace")
        if r.returncode != 0:
            print("%-14s 등록 안 됨" % 이름)
            continue
        줄들 = [x.strip() for x in (r.stdout or "").splitlines() if x.strip()]
        쓸것 = [x for x in 줄들 if any(k in x for k in ("상태", "다음 실행", "마지막 실행", "Status", "Next Run", "Last Run"))]
        print("%-14s %s" % (이름, " | ".join(쓸것[:3])))
    try:
        import 창고
        c = 창고.열기()
        hb = c.심장박동_지난분()
        print("\nPC 심장박동: %s" % ("없음" if hb > 10 ** 5 else "%.0f분 전" % hb))
        print("잠금: %s" % (c.읽기("잠금.json") or "없음"))
        끝 = (c.글읽기("자동기록.txt", "") or "").strip().splitlines()[-8:]
        print("\n최근 기록 (창고)")
        for x in 끝:
            print("  " + x)
    except Exception as e:
        print("\nR2 창고에 못 닿는다: %s" % type(e).__name__)
    return 0


def main():
    ap = argparse.ArgumentParser(description="스케줄러가 부르는 자리")
    ap.add_argument("--바퀴", action="store_true")
    ap.add_argument("--대타", action="store_true", help="깃허브. PC 심장박동이 없을 때만 돈다")
    ap.add_argument("--심장박동", action="store_true", help="PC 가 몇 분 전에 살아 있었나")
    ap.add_argument("--붙이기", action="store_true")
    ap.add_argument("--떼기", action="store_true")
    ap.add_argument("--상태", action="store_true")
    a = ap.parse_args()

    if a.바퀴:
        return 바퀴(대타=a.대타)
    if a.심장박동:
        return 심장박동()
    if a.붙이기:
        return 붙이기()
    if a.떼기:
        return 떼기()
    if a.상태:
        return 상태()
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
