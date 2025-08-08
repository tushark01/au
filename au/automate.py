from aiohttp import ClientError
import streamlit as st
import asyncio
import os
import sys
from datetime import datetime
import time
import tempfile
import zipfile
from pathlib import Path
import base64
from dotenv import load_dotenv
import requests
from PIL import Image
from io import BytesIO
import boto3

from get_pre_url import generate_presigned_url
from zip_utils import get_latest_zip_filename, get_pdf_files_from_s3

load_dotenv()

import subprocess
import sys
from pathlib import Path

@st.cache_resource
def install_playwright_on_first_run():
    """Install Playwright browsers on first app load - cached to avoid repeated installs"""
    
    # Check if browsers are already installed
    playwright_cache = Path.home() / ".cache" / "ms-playwright"
    chromium_dirs = list(playwright_cache.glob("chromium-*")) if playwright_cache.exists() else []
    
    if chromium_dirs:
        st.success("✅ Playwright browsers already installed!")
        return True
    
    # Install browsers if not found
    try:
        with st.spinner("🎭 Installing Playwright browsers... This may take 1-2 minutes on first deployment."):
            
            # Install Chromium browser
            result = subprocess.run([
                sys.executable, "-m", "playwright", "install", "chromium"
            ], capture_output=True, text=True, check=True)
            
            # Try to install system dependencies (may fail on Streamlit Cloud but worth trying)
            try:
                subprocess.run([
                    sys.executable, "-m", "playwright", "install-deps", "chromium"
                ], capture_output=True, text=True, check=True)
            except subprocess.CalledProcessError:
                # Dependencies might fail, but browsers can still work
                pass
                
        st.success("✅ Playwright browsers installed successfully!")
        return True
        
    except subprocess.CalledProcessError as e:
        st.error(f"❌ Failed to install Playwright browsers: {e.stderr}")
        st.info("💡 Consider using Selenium as an alternative for better deployment compatibility.")
        return False

# Call this before your app logic starts
if 'playwright_ready' not in st.session_state:
    st.session_state['playwright_ready'] = install_playwright_on_first_run()

if not st.session_state['playwright_ready']:
    st.error("⚠️ Cannot run automation without Playwright browsers")
    st.stop()

st.set_page_config(page_title="GFGC Drafter-CoPilot", page_icon="🤖", layout="centered")

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
img_extract_path = os.path.join(parent_dir, 'img_extract')
doc_extract_path = os.path.join(parent_dir, 'doc_extract')

# Add paths to sys.path
sys.path.insert(0, parent_dir)
sys.path.insert(0, img_extract_path)
sys.path.insert(0, doc_extract_path)

from au.drafter_field import drafter_field_main
from au.mobileapp import mobileapp_main
from au.login_agent import start_salesforce_session
from static.document import document_field_main
from au.case_search import case_search_main
from static.json_utils import JSONHandler
from static.unified_s3_manager import UnifiedS3Manager
from static.unified_logger import UnifiedLogger
from drafter_manual_input import DrafterManualInputAssistant
from static.drafter_assistant_gif import show_floating_assistant
from static.showDoc_buttonUI import display_local_document_manager
from static.document_download import zip_download

# **FAVICON SETUP WITH ERROR HANDLING**
favicon_url = generate_presigned_url("dfautoindusind", "UI_images/copilot_favicon.jpeg")
header_url = generate_presigned_url("dfautoindusind", "UI_images/header.jpeg")
show_floating_assistant("👋 Hello! I'm your Drafter Assistant.","https://media1.giphy.com/media/v1.Y2lkPTc5MGI3NjExY3BmYzg0MzhpbWQ0a3djanAzM3l6dmRhanhtdXF3cmVuZTYxZjh6aiZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9cw/c1hhT9nPjLRkLeK83H/giphy.gif")

if favicon_url:
    try:
        icon_bytes = requests.get(favicon_url).content
        icon_img = Image.open(BytesIO(icon_bytes))
    except Exception as e:
        st.warning(f"⚠️ Couldn't load favicon: {e}")

# **IMPORT WITH ERROR HANDLING**
try:
    from img_extract.main import DocumentExtractionPipeline
except ImportError as e:
    st.error(f"❌ Import Error: {e}")
    st.error("🔧 **Troubleshooting Information:**")
    st.code(f"""
Current directory: {current_dir}
Parent directory: {parent_dir}
img_extract path: {img_extract_path}
img_extract exists: {os.path.exists(img_extract_path)}
main.py exists: {os.path.exists(os.path.join(img_extract_path, 'main.py'))}
s3_downloader.py exists: {os.path.exists(os.path.join(img_extract_path, 's3_downloader.py'))}
Python path: {sys.path[:3]}...
    """)
    st.stop()

# **DOCUMENT ANALYZER IMPORT**
try:
    from doc_extract.docs_analyzer import DocumentAnalyzer
except ImportError as e:
    st.error(f"❌ Document Analyzer Import Error: {e}")
    st.error("🔧 **Document Analyzer Troubleshooting:**")
    st.code(f"""
doc_extract path: {doc_extract_path}
doc_extract exists: {os.path.exists(doc_extract_path)}
docs_analyzer.py exists: {os.path.exists(os.path.join(doc_extract_path, 'docs_analyzer.py'))}
    """)
    st.stop()

# Custom CSS for better UI
st.markdown("""
<style>
    .main-header {
        text-align: center;
        color: #1f77b4;
        font-size: 2.5rem;
        margin-bottom: 2rem;
    }
    .case-info {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 1rem 0;
    }
    .stButton>button {
        width: 100%;
    }
    .field-container {
        margin-bottom: 1rem;
        padding: 0.5rem;
        border-radius: 0.25rem;
        background-color: #f8f9fa;
    }
    .required-field {
        color: #dc3545;
        font-weight: bold;
    }
    .progress-container {
        background-color: #f8f9fa;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 1rem 0;
        border: 1px solid #dee2e6;
    }
    .step-status {
        display: flex;
        align-items: center;
        margin: 0.5rem 0;
        padding: 0.5rem;
        border-radius: 0.25rem;
    }
    .step-completed {
        background-color: #d4edda;
        color: #155724;
        border: 1px solid #c3e6cb;
    }
    .step-running {
        background-color: #fff3cd;
        color: #856404;
        border: 1px solid #ffeaa7;
    }
    .step-pending {
        background-color: #f8f9fa;
        color: #6c757d;
        border: 1px solid #dee2e6;
    }
    .step-failed {
        background-color: #f8d7da;
        color: #721c24;
        border: 1px solid #f5c6cb;
    }
</style>
""", unsafe_allow_html=True)

if header_url:
    try:
        header_bytes = requests.get(header_url).content
        header_img = Image.open(BytesIO(header_bytes))
        st.image(header_img, use_container_width=True)
    except Exception as e:
        st.warning(f"⚠️ Couldn't load header image: {e}")

st.markdown('<h1 class="main-header">🤖 GFGC Drafter Co-Pilot</h1>', unsafe_allow_html=True)

# **PROGRESS TRACKING FUNCTIONS**
def update_progress_bar(progress_bar, value, text):
    """Update progress bar"""
    progress_bar.progress(value, text=text)
    time.sleep(0.1)

def show_step_status(step_name, status, message=""):
    """Show step status with proper styling"""
    status_classes = {
        'completed': 'step-completed',
        'running': 'step-running',
        'pending': 'step-pending',
        'failed': 'step-failed'
    }
    
    status_icons = {
        'completed': '✅',
        'running': '🔄',
        'pending': '⏳',
        'failed': '❌'
    }
    
    st.markdown(f"""
    <div class="step-status {status_classes.get(status, 'step-pending')}">
        {status_icons.get(status, '⏳')} <strong>{step_name}</strong>
        {f": {message}" if message else ""}
    </div>
    """, unsafe_allow_html=True)

def create_progress_container():
    """Create progress tracking container"""
    return st.container()

# HELPER FUNCTIONS - Define all functions before they're called
async def extract_pdfs_from_zip(case_number, s3_manager, progress_container=None):
    """Extract PDFs from ZIP file and upload to S3 extracted_files folder"""
    try:
        if progress_container:
            with progress_container:
                show_step_status("PDF Extraction", "running", "Locating ZIP file...")

        zip_filename = get_latest_zip_filename(s3_manager, case_number)
        if not zip_filename:
            if progress_container:
                with progress_container:
                    show_step_status("PDF Extraction", "failed", "No ZIP file found")
            st.warning("⚠️ No ZIP file found for extraction")
            return False
                
        zip_s3_path = f"{s3_manager.base_path}/downloads/{zip_filename}"
        
        with tempfile.TemporaryDirectory() as temp_main_dir:
            temp_zip_path = os.path.join(temp_main_dir, f"temp_{zip_filename}")
            extract_dir = os.path.join(temp_main_dir, "extracted")

            if progress_container:
                with progress_container:
                    show_step_status("PDF Extraction", "running", "Downloading ZIP file...")
            
            try:
                s3_manager.s3_client.download_file(
                    s3_manager.bucket,
                    zip_s3_path,
                    temp_zip_path
                )
                
            except Exception as download_error:
                if progress_container:
                    with progress_container:
                        show_step_status("PDF Extraction", "failed", f"Download failed: {download_error}")
                st.error(f"❌ Failed to download ZIP file: {download_error}")
                return False
            
            os.makedirs(extract_dir, exist_ok=True)
            pdf_count = 0

            if progress_container:
                with progress_container:
                    show_step_status("PDF Extraction", "running", "Extracting PDF files...")

            try:
                with zipfile.ZipFile(temp_zip_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)
                
                for root, dirs, files in os.walk(extract_dir):
                    for file in files:
                        if file.lower().endswith('.pdf'):
                            pdf_path = os.path.join(root, file)
                            
                            try:
                                file_size = os.path.getsize(pdf_path)
                                
                                if file_size > 0:
                                    with open(pdf_path, 'rb') as pdf_file:
                                        s3_manager.upload_file(
                                            pdf_file.read(),
                                            'extracted_files',
                                            file,
                                            'application/pdf'
                                        )
                                    pdf_count += 1
                                else:
                                    st.warning(f"⚠️ Skipping empty PDF: {file}")
                                    
                            except Exception as upload_error:
                                st.warning(f"⚠️ Failed to process {file}: {upload_error}")
                
            except zipfile.BadZipFile:
                if progress_container:
                    with progress_container:
                        show_step_status("PDF Extraction", "failed", "Invalid ZIP file format")
                st.error("❌ Invalid ZIP file format")
                return False
            except Exception as extract_error:
                if progress_container:
                    with progress_container:
                        show_step_status("PDF Extraction", "failed", f"Failed to extract ZIP file: {extract_error}")
                st.error(f"❌ Failed to extract ZIP file: {extract_error}")
                return False
            
        if pdf_count > 0:
            if progress_container:
                with progress_container:
                    show_step_status("PDF Extraction", "completed", f"Extracted {pdf_count} PDF files")

            return True
        else:
            if progress_container:
                with progress_container:
                    show_step_status("PDF Extraction", "failed", "No valid PDF files found")

            st.warning("⚠️ No valid PDF files found in ZIP")
            return False
            
    except Exception as e:
        if progress_container:
            with progress_container:
                show_step_status("PDF Extraction", "failed", f"Error: {str(e)}")

        st.error(f"❌ Failed to extract PDFs: {str(e)}")
        return False

async def run_image_extraction_pipeline(case_number, s3_manager, progress_container=None):
    """Run the image extraction pipeline on the downloaded zip file"""
    try:
        if progress_container:
            with progress_container:
                show_step_status("Image Extraction", "running", "Initializing pipeline...")

        zip_filename = get_latest_zip_filename(s3_manager, case_number)
        
        if not zip_filename:
            if progress_container:
                with progress_container:
                    show_step_status("Image Extraction", "failed", "No zip file found")

            return {
                'success': False,
                'error': 'No zip file found in downloads folder'
            }
        if progress_container:
            with progress_container:
                show_step_status("Image Extraction", "running", "Processing images...")
        
        zip_s3_path = f"{s3_manager.base_path}/downloads/{zip_filename}"
                
        pipeline = DocumentExtractionPipeline()
        
        bucket_name = s3_manager.bucket
        s3_url = f"s3://{bucket_name}/{zip_s3_path}"
        
        result_json, s3_result_key = await pipeline.process_s3_zip_direct(s3_url)
        
        if result_json:
            if progress_container:
                with progress_container:
                    show_step_status("Image Extraction", "running", "Uploading results...")

            extraction_key = f"json_data/extracted_analysis_{case_number}.json"
            s3_manager.upload_file(result_json, 'json_data', f'extracted_analysis_{case_number}.json')

            if progress_container:
                with progress_container:
                    show_step_status("Image Extraction", "completed", "Images processed successfully")

            return {
                'success': True,
                'json_data': result_json,
                's3_key': extraction_key,
                'zip_filename': zip_filename
            }
        else:
            if progress_container:
                with progress_container:
                    show_step_status("Image Extraction", "failed", "No data extracted")

            return {
                'success': False,
                'error': 'No data extracted from images'
            }
            
    except Exception as e:
        if progress_container:
            with progress_container:
                show_step_status("Image Extraction", "failed", f"Error: {str(e)}")

        st.error(f"Image extraction error: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }

async def run_document_analysis_pipeline(case_number, s3_manager,progress_container=None):
    """Run the document analysis pipeline with PDF display"""
    try:
        if progress_container:
            with progress_container:
                show_step_status("Document Analysis", "running", "Searching for PDF files...")

        pdf_files = get_pdf_files_from_s3(s3_manager, case_number)
        
        if not pdf_files:
            if progress_container:
                with progress_container:
                    show_step_status("Document Analysis", "failed", "No PDF files found")

            st.warning("⚠️ No PDF files found in extracted_files folder")
            return {
                'success': False,
                'error': 'No PDF files found in extracted_files folder'
            }
        if progress_container:
            with progress_container:
                show_step_status("Document Analysis", "running", f"Initializing analyzer for {len(pdf_files)} files...")
        
        try:
            doc_analyzer = DocumentAnalyzer()
        except Exception as init_error:
            if progress_container:
                with progress_container:
                    show_step_status("Document Analysis", "failed", f"Initialization failed: {init_error}")

            st.error(f"❌ Failed to initialize DocumentAnalyzer: {init_error}")
            return {
                'success': False,
                'error': f'Failed to initialize DocumentAnalyzer: {init_error}'
            }
        
        with tempfile.TemporaryDirectory() as temp_dir:
            local_pdf_paths = []
            if progress_container:
                with progress_container:
                    show_step_status("Document Analysis", "running", "Downloading PDF files...")
            
            for pdf_file in pdf_files:
                try:
                    local_path = os.path.join(temp_dir, pdf_file['filename'])
                    s3_manager.s3_client.download_file(
                        s3_manager.bucket, 
                        pdf_file['key'], 
                        local_path
                    )
                    
                    if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
                        local_pdf_paths.append(local_path)
                    else:
                        st.warning(f"⚠️ Downloaded file is empty or missing: {pdf_file['filename']}")
                        
                except Exception as download_error:
                    st.warning(f"⚠️ Failed to download {pdf_file['filename']}: {download_error}")
            
            if not local_pdf_paths:
                if progress_container:
                    with progress_container:
                        show_step_status("Document Analysis", "failed", "No files downloaded successfully")

                return {
                    'success': False,
                    'error': 'Failed to download any PDF files for processing'
                }
            
            if progress_container:
                with progress_container:
                    show_step_status("Document Analysis", "running", "Analyzing documents...")
          
            try:
                if hasattr(doc_analyzer.analyze_property_documents, '__call__'):
                    try:
                        result_json = await doc_analyzer.analyze_property_documents(local_pdf_paths)
                    except TypeError:
                        result_json = doc_analyzer.analyze_property_documents(local_pdf_paths)
                else:
                    result_json = doc_analyzer.analyze_property_documents(local_pdf_paths)
                    
            except Exception as analysis_error:
                if progress_container:
                    with progress_container:
                        show_step_status("Document Analysis", "failed", f"Analysis failed: {analysis_error}")

                st.error(f"❌ Document analysis failed: {analysis_error}")
                return {
                    'success': False,
                    'error': f'Document analysis failed: {analysis_error}'
                }
        
        if result_json:
            if progress_container:
                with progress_container:
                    show_step_status("Document Analysis", "running", "Uploading results...")

            
            doc_analysis_key = f"json_data/document_analysis_{case_number}.json"
            
            try:
                s3_manager.upload_file(result_json, 'json_data', f'document_analysis_{case_number}.json')
            except Exception as upload_error:
                st.warning(f"⚠️ Failed to upload results to S3: {upload_error}")
            
            if progress_container:
                with progress_container:
                    show_step_status("Document Analysis", "completed", f"Analysis completed for {len(pdf_files)} documents")
            return {
                'success': True,
                'json_data': result_json,
                's3_key': doc_analysis_key,
                'pdf_count': len(pdf_files)
            }
        else:
            if progress_container:
                with progress_container:
                    show_step_status("Document Analysis", "failed", "No data returned from analysis")
            st.warning("⚠️ Document analysis returned no data")
            return {
                'success': False,
                'error': 'No data extracted from documents'
            }
            
    except Exception as e:
        if progress_container:
            with progress_container:
                show_step_status("Document Analysis", "failed", f"Pipeline error: {str(e)}")
        st.error(f"❌ Document analysis pipeline error: {str(e)}")
        import traceback
        st.error(f"🔍 Detailed error: {traceback.format_exc()}")
        
        return {
            'success': False,
            'error': str(e)
        }

async def run_initial_automation():
    """Run the initial automation phase until blank fields are detected"""
    # **INITIALIZE ALL VARIABLES AT THE TOP TO PREVENT SCOPE ERRORS**
    s3_manager = None
    main_logger = None
    playwright = None
    browser = None
    context = None
    page = None
    current_url = None  # FIXED: Initialize current_url to None
    
    # **WORKFLOW STATUS VARIABLES - INITIALIZE BEFORE USE**
    extraction_result = {'success': False, 'error': 'Not started'}
    document_analysis_result = {'success': False, 'error': 'Not started'}  
    drafter_done = False
    doc_download_result = False

        # Create progress tracking
    progress_container = st.container()
    main_progress = st.progress(0, text="Starting automation...")

    try:
        with progress_container:
            st.markdown('<div class="progress-container">', unsafe_allow_html=True)
            st.markdown("### 🔄 Automation Progress")

            show_step_status("Initialization", "running", "Setting up S3 manager and logger...")
            update_progress_bar(main_progress, 10, "Initializing...")
            
        # Initialize S3 manager with case number
        s3_manager = UnifiedS3Manager(case_number.strip())
        main_logger = UnifiedLogger(s3_manager, "main_controller")
        
        st.session_state['s3_manager'] = s3_manager
        with progress_container:
            show_step_status("Initialization", "completed", "S3 manager and logger initialized")
            show_step_status("Salesforce Login", "running", "Starting browser session...")
            update_progress_bar(main_progress, 20, "Connecting to Salesforce...")
            show_floating_assistant("Login in to Salesforce portal, please wait...","https://media3.giphy.com/media/v1.Y2lkPTc5MGI3NjExMno1bmoyaXQ2MHdnd3Fjem51dDFtNTE5YzVpZWkyeXlhbWNxNmx5dSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9cw/XtU1Ja4CGWfkcZgkqs/giphy.gif")


        # Start Salesforce session in headless mode
        playwright, browser, context, page = await start_salesforce_session(
            salesforce_username, salesforce_password)
        with progress_container:
            show_step_status("Salesforce Login", "completed", "Successfully logged in")
            show_step_status("Case Navigation", "running", f"Searching for case {case_number.strip()}...")
            update_progress_bar(main_progress, 30, "Navigating to case...")
            show_floating_assistant("Searching for the case number in Salesforce..." , "https://media0.giphy.com/media/v1.Y2lkPTc5MGI3NjExMG1jYzlzMWxlemx0aDZ2eDBpYWhqZGNkYmsxOGw5NHJ0anllbmN4YSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9cw/b9wV1DPulEiwo94qUh/giphy.gif")
        
        # Case search and navigation
        await case_search_main(page, case_number.strip())
        with progress_container:
            show_step_status("Case Navigation", "completed", "Case found and loaded")
            show_step_status("Geolocation Extraction", "running", "Extracting geolocation data...")
            update_progress_bar(main_progress, 40, "Extracting geolocation...")
        
        # FIXED: Get current URL immediately after navigation
        current_url = page.url
        main_logger.info(f"Current URL captured: {current_url}")
        
        # Locate the geolocation field
        locator = page.locator("div.slds-form-element", has_text="Actual Geolocation")
        geo_value = await locator.locator("lightning-formatted-location").text_content()
        
        # Upload geolocation data
        s3_manager.upload_file(
            {
                'actual_geolocation': geo_value.strip(), 
                'timestamp': datetime.now().isoformat(),
                'case_number': case_number.strip()
            },
            'json_data',
            'geolocation_data.json'
        )

        with progress_container:
            show_step_status("Geolocation Extraction", "completed", f"Geolocation: {geo_value.strip()}")
            show_step_status("Document Download", "running", "Downloading case documents...")
            update_progress_bar(main_progress, 50, "Downloading documents...")
            show_floating_assistant("Fetching files and extracting information, please wait...","https://media3.giphy.com/media/v1.Y2lkPTc5MGI3NjExNmkzbzM0dXdiNWF6ajkzanhsNHZsc3hudXp3bW94bDJ0ZTdzbHNmcCZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9cw/K7ee5L9CZ5eHYBdsLb/giphy.gif")
        
        # Document download and processing
        doc_download_result = await zip_download(page, case_number.strip(), s3_manager)
        
        if doc_download_result:
            with progress_container:
                show_step_status("Document Download", "completed", "Documents downloaded successfully")
                update_progress_bar(main_progress, 60, "Processing documents...")

            st.success("📁 **Document download:** ✅ Completed successfully")
            
            # Extract PDFs from ZIP
            pdf_extracted = await extract_pdfs_from_zip(case_number.strip(), s3_manager)
            with progress_container:
                update_progress_bar(main_progress, 70, "Analyzing documents...")
            # Process document analysis
            document_analysis_result = await run_document_analysis_pipeline(case_number.strip(), s3_manager)
            with progress_container:
                update_progress_bar(main_progress, 80, "Extracting images...")
            # Process image extraction
            extraction_result = await run_image_extraction_pipeline(case_number.strip(), s3_manager)
            with progress_container:
                show_step_status("Drafter Automation", "running", "Processing drafter fields...")
                update_progress_bar(main_progress, 90, "Processing drafter fields...")
                show_floating_assistant("Processing drafter fields, please wait...", "https://media3.giphy.com/media/v1.Y2lkPTc5MGI3NjExMno1bmoyaXQ2MHdnd3Fjem51dDFtNTE5YzVpZWkyeXlhbWNxNmx5dSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9cw/XtU1Ja4CGWfkcZgkqs/giphy.gif")
            
            st.success("✅ Document analysis completed successfully")

            # Initialize JSON handler with case-based S3 manager
            json_handler = JSONHandler(case_number.strip(), s3_manager)
            
            # Drafter field automation
            drafter_done = await drafter_field_main(page, json_handler, s3_manager)
            
            if drafter_done:
                with progress_container:
                    show_step_status("Drafter Automation", "completed", f"Found {len(drafter_done) if isinstance(drafter_done, list) else 0} blank fields")
                    update_progress_bar(main_progress, 95, "Waiting for manual input...")
                    st.markdown('</div>', unsafe_allow_html=True)
                
                # Store blank fields in session state
                st.session_state['blank_fields'] = drafter_done
                print(f"Blank fields detected: {st.session_state['blank_fields']}")
                
                # FIXED: Update current URL before closing browser
                current_url = page.url
                main_logger.info(f"Updated current URL before closing: {current_url}")
                
                # Set phase to waiting for input
                st.session_state['automation_phase'] = 'waiting_for_input'
                st.session_state['automation_status'] = 'waiting_for_input'
                show_floating_assistant("User input required to proceed...","https://media4.giphy.com/media/v1.Y2lkPTc5MGI3NjExc29lNXk0M2ZoeW43aTA1eGFkbTF2dGpsMnQxNzJ6NWkzNTJvZHo4YSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9cw/pbex0XnwxHhLUtSIxf/giphy.gif")

                
                # Close browser to free resources
                await browser.close()
                await playwright.stop()
                
                # Rerun to show the form
                st.rerun()
            else:
                with progress_container:
                    show_step_status("Drafter Automation", "failed", "Failed to process fields")
                    st.markdown('</div>', unsafe_allow_html=True)
                st.warning("✍️ **Drafter field automation:** ⚠️ Failed")
                st.session_state['automation_status'] = 'failed'
                st.session_state['automation_started'] = False
        else:
            with progress_container:
                show_step_status("Document Download", "failed", "Download failed")
                st.markdown('</div>', unsafe_allow_html=True)
            st.error("📁 **Document download:** ❌ Failed")
            st.session_state['automation_status'] = 'failed'
            st.session_state['automation_started'] = False
            
    except Exception as e:
        with progress_container:
            show_step_status("Automation", "failed", f"Error: {str(e)}")
            st.markdown('</div>', unsafe_allow_html=True)
        st.error(f"❌ **Automation failed:** {str(e)}")
        st.session_state['automation_status'] = 'failed'
        st.session_state['automation_started'] = False
        
        # Close browser if it exists
        if browser:
            await browser.close()
        if playwright:
            await playwright.stop()

    # FIXED: Always return current_url, even if None
    return current_url

async def continue_automation(url):
    """Continue automation after manual input is submitted"""
    # **INITIALIZE ALL VARIABLES AT THE TOP TO PREVENT SCOPE ERRORS**
    s3_manager = None
    main_logger = None
    playwright = None
    browser = None
    context = None
    page = None
    
    # **WORKFLOW STATUS VARIABLES - INITIALIZE BEFORE USE**
    mobile_done = False
    doc_field_done = False

    # Create progress tracking for continuation
    progress_container = st.container()
    main_progress = st.progress(0, text="Continuing automation...")

    try:
        with progress_container:
            st.markdown('<div class="progress-container">', unsafe_allow_html=True)
            st.markdown("### 🔄 Continuation Progress")

            show_step_status("Reconnection", "running", "Reconnecting to Salesforce...")
            update_progress_bar(main_progress, 10, "Reconnecting...")
            show_floating_assistant("Login in to Salesforce portal, please wait...","https://media3.giphy.com/media/v1.Y2lkPTc5MGI3NjExMno1bmoyaXQ2MHdnd3Fjem51dDFtNTE5YzVpZWkyeXlhbWNxNmx5dSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9cw/XtU1Ja4CGWfkcZgkqs/giphy.gif")

        # Initialize S3 manager with case number
        s3_manager = st.session_state.get('s3_manager')
        
        if not s3_manager:
            # Fallback: create new S3 manager if not found in session state
            s3_manager = UnifiedS3Manager(case_number.strip())
        
        main_logger = UnifiedLogger(s3_manager, "main_controller")
        
        # Reconnect to Salesforce session in headless mode
        playwright, browser, context, page = await start_salesforce_session(
            salesforce_username, salesforce_password)
        with progress_container:
            show_step_status("Reconnection", "completed", "Successfully reconnected")
            show_step_status("Case Navigation", "running", "Navigating to case...")
            update_progress_bar(main_progress, 20, "Navigating to case...")
            show_floating_assistant("Searching for the case number in Salesforce..." , "https://media0.giphy.com/media/v1.Y2lkPTc5MGI3NjExMG1jYzlzMWxlemx0aDZ2eDBpYWhqZGNkYmsxOGw5NHJ0anllbmN4YSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9cw/b9wV1DPulEiwo94qUh/giphy.gif")

        main_logger.info(f"Continuing automation for case: {case_number.strip()}")
        main_logger.info(f"Current URL: {url}")
        
        # FIXED: Handle None URL case
        if url and url != "None":
            try:
                await page.goto(url)
                main_logger.info(f"Successfully navigated to: {url}")
            except Exception as nav_error:
                main_logger.warning(f"Failed to navigate to saved URL: {nav_error}")
                # Fallback to case search
                await case_search_main(page, case_number.strip())
        else:
            main_logger.warning("No saved URL found, performing case search")
            # Navigate to case using case search
            await case_search_main(page, case_number.strip())
        
        # Navigate to Drafter's Field tab
        await page.locator("//a[@data-label=\"Drafter's Field\"]").click()
        await page.wait_for_selector("//button[@data-id='Status_of_holding__c']")
        await page.locator("//button[@data-id='Status_of_holding__c']").click()
        
        with progress_container:
            show_step_status("Case Navigation", "completed", "Navigated to drafter fields")
            show_step_status("Manual Input Processing", "running", "Filling manual inputs...")
            update_progress_bar(main_progress, 40, "Processing manual inputs...")
            show_floating_assistant("Processing drafter input fields, please wait...", "https://media3.giphy.com/media/v1.Y2lkPTc5MGI3NjExMno1bmoyaXQ2MHdnd3Fjem51dDFtNTE5YzVpZWkyeXlhbWNxNmx5dSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9cw/XtU1Ja4CGWfkcZgkqs/giphy.gif")
        
        # Fill manual inputs from session state
        assistant = DrafterManualInputAssistant(s3_manager)
        await assistant.fill_manual_inputs(page, st.session_state['manual_inputs'])
        
        # Save report
        await assistant.save_manual_input_report(
            case_number.strip(), 
            st.session_state['blank_fields'], 
            st.session_state['manual_inputs']
        )

        with progress_container:
            show_step_status("Manual Input Processing", "completed", "Manual inputs processed and saved")
            show_step_status("Mobile App Automation", "running", "Processing mobile app fields...")
            update_progress_bar(main_progress, 60, "Mobile app automation...")
            show_floating_assistant("Processing mobile app fields, please wait...","https://media3.giphy.com/media/v1.Y2lkPTc5MGI3NjExMno1bmoyaXQ2MHdnd3Fjem51dDFtNTE5YzVpZWkyeXlhbWNxNmx5dSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9cw/XtU1Ja4CGWfkcZgkqs/giphy.gif")
        
        # Mobile app automation
        json_handler = JSONHandler(case_number.strip(), s3_manager)
        mobile_done = await mobileapp_main(page, json_handler, s3_manager)
        
        with progress_container:
            if mobile_done:
                show_step_status("Mobile App Automation", "completed", "Mobile app fields processed")
            else:
                show_step_status("Mobile App Automation", "failed", "Mobile app automation failed")
            
            show_step_status("Document Field Automation", "running", "Processing document fields...")
            update_progress_bar(main_progress, 80, "Document field automation...")
            show_floating_assistant("Document Selection in progress, please wait..." , "https://media1.giphy.com/media/v1.Y2lkPTc5MGI3NjExMzRjbjc4YXRya2Q5aG5kaHFlZWFla283bDgxN2swdWdjeHBnc2l3biZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9cw/VXx09FerN4t7JM9B4d/giphy.gif")

        # Document field automation
        doc_field_done = await document_field_main(page, s3_manager)
        
        with progress_container:
            if doc_field_done:
                show_step_status("Document Field Automation", "completed", "Document fields processed")
            else:
                show_step_status("Document Field Automation", "failed", "Document field automation failed")
            
            show_step_status("Final Processing", "running", "Saving completion status...")
            update_progress_bar(main_progress, 90, "Finalizing...")
        
        # Complete automation
        st.session_state['automation_status'] = 'completed'
        st.session_state['automation_completed'] = True
        st.session_state['automation_started'] = False
        
        # Upload final completion status
        completion_data = {
            'status': 'completed',
            'case_number': case_number.strip(),
            'unique_case_folder': s3_manager.unique_case_folder,
            'completion_time': datetime.now().isoformat(),
            'modules_completed': {
                'geolocation': True,
                'document_download': True,
                'image_extraction': True,
                'drafter': True,
                'mobile_app': mobile_done,
                'document_field': doc_field_done
            },
            'settings': {
                'debug_mode': debug_mode,
                'auto_cleanup': auto_cleanup,
                'save_local_copy': save_local_copy
            }
        }
        
        s3_manager.upload_file(completion_data, 'json_data', 'final_completion_status.json')
        with progress_container:
            show_step_status("Final Processing", "completed", "All processes completed successfully")
            update_progress_bar(main_progress, 100, "Automation completed!")
            st.markdown('</div>', unsafe_allow_html=True)
            show_floating_assistant("Kindly review and submit it....", "https://media2.giphy.com/media/v1.Y2lkPTc5MGI3NjExcGJjbGJtZjZraTFhMHQzZGN3a3Fnbm5mZjJ4ajgxMmZ4eGcxYzRweSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9cw/5vCSH6dHK8w6QJLo06/giphy.gif")

        
        # Save local copy if requested
        if save_local_copy:
            local_filename = f"{case_number.strip()}_completion_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(local_filename, 'w') as f:
                import json
                json.dump(completion_data, f, indent=2)
            st.info(f"💾 **Local copy saved:** {local_filename}")
        
        # Close browser        
        # Show success message
        st.balloons()
        show_floating_assistant("Kindly review and submit it & Refresh the page for new case....", "https://media2.giphy.com/media/v1.Y2lkPTc5MGI3NjExcGJjbGJtZjZraTFhMHQzZGN3a3Fnbm5mZjJ4ajgxMmZ4eGcxYzRweSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9cw/5vCSH6dHK8w6QJLo06/giphy.gif")

        
    except Exception as e:
        with progress_container:
            show_step_status("Continuation", "failed", f"Error: {str(e)}")
            st.markdown('</div>', unsafe_allow_html=True)
        st.error(f"❌ **Continuation failed:** {str(e)}")
        st.session_state['automation_status'] = 'failed'
        st.session_state['automation_started'] = False
        
        # Close browser if it exists
        if browser:
            await browser.close()
        if playwright:
            await playwright.stop()

# Initialize session state variables
if 'automation_phase' not in st.session_state:
    st.session_state['automation_phase'] = 'initial'  # 'initial', 'waiting_for_input', 'continuing'
if 'automation_started' not in st.session_state:
    st.session_state['automation_started'] = False
if 'automation_completed' not in st.session_state:
    st.session_state['automation_completed'] = False
if 'automation_status' not in st.session_state:
    st.session_state['automation_status'] = 'idle'
if 'blank_fields' not in st.session_state:
    st.session_state['blank_fields'] = []
if 'manual_inputs' not in st.session_state:
    st.session_state['manual_inputs'] = {}
if 'manual_inputs_submitted' not in st.session_state:
    st.session_state['manual_inputs_submitted'] = False
if 's3_manager' not in st.session_state:
    st.session_state['s3_manager'] = None
if 'automation_url' not in st.session_state:  # FIXED: Add URL session state
    st.session_state['automation_url'] = None


# Get Salesforce credentials
st.markdown("### Login Credentials")
salesforce_username = st.text_input("Username:")
show_floating_assistant("👋 Hello! I'm your Drafter Assistant.","https://media1.giphy.com/media/v1.Y2lkPTc5MGI3NjExY3BmYzg0MzhpbWQ0a3djanAzM3l6dmRhanhtdXF3cmVuZTYxZjh6aiZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9cw/c1hhT9nPjLRkLeK83H/giphy.gif")


salesforce_password = st.text_input("Password", type="password")
show_floating_assistant("👋 Hello! I'm your Drafter Assistant.","https://media1.giphy.com/media/v1.Y2lkPTc5MGI3NjExY3BmYzg0MzhpbWQ0a3djanAzM3l6dmRhanhtdXF3cmVuZTYxZjh6aiZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9cw/c1hhT9nPjLRkLeK83H/giphy.gif")

# Main input section
st.markdown("### 📝 Case Information")
case_number = st.text_input(
    "Enter Case Number", 
    placeholder="e.g., T-0000045703",
    help="Enter the Salesforce case number for property valuation automation",
    disabled=st.session_state['automation_started']
)

if case_number:
    if case_number.strip():
        st.markdown(f'<div class="case-info">📁 <strong>Case Number:</strong> {case_number}</div>', unsafe_allow_html=True)
    else:
        st.warning("⚠️ Please enter a valid case number")

if st.session_state['automation_status'] != 'idle':
    status_colors = {'running': '🔄', 'completed': '✅', 'failed': '❌', 'waiting_for_input': '⏳'}
    status_messages = {
        'running': 'Automation in progress...',
        'completed': 'Automation completed successfully!',
        'failed': 'Automation encountered an error',
        'waiting_for_input': 'Waiting for your manual input...'
    }
    st.info(f"{status_colors.get(st.session_state['automation_status'], '⚠️')} **Automation Status:** {st.session_state['automation_status'].title()}")

with st.expander("⚙️ Advanced Options"):
    col1, col2 = st.columns(2)
    with col1:
        auto_cleanup = st.checkbox("Auto cleanup on completion", value=False, disabled=st.session_state['automation_started'])
        debug_mode = st.checkbox("Enable debug mode", value=False, disabled=st.session_state['automation_started'])
    with col2:
        save_local_copy = st.checkbox("Save local JSON copy", value=False, disabled=st.session_state['automation_started'])

# **FIXED: Proper button state management with immediate disable**
button_disabled = (
    st.session_state['automation_started'] or 
    not case_number or 
    not case_number.strip() or
    not salesforce_username or
    not salesforce_password or
    st.session_state['automation_status'] == 'running' or
    st.session_state['automation_status'] == 'waiting_for_input'
)

button_text = "🔄 Running..." if st.session_state['automation_started'] else "🚀 Run Automation"

run_button = st.button(
    button_text,
    type="primary", 
    use_container_width=True, 
    disabled=button_disabled
)

if run_button:
    if not case_number or not case_number.strip():
        st.error("⚠️ Please enter a case number before proceeding.")
    elif not salesforce_username or not salesforce_password:
        st.error("⚠️ Please enter Salesforce credentials before proceeding.")
    else:
        # **IMMEDIATELY SET STATES TO DISABLE BUTTON**
        st.session_state['automation_started'] = True
        st.session_state['automation_completed'] = False
        st.session_state['automation_status'] = 'running'
        st.session_state['automation_phase'] = 'initial'
        st.session_state['blank_fields'] = []
        st.session_state['manual_inputs'] = {}
        st.session_state['manual_inputs_submitted'] = False
        
        # **FORCE IMMEDIATE RERUN TO UPDATE BUTTON STATE**
        st.rerun()

# Run automation based on current phase
if st.session_state['automation_started'] and st.session_state['automation_status'] == 'running':
    if st.session_state['automation_phase'] == 'initial':
        # Run initial automation until blank fields are detected
        url = asyncio.run(run_initial_automation())
        st.session_state['automation_url'] = url  # Save for later
    elif st.session_state['automation_phase'] == 'continuing':
        # Continue automation after manual input is submitted
        url = st.session_state.get('automation_url')
        asyncio.run(continue_automation(url))


if st.session_state['automation_phase'] == 'waiting_for_input':
    show_floating_assistant("User input required to proceed...","https://media4.giphy.com/media/v1.Y2lkPTc5MGI3NjExc29lNXk0M2ZoeW43aTA1eGFkbTF2dGpsMnQxNzJ6NWkzNTJvZHo4YSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9cw/pbex0XnwxHhLUtSIxf/giphy.gif")

    # FIXED: Use existing S3 manager from session state
    s3_manager = st.session_state.get('s3_manager')
    if not s3_manager:
        s3_manager = UnifiedS3Manager(case_number.strip())
    
    assistant = DrafterManualInputAssistant(s3_manager)
    # Show manual input form if in waiting_for_input phase
    show_floating_assistant("User input required to proceed...","https://media4.giphy.com/media/v1.Y2lkPTc5MGI3NjExc29lNXk0M2ZoeW43aTA1eGFkbTF2dGpsMnQxNzJ6NWkzNTJvZHo4YSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9cw/pbex0XnwxHhLUtSIxf/giphy.gif")

    
    # Validate and transform empty fields
    validated_fields = assistant.validate_and_transform_empty_fields(st.session_state['blank_fields'])
    
    if validated_fields:
        st.info("👤 **Manual Input Required:** Please fill in the following fields:")
        
        # Create a form in Streamlit
        with st.form(key="manual_input_form"):
            manual_inputs = {}
            # Group fields by category for better UI
            categorized_fields = assistant.categorize_empty_fields(validated_fields)
            
            for category, fields in categorized_fields['By_Category'].items():
                st.subheader(category)
                for field in fields:
                    field_key = field['key']
                    field_label = field['label']
                    field_type = field['type']
                    required = field['required']
                    options = field.get('options', [])
                    
                    # Create appropriate widget based on field type
                    if field_type == 'dropdown':
                        value = st.selectbox(
                            field_label + (" *" if required else ""),
                            options=[''] + options,  # Add empty option
                            key=field_key
                        )
                    else:
                        value = st.text_input(
                            field_label + (" *" if required else ""),
                            key=field_key
                        )
                    
                    manual_inputs[field_key] = value
            
            # Add submit button
            submitted = st.form_submit_button("Submit")
            if submitted:
                # Validate required fields
                missing_required = []
                for field in validated_fields:
                    if field['required'] and not manual_inputs.get(field['key'], '').strip():
                        missing_required.append(field['label'])
                
                if missing_required:
                    st.error(f"Please fill in the required fields: {', '.join(missing_required)}")

                else:
                    st.success("Form submitted successfully. Continuing automation...")
                    st.session_state['manual_inputs'] = manual_inputs
                    st.session_state['manual_inputs_submitted'] = True
                    st.session_state['automation_phase'] = 'continuing'
                    st.session_state['automation_status'] = 'running'
                    st.rerun()
    else:
        st.info("No fields require manual input.")
        st.session_state['manual_inputs'] = {}
        st.session_state['manual_inputs_submitted'] = True
        st.session_state['automation_phase'] = 'continuing'
        st.session_state['automation_status'] = 'running'
        st.rerun()

# Always display the local document manager if a case number is entered
if case_number and case_number.strip():
    display_local_document_manager(case_number)


# Footer information
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666; font-size: 0.8rem;'>
    <p>🔧 <strong>Salesforce Drafter Automation System</strong> | Case Number-Based S3 Storage | Version 4.0</p>
    <p>📁 Storage: Automatic case folder creation with increment handling (_1, _2, etc.)</p>
</div>
""", unsafe_allow_html=True)
