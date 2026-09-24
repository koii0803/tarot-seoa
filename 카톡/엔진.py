# -*- coding: utf-8 -*-
"""타로 엔진 (2026-09-23). 팔자오빠와 완전 분리 — 그쪽 파일을 하나도 import 하지 않는다.

무엇을 하는 기계인가
    사주 봇에서 만세력 엔진이 하던 자리를 대신한다.
    만세력 엔진 : 생년월일  → 일간·오행·세운    (지어낼 수 없는 숫자)
    타로 엔진   : 사람+날짜 → 카드·상징·되물음  (지어낼 수 없는 재료)

    핵심은 "심리 기술을 LLM 에게 시키지 않는다" 이다.
    LLM 은 이 파일이 내준 재료 밖으로 나갈 수 없다. digest() 가 내주고 check_output() 이 막는다.

쓰는 법
    python 타로엔진.py --draw 홍길동            그 사람 오늘 카드
    python 타로엔진.py --test "요즘 일이 안 풀려요"   댓글 하나로 재료 전체를 뽑아 본다
    python 타로엔진.py --selftest              자가진단

밖에서 쓸 때
    from 타로엔진 import draw, digest, check_output, heavy_check

절대 규칙
    - 표준 라이브러리만 쓴다. 설치할 것 없다.
    - SALT 를 바꾸면 모든 사람의 카드가 바뀐다. 한번 쓰기 시작하면 건드리지 않는다.
    - 여기 없는 말은 풀이에 못 쓴다. (사주 봇의 facts_digest 와 같은 역할)
"""
from __future__ import annotations

import io
import re
import sys
import json
import hashlib
import argparse
import datetime as dt
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
DATA = HERE / "데이터"

# 카드 고정에 쓰는 소금. 바꾸면 모두의 카드가 바뀐다.
SALT = "paljaoppa-tarot-2026"

# 그림이 있는 곳. 파일 이름은 데이터/카드22.json 의 img 에 같이 들어 있다.
# 텍스트와 그림을 따로 찾지 않게 한 군데로 모아 뒀다 (2026-09-23 사장님 지시).
IMG_DIR = (HERE.parent / "카드이미지" / "타로22장")
BACK_IMG = (HERE.parent / "카드이미지" / "타로-카드뒷면.webp")

# ──────────────────────────────────────────────────────────────
# 1. 재료 불러오기
# ──────────────────────────────────────────────────────────────

def _load(name):
    with io.open(DATA / name, encoding="utf-8") as f:
        return json.load(f)


CARDS = _load("카드22.json")                       # 22장. 사이트 tarot-pages.ts 에서 뽑아 복사해 둔 것
OPEN_Q = _load("열린질문.json")                     # 유형 x 시제 x 3벌
OPEN_Q_BAN = _load("열린질문_반말.json")             # 같은 칸의 반말 벌 (스레드용)
CARD_Q = _load("카드별질문.json")                   # 카드 고유. 비어 있으면 위로 내려간다

# 말투. 스레드는 반말, 사이트는 존댓말. 2026-09-23 사장님 지시로 반말에 "약간의 여성미"를 넣었다.
TONES = ("반말", "존대")
OPEN_Q_BY_TONE = {"존대": OPEN_Q, "반말": OPEN_Q_BAN}

BY_SLUG = {c["slug"]: c for c in CARDS}
BY_ID = {c["id"]: c for c in CARDS}

# 2026-09-23 스레드 실측으로 재회·시험을 더했다 (데이터/스레드질문샘플.md)
# "합격"은 금지어라 유형 이름을 "시험"으로 둔다
ASK_TYPES = ("연애", "재회", "일", "시험", "돈", "관계", "불안", "결정")
TENSES = ("지난것", "지금", "앞일")
DIRECTIONS = ("정방향", "역방향")

# ──────────────────────────────────────────────────────────────
# 2. 금지어 (사주 봇 목록을 복사해 왔다. import 아니다)
#    타로용으로 뺀 것: "죽을"(죽음 카드 이름과 충돌), "우울"·"공황"(입력 감지에만 쓴다)
#    타로용으로 더한 것: 맞힘을 뜻하는 말
# ──────────────────────────────────────────────────────────────
BANNED = [
    "소름", "자빠질", "터진다", "터져", "100%", "반드시", "무조건", "확실", "틀림없", "족집게", "적중", "보장",
    "정확", "복권", "로또", "행운의 숫자", "당첨", "투자", "주식", "가상화폐", "암호화폐", "비트코인", "부동산",
    "합격", "수술", "수명", "임신", "유산", "불임", "심장", "신장", "혈압", "혈당", "부적", "굿", "액운", "액막이",
    "저주", "운명을 바꾼", "마지막 기회", "오늘만", "놓치면", "검증", "1위", "유일", "최고", "전문가",
    "직접 감정", "상담", "—",
    # 타로에서 특히 위험한 것 (맞힌다는 말)
    "맞았", "맞힙", "맞힌", "예언", "점지", "운명입니다", "정해져",
]

# 미래를 단정하는 말꼬리. 타로는 이쪽으로 흐르기 쉬워 따로 막는다.
FUTURE_PAT = re.compile(
    r"(할 겁니다|될 겁니다|올 겁니다|옵니다\.|하게 됩니다|생깁니다|이뤄집니다|끝납니다|만나게 됩니다)"
)

# 무거운 신호. 잡히면 봇이 답하지 않고 사람에게 넘긴다. (출력 금지어와 별개다)
HEAVY_PAT = re.compile(
    r"(죽고\s*싶|죽어\s*버리|자살|자해|목\s*매|뛰어내리|살기\s*싫|사라지고\s*싶|없어지고\s*싶|"
    r"우울증|공황장애|정신과|극단적\s*선택)"
)

# 나이. 하나라도 걸리면 그 자리에서 멈춘다 (2026-09-23 사장님 지시)
AGE_PAT = re.compile(
    r"(?:만\s*)?\d{1,2}\s*(?:살|세)(?![기대])"                      # 17살 · 만 14세
    r"|(?:한|두|세|네|다섯|여섯|일곱|여덟|아홉|열|스무)\s*살"          # 열 살 · 스무 살
    r"|\d{2,4}\s*년\s*생(?![활계])"                                 # 2010년생 · 05년생
    r"|\d{4}\s*년\s*\d{1,2}\s*월\s*생"
    r"|몇\s*살|나이"
    r"|스물|서른|마흔|쉰|예순"
    r"|초등학|중학생|고등학생|초딩|중딩|고딩"
    r"|[중고][1-3](?![0-9])|초[1-6](?![0-9])"
    r"|[1-6]\s*학년"
)

# 나이가 나왔을 때 내보낼 단 한 줄. 이 줄만 나가고 그 사람에게는 더 답하지 않는다.
STOP_LINE = "나이가 적힌 글에는 답을 드리지 않습니다. 여기서 멈추겠습니다."

# 되비추기 단어에서 걸러낼 흔한 말
STOP = set("""
그냥 진짜 너무 정말 조금 많이 요즘 오늘 내일 어제 지금 이제 저는 제가 근데 그래서 하지만 그리고
사람 생각 마음 기분 상황 부분 정도 이야기 얘기 때문 자꾸 계속 아직 혹시 제발 한번 다시 이런 그런
""".split())


# ──────────────────────────────────────────────────────────────
# 3. 카드 뽑기 — 사람 + 날짜로 고정. 조작 불가, 같은 날 같은 카드
# ──────────────────────────────────────────────────────────────

def today_str():
    """서울 기준 오늘. (UTC+9 를 직접 더한다. 설치할 것 없이 돌게)"""
    return (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=9)).strftime("%Y-%m-%d")


def _seed(who, day):
    raw = "%s|%s|%s" % (SALT, str(who).strip(), day)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def draw(who, day=None):
    """그 사람의 그날 카드. 몇 번을 불러도 같은 값이 나온다."""
    day = day or today_str()
    h = _seed(who, day)
    card = BY_ID[int(h[0:8], 16) % 22]
    direction = DIRECTIONS[int(h[8:12], 16) % 2]
    return {"카드": card, "방향": direction, "날짜": day, "seed": h}


def pick_symbol(card, h):
    """그 카드의 상징 하나를 고정해 고른다. 매번 같은 것이 나온다."""
    pts = card.get("symbolPoints") or []
    if not pts:
        return None
    return pts[int(h[12:16], 16) % len(pts)]


def pick_question(card_slug, ask_type, tense, h, tone="반말"):
    """열린 질문 하나. 카드 고유가 있으면 그걸 먼저 쓰고, 없으면 유형x시제로 내려간다."""
    pool = None
    src = "유형"
    # 카드별질문.json 은 **반말로만** 채워져 있다 (2026-09-24, 스레드용 704줄).
    # 존댓말(사이트)에 이걸 쓰면 반말이 그대로 나간다. 그래서 반말일 때만 본다
    c = CARD_Q.get(card_slug) if tone == "반말" else None
    if isinstance(c, dict):
        v = c.get(ask_type)
        if isinstance(v, dict):
            v = v.get(tense)
        if isinstance(v, list) and v:
            pool, src = v, "카드"
    if pool is None:
        pool = OPEN_Q_BY_TONE[tone][ask_type][tense]
    return pool[int(h[16:20], 16) % len(pool)], src


# ──────────────────────────────────────────────────────────────
# 4. 되비추기 — 손님이 쓴 말만 돌려준다
# ──────────────────────────────────────────────────────────────

# 조사 — **긴 것부터** 써야 한다 (2026-09-24 고침).
#   전에는 `이랑` 이 빠져 있고 `랑` 만 있었다. 그래서 "남친이랑" 에서 `랑` 만 떨어지고
#   **"남친이" 가 남았다.** 그게 "남친이 헤어졌는데 하는 마음에" 로 깨진 진짜 범인이다.
조사 = ("이랑", "에게서", "한테서", "에서", "으로", "하고", "부터", "까지",
        "한테", "에게", "이나", "보다", "처럼", "이라", "라고", "께서",
        "은", "는", "이", "가", "을", "를", "에", "로", "랑", "과", "와",
        "도", "만", "의", "나", "께")
조사떼기 = re.compile("(" + "|".join(조사) + ")$")

# 용언 어절 신호. 이게 걸리면 **명사가 아니다** → 명사 자리에 꽂으면 문장이 깨진다.
#   "헤어졌는데" 는 조사 목록에 안 걸려 통째로 살아남아서 명사인 척 꽂혔다.
용언끝 = re.compile(
    r"(다|까|네|지만|는데|은데|ㄴ데|았|었|겠|잖아|거든|니까|더라|"
    r"려고|아서|어서|든지|세요|해요|어요|아요|구나|더니|면서|는지|을지|"
    r"라서|기는|해도|해서|한데|인데|길래|든가)$")

# 절(節)이 끝나는 어미. 여기까지는 **안 자르고 통째로** 가져온다.
#   `-까` 는 뺐다. 그걸 넣으면 "지금 직장 그만두는게 나을까" 처럼 **질문 전체**가 잡혀서
#   되비춤이 아니라 앵무새가 된다. 중간에서 끊기는 어미만 본다.
절끝 = re.compile(r"(는데|은데|거든|잖아|니까|아서|어서|더라|길래|는지|려고|면서)$")


def mirror_words(text, limit=3):
    """댓글에서 손님이 실제로 쓴 낱말을 뽑는다. LLM 없이도 돌아간다."""
    words = re.findall(r"[가-힣]{2,}", text or "")
    out = []
    for w in words:
        w = 조사떼기.sub("", w)
        if len(w) < 2 or w in STOP or w in out:
            continue
        out.append(w)
        if len(out) >= limit:
            break
    return out


# 확실한 명사만 모은 사전 (2026-09-24 신설).
#   정규식으로 한국어 품사를 가르는 건 안 된다. "사귄" "단절된" "다니기" "모여" 가 다 샜다.
#   그래서 **추측을 버리고 사전으로 간다.** 분류.py 유형낱말에서 명사만 옮겨 왔다
#   (거기 쓰이는 말이라 손님이 실제로 쓰는 말이고, 전부 확실한 명사다).
#   사전에 없으면 명사되비춤을 아예 안 만든다 — 틀린 걸 꽂느니 안 꽂는 게 낫다.
명사사전 = (
    "남친", "여친", "전남친", "전여친", "남자친구", "여자친구", "썸남", "썸녀",
    "남편", "아내", "애인", "그사람", "이별", "재회", "재결합", "연애", "썸",
    "고백", "연락", "인연", "만남", "관계", "마음", "감정", "사이",
    "회사", "직장", "이직", "퇴사", "복직", "업무", "상사", "사업", "동료",
    "일자리", "직업", "커리어", "승진", "면접", "서류", "채용", "취업", "입사",
    "시험", "합격", "발표", "자격", "공부", "학교",
    "돈", "월급", "빚", "대출", "재물", "투자", "수입", "생활비", "카드값",
    "친구", "가족", "엄마", "아빠", "부모님", "시댁", "사람들", "인간관계",
    "건강", "이사", "독립", "결정", "선택", "계약", "여행", "집", "방",
)


def 명사낱말(text, limit=2):
    """**사전에 있는 명사만** 뽑는다 (2026-09-24 신설).

    `{되비춤} 얘기` 처럼 **명사를 기대하는 틀**에 꽂을 것.
    "헤어졌는데" 같은 걸 여기에 꽂으면 말이 안 된다.

    추측하지 않는다. 사전에 없으면 안 뽑고, 그러면 조립이 절(節) 틀로 간다.
    """
    t = text or ""
    out = []
    # 긴 것부터 본다. 안 그러면 "썸남" 과 "썸" 이 같이 잡힌다
    for n in sorted(명사사전, key=len, reverse=True):
        if n not in t:
            continue
        if any(n in 이미 for 이미 in out):      # 이미 고른 것 안에 들어 있으면 건너뛴다
            continue
        out.append(n)
        if len(out) >= limit:
            break
    return out


def 절뽑기(text, 최대글자=22):
    """손님 원문에서 **절 하나를 안 자르고 통째로** 가져온다 (2026-09-24 신설).

    `{되비춤} 하는 마음에` 처럼 **절을 기대하는 틀**에 꽂을 것.
    자르니까 깨지는 거라, 안 자르면 애초에 조사 문제가 안 생긴다.
    AI 답이 잘 되는 이유도 이거다 — "나만 붙잡고 있는 거 같다는 그 말이".
    """
    깨끗 = re.sub(r"[^\w\s가-힣]", " ", text or "")
    어절 = 깨끗.split()
    for i, w in enumerate(어절):
        if 절끝.search(w):
            조각 = " ".join(어절[: i + 1])
            if 2 <= len(조각) <= 최대글자:
                return 조각
    return ""


def verify_words(text, words):
    """LLM 이 뽑아 온 낱말이 원문에 진짜 있는지 본다. 없으면 버린다 = 지어내기 차단."""
    src = text or ""
    return [w for w in (words or []) if w and w in src]


def heavy_check(text):
    """무거운 신호. True 면 봇이 답하지 않는다."""
    return bool(HEAVY_PAT.search(text or ""))


def age_check(text):
    """나이가 나왔나. 2026-09-23 사장님 지시: 나이를 밝히면 그 자리에서 안 된다고 말하고 응답 중지.
    미성년만이 아니라 **나이가 나오면 전부** 멈춘다. 넓게 잡아 놓쳐서 받는 쪽보다 막는 쪽으로 기울였다."""
    m = AGE_PAT.search(text or "")
    return (True, m.group(0).strip()) if m else (False, "")


def stop_check(text):
    """멈출 일인가. (멈춤여부, 까닭, 내보낼 한 줄)
    나이 → 정해진 한 줄만 내보내고 끝. 무거운 신호 → 아무 말 없이 사람에게 넘긴다."""
    yes, found = age_check(text)
    if yes:
        return True, "나이", STOP_LINE
    if heavy_check(text):
        return True, "무거움", ""
    return False, "", ""


# ──────────────────────────────────────────────────────────────
# 5. 재료표 — 이 밖의 말은 풀이에 못 쓴다 (사주 봇의 facts_digest 자리)
# ──────────────────────────────────────────────────────────────

def digest(who, text, ask_type, tense, day=None, llm_words=None, tone="반말",
           고른카드=None, 고른방향=None):
    """LLM 에게 넘길 재료 전부. 이게 유일한 입력이다. tone 은 "반말"(스레드) 또는 "존대"(사이트).

    `고른카드` 가 오면 기계가 뽑지 않고 **손님이 뽑아 온 카드**를 쓴다 (2026-09-24 카톡).
    손님이 사이트에서 직접 뽑고 이름을 적어 보내는 길이 있어서 생긴 인자다.
    """
    if tone not in TONES:
        raise ValueError("말투가 아니다: %r (%s 중 하나)" % (tone, "·".join(TONES)))
    if ask_type not in ASK_TYPES:
        raise ValueError("질문유형이 아니다: %r (%s 중 하나)" % (ask_type, "·".join(ASK_TYPES)))
    if tense not in TENSES:
        raise ValueError("시제가 아니다: %r (%s 중 하나)" % (tense, "·".join(TENSES)))

    d = draw(who, day)
    if 고른카드 is not None:                      # 손님이 직접 뽑아 온 것
        d = dict(d, 카드=고른카드, 방향=고른방향 or d["방향"])
    card, h = d["카드"], d["seed"]
    sym = pick_symbol(card, h)
    q, qsrc = pick_question(card["slug"], ask_type, tense, h, tone)

    멈춤, 까닭, 한줄 = stop_check(text)
    heavy = (까닭 == "무거움")
    나이밝힘 = (까닭 == "나이")
    # 멈출 글이면 되비출 말을 아예 안 넘긴다. 그 낱말이 풀이에 섞이면 안 된다.
    words = [] if 멈춤 else (verify_words(text, llm_words) if llm_words else mirror_words(text))

    return {
        "중지": 멈춤,             # True 면 풀이를 쓰지 않는다
        "중지까닭": 까닭,           # "나이" 또는 "무거움"
        "중지문구": 한줄,           # 나이일 때만 내용이 있다. 이 한 줄만 내보낸다
        "나이밝힘": 나이밝힘,
        "무거움": heavy,          # True 면 아무 말 없이 사람에게 넘긴다
        "카드번호": card["id"],
        "카드": card["ko"],
        "슬러그": card["slug"],
        "로마숫자": card["roman"],
        "방향": d["방향"],
        "열쇠말": card["keywords"],
        "상징하나": (sym or {}).get("part", ""),      # 이 상징 말고 다른 그림 얘기는 못 쓴다
        "상징뜻": (sym or {}).get("means", ""),
        "상징전부": [p["part"] for p in (card.get("symbolPoints") or [])],
        "한줄": card["upright_summary"] if d["방향"] == "정방향" else card["reversed_summary"],
        "질문유형": ask_type,
        "시제": tense,
        "손님단어": words,                              # 되비추기에 쓸 말. 원문에 있는 것만 남았다
        # 되비춤 두 종류 (2026-09-24). 틀이 명사를 기대하는지 절을 기대하는지에 맞춰 골라 쓴다
        "손님명사": [] if 멈춤 else 명사낱말(text),        # 용언 어절 버린 명사만
        "손님절": "" if 멈춤 else 절뽑기(text),           # 안 자른 절 하나
        "열린질문": q,
        "질문출처": qsrc,
        "말투": tone,
        "날짜": d["날짜"],
        # 그림. 텍스트와 같이 나온다. 앞면파일/뒷면파일은 이 PC 의 실제 경로다
        "앞면": card.get("img", ""),                       # 00-바보.webp
        "앞면경로": str(IMG_DIR / card["img"]) if card.get("img") else "",
        "앞면png": str(IMG_DIR / card["imgPng"]) if card.get("imgPng") else "",
        "앞면웹": card.get("webPath", ""),                  # 사이트에 올릴 때 쓸 영문 주소
        "뒷면": BACK_IMG.name,
        "뒷면경로": str(BACK_IMG),
    }


def 그림있나(fact):
    """앞면 그림 파일이 실제로 있나. R2 에 올리기 전에 이걸로 본다."""
    p = fact.get("앞면경로") or ""
    return bool(p) and Path(p).exists()


# ──────────────────────────────────────────────────────────────
# 6. 나온 글 검사 — 재료 밖으로 나갔는지 본다
# ──────────────────────────────────────────────────────────────

def check_output(text, fact, need_question=True):
    """풀이 글을 검사한다. 빈 목록이면 통과.
    need_question=False 는 되묻지 않는 갈래("카드만")에 쓴다."""
    bad = []
    t = text or ""

    for w in BANNED:
        if w in t:
            bad.append("금지어: %s" % w)

    m = FUTURE_PAT.search(t)
    if m:
        bad.append("미래 단정: %s" % m.group(1))

    # 뽑힌 카드 이름은 먼저 지우고 본다. "여황제" 안에 "황제"가 들어 있어서 오탐이 났다
    # (2026-09-23 실제 글에서 걸림)
    t2 = t.replace(fact["카드"], " ")

    # 뽑힌 카드 말고 다른 카드 이름을 꺼냈는가
    # 달·탑·별·힘 같은 두 글자 이름은 보통 낱말과 겹친다("2달 반"의 달). 그래서 짧은 이름은
    # 뒤에 "카드"나 방향이 붙었을 때만 카드로 본다. (2026-09-23 실제 글에서 오탐이 나와 고침)
    for c in CARDS:
        if c["id"] == fact["카드번호"]:
            continue
        이름 = c["ko"]
        if len(이름) >= 3:
            걸림 = 이름 in t2
        else:
            걸림 = bool(re.search(re.escape(이름) + r"\s*(카드|정방향|역방향)", t2))
        if 걸림:
            bad.append("다른 카드 언급: %s" % 이름)

    # 그 카드에 없는 상징을 지어냈는가
    for c in CARDS:
        if c["id"] == fact["카드번호"]:
            continue
        for p in (c.get("symbolPoints") or []):
            if len(p["part"]) >= 3 and p["part"] in t and p["part"] not in fact["상징전부"]:
                bad.append("없는 상징: %s" % p["part"])

    # 되비추기라면서 손님이 안 쓴 말을 지어냈는가는 LLM 응답 쪽에서 verify_words 로 이미 걸러진다

    if need_question and "?" not in t and "나요" not in t and "까요" not in t:
        bad.append("열린 질문이 없다")

    return bad


# ──────────────────────────────────────────────────────────────
# 6-2. 말투 검사 — LLM 이 빠지는 구덩이 네 개를 막는다
#      해설서 말투 / 상담사 말투 / 점쟁이 말투 / 말투 섞임
# ──────────────────────────────────────────────────────────────

# 존댓말 꼬리. 반말 글에 이게 있으면 섞인 것이다.
JONDAE = re.compile(r"(습니다|입니다|해요|예요|이에요|세요|나요\?|가요\?|까요\?|드려요|드립니다|십니다|하십|시겠)")
# 반말 꼬리. 존댓말 글에 이게 있으면 섞인 것이다.
BANMAL = re.compile(r"(야\?|했어\?|있어\?|없어\?|뭐야|거야\?|같아\?|할까\?|그래\?|하자|해라)")

# 해설서 말투. 기획안 1-3절이 금지한 바로 그것.
HAESEOL = re.compile(r"(의미합니다|의미해|의미한다|상징합니다|상징해|상징한다|나타냅니다|나타낸다|뜻합니다|뜻한다|를 의미|을 의미)")
# 상담사 말투. 심리 기법을 넣었으니 LLM 이 여기로 흐른다. 우리는 상담사가 아니다.
SANGDAM = re.compile(r"(그러셨군요|그랬구나|많이 힘드셨|힘들었겠|마음이 아프|토닥|다독|공감해|잘 견뎌왔)")
# 점쟁이 말투.
JEOM = re.compile(r"(리라(?=[.!?\s]|$)|리로다|그러하니|운명이니|점지|천기)")
# 애교. "약간의" 여성미지 애교가 아니다.
AEGYO = re.compile(r"(ㅎㅎ|ㅋㅋ|ㅠㅠ|ㅜㅜ|~~|!!!)")

EMOJI = re.compile("[🀀-🫿☀-➿]")

MAX_SENT = 45          # 한 문장이 이보다 길면 끊으라는 신호


def 말투검사(text, tone="반말"):
    """말투를 본다. 빈 목록이면 통과. check_output() 과 따로 부른다."""
    bad = []
    t = (text or "").strip()
    if tone not in TONES:
        raise ValueError("말투가 아니다: %r" % tone)

    if tone == "반말":
        m = JONDAE.search(t)
        if m:
            bad.append("반말인데 존댓말이 섞였다: %s" % m.group(1))
    else:
        m = BANMAL.search(t)
        if m:
            bad.append("존댓말인데 반말이 섞였다: %s" % m.group(1))

    for 패턴, 이름 in ((HAESEOL, "해설서 말투"), (SANGDAM, "상담사 말투"), (JEOM, "점쟁이 말투"), (AEGYO, "애교")):
        m = 패턴.search(t)
        if m:
            bad.append("%s: %s" % (이름, m.group(1)))

    for 문장 in [x.strip() for x in re.split("[.!?" + chr(10) + "]", t) if x.strip()]:
        if len(문장) > MAX_SENT:
            bad.append("문장이 길다(%d자): %s…" % (len(문장), 문장[:20]))
            break

    n = len(EMOJI.findall(t))
    if n > 2:
        bad.append("이모지가 많다: %d개" % n)

    return bad


# ──────────────────────────────────────────────────────────────
# 7. 화면 출력 / 자가진단
# ──────────────────────────────────────────────────────────────

def show(fact):
    print("─" * 52)
    print("  %s %s  (%s)" % (fact["로마숫자"], fact["카드"], fact["방향"]))
    print("  열쇠말   %s" % fact["열쇠말"])
    print("  한 줄    %s" % fact["한줄"])
    print("  상징     %s — %s" % (fact["상징하나"], fact["상징뜻"]))
    print("  질문     %s / %s / %s" % (fact["질문유형"], fact["시제"], fact["말투"]))
    print("  되비춤   %s" % ", ".join(fact["손님단어"]) if fact["손님단어"] else "  되비춤   (없음)")
    print("  되물음   %s   [%s]" % (fact["열린질문"], fact["질문출처"]))
    print("  그림     %s  %s" % (fact["앞면"], "(있음)" if 그림있나(fact) else "(파일 없음)"))
    if fact["중지까닭"] == "나이":
        print("  ** 나이가 나왔다. 응답 중지 **")
        print("  내보낼 한 줄: %s" % fact["중지문구"])
    elif fact["무거움"]:
        print("  ** 무거운 신호. 아무 말 없이 사람에게 넘긴다 **")
    print("─" * 52)


def selftest():
    ok, fail = 0, []

    def t(name, cond):
        nonlocal ok
        if cond:
            ok += 1
        else:
            fail.append(name)

    t("카드 22장", len(CARDS) == 22)
    t("상징 전부 있음", all(len(c["symbolPoints"]) >= 4 for c in CARDS))
    t("한 줄 전부 있음", all(c["upright_summary"] and c["reversed_summary"] for c in CARDS))
    # 그림이 텍스트 옆에 같이 있나 (2026-09-23)
    t("22장 전부 그림 이름 있음", all(c.get("img") and c.get("imgPng") and c.get("webPath") for c in CARDS))
    있는것 = sum(1 for c in CARDS if (IMG_DIR / c["img"]).exists())
    t("그림 파일 22장 전부 있음 (%d/22)" % 있는것, 있는것 == 22)
    t("뒷면 파일 있음", BACK_IMG.exists())
    f그림 = digest("@i", "요즘 일이 안 풀려", "일", "지금", "2026-09-23")
    t("재료에 그림이 같이 나온다", 그림있나(f그림))
    t("열린질문 18칸", all(len(OPEN_Q[a][s]) >= 3 for a in ASK_TYPES for s in TENSES))
    t("열린질문 전부 물음표", all(q.endswith("?") for a in ASK_TYPES for s in TENSES for q in OPEN_Q[a][s]))

    a = draw("사람1", "2026-09-23")
    b = draw("사람1", "2026-09-23")
    c = draw("사람2", "2026-09-23")
    d = draw("사람1", "2026-09-24")
    t("같은 사람 같은 날 = 같은 카드", a["카드"]["id"] == b["카드"]["id"] and a["방향"] == b["방향"])
    t("다른 사람 = 갈린다", (a["카드"]["id"], a["방향"]) != (c["카드"]["id"], c["방향"]))
    t("다음 날 = 갈린다", (a["카드"]["id"], a["방향"]) != (d["카드"]["id"], d["방향"]))

    # 22장이 고루 나오나 (2200명 돌려 본다)
    seen = {}
    for i in range(2200):
        k = draw("u%d" % i, "2026-09-23")["카드"]["id"]
        seen[k] = seen.get(k, 0) + 1
    t("22장 전부 나옴", len(seen) == 22)
    t("한 장에 쏠리지 않음", max(seen.values()) < 200)
    정 = sum(1 for i in range(2200) if draw("u%d" % i, "2026-09-23")["방향"] == "정방향")
    t("정/역이 한쪽으로 안 쏠림", 900 < 정 < 1300)

    f = digest("아무개", "요즘 일이 안 풀려요 회사도 그만두고 싶고", "일", "지금", "2026-09-23")
    t("재료에 상징 있음", bool(f["상징하나"]))
    t("되비추기 뽑힘", len(f["손님단어"]) >= 1)
    t("되비추기는 원문에 있는 말", all(w in "요즘 일이 안 풀려요 회사도 그만두고 싶고" for w in f["손님단어"]))
    t("무겁지 않음", f["무거움"] is False)
    t("멀쩡한 글은 안 멈춘다", f["중지"] is False)

    # 나이 규칙 (2026-09-23 사장님 지시)
    for 글 in ["저 17살이에요", "만 14세입니다", "2010년생입니다", "05년생이요", "고2인데요",
               "중학생인데 봐주세요", "스무 살 됐어요", "제 나이가 걸려요", "몇 살로 보이나요",
               "3학년이에요", "서른 넘었어요"]:
        t("나이 잡힘: %s" % 글, age_check(글)[0] is True)
    for 글 in ["요즘 일이 안 풀려요", "살이 쪄서 고민이에요", "세 번이나 떨어졌어요",
               "10세기 유물 같은 회사예요", "3세대 가족이 같이 살아요", "대학생활이 힘들어요"]:
        t("나이 아님: %s" % 글, age_check(글)[0] is False)

    f2 = digest("아무개", "저 17살인데 타로 봐주세요", "불안", "지금", "2026-09-23")
    t("나이 나오면 중지", f2["중지"] is True and f2["중지까닭"] == "나이")
    t("나이 중지엔 한 줄이 있다", f2["중지문구"] == STOP_LINE)
    t("나이 중지면 되비춤 없음", f2["손님단어"] == [])
    f3 = digest("아무개", "죽고 싶어요", "불안", "지금", "2026-09-23")
    t("무거우면 중지", f3["중지"] is True and f3["중지까닭"] == "무거움")
    t("무거우면 내보낼 말 없음", f3["중지문구"] == "")

    t("무거운 신호 잡힘", heavy_check("그냥 죽고 싶어요") is True)
    t("무거운 신호 오탐 없음", heavy_check("일이 너무 힘들어요") is False)

    t("지어낸 낱말 버림", verify_words("일이 안 풀려요", ["일", "이혼"]) == ["일"])

    bad = check_output("금이 간 자리를 그냥 두면 더 벌어집니다. 오늘 하나만 정리해 보시겠어요?", f)
    t("멀쩡한 글은 통과", bad == [], )
    t("금지어 걸림", "금지어: 적중" in check_output("이건 적중입니다. 어떠신가요?", f))
    t("미래 단정 걸림", any("미래 단정" in x for x in check_output("곧 좋은 일이 생깁니다. 어떠신가요?", f)))
    t("질문 없으면 걸림", "열린 질문이 없다" in check_output("그냥 그렇습니다.", f))
    other = "매달린 사람" if f["카드"] != "매달린 사람" else "은둔자"
    t("다른 카드 언급 걸림", any("다른 카드" in x for x in check_output("%s 카드도 같이 보입니다. 어떠신가요?" % other, f)))
    # 이름이 이름을 품는 오탐 (2026-09-23 실제 글에서 "여황제"의 황제가 걸렸다)
    f여 = digest("@q", "직장 그만두는게 나을까", "일", "지금", "2026-09-23")
    if f여["카드"] == "여황제":
        t("여황제 안의 황제는 안 걸린다",
          not any("다른 카드 언급" in x for x in check_output("여황제 역방향 나왔어. 어때?", f여)))
    else:
        t("여황제 안의 황제는 안 걸린다", True)

    # 두 글자 이름 오탐 (2026-09-23 실제 글에서 "2달 반"의 달이 걸렸다)
    f달 = digest("@t", "헤어진 지 2달 반 됐어", "재회", "앞일", "2026-09-23")
    t("2달 반은 달 카드가 아니다",
      not any("다른 카드 언급: 달" in x for x in check_output("헤어진 지 2달 반이면 그럴 수 있어. 어때?", f달)))
    t("달 카드라고 쓰면 걸린다",
      any("다른 카드 언급: 달" in x for x in check_output("달 카드가 같이 보여. 어때?", f달))
      or f달["카드"] == "달")

    # 말투 (2026-09-23)
    t("반말 벌도 24칸", all(len(OPEN_Q_BAN[a][s2]) >= 3 for a in ASK_TYPES for s2 in TENSES))
    t("반말 벌 전부 물음표", all(q.endswith("?") for a in ASK_TYPES for s2 in TENSES for q in OPEN_Q_BAN[a][s2]))
    t("반말 벌에 존댓말 안 섞임",
      all(not 말투검사(q, "반말") for a in ASK_TYPES for s2 in TENSES for q in OPEN_Q_BAN[a][s2]))
    t("존댓말 벌에 반말 안 섞임",
      all(not 말투검사(q, "존대") for a in ASK_TYPES for s2 in TENSES for q in OPEN_Q[a][s2]))
    fb = digest("아무개", "요즘 일이 안 풀려", "일", "지금", "2026-09-23", tone="반말")
    fj = digest("아무개", "요즘 일이 안 풀려요", "일", "지금", "2026-09-23", tone="존대")
    t("말투 따라 질문이 갈린다", fb["열린질문"] != fj["열린질문"])
    t("반말 재료에 말투 표시", fb["말투"] == "반말")
    t("해설서 말투 걸림", any("해설서" in x for x in 말투검사("이 카드는 종결을 의미해. 어때?", "반말")))
    t("상담사 말투 걸림", any("상담사" in x for x in 말투검사("그랬구나. 많이 힘들었겠다. 어때?", "반말")))
    t("점쟁이 말투 걸림", any("점쟁이" in x for x in 말투검사("머지않아 길이 열리리라. 어때?", "반말")))
    t("애교 걸림", any("애교" in x for x in 말투검사("괜찮아 ㅎㅎ 잘 될 거야?", "반말")))
    t("긴 문장 걸림", any("문장이 길다" in x for x in 말투검사("가" * 60 + "?", "반말")))
    t("멀쩡한 반말은 통과", 말투검사("금이 간 자리는 그냥 두면 더 벌어져. 오늘 하나만 정리해볼래?", "반말") == [])

    try:
        digest("아무개", "글", "취업", "지금")
        t("엉뚱한 유형 막힘", False)
    except ValueError:
        t("엉뚱한 유형 막힘", True)
    try:
        digest("아무개", "글", "일", "지금", tone="높임")
        t("엉뚱한 말투 막힘", False)
    except ValueError:
        t("엉뚱한 말투 막힘", True)

    print("통과 %d / 실패 %d" % (ok, len(fail)))
    for x in fail:
        print("  실패 → %s" % x)
    return 0 if not fail else 1


def main():
    ap = argparse.ArgumentParser(description="타로 엔진")
    ap.add_argument("--draw", metavar="누구", help="그 사람의 오늘 카드")
    ap.add_argument("--date", metavar="YYYY-MM-DD", help="날짜 (기본 오늘)")
    ap.add_argument("--test", metavar="댓글", help="댓글 하나로 재료 전체를 뽑아 본다")
    ap.add_argument("--type", default="일", choices=list(ASK_TYPES), help="질문유형")
    ap.add_argument("--tense", default="지금", choices=list(TENSES), help="시제")
    ap.add_argument("--tone", default="반말", choices=list(TONES), help="말투 (스레드=반말, 사이트=존대)")
    ap.add_argument("--json", action="store_true", help="재료를 JSON 으로")
    ap.add_argument("--selftest", action="store_true", help="자가진단")
    a = ap.parse_args()

    if a.selftest:
        sys.exit(selftest())

    if a.test is not None:
        f = digest(a.draw or "테스트손님", a.test, a.type, a.tense, a.date, tone=a.tone)
    elif a.draw:
        f = digest(a.draw, "", a.type, a.tense, a.date, tone=a.tone)
    else:
        ap.print_help()
        return

    if a.json:
        print(json.dumps(f, ensure_ascii=False, indent=2))
    else:
        show(f)


if __name__ == "__main__":
    main()
