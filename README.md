# Xi S&D 맛집 정보 시스템 (Restaurant Map)

회사 근처(남산스퀘어) 맛집을 공유하고 랜덤으로 점심 메뉴를 추천받을 수 있는 스트림릿 애플리케이션입니다.

## 기능
- **맛집 지도**: 등록된 맛집 위치 확인 및 필터링 (한식, 중식, 일식 등)
- **맛집 리스트**: 전체 맛집 목록 및 상세 정보 (평점, 리뷰, 추천 메뉴)
- **랜덤 추천**: 점심 메뉴 고민 해결을 위한 룰렛 기능
- **맛집 등록**: 새로운 맛집을 직접 등록하고 공유

## 실행 방법
1. 가상환경 생성 및 패키지 설치:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. 앱 실행:
   ```bash
   streamlit run app.py
   ```

## 주의사항
- API Key가 포함되어 있으므로 **Private Repository**로 유지하는 것을 권장합니다.
