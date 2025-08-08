import logging
import os
import json
from datetime import datetime
import asyncio
from playwright.async_api import TimeoutError as PlaywrightTimeoutError, Page
from dotenv import load_dotenv
from typing import Dict, Any, Optional
import re
from static.unified_s3_manager import UnifiedS3Manager
from static.unified_logger import UnifiedLogger

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('salesforce_automation.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
load_dotenv()

# Document Selection Constraints (from new_selection.py)
PHOTO_CONSTRAINTS = {
    "Internal Photos": 5,
    "Site Plan": 2,
    "Selfie with customer Outside": 1,
    "Selfie with customer Inside": 1,
    "Front Elevation": 3,
    "Approach Road": 3,
    "Kitchen": 1,
    "E-Meter No": 1,
    "Selfie": 1,
    "Bathroom": 1,
    "DLC Rate Photo": 1,
    "Hybrid Map": 1,
    "Road Map": 1,
    "Other": 1
}

class DocumentFieldAutomation:
    """Document field automation with constraints-based processing"""
    
    def __init__(self, s3_manager: UnifiedS3Manager):
        self.s3_manager = s3_manager
        self.logger = UnifiedLogger(s3_manager, "document_field")
        self.selected_counts = {}  # Track how many times each title has been selected

    async def take_screenshot_and_upload(self, page: Page, context: str = "general") -> Optional[str]:
        """Takes a screenshot and uploads it to unified S3 storage"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"document_field_{context}_{timestamp}.png"
        try:
            screenshot_bytes = await page.screenshot(timeout=10000)
            s3_url = self.s3_manager.upload_file(
                screenshot_bytes,
                'screenshots',
                filename,
                'image/png'
            )
            self.logger.info(f"Screenshot uploaded: {s3_url}")
            return s3_url
        except Exception as e:
            self.logger.error(f"Failed to take and upload screenshot for {context}: {e}")
            return None

    async def navigate_to_documents_tab(self, page):
        """Navigate to Documents tab"""
        self.logger.info("📂 Navigating to Documents tab...")
        try:
            await page.locator("//a[@data-label=\"Documents\"]").click(timeout=10000)
            await page.wait_for_timeout(3000)
            self.logger.info("✅ Successfully navigated to Documents tab")
            return True
        except PlaywrightTimeoutError as e:
            self.logger.error(f"Timeout navigating to Documents tab: {e}")
            return False

    async def extract_checkbox_title(self, checkbox):
        """Extract title from checkbox container"""
        try:
            parent_strategies = [
                ("Level 3 Parent", "xpath=ancestor::*[3]"),
                ("Level 4 Parent", "xpath=ancestor::*[4]"),
                ("Level 5 Parent", "xpath=ancestor::*[5]"),
                ("Level 6 Parent", "xpath=ancestor::*[6]"),
                ("Level 7 Parent", "xpath=ancestor::*[7]"),
            ]
            
            for strategy_name, xpath in parent_strategies:
                try:
                    container = checkbox.locator(xpath)
                    if await container.count() > 0:
                        container_text = await container.inner_text()
                        if "Visible in report" in container_text:
                            title = await self.extract_title_from_text(container_text)
                            if title:
                                return title
                except Exception:
                    continue
            return None
        except Exception as e:
            self.logger.debug(f"Error extracting checkbox title: {e}")
            return None

    async def extract_title_from_text(self, container_text):
        """Extract the actual document title from container text"""
        try:
            lines = container_text.split('\n')
            meaningful_lines = [line.strip() for line in lines if line.strip() and len(line.strip()) > 2]
            
            known_patterns = [
                "bathroom", "road map", "hybrid map", "dlc rate", "e-meter", "selfi", "selfie",
                "kitchen", "approach road", "internal photos", "site plan", "front elevation", "other",
                "selfie with customer outside", "selfie with customer inside"
            ]
            
            # First pass: look for exact matches with known patterns
            for line in meaningful_lines:
                line_clean = line.strip()
                if self.is_potential_title(line_clean):
                    line_lower = line_clean.lower()
                    for pattern in known_patterns:
                        if pattern in line_lower:
                            mapped_title = self.map_to_constraint_title(line_clean)
                            if mapped_title:
                                return mapped_title
            
            # Second pass: look for any potential title
            for line in meaningful_lines:
                line_clean = line.strip()
                if self.is_potential_title(line_clean):
                    mapped_title = self.map_to_constraint_title(line_clean)
                    if mapped_title:
                        return mapped_title
            
            return None
        except Exception as e:
            self.logger.debug(f"Error extracting title from text: {e}")
            return None

    def is_potential_title(self, text):
        """Check if text could be a document title"""
        if not text or len(text) <= 1:
            return False
        
        skip_patterns = [
            "visible in report", "click to preview", "select", "▼", "•",
            "-", "*", "+", "upload documents", "download", "edit", "delete",
            "view", "save", "cancel", "close", "expand", "collapse"
        ]
        
        text_lower = text.lower()
        if any(pattern in text_lower for pattern in skip_patterns):
            return False
        
        if len(text) > 100 or text.isdigit() or not any(c.isalpha() for c in text):
            return False
        
        return True

    def map_to_constraint_title(self, extracted_title):
        """Map extracted title to constraint keys"""
        title_lower = extracted_title.lower().strip()
        
        # Exact matches
        exact_matches = {
            "bathroom": "Bathroom",
            "road map": "Road Map",
            "route map": "Road Map",
            "hybrid map": "Hybrid Map",
            "dlc rate photo": "DLC Rate Photo",
            "dlc rate": "DLC Rate Photo",
            "e-meter no": "E-Meter No",
            "e-meter": "E-Meter No",
            "selfi": "Selfie",
            "kitchen": "Kitchen",
            "internal photos": "Internal Photos",
            "site plan": "Site Plan",
            "Site Plan": "Site Plan",
            "front elevation": "Front Elevation",
            "approach road": "Approach Road",
            "selfie": "Selfie",
            "other": "Other",
            "selfie with customer outside": "Selfie with customer Outside",
            "selfie with customer inside": "Selfie with customer Inside"
        }
        
        if title_lower in exact_matches:
            return exact_matches[title_lower]
        
        # Partial matches
        partial_matches = {
            "Bathroom": ["bathroom", "toilet", "restroom"],
            "Road Map": ["road map", "route map", "street map"],
            "Hybrid Map": ["hybrid map", "hybrid"],
            "DLC Rate Photo": ["dlc rate", "dlc photo", "dlc"],
            "E-Meter No": ["e-meter", "meter", "electricity meter", "electric meter"],
            "Selfie": ["selfie", "selfi"],
            "Kitchen": ["kitchen"],
            "Internal Photos": ["internal photos","Internal photo", "internal", "inside photos"],
            "Site Plan": ["site plan", "site layout", "site map" , "Site Plan"],
            "Front Elevation": ["front elevation", "elevation", "front view"],
            "Approach Road": ["approach road", "approach", "access road"],
            "Other": ["other", "misc"],
            "Selfie with customer Outside": ["selfie with customer outside", "customer selfie outside", "outside selfie"],
            "Selfie with customer Inside": ["selfie with customer inside", "customer selfie inside", "inside selfie"]
        }
        
        for constraint_title, keywords in partial_matches.items():
            for keyword in keywords:
                if keyword in title_lower:
                    return constraint_title
        
        return None

    async def select_checkbox_safely(self, page, checkbox, title):
        """Select checkbox with multiple strategies"""
        self.logger.info(f"🎯 Selecting checkbox for: '{title}'")
        try:
            if await checkbox.is_checked():
                self.logger.info(f"✅ '{title}' is already checked")
                return True
            
            await checkbox.scroll_into_view_if_needed()
            await page.wait_for_timeout(500)
            
            strategies = [
                ("Standard click", lambda: checkbox.click(timeout=5000)),
                ("Force click", lambda: checkbox.click(force=True, timeout=5000)),
                ("JavaScript click", lambda: page.evaluate("arguments[0].click()", checkbox.element_handle())),
                ("Focus and space", self.focus_and_space),
            ]
            
            for strategy_name, strategy_func in strategies:
                try:
                    if strategy_name == "Focus and space":
                        await strategy_func(page, checkbox)
                    else:
                        await strategy_func()
                    
                    await page.wait_for_timeout(1000)
                    
                    if await checkbox.is_checked():
                        self.logger.info(f"🎉 SUCCESS: {strategy_name} worked for '{title}'")
                        return True
                except Exception as e:
                    self.logger.debug(f" {strategy_name} failed: {e}")
                    continue
            
            self.logger.warning(f"❌ All strategies failed for '{title}'")
            return False
        except Exception as e:
            self.logger.error(f"❌ Error selecting '{title}': {e}")
            return False

    async def focus_and_space(self, page, checkbox):
        """Focus checkbox and press space"""
        await checkbox.focus()
        await page.wait_for_timeout(300)
        await page.keyboard.press('Space')

    async def process_documents_with_constraints(self, page):
        """Main processing method - iterate through checkboxes and apply constraints"""
        self.logger.info("🚀 Processing documents with CONSTRAINTS...")
        
        # Initialize selected counts
        self.selected_counts = {title: 0 for title in PHOTO_CONSTRAINTS.keys()}
        
        results = {
            'selected': [],
            'skipped_not_in_constraints': [],
            'skipped_limit_reached': [],
            'failed_selections': [],
            'total_checkboxes': 0
        }
        
        try:
            await page.wait_for_timeout(5000)
            
            all_checkboxes = page.locator("input[type='checkbox']")
            total_checkboxes = await all_checkboxes.count()
            results['total_checkboxes'] = total_checkboxes
            
            self.logger.info(f"📋 Found {total_checkboxes} total checkboxes to process")
            
            if total_checkboxes == 0:
                self.logger.error("❌ No checkboxes found!")
                return {'success': False, 'error': 'No checkboxes found'}
            
            # Process each checkbox in order
            for i in range(total_checkboxes):
                try:
                    self.logger.info(f"\n📍 Processing checkbox {i+1}/{total_checkboxes}")
                    checkbox = all_checkboxes.nth(i)
                    
                    # Extract title from this checkbox
                    title = await self.extract_checkbox_title(checkbox)
                    
                    if not title:
                        self.logger.info(f" ❌ Could not extract title from checkbox {i+1} - skipping")
                        results['skipped_not_in_constraints'].append({
                            'checkbox_index': i+1,
                            'reason': 'Could not extract title'
                        })
                        continue
                    
                    self.logger.info(f" 📄 Extracted title: '{title}'")
                    
                    # Check if title is in our constraints
                    if title not in PHOTO_CONSTRAINTS:
                        self.logger.info(f" ⏭️ '{title}' not in constraints - skipping")
                        results['skipped_not_in_constraints'].append({
                            'checkbox_index': i+1,
                            'title': title,
                            'reason': 'Not in constraints list'
                        })
                        continue
                    
                    # Check current count vs max allowed
                    current_count = self.selected_counts[title]
                    max_allowed = PHOTO_CONSTRAINTS[title]
                    
                    self.logger.info(f" 📊 '{title}': current={current_count}, max={max_allowed}")
                    
                    if current_count >= max_allowed:
                        self.logger.info(f" 🛑 '{title}' limit reached ({current_count}/{max_allowed}) - skipping")
                        results['skipped_limit_reached'].append({
                            'checkbox_index': i+1,
                            'title': title,
                            'current_count': current_count,
                            'max_allowed': max_allowed
                        })
                        continue
                    
                    # Try to select the checkbox
                    self.logger.info(f" 🎯 Selecting '{title}' ({current_count+1}/{max_allowed})")
                    success = await self.select_checkbox_safely(page, checkbox, title)
                    
                    if success:
                        # Increment counter
                        self.selected_counts[title] += 1
                        self.logger.info(f" ✅ Successfully selected '{title}' - new count: {self.selected_counts[title]}")
                        results['selected'].append({
                            'checkbox_index': i+1,
                            'title': title,
                            'selection_number': self.selected_counts[title],
                            'max_allowed': max_allowed
                        })
                    else:
                        self.logger.warning(f" ❌ Failed to select '{title}'")
                        results['failed_selections'].append({
                            'checkbox_index': i+1,
                            'title': title,
                            'reason': 'Selection failed'
                        })
                
                except Exception as e:
                    self.logger.error(f"Error processing checkbox {i+1}: {e}")
                    results['failed_selections'].append({
                        'checkbox_index': i+1,
                        'reason': f'Error: {str(e)}'
                    })
                    continue
            
            # Final summary
            total_selected = len(results['selected'])
            total_skipped_constraints = len(results['skipped_not_in_constraints'])
            total_skipped_limits = len(results['skipped_limit_reached'])
            total_failed = len(results['failed_selections'])
            
            self.logger.info("\n" + "=" * 80)
            self.logger.info("🎉 CONSTRAINTS-BASED PROCESSING RESULTS")
            self.logger.info("=" * 80)
            self.logger.info(f"📋 Total Checkboxes Processed: {total_checkboxes}")
            self.logger.info(f"✅ Successfully Selected: {total_selected}")
            self.logger.info(f"⏭️ Skipped (not in constraints): {total_skipped_constraints}")
            self.logger.info(f"🛑 Skipped (limit reached): {total_skipped_limits}")
            self.logger.info(f"❌ Failed Selections: {total_failed}")
            
            # Show final counts
            self.logger.info(f"\n📊 FINAL SELECTION COUNTS:")
            for title, count in self.selected_counts.items():
                max_allowed = PHOTO_CONSTRAINTS[title]
                status = "✅ COMPLETE" if count == max_allowed else f"📊 {count}/{max_allowed}"
                self.logger.info(f" {title}: {count}/{max_allowed} {status}")
            
            results['success'] = True
            results['selected_counts'] = dict(self.selected_counts)
            return results
        
        except Exception as e:
            self.logger.error(f"❌ Error in constraints processing: {e}")
            return {'success': False, 'error': str(e)}

    async def process_document_fields(self, page: Page) -> bool:
        """Process document fields using constraints-based logic"""
        try:
            self.logger.info("Starting document field processing with constraints-based logic")
            
            if not await self.navigate_to_documents_tab(page):
                self.logger.error("Failed to navigate to Documents tab")
                return False
            
            await self.take_screenshot_and_upload(page, "before_processing")
            
            results = await self.process_documents_with_constraints(page)
            
            if results['success']:
                self.logger.info("🎉 AUTOMATION COMPLETED!")
                self.logger.info(f"📊 Results: {len(results['selected'])} selected, {len(results['skipped_not_in_constraints']) + len(results['skipped_limit_reached'])} skipped, {len(results['failed_selections'])} failed")
                await self.take_screenshot_and_upload(page, "after_processing")
                return True
            else:
                self.logger.error("Document processing failed")
                await self.take_screenshot_and_upload(page, "processing_failed")
                return False
        
        except Exception as e:
            self.logger.error(f"Error in document field processing: {e}")
            await self.take_screenshot_and_upload(page, "processing_error")
            return False

async def document_field_main(page: Page, s3_manager: UnifiedS3Manager) -> bool:
    """
    Main document field automation function using constraints-based logic
    
    Args:
        page: Playwright page object
        s3_manager: Unified S3 manager instance
    
    Returns:
        bool: True if successful, False otherwise
    """
    automation = DocumentFieldAutomation(s3_manager)
    try:
        automation.logger.info("Starting Document Field automation workflow")
        
        initial_status = {
            "status": "started",
            "process_uuid": getattr(s3_manager, 'process_uuid', 'unknown'),
            "start_time": datetime.now().isoformat()
        }
        s3_manager.upload_file(json.dumps(initial_status).encode('utf-8'), 'json_data', 'document_field_start_status.json', 'application/json')
        
        process_success = await automation.process_document_fields(page)
        
        if not process_success:
            raise Exception("Failed to process document fields")
        
        completion_status = {
            "status": "completed",
            "process_uuid": getattr(s3_manager, 'process_uuid', 'unknown'),
            "completion_time": datetime.now().isoformat()
        }
        s3_manager.upload_file(json.dumps(completion_status).encode('utf-8'), 'json_data', 'document_field_completion_status.json', 'application/json')
        
        automation.logger.info("Document Field automation completed successfully")
        return True
    
    except Exception as e:
        automation.logger.error(f"Document Field automation failed: {str(e)}")
        
        error_report = {
            "status": "failed",
            "error": str(e),
            "process_uuid": getattr(s3_manager, 'process_uuid', 'unknown'),
            "failure_time": datetime.now().isoformat(),
            "error_type": type(e).__name__
        }
        s3_manager.upload_file(json.dumps(error_report).encode('utf-8'), 'json_data', 'document_field_error_report.json', 'application/json')
        
        try:
            await automation.take_screenshot_and_upload(page, "final_error")
        except:
            pass
        
        return False
    
    finally:
        try:
            automation.logger.save_logs()
        except Exception as e:
            logger.error(f"Failed to save logs: {e}")

# Entry point for testing
if __name__ == "__main__":
    print("document.py - Document Field Automation Module")
    print("This module should be imported and called from the main automation script.")
