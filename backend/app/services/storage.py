"""
Aliyun OSS storage service.
Handles file uploads and generates public URLs.
"""

import oss2
import asyncio
import logging
import os
from typing import Optional, List
from pathlib import Path
from datetime import datetime, timedelta
import mimetypes

from app.config import settings

logger = logging.getLogger(__name__)


class StorageError(Exception):
    """Custom exception for storage failures."""

    pass


class OSSStorage:
    """
    Aliyun OSS storage client.
    Handles file uploads and URL generation.
    """

    def __init__(
        self,
        access_key_id: Optional[str] = None,
        access_key_secret: Optional[str] = None,
        bucket_name: Optional[str] = None,
        endpoint: Optional[str] = None,
    ):
        """
        Initialize OSS client.

        Args:
            access_key_id: Aliyun access key ID
            access_key_secret: Aliyun access key secret
            bucket_name: OSS bucket name
            endpoint: OSS endpoint URL
        """
        self.access_key_id = access_key_id or settings.oss_access_key_id
        self.access_key_secret = access_key_secret or settings.oss_access_key_secret
        self.bucket_name = bucket_name or settings.oss_bucket
        self.endpoint = endpoint or settings.oss_endpoint

        # Initialize auth
        self.auth = oss2.Auth(self.access_key_id, self.access_key_secret)

        # Initialize bucket (we'll control proxy via environment variables)
        self.bucket = oss2.Bucket(self.auth, self.endpoint, self.bucket_name)

    def _get_content_type(self, file_path: str) -> str:
        """Determine content type from file extension."""
        content_type, _ = mimetypes.guess_type(file_path)
        return content_type or "application/octet-stream"

    def _disable_proxy_env(self) -> dict:
        """Temporarily disable proxy environment variables for OSS access."""
        saved = {}
        for key in ["http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"]:
            if key in os.environ:
                saved[key] = os.environ.pop(key)
        return saved

    def _restore_proxy_env(self, saved: dict):
        """Restore proxy environment variables."""
        for key, value in saved.items():
            os.environ[key] = value

    async def upload_file(
        self, local_path: str, object_key: str, content_type: Optional[str] = None
    ) -> str:
        """
        Upload file to OSS.

        Args:
            local_path: Local file path
            object_key: OSS object key (path in bucket)
            content_type: Optional content type override

        Returns:
            Public URL of uploaded file

        Raises:
            StorageError: If upload fails
        """
        if not Path(local_path).exists():
            raise StorageError(f"Local file not found: {local_path}")

        if content_type is None:
            content_type = self._get_content_type(local_path)

        loop = asyncio.get_event_loop()

        def do_upload():
            # Temporarily disable proxy for OSS access
            saved_proxy = self._disable_proxy_env()
            try:
                headers = {"Content-Type": content_type}
                with open(local_path, "rb") as f:
                    result = self.bucket.put_object(object_key, f, headers=headers)
                return result
            finally:
                self._restore_proxy_env(saved_proxy)

        try:
            logger.info(f"Uploading {local_path} to OSS: {object_key}")
            result = await loop.run_in_executor(None, do_upload)

            if result.status != 200:
                raise StorageError(f"Upload failed with status: {result.status}")

            url = self.get_public_url(object_key)
            logger.info(f"Upload successful: {url}")

            return url

        except oss2.exceptions.OssError as e:
            logger.error(f"OSS upload error: {e}")
            raise StorageError(f"OSS upload failed: {e}")

    async def upload_data(
        self,
        data: bytes,
        object_key: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        """
        Upload bytes data to OSS.

        Args:
            data: Bytes data to upload
            object_key: OSS object key
            content_type: Content type

        Returns:
            Public URL of uploaded data
        """
        loop = asyncio.get_event_loop()

        def do_upload():
            headers = {"Content-Type": content_type}
            result = self.bucket.put_object(object_key, data, headers=headers)
            return result

        try:
            logger.info(f"Uploading data to OSS: {object_key}")
            result = await loop.run_in_executor(None, do_upload)

            if result.status != 200:
                raise StorageError(f"Upload failed with status: {result.status}")

            return self.get_public_url(object_key)

        except oss2.exceptions.OssError as e:
            logger.error(f"OSS upload error: {e}")
            raise StorageError(f"OSS upload failed: {e}")

    def get_public_url(self, object_key: str) -> str:
        """
        Generate public URL for OSS object.

        Args:
            object_key: OSS object key

        Returns:
            Public URL (bucket must have public read permission)
        """
        return f"https://{self.bucket_name}.{self.endpoint}/{object_key}"

    async def delete_file(self, object_key: str) -> bool:
        """
        Delete file from OSS.

        Args:
            object_key: OSS object key

        Returns:
            True if successful
        """
        loop = asyncio.get_event_loop()

        def do_delete():
            self.bucket.delete_object(object_key)

        try:
            await loop.run_in_executor(None, do_delete)
            logger.info(f"Deleted from OSS: {object_key}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete from OSS: {e}")
            return False

    async def check_exists(self, object_key: str) -> bool:
        """
        Check if object exists in OSS.

        Args:
            object_key: OSS object key

        Returns:
            True if exists
        """
        loop = asyncio.get_event_loop()

        def do_check():
            return self.bucket.object_exists(object_key)

        try:
            return await loop.run_in_executor(None, do_check)
        except Exception as e:
            logger.error(f"Failed to check OSS object: {e}")
            return False

    async def cleanup_old_files(
        self, 
        prefix: str = "downloads/", 
        max_age_hours: int = 24,
        dry_run: bool = False
    ) -> dict:
        """
        Clean up old files from OSS.

        Args:
            prefix: OSS path prefix to clean (default: "downloads/")
            max_age_hours: Delete files older than this (default: 24 hours)
            dry_run: If True, only list files without deleting

        Returns:
            Dict with cleanup statistics
        """
        loop = asyncio.get_event_loop()
        cutoff_time = datetime.utcnow() - timedelta(hours=max_age_hours)
        
        stats = {
            "scanned": 0,
            "deleted": 0,
            "failed": 0,
            "total_size_bytes": 0,
            "deleted_files": [],
            "dry_run": dry_run
        }

        def do_cleanup():
            # Temporarily disable proxy for OSS access
            saved_proxy = self._disable_proxy_env()
            try:
                # List all objects with the given prefix
                for obj in oss2.ObjectIterator(self.bucket, prefix=prefix):
                    stats["scanned"] += 1
                    
                    # Check if file is older than cutoff
                    last_modified = obj.last_modified
                    if last_modified:
                        # Convert timestamp to datetime
                        file_time = datetime.utcfromtimestamp(last_modified)
                        
                        if file_time < cutoff_time:
                            if dry_run:
                                stats["deleted"] += 1
                                stats["total_size_bytes"] += obj.size or 0
                                stats["deleted_files"].append({
                                    "key": obj.key,
                                    "size": obj.size,
                                    "last_modified": file_time.isoformat()
                                })
                            else:
                                try:
                                    self.bucket.delete_object(obj.key)
                                    stats["deleted"] += 1
                                    stats["total_size_bytes"] += obj.size or 0
                                    stats["deleted_files"].append({
                                        "key": obj.key,
                                        "size": obj.size,
                                        "last_modified": file_time.isoformat()
                                    })
                                    logger.info(f"Deleted old file: {obj.key}")
                                except Exception as e:
                                    stats["failed"] += 1
                                    logger.error(f"Failed to delete {obj.key}: {e}")
                return stats
            finally:
                self._restore_proxy_env(saved_proxy)

        try:
            logger.info(f"Starting OSS cleanup: prefix={prefix}, max_age={max_age_hours}h, dry_run={dry_run}")
            result = await loop.run_in_executor(None, do_cleanup)
            logger.info(
                f"OSS cleanup complete: scanned={result['scanned']}, "
                f"deleted={result['deleted']}, failed={result['failed']}, "
                f"freed={result['total_size_bytes'] / 1024 / 1024:.2f}MB"
            )
            return result
        except Exception as e:
            logger.error(f"OSS cleanup failed: {e}")
            raise StorageError(f"Cleanup failed: {e}")

    async def list_files(self, prefix: str = "", limit: int = 100) -> List[dict]:
        """
        List files in OSS bucket.

        Args:
            prefix: Path prefix to filter
            limit: Maximum number of files to return

        Returns:
            List of file info dicts
        """
        loop = asyncio.get_event_loop()

        def do_list():
            saved_proxy = self._disable_proxy_env()
            try:
                files = []
                for i, obj in enumerate(oss2.ObjectIterator(self.bucket, prefix=prefix)):
                    if i >= limit:
                        break
                    files.append({
                        "key": obj.key,
                        "size": obj.size,
                        "last_modified": datetime.utcfromtimestamp(obj.last_modified).isoformat() if obj.last_modified else None
                    })
                return files
            finally:
                self._restore_proxy_env(saved_proxy)

        try:
            return await loop.run_in_executor(None, do_list)
        except Exception as e:
            logger.error(f"Failed to list OSS files: {e}")
            return []


# Global storage instance
_storage: Optional[OSSStorage] = None


def get_storage() -> OSSStorage:
    """Get or create global storage instance."""
    global _storage
    if _storage is None:
        _storage = OSSStorage()
    return _storage


# Convenience functions
async def upload_file(local_path: str, object_key: str) -> str:
    """Quick upload function."""
    storage = get_storage()
    return await storage.upload_file(local_path, object_key)


async def upload_video(local_path: str, task_id: str) -> str:
    """Upload video file with standardized naming."""
    object_key = f"videos/{task_id}/{Path(local_path).name}"
    return await upload_file(local_path, object_key)


async def upload_audio(local_path: str, task_id: str) -> str:
    """Upload audio file with standardized naming."""
    object_key = f"audio/{task_id}/{Path(local_path).name}"
    return await upload_file(local_path, object_key)
