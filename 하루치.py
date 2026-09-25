# -*- coding: utf-8 -*-
"""하루치 글을 **새벽 4시에 한 번** 만들어 예약표에 넣는다 (2026-09-24 사장님 지시).

    스레드에는 예약 발행이 없다. 그래서 만들어만 두고, 시각이 되면 우리가 신호를 줘서 내보낸다.

    python 하루치.py --짜기              오늘치를 짜서 예약표에 넣는다 (타로 3개만 만든다)
    python 하루치.py --본다              오늘 예약표
    python 하루치.py --내보내기           시각 지난 것을 내보낸다 (시늉)
    python 하루치.py --내보내기 --진짜    진짜 올린다
    python 하루치.py --일상 3 "글 내용"   일상 자리에 사장님이 쓴 글을 넣는다

하루 구성 (2026-09-24 사장님 확정: 내일부터 **타로만 4개**)
    08:00 쯤   타로   한장
    12:30 쯤   타로   한장
    17:00 쯤   타로   한장
    21:30 쯤   타로   무료 리딩 (하루 한 번만. 매번 하면 구걸로 보인다)

    일상글은 사진이랑 같이 나가야 해서 하루치에서 뺐다.
    올릴 때는 python 발행.py --올리기 일상 --진짜

못 박은 것
- 분은 랜덤으로 흔든다. 매일 같은 시각에 나가면 봇 티가 난다
- 타로 글 3개는 **카드가 서로 달라야 한다.** 씨앗을 갈라서 뽑는다
- 글틀도 서로 겹치지 않게 고른다
- 자정을 넘기는 자리는 버린다

표준 라이브러리만 쓴다. 팔자오빠 것을 하나도 부르지 않는다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import random
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import 발행기록
import 그림올리기
import 풀이
import 창고
import 알림

예약표 = "하루치.json"           # R2 창고 seoa/ 아래 (2026-09-25)

# 글 간격 (2026-09-24 사장님 지시)
#   **최소 3시간. 보통 4~5시간.** 짧게 몰아 올리면 노출이 깎이고 봇 티가 난다
최소간격분 = 3 * 60
노리는간격분 = (4 * 60, 5 * 60)

# (시각, 분흔들기, 종류, 글감)  종류: 타로 / 일상
# 2026-09-24 사장님 지시: **내일부터 타로만 4개.** 일상 자리는 뺐다.
# 4개면 4시간 반씩 띄울 수 있어서 간격이 넉넉하다
# 2026-09-24: **무료 리딩을 하루 2개로 늘렸다.**
# 댓글이 붙는 건 무료 리딩뿐이고, 카드 한장 글은 조회만 나오고 답글이 안 붙는다
# (팔자오빠 성적표: "나 오늘 양띠 하나만 짚고 갈게" 조회 19). 터지는 걸 하나만 던질 이유가 없다
# 2026-09-25 스레드 실측(데이터/스레드타로계정조사.md 8부)으로 한장 글을 뺐다.
#   한장 글은 조회 200 에 좋아요 1, 답글 0 이었다. 댓글이 붙는 건 무료 리딩 · 번호 골라(픽어카드),
#   리포스트가 붙는 건 사람 행동 목록(노하우) 글이다.
자리들 = [
    ("08:00", 20, "타로", "번호"),       # 출근길. 번호만 적으면 되니 가볍다 (실측: 답글 226·105)
    ("12:30", 20, "타로", "무료"),       # 점심. 사람 많은 시간
    ("17:00", 20, "타로", "노하우"),     # 퇴근 무렵. 리포스트용
    ("21:30", 20, "타로", "무료"),       # 밤이 댓글 제일 많이 붙는다
]

# 2026-09-24 하루는 이미 옛 시간표(일상 2 + 타로 3)로 잡아 둔 날이라 그대로 둔다.
# 이 날짜를 넘어가면 위의 타로 4개짜리로 간다
바뀌는날 = "2026-09-25"
옛자리들 = [
    ("07:30", 20, "일상", None),
    ("11:40", 20, "타로", "한장"),
    ("16:00", 20, "일상", None),
    ("20:10", 20, "타로", "무료"),
    ("23:30", 15, "타로", "한장"),
]


# 2026-09-26 사장님: **2026-09-27 부터 이 네 창 안에서 시각 완전 랜덤.** 이 밖엔 글이 안 나간다.
#   종류는 그대로 (번호 · 무료 · 노하우 · 무료). 기준 자리에 "시작-끝" 을 적으면 그 창 안에서 고른다
창자리들 = [
    ("06:17-07:27", None, "타로", "번호"),
    ("14:13-15:11", None, "타로", "무료"),
    ("18:33-18:46", None, "타로", "노하우"),
    ("23:00-23:30", None, "타로", "무료"),
]
창바뀌는날 = "2026-09-27"


def 오늘자리들(날):
    if 날 >= 창바뀌는날:
        return 창자리들
    return 자리들 if 날 >= 바뀌는날 else 옛자리들

# 일상글을 올리고 싶을 때는 하루치에 안 넣고 따로 올린다 (사진이랑 같이 나가야 해서).
#     python 발행.py --올리기 일상 --진짜
# 간격은 발행기록.py 가 알아서 막는다


def 지금():
    return dt.datetime.now()


def 오늘():
    return 지금().strftime("%Y-%m-%d")


def _읽기():
    return 창고.열기().읽기(예약표, {}) or {}


def _쓰기(d):
    창고.열기().쓰기(예약표, d)


def 시각짜기(기준, 흔들기, 날, 앞엣것=None):
    """분을 흔들되 **앞 글과 최소 간격은 반드시 지킨다.**

    흔들기만 하면 우연히 두 글이 붙어 나갈 수 있다. 그건 노출이 깎인다.
    """
    if "-" in 기준:
        # "06:17-07:27" 창 안에서 완전 랜덤 (2026-09-26)
        시작, 끝 = [int(a) * 60 + int(b) for a, b in (x.split(":") for x in 기준.split("-"))]
        시, 분 = 0, random.randint(시작, 끝)
    else:
        시, 분 = [int(x) for x in 기준.split(":")]
        분 += random.randint(-흔들기, 흔들기)
    때 = dt.datetime.strptime(날, "%Y-%m-%d") + dt.timedelta(hours=시, minutes=분)
    if 앞엣것 is not None:
        빠른한계 = 앞엣것 + dt.timedelta(minutes=최소간격분)
        if 때 < 빠른한계:
            때 = 빠른한계
    return 때


def 짜기(날=None, 다시=False):
    날 = 날 or 오늘()
    d = _읽기()
    if d.get("날") == 날 and not 다시:
        print("오늘치는 이미 짜여 있다 (%d칸). 다시 짜려면 --다시" % len(d.get("자리", [])))
        return 0

    쓸자리 = 오늘자리들(날)
    타로수 = sum(1 for x in 쓸자리 if x[2] == "타로")
    print("%s 하루치를 짠다. 타로 %d개 (칸 %d개)\n" % (날, 타로수, len(쓸자리)))
    짜인것 = []
    쓴틀 = set()
    쓴카드 = set()
    타로번호 = 0

    앞때 = None
    for 기준, 흔들기, 종류, 글감 in 쓸자리:
        때 = 시각짜기(기준, 흔들기, 날, 앞때)
        if 때.strftime('%Y-%m-%d') != 날:
            print('  (자정을 넘어서 이 자리는 버린다)')
            continue
        앞때 = 때
        칸 = {"때": 때.isoformat(timespec="minutes"), "종류": 종류,
              "글감": 글감, "상태": "빈칸" if 종류 == "일상" else "대기"}

        if 종류 == "일상":
            칸["글"] = ""
            칸["메모"] = "사장님이 직접 쓴다. python 하루치.py --일상 <번호> \"글\""
            짜인것.append(칸)
            print("  %s  일상   (빈칸 — 사장님)" % 때.strftime("%H:%M"))
            continue

        # 타로 — 카드와 틀이 앞엣것과 안 겹치게 몇 번 다시 뽑는다
        타로번호 += 1
        글, ok, 문제, fact = "", False, [], {}
        for _ in range(4):
            씨앗 = "eslyn_yes" if 타로번호 == 1 else "eslyn_yes#%d" % 타로번호
            글, ok, 문제, _n, fact = 풀이.글쓰기(씨앗, 글감, day=날)
            if ok and fact.get("카드") not in 쓴카드 and fact.get("축") not in 쓴틀:
                break
            타로번호 += 10       # 씨앗을 확 흔들어 다시
        칸.update({"글": 글, "카드": fact.get("카드", ""), "방향": fact.get("방향", ""),
                   "틀": fact.get("축", ""), "슬러그": fact.get("슬러그", "")})
        if not ok:
            칸["상태"] = "실패"
            칸["까닭"] = " / ".join(문제)
            print("  %s  타로   실패: %s" % (때.strftime("%H:%M"), " / ".join(문제[:2])))
            짜인것.append(칸)
            continue
        쓴카드.add(fact.get("카드"))
        쓴틀.add(fact.get("축"))
        if 글감 == "번호":
            칸["그림주소"] = 그림올리기.번호그림주소()      # 뒷면 넉 장 + 숫자
        elif fact.get("슬러그"):
            칸["그림주소"] = 그림올리기.앞면주소(fact["슬러그"], fact.get("방향", "정방향"))
        짜인것.append(칸)
        print("  %s  타로   %s %s [%s]" % (때.strftime("%H:%M"), fact.get("카드"),
                                           fact.get("방향"), fact.get("축") or 글감))
        for line in 글.splitlines():
            print("           | %s" % line)

    _쓰기({"날": 날, "짠때": 지금().isoformat(timespec="minutes"), "자리": 짜인것})
    print("\n예약표에 넣었다: 창고 %s" % 예약표)
    실패한것 = [x for x in 짜인것 if x.get("상태") == "실패"]
    if 실패한것:
        # 조용히 넘어가면 그날 글이 안 나가고 며칠 뒤에나 안다
        알림.보내기("하루치 %d칸이 실패했어 (%s). 오늘 글이 그만큼 안 나가\n%s" % (
            len(실패한것), 날, "\n".join((x.get("까닭") or "")[:60] for x in 실패한것[:3])))
    print("시각 되면: python 하루치.py --내보내기 --진짜")
    return 0


def 본다():
    d = _읽기()
    if not d:
        print("예약표가 없다. python 하루치.py --짜기")
        return 1
    print("%s (짠 때 %s)\n" % (d.get("날"), d.get("짠때")))
    for i, 칸 in enumerate(d.get("자리", []), 1):
        때 = dt.datetime.fromisoformat(칸["때"]).strftime("%H:%M")
        print("[%d] %s  %-4s %-6s %s %s" % (i, 때, 칸["종류"], 칸["상태"],
                                            칸.get("카드", ""), 칸.get("방향", "")))
        for line in (칸.get("글") or "(비어 있음)").splitlines():
            print("      | %s" % line)
        print()
    return 0


def 일상넣기(번호, 글, 그림주소=None):
    """일상 자리에 글을 넣는다. **사진 주소도 같이 넣을 수 있다.**

    일상글은 서아 사진과 같이 올린다. 그래서 4시 자동화에서 빼놨다 (사장님 지시 2026-09-24).
    사진은 인터넷 주소여야 한다. 메타가 그 주소로 가지러 온다.
    """
    d = _읽기()
    자리 = d.get("자리", [])
    if not 1 <= 번호 <= len(자리):
        print("%d번 자리가 없다" % 번호)
        return 1
    칸 = 자리[번호 - 1]
    if 칸["종류"] != "일상":
        print("%d번은 일상 자리가 아니다 (%s)" % (번호, 칸["종류"]))
        return 1
    칸["글"] = 글.strip()
    if 그림주소:
        칸["그림주소"] = 그림주소
    칸["상태"] = "대기"
    _쓰기(d)
    print("넣었다. %s 에 나간다%s" % (dt.datetime.fromisoformat(칸["때"]).strftime("%H:%M"),
                                     " (사진 같이)" if 그림주소 else " (글만)"))
    return 0


def 내보내기(진짜=False):
    import 발행
    d = _읽기()
    자리 = d.get("자리", [])
    if not 자리:
        print("예약표가 없다")
        return 1
    나간것 = 0
    for i, 칸 in enumerate(자리, 1):
        if 칸.get("상태") != "대기":
            continue
        때 = dt.datetime.fromisoformat(칸["때"])
        if 때 > 지금():
            print("[%d] %s 아직 (%s)" % (i, 때.strftime("%H:%M"), 칸["종류"]))
            continue
        if not (칸.get("글") or "").strip():
            print("[%d] %s 글이 비었다. 건너뜀" % (i, 때.strftime("%H:%M")))
            continue
        print("\n[%d] %s %s" % (i, 때.strftime("%H:%M"), 칸["종류"]))
        for line in 칸["글"].splitlines():
            print("   | %s" % line)
        if not 진짜:
            print("   (시늉. 안 나갔다)")
            continue
        try:
            아이디 = 발행.스레드에올리기(칸["글"], 칸.get("그림주소"))
        except 발행.스레드거절 as e:
            # **한 칸이 거절돼도 다음 칸은 간다** (2026-09-25). 전에는 여기서 멈춰 그날 뒤 글이 다 막혔다.
            # 토큰·권한·한도 문제는 칸 탓이 아니라 예전처럼 멈추고 알린다(자동.py 해보기)
            if 발행.전체문제냐(e):
                raise
            칸["발행실패"] = int(칸.get("발행실패") or 0) + 1
            이유 = e.원문[:150]
            if 칸["발행실패"] >= 발행.발행포기횟수:
                칸["상태"] = "못나감"
                칸["까닭"] = "스레드가 %d번 거절: %s" % (칸["발행실패"], 이유)
                알림.보내기("%s 예약글을 스레드가 %d번 거절해서 멈춰 뒀어. 직접 봐줘\n이유: %s\n\n%s"
                            % (때.strftime("%H:%M"), 칸["발행실패"], 이유, 칸["글"][:200]))
            else:
                칸["때"] = (지금() + dt.timedelta(minutes=발행.다시해볼분)).isoformat(timespec="minutes")
                if 칸["발행실패"] == 1:
                    알림.보내기("%s 예약글을 스레드가 거절했어 (%s). %d분 뒤 다시 해볼게"
                                % (때.strftime("%H:%M"), 이유, 발행.다시해볼분))
            _쓰기(d)
            print("   → 거절 %d번째: %s" % (칸["발행실패"], 이유))
            continue
        칸["상태"] = "나감"
        칸["나간아이디"] = 아이디
        _쓰기(d)             # **올리자마자 적는다.** 뒤에서 터져도 같은 글이 또 안 나간다
        발행기록.기록하기(칸.get("글감") or 칸["종류"], 글=칸["글"],
                          카드=칸.get("카드", ""), 소재=칸.get("틀", ""))
        나간것 += 1
        print("   → 나갔다 (%s)" % 아이디)
    if 진짜:
        print("\n%d개 내보냈다" % 나간것)
    return 0


def main():
    ap = argparse.ArgumentParser(description="하루치 짜기와 내보내기")
    ap.add_argument("--짜기", action="store_true")
    ap.add_argument("--다시", action="store_true", help="이미 짜여 있어도 다시 짠다")
    ap.add_argument("--날", metavar="YYYY-MM-DD")
    ap.add_argument("--본다", action="store_true")
    ap.add_argument("--내보내기", action="store_true")
    ap.add_argument("--진짜", action="store_true")
    ap.add_argument("--일상", nargs=2, metavar=("번호", "글"), help="일상 자리에 사장님 글 넣기")
    ap.add_argument("--사진", metavar="주소", help="--일상 과 같이. 사진 주소를 붙인다")
    a = ap.parse_args()

    if a.짜기:
        return 짜기(a.날, 다시=a.다시)
    if a.본다:
        return 본다()
    if a.일상:
        return 일상넣기(int(a.일상[0]), a.일상[1], a.사진)
    if a.내보내기:
        return 내보내기(진짜=a.진짜)
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
