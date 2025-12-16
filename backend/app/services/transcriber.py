"""
Audio transcription service using Aliyun Paraformer-v2.
Provides speech-to-text with timestamps and speaker diarization.
"""
import dashscope
from dashscope.audio.asr import Transcription
import asyncio
import logging
import requests
from typing import Optional, List, Dict, Any

from app.config import settings

logger = logging.getLogger(__name__)


class TranscriptionError(Exception):
    """Custom exception for transcription failures."""
    pass


class ParaformerTranscriber:
    """
    Transcription service using Aliyun Paraformer-v2 API.
    Supports speaker diarization and millisecond-level timestamps.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize transcriber with API key.
        
        Args:
            api_key: Aliyun DashScope API key
        """
        self.api_key = api_key or settings.qwen_api_key
        dashscope.api_key = self.api_key
        
        self.max_wait_time = settings.transcription_timeout
        self.poll_interval = settings.poll_interval
    
    async def transcribe_from_url(
        self,
        audio_url: str,
        enable_diarization: bool = True,
        language: str = "auto"
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Transcribe audio from a public URL.
        
        Args:
            audio_url: Public URL of the audio file
            enable_diarization: Enable speaker diarization
            language: Language hint ("auto", "zh", "en", etc.)
            
        Returns:
            List of transcript segments with timestamps, or None if failed
            Format: [{"text": "...", "start_time": 0.1, "end_time": 3.5, "speaker_id": 0}]
        """
        try:
            logger.info(f"Starting transcription for: {audio_url}")
            
            # Submit async transcription task
            response = await self._submit_task(audio_url, enable_diarization)
            
            if not response or not hasattr(response, 'output'):
                raise TranscriptionError("Failed to submit transcription task")
            
            task_id = response.output.task_id
            logger.info(f"Transcription task submitted: {task_id}")
            
            # Poll for completion
            result = await self._poll_task(task_id)
            
            if result is None:
                raise TranscriptionError("Transcription task timed out or failed")
            
            # Parse and return results
            segments = self._parse_result(result)
            logger.info(f"Transcription completed: {len(segments)} segments")
            
            return segments
            
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            return None
    
    async def _submit_task(
        self, 
        audio_url: str, 
        enable_diarization: bool
    ) -> Any:
        """Submit async transcription task."""
        loop = asyncio.get_event_loop()
        
        def submit():
            return Transcription.async_call(
                model='paraformer-v2',
                file_urls=[audio_url],
                diarization_enabled=enable_diarization,
            )
        
        return await loop.run_in_executor(None, submit)
    
    async def _poll_task(self, task_id: str) -> Optional[Any]:
        """
        Poll transcription task until completion.
        
        Args:
            task_id: Transcription task ID
            
        Returns:
            Task output or None if failed/timeout
        """
        elapsed = 0
        loop = asyncio.get_event_loop()
        
        def fetch():
            return Transcription.fetch(task=task_id)
        
        while elapsed < self.max_wait_time:
            await asyncio.sleep(self.poll_interval)
            elapsed += self.poll_interval
            
            try:
                result = await loop.run_in_executor(None, fetch)
                status = result.output.task_status
                
                logger.debug(f"Task {task_id} status: {status} ({elapsed}s elapsed)")
                
                if status == "SUCCEEDED":
                    return result.output
                elif status == "FAILED":
                    error = getattr(result.output, 'message', 'Unknown error')
                    logger.error(f"Transcription task failed: {error}")
                    return None
                    
            except Exception as e:
                logger.warning(f"Error polling task: {e}")
                continue
        
        logger.error(f"Transcription task timed out after {self.max_wait_time}s")
        return None
    
    def _parse_result(self, output: Any) -> List[Dict[str, Any]]:
        """
        Parse Paraformer transcription result.
        
        Args:
            output: Raw Paraformer output
            
        Returns:
            List of parsed transcript segments
        """
        segments = []
        
        if not hasattr(output, 'results') or not output.results:
            logger.warning("No results in transcription output")
            return segments
        
        for result in output.results:
            transcription_url = result.get('transcription_url')
            
            if not transcription_url:
                continue
            
            try:
                # Fetch detailed transcription from URL
                response = requests.get(transcription_url, timeout=30)
                response.raise_for_status()
                data = response.json()
                
                for transcript in data.get('transcripts', []):
                    for sentence in transcript.get('sentences', []):
                        segment = {
                            'text': sentence.get('text', ''),
                            'start_time': sentence.get('begin_time', 0) / 1000.0,
                            'end_time': sentence.get('end_time', 0) / 1000.0,
                            'speaker_id': sentence.get('speaker_id', 0)
                        }
                        segments.append(segment)
                        
            except Exception as e:
                logger.error(f"Failed to parse transcription URL: {e}")
                continue
        
        return segments
    
    def generate_srt(self, segments: List[Dict[str, Any]]) -> str:
        """
        Generate SRT subtitle content from transcript segments.
        
        Args:
            segments: List of transcript segments
            
        Returns:
            SRT formatted string
        """
        srt_lines = []
        
        for i, segment in enumerate(segments, 1):
            start = self._format_srt_time(segment['start_time'])
            end = self._format_srt_time(segment['end_time'])
            text = segment['text']
            
            srt_lines.append(f"{i}")
            srt_lines.append(f"{start} --> {end}")
            srt_lines.append(text)
            srt_lines.append("")
        
        return "\n".join(srt_lines)
    
    def _format_srt_time(self, seconds: float) -> str:
        """Format seconds to SRT timestamp (HH:MM:SS,mmm)."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds - int(seconds)) * 1000)
        
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
    
    def get_full_text(self, segments: List[Dict[str, Any]]) -> str:
        """
        Combine all segments into full text.
        
        Args:
            segments: List of transcript segments
            
        Returns:
            Full transcription text
        """
        return " ".join(seg['text'] for seg in segments if seg.get('text'))


# Convenience function
async def transcribe_audio(
    audio_url: str,
    api_key: Optional[str] = None,
    enable_diarization: bool = True
) -> Optional[List[Dict[str, Any]]]:
    """
    Quick transcription function.
    
    Args:
        audio_url: Public URL of audio file
        api_key: Optional API key override
        enable_diarization: Enable speaker diarization
        
    Returns:
        List of transcript segments or None
    """
    transcriber = ParaformerTranscriber(api_key=api_key)
    return await transcriber.transcribe_from_url(
        audio_url, 
        enable_diarization=enable_diarization
    )
