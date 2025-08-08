import logging
import json
from datetime import datetime
from typing import List, Dict, Any
import sys
import io
import asyncio

if sys.platform.startswith('win'):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

class UnifiedLogger:
    """Centralized logging system with S3 integration"""
    
    def __init__(self, s3_manager, module_name: str):
        self.s3_manager = s3_manager
        self.module_name = module_name
        self.log_entries: List[Dict[str, Any]] = []
        
        # Setup console logger
        self.console_logger = logging.getLogger(f"{module_name}_{s3_manager.process_uuid}")
        self.console_logger.setLevel(logging.INFO)
        
        if not self.console_logger.handlers:
            # Wrap sys.stdout with UTF-8 encoding for emoji/log safety
            utf8_stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
            handler = logging.StreamHandler(utf8_stdout)

            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.console_logger.addHandler(handler)
    
    def log(self, level: str, message: str, extra_data: Dict[str, Any] = None):
        """Log message with optional extra data"""
        entry = {
            'timestamp': datetime.now().isoformat(),
            'module': self.module_name,
            'level': level.upper(),
            'message': message,
            'process_uuid': self.s3_manager.process_uuid,
            'case_number': self.s3_manager.case_number
        }
        
        if extra_data:
            entry['extra_data'] = extra_data
            
        self.log_entries.append(entry)
        
        # Also log to console
        getattr(self.console_logger, level.lower())(f"[{self.module_name}] {message}")
    
    def info(self, message: str, extra_data: Dict[str, Any] = None):
        self.log('INFO', message, extra_data)
    
    def warning(self, message: str, extra_data: Dict[str, Any] = None):
        self.log('WARNING', message, extra_data)
    
    def error(self, message: str, extra_data: Dict[str, Any] = None):
        self.log('ERROR', message, extra_data)
    
    def debug(self, message: str, extra_data: Dict[str, Any] = None):
        self.log('DEBUG', message, extra_data)
    
    def save_logs(self) -> str:
        """Save all logs to S3"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{self.module_name}_{timestamp}.json"
            
            log_data = {
                'module': self.module_name,
                'process_uuid': self.s3_manager.process_uuid,
                'case_number': self.s3_manager.case_number,
                'log_count': len(self.log_entries),
                'logs': self.log_entries
            }
            
            s3_url = self.s3_manager.upload_file(log_data, 'logs', filename, 'application/json')
            self.info(f"Logs saved to S3: {s3_url}")
            return s3_url
            
        except Exception as e:
            self.console_logger.error(f"Failed to save logs to S3: {e}")
            return None