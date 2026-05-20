# Metrics 아키텍처

6개 채점 서비스를 **담당 폴더 단위로 분리**하고, **`POST /video/analyze` 한 곳**에서 **비동기 병렬** 실행 후 결과를 합친다.

상세: [ARCHITECTURE.md](./ARCHITECTURE.md)
