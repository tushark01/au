import os
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from playwright.async_api import Page
from static.unified_s3_manager import UnifiedS3Manager
from static.unified_logger import UnifiedLogger
import streamlit as st

async def zip_download(page: Page, case_number: str, s3_manager: UnifiedS3Manager) -> str:
    """
    Enhanced document download with local extraction functionality
    
    Args:
        page: Playwright page object
        case_number: Case number for organizing files
        s3_manager: S3 manager for cloud storage
        
    Returns:
        str: S3 URL of uploaded ZIP file
    """
    
    doc_logger = UnifiedLogger(s3_manager, "document_download")
    
    try:
        # Navigate to Documents tab
        doc_logger.info("📂 Navigating to Documents tab...")
        await page.locator("//a[@data-label=\"Documents\"]").click()
        await page.wait_for_timeout(3000)

        # Initiate download
        doc_logger.info("⬇️ Downloading all documents (zip)...")
        
        async with page.expect_download(timeout=45000) as download_info:
            await page.get_by_role("button", name="Download All").click()
        
        download = await download_info.value
        doc_logger.info("📥 Download initiated.")

        # Get download path
        download_path = await download.path()
        if download_path is None:
            raise Exception("❌ Failed to get download path")

        # Create unique filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_filename = f"{case_number}_{timestamp}.zip"
        
        # Define local case folder structure
        local_case_folder = f"local_documents/{case_number}"
        os.makedirs(local_case_folder, exist_ok=True)
        
        # Copy ZIP to local folder
        local_zip_path = os.path.join(local_case_folder, unique_filename)
        shutil.copyfile(download_path, local_zip_path)
        doc_logger.info(f"💾 ZIP saved locally: {local_zip_path}")
        
        # Create extraction folder
        extract_folder = os.path.join(local_case_folder, "extracted")
        os.makedirs(extract_folder, exist_ok=True)
        
        # Extract ZIP contents locally
        try:
            with zipfile.ZipFile(local_zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_folder)
                extracted_files = zip_ref.namelist()
                doc_logger.info(f"📂 ZIP extracted to: {extract_folder}")
                doc_logger.info(f"📄 Extracted {len(extracted_files)} files")
        except zipfile.BadZipFile:
            doc_logger.error("❌ Invalid ZIP file format")
            raise Exception("Downloaded file is not a valid ZIP archive")
        except Exception as e:
            doc_logger.error(f"❌ ZIP extraction failed: {e}")
            raise Exception(f"Failed to extract ZIP file: {e}")
        
        # Upload original ZIP to S3
        doc_logger.info("☁️ Uploading ZIP to S3...")
        try:
            with open(download_path, 'rb') as file:
                s3_url = s3_manager.upload_file(
                    file.read(),
                    'downloads',
                    unique_filename,
                    'application/zip'
                )
            doc_logger.info(f"✅ Uploaded to S3: {s3_url}")
        except Exception as e:
            doc_logger.error(f"❌ S3 upload failed: {e}")
            # Continue even if S3 upload fails, as local extraction succeeded
            s3_url = f"local://{local_zip_path}"
        
        # Store local extraction path in session state
        session_key = f'local_docs_path_{case_number}'
        if 'streamlit' in globals() or 'st' in globals():
            try:
                st.session_state[session_key] = extract_folder
                doc_logger.info(f"💾 Stored local path in session: {session_key}")
            except Exception as e:
                doc_logger.warning(f"Could not store in session state: {e}")
        
        # Clean up original download file
        try:
            os.remove(download_path)
            doc_logger.info("🗑️ Cleaned up original download file")
        except Exception as e:
            doc_logger.warning(f"Could not clean up original file: {e}")
        
        # Log summary
        doc_logger.info("="*50)
        doc_logger.info("📊 DOWNLOAD SUMMARY")
        doc_logger.info(f"📁 Local ZIP: {local_zip_path}")
        doc_logger.info(f"📂 Extracted to: {extract_folder}")
        doc_logger.info(f"📄 Files extracted: {len(extracted_files)}")
        doc_logger.info(f"☁️ S3 URL: {s3_url}")
        doc_logger.info("="*50)
        
        return s3_url

    except Exception as e:
        doc_logger.error(f"❌ Failed to download documents: {e}")
        raise
    
    finally:
        doc_logger.save_logs()


def get_local_documents_path(case_number: str) -> str:
    """
    Get the local documents path for the specified case
    
    Args:
        case_number: Case number to look up
        
    Returns:
        str: Path to extracted documents or None if not found
    """
    # Check session state first
    session_key = f'local_docs_path_{case_number}'
    if 'streamlit' in globals() or 'st' in globals():
        try:
            if session_key in st.session_state:
                path = st.session_state[session_key]
                if os.path.exists(path):
                    return path
        except Exception:
            pass
    
    # Fallback to standard pattern
    local_case_folder = f"local_documents/{case_number}/extracted"
    if os.path.exists(local_case_folder):
        return local_case_folder
    
    return None


def list_local_documents(folder_path: str) -> dict:
    """
    List and categorize documents in the local folder
    
    Args:
        folder_path: Path to the extracted documents folder
        
    Returns:
        dict: Categorized file lists
    """
    if not folder_path or not os.path.exists(folder_path):
        return {"images": [], "pdfs": [], "others": [], "total": 0}
    
    # Get all files recursively
    file_list = list(Path(folder_path).rglob("*"))
    file_list = [f for f in file_list if f.is_file()]  # Only files, not directories
    
    # Categorize files
    images = [f for f in file_list if f.suffix.lower() in [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp"]]
    pdfs = [f for f in file_list if f.suffix.lower() == ".pdf"]
    others = [f for f in file_list if f not in images and f not in pdfs]
    
    return {
        "images": sorted(images, key=lambda x: x.name),
        "pdfs": sorted(pdfs, key=lambda x: x.name),
        "others": sorted(others, key=lambda x: x.name),
        "total": len(file_list)
    }


def cleanup_local_documents(case_number: str) -> bool:
    """
    Clean up local documents for a specific case
    
    Args:
        case_number: Case number to clean up
        
    Returns:
        bool: True if cleanup successful, False otherwise
    """
    try:
        local_case_folder = f"local_documents/{case_number}"
        
        if os.path.exists(local_case_folder):
            # Remove the entire case folder
            shutil.rmtree(local_case_folder)
            
            # Clear from session state if available
            if 'streamlit' in globals() or 'st' in globals():
                try:
                    session_key = f'local_docs_path_{case_number}'
                    if session_key in st.session_state:
                        del st.session_state[session_key]
                except Exception:
                    pass
            
            return True
        else:
            return False
            
    except Exception as e:
        print(f"❌ Failed to clean up local documents: {e}")
        return False


def cleanup_all_local_documents() -> int:
    """
    Clean up all local document folders
    
    Returns:
        int: Number of folders cleaned up
    """
    try:
        base_folder = "local_documents"
        if not os.path.exists(base_folder):
            return 0
        
        # Get all case folders
        case_folders = [f for f in os.listdir(base_folder) if os.path.isdir(os.path.join(base_folder, f))]
        
        # Remove each case folder
        cleaned_count = 0
        for case_folder in case_folders:
            try:
                folder_path = os.path.join(base_folder, case_folder)
                shutil.rmtree(folder_path)
                cleaned_count += 1
            except Exception as e:
                print(f"❌ Failed to clean up {case_folder}: {e}")
        
        # Remove base folder if empty
        try:
            if not os.listdir(base_folder):
                os.rmdir(base_folder)
        except Exception:
            pass
        
        # Clear all related session state
        if 'streamlit' in globals() or 'st' in globals():
            try:
                keys_to_remove = [key for key in st.session_state.keys() if key.startswith('local_docs_path_')]
                for key in keys_to_remove:
                    del st.session_state[key]
            except Exception:
                pass
        
        return cleaned_count
        
    except Exception as e:
        print(f"❌ Failed to clean up all local documents: {e}")
        return 0


def get_document_stats(case_number: str) -> dict:
    """
    Get statistics about documents for a case
    
    Args:
        case_number: Case number to analyze
        
    Returns:
        dict: Document statistics
    """
    folder_path = get_local_documents_path(case_number)
    
    if not folder_path:
        return {"exists": False, "total_files": 0, "total_size": 0}
    
    try:
        file_list = list(Path(folder_path).rglob("*"))
        file_list = [f for f in file_list if f.is_file()]
        
        total_size = sum(f.stat().st_size for f in file_list)
        
        # Categorize files
        categories = list_local_documents(folder_path)
        
        return {
            "exists": True,
            "folder_path": folder_path,
            "total_files": len(file_list),
            "total_size": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "images": len(categories["images"]),
            "pdfs": len(categories["pdfs"]),
            "others": len(categories["others"])
        }
        
    except Exception as e:
        return {"exists": False, "error": str(e), "total_files": 0, "total_size": 0}


# Utility function for file size formatting
def format_file_size(size_bytes: int) -> str:
    """
    Format file size in human readable format
    
    Args:
        size_bytes: Size in bytes
        
    Returns:
        str: Formatted size string
    """
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB"]
    i = 0
    size = float(size_bytes)
    
    while size >= 1024.0 and i < len(size_names) - 1:
        size /= 1024.0
        i += 1
    
    return f"{size:.1f} {size_names[i]}"

# Main execution guard
if __name__ == "__main__":
    print("📁 Document Download Module")
    print("This module handles document downloading and local extraction.")
    print("Import this module to use its functions in your main application.")