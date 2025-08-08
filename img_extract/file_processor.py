import os
import zipfile
from pathlib import Path
from typing import Tuple, List

class FileProcessor:
    """Handle file unzipping and categorization"""
    
    def unzip_and_categorize(self, zip_path: str, extract_dir: str) -> Tuple[List[str], List[str], List[str]]:
        """
        Unzip file and categorize contents
        
        Returns:
            Tuple of (images, pdfs, others)
        """
        try:
            # Create extraction directory
            os.makedirs(extract_dir, exist_ok=True)
            
            # Unzip file
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            
            # Categorize files
            images = []
            pdfs = []
            others = []
            
            # Walk through extracted files
            for root, dirs, files in os.walk(extract_dir):
                for file in files:
                    ext = Path(file).suffix.lower()
                    full_path = os.path.join(root, file)
                    
                    if ext in ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.webp']:
                        images.append(full_path)
                    elif ext == '.pdf':
                        pdfs.append(full_path)
                    else:
                        others.append(full_path)
            
            print(f"📁 Categorized: {len(images)} images, {len(pdfs)} PDFs, {len(others)} others")
            return images, pdfs, others
            
        except Exception as e:
            print(f"❌ Failed to unzip and categorize: {e}")
            return [], [], []
