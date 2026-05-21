# Metrics 아키텍처

6개 채점 서비스를 **담당 폴더 단위로 분리**하고, **`POST /video/analyze` 한 곳**에서 **비동기 병렬** 실행 후 결과를 합친다.

| 문서 | 내용 |
|------|------|
| [ARCHITECTURE.md](./ARCHITECTURE.md) | 6 metric 규범, 추출/채점 경계, API 스펙 |
| [INTEGRATION_STRATEGY.md](./INTEGRATION_STRATEGY.md) | 통합 전략, prefix 충돌, Phase 설계 |
| [ORCHESTRATOR.md](./ORCHESTRATOR.md) | **오케스트레이터·extract_coordinator** 대화 정리 및 구현 현황 |
