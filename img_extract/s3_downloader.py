import os
import boto3
import asyncio
import json
import tempfile
import shutil
from urllib.parse import urlparse
from pathlib import Path
from datetime import datetime

class S3Downloader:
    """Enhanced S3 manager with direct upload capabilities and automatic cleanup"""
    
    def __init__(self):
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            region_name=os.getenv('AWS_REGION')
        )
        self.bucket = os.getenv('S3_BUCKET')
    
    def parse_s3_url(self, s3_url: str):
        """Parse S3 URL to extract bucket and key"""
        parsed = urlparse(s3_url)
        bucket = parsed.netloc
        key = parsed.path.lstrip('/')
        return bucket, key
    
    async def download_from_s3(self, s3_url: str, local_dir: str):
        """Download file from S3 to local directory"""
        try:
            bucket, key = self.parse_s3_url(s3_url)
            os.makedirs(local_dir, exist_ok=True)
            
            filename = Path(key).name
            local_path = os.path.join(local_dir, filename)
            
            await asyncio.to_thread(
                self.s3_client.download_file,
                bucket, key, local_path
            )
            
            print(f"✅ Downloaded to temporary storage: {local_path}")
            return local_path
            
        except Exception as e:
            print(f"❌ Failed to download from S3: {e}")
            return None
    
    async def upload_json_to_s3(self, data: dict, s3_key: str, metadata: dict = None):
        """Upload JSON data directly to S3"""
        try:
            json_data = json.dumps(data, indent=2, ensure_ascii=False)
            
            upload_args = {
                'Bucket': self.bucket,
                'Key': s3_key,
                'Body': json_data.encode('utf-8'),
                'ContentType': 'application/json'
            }
            
            if metadata:
                upload_args['Metadata'] = metadata
            
            await asyncio.to_thread(
                self.s3_client.put_object,
                **upload_args
            )
            
            print(f"✅ JSON uploaded to S3: s3://{self.bucket}/{s3_key}")
            return f"s3://{self.bucket}/{s3_key}"
            
        except Exception as e:
            print(f"❌ Failed to upload JSON to S3: {e}")
            raise
    
    def generate_s3_result_key(self, original_s3_url: str) -> str:
        """Generate S3 key for storing results"""
        # Extract process UUID from original URL
        # s3://bucket/processes/uuid/downloads/file.zip -> processes/uuid/results/
        parts = original_s3_url.replace("s3://", "").split("/")
        if len(parts) >= 4 and parts[1] == "processes":
            process_uuid = parts[2]
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            return f"processes/{process_uuid}/results/extracted_data_{timestamp}.json"
        else:
            # Fallback
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            return f"extraction_results/extracted_data_{timestamp}.json"
