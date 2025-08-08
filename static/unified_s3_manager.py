import boto3
import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional, Union
from io import BytesIO

logger = logging.getLogger(__name__)

class UnifiedS3Manager:
    """Centralized S3 manager with case number-based folder organization"""
    
    def __init__(self, case_number: str = None):
        try:
            self.s3_client = boto3.client(
                's3',
                aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
                region_name=os.getenv('AWS_REGION')
            )
            self.bucket = os.getenv('S3_BUCKET')
            
            # Use case number instead of UUID
            self.case_number = case_number or "UNKNOWN"
            
            # Generate unique folder name with incremental suffix if needed
            self.unique_case_folder = self._generate_unique_case_folder(self.case_number)
            
            # BACKWARD COMPATIBILITY: Add process_uuid for legacy code
            self.process_uuid = self.unique_case_folder  # Map to case folder for compatibility
            
            # Create standardized folder structure based on case number
            self.base_path = f"cases/{self.unique_case_folder}"
            self.folders = {
                'logs': f"{self.base_path}/logs",
                'screenshots': f"{self.base_path}/screenshots", 
                'documents': f"{self.base_path}/documents",
                'json_data': f"{self.base_path}/json_data",
                'downloads': f"{self.base_path}/downloads",
                'ai_corrections': f"{self.base_path}/ai_corrections",
                'dlc_data': f"{self.base_path}/dlc_data",
                'extracted_files': f"{self.base_path}/extracted_files"
            }
            
            logger.info(f"UnifiedS3Manager initialized - Case: {self.unique_case_folder}")
            
        except Exception as e:
            logger.error(f"Failed to initialize UnifiedS3Manager: {e}")
            raise

    def _generate_unique_case_folder(self, case_number: str) -> str:
        """Generate unique case folder name with incremental suffix"""
        try:
            # Clean case number (remove invalid characters)
            clean_case = self._clean_case_number(case_number)
            
            # Check if case folder already exists
            base_folder = clean_case
            counter = 0
            
            while self._case_folder_exists(base_folder):
                counter += 1
                base_folder = f"{clean_case}_{counter}"
            
            logger.info(f"Generated unique case folder: {base_folder}")
            return base_folder
            
        except Exception as e:
            logger.error(f"Failed to generate unique case folder: {e}")
            # Fallback to timestamp-based folder
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            return f"{clean_case}_{timestamp}"
    
    def _clean_case_number(self, case_number: str) -> str:
        """Clean case number for S3 folder naming"""
        import re
        # Remove invalid S3 characters and replace with underscores
        clean = re.sub(r'[^a-zA-Z0-9\-_]', '_', case_number)
        # Remove multiple consecutive underscores
        clean = re.sub(r'_+', '_', clean)
        # Remove leading/trailing underscores
        clean = clean.strip('_')
        return clean or "UNKNOWN_CASE"
    
    def _case_folder_exists(self, folder_name: str) -> bool:
        """Check if case folder already exists in S3"""
        try:
            prefix = f"cases/{folder_name}/"
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket,
                Prefix=prefix,
                MaxKeys=1
            )
            return 'Contents' in response and len(response['Contents']) > 0
        except Exception as e:
            logger.warning(f"Error checking folder existence: {e}")
            return False

    def upload_file(self, file_data: Union[str, bytes, dict], category: str, filename: str, content_type: str = None) -> str:
        """Upload file to appropriate category folder"""
        s3_key = f"{self.folders[category]}/{filename}"
        
        try:
            # Handle different data types
            if isinstance(file_data, dict):
                body = json.dumps(file_data, indent=2).encode('utf-8')
                content_type = content_type or 'application/json'
            elif isinstance(file_data, str):
                body = file_data.encode('utf-8')
                content_type = content_type or 'text/plain'
            else:
                body = file_data
                content_type = content_type or 'application/octet-stream'
            
            self.s3_client.put_object(
                Bucket=self.bucket,
                Key=s3_key,
                Body=body,
                ContentType=content_type,
                Metadata={
                    'case_number': self.case_number,
                    'unique_case_folder': self.unique_case_folder,
                    'process_uuid': self.process_uuid,  # For backward compatibility
                    'upload_timestamp': datetime.now().isoformat(),
                    'category': category
                }
            )
            
            s3_url = f"s3://{self.bucket}/{s3_key}"
            logger.info(f"✅ Uploaded to {s3_url}")
            return s3_url
            
        except Exception as e:
            logger.error(f"❌ Failed to upload {filename} to {category}: {e}")
            raise

    def upload_stream(self, stream, category: str, filename: str, content_type: str = None) -> str:
        """Upload stream data to S3"""
        s3_key = f"{self.folders[category]}/{filename}"
        
        try:
            self.s3_client.upload_fileobj(
                stream,
                Bucket=self.bucket,
                Key=s3_key,
                ExtraArgs={
                    'ContentType': content_type or 'application/octet-stream',
                    'Metadata': {
                        'case_number': self.case_number,
                        'unique_case_folder': self.unique_case_folder,
                        'process_uuid': self.process_uuid,  # For backward compatibility
                        'upload_timestamp': datetime.now().isoformat(),
                        'category': category
                    }
                }
            )
            
            s3_url = f"s3://{self.bucket}/{s3_key}"
            logger.info(f"✅ Uploaded stream to {s3_url}")
            return s3_url
            
        except Exception as e:
            logger.error(f"❌ Failed to upload stream {filename} to {category}: {e}")
            raise

    def get_process_summary(self) -> Dict[str, Any]:
        """Return process summary for logging"""
        return {
            'case_number': self.case_number,
            'unique_case_folder': self.unique_case_folder,
            'process_uuid': self.process_uuid,  # For backward compatibility
            'base_path': self.base_path,
            'folders': self.folders,
            'bucket': self.bucket,
            'created_at': datetime.now().isoformat()
        }

    def cleanup_case_folder(self) -> bool:
        """Delete entire case folder from S3"""
        try:
            # List all objects in the case folder
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket,
                Prefix=self.base_path
            )
            
            if 'Contents' in response:
                objects_to_delete = [{'Key': obj['Key']} for obj in response['Contents']]
                
                self.s3_client.delete_objects(
                    Bucket=self.bucket,
                    Delete={'Objects': objects_to_delete}
                )
                
                logger.info(f"✅ Cleaned up case folder: {self.base_path}")
                return True
            else:
                logger.info(f"No objects found in case folder: {self.base_path}")
                return True
                
        except Exception as e:
            logger.error(f"❌ Failed to cleanup case folder: {e}")
            return False
    
    def list_existing_case_runs(self, base_case_number: str) -> list:
        """List all existing runs for a case number"""
        try:
            clean_case = self._clean_case_number(base_case_number)
            prefix = f"cases/{clean_case}"
            
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket,
                Prefix=prefix,
                Delimiter='/'
            )
            
            existing_runs = []
            if 'CommonPrefixes' in response:
                for prefix_info in response['CommonPrefixes']:
                    folder_name = prefix_info['Prefix'].split('/')[-2]
                    existing_runs.append(folder_name)
            
            return sorted(existing_runs)
            
        except Exception as e:
            logger.error(f"Failed to list existing case runs: {e}")
            return []

    # BACKWARD COMPATIBILITY METHODS
    @property
    def process_uuid_alias(self):
        """Alias for process_uuid to ensure backward compatibility"""
        return self.unique_case_folder
    
    def cleanup_process(self) -> bool:
        """Backward compatibility method - maps to cleanup_case_folder"""
        return self.cleanup_case_folder()
    def download_json(self, s3_key):
        """Download JSON file from S3 and return as dict"""
        try:
            # Remove leading slash if present
            if s3_key.startswith('/'):
                s3_key = s3_key[1:]
            
            # Construct full S3 key
            full_key = f"{self.base_path}/{s3_key}"
            
            # Download from S3
            response = self.s3_client.get_object(Bucket=self.bucket, Key=full_key)
            json_content = response['Body'].read().decode('utf-8')
            
            # Parse JSON
            import json
            return json.loads(json_content)
            
        except self.s3_client.exceptions.NoSuchKey:
            print(f"File not found in S3: {full_key}")
            return None
        except Exception as e:
            print(f"Error downloading JSON from S3: {str(e)}")
            return None
