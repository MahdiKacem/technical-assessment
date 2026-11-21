import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

SEND_WIDTH = 768
JPEG_QUALITY = 80
FEATURE_EXTRACTOR = "handcrafted-v1"


@dataclass
class Frame:
    timestamp: float
    image: np.ndarray
    feature: np.ndarray | None = None
    relevance: float = 0.0
    path: str | None = None
    content_hash: str | None = None
    meta: dict = field(default_factory=dict)


def _resize(frame: np.ndarray, width: int) -> np.ndarray:
    h, w = frame.shape[:2]
    if w <= width:
        return frame
    return cv2.resize(frame, (width, int(h * width / w)), interpolation=cv2.INTER_AREA)


def extract_frames(video_path: str, timestamps: list[float]) -> list[Frame]:
    timestamps = sorted(timestamps)
    if not timestamps:
        return []
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")
    frames: list[Frame] = []
    try:
        cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, timestamps[0] - 1.0) * 1000)
        targets = iter(timestamps)
        target = next(targets)
        while True:
            ok, image = cap.read()
            if not ok:
                break
            t = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
            while target is not None and t >= target:
                frames.append(Frame(timestamp=round(target, 3), image=_resize(image, SEND_WIDTH)))
                target = next(targets, None)
            if target is None:
                break
    finally:
        cap.release()
    return frames


def compute_features(frames: list[Frame]) -> None:
    for frame in frames:
        gray = cv2.cvtColor(frame.image, cv2.COLOR_BGR2GRAY)
        layout = cv2.resize(gray, (64, 36), interpolation=cv2.INTER_AREA).astype(np.float32).ravel()
        layout = (layout - layout.mean()) / (layout.std() + 1e-6)
        hsv = cv2.cvtColor(frame.image, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1, 2], None, [8, 4, 4], [0, 180, 0, 256, 0, 256]).ravel()
        hist = hist / (hist.sum() + 1e-6)
        vector = np.concatenate([layout / np.sqrt(layout.size), hist * 4.0])
        frame.feature = vector / (np.linalg.norm(vector) + 1e-9)


def save_frames(frames: list[Frame], output_dir: str) -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    for frame in frames:
        ok, buffer = cv2.imencode(".jpg", frame.image, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        if not ok:
            raise RuntimeError(f"JPEG encoding failed at {frame.timestamp}")
        data = buffer.tobytes()
        frame.content_hash = hashlib.sha256(data).hexdigest()
        path = out / f"t{frame.timestamp:09.2f}.jpg"
        path.write_bytes(data)
        frame.path = str(path)
