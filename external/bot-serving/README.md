# Bot Detection Inference API

FastAPI 기반의 봇 탐지 추론 서버입니다.  
현재 저장소는 FE(프론트엔드 행동 로그) 모델과 BE(백엔드 요청 패턴) 모델을 함께 서빙하며, 입력 feature를 받아 봇 확률(`bot_score`)과 최종 판정(`bot` / `human`)을 반환합니다.

## 1. 프로젝트 개요

이 프로젝트의 목적은 학습이 끝난 머신러닝 모델을 API 형태로 배포하여,
서비스 운영 환경에서 실시간 또는 준실시간으로 봇 여부를 판정할 수 있도록 만드는 것입니다.

핵심 포인트는 다음과 같습니다.

- FE 모델과 BE 모델을 분리하여 서로 다른 신호를 독립적으로 추론
- `scikit-learn Pipeline` 형태의 모델을 그대로 로드하여 전처리와 추론을 일관되게 수행
- `FastAPI` 기반으로 가볍고 빠른 추론 API 제공
- 헬스체크 엔드포인트를 통해 모델 로딩 상태 확인 가능
- Docker 이미지로 패키징 가능

## 2. 시스템 구성

서버는 시작 시 두 개의 피클 모델을 로드합니다.

- FE 모델: `models/fe_model.pkl`
- BE 모델: `models/be_model.pkl`

애플리케이션 동작 흐름은 아래와 같습니다.

1. 서버 부팅
2. 설정값 및 threshold 검증
3. FE / BE 모델 로드
4. 요청별 feature를 `DataFrame`으로 변환
5. `predict_proba()`로 봇 확률 계산
6. threshold 기준으로 `bot` 또는 `human` 라벨 결정
7. 운영 식별자와 함께 응답 반환

## 3. 프로젝트 구조

```text
bot_serving/
├── app/
│   ├── config.py         # 환경설정, 모델 경로, threshold, feature 컬럼 정의
│   ├── main.py           # FastAPI 앱과 엔드포인트
│   ├── model_loader.py   # 모델 파일 검증 및 로딩
│   ├── predictor.py      # 예측 점수 및 라벨 계산
│   └── schemas.py        # 요청/응답 스키마
├── models/
│   ├── fe_model.pkl      # FE 추론 모델
│   └── be_model.pkl      # BE 추론 모델
├── Dockerfile
├── requirements.txt
└── README.md
```

## 4. 기술 스택

- Python 3.13
- FastAPI
- Uvicorn
- Pydantic v2
- pandas
- scikit-learn
- joblib
- xgboost
- catboost
- Docker

## 5. 핵심 모듈 설명

### `app/config.py`

프로젝트 전역 설정을 관리합니다.

- 모델 파일 경로
- API 제목 / 버전
- FE / BE threshold
- bot class index
- FE / BE feature 컬럼 정의

### `app/model_loader.py`

모델 적재 단계에서 아래 항목을 검증합니다.

- 파일 존재 여부
- `sklearn Pipeline` 형식 여부
- `preprocessor`, `model` step 존재 여부
- 기대 feature 컬럼과 실제 컬럼 일치 여부
- `predict_proba()` 지원 여부

즉, 잘못된 모델이 배포되는 상황을 사전에 차단하는 역할을 합니다.

### `app/predictor.py`

입력 feature를 `pandas.DataFrame`으로 구성한 뒤 `predict_proba()`를 호출하여 `bot_score`를 계산합니다.  
이 점수가 threshold 이상이면 `bot`, 미만이면 `human`으로 판정합니다.

### `app/schemas.py`

Pydantic 기반 요청/응답 스키마를 정의합니다.

- 잘못된 필드 입력 차단
- 음수 입력 방지
- 필수 문자열 공백 검사
- API 문서 자동화

### `app/main.py`

실제 API 엔드포인트를 제공합니다.

- `GET /health`
- `POST /predict/fe`
- `POST /predict/be`

## 6. 입력 Feature 정의

### FE 모델 입력

- `duration_ms`
- `mousemove_teleport_count`
- `mousemove_count`

운영 식별자는 함께 받지만 모델 입력에는 직접 넣지 않습니다.

- `X-Session-Ticket`
- `showScheduleId`

### BE 모델 입력

- `ts_payment_ready`
- `ts_whole_session`
- `req_interval_cv_pre_hold`
- `req_interval_cv_hold_gap`

운영 식별자는 함께 받지만 모델 입력에는 직접 넣지 않습니다.

- `X-User-Id`
- `orderId`

## 7. API 명세

### 7-1. Health Check

`GET /health`

응답 예시:

```json
{
  "status": "ok",
  "fe_loaded": true,
  "be_loaded": true,
  "fe_model_path": "models/fe_model.pkl",
  "be_model_path": "models/be_model.pkl"
}
```

### 7-2. FE 예측 API

`POST /predict/fe`

요청 예시:

```json
{
  "X-Session-Ticket": "session_abc123",
  "showScheduleId": 101,
  "duration_ms": 5320,
  "mousemove_teleport_count": 7,
  "mousemove_count": 21
}
```

응답 예시:

```json
{
  "model_type": "fe",
  "label": "bot",
  "bot_score": 0.913245,
  "threshold": 0.5,
  "model_name": "XGBClassifier",
  "X-Session-Ticket": "session_abc123",
  "showScheduleId": 101
}
```

### 7-3. BE 예측 API

`POST /predict/be`

요청 예시:

```json
{
  "X-User-Id": "user_1001",
  "orderId": "order_20260410_001",
  "ts_payment_ready": 1.7,
  "ts_whole_session": 9.3,
  "req_interval_cv_pre_hold": 0.18,
  "req_interval_cv_hold_gap": 0.07
}
```

응답 예시:

```json
{
  "model_type": "be",
  "label": "human",
  "bot_score": 0.214587,
  "threshold": 0.5,
  "model_name": "CatBoostClassifier",
  "X-User-Id": "user_1001",
  "orderId": "order_20260410_001"
}
```

## 8. 실행 방법

### 8-1. 로컬 실행

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

실행 후 접속:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- Health Check: `http://localhost:8000/health`

### 8-2. Docker 실행

```bash
docker build -t bot-serving .
docker run -p 8000:8000 bot-serving
```

## 9. 환경변수

기본값이 코드에 들어 있어 별도 설정 없이도 실행할 수 있지만, 운영 환경에서는 아래 값을 환경변수로 주입할 수 있습니다.

| 변수명 | 기본값 | 설명 |
|---|---|---|
| `FE_MODEL_PATH` | `models/fe_model.pkl` | FE 모델 파일 경로 |
| `BE_MODEL_PATH` | `models/be_model.pkl` | BE 모델 파일 경로 |
| `API_TITLE` | `Bot Detection Inference API` | FastAPI 문서 제목 |
| `API_VERSION` | `1.0.0` | API 버전 |
| `FE_THRESHOLD` | `0.5` | FE 봇 판정 기준 |
| `BE_THRESHOLD` | `0.5` | BE 봇 판정 기준 |
| `BOT_CLASS_INDEX` | `1` | `predict_proba()`에서 봇 클래스 인덱스 |

예시:

```bash
export FE_THRESHOLD=0.6
export BE_THRESHOLD=0.7
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## 10. 핵심 정리

### 문제 정의

- 서비스 운영 과정에서 봇 트래픽을 빠르게 탐지할 필요가 있음
- FE 행동 로그와 BE 요청 패턴은 서로 다른 탐지 신호를 제공함

### 해결 방식

- 학습 완료된 모델을 API 서버로 배포
- FE / BE 모델을 분리 서빙
- 확률 기반 점수와 최종 판정을 함께 반환

### 장점

- 모델 교체가 쉬움
- 입력 검증이 명확함
- 운영 시스템과 연동이 쉬움
- Docker 기반 배포 가능

## 11. 향후 개선 아이디어

- 추론 로그 저장 및 모니터링
- 요청 이력 기반 누적 리스크 스코어링
- threshold 환경별 분리 운영
- 인증 / 인가 추가
- batch 추론 API 추가
- 모델 버전 관리 체계화

## 12. GitHub 업로드 명령

현재 이 저장소의 원격 저장소는 아래와 같습니다.

`origin = https://github.com/kim-daehyun/bot-serving.git`

가장 기본적인 업로드 순서는 아래와 같습니다.

```bash
git status
git add README.md
git commit -m "docs: improve README for presentation"
git push origin main
```

만약 README뿐 아니라 전체 변경사항을 함께 올릴 경우:

```bash
git status
git add .
git commit -m "update project files"
git push origin main
```

참고로 현재 작업 트리에는 `.DS_Store`와 모델 파일 변경도 보이므로, 불필요한 macOS 숨김 파일은 제외하고 올리는 것을 권장합니다.

예시:

```bash
git add README.md app Dockerfile requirements.txt models/*.pkl
git commit -m "docs: improve README and update serving assets"
git push origin main
```
