import json
import logging
from typing import Dict, Any, Optional
from static.unified_s3_manager import UnifiedS3Manager
import datetime

logger = logging.getLogger(__name__)

class JSONHandler:
    """Centralized JSON handling with unified S3 storage"""

    def __init__(self, case_number: str, s3_manager: UnifiedS3Manager = None):
        self.case_number = case_number
        self.s3_manager = s3_manager or UnifiedS3Manager(case_number)
        self._data_cache: Optional[Dict[str, Any]] = None
        self.json_filename = f"{case_number}.json"
        
        logger.info(f"JSONHandler initialized for case: {case_number}")

    def load_json(self) -> Dict[str, Any]:
        """Load JSON data from local file with S3 backup"""
        if self._data_cache is not None:
            return self._data_cache

        try:
            # Try to load from local file first
            with open(self.json_filename, 'r', encoding='utf-8') as f:
                self._data_cache = json.load(f)
                
            # Backup to S3
            self.s3_manager.upload_file(
                self._data_cache, 
                'json_data', 
                f"input_{self.json_filename}",
                'application/json'
            )
            
            logger.info(f"✅ Loaded JSON from local file: {self.json_filename}")
            return self._data_cache
            
        except FileNotFoundError:
            logger.error(f"❌ JSON file not found: {self.json_filename}")
            return {}
        except json.JSONDecodeError as e:
            logger.error(f"❌ Invalid JSON in file: {e}")
            return {}

    def save_json(self, data: Dict[str, Any]) -> bool:
        """Save JSON data locally and to S3"""
        try:
            # Save locally
            with open(self.json_filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            
            # Save to S3
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            s3_filename = f"updated_{self.json_filename}_{timestamp}"
            self.s3_manager.upload_file(data, 'json_data', s3_filename, 'application/json')
            
            self._data_cache = data
            logger.info(f"✅ Saved JSON locally and to S3")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to save JSON: {e}")
            return False

    def update_field(self, field_path: str, value: Any) -> bool:
        """Update a specific field in the JSON data using dot notation"""
        try:
            data = self.load_json()
            keys = field_path.split('.')
            current = data
            
            for key in keys[:-1]:
                if key not in current or not isinstance(current[key], dict):
                    current[key] = {}
                current = current[key]
                
            current[keys[-1]] = value
            return self.save_json(data)
            
        except Exception as e:
            logger.error(f"Error updating field {field_path}: {e}")
            return False

    def get_field(self, field_path: str, default: Any = None) -> Any:
        """Get a specific field from JSON data using dot notation"""
        try:
            data = self.load_json()
            keys = field_path.split('.')
            current = data
            
            for key in keys:
                if isinstance(current, dict) and key in current:
                    current = current[key]
                else:
                    return default
                    
            return current
            
        except Exception as e:
            logger.error(f"Error getting field {field_path}: {e}")
            return default

    def get_client_reference(self) -> str:
        """Extract client reference number"""
        try:
            data = self.load_json()
            return data.get("drafter_field", {}).get("generalInformation", {}).get("clientReferenceNo", self.case_number)
        except Exception as e:
            logger.warning(f"Could not read clientReferenceNo: {e}")
            return self.case_number

    def clear_cache(self):
        self._data_cache = None
