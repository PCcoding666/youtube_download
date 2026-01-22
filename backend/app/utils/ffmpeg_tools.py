"""
FFmpeg utility functions for audio/video processing.
"""

import asyncio
import logging
import subprocess
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class FFmpegError(Exception):
    """Custom exception for FFmpeg failures."""

    pass


async def extract_audio(
    video_path: str,
    output_path: Optional[str] = None,
    sample_rate: int = 16000,
    channels: int = 1,
) -> str:
    """
    Extract audio from video file optimized for Paraformer.

    Args:
        video_path: Path to input video file
        output_path: Optional output path (default: same dir as video)
        sample_rate: Audio sample rate (default: 16000 Hz)
        channels: Number of audio channels (default: 1 for mono)

    Returns:
        Path to extracted audio file

    Raises:
        FFmpegError: If extraction fails
    """
    video_path = Path(video_path)

    if not video_path.exists():
        raise FFmpegError(f"Video file not found: {video_path}")

    if output_path is None:
        output_path = video_path.with_suffix(".wav")
    else:
        output_path = Path(output_path)

    # FFmpeg command for audio extraction
    # Optimized for Paraformer: mono, 16kHz, PCM 16-bit
    cmd = [
        "ffmpeg",
        "-i",
        str(video_path),
        "-vn",  # Disable video
        "-acodec",
        "pcm_s16le",  # PCM 16-bit encoding
        "-ar",
        str(sample_rate),  # Sample rate
        "-ac",
        str(channels),  # Channels
        "-f",
        "wav",  # WAV format
        str(output_path),
        "-y",  # Overwrite output
    ]

    logger.info(f"Extracting audio: {video_path} -> {output_path}")

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown error"
            logger.error(f"FFmpeg error: {error_msg}")
            raise FFmpegError(f"Audio extraction failed: {error_msg}")

        if not output_path.exists():
            raise FFmpegError(f"Output file not created: {output_path}")

        logger.info(f"Audio extraction complete: {output_path}")
        return str(output_path)

    except FileNotFoundError:
        raise FFmpegError("FFmpeg not found. Please install FFmpeg.")
    except Exception as e:
        raise FFmpegError(f"Audio extraction failed: {e}")


async def get_video_duration(video_path: str) -> float:
    """
    Get video duration in seconds.

    Args:
        video_path: Path to video file

    Returns:
        Duration in seconds
    """
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        video_path,
    ]

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()

        if process.returncode == 0 and stdout:
            return float(stdout.decode().strip())

        return 0.0

    except Exception as e:
        logger.warning(f"Failed to get video duration: {e}")
        return 0.0


async def get_audio_info(audio_path: str) -> dict:
    """
    Get audio file information.

    Args:
        audio_path: Path to audio file

    Returns:
        Dict with duration, sample_rate, channels
    """
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=duration,sample_rate,channels",
        "-of",
        "json",
        audio_path,
    ]

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()

        if process.returncode == 0 and stdout:
            import json

            data = json.loads(stdout.decode())
            stream = data.get("streams", [{}])[0]
            return {
                "duration": float(stream.get("duration", 0)),
                "sample_rate": int(stream.get("sample_rate", 0)),
                "channels": int(stream.get("channels", 0)),
            }

        return {"duration": 0, "sample_rate": 0, "channels": 0}

    except Exception as e:
        logger.warning(f"Failed to get audio info: {e}")
        return {"duration": 0, "sample_rate": 0, "channels": 0}


async def convert_to_mp3(
    input_path: str, output_path: Optional[str] = None, bitrate: str = "128k"
) -> str:
    """
    Convert audio/video to MP3.

    Args:
        input_path: Input file path
        output_path: Output MP3 path
        bitrate: Audio bitrate

    Returns:
        Path to MP3 file
    """
    input_path = Path(input_path)

    if output_path is None:
        output_path = input_path.with_suffix(".mp3")
    else:
        output_path = Path(output_path)

    cmd = [
        "ffmpeg",
        "-i",
        str(input_path),
        "-vn",
        "-acodec",
        "libmp3lame",
        "-b:a",
        bitrate,
        str(output_path),
        "-y",
    ]

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )

        await process.communicate()

        if process.returncode != 0 or not output_path.exists():
            raise FFmpegError("MP3 conversion failed")

        return str(output_path)

    except Exception as e:
        raise FFmpegError(f"MP3 conversion failed: {e}")


def check_ffmpeg_installed() -> bool:
    """Check if FFmpeg is installed and accessible."""
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False


def get_ffmpeg_version() -> Optional[str]:
    """Get FFmpeg version string."""
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
        if result.returncode == 0:
            first_line = result.stdout.split("\n")[0]
            return first_line
        return None
    except Exception:
        return None
