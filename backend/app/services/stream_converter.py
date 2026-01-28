"""
Stream converter service for converting m3u8 streams to MP4 files.
Uses FFmpeg to download and convert HLS streams.
"""

import asyncio
import logging
import os
import uuid
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ConversionError(Exception):
    """Exception raised when stream conversion fails."""

    pass


class StreamConverter:
    """
    Converts m3u8/HLS streams to MP4 files using FFmpeg.

    This is needed because YouTube's SABR streaming forces high-quality
    videos to use m3u8 format instead of direct download URLs.
    """

    def __init__(self, rate_limit: float = 0):
        """
        Initialize the stream converter.

        Args:
            rate_limit: Download rate limit as multiplier of playback speed.
                       0 = no limit (fastest)
                       1 = 1x playback speed (safest, mimics normal viewing)
                       2 = 2x playback speed
        """
        self.rate_limit = rate_limit

    async def convert_m3u8_to_mp4(
        self,
        m3u8_url: str,
        output_dir: str,
        filename: Optional[str] = None,
        timeout: int = 600,
        progress_callback: Optional[callable] = None,
    ) -> str:
        """
        Convert m3u8 stream to MP4 file.

        Args:
            m3u8_url: URL of the m3u8 playlist
            output_dir: Directory to save the output file
            filename: Optional filename (without extension). If None, generates UUID.
            timeout: Maximum time in seconds for conversion (default: 10 minutes)
            progress_callback: Optional callback for progress updates

        Returns:
            Path to the converted MP4 file

        Raises:
            ConversionError: If conversion fails
        """
        from app.config import settings

        start_time = time.time()

        # Ensure output directory exists
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        # Generate output filename
        if filename is None:
            filename = str(uuid.uuid4())
        output_file = os.path.join(output_dir, f"{filename}.mp4")

        logger.info(f"Starting m3u8 conversion: {m3u8_url[:80]}...")
        logger.info(f"Output file: {output_file}")

        # Build FFmpeg command
        cmd = self._build_ffmpeg_command(m3u8_url, output_file)

        # Set up environment with proxy if configured
        env = os.environ.copy()
        if settings.http_proxy:
            env["http_proxy"] = settings.http_proxy
            env["https_proxy"] = settings.http_proxy
            logger.info(f"FFmpeg using proxy: {settings.http_proxy}")

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

            # Wait for completion with timeout
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )

            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                logger.error(f"FFmpeg conversion failed: {error_msg}")
                raise ConversionError(f"FFmpeg error: {error_msg[:500]}")

            # Verify output file exists and has content
            if not os.path.exists(output_file):
                raise ConversionError("Output file was not created")

            file_size = os.path.getsize(output_file)
            if file_size == 0:
                os.remove(output_file)
                raise ConversionError("Output file is empty")

            duration = time.time() - start_time
            logger.info(
                f"Conversion completed in {duration:.2f}s, file size: {file_size / 1024 / 1024:.2f}MB"
            )

            return output_file

        except asyncio.TimeoutError:
            # Kill the process if it times out
            if process:
                process.kill()
                await process.wait()

            # Clean up partial file
            if os.path.exists(output_file):
                os.remove(output_file)

            raise ConversionError(f"Conversion timed out after {timeout}s")

        except Exception as e:
            # Clean up on any error
            if os.path.exists(output_file):
                os.remove(output_file)

            if isinstance(e, ConversionError):
                raise
            raise ConversionError(f"Conversion failed: {str(e)}")

    def _build_ffmpeg_command(self, input_url: str, output_file: str) -> list:
        """Build FFmpeg command for m3u8 to MP4 conversion."""
        cmd = [
            "ffmpeg",
            "-y",  # Overwrite output file
            "-hide_banner",
            "-loglevel",
            "info",  # Show progress info
            "-stats",  # Show encoding progress
            # Input options
            "-reconnect",
            "1",
            "-reconnect_streamed",
            "1",
            "-reconnect_delay_max",
            "5",
            "-timeout",
            "30000000",  # 30 second timeout for connections
            "-i",
            input_url,
            # Output options - copy streams without re-encoding (fast)
            "-c",
            "copy",
            # Fix audio format for MP4 container
            "-bsf:a",
            "aac_adtstoasc",
            # Optimize for web playback
            "-movflags",
            "+faststart",
            output_file,
        ]

        return cmd

    async def convert_and_merge(
        self,
        video_url: str,
        audio_url: Optional[str],
        output_dir: str,
        filename: Optional[str] = None,
        timeout: int = 900,
    ) -> str:
        """
        Convert and merge separate video and audio streams.

        Args:
            video_url: URL of video stream (can be m3u8 or direct)
            audio_url: URL of audio stream (can be m3u8 or direct), or None
            output_dir: Directory to save the output file
            filename: Optional filename (without extension)
            timeout: Maximum time in seconds

        Returns:
            Path to the merged MP4 file
        """
        from app.config import settings

        start_time = time.time()

        Path(output_dir).mkdir(parents=True, exist_ok=True)

        if filename is None:
            filename = str(uuid.uuid4())
        output_file = os.path.join(output_dir, f"{filename}.mp4")

        logger.info("Starting stream merge conversion")
        logger.info(f"Video URL: {video_url[:80]}...")
        if audio_url:
            logger.info(f"Audio URL: {audio_url[:80]}...")

        # Build FFmpeg command for merging
        cmd = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "info",  # Show progress
            "-stats",  # Show encoding progress
            # Reconnect options for streaming
            "-reconnect",
            "1",
            "-reconnect_streamed",
            "1",
            "-reconnect_delay_max",
            "5",
            "-i",
            video_url,
        ]

        if audio_url:
            cmd.extend(
                [
                    "-reconnect",
                    "1",
                    "-reconnect_streamed",
                    "1",
                    "-reconnect_delay_max",
                    "5",
                    "-i",
                    audio_url,
                ]
            )

        cmd.extend(
            [
                "-c",
                "copy",
                "-bsf:a",
                "aac_adtstoasc",
                "-movflags",
                "+faststart",
            ]
        )

        if audio_url:
            # Map both video and audio streams
            cmd.extend(["-map", "0:v:0", "-map", "1:a:0"])

        cmd.append(output_file)

        # SMART FALLBACK: Try direct download first, fallback to proxy if blocked
        # Since we extracted URLs with server DC IP, download URLs are bound to server IP
        # Server can download directly without proxy (saves bandwidth cost)
        # But if server IP is blocked, we'll retry with proxy
        
        from app.config import settings
        
        # First attempt: Direct download (no proxy)
        env = os.environ.copy()
        env.pop("http_proxy", None)
        env.pop("https_proxy", None)
        env.pop("HTTP_PROXY", None)
        env.pop("HTTPS_PROXY", None)
        logger.info("FFmpeg merge: attempting direct download (no proxy)")

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )

            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                
                # Check if error indicates blocking (403, forbidden, etc.)
                is_blocked = (
                    "403" in error_msg or 
                    "forbidden" in error_msg.lower() or
                    "HTTP error 403" in error_msg or
                    "access denied" in error_msg.lower()
                )
                
                if is_blocked:
                    logger.warning(f"Direct download blocked: {error_msg[:200]}")
                    logger.info("Retrying download with proxy fallback...")
                    raise ConversionError("BLOCKED_RETRY_WITH_PROXY")  # Special error for fallback
                else:
                    logger.error(f"FFmpeg merge failed: {error_msg}")
                    raise ConversionError(f"FFmpeg error: {error_msg[:500]}")

            if not os.path.exists(output_file) or os.path.getsize(output_file) == 0:
                if os.path.exists(output_file):
                    os.remove(output_file)
                raise ConversionError("Output file is empty or not created")

            duration = time.time() - start_time
            file_size = os.path.getsize(output_file)
            logger.info(
                f"Merge completed in {duration:.2f}s, file size: {file_size / 1024 / 1024:.2f}MB"
            )

            return output_file

        except ConversionError as e:
            # If blocked, retry with proxy
            if "BLOCKED_RETRY_WITH_PROXY" in str(e):
                proxy = settings.effective_http_proxy
                if proxy:
                    logger.info(f"Retrying download with proxy: {proxy[:50]}...")
                    env_proxy = os.environ.copy()
                    env_proxy["http_proxy"] = proxy
                    env_proxy["https_proxy"] = proxy
                    env_proxy["HTTP_PROXY"] = proxy
                    env_proxy["HTTPS_PROXY"] = proxy
                    
                    try:
                        process = await asyncio.create_subprocess_exec(
                            *cmd,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                            env=env_proxy,
                        )

                        stdout, stderr = await asyncio.wait_for(
                            process.communicate(), timeout=timeout
                        )

                        if process.returncode != 0:
                            error_msg = stderr.decode() if stderr else "Unknown error"
                            logger.error(f"FFmpeg merge failed even with proxy: {error_msg[:200]}")
                            if os.path.exists(output_file):
                                os.remove(output_file)
                            raise ConversionError(f"FFmpeg error (proxy): {error_msg[:500]}")

                        if not os.path.exists(output_file) or os.path.getsize(output_file) == 0:
                            if os.path.exists(output_file):
                                os.remove(output_file)
                            raise ConversionError("Output file is empty or not created")

                        duration = time.time() - start_time
                        file_size = os.path.getsize(output_file)
                        logger.info(
                            f"Merge completed with proxy fallback in {duration:.2f}s, file size: {file_size / 1024 / 1024:.2f}MB"
                        )
                        return output_file
                    except Exception as proxy_error:
                        if os.path.exists(output_file):
                            os.remove(output_file)
                        raise ConversionError(f"Proxy fallback failed: {str(proxy_error)}")
                else:
                    logger.error("Direct download blocked but no proxy configured")
                    if os.path.exists(output_file):
                        os.remove(output_file)
                    raise ConversionError("Download blocked and no proxy available for fallback")
            else:
                # Other ConversionError, re-raise
                if os.path.exists(output_file):
                    os.remove(output_file)
                raise

        except asyncio.TimeoutError:
            if 'process' in locals() and process:
                process.kill()
                await process.wait()
            if os.path.exists(output_file):
                os.remove(output_file)
            raise ConversionError(f"Merge timed out after {timeout}s")

        except Exception as e:
            if os.path.exists(output_file):
                os.remove(output_file)
            if isinstance(e, ConversionError):
                raise
            raise ConversionError(f"Merge failed: {str(e)}")


async def convert_stream_to_mp4(
    video_url: str,
    audio_url: Optional[str],
    output_dir: str,
    is_streaming: bool = False,
    needs_merge: bool = False,
    filename: Optional[str] = None,
    timeout: int = 600,
) -> str:
    """
    Convenience function to convert video/audio URLs to MP4.

    Handles both direct download URLs and m3u8 streams.

    Args:
        video_url: Video URL (direct or m3u8)
        audio_url: Audio URL (direct or m3u8), or None if combined
        output_dir: Output directory
        is_streaming: True if URLs are m3u8 streams
        needs_merge: True if video and audio need to be merged
        filename: Optional output filename
        timeout: Timeout in seconds

    Returns:
        Path to the output MP4 file
    """
    converter = StreamConverter()

    if needs_merge and audio_url:
        # Separate video and audio streams - need to merge
        return await converter.convert_and_merge(
            video_url=video_url,
            audio_url=audio_url,
            output_dir=output_dir,
            filename=filename,
            timeout=timeout,
        )
    elif is_streaming:
        # Single m3u8 stream with video+audio combined
        return await converter.convert_m3u8_to_mp4(
            m3u8_url=video_url,
            output_dir=output_dir,
            filename=filename,
            timeout=timeout,
        )
    else:
        # Direct download URL - still use FFmpeg for consistency
        # This handles the case where we have a direct URL but want MP4 output
        return await converter.convert_m3u8_to_mp4(
            m3u8_url=video_url,
            output_dir=output_dir,
            filename=filename,
            timeout=timeout,
        )
