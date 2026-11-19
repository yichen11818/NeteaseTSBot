from dataclasses import dataclass

from .config import Settings


@dataclass(frozen=True)
class RecoveryPolicy:
    enabled: bool
    retry_count: int
    initial_delay_seconds: int
    max_delay_seconds: int
    exhausted_action: str
    cooldown_seconds: int
    failed_tracks_before_cooldown: int

    @classmethod
    def snapshot(cls, settings: Settings) -> 'RecoveryPolicy':
        return cls(
            settings.playback_recovery_enabled, settings.playback_retry_count,
            settings.playback_retry_initial_delay_seconds, settings.playback_retry_max_delay_seconds,
            settings.playback_exhausted_action.upper(), settings.playback_cooldown_seconds,
            settings.playback_failed_tracks_before_cooldown,
        )

    def retry_delay(self, attempt: int) -> int:
        return min(self.max_delay_seconds, self.initial_delay_seconds * 2 ** (attempt - 1))
