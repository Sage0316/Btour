# 🙈 Seoul Blind Trip

외국인 관광객이 **무드(테마)만 고르면**, AI가 목적지를 숨긴 채 서울 동선을 짜주고
사용자는 힌트와 지도만 보고 따라가는 "블라인드 여행" 데모.

## 실행

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # 이 폴더에서 실행해야 테마 설정이 적용됨
export NVIDIA_API_KEY=nvapi-...        # build.nvidia.com 에서 발급 (없어도 동작)
.venv/bin/streamlit run app.py
```

키가 없으면 테마 태그 점수 + 직접 작성한 영어 힌트로 동작하고, 키가 있으면 Nemotron이 켜진다.
`ui.py`·`planner.py` 등을 고친 뒤에는 Streamlit을 재시작해야 반영된다.

## 기능

**테마 (12개 + 자유 문장 무드)**
🌿 Healing · 🏙️ Landmarks · 🍜 Foodie · 🏯 Traditional · 🎤 K-Culture · 🌃 Night Views ·
💑 Date & Romance · 📸 Photo Spots · 🛍️ Shopping · 🌧️ Rainy Day · 👨‍👩‍👧 Family & Kids · 🎬 K-Drama Spots

**경로 옵션 (Add to my route)** — 경로 안에 Secret Stop으로 끼워 넣음
- 🍽️ 식당·카페 1곳: 점심(11:30–14:00)/저녁(17:30–20:30)에 1시간 이상 걸치면 그 시간대 식당·시장, 아니면 카페. Foodie 테마에선 숨김(식당 최대 2 + 카페 1).
- 🎟️ 액티비티 1곳: 시티투어버스(주간/야경), 한강 유람선, 한복 대여, 남산 케이블카, 롯데월드, 한강 자전거, 코인노래방

**게임 요소**
- 🧩 힌트 난이도: Easy(장소 종류·거리 추가 힌트) / Medium / Hard(스톱 종류 배지 숨김, 더 어려운 수수께끼)
- 📷 사진 미션: 도착 후 "전통적인 무언가를 찍어보세요"처럼 **장소를 스포일러하지 않는** 미션을 통과해야 공개. NVIDIA 비전 모델이 사진 판정.
- 🏁 두 팀 레이스: 같은 숙소에서 출발해 서로 겹치지 않는 비밀 경로로 이동, **같은 비밀 만남 장소**에서 합류. 먼저 도착한 팀 기록.
- 🛂 여행 여권: 완주하면 스톱마다 도장이 찍힌 여권 카드

**여행 중**
- ⏰ Running late?: 늦은 만큼 남은 스톱을 현재 위치에서 다시 최적화(목적지는 계속 비밀)
- 🆘 Lost? Peek: 확인 후 현재 목적지만 미리 보기
- 🔊 힌트 음성 읽기(선택한 언어), 🌦️ 날씨 반영(비 예보 시 실내 우선, 사이드바에서 비 시뮬레이션 가능)
- 🎬 공개 카드에 촬영된 K-드라마 표시

## 구조

| 파일 | 역할 |
|---|---|
| `app.py` | Streamlit UI: 설정 → 비밀 스톱 카드 → 길안내 → 도착(미션) → 공개 → 여권 |
| `ui.py`, `.streamlit/config.toml` | 디자인 시스템: 크림 캔버스, 6색 컬러 카드(스톱마다 순환), Inter, 둥근 모서리, 클레이풍 히어로 일러스트 |
| `planner.py` | 동선 최적화: Prize-collecting TSP with time windows, 그룹 제약, 재계획, 2팀 VRP (cuOpt / CPU exact DP) |
| `llm.py` | Nemotron: 무드 → 장소 점수, 다국어·난이도별 힌트, 스포일러 가드, 사진 미션 판정 |
| `weather.py` | Open-Meteo 예보(키 불필요)로 여행 시간대 강수 확률·기온 |
| `data/seoul_pois.json` | 서울 54곳: 명소·액티비티·식당·카페·시장 (좌표는 OpenStreetMap으로 교차 확인) |
| `cuopt_check.py` | GPU 머신에서 cuOpt vs CPU 결과 비교 |

## NVIDIA 기술이 들어가는 곳

1. **Nemotron (build.nvidia.com)**
   - 자유 문장 무드("rainy day, solo, I love tea and old books")를 전체 장소 점수(0–10)로 변환
   - 여행자 언어(영/일/중/스/프/한)·난이도에 맞춰 **이름을 말하지 않는** 힌트 생성, 장소명이 섞이면 큐레이션 힌트로 교체
   - 사진 미션 판정: `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` (실패 시 `meta/llama-3.2-11b-vision-instruct`)
2. **cuOpt**
   - 1인 여행: 장소 점수 = prize, 영업시간 = time window, 체류시간 = service time, 여행 시간 = vehicle time window.
     식당/액티비티 옵션은 그룹별 capacity dimension(최대 1곳) + 큰 prize(사실상 필수).
   - 레이스 모드: **차량 2대 VRP** — 두 차량이 같은 출발점에서 나가 같은 만남 장소로 복귀(`set_vehicle_locations`, `set_min_vehicles(2)`).
   - 재계획: 현재 위치·시각에서 남은 시간으로 다시 풂.
   - CPU 대체(비트마스크 DP)는 정확하지만 후보 12곳까지만 현실적이고, 레이스는 팀 A→B 순차 드래프트로 근사한다.

## cuOpt를 GPU에서 돌리기 (Colab T4 / Brev)

```bash
pip install --extra-index-url=https://pypi.nvidia.com 'cuopt-cu12==26.2.*' requests
python cuopt_check.py          # CPU vs cuOpt 결과 비교 출력
```

사이드바 "Route solver"에서 `cuopt`를 고르면 cuOpt를 쓴다. 없으면 CPU로 자동 대체되고 Judge mode에 표시된다.
cuOpt 코드는 공식 API로 작성했지만 **GPU에서 아직 실행해 보지 않았다.** 데모 전에 `cuopt_check.py`로 꼭 확인할 것.

## 3분 데모 시나리오

1. **문제 (20초)**: "서울 온 외국인은 어디 갈지 고르는 데서 지친다. 결정은 AI에게 맡기고 놀라움만 즐기자."
2. **무드 입력 (30초)**: `🌿 Healing & Slow` + 🍽️·🎟️ 토글 ON, 언어 日本語, 난이도 Easy, 📷 사진 미션 ON. 날짜는 화요일 이후(시티투어버스 월요일 휴무).
3. **플래닝 (20초)**: 상태창에 "Nemotron이 장소를 읽는 중 → 동선 최적화 → 힌트 작성".
4. **블라인드 진행 (50초)**: 🔒 힌트 → 🔊 읽기 → Google Maps(현재 위치에서 대중교통 길안내) → 📍 도착 → 📷 사진 미션 → 공개(한글 이름·🎬 드라마).
5. **돌발 상황 (30초)**: ⏰ "30분 늦었어요" → 남은 동선 재최적화, 사이드바 🌧️ 비 시뮬레이션으로 실내 위주 경로.
6. **Judge mode + 레이스 (30초)**: 점수표·후보·솔버 표시, 🏁 두 팀 레이스로 cuOpt 2-vehicle VRP 소개.

## 알려진 한계

- 이동시간은 직선거리 기반 추정치(1.2 km 이하는 도보, 그 이상은 지하철). 실서비스는 경로 API로 교체 필요.
- 영업시간·휴무일은 대략값. 공휴일·계절 운영(예: 반포 분수 4–10월)은 미반영.
- 시티투어버스·유람선 등 출발 시각이 정해진 액티비티는 "도착 가능 시간대"로 근사.
- 식당은 미쉐린/블루리본 노포 위주. 예약 필수 파인다이닝(밍글스, 정식당, 온지음)은 워크인 동선과 맞지 않아 제외.
- K-드라마 촬영지는 여행 가이드(Pelago 등) 기준이며 장면 단위로 검증하지는 않았다.
- 음성 읽기는 브라우저 내장 음성(Web Speech API)이라 기기에 해당 언어 음성이 있어야 한다. NVIDIA Riva/Nemotron Speech는 추후 과제.
- 카메라는 HTTPS 또는 localhost에서만 동작한다(폰으로 시연하려면 HTTPS 배포 필요). 사진 업로드는 어디서나 가능.
- 길안내는 외국인이 주로 쓰는 Google Maps(대중교통)만 사용. 좌표만 넘기지만 Google Maps가 도착지 주소를 표시해 장소가 드러날 수 있다. 한국에서는 Google Maps 도보·자동차 길찾기가 제한적이다.
- 스포일러 가드는 영문명·한글명 문자열만 검사한다. 일본어·중국어 표기(예: 景福宮)는 걸러내지 못한다.
