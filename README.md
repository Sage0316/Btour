# 📦 Unboxing Seoul (언박싱 서울)

## Choose a mood, not a destination.

A blind-trip planner for international visitors to Seoul. Travelers choose a mood, follow clues to secret stops, and discover each destination only when they arrive.

**NVIDIA 해커톤 · 팀 투니버스** — 윤지혜(팀장), 이정후

## Why this matters

Seoul offers endless places to explore, but international visitors often face choice overload and information fatigue. Unboxing Seoul hands those decisions to AI, leaving travelers with the excitement of discovery.

## Built with NVIDIA

- **Nemotron** scores custom moods and writes multilingual, spoiler-free clues.
- **Nemotron vision** checks photo missions before each reveal.
- **cuOpt** plans time-aware routes, replans when travelers run late, and solves the two-team race as a 2-vehicle VRP. Six GPU test cases passed, including the race.

## Demo video

[![Watch the Unboxing Seoul demo](https://i.ytimg.com/vi/XpnAdOh8B7M/hqdefault.jpg)](https://youtu.be/XpnAdOh8B7M)

## How it works

1. Choose a mood, trip time, and starting area.
2. Follow a clue and directions toward one secret stop at a time.
3. Arrive, complete an optional photo mission, and unbox the destination.
4. Continue the route or replan if running late; finish with a stamped travel passport.

## 기능

### 테마

12개 프리셋 또는 자유 문장 무드: Healing · Landmarks · Foodie · Traditional · K-Culture · Night Views · Date & Romance · Photo Spots · Shopping · Rainy Day · Family & Kids · K-Drama Spots

### 경로 옵션 (Add to my route)

- 식당·카페 1곳: 점심(11:30–14:00)/저녁(17:30–20:30)에 1시간 이상 걸치면 그 시간대 식당·시장, 아니면 카페. Foodie 테마에선 숨김(식당 최대 2 + 카페 1).
- 액티비티 1곳: 시티투어버스(주간/야경), 한강 유람선, 한복 대여, 남산 케이블카, 롯데월드, 한강 자전거, 코인노래방.

두 옵션 모두 경로 안에 Secret Stop으로 끼워 넣는다.

### 스톱 카드

- **What's waiting for you** — 도착하면 눈에 보이는 것 2가지를 쉬운 말로(장소명·동네명·"가장 오래된" 같은 표현 금지). Hard 난이도만 시적인 수수께끼.
- **How to get there** — ① 구글맵은 근처 역(또는 200 m 앞 지점)까지만 → ② "I'm in the area"를 누르면 도보 안내(23곳은 직접 쓴 안내, 나머지는 방향·거리) → ③ 못 찾으면 정확한 위치를 구글맵으로. 800 m 이내 구간은 바로 도보 안내.
- 구글맵에는 항상 **현재 스톱 하나만** 넘긴다. 다음 스톱은 지금 스톱을 공개해야 생긴다.

### 게임 요소

- 힌트 난이도: Easy(장소 종류·거리 추가 힌트) / Medium / Hard(스톱 종류 배지 숨김).
- 사진 미션: 도착 후 "전통적인 무언가를 찍어보세요"처럼 **장소를 스포일러하지 않는** 미션을 통과해야 공개. 비전 모델이 판정.
- 두 팀 레이스: 같은 숙소에서 출발해 겹치지 않는 비밀 경로로 이동, **같은 비밀 만남 장소**에서 합류. 먼저 도착한 팀 기록.
- 여행 여권: 완주하면 스톱마다 도장이 찍힌 여권 카드.

### 여행 중

- Running late?: 늦은 만큼 남은 스톱을 현재 위치에서 다시 최적화(목적지는 계속 비밀).
- Lost? Peek: 확인 후 현재 목적지만 미리 보기.
- 자동 저장: 버튼을 누를 때마다 로컬 `.trips/`에 저장, 주소의 `?trip=<id>`로 새로고침·앱 전환 후에도 이어짐, 첫 화면 "Continue your last trip".
- 힌트 음성 읽기(선택한 언어), 날씨 반영(비 예보 시 실내 우선, 사이드바에서 비 시뮬레이션), 공개 카드에 K-드라마 촬영작 표시.

## 실행

```bash
git clone https://github.com/Sage0316/Btour.git && cd Btour
python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt
.venv/bin/streamlit run app.py        # 이 폴더에서 실행해야 테마 설정(.streamlit/config.toml)이 적용됨
```

- **NVIDIA API 키** ([build.nvidia.com](https://build.nvidia.com)에서 발급, 없어도 동작): `NVIDIA_API_KEY=nvapi-...`를
  환경변수로 주거나, `app.py` 옆 `.env` 파일에 한 줄로 저장한다. `.env`는 git에 올라가지 않는다.
- 키가 없으면 테마 태그 점수 + 직접 작성한 영어 힌트로 동작하고, 키가 있으면 Nemotron이 켜진다.
- 같은 와이파이의 폰에서는 `http://<노트북 IP>:8501`로 접속한다(실행 시 터미널의 Network URL).
- 코드를 고친 뒤에는 Streamlit을 재시작해야 반영된다.

## 구조

| 파일 | 역할 |
|---|---|
| `app.py` | Streamlit UI: 설정 → 스톱 카드(힌트·길찾기) → 도착(사진 미션) → 공개 → 여권, 자동 저장·복원 |
| `ui.py`, `.streamlit/config.toml` | 디자인: 크림 캔버스, 파스텔 스톱 카드(스톱마다 색 순환), Inter, 둥근 모서리, 클레이풍 히어로 일러스트 |
| `planner.py` | 동선 최적화: Prize-collecting TSP with time windows, 그룹 제약, 재계획, 2팀 VRP (cuOpt / CPU exact DP) |
| `llm.py` | Nemotron: 무드 → 장소 점수, 다국어·난이도별 힌트(병렬), 스포일러·언어 검사, 사진 미션 판정 |
| `weather.py` | Open-Meteo 예보(키 불필요)로 여행 시간대 강수 확률·기온 |
| `data/seoul_pois.json` | 서울 54곳: 명소·액티비티·식당·카페·시장, 역 기준 도보 안내 23곳 (좌표는 OpenStreetMap으로 교차 확인) |
| `cuopt_check.py` | GPU 머신에서 cuOpt vs CPU 결과 비교 + 성공 여부 요약 |

## NVIDIA 기술이 들어가는 곳

1. **Nemotron (build.nvidia.com NIM API)**
   - 힌트·장소 설명·도보 안내 번역: `nvidia/nemotron-3-super-120b-a12b` (예비: `nemotron-3.5-lightning-30b-a3b`)
   - 자유 문장 무드("rainy day, solo, I love tea and old books") → 전체 장소 점수(0–10). 기본 테마는 태그 점수로 충분해 생략.
   - 사진 미션 판정: `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` (혼잡 시 `meta/llama-3.2-11b-vision-instruct`)
   - 속도: `chat_template_kwargs.enable_thinking=false`로 추론 과정을 꺼서 응답 1–3초(켜 두면 70초+).
     첫 스톱 힌트만 받고 출발하고, 나머지는 이동 중 백그라운드에서 병렬 생성. 429/503(혼잡)이면 같은 모델로 1회 재시도.
2. **cuOpt**
   - 1인 여행: 장소 점수 = prize, 영업시간 = time window, 체류시간 = service time, 여행 시간 = vehicle time window.
     식당/액티비티 옵션은 그룹별 capacity dimension(최대 1곳) + 큰 prize(사실상 필수).
   - 레이스 모드: **차량 2대 VRP** — 두 차량이 같은 출발점에서 나가 같은 만남 장소로 복귀(`set_vehicle_locations`, `set_min_vehicles(2)`).
   - 재계획: 현재 위치·시각에서 남은 시간으로 다시 풂.
   - **GPU 검증 완료**: Linux + NVIDIA GPU에서 `cuopt_check.py`의 6개 케이스(1인 여행 5개 + 두 팀 레이스)를 모두 cuOpt가 해결.
     레이스는 약 3초(솔버 시간 제한) 만에 두 팀 경로를 동시에 산출했고, CPU 정확해와 같은 경로임을 확인.
   - GPU가 없으면 CPU 비트마스크 DP로 자동 대체(정확하지만 후보 12곳까지 현실적, 레이스는 팀 A→B 순차 드래프트로 근사).
   - 구현 시 NVIDIA Agent Skills(`cuopt-routing-api-python`, `cuopt-install`)를 참고했다.

## cuOpt를 GPU에서 돌리기 (Linux + NVIDIA GPU, Volta 이상)

```bash
nvidia-smi                                   # 오른쪽 위 CUDA Version 확인
source .venv/bin/activate
python -m pip install --extra-index-url=https://pypi.nvidia.com cuopt-cu12   # CUDA 13이면 cuopt-cu13
python cuopt_check.py                        # 맨 아래 SUMMARY에서 ✅/❌ 확인
```

- cuOpt는 RAPIDS(cuDF 등)를 함께 설치해서 **수 GB**를 받는다. 리눅스 전용(윈도우는 WSL2).
- 사이드바 "Route solver"에서 `cuopt`를 고르면 cuOpt를 쓰고, 없으면 CPU로 자동 대체된다(Judge mode에 표시).

## 3분 데모 시나리오

1. **문제 (20초)**: "서울 온 외국인은 어디 갈지 고르는 데서 지친다. 결정은 AI에게 맡기고 설렘만 즐기자."
2. **설정 (20초)**: `🌿 Healing & Slow` + 🍽️·🎟️ 토글 ON, 언어 日本語, 📷 사진 미션 ON. 날짜는 화요일 이후(시티투어버스 월요일 휴무). 기본 테마로 시연하면 약 6초 만에 출발.
3. **블라인드 진행 (60초)**: 🔒 What's waiting → 🔊 읽기 → 🧭 구글맵으로 역까지 → 🚶 I'm in the area → 도보 안내 → 📍 unbox it! → 📷 사진 미션 → 📦 공개(한글 이름·🎬 드라마).
4. **돌발 상황 (30초)**: ⏰ "30분 늦었어요" → 남은 동선 재최적화, 사이드바 🌧️ 비 시뮬레이션으로 실내 위주 경로.
5. **Judge mode + 레이스 (30초)**: 점수표·후보·솔버 표시, 🏁 두 팀 레이스로 cuOpt 2-vehicle VRP 소개.
6. **마무리 (20초)**: 🛂 여행 여권, 확장 계획(실시간 GPS, 경로 API, 음성 가이드, 전국 확장).

## 알려진 한계

- 이동시간은 직선거리 기반 추정치(1.2 km 이하는 도보, 그 이상은 지하철). 실서비스는 경로 API로 교체 필요.
- 영업시간·휴무일은 대략값. 공휴일·계절 운영(예: 반포 분수 4–10월)은 미반영.
- 시티투어버스·유람선 등 출발 시각이 정해진 액티비티는 "도착 가능 시간대"로 근사.
- 직접 쓴 도보 안내(방향·거리)는 지도 기준으로 작성했고 현장에서 걸어 보며 검증하지는 않았다.
- 식당은 미쉐린/블루리본 노포 위주. 예약 필수 파인다이닝(밍글스, 정식당, 온지음)은 워크인 동선과 맞지 않아 제외.
- K-드라마 촬영지는 여행 가이드(Pelago 등) 기준이며 장면 단위로 검증하지는 않았다.
- 자유 문장 무드는 Nemotron 장소 점수 계산 때문에 출발까지 약 30초 더 걸린다.
- 음성 읽기는 브라우저 내장 음성(Web Speech API)이라 기기에 해당 언어 음성이 있어야 한다.
- 카메라 토글은 HTTPS 또는 localhost에서만 동작한다. 폰에서는 "Upload a photo"로 카메라 촬영이 가능하다.
- 구글맵은 좌표만 받아도 도착지 주소를 표시해 장소가 드러날 수 있다(그래서 역까지만 안내). 한국에서는 구글맵 도보·자동차 길찾기가 제한적이라 대중교통 모드를 쓴다.
- 스포일러 가드는 영문명·한글명 문자열만 검사한다. 일본어·중국어 표기(예: 景福宮)는 걸러내지 못한다.
- 자동 저장은 서버 로컬 파일이라 같은 서버를 쓰는 사람에게 "Continue your last trip"이 보일 수 있다(데모용).
