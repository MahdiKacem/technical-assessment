from pipeline.analysis.transcription import (transcribe_audio, save_transcription,)

MATCH_DIR = "data/artifacts/El classico 2017"

audio_path = f"{MATCH_DIR}/audio/audio.wav"

segments = transcribe_audio(
    audio_path,
    model_size="small",
    language="en",
)

save_transcription(
    segments,
    f"{MATCH_DIR}/signals/transcription.json",
)

print(f"Transcribed {len(segments)} segments.")

for segment in segments:
    print(
        f"[{segment['start_time']:.2f}s - "
        f"{segment['end_time']:.2f}s] "
        f"{segment['text']}"
    )