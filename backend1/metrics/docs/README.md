# Metrics 아키텍처

6개 metric을 **담당 폴더 단위로 분리**한다. **영상 추출은 각 `metrics/<이름>/`**, **`POST /video/analyze` 오케스트레이터는 추출 없이** 저장된 결과만 로드·정렬·`score_*` 병렬·병합한다.

상세: [ARCHITECTURE.md](./ARCHITECTURE.md)
