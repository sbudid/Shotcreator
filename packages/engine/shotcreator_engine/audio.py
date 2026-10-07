"""Audio: attach music / murottal / TTS voiceover to a rendered video."""
from __future__ import annotations

import subprocess


def mux_audio(video_in: str, audio_in: str, video_out: str,
              loop_audio: bool = True, audio_codec: str = "aac",
              volume: float = 1.0, overwrite: bool = True) -> str:
    """Mux an audio track onto a silent video. Returns video_out.

    The video always keeps its full duration: when the audio is shorter
    than the video it is looped to fill it (loop_audio=True) instead of
    cutting the video short.
    """
    cmd = [
        "ffmpeg", "-y" if overwrite else "-n",
        "-i", video_in,
    ]
    if loop_audio:
        # repeat the audio indefinitely, then stop at the end of the video
        cmd += ["-stream_loop", "-1"]
    cmd += [
        "-i", audio_in,
        "-c:v", "copy", "-c:a", audio_codec,
    ]
    if volume != 1.0:
        cmd += ["-af", f"volume={volume}"]
    if loop_audio:
        cmd += ["-shortest"]
    cmd += [video_out]
    r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg mux exited with code {r.returncode}")
    return video_out


def media_duration(path: str) -> float:
    """Duration in seconds via ffprobe; 0.0 when ffprobe is unavailable."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=15,
        )
        return float(r.stdout.strip())
    except Exception:
        return 0.0
