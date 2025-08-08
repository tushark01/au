import logging
import asyncio
import os
from datetime import datetime
from playwright.async_api import TimeoutError as PlaywrightTimeoutError, Page
from dotenv import load_dotenv
from typing import Dict, Any, Optional
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

class TechnicalFieldAutomation:
    """Technical field automation with unified S3 storage"""
    
    def __init__(self, s3_manager: UnifiedS3Manager):
        self.s3_manager = s3_manager
        self.logger = UnifiedLogger(s3_manager, "technical_field")
        
    async def take_screenshot_and_upload(self, page: Page, context: str = "general") -> Optional[str]:
        """Takes a screenshot and uploads it to unified S3 storage"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"technical_field_{context}_{timestamp}.png"
        
        try:
            screenshot_bytes = await page.screenshot()
            s3_url = self.s3_manager.upload_file(
                screenshot_bytes, 
                'screenshots', 
                filename, 
                'image/png'
            )
            self.logger.info(f"Screenshot uploaded: {s3_url}")
            return s3_url
        except Exception as e:
            self.logger.error(f"Failed to take and upload screenshot: {e}")
            return None

    async def fill_inputs(self, page, data, field_map):
        """Fill input fields using the old working logic"""
        for label, idx in field_map.items():
            try:
                value = data["technical_field"].get(label, "")
                if value and str(value).strip():  # Only fill if value exists and is not empty
                    self.logger.info(f"Filling {label} with value: {value}")
                    await page.get_by_label("Technical Detail").locator(
                        "//lightning-input[@data-id='1']//input[@type='text']"
                    ).nth(idx).fill(str(value))
                    await page.wait_for_timeout(500)
                else:
                    self.logger.warning(f"Skipping {label} - empty or missing value")
            except Exception as e:
                self.logger.error(f"Error filling {label}: {e}")

    async def fill_dropdown(self, page, field_name, value):
        """Fill dropdown using enhanced error handling"""
        try:
            # **FIX: Validate value before attempting to select**
            if not value or str(value).strip() == "":
                self.logger.warning(f"Skipping {field_name} - empty value provided")
                return False
            
            value_str = str(value).strip()
            self.logger.info(f"Filling {field_name} with value: '{value_str}'")
            
            # Click the dropdown to open it
            await page.get_by_label("Technical Detail").locator(
                f"//button[@role='combobox' and @name='{field_name}' and contains(@class, 'slds-combobox__input')]"
            ).click()
            
            await page.wait_for_timeout(1000)  # Wait for dropdown to open
            
            # **FIX: Use more specific locator to avoid strict mode violation**
            option_locator = page.get_by_label("Technical Detail").get_by_role("option", name=value_str, exact=True)
            
            # Check if the option exists
            if await option_locator.count() > 0:
                await option_locator.click()
                await page.wait_for_timeout(500)
                self.logger.info(f"Successfully selected '{value_str}' for {field_name}")
                return True
            else:
                # Try partial match if exact match fails
                self.logger.warning(f"Exact match failed for '{value_str}', trying partial match")
                option_locator = page.get_by_label("Technical Detail").locator(f"//lightning-base-combobox-item[contains(text(), '{value_str}')]")
                
                if await option_locator.count() > 0:
                    await option_locator.first.click()
                    await page.wait_for_timeout(500)
                    self.logger.info(f"Successfully selected '{value_str}' for {field_name} (partial match)")
                    return True
                else:
                    self.logger.error(f"No option found for '{value_str}' in {field_name}")
                    return False
                    
        except Exception as e:
            self.logger.error(f"Error filling dropdown {field_name} with value '{value}': {e}")
            return False

    async def floorunit(self, page, data):
        """Process floor unit using old working logic with enhanced error handling"""
        try:
            self.logger.info("Processing floor unit form")
            
            # Fill input fields
            success = await self.fill_inputs(page, data, {
                "Area documented": 0,
                "Area permissible": 2,
                "Sanction": 3,
                "Accommodation": 6,
                "Market rate existing": 9,
                "Market rate after completion": 11
            })

            # Tab navigation
            for i in range(19):
                await page.keyboard.press("Tab")
                await page.wait_for_timeout(100)  # Small delay between tabs
                
            # User confirmation
            confirm_script = """
            () => {
            return new Promise((resolve) => {
                const overlay = document.createElement('div');
                overlay.style.position = 'fixed';
                overlay.style.top = '0';
                overlay.style.left = '0';
                overlay.style.width = '100%';
                overlay.style.height = '100%';
                overlay.style.backgroundColor = 'rgba(0,0,0,0.5)';
                overlay.style.zIndex = '9999';
                overlay.style.display = 'flex';
                overlay.style.alignItems = 'center';
                overlay.style.justifyContent = 'center';

                const box = document.createElement('div');
                box.style.background = '#fff';
                box.style.padding = '30px';
                box.style.borderRadius = '8px';
                box.style.textAlign = 'center';
                box.innerHTML = '<p style="font-size:16px;">Do you want to proceed with saving the floor unit form?</p>';

                const okBtn = document.createElement('button');
                okBtn.textContent = 'OK';
                okBtn.style.marginRight = '10px';
                okBtn.style.padding = '10px 20px';
                okBtn.style.backgroundColor = '#007bff';
                okBtn.style.color = 'white';
                okBtn.style.border = 'none';
                okBtn.style.borderRadius = '4px';
                okBtn.onclick = () => {
                document.body.removeChild(overlay);
                resolve(true);
                };

                const cancelBtn = document.createElement('button');
                cancelBtn.textContent = 'Cancel';
                cancelBtn.style.padding = '10px 20px';
                cancelBtn.style.backgroundColor = '#6c757d';
                cancelBtn.style.color = 'white';
                cancelBtn.style.border = 'none';
                cancelBtn.style.borderRadius = '4px';
                cancelBtn.onclick = () => {
                document.body.removeChild(overlay);
                resolve(false);
                };

                box.appendChild(okBtn);
                box.appendChild(cancelBtn);
                overlay.appendChild(box);
                document.body.appendChild(overlay);
            });
            }
            """
            
            try:
                result = await asyncio.wait_for(page.evaluate(confirm_script), timeout=30)
                if result:
                    self.logger.info("User confirmed, proceeding to save")
                    for i in range(59):
                        await page.keyboard.press("Tab")
                        await page.wait_for_timeout(50)
                    await page.keyboard.press("Enter")
                    await page.wait_for_timeout(10000)
                    self.logger.info("Floor unit form saved successfully")
                    return True
                else:
                    self.logger.warning("User cancelled floor unit form")
                    return False
            except asyncio.TimeoutError:
                self.logger.warning("No response from user in 30 seconds")
                return False

        except Exception as e:
            self.logger.error(f"Error in floorunit: {str(e)}")
            return False

    async def apartmentfloorunit(self, page, data):
        """Process apartment floor unit with enhanced error handling"""
        try:
            self.logger.info("Processing apartment floor unit form")
            
            # **FIX: Validate data before processing**
            technical_data = data.get("technical_field", {})
            
            # Fill dropdowns with validation
            dropdown_fields = [

                # These fields are already filled by the field visit executive.
                # ("apartmentFloorUnit", technical_data.get("Apartment Floor name", "")),
                # ("unitArea", technical_data.get("Unit", "")),
                ("unitCalculation", technical_data.get("Unit Calculation", ""))
            ]
            
            dropdown_success = True
            for field_name, field_value in dropdown_fields:
                if field_value and str(field_value).strip():
                    success = await self.fill_dropdown(page, field_name, field_value)
                    if not success:
                        self.logger.warning(f"Failed to fill dropdown {field_name}")
                        dropdown_success = False
                else:
                    self.logger.warning(f"Skipping dropdown {field_name} - no value provided")
            
            # Fill input fields
            input_success = await self.fill_inputs(page, data, {
                "Super Built-up-area": 0,
                "Built-area": 1,
                "Carpet-area": 2,
                "Rate of construction": 3,
                "DLC Rate": 5
            })

            # Tab navigation
            for i in range(7):
                await page.keyboard.press("Tab")
                await page.wait_for_timeout(100)

            # User confirmation
            confirm_script = """
            () => {
            return new Promise((resolve) => {
                const overlay = document.createElement('div');
                overlay.style.position = 'fixed';
                overlay.style.top = '0';
                overlay.style.left = '0';
                overlay.style.width = '100%';
                overlay.style.height = '100%';
                overlay.style.backgroundColor = 'rgba(0,0,0,0.5)';
                overlay.style.zIndex = '9999';
                overlay.style.display = 'flex';
                overlay.style.alignItems = 'center';
                overlay.style.justifyContent = 'center';

                const box = document.createElement('div');
                box.style.background = '#fff';
                box.style.padding = '30px';
                box.style.borderRadius = '8px';
                box.style.textAlign = 'center';
                box.innerHTML = '<p style="font-size:16px;">Do you want to proceed with saving the apartment form?</p>';

                const okBtn = document.createElement('button');
                okBtn.textContent = 'OK';
                okBtn.style.marginRight = '10px';
                okBtn.style.padding = '10px 20px';
                okBtn.style.backgroundColor = '#007bff';
                okBtn.style.color = 'white';
                okBtn.style.border = 'none';
                okBtn.style.borderRadius = '4px';
                okBtn.onclick = () => {
                document.body.removeChild(overlay);
                resolve(true);
                };

                const cancelBtn = document.createElement('button');
                cancelBtn.textContent = 'Cancel';
                cancelBtn.style.padding = '10px 20px';
                cancelBtn.style.backgroundColor = '#6c757d';
                cancelBtn.style.color = 'white';
                cancelBtn.style.border = 'none';
                cancelBtn.style.borderRadius = '4px';
                cancelBtn.onclick = () => {
                document.body.removeChild(overlay);
                resolve(false);
                };

                box.appendChild(okBtn);
                box.appendChild(cancelBtn);
                overlay.appendChild(box);
                document.body.appendChild(overlay);
            });
            }
            """

            try:
                result = await asyncio.wait_for(page.evaluate(confirm_script), timeout=30)
                if result:
                    self.logger.info("User confirmed, proceeding to save")
                    for i in range(59):
                        await page.keyboard.press("Tab")
                        await page.wait_for_timeout(50)
                    await page.keyboard.press("Enter")
                    await page.wait_for_timeout(100000)
                    self.logger.info("Apartment form saved successfully")
                    return True
                else:
                    self.logger.warning("User cancelled apartment form")
                    return False
            except asyncio.TimeoutError:
                self.logger.warning("No response from user in 30 seconds")
                return False

        except Exception as e:
            self.logger.error(f"Error in apartmentfloorunit: {str(e)}")
            return False

    async def process_technical_fields(self, page: Page, json_handler) -> bool:
        """Process technical fields using the old working navigation logic"""
        
        try:
            self.logger.info("Starting technical field processing with old navigation logic")
            
            # **OLD WORKING NAVIGATION LOGIC**
            await page.locator("#flexipage_tab__item").click()
            await page.wait_for_timeout(3000)

            # Load data
            data = json_handler.load_json()
            
            # **FIX: Validate data structure**
            if not data or "technical_field" not in data:
                self.logger.error("Invalid data structure - missing technical_field")
                return False
            
            # Upload input data to S3
            self.s3_manager.upload_file(data, 'json_data', 'technical_field_input_data.json')
            
            # Take screenshot before processing
            await self.take_screenshot_and_upload(page, "before_processing")

            # **ENHANCED FORM DETECTION LOGIC**
            selector_apartment = "//button[@role='combobox' and @name='apartmentFloorUnit' and contains(@class, 'slds-combobox__input')]"
            selector_floor = "//button[@role='combobox' and @name='floorName' and contains(@class, 'slds-combobox__input')]"

            combobox_apartment = page.get_by_label("Technical Detail").locator(selector_apartment)
            combobox_floor = page.get_by_label("Technical Detail").locator(selector_floor)

            result = False
            
            # Try apartment form first
            if await combobox_apartment.is_visible(timeout=3000):
                self.logger.info("Apartment form detected, processing...")
                result = await self.apartmentfloorunit(page, data)
            elif await combobox_floor.is_visible(timeout=3000):
                self.logger.info("Floor form detected, processing...")
                result = await self.floorunit(page, data)
            else:
                # Try to add independent house
                self.logger.info("No form detected, trying to add independent house...")
                try:
                    add_house_button = page.get_by_title("Add Independent House")
                    if await add_house_button.is_visible(timeout=3000):
                        await add_house_button.click()
                    else:
                        await page.get_by_role("button", name="Add Independent House").click()
                except Exception as e:
                    self.logger.warning(f"Could not click Add Independent House button: {e}")

                await page.wait_for_timeout(2000)

                # Check again after adding house
                if await combobox_apartment.is_visible(timeout=3000):
                    self.logger.info("Apartment form now visible, processing...")
                    result = await self.apartmentfloorunit(page, data)
                elif await combobox_floor.is_visible(timeout=3000):
                    self.logger.info("Floor form now visible, processing...")
                    result = await self.floorunit(page, data)
                else:
                    self.logger.error("Neither apartmentFloorUnit nor floorName was visible after attempting to add house")
                    result = False

            # Take screenshot after processing
            await self.take_screenshot_and_upload(page, "after_processing")
            
            if result:
                self.logger.info("Technical field processing completed successfully")
            else:
                self.logger.error("Technical field processing failed")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error during technical field processing: {str(e)}")
            await self.take_screenshot_and_upload(page, "processing_error")
            return False

# MAIN FUNCTION
async def technical_field_main(page: Page, json_handler, s3_manager: UnifiedS3Manager) -> bool:
    """
    Main technical field automation function using old working logic
    
    Args:
        page: Playwright page object
        json_handler: JSON handler for data management
        s3_manager: Unified S3 manager instance
        
    Returns:
        bool: True if successful, False otherwise
    """
    
    # Initialize technical field automation
    automation = TechnicalFieldAutomation(s3_manager)
    
    try:
        automation.logger.info("Starting Technical Field automation workflow")
        
        # Upload initial status
        initial_status = {
            "status": "started",
            "process_uuid": s3_manager.process_uuid,
            "start_time": datetime.now().isoformat()
        }
        s3_manager.upload_file(initial_status, 'json_data', 'technical_field_start_status.json')
        
        # Process technical fields using old logic
        process_success = await automation.process_technical_fields(page, json_handler)
        
        if process_success:
            # Upload completion status
            completion_status = {
                "status": "completed",
                "process_uuid": s3_manager.process_uuid,
                "completion_time": datetime.now().isoformat()
            }
            s3_manager.upload_file(completion_status, 'json_data', 'technical_field_completion_status.json')
            
            automation.logger.info("Technical Field automation completed successfully")
            return True
        else:
            raise Exception("Technical field processing returned False")
        
    except Exception as e:
        automation.logger.error(f"Technical Field automation failed: {str(e)}")
        
        # Upload error report
        error_report = {
            "status": "failed",
            "error": str(e),
            "process_uuid": s3_manager.process_uuid,
            "failure_time": datetime.now().isoformat(),
            "error_type": type(e).__name__
        }
        s3_manager.upload_file(error_report, 'json_data', 'technical_field_error_report.json')
        
        # Take final error screenshot
        try:
            await automation.take_screenshot_and_upload(page, "final_error")
        except:
            pass
        
        return False
        
    finally:
        # Save all logs
        automation.logger.save_logs()

# Entry point for testing
if __name__ == "__main__":
    print("technical.py - Technical Field Automation Module")
    print("This module should be imported and called from the main automation script.")
