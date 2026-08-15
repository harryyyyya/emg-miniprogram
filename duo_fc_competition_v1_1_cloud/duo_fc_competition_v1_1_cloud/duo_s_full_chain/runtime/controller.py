from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class Validity(IntEnum):
    VALID = 0
    LOW_CONFIDENCE = 1
    SIGNAL_INVALID = 2


@dataclass(frozen=True)
class ControllerConfig:
    margin_threshold: float
    vote_horizon_ms: int = 300
    vote_required_fraction: float = 0.70
    nominal_step_ms: int = 40
    low_confidence_hold_ms: int = 200
    rest_label: int = 0

    def __post_init__(self) -> None:
        if not 0 <= self.rest_label <= 8:
            raise ValueError("rest_label must be in 0..8")
        if self.low_confidence_hold_ms > 200:
            raise ValueError("low_confidence_hold_ms must not exceed 200")
        if self.vote_horizon_ms <= 0 or self.nominal_step_ms <= 0:
            raise ValueError("vote timing values must be positive")
        if not 0.0 < self.vote_required_fraction <= 1.0:
            raise ValueError("vote_required_fraction must be in (0, 1]")


@dataclass(frozen=True)
class ControllerOutput:
    frame_seq: int
    state_seq: int
    gesture_id: int
    validity: Validity
    margin: float
    timestamp_ms: int
    candidate_label: int


class EmgController:
    """Behavioral port of the authoritative emg_controller.c."""

    def __init__(self, config: ControllerConfig) -> None:
        self.config = config
        self.frame_seq = 0
        self.state_seq = 0
        self.stable_label = config.rest_label
        self.last_timestamp_ms: int | None = None
        self.last_confident_timestamp_ms: int | None = None
        self.election_start_timestamp_ms: int | None = None
        self.votes: list[tuple[int, int]] = []
        self.last_output = ControllerOutput(0, 0, config.rest_label, Validity.VALID, 0.0, 0, config.rest_label)

    def _clear_votes(self) -> None:
        self.votes.clear()
        self.election_start_timestamp_ms = None

    def _reset_to_rest(self) -> None:
        self._clear_votes()
        self.stable_label = self.config.rest_label
        self.last_confident_timestamp_ms = None

    def _emit(self, timestamp_ms: int, gesture_id: int, validity: Validity, margin: float, candidate: int) -> ControllerOutput:
        if gesture_id != self.last_output.gesture_id or validity != self.last_output.validity:
            self.state_seq = (self.state_seq + 1) & 0xFFFFFFFF
        output = ControllerOutput(self.frame_seq, self.state_seq, gesture_id, validity, float(margin), timestamp_ms, candidate)
        self.last_output = output
        return output

    def reset_for_continuity_block(self, timestamp_ms: int = 0) -> ControllerOutput:
        self._reset_to_rest()
        self.last_timestamp_ms = None
        return self._emit(timestamp_ms, self.config.rest_label, Validity.SIGNAL_INVALID, 0.0, self.config.rest_label)

    def update(self, timestamp_ms: int, candidate_label: int, margin: float, valid_signal: bool = True) -> ControllerOutput:
        candidate = int(candidate_label)
        if not 0 <= candidate <= 8:
            valid_signal = False
            candidate = self.config.rest_label
        timestamp = int(timestamp_ms) & 0xFFFFFFFF
        self.frame_seq = (self.frame_seq + 1) & 0xFFFFFFFF
        if self.last_timestamp_ms is not None and timestamp < self.last_timestamp_ms:
            self._reset_to_rest()
            self.last_timestamp_ms = None
            return self._emit(timestamp, self.config.rest_label, Validity.SIGNAL_INVALID, margin, candidate)
        self.last_timestamp_ms = timestamp
        if not valid_signal:
            self._reset_to_rest()
            return self._emit(timestamp, self.config.rest_label, Validity.SIGNAL_INVALID, margin, candidate)
        if margin < self.config.margin_threshold:
            hold = (
                self.last_confident_timestamp_ms is not None
                and ((timestamp - self.last_confident_timestamp_ms) & 0xFFFFFFFF) <= self.config.low_confidence_hold_ms
            )
            if not hold:
                self._reset_to_rest()
            gesture = self.stable_label if hold else self.config.rest_label
            return self._emit(timestamp, gesture, Validity.LOW_CONFIDENCE, margin, candidate)
        self.last_confident_timestamp_ms = timestamp
        if self.election_start_timestamp_ms is None:
            self.election_start_timestamp_ms = timestamp
        self.votes = [(ts, label) for ts, label in self.votes if ((timestamp - ts) & 0xFFFFFFFF) <= self.config.vote_horizon_ms]
        if len(self.votes) < 16:
            self.votes.append((timestamp, candidate))
        min_count = self.config.vote_horizon_ms // self.config.nominal_step_ms + 1
        mature = (
            self.election_start_timestamp_ms is not None
            and len(self.votes) >= min_count
            and ((timestamp - self.election_start_timestamp_ms) & 0xFFFFFFFF) >= self.config.vote_horizon_ms
        )
        if mature:
            for _, label in self.votes:
                count = sum(vote_label == label for _, vote_label in self.votes)
                if count / len(self.votes) >= self.config.vote_required_fraction:
                    self.stable_label = label
                    break
        return self._emit(timestamp, self.stable_label, Validity.VALID, margin, candidate)
