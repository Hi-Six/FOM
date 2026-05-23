"""
멈춤 검출 튜닝 단계 (0=기본, 1~5 누적).

1. 자동 임계값 완화 (t_low↑, t_high↓)
2. 연속 저속 N프레임 + 진입 조건 완화 (직전 >= t_low)
3. 멈춤 병합 간격·최소 동작 구간 축소
4. (예약) 수동 임계값 배율 — level≥4 시 t_low 추가 상향
5. motion: 멈춤 매칭 ε 확대 + ref 미매칭 인접 구간 스킵 해제
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PauseTuning:
    level: int = 0

    def __post_init__(self) -> None:
        if not 0 <= self.level <= 5:
            raise ValueError("pause_tuning.level 은 0~5")

    @property
    def relaxed_thresholds(self) -> bool:
        return self.level >= 1

    @property
    def run_based_pauses(self) -> bool:
        return self.level >= 2

    @property
    def tight_segments(self) -> bool:
        return self.level >= 3

    @property
    def extra_low_boost(self) -> bool:
        return self.level >= 4

    @property
    def relaxed_matching(self) -> bool:
        return self.level >= 5

    @property
    def min_pause_gap_sec(self) -> float:
        return 0.04 if self.tight_segments else 0.08

    @property
    def min_motion_sec(self) -> float:
        return 0.15 if self.tight_segments else 0.25

    @property
    def pause_min_run_frames(self) -> int:
        return 2 if self.run_based_pauses else 1

    @property
    def pause_match_epsilon_scale(self) -> float:
        return 1.6 if self.relaxed_matching else 1.0

    @property
    def skip_unmatched_adjacent_segments(self) -> bool:
        return not self.relaxed_matching

    @property
    def pause_boundary_tol_sec(self) -> float:
        return 0.12 if self.relaxed_matching else 0.06
