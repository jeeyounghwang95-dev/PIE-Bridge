# backend/app/services/rag_service.py
#
# PIE BRIDGE - RAG 서비스 (ChromaDB + Google Generative AI Embeddings)
#
# 역할:
#   1. 햄스터-S API 문서를 청크로 분할 → Google 임베딩 → ChromaDB에 저장
#   2. 학생의 행동 계획을 쿼리로 관련 API 문서 검색
#   3. 검색 결과를 gemini_service.py 에 컨텍스트로 전달
#
# 플랫폼별 문서:
#   - robomation: 로보메이션 Block Composer 방식
#                 (asyncio + __('HamsterS*0:...') 메타 접근자)
#   - entry:      엔트리 파이썬 에디터 방식
#                 (import Hamster + Hamster.메서드() 직접 호출)
#   ⚠️ 두 방식은 문법이 완전히 다르므로 컬렉션을 분리해서 운용.
#
# 최초 실행 시 DB 빌드:
#   python -m app.services.rag_service              # 증분 빌드
#   python -m app.services.rag_service --rebuild    # 강제 재빌드 (로보메이션만)
#
# ⚠️ 중요: 기존에 roboid 기반 문서로 빌드된 DB가 있다면 반드시 --rebuild 실행.
#          (구 문서와 섞이면 검색 품질이 크게 떨어짐)
#
# 의존성:
#   pip install chromadb langchain langchain-google-genai

import logging
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── ChromaDB 경로 (백엔드 루트 기준) ────────────────────────
CHROMA_DIR = Path(__file__).parent.parent.parent / "chroma_db"
COLLECTION_NAME         = "hamster_s_api"       # 로보메이션 Block Composer 전용

# ── 검색 설정 ────────────────────────────────────────────────
TOP_K = 5           # 검색 결과 상위 몇 개를 가져올지
MIN_RELEVANCE = 0.3 # 이 유사도 미만은 제외 (0~1, 낮을수록 유사)


# ─────────────────────────────────────────────────────────────
# 햄스터-S 전체 API 문서 (로보메이션 Block Composer 기준)
# 출처: 로보메이션 랩 Block Composer 공식 예제 기반
# ⚠️ 주의: 아래 문서는 "Block Composer" 방식 (asyncio + __() 메타 접근자) 전용.
#        엔트리 파이썬 에디터의 `import Hamster` 방식과는 완전히 다르며,
#        또한 로컬 `from roboid import *` 방식과도 다름.
# ─────────────────────────────────────────────────────────────
HAMSTER_S_DOCS = [

    # ── 섹션 1: 기본 구조 및 핵심 문법 ─────────────────────────
    {
        "id": "bc_setup_basic",
        "title": "로보메이션 Block Composer 기본 구조 및 핵심 문법",
        "content": """
# 로보메이션 Block Composer 햄스터 S 기본 구조

## 필수 임포트 및 코드 골격
```python
import asyncio

# put setup code here, to run once:
async def setup():
    # 한 번 실행할 동작을 여기에 작성
    pass

# put control code here, to run repeatedly:
async def loop():
    # 반복 실행 코드 (사용 안 하면 pass)
    pass
```

## 절대 규칙 (Block Composer 전용)
- 반드시 `import asyncio` 로 시작 (다른 import는 불필요)
- **`from roboid import *` 사용 금지**, **`import Hamster` 사용 금지**
- **`HamsterS()` 인스턴스 생성 금지** — `__('HamsterS*0:...')` 메타 접근자로 직접 제어
- **들여쓰기는 반드시 스페이스 4칸으로 통일** (탭과 스페이스 혼용 금지 — IndentationError 방지)
- 한 번 실행할 이동/동작 코드는 **반드시 `async def setup():`** 안에 작성
- **`setup()` 과 `loop()` 는 반드시 `async def` 로 선언** (일반 `def` 면 TypeError 로 중단됨)
- 반복 실행 코드는 `async def loop():` 안에 작성. 실행할 코드가 없으면 `return` 대신 `pass`
- 대기는 **`await asyncio.sleep(초)`** — `setup()` 또는 `async def loop()` 안에서만 사용
- `try/finally` 구조 사용 금지, `dispose()` 호출 금지

## 메타 접근자 기본 문법
Block Composer는 모든 센서/액추에이터를 `__('디바이스ID:속성경로')` 로 접근한다.
```python
# 값 쓰기 (액추에이터 제어)
__('HamsterS*0:wheel.speed.left').d = 50

# 값 읽기 (센서 값)
value = __('HamsterS*0:proximity.left').d

# 이벤트 대기 (이동 완료 등)
await __('HamsterS*0:wheel.!move').w()
```
- `HamsterS*0` : USB 동글에 첫 번째로 연결된 햄스터 S (0번). 두 번째 로봇은 `HamsterS*1`
- `.d` : 데이터(data) 속성 — 값 읽기/쓰기
- `.w()` : wait — 해당 이벤트(예: 이동 완료)가 발생할 때까지 대기

## 자주 쓰는 헬퍼 함수 (Block Composer 제공, 별도 import 불필요)
| 함수 | 설명 |
|------|------|
| `__getSpeed(디바이스, 속도)` | 속도 값을 디바이스에 맞게 변환 (-100~100) |
| `__getSpeedInput(디바이스, 값)` | 디바이스 내부값을 속도값(%)으로 역변환 |
| `__getDistance(디바이스, 값, 단위)` | 거리 값을 내부값으로 변환 ('cm', 'mm' 등) |
| `__stopMove(디바이스)` | 이동 즉시 정지 |
| `__stopAfterDelay(디바이스, 초, True)` | n초 후 정지 (await 필요) |
| `__turnDegreeLeft(디바이스, 각도, True)` | 제자리 왼쪽 회전 (await 필요) |
| `__turnDegreeRight(디바이스, 각도, True)` | 제자리 오른쪽 회전 (await 필요) |
| `__keypressed(키코드)` | 키보드 입력 감지 (38=↑, 40=↓, 37=←, 39=→, 32=space) |
| `__scope(이름, 최소, 최대, 색상, 값)` | 스코프 그래프에 값 출력 |
""",
    },

    # ── 섹션 2: 바퀴 속도 제어 (전진/후진) ─────────────────────
    {
        "id": "bc_wheel_speed",
        "title": "바퀴 속도 제어 — 전진, 후진, 정지 (Block Composer)",
        "content": """
# Block Composer 바퀴 속도 제어

## 핵심 속성
- `__('HamsterS*0:wheel.speed.left').d`  — 왼쪽 바퀴 속도 (-100~100)
- `__('HamsterS*0:wheel.speed.right').d` — 오른쪽 바퀴 속도 (-100~100)
- `__('HamsterS*0:wheel.move').d`        — 거리 이동 모드 상태 (0이 아니면 먼저 0으로 리셋)

## 속도 설정 표준 패턴 (매우 중요!)
속도를 바꾸기 전에 반드시 `wheel.move` 상태를 0으로 리셋해야 거리 이동 명령과 충돌하지 않는다.
```python
# 표준 패턴 — 이 4줄이 "속도 설정"의 완전한 형태
if __('HamsterS*0:wheel.move').d != 0:
    __('HamsterS*0:wheel.move').d = 0
__('HamsterS*0:wheel.speed.left').d = __getSpeed('HamsterS*0', 50)
__('HamsterS*0:wheel.speed.right').d = __getSpeed('HamsterS*0', 50)
```

## 전진/후진/정지 완전 예시
```python
import asyncio

async def setup():
    # 전진: 속도 50으로 2초
    if __('HamsterS*0:wheel.move').d != 0:
        __('HamsterS*0:wheel.move').d = 0
    __('HamsterS*0:wheel.speed.left').d = __getSpeed('HamsterS*0', 50)
    __('HamsterS*0:wheel.speed.right').d = __getSpeed('HamsterS*0', 50)
    await asyncio.sleep(2)

    # 정지
    __stopMove('HamsterS*0')
    await asyncio.sleep(1)

    # 후진: 속도 -50으로 2초
    if __('HamsterS*0:wheel.move').d != 0:
        __('HamsterS*0:wheel.move').d = 0
    __('HamsterS*0:wheel.speed.left').d = __getSpeed('HamsterS*0', -50)
    __('HamsterS*0:wheel.speed.right').d = __getSpeed('HamsterS*0', -50)
    await asyncio.sleep(2)
    __stopMove('HamsterS*0')
    return

async def loop():
    pass
```

## 부호 규칙
- 전진 방향은 `+` (양수) — 예: `__getSpeed('HamsterS*0', 50)`
- 후진 방향은 `-` (음수) — 예: `__getSpeed('HamsterS*0', -50)`
- 속도 범위: -100 ~ 100 (교실 수업 권장: 30~50)

## 정지 방법 2가지
1. **`__stopMove('HamsterS*0')`** — 헬퍼 함수 (권장)
2. **양쪽 바퀴 속도를 0으로 설정** — 명시적 정지
```python
__('HamsterS*0:wheel.speed.left').d = __getSpeed('HamsterS*0', 0)
__('HamsterS*0:wheel.speed.right').d = __getSpeed('HamsterS*0', 0)
```
""",
    },

    # ── 섹션 3: 회전 (좌회전/우회전) ───────────────────────────
    {
        "id": "bc_turn",
        "title": "제자리 회전 및 바퀴 차동 회전 (Block Composer)",
        "content": """
# Block Composer 회전 제어

## 1. 각도 기반 제자리 회전 (헬퍼 함수, 권장)
가장 정확하고 간단한 방법. 지정 각도만큼 정확히 회전한 후 자동 정지.
```python
# 왼쪽 90도 회전 (제자리)
await __turnDegreeLeft('HamsterS*0', 90, True)

# 오른쪽 90도 회전 (제자리)
await __turnDegreeRight('HamsterS*0', 90, True)

# 180도 유턴 (왼쪽 기준)
await __turnDegreeLeft('HamsterS*0', 180, True)
```
- 마지막 인자 `True` : 회전 완료까지 대기 (await 필수)
- 각도 범위: 0 ~ 360

## 2. 바퀴 차동 속도로 회전 (수동 방식)
한쪽 바퀴만 돌리거나, 양쪽을 반대로 돌려 회전.
```python
import asyncio

async def setup():
    # 왼쪽으로 회전 (왼쪽 바퀴 정지, 오른쪽 바퀴 전진)
    if __('HamsterS*0:wheel.move').d != 0:
        __('HamsterS*0:wheel.move').d = 0
    __('HamsterS*0:wheel.speed.left').d = __getSpeed('HamsterS*0', 0)
    __('HamsterS*0:wheel.speed.right').d = __getSpeed('HamsterS*0', 50)
    await asyncio.sleep(1)
    __stopMove('HamsterS*0')

    # 오른쪽으로 회전 (왼쪽 바퀴 전진, 오른쪽 바퀴 정지)
    if __('HamsterS*0:wheel.move').d != 0:
        __('HamsterS*0:wheel.move').d = 0
    __('HamsterS*0:wheel.speed.left').d = __getSpeed('HamsterS*0', 50)
    __('HamsterS*0:wheel.speed.right').d = __getSpeed('HamsterS*0', 0)
    await asyncio.sleep(1)
    __stopMove('HamsterS*0')

    # 제자리 회전 (양쪽 반대)
    __('HamsterS*0:wheel.speed.left').d = __getSpeed('HamsterS*0', -50)
    __('HamsterS*0:wheel.speed.right').d = __getSpeed('HamsterS*0', 50)
    await asyncio.sleep(1)
    __stopMove('HamsterS*0')
    return
```

## 언제 무엇을 쓸까?
- **정확한 각도가 중요** → `__turnDegreeLeft/Right` (권장)
- **부드러운 커브, 연속 주행** → 바퀴 차동 속도
- **키보드 제어(리모컨)** → 바퀴 차동 속도
""",
    },

    # ── 섹션 4: 바퀴 가감속 (속도 점진 변경) ───────────────────
    {
        "id": "bc_wheel_acceleration",
        "title": "바퀴 가감속 제어 — 점진적 속도 증가/감소 (Block Composer)",
        "content": """
# Block Composer 바퀴 가감속 제어

## 개념
`while` 반복문으로 속도를 조금씩 증가/감소시켜 부드러운 출발/정지 구현.
`__getSpeedInput()` 로 현재 내부값을 속도(%)로 역변환해서 조건 비교에 사용.

## 완전 예시: 0 → 50 가속 → 1초 대기 → 50 → 0 감속
```python
import asyncio

async def setup():
    # 초기 속도 0
    if __('HamsterS*0:wheel.move').d != 0:
        __('HamsterS*0:wheel.move').d = 0
    __('HamsterS*0:wheel.speed.left').d = __getSpeed('HamsterS*0', 0)
    __('HamsterS*0:wheel.speed.right').d = __getSpeed('HamsterS*0', 0)

    # 가속: 0 → 50까지 0.2초마다 5씩 증가
    while 50 > __getSpeedInput('HamsterS*0', __('HamsterS*0:wheel.speed.left').d):
        if __('HamsterS*0:wheel.move').d != 0:
            __('HamsterS*0:wheel.move').d = 0
        __('HamsterS*0:wheel.speed.left').d = (
            __('HamsterS*0:wheel.speed.left').d + __getSpeed('HamsterS*0', 5)
        )
        __('HamsterS*0:wheel.speed.right').d = (
            __('HamsterS*0:wheel.speed.right').d + __getSpeed('HamsterS*0', 5)
        )
        await asyncio.sleep(0.2)

    # 최대속도 유지 1초
    await asyncio.sleep(1)

    # 감속: 50 → 0까지 0.2초마다 5씩 감소
    while 0 < __getSpeedInput('HamsterS*0', __('HamsterS*0:wheel.speed.left').d):
        if __('HamsterS*0:wheel.move').d != 0:
            __('HamsterS*0:wheel.move').d = 0
        __('HamsterS*0:wheel.speed.left').d = (
            __('HamsterS*0:wheel.speed.left').d + __getSpeed('HamsterS*0', -5)
        )
        __('HamsterS*0:wheel.speed.right').d = (
            __('HamsterS*0:wheel.speed.right').d + __getSpeed('HamsterS*0', -5)
        )
        await asyncio.sleep(0.2)
    return

async def loop():
    # 스코프에 현재 바퀴 속도 실시간 표시
    __scope('바퀴속도', 0, 100, '#ff0000',
            __getSpeedInput('HamsterS*0', __('HamsterS*0:wheel.speed.left').d))
    return
```

## 포인트
- 비교는 `__getSpeedInput(...)` 으로 속도(%) 기준 — 내부값과 %를 혼용하지 말 것
- 증감은 `+ __getSpeed('HamsterS*0', 5)` 처럼 **델타를 내부값으로 변환해서 더함**
- 각 스텝 사이 `await asyncio.sleep(0.2)` 로 가감속 속도 조절
""",
    },

    # ── 섹션 5: 거리 이동 제어 (앞/뒤/좌/우) — 모든 이동의 유일한 표준 ─
    {
        "id": "bc_move_distance",
        "title": "거리 이동 제어 — 앞/뒤/좌/우 이동 (모든 이동의 유일한 표준, Block Composer)",
        "content": """
# Block Composer 거리 이동 제어 (앞·뒤·좌·우)

## ★★★ 절대 규칙 (모든 이동은 반드시 이 문서를 따른다) ★★★
- 햄스터 S 가 **이동(앞으로/뒤로/왼쪽/오른쪽)** 할 때는 **오직 이 거리 이동 블록만** 사용한다.
- **말판(격자 보드)이 있든 없든 항상 동일하게 거리 이동 블록을 사용**한다.
  (말판이 있다고 해서 다른 이동 방식으로 바꾸지 않는다.)
- **라인 트레이싱 / 선 따라가기 / `wheel.trace.*` (trace.speed, trace.gain, trace.mode,
  `wheel.trace.!mode`) 코드는 절대 생성 금지.** 이동은 무조건 거리 이동 블록으로만 표현한다.
- 전진/후진은 아래 "거리 이동 블록", 좌회전/우회전은 `__turnDegreeLeft/Right` 헬퍼만 사용한다.

## 핵심: `wheel.move` 속성 + `!move` 이벤트 대기
지정 거리만큼 이동한 후 자동 정지하는 방식. 속도 + 거리 + 완료 대기의 3단 구조.

## 앞으로 이동 (전진) — 표준 거리 이동 블록
```python
# 바퀴 속력 50으로 5cm 앞으로 이동
if __('HamsterS*0:wheel.move').d != 0:
    __('HamsterS*0:wheel.move').d = 0
__('HamsterS*0:wheel.speed.left').d = __getSpeed('HamsterS*0', 50)
__('HamsterS*0:wheel.speed.right').d = __getSpeed('HamsterS*0', 50)
__('HamsterS*0:wheel.move').d = __getDistance('HamsterS*0', 5, 'cm')
await __('HamsterS*0:wheel.!move').w()   # 이동 완료까지 대기
```

## 뒤로 이동 (후진) — 속도에 음수(-) 부호, 거리는 양수 유지
```python
# 바퀴 속력 50으로 뒤로 5cm 뒤로 이동
if __('HamsterS*0:wheel.move').d != 0:
    __('HamsterS*0:wheel.move').d = 0
__('HamsterS*0:wheel.speed.left').d = __getSpeed('HamsterS*0', -50)
__('HamsterS*0:wheel.speed.right').d = __getSpeed('HamsterS*0', -50)
__('HamsterS*0:wheel.move').d = __getDistance('HamsterS*0', 5, 'cm')
await __('HamsterS*0:wheel.!move').w()
```

## 왼쪽 / 오른쪽 회전 — 제자리 각도 회전 헬퍼
```python
# 제자리에서 왼쪽으로 90도 회전
await __turnDegreeLeft('HamsterS*0', 90, True)
# 제자리에서 오른쪽으로 90도 회전
await __turnDegreeRight('HamsterS*0', 90, True)
```

## 완전 예시: 전진 5cm → 왼쪽 90도 → 오른쪽 90도 → 후진 5cm
```python
import asyncio

# 햄스터 S 거리 이동 제어
async def setup():
    # 바퀴 속력 50으로 5cm 앞으로 이동
    if __('HamsterS*0:wheel.move').d != 0:
        __('HamsterS*0:wheel.move').d = 0
    __('HamsterS*0:wheel.speed.left').d = __getSpeed('HamsterS*0', 50)
    __('HamsterS*0:wheel.speed.right').d = __getSpeed('HamsterS*0', 50)
    __('HamsterS*0:wheel.move').d = __getDistance('HamsterS*0', 5, 'cm')
    await __('HamsterS*0:wheel.!move').w()
    await asyncio.sleep(0.5)
    # 제자리에서 왼쪽으로 90도 회전
    await __turnDegreeLeft('HamsterS*0', 90, True)
    await asyncio.sleep(0.5)
    # 제자리에서 오른쪽으로 90도 회전
    await __turnDegreeRight('HamsterS*0', 90, True)
    await asyncio.sleep(0.5)
    # 바퀴 속력 50으로 뒤로 5cm 뒤로 이동
    if __('HamsterS*0:wheel.move').d != 0:
        __('HamsterS*0:wheel.move').d = 0
    __('HamsterS*0:wheel.speed.left').d = __getSpeed('HamsterS*0', -50)
    __('HamsterS*0:wheel.speed.right').d = __getSpeed('HamsterS*0', -50)
    __('HamsterS*0:wheel.move').d = __getDistance('HamsterS*0', 5, 'cm')
    await __('HamsterS*0:wheel.!move').w()
    await asyncio.sleep(0.5)
    return

async def loop():
    pass
```

## 포인트
- `__getDistance(디바이스, 값, 'cm')` — 단위는 `'cm'` 문자열
- `await __('HamsterS*0:wheel.!move').w()` — 속성명 앞에 `!` 를 붙인 "완료 이벤트"를 대기
- 각 동작 사이 `await asyncio.sleep(0.5)` 로 간격을 두면 안정성 향상
- 후진도 **부호(-)** 를 속도에 붙이고 거리는 양수로 유지
- 회전 각도/이동 거리만 바꾸면 어떤 경로든 모두 이 블록 조합으로 표현 가능
""",
    },

    # ── 섹션 6: 시간 이동 (초 단위) ────────────────────────────
    {
        "id": "bc_move_time",
        "title": "시간 이동 — 초 단위 이동 후 자동 정지 (Block Composer)",
        "content": """
# Block Composer 시간 이동 제어

## 핵심 헬퍼: `__stopAfterDelay`
지정 속도로 출발한 뒤 n초 후 자동 정지하는 헬퍼 함수.

## 표준 패턴
```python
# 속도 50으로 5초 전진
if __('HamsterS*0:wheel.move').d != 0:
    __('HamsterS*0:wheel.move').d = 0
__('HamsterS*0:wheel.speed.left').d = __getSpeed('HamsterS*0', 50)
__('HamsterS*0:wheel.speed.right').d = __getSpeed('HamsterS*0', 50)
await __stopAfterDelay('HamsterS*0', 5, True)
```

## 완전 예시: 5초 전진 → 5초 후진
```python
import asyncio

async def setup():
    # 속도 50으로 5초 전진
    if __('HamsterS*0:wheel.move').d != 0:
        __('HamsterS*0:wheel.move').d = 0
    __('HamsterS*0:wheel.speed.left').d = __getSpeed('HamsterS*0', 50)
    __('HamsterS*0:wheel.speed.right').d = __getSpeed('HamsterS*0', 50)
    await __stopAfterDelay('HamsterS*0', 5, True)
    await asyncio.sleep(0.5)

    # 속도 -50으로 5초 후진
    if __('HamsterS*0:wheel.move').d != 0:
        __('HamsterS*0:wheel.move').d = 0
    __('HamsterS*0:wheel.speed.left').d = __getSpeed('HamsterS*0', -50)
    __('HamsterS*0:wheel.speed.right').d = __getSpeed('HamsterS*0', -50)
    await __stopAfterDelay('HamsterS*0', 5, True)
    return

async def loop():
    pass
```

## 거리 이동 vs 시간 이동 — 언제 무엇을 쓸까?
| 상황 | 권장 방법 | 이유 |
|------|----------|------|
| 정확한 거리(예: "5cm") | `__getDistance` + `!move` 대기 | 거리 정밀도↑ |
| 정해진 시간 동안 계속 이동 | `__stopAfterDelay` | 시간 기준이 자연스러움 |
| 단순 직진 데모 | `await asyncio.sleep(초)` + `__stopMove` | 가장 간단 |
""",
    },

    # ── 섹션 7: 키보드 제어 (리모컨) ───────────────────────────
    {
        "id": "bc_keyboard_control",
        "title": "키보드로 햄스터 조종 — 리모컨 만들기 (Block Composer)",
        "content": """
# Block Composer 키보드 제어

## 키코드 상수 (JavaScript keyCode 기준)
- `38` : 위쪽 화살표 (↑)
- `40` : 아래쪽 화살표 (↓)
- `37` : 왼쪽 화살표 (←)
- `39` : 오른쪽 화살표 (→)
- `32` : 스페이스바

## 핵심: `async def loop()` + `__keypressed()`
키 입력은 계속 감지해야 하므로 `loop()` 안에 작성. 단, `await`를 쓰려면 `async def loop()` 로 정의.

## 완전한 리모컨 예시
```python
import asyncio

async def setup():
    # 초기 바퀴 속도 0
    if __('HamsterS*0:wheel.move').d != 0:
        __('HamsterS*0:wheel.move').d = 0
    __('HamsterS*0:wheel.speed.left').d = __getSpeed('HamsterS*0', 0)
    __('HamsterS*0:wheel.speed.right').d = __getSpeed('HamsterS*0', 0)
    return

async def loop():
    # ↑ : 전진
    if __keypressed(38):
        if __('HamsterS*0:wheel.move').d != 0:
            __('HamsterS*0:wheel.move').d = 0
        __('HamsterS*0:wheel.speed.left').d = __getSpeed('HamsterS*0', 50)
        __('HamsterS*0:wheel.speed.right').d = __getSpeed('HamsterS*0', 50)
    # ← : 왼쪽 회전 (왼쪽 바퀴 정지, 오른쪽 바퀴 전진)
    if __keypressed(37):
        if __('HamsterS*0:wheel.move').d != 0:
            __('HamsterS*0:wheel.move').d = 0
        __('HamsterS*0:wheel.speed.left').d = __getSpeed('HamsterS*0', 0)
        __('HamsterS*0:wheel.speed.right').d = __getSpeed('HamsterS*0', 50)
    # → : 오른쪽 회전
    if __keypressed(39):
        if __('HamsterS*0:wheel.move').d != 0:
            __('HamsterS*0:wheel.move').d = 0
        __('HamsterS*0:wheel.speed.left').d = __getSpeed('HamsterS*0', 50)
        __('HamsterS*0:wheel.speed.right').d = __getSpeed('HamsterS*0', 0)
    # ↓ : 후진
    if __keypressed(40):
        if __('HamsterS*0:wheel.move').d != 0:
            __('HamsterS*0:wheel.move').d = 0
        __('HamsterS*0:wheel.speed.left').d = __getSpeed('HamsterS*0', -50)
        __('HamsterS*0:wheel.speed.right').d = __getSpeed('HamsterS*0', -50)
    # Space : 정지
    if __keypressed(32):
        if __('HamsterS*0:wheel.move').d != 0:
            __('HamsterS*0:wheel.move').d = 0
        __('HamsterS*0:wheel.speed.left').d = __getSpeed('HamsterS*0', 0)
        __('HamsterS*0:wheel.speed.right').d = __getSpeed('HamsterS*0', 0)
    return
```

## 포인트
- `loop()` 는 반복 실행되는 "무한 반복하기" 블록
- 키 입력 감지가 있는 loop는 반드시 `async def loop():` (await 사용 가능하도록)
- `if` 여러 개 병렬 배치 — 동시 누름도 감지되지만 나중 판정 결과가 적용됨
""",
    },

    # ── 섹션 8: LED 색상 제어 (미리 정의된 색) ─────────────────
    {
        "id": "bc_led_color_preset",
        "title": "LED 색상 제어 — 미리 정의된 색상 설정 (Block Composer)",
        "content": """
# Block Composer LED 색상 제어

## 핵심 속성
- `__('HamsterS*0:led.left').d`  — 왼쪽 LED  [R, G, B]  각 0~255
- `__('HamsterS*0:led.right').d` — 오른쪽 LED [R, G, B]  각 0~255

## 자주 쓰는 색상표 (RGB)
| 색 | RGB | 용도 |
|----|-----|------|
| 빨강 | `[255, 0, 0]`     | 경고, 정지 |
| 주황 | `[255, 128, 0]`   | 주의 |
| 노랑 | `[255, 255, 0]`   | 대기 |
| 초록 | `[0, 255, 0]`     | 정상, 출발 |
| 파랑 | `[0, 0, 255]`     | 정보 |
| 보라 | `[128, 0, 255]`   | 특수 |
| 흰색 | `[255, 255, 255]` | 최대 밝기 |
| 끄기 | `[0, 0, 0]`       | LED 꺼짐 |

## 완전 예시: 양쪽 빨강 → 왼쪽 초록 → 오른쪽 파랑 → 끄기
```python
import asyncio

async def setup():
    # 1. 양쪽 LED 빨간색
    __('HamsterS*0:led.left').d = [255, 0, 0]
    __('HamsterS*0:led.right').d = [255, 0, 0]
    await asyncio.sleep(1)

    # 2. 왼쪽만 초록색으로 변경
    __('HamsterS*0:led.left').d = [0, 255, 0]
    await asyncio.sleep(1)

    # 3. 오른쪽만 파란색으로 변경
    __('HamsterS*0:led.right').d = [0, 0, 255]
    await asyncio.sleep(1)

    # 4. 양쪽 LED 끄기
    __('HamsterS*0:led.left').d = [0, 0, 0]
    __('HamsterS*0:led.right').d = [0, 0, 0]
    return

async def loop():
    pass
```

## 포인트
- LED 색은 **리스트 `[R, G, B]`** 로 한 번에 설정 (값은 즉시 반영)
- 왼쪽/오른쪽을 각각 다르게 설정 가능 → 방향 표시등(깜빡이) 연출 가능
- 다음 값을 설정하기 전까지 색은 유지됨 — 끄려면 명시적으로 `[0, 0, 0]`
""",
    },

    # ── 섹션 9: LED 밝기 디밍 (점진 변화) ──────────────────────
    {
        "id": "bc_led_dimming",
        "title": "LED 밝기 디밍 — 점진적으로 밝아지고 어두워지기 (Block Composer)",
        "content": """
# Block Composer LED 디밍 효과

## 개념
`for` 반복문으로 RGB 값을 조금씩 증가/감소시켜 서서히 밝아지거나 어두워지는 효과.

## 완전 예시: 흰색 페이드 인/아웃 → 빨간색 페이드 인/아웃
```python
import asyncio

async def setup():
    # 초기 꺼짐 상태
    __('HamsterS*0:led.left').d = [0, 0, 0]
    __('HamsterS*0:led.right').d = [0, 0, 0]

    # 1. 흰색으로 서서히 켜기 (RGB 전부 +10씩 25회 → 최대 250)
    for count in range(25):
        __('HamsterS*0:led.left').d = [
            __('HamsterS*0:led.left').d[0] + 10,
            __('HamsterS*0:led.left').d[1] + 10,
            __('HamsterS*0:led.left').d[2] + 10,
        ]
        __('HamsterS*0:led.right').d = [
            __('HamsterS*0:led.right').d[0] + 10,
            __('HamsterS*0:led.right').d[1] + 10,
            __('HamsterS*0:led.right').d[2] + 10,
        ]
        await asyncio.sleep(0.1)

    # 2. 흰색에서 서서히 꺼지기 (RGB 전부 -10씩 25회)
    for count2 in range(25):
        __('HamsterS*0:led.left').d = [
            __('HamsterS*0:led.left').d[0] - 10,
            __('HamsterS*0:led.left').d[1] - 10,
            __('HamsterS*0:led.left').d[2] - 10,
        ]
        __('HamsterS*0:led.right').d = [
            __('HamsterS*0:led.right').d[0] - 10,
            __('HamsterS*0:led.right').d[1] - 10,
            __('HamsterS*0:led.right').d[2] - 10,
        ]
        await asyncio.sleep(0.1)

    # 3. 빨간색으로 서서히 켜기 (R만 +10씩)
    for count3 in range(25):
        __('HamsterS*0:led.left').d = [
            __('HamsterS*0:led.left').d[0] + 10, 0, 0
        ]
        __('HamsterS*0:led.right').d = [
            __('HamsterS*0:led.right').d[0] + 10, 0, 0
        ]
        await asyncio.sleep(0.1)

    # 4. 빨간색에서 서서히 꺼지기
    for count4 in range(25):
        __('HamsterS*0:led.left').d = [
            __('HamsterS*0:led.left').d[0] - 10, 0, 0
        ]
        __('HamsterS*0:led.right').d = [
            __('HamsterS*0:led.right').d[0] - 10, 0, 0
        ]
        await asyncio.sleep(0.1)
    return

async def loop():
    pass
```

## 포인트
- `range(25)` × `+10` = 최대 250 (0~255 범위 안)
- 각 반복마다 `await asyncio.sleep(0.1)` 로 부드러운 페이드 효과
- 원하는 색만 증가/감소시켜 특정 색조의 디밍 가능 (빨강만, 초록만 등)
- 한 색만 증가시키고 나머지 채널은 `0` 으로 고정하면 선명한 단색 디밍
""",
    },

    # ── 섹션 10: 버저 음악 재생 ────────────────────────────────
    {
        "id": "bc_buzzer_music",
        "title": "버저로 음 재생 — 도레미파솔, 주파수 제어 (Block Composer)",
        "content": """
# Block Composer 버저 주파수 제어

## 핵심 속성
- `__('HamsterS*0:sound.buzz').d` — 버저 주파수 (Hz, 실수)
- 범위: 0Hz ~ 6502Hz, 소수점 1자리까지 정확도
- `0` 으로 설정 = 음소거

## 피아노 88건반 주요 주파수표
| 음 | 4옥타브 | 5옥타브 |
|----|---------|---------|
| 도 (C) | 261.6 | 523.3 |
| 레 (D) | 293.7 | 587.3 |
| 미 (E) | 329.6 | 659.3 |
| 파 (F) | 349.2 | 698.5 |
| 솔 (G) | 392.0 | 784.0 |
| 라 (A) | 440.0 | 880.0 |
| 시 (B) | 493.9 | 987.8 |

## 완전 예시: 도레미파솔 0.5초씩 재생
```python
import asyncio

async def setup():
    # 도 (C4)
    __('HamsterS*0:sound.buzz').d = 261.6
    await asyncio.sleep(0.5)
    # 레 (D4)
    __('HamsterS*0:sound.buzz').d = 293.7
    await asyncio.sleep(0.5)
    # 미 (E4)
    __('HamsterS*0:sound.buzz').d = 329.6
    await asyncio.sleep(0.5)
    # 파 (F4)
    __('HamsterS*0:sound.buzz').d = 349.2
    await asyncio.sleep(0.5)
    # 솔 (G4)
    __('HamsterS*0:sound.buzz').d = 392.0
    await asyncio.sleep(0.5)

    # 음소거
    __('HamsterS*0:sound.buzz').d = 0
    return

async def loop():
    pass
```

## 포인트
- 주파수는 **설정 즉시 반영** — `await asyncio.sleep()` 으로 음 길이 조절
- 곡을 끝낼 때는 반드시 마지막에 `sound.buzz = 0` 으로 음소거
- 같은 음을 끊어서 연주하려면 중간에 `= 0` → `await sleep(짧게)` → `= 주파수` 패턴
""",
    },

    # ── 섹션 11: 근접 센서 ────────────────────────────────────
    {
        "id": "bc_proximity_sensor",
        "title": "근접 센서 — 장애물/손 감지 (Block Composer)",
        "content": """
# Block Composer 근접 센서

## 핵심 속성
- `__('HamsterS*0:proximity.left').d`  — 왼쪽 근접 센서 값 (0~255)
- `__('HamsterS*0:proximity.right').d` — 오른쪽 근접 센서 값 (0~255)
- 값이 클수록 물체가 가까움 (센서 앞에 손을 대면 ~255 근처)
- 기준값 예: 약 50 이상이면 "손/장애물 감지"로 판정하는 것이 무난

## 완전 예시: 근접 센서 값을 LED 밝기로 연동
```python
import asyncio

async def setup():
    # 별도 초기화 불필요
    return

async def loop():
    # 스코프에 센서값 실시간 출력 (디버깅용)
    __scope('근접 센서', 0, 255, '#ff0000', __('HamsterS*0:proximity.left').d)
    __scope('근접 센서', 0, 255, '#00cc00', __('HamsterS*0:proximity.right').d)

    # 근접 센서 값을 LED 밝기로 표현 (가까울수록 밝아짐)
    __('HamsterS*0:led.left').d  = [__('HamsterS*0:proximity.left').d, 0, 0]
    __('HamsterS*0:led.right').d = [0, __('HamsterS*0:proximity.right').d, 0]
    return
```

## 장애물 감지로 멈추기 예시
```python
import asyncio

async def setup():
    # 전진 시작
    if __('HamsterS*0:wheel.move').d != 0:
        __('HamsterS*0:wheel.move').d = 0
    __('HamsterS*0:wheel.speed.left').d = __getSpeed('HamsterS*0', 30)
    __('HamsterS*0:wheel.speed.right').d = __getSpeed('HamsterS*0', 30)
    return

async def loop():
    # 양쪽 근접 센서 중 하나라도 장애물 감지 → 정지
    if __('HamsterS*0:proximity.left').d > 50 or __('HamsterS*0:proximity.right').d > 50:
        __stopMove('HamsterS*0')
        # 경고 LED (빨강)
        __('HamsterS*0:led.left').d = [255, 0, 0]
        __('HamsterS*0:led.right').d = [255, 0, 0]
    return
```

## 포인트
- 센서 값은 `loop()` 안에서 계속 읽어야 실시간 반응
- 임계값(50 등)은 환경에 따라 조정 필요 — 스코프로 실제 값 확인 후 조정
- LED 밝기를 센서값에 직접 매핑하면 시각적 피드백이 강함
""",
    },

    # ── 섹션 13: 종합 예제 — 학생 수업 시나리오 ────────────────
    {
        "id": "bc_full_examples",
        "title": "Block Composer 종합 예제 — 수업 시나리오별 완성 코드",
        "content": """
# Block Composer 햄스터 S 종합 예제

## 예제 1: 사각형 경로 그리기 (5cm × 4번, 90도 × 4번)
```python
import asyncio

async def setup():
    for i in range(4):
        # 5cm 전진
        if __('HamsterS*0:wheel.move').d != 0:
            __('HamsterS*0:wheel.move').d = 0
        __('HamsterS*0:wheel.speed.left').d = __getSpeed('HamsterS*0', 40)
        __('HamsterS*0:wheel.speed.right').d = __getSpeed('HamsterS*0', 40)
        __('HamsterS*0:wheel.move').d = __getDistance('HamsterS*0', 5, 'cm')
        await __('HamsterS*0:wheel.!move').w()
        await asyncio.sleep(0.3)

        # 오른쪽 90도 회전
        await __turnDegreeRight('HamsterS*0', 90, True)
        await asyncio.sleep(0.3)
    __stopMove('HamsterS*0')
    return

async def loop():
    pass
```

## 예제 2: 장애물 회피 — 가까우면 후진 후 우회
```python
import asyncio

async def setup():
    # 초기 전진
    if __('HamsterS*0:wheel.move').d != 0:
        __('HamsterS*0:wheel.move').d = 0
    __('HamsterS*0:wheel.speed.left').d = __getSpeed('HamsterS*0', 30)
    __('HamsterS*0:wheel.speed.right').d = __getSpeed('HamsterS*0', 30)
    return

async def loop():
    # 장애물 감지
    if __('HamsterS*0:proximity.left').d > 60 or __('HamsterS*0:proximity.right').d > 60:
        # 경고 LED
        __('HamsterS*0:led.left').d = [255, 0, 0]
        __('HamsterS*0:led.right').d = [255, 0, 0]
        # 짧게 후진
        __('HamsterS*0:wheel.speed.left').d = __getSpeed('HamsterS*0', -30)
        __('HamsterS*0:wheel.speed.right').d = __getSpeed('HamsterS*0', -30)
        await asyncio.sleep(0.5)
        __stopMove('HamsterS*0')
        # 오른쪽으로 90도 회전 후 다시 전진
        await __turnDegreeRight('HamsterS*0', 90, True)
        __('HamsterS*0:wheel.speed.left').d = __getSpeed('HamsterS*0', 30)
        __('HamsterS*0:wheel.speed.right').d = __getSpeed('HamsterS*0', 30)
        # LED 초록 (정상 주행)
        __('HamsterS*0:led.left').d = [0, 255, 0]
        __('HamsterS*0:led.right').d = [0, 255, 0]
    return
```

## 예제 3: 신호등 만들기 (LED + 버저)
```python
import asyncio

async def setup():
    # 빨강 (3초, 멈춤)
    __('HamsterS*0:led.left').d = [255, 0, 0]
    __('HamsterS*0:led.right').d = [255, 0, 0]
    __('HamsterS*0:sound.buzz').d = 261.6   # 도
    await asyncio.sleep(0.3)
    __('HamsterS*0:sound.buzz').d = 0
    await asyncio.sleep(2.7)

    # 노랑 (1초, 주의)
    __('HamsterS*0:led.left').d = [255, 255, 0]
    __('HamsterS*0:led.right').d = [255, 255, 0]
    __('HamsterS*0:sound.buzz').d = 329.6   # 미
    await asyncio.sleep(0.3)
    __('HamsterS*0:sound.buzz').d = 0
    await asyncio.sleep(0.7)

    # 초록 (3초, 출발)
    __('HamsterS*0:led.left').d = [0, 255, 0]
    __('HamsterS*0:led.right').d = [0, 255, 0]
    __('HamsterS*0:sound.buzz').d = 392.0   # 솔
    await asyncio.sleep(0.3)
    __('HamsterS*0:sound.buzz').d = 0
    # 초록불 동안 전진
    if __('HamsterS*0:wheel.move').d != 0:
        __('HamsterS*0:wheel.move').d = 0
    __('HamsterS*0:wheel.speed.left').d = __getSpeed('HamsterS*0', 30)
    __('HamsterS*0:wheel.speed.right').d = __getSpeed('HamsterS*0', 30)
    await asyncio.sleep(2.7)
    __stopMove('HamsterS*0')
    # 끄기
    __('HamsterS*0:led.left').d = [0, 0, 0]
    __('HamsterS*0:led.right').d = [0, 0, 0]
    return

async def loop():
    pass
```

## 예제 4: 거리 이동으로 사각형 + 도착 시 LED·경고음
```python
import asyncio

async def setup():
    for i in range(4):
        # 10cm 전진 (속도 40)
        if __('HamsterS*0:wheel.move').d != 0:
            __('HamsterS*0:wheel.move').d = 0
        __('HamsterS*0:wheel.speed.left').d = __getSpeed('HamsterS*0', 40)
        __('HamsterS*0:wheel.speed.right').d = __getSpeed('HamsterS*0', 40)
        __('HamsterS*0:wheel.move').d = __getDistance('HamsterS*0', 10, 'cm')
        await __('HamsterS*0:wheel.!move').w()
        await asyncio.sleep(0.3)
        # 오른쪽 90도 회전
        await __turnDegreeRight('HamsterS*0', 90, True)
        await asyncio.sleep(0.3)
    __stopMove('HamsterS*0')
    # 도착 신호: 초록 LED + 짧은 경고음
    __('HamsterS*0:led.left').d = [0, 255, 0]
    __('HamsterS*0:led.right').d = [0, 255, 0]
    __('HamsterS*0:sound.buzz').d = 880.0
    await asyncio.sleep(0.2)
    __('HamsterS*0:sound.buzz').d = 0
    return

async def loop():
    pass
```

## 자주 하는 실수 체크리스트
1. ❌ `from roboid import *` / `import Hamster` 사용 → ✅ `import asyncio` 만
2. ❌ `HamsterS()` 인스턴스 생성 → ✅ `__('HamsterS*0:...')` 메타 접근자
3. ❌ 속도 설정 전에 `wheel.move` 리셋 안 함 → ✅ `if __('...wheel.move').d != 0: ...d = 0`
4. ❌ `time.sleep()` 사용 → ✅ `await asyncio.sleep()` (setup 또는 async loop 안에서)
5. ❌ 거리 이동 후 `!move.w()` 대기 안 함 → ✅ `await __('...wheel.!move').w()`
6. ❌ 속도에 단위(%, cm) 포함 → ✅ 숫자만 (-100~100)
7. ❌ 마지막에 `dispose()` 호출 → ✅ Block Composer는 필요 없음
8. ❌ 라인 트레이싱 / `wheel.trace.*` (trace.speed/gain/mode) 로 이동 → ✅ 이동은 무조건 거리 이동 블록(`wheel.move`+`__getDistance`+`!move`)과 `__turnDegreeLeft/Right` 만 사용 (말판 유무 무관)
""",
    },
]



# ─────────────────────────────────────────────────────────────
# RAGService 클래스
# ─────────────────────────────────────────────────────────────

class RAGService:
    """
    햄스터-S API 문서를 ChromaDB에 임베딩하고 검색하는 서비스.

    앱 시작 시 자동으로 DB를 빌드합니다.
    이미 빌드된 DB가 있으면 재사용합니다.
    """

    def __init__(self):
        self._client: chromadb.PersistentClient | None = None
        self._collection = None
        self._embeddings = None

    def _get_embeddings(self) -> GoogleGenerativeAIEmbeddings:
        """Google Generative AI 임베딩 모델 (지연 초기화)."""
        if self._embeddings is None:
            self._embeddings = GoogleGenerativeAIEmbeddings(
                model="models/gemini-embedding-001",  # 실제 사용 가능한 최신 모델
                google_api_key=settings.GEMINI_API_KEY,
                task_type="retrieval_document",
            )
        return self._embeddings

    def _get_client(self) -> chromadb.PersistentClient:
        """ChromaDB 클라이언트 (지연 초기화)."""
        if self._client is None:
            CHROMA_DIR.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(
                path=str(CHROMA_DIR),
                settings=ChromaSettings(anonymized_telemetry=False),
            )
        return self._client

    def build_db(self, force_rebuild: bool = False, platform: str = "robomation") -> None:
        """
        햄스터-S(로보메이션 Block Composer) API 문서를 임베딩해서 ChromaDB에 저장한다.
        platform 인자는 하위 호환을 위해 남겨 두었지만 로보메이션만 지원한다.
        """
        client = self._get_client()

        col_name = COLLECTION_NAME
        docs_list = HAMSTER_S_DOCS

        # 강제 재빌드 시 기존 컬렉션 삭제
        if force_rebuild:
            try:
                client.delete_collection(col_name)
                logger.info(f"기존 ChromaDB 컬렉션 삭제 완료 ({col_name})")
            except Exception:
                pass

        # 컬렉션 가져오기 (없으면 생성)
        collection = client.get_or_create_collection(
            name=col_name,
            metadata={"hnsw:space": "cosine"},
        )

        # 이미 문서가 있으면 재빌드 생략
        existing_count = collection.count()
        if existing_count >= len(docs_list) and not force_rebuild:
            logger.info(
                f"ChromaDB 이미 빌드됨 ({existing_count}개 청크, {col_name}). 건너뜁니다."
            )
            self._collection = collection
            return

        logger.info(f"ChromaDB 빌드 시작 ({len(docs_list)}개 문서, {col_name})...")

        # ── 문서 → 청크 분할 → 임베딩 ────────────────────────
        # 마크다운 헤더 기준으로 1차 분할
        md_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=[("#", "h1"), ("##", "h2"), ("###", "h3")],
            strip_headers=False,
        )
        # 길이 기준으로 2차 분할 (ChromaDB 토큰 한도 초과 방지)
        char_splitter = RecursiveCharacterTextSplitter(
            chunk_size=800,
            chunk_overlap=100,
            separators=["\n\n", "\n", "```", " "],
        )

        all_ids, all_docs, all_metas, all_embeddings = [], [], [], []

        for doc in docs_list:
            # 1차 마크다운 분할
            md_chunks = md_splitter.split_text(doc["content"])

            for i, chunk in enumerate(md_chunks):
                # chunk 는 Document 객체 or 문자열일 수 있음
                chunk_text = chunk.page_content if hasattr(chunk, "page_content") else str(chunk)

                # 2차 길이 분할
                sub_chunks = char_splitter.split_text(chunk_text)

                for j, sub_text in enumerate(sub_chunks):
                    if len(sub_text.strip()) < 20:
                        continue  # 너무 짧은 청크 제외

                    chunk_id = f"{doc['id']}__{i}_{j}"
                    all_ids.append(chunk_id)
                    all_docs.append(sub_text)
                    all_metas.append({
                        "source_id": doc["id"],
                        "title": doc["title"],
                        "chunk_index": f"{i}_{j}",
                    })

        # Google 임베딩 생성 (배치 처리)
        logger.info(f"  임베딩 생성 중... ({len(all_docs)}개 청크)")
        embeddings_model = self._get_embeddings()
        all_embeddings = embeddings_model.embed_documents(all_docs)

        # ChromaDB에 업서트 (배치 100개씩)
        BATCH = 100
        for start in range(0, len(all_ids), BATCH):
            end = min(start + BATCH, len(all_ids))
            collection.upsert(
                ids=all_ids[start:end],
                documents=all_docs[start:end],
                metadatas=all_metas[start:end],
                embeddings=all_embeddings[start:end],
            )
            logger.info(f"  업서트: {end}/{len(all_ids)}")

        self._collection = collection
        logger.info(f"ChromaDB 빌드 완료! 총 {collection.count()}개 청크 저장됨 ({col_name}).")

    def search(self, query: str, top_k: int = TOP_K, platform: str = "robomation") -> str:
        """
        행동 계획 또는 목표 텍스트를 쿼리로 관련 API 문서를 검색한다.
        platform 인자는 하위 호환용이며 로보메이션 Block Composer 문서만 검색한다.
        """
        if self._collection is None:
            self.build_db()
        collection = self._collection
        fallback = _FALLBACK_CONTEXT

        # 쿼리 임베딩 (retrieval_query 태스크 — 문서 임베딩과 태스크 분리)
        query_embedder = GoogleGenerativeAIEmbeddings(
            model="models/gemini-embedding-001",
            google_api_key=settings.GEMINI_API_KEY,
            task_type="retrieval_query",
        )
        query_embedding = query_embedder.embed_query(query)

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )

        # 결과 조합 및 필터링
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        if not docs:
            logger.warning(f"RAG 검색 결과 없음: query='{query[:50]}'")
            return fallback

        # 유사도 임계값 필터링 후 컨텍스트 문자열 구성
        context_parts = []
        for doc, meta, dist in zip(docs, metas, distances):
            if dist > (1 - MIN_RELEVANCE):  # cosine distance: 낮을수록 유사
                continue
            context_parts.append(
                f"## [{meta.get('title', '참고 문서')}]\n{doc}"
            )

        if not context_parts:
            return fallback

        context = "\n\n---\n\n".join(context_parts)
        logger.debug(f"RAG 검색: query='{query[:40]}', {len(context_parts)}개 청크 반환")
        return context


# ─────────────────────────────────────────────────────────────
# 폴백 컨텍스트 (ChromaDB 실패 시 사용)
# ─────────────────────────────────────────────────────────────
_FALLBACK_CONTEXT = """
## 햄스터-S Block Composer 기본 API (폴백)
```python
import asyncio

# put setup code here, to run once:
async def setup():
    # [바퀴 속도 설정 — 반드시 wheel.move 를 먼저 0으로 리셋]
    if __('HamsterS*0:wheel.move').d != 0:
        __('HamsterS*0:wheel.move').d = 0
    __('HamsterS*0:wheel.speed.left').d  = __getSpeed('HamsterS*0', 50)    # 왼쪽 바퀴 (-100~100)
    __('HamsterS*0:wheel.speed.right').d = __getSpeed('HamsterS*0', 50)    # 오른쪽 바퀴 (-100~100)
    await asyncio.sleep(2)                                                 # n초 대기
    __stopMove('HamsterS*0')                                               # 즉시 정지

    # [거리 이동 (cm)]
    __('HamsterS*0:wheel.move').d = __getDistance('HamsterS*0', 5, 'cm')
    await __('HamsterS*0:wheel.!move').w()    # 이동 완료까지 대기

    # [시간 이동 (초)]
    await __stopAfterDelay('HamsterS*0', 5, True)

    # [제자리 회전 — 각도 지정]
    await __turnDegreeLeft('HamsterS*0', 90, True)
    await __turnDegreeRight('HamsterS*0', 90, True)

    # [LED — [R, G, B], 각 0~255]
    __('HamsterS*0:led.left').d  = [255, 0, 0]    # 왼쪽 LED 빨강
    __('HamsterS*0:led.right').d = [0, 0, 255]    # 오른쪽 LED 파랑

    # [버저 — 주파수 Hz]
    __('HamsterS*0:sound.buzz').d = 392.0    # 솔(G4)
    await asyncio.sleep(0.5)
    __('HamsterS*0:sound.buzz').d = 0        # 음소거
    return

# put control code here, to run repeatedly:
async def loop():
    # [센서 읽기]
    left_prox  = __('HamsterS*0:proximity.left').d     # 왼쪽 근접 (0~255)
    right_prox = __('HamsterS*0:proximity.right').d    # 오른쪽 근접 (0~255)
    # [키보드] 38=↑, 40=↓, 37=←, 39=→, 32=space
    if __keypressed(32):
        __stopMove('HamsterS*0')
    return
```

⚠️ Block Composer 절대 규칙:
- `from roboid import *` / `import Hamster` / `HamsterS()` 인스턴스 생성 금지
- `time.sleep()` 대신 `await asyncio.sleep()` (setup 또는 async def loop 안에서만)
- `dispose()` 호출 금지
"""

# ── 싱글턴 인스턴스 ──────────────────────────────────────────
rag_service = RAGService()


# ─────────────────────────────────────────────────────────────
# 단독 실행: DB 빌드 스크립트 (로보메이션 Block Composer 전용)
#   python -m app.services.rag_service              # 증분 빌드
#   python -m app.services.rag_service --rebuild    # 강제 재빌드
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    force = "--rebuild" in sys.argv

    print(f"\n===== [robomation] {'강제 재빌드' if force else '증분 빌드'} 시작 =====")
    rag_service.build_db(force_rebuild=force)

    # 빌드 후 테스트 검색
    tests = [
        "장애물을 피해서 앞으로 이동하기",
        "10cm 전진 후 90도 회전",
        "LED를 빨간색으로 켜기",
        "안전하게 느린 속도로 이동",
        "키보드 화살표로 햄스터 조종하기",
        "앞으로 이동 후 회전하고 뒤로 이동",
    ]
    print(f"\n── [robomation] 테스트 검색 ──")
    for q in tests:
        result = rag_service.search(q, top_k=2)
        print(f"\n쿼리: {q}")
        print(f"결과 미리보기: {result[:200]}...")
