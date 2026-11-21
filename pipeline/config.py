import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_MATCH_ID = "El classico 2017"
DEFAULT_VIDEO = "data/input/Barcelona vs Real Madrid (2017).mp4"
DEFAULT_ROSTERS = [
    "data/input/El_Clasico_2017_Lineups.xlsx - Barcelona.csv",
    "data/input/El_Clasico_2017_Lineups.xlsx - Real Madrid.csv",
]


@dataclass(frozen=True)
class MatchConfig:
    match_id: str = DEFAULT_MATCH_ID
    video_path: str = DEFAULT_VIDEO
    roster_paths: list[str] = field(default_factory=lambda: list(DEFAULT_ROSTERS))
    artifacts_root: str = "data/artifacts"

    @property
    def artifact_dir(self) -> Path:
        return Path(self.artifacts_root) / self.match_id

    @property
    def db_path(self) -> str:
        return str(self.artifact_dir / "match.db")

    @property
    def index_dir(self) -> Path:
        return self.artifact_dir / "index"

    @property
    def signals_dir(self) -> Path:
        return self.artifact_dir / "signals"

    @property
    def audio_path(self) -> str:
        return str(self.artifact_dir / "audio" / "audio.wav")

    @property
    def keyframes_dir(self) -> str:
        return str(self.index_dir / "keyframes")

    @property
    def event_frames_dir(self) -> str:
        return str(self.artifact_dir / "event_keyframes")


def load_config(match_id: str | None = None, video_path: str | None = None) -> MatchConfig:
    return MatchConfig(
        match_id=match_id or os.getenv("MATCH_ID", DEFAULT_MATCH_ID),
        video_path=video_path or os.getenv("MATCH_VIDEO", DEFAULT_VIDEO),
    )
