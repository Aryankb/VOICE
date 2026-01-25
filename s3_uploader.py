"""
S3 uploader for recording archival
"""

import asyncio
import logging
from typing import Optional
from datetime import datetime
import aioboto3
import aiohttp
from botocore.exceptions import ClientError
from botocore.config import Config as BotoConfig
from config import settings
from exceptions import S3UploadException

logger = logging.getLogger(__name__)


class S3Uploader:
    """Async S3 uploader for call recordings"""

    def __init__(self):
        self.region = settings.aws_region
        self.bucket = settings.s3_bucket_recordings
        self.prefix = settings.s3_recordings_prefix
        self.session = None
        self._initialized = False

        # Boto3 config with retry logic
        self.boto_config = BotoConfig(
            region_name=self.region,
            retries={
                'max_attempts': 3,
                'mode': 'adaptive'
            }
        )

    async def _ensure_initialized(self):
        """Ensure the session is initialized"""
        if not self._initialized:
            if settings.aws_access_key_id and settings.aws_secret_access_key:
                self.session = aioboto3.Session(
                    aws_access_key_id=settings.aws_access_key_id,
                    aws_secret_access_key=settings.aws_secret_access_key,
                    region_name=self.region
                )
            else:
                self.session = aioboto3.Session(region_name=self.region)

            self._initialized = True

    async def download_recording(self, recording_url: str) -> bytes:
        """
        Download recording from Twilio

        Args:
            recording_url: Twilio recording URL

        Returns:
            Recording audio bytes
        """
        try:
            # Add .mp3 extension to get MP3 format
            if not recording_url.endswith('.mp3'):
                recording_url = f"{recording_url}.mp3"

            logger.info(f"Downloading recording from {recording_url}")

            # Use aiohttp for async download
            async with aiohttp.ClientSession() as session:
                # Use Twilio credentials for authentication
                auth = aiohttp.BasicAuth(
                    settings.twilio_account_sid,
                    settings.twilio_auth_token
                )

                async with session.get(recording_url, auth=auth) as response:
                    if response.status != 200:
                        raise S3UploadException(
                            f"Failed to download recording: HTTP {response.status}"
                        )

                    audio_data = await response.read()
                    logger.info(f"Downloaded {len(audio_data)} bytes")
                    return audio_data

        except Exception as e:
            logger.error(f"Error downloading recording from {recording_url}: {e}")
            raise S3UploadException(f"Failed to download recording: {e}")

    async def upload_to_s3(
        self,
        audio_data: bytes,
        call_sid: str,
        content_type: str = "audio/mpeg"
    ) -> str:
        """
        Upload audio to S3

        Args:
            audio_data: Audio bytes
            call_sid: Twilio call SID (used as filename)
            content_type: MIME type of the audio

        Returns:
            S3 URL (s3://bucket/key format)
        """
        await self._ensure_initialized()

        try:
            # Generate S3 key
            s3_key = f"{self.prefix}{call_sid}.mp3"

            logger.info(f"Uploading to S3: s3://{self.bucket}/{s3_key}")

            async with self.session.client('s3', config=self.boto_config) as s3:
                await s3.put_object(
                    Bucket=self.bucket,
                    Key=s3_key,
                    Body=audio_data,
                    ContentType=content_type,
                    ServerSideEncryption='AES256',  # Encrypt at rest
                    Metadata={
                        'call_sid': call_sid,
                        'uploaded_at': datetime.now().isoformat()
                    }
                )

            s3_url = f"s3://{self.bucket}/{s3_key}"
            logger.info(f"Successfully uploaded recording to {s3_url}")
            return s3_url

        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.error(f"S3 upload error ({error_code}): {e}")
            raise S3UploadException(f"Failed to upload to S3: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in S3 upload: {e}")
            raise S3UploadException(f"Unexpected error: {e}")

    async def download_and_upload_recording(
        self,
        recording_url: str,
        call_sid: str,
        max_retries: int = 3,
        retry_delay: int = 5
    ) -> Optional[str]:
        """
        Download recording from Twilio and upload to S3 with retry logic

        Args:
            recording_url: Twilio recording URL
            call_sid: Twilio call SID
            max_retries: Maximum number of retry attempts
            retry_delay: Delay between retries in seconds

        Returns:
            S3 URL if successful, None if failed
        """
        for attempt in range(max_retries):
            try:
                # Download from Twilio
                audio_data = await self.download_recording(recording_url)

                # Upload to S3
                s3_url = await self.upload_to_s3(audio_data, call_sid)

                logger.info(
                    f"Successfully archived recording for {call_sid}: "
                    f"{len(audio_data)} bytes -> {s3_url}"
                )

                return s3_url

            except S3UploadException as e:
                if "404" in str(e) and attempt < max_retries - 1:
                    # Recording not ready yet, wait and retry
                    logger.warning(
                        f"Recording not ready for {call_sid}, "
                        f"retrying in {retry_delay}s (attempt {attempt + 1}/{max_retries})"
                    )
                    await asyncio.sleep(retry_delay)
                else:
                    logger.error(
                        f"Failed to download and upload recording for {call_sid}: {e}"
                    )
                    # Return None on failure (don't block call finalization)
                    return None
            except Exception as e:
                logger.error(
                    f"Failed to download and upload recording for {call_sid}: {e}"
                )
                # Return None on failure (don't block call finalization)
                return None

        return None

    async def get_recording_url(self, call_sid: str) -> Optional[str]:
        """
        Get S3 URL for a call recording

        Args:
            call_sid: Twilio call SID

        Returns:
            S3 URL if exists, None otherwise
        """
        s3_key = f"{self.prefix}{call_sid}.mp3"
        return f"s3://{self.bucket}/{s3_key}"

    async def generate_presigned_url(
        self,
        call_sid: str,
        expiration: int = 3600
    ) -> Optional[str]:
        """
        Generate presigned URL for S3 recording

        Args:
            call_sid: Twilio call SID
            expiration: URL expiration time in seconds (default: 1 hour)

        Returns:
            Presigned URL if successful, None if failed
        """
        await self._ensure_initialized()

        try:
            s3_key = f"{self.prefix}{call_sid}.mp3"

            async with self.session.client('s3', config=self.boto_config) as s3:
                url = await s3.generate_presigned_url(
                    'get_object',
                    Params={
                        'Bucket': self.bucket,
                        'Key': s3_key
                    },
                    ExpiresIn=expiration
                )

            logger.info(f"Generated presigned URL for {call_sid}")
            return url

        except Exception as e:
            logger.error(f"Error generating presigned URL for {call_sid}: {e}")
            return None


# Global S3 uploader instance
s3_uploader = S3Uploader()
