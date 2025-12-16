"""
Aliyun OSS storage service.
Handles file uploads and generates public URLs.
"""
import oss2
import asyncio
import logging
from typing import Optional
from pathlib import Path
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
        endpoint: Optional[str] = None
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
        
        # Initialize auth and bucket
        self.auth = oss2.Auth(self.access_key_id, self.access_key_secret)
        self.bucket = oss2.Bucket(self.auth, self.endpoint, self.bucket_name)
    
    def _get_content_type(self, file_path: str) -> str:
        """Determine content type from file extension."""
        content_type, _ = mimetypes.guess_type(file_path)
        return content_type or 'application/octet-stream'
    
    async def upload_file(
        self,
        local_path: str,
        object_key: str,
        content_type: Optional[str] = None
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
            headers = {'Content-Type': content_type}
            with open(local_path, 'rb') as f:
                result = self.bucket.put_object(object_key, f, headers=headers)
            return result
        
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
        content_type: str = 'application/octet-stream'
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
            headers = {'Content-Type': content_type}
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
            Public URL
        """
        # Remove 'oss-' prefix if present in endpoint for URL
        endpoint = self.endpoint
        if endpoint.startswith('oss-'):
            endpoint = endpoint
        
        return f"https://{self.bucket_name}.{endpoint}/{object_key}"
    
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
