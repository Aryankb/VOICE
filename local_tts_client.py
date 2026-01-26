"""
Local TTS Client using XTTS-v2 or MeloTTS
Generates audio files locally for Twilio playback
"""

import os
import uuid
import logging
import asyncio
from pathlib import Path
from typing import Optional
from config import settings

logger = logging.getLogger(__name__)


class LocalTTSClient:
    """
    Client for local text-to-speech generation
    Supports XTTS-v2 and MeloTTS engines
    """

    def __init__(self):
        self.engine = settings.tts_engine
        self.output_dir = Path(settings.tts_output_dir)
        self.sample_rate = settings.tts_sample_rate
        self.cleanup_delay = settings.tts_cleanup_delay

        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Initialize TTS engine
        self.tts = None
        self._initialized = False

    def _init_engine(self):
        """Lazy initialization of TTS engine"""
        if self._initialized:
            return

        try:
            if self.engine == "xtts":
                from TTS.api import TTS
                import os
                # Set environment variable to auto-agree to TOS
                os.environ['COQUI_TOS_AGREED'] = '1'
                logger.info("Loading XTTS-v2 model...")
                self.tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2")
                logger.info("✅ XTTS-v2 model loaded")

            elif self.engine == "melo":
                from melotts import MeloTTS
                logger.info("Loading MeloTTS model...")
                self.tts = MeloTTS()
                logger.info("✅ MeloTTS model loaded")

            else:
                raise ValueError(f"Unknown TTS engine: {self.engine}")

            self._initialized = True

        except ImportError as e:
            logger.error(f"TTS library not installed: {str(e)}")
            logger.error(f"Install with: pip install coqui-tts (for XTTS) or pip install melotts (for MeloTTS)")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize TTS engine: {str(e)}", exc_info=True)
            raise

    async def generate_speech(
        self,
        text: str,
        language: str = "en-US",
        voice: Optional[str] = None
    ) -> str:
        """
        Generate speech from text and return file path

        Args:
            text: Text to convert to speech
            language: Language code (e.g., "en-US", "hi-IN")
            voice: Optional voice identifier

        Returns:
            Path to generated audio file (WAV format)
        """
        # Initialize engine on first use
        self._init_engine()

        # Generate unique filename
        file_id = str(uuid.uuid4())
        output_file = self.output_dir / f"tts_{file_id}.wav"

        try:
            # Convert language code to format expected by TTS engines
            lang_code = self._convert_language_code(language)

            logger.info(f"Generating TTS for text: {text[:50]}... (language: {lang_code})")

            # Run in thread pool to avoid blocking
            await asyncio.to_thread(self._generate_sync, text, str(output_file), lang_code, voice)

            logger.info(f"✅ TTS generated: {output_file}")

            # Schedule cleanup
            asyncio.create_task(self._cleanup_file(str(output_file)))

            return str(output_file)

        except Exception as e:
            logger.error(f"TTS generation error: {str(e)}", exc_info=True)
            # Cleanup partial file
            if output_file.exists():
                output_file.unlink()
            raise Exception(f"TTS generation failed: {str(e)}")

    def _generate_sync(self, text: str, output_file: str, language: str, voice: Optional[str]):
        """
        Synchronous TTS generation (runs in thread pool)
        """
        if self.engine == "xtts":
            # XTTS-v2 generation with preset speaker
            # Use preset speaker if no voice specified
            speaker_name = voice if voice else "Ana Florence"  # Default female voice

            self.tts.tts_to_file(
                text=text,
                file_path=output_file,
                language=language,
                speaker=speaker_name  # Use preset speaker instead of speaker_wav
            )

        elif self.engine == "melo":
            # MeloTTS generation
            # Note: MeloTTS API might be different, adjust as needed
            self.tts.tts_to_file(
                text=text,
                output_path=output_file,
                language=language
            )

    def _convert_language_code(self, language: str) -> str:
        """
        Convert Twilio language codes to TTS engine format

        Args:
            language: Twilio language code (e.g., "en-US", "hi-IN")

        Returns:
            TTS engine language code
        """
        # Map common language codes
        lang_map = {
            "en-US": "en",
            "en-GB": "en",
            "hi-IN": "hi",
            "es-ES": "es",
            "fr-FR": "fr",
            "de-DE": "de",
            "pt-BR": "pt",
            "zh-CN": "zh",
            "ja-JP": "ja",
            "ko-KR": "ko",
        }

        return lang_map.get(language, language.split("-")[0])

    async def _cleanup_file(self, file_path: str):
        """
        Delete audio file after delay

        Args:
            file_path: Path to file to delete
        """
        try:
            # Wait for cleanup delay
            await asyncio.sleep(self.cleanup_delay)

            # Delete file
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"🗑️ Cleaned up TTS file: {file_path}")

        except Exception as e:
            logger.error(f"Failed to cleanup file {file_path}: {str(e)}")

    def cleanup_all(self):
        """
        Cleanup all TTS files in output directory
        """
        try:
            for file in self.output_dir.glob("tts_*.wav"):
                file.unlink()
                logger.info(f"🗑️ Cleaned up: {file}")
        except Exception as e:
            logger.error(f"Failed to cleanup TTS files: {str(e)}")

    async def health_check(self) -> bool:
        """
        Check if TTS engine is ready

        Returns:
            True if healthy, False otherwise
        """
        try:
            # Try to initialize
            self._init_engine()

            # List available speakers
            if self.engine == "xtts" and hasattr(self.tts, 'speakers'):
                logger.info(f"Available XTTS speakers: {self.tts.speakers}")

            # Test generation
            test_file = self.output_dir / "test.wav"
            await asyncio.to_thread(
                self._generate_sync,
                "Test",
                str(test_file),
                "en",
                "Ana Florence"  # Use preset speaker for test
            )

            # Cleanup test file
            if test_file.exists():
                test_file.unlink()

            logger.info("✅ TTS health check passed")
            return True

        except Exception as e:
            logger.error(f"TTS health check failed: {str(e)}")
            return False


# Global client instance
_tts_client: Optional[LocalTTSClient] = None


def get_tts_client() -> LocalTTSClient:
    """Get or create the global TTS client instance"""
    global _tts_client
    if _tts_client is None:
        _tts_client = LocalTTSClient()
    return _tts_client
