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

## 테마 & 경로 옵션

- **테마**: 🌿 Healing · 🏙️ Landmarks · 🍜 Foodie · 🏯 Traditional · 🎤 K-Culture · 🌃 Night Views (+ 자유 문장 무드)
- **Add to my route** (경로 안에 Secret Stop으로 끼워 넣음, 옵티마이저가 위치·시간에 맞는 곳을 고름)
  - 🍽️ 식당·카페 1곳: 여행이 점심(11:30–14:00)/저녁(17:30–20:30)에 1시간 이상 걸치면 그 시간대에 식당·시장, 아니면 카페. Foodie 테마에선 숨김 (식당 최대 2 + 카페 1).
  - 🎟️ 액티비티 1곳: 시티투어버스(주간/야경), 한강 유람선, 한복 대여, 남산 케이블카, 롯데월드, 한강 자전거, 코인노래방
- 식당·카페·액티비티는 옵션을 켰을 때만 경로에 들어간다(Foodie 테마의 식당·카페 제외).

## 구조

| 파일 | 역할 |
|---|---|
| `app.py` | Streamlit UI: 무드 선택 → 비밀 스톱 카드 → 길안내 → 도착 시 공개 |
| `ui.py`, `.streamlit/config.toml` | 디자인 시스템: 크림 캔버스, 6색 컬러 카드(스톱마다 순환), Inter, 둥근 모서리, 클레이풍 히어로 일러스트 |
| `planner.py` | 동선 최적화: **Prize-collecting TSP with time windows** (cuOpt / CPU exact DP) |
| `llm.py` | Nemotron: 자유 문장 무드 → 장소 점수, 다국어 수수께끼 힌트, 스포일러 가드 |
| `data/seoul_pois.json` | 서울 51곳: 명소 30, 액티비티 8, 식당 7, 카페 4, 시장 2 (좌표는 OpenStreetMap으로 교차 확인) |
| `cuopt_check.py` | GPU 머신에서 cuOpt vs CPU 결과 비교 |

## NVIDIA 기술이 들어가는 곳

1. **Nemotron (build.nvidia.com)**
   - "rainy day, solo, I love tea and old books" 같은 자유 문장을 전체 장소 점수(0–10)로 변환
   - 선택된 동선에 대해 여행자 언어(영/일/중/스/프/한)로 **이름을 말하지 않는** 힌트 생성
   - 생성된 힌트에 장소명이 섞이면 자동으로 큐레이션 힌트로 교체 (스포일러 가드)
2. **cuOpt**: 각 장소 점수를 prize로, 영업시간을 time window로, 체류시간을 service time으로,
   여행 시간 예산을 vehicle time window로 넣고 "어디를 갈지 + 어떤 순서로 갈지"를 한 번에 푼다.
   식당/액티비티 옵션은 그룹별 capacity dimension(최대 1곳) + 큰 prize(사실상 필수)로 표현한다.
   - CPU 대체 경로(비트마스크 DP)는 정확하지만 후보 12곳까지만 현실적이다.
   - cuOpt는 전체 후보를 다 넣고 풀 수 있어서, 도시 전체 카탈로그와 여러 여행자로 확장할 수 있다.

## cuOpt를 GPU에서 돌리기 (Colab T4 / Brev)

```bash
pip install --extra-index-url=https://pypi.nvidia.com 'cuopt-cu12==26.2.*' requests
python cuopt_check.py          # CPU vs cuOpt 결과 비교 출력
```

앱 사이드바의 "Route solver"에서 `cuopt`를 고르면 cuOpt를 쓴다. 설치돼 있지 않으면 CPU로 자동 대체되고,
Judge mode에 그 사실이 표시된다. cuOpt 코드는 공식 API(`set_order_prizes`, `set_order_time_windows`,
`set_drop_return_trips` 등)로 작성했지만 **GPU에서 아직 실행해 보지 않았다.** 데모 전에 `cuopt_check.py`로 꼭 확인할 것.

## 3분 데모 시나리오

1. **문제 (20초)**: "서울 온 외국인은 어디 갈지 고르는 데서 지친다. 결정은 AI에게 맡기고 놀라움만 즐기자."
2. **무드 입력 (30초)**: `🌿 Healing & Slow` 선택 + 🍽️ 식당, 🎟️ 액티비티 토글 ON, 숙소 Myeongdong, 언어 日本語.
   날짜는 화요일 이후로 (시티투어버스는 월요일 휴무).
3. **플래닝 (20초)**: 상태창에 "Nemotron이 장소를 읽는 중 → 동선 최적화 → 힌트 작성" 순서가 보인다.
4. **블라인드 진행 (60초)**: 🔒 Secret Stop 1의 힌트를 보여주고 Kakao Map 버튼을 누른다. 지도에는 "Secret Stop 1"로만 표시된다. 이어서 📍 도착 버튼을 눌러 이름을 공개한다(한글 이름은 현지인에게 보여주는 용도).
5. **Judge mode (40초)**: 사이드바 토글로 점수표, 후보 목록, 사용한 경로 계산 방식과 소요 시간, 전체 동선 지도를 보여준다.
6. **확장 (10초)**: 음성 가이드(Nemotron Speech), 실시간 GPS, 전국 확장.

## 알려진 한계

- 이동시간은 직선거리 기반 추정치다(1.2 km 이하는 도보, 그 이상은 지하철로 계산). 실서비스에서는 카카오모빌리티 같은 경로 API로 바꿔야 한다.
- 영업시간과 휴무일은 대략값이다. 공휴일과 계절 운영(예: 반포 분수는 4–10월)은 반영하지 않았다.
- 시티투어버스·유람선처럼 정해진 출발 시각이 있는 액티비티는 "도착 가능 시간대"로 근사했다(출발 대기 시간 미반영).
- 식당은 미쉐린/블루리본 등 오래된 유명 노포 위주. 예약 필수 파인다이닝(밍글스, 정식당, 온지음)은
  워크인 블라인드 동선과 맞지 않아 제외했다.
- Google Maps는 좌표만 넘겨도 주소를 표시해서 장소가 드러날 수 있다. Kakao Map 링크는 라벨을 "Secret Stop N"으로 덮는다.
- 스포일러 가드는 영문명과 한글명 문자열만 검사한다. 일본어나 중국어 표기(예: 景福宮)는 걸러내지 못한다.
