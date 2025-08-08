import logging
from datetime import datetime
from playwright.async_api import TimeoutError as PlaywrightTimeoutError, Page
from dotenv import load_dotenv
from typing import Optional
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

class DrafterFieldAutomation:
    """Drafter field automation with S3-only data source"""

    def __init__(self, s3_manager: UnifiedS3Manager):
        self.s3_manager = s3_manager
        self.logger = UnifiedLogger(s3_manager, "drafter_field")

    async def take_screenshot_and_upload(self, page: Page, context: str = "general") -> Optional[str]:
        """Takes a screenshot and uploads it to unified S3 storage"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"drafter_field_{context}_{timestamp}.png"

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
        
    def load_document_analysis_data(self, case_number):
        """Load document analysis data from S3"""
        try:
            doc_data = self.s3_manager.download_json(f"json_data/document_analysis_{case_number}.json")
            if doc_data:
                self.logger.info(f"✅ Successfully loaded document analysis data from S3 for case: {case_number}")
                return doc_data
            else:
                self.logger.warning(f"⚠️ No document analysis data found in S3 for case: {case_number}")
                return None
        except Exception as e:
            self.logger.error(f"❌ Error loading document analysis data from S3: {str(e)}")
            return None


    def load_extracted_data_only(self, case_number):
        """Load ONLY AI extracted data from S3 - no local JSON fallback"""
        try:
            # **ONLY load from S3 extracted analysis**
            extracted_data = self.s3_manager.download_json(f"json_data/extracted_analysis_{case_number}.json")
            if extracted_data:
                self.logger.info(f"✅ Successfully loaded extracted data from S3 for case: {case_number}")
                return extracted_data
            else:
                self.logger.warning(f"⚠️ No extracted data found in S3 for case: {case_number}")
                return self.get_default_drafter_template()
        except Exception as e:
            self.logger.error(f"❌ Error loading extracted data from S3: {str(e)}")
            return self.get_default_drafter_template()
        
    def find_blank_fields(self ,data):
        blank_fields = []

        for key, value in data.items():
            if isinstance(value, (str, list, dict, tuple)) and len(value) == 0:
                blank_fields.append(key)
        
        return blank_fields
    
    def load_combined_analysis_data(self, case_number):
        """Load and combine both image extraction and document analysis data"""
        try:
            self.logger.info(f"🔄 Loading combined analysis data for case: {case_number}")
            
            # Load image extraction data
            image_data = self.load_extracted_data_only(case_number)
            
            # Load document analysis data
            doc_data = self.load_document_analysis_data(case_number)
            
            # Combine the data
            combined_data = {}
            
            if image_data:
                combined_data['image_analysis'] = image_data
                self.logger.info("✅ Image analysis data loaded")
            
            if doc_data:
                combined_data['document_analysis'] = doc_data
                self.logger.info("✅ Document analysis data loaded")
            
            if not combined_data:
                self.logger.warning("⚠️ No analysis data found, using default template")
                return self.get_default_drafter_template()
            
            # Upload combined data to S3 for reference
            self.s3_manager.upload_file(combined_data, 'json_data', 'combined_analysis_data.json')
            
            return combined_data
            
        except Exception as e:
            self.logger.error(f"❌ Error loading combined analysis data: {str(e)}")
            return self.get_default_drafter_template()

    def get_default_drafter_template(self):
        """Return default template structure for drafter fields"""
        return {
            "drafter_field": {
                # General Information
                "Document Provided for Valuation": " ",
                "Status of holding": "",
                "Type of Property As per Document": "",
                "Property situated": "",
                "Flats(on each floor)": "",
                "Occupancy percent": "",
                "Residual age of Property (years)": "",
                "Request From/Allocated By": "",

                #Documented Address
                "Plot No/House No": "",
                "Floor No.": "",
                "Building/Wing Name": "",
                "Street No./Road Name": "",
                "Scheme Name": "",
                "Village/City": "",
                "Pincode": "",
                "Locality": "",
                "Address as per Identifier Docs": "",

                #Locality Information
                "Class of Locality": "",
                "Property usage": "",
                "Any Negative Locality": "",
                "Location- As per DLC Portal": "",

                # Property Basic condition
                "Basic amenities available? (Water, Road)": "Yes",
                "Maintenance Levels": "",
                "Deviation For AU-Remark": "",

                #Setback Info
                "Setbacks As per Rule-Front": "",
                "Setbacks As per Rule-Back": "",
                "Setbacks As per Rule-Side 1": "",
                "Setbacks As per Rule-Side 2": "",

                # Boundary information
                "East - As Per Document(Boundary)": "",
                "West - As Per Document(Boundary)": "",
                "North - As per Document(Boundary)": "",
                "south - As per Document(Boundary)": "",

                # Dimensions
                "Unit For Dimension (Doc)": "ft",
                "East - As per Docs(Dimension)": "",
                "West - As per Docs(Dimension)": "",
                "North - As per Docs(Dimension)": "",
                "South - As per Docs(Dimension)": ""
            
        }
    }
    def convert_combined_to_drafter_format(self, combined_data):
        """Convert combined analysis data (image + document) to drafter field format"""
        try:
            # Start with default template
            drafter_data = self.get_default_drafter_template()
            
            self.logger.info("🔄 Converting combined analysis data to drafter format")
            
            # Process document analysis data first (higher priority for ownership/title info)
            if 'document_analysis' in combined_data:
                doc_data = combined_data['document_analysis']
                self.logger.info("📄 Processing document analysis data")
                
                # Map document fields to drafter fields
                doc_field_mapping = {
                    # Document-specific fields
                    "Property situated": "Property_Situated", 
                    "Document Provided for Valuation":"Document_Type",
                    "Status of holding": "Holding_status",
                    "Type of Property As per Document": "Type_of_Property_As_per_document",
                    "Plot No/House No": "Plot_No/House_No",
                    "Floor No.": "Floor_No",
                    "Building/Wing Name": "Building/Wing_Name",
                    "Street No./Road Name": "Street_No/Road_Name",
                    "Scheme Name": "Scheme_Name",
                    "Village/City": "Village_City",
                    "Pincode": "pincode",
                    "Locality": "Locality",

                    "Setbacks As per Rule-Front": "setbacks.Setbacks As per Rule-Front",
                    "Setbacks As per Rule-Back": "setbacks.Setbacks As per Rule-Back",
                    "Setbacks As per Rule-Side 1": "setbacks.Setbacks As per Rule-Side 1",
                    "Setbacks As per Rule-Side 2": "setbacks.Setbacks As per Rule-Side 2",

                    # Boundary fields from document
                    "East - As Per Document(Boundary)": "property_boundaries.east",
                    "West - As Per Document(Boundary)": "property_boundaries.west", 
                    "North - As Per Document(Boundary)": "property_boundaries.north",
                    "South - As Per Document(Boundary)": "property_boundaries.south",
                    
                    # Dimension fields from document
                    "East - As Per Docs(Dimension)": "property_dimensions.east",
                    "West - As Per Docs(Dimension)": "property_dimensions.west",
                    "North - As Per Docs(Dimension)": "property_dimensions.north", 
                    "South - As Per Docs(Dimension)": "property_dimensions.south",
                    "Unit - For Dimension (Doc)": "property_dimensions.unit"
                }
                
                # Update drafter data with document analysis values
                for drafter_field, doc_field in doc_field_mapping.items():
                    try:
                        if '.' in doc_field:
                            # Handle nested fields like property_boundaries.east
                            main_field, sub_field = doc_field.split('.')
                            if main_field in doc_data and isinstance(doc_data[main_field], dict):
                                if sub_field in doc_data[main_field] and doc_data[main_field][sub_field] != "NA":
                                    drafter_data["drafter_field"][drafter_field] = doc_data[main_field][sub_field]
                                    self.logger.info(f"✅ Mapped {doc_field} -> {drafter_field}")
                        else:
                            # Handle top-level fields
                            if doc_field in doc_data and doc_data[doc_field] != "NA":
                                drafter_data["drafter_field"][drafter_field] = doc_data[doc_field]
                                self.logger.info(f"✅ Mapped {doc_field} -> {drafter_field}")
                    except Exception as field_error:
                        self.logger.warning(f"⚠️ Failed to map {doc_field}: {field_error}")
            
            # Process image analysis data second (fills in remaining fields)
            if 'image_analysis' in combined_data:
                image_data = combined_data['image_analysis']
                self.logger.info("🖼️ Processing image analysis data")
                
                # Handle both nested drafter_field and top-level fields
                if isinstance(image_data, dict):
                    if "drafter_field" in image_data:
                        image_extracted = image_data["drafter_field"]
                        
                        # Map image analysis fields
                        image_field_mapping = {
                            # Property condition fields
                            "Flats(on each floor)": "FlatOnEachFloor",
                            
                            # Analysis fields
                            "Occupancy percent": "OccupancyPercent",
                            "Class of Locality":"ClassOfLocality",
                            "Property usage": "PropertyUsage",
                        }
                        
                        # Update drafter data with image analysis values (only if not already set)
                        for drafter_field, image_field in image_field_mapping.items():
                            if (image_field in image_extracted and 
                                image_extracted[image_field] and 
                                image_extracted[image_field] != "NA" and
                                not drafter_data["drafter_field"][drafter_field]):
                                drafter_data["drafter_field"][drafter_field] = image_extracted[image_field]
                                self.logger.info(f"✅ Mapped image field {image_field} -> {drafter_field}")
                    
                    # Also check top-level image fields
                    top_level_image_mapping = {
                            "Flats(on each floor)": "FlatOnEachFloor",
                            
                            # Analysis fields
                            "Occupancy percent": "OccupancyPercent",
                            "Class of Locality":"ClassOfLocality",
                            "Property usage": "PropertyUsage",
                    }
                    
                    for drafter_field, image_field in top_level_image_mapping.items():
                        if (image_field in image_data and 
                            image_data[image_field] and 
                            image_data[image_field] != "NA" and
                            not drafter_data["drafter_field"][drafter_field]):
                            drafter_data["drafter_field"][drafter_field] = image_data[image_field]
                            self.logger.info(f"✅ Mapped top-level image field {image_field} -> {drafter_field}")
            
            self.logger.info("✅ Successfully converted combined analysis data to drafter format")
            return drafter_data
            
        except Exception as e:
            self.logger.error(f"❌ Error converting combined analysis data: {str(e)}")
            return self.get_default_drafter_template()

    async def fill_field(self, page, label, value, delay=300):
        """Fill a field with enhanced error handling and tracking"""
        if not value or str(value).strip() == "":
            self.logger.debug(f"Skipping empty field: {label}")
            return False

        self.logger.info(f"Filling field: {label} with value: {value}")
        try:
            # Try multiple selectors for better compatibility
            selectors = [
                page.get_by_label(label),
                page.locator(f"input[aria-label='{label}']"),
                page.locator(f"textarea[aria-label='{label}']"),
                page.locator(f"//label[contains(text(),'{label}')]/following-sibling::input"),
                page.locator(f"//label[contains(text(),'{label}')]/following-sibling::textarea")
            ]

            filled = False
            for selector in selectors:
                try:
                    await selector.fill(str(value))
                    await page.wait_for_timeout(delay)
                    filled = True
                    break
                except Exception:
                    continue

            if not filled:
                self.logger.warning(f"Could not find field: {label}")
                return False

            return True

        except Exception as e:
            self.logger.error(f"Failed to fill field {label}: {e}")
            await self.take_screenshot_and_upload(page, f"fill_field_error_{label.replace(' ', '_')}")
            return False

    async def select_dropdown(self, page, label, value, delay=300):
        """Select dropdown option with enhanced error handling"""
        if not value or str(value).strip() == "":
            self.logger.debug(f"Skipping empty dropdown: {label}")
            return False

        self.logger.info(f"Selecting dropdown: {label} with value: {value}")
        try:
            await page.get_by_role("combobox", name=label).click()
            await page.wait_for_timeout(delay)
            await page.get_by_role("option", name=value, exact=True).click()
            await page.wait_for_timeout(delay)
            return True
        except Exception as e:
            self.logger.error(f"Failed to select dropdown {label}: {e}")
            await self.take_screenshot_and_upload(page, f"dropdown_error_{label.replace(' ', '_')}")
            return False

    async def navigate_to_drafter_field(self, page: Page) -> bool:
        """Navigate to the Drafter Field tab"""
        try:
            self.logger.info("Navigating to Drafter Field tab")

            # Navigate to Drafter's Field tab
            await page.locator("//a[@data-label=\"Drafter's Field\"]").click()
            await page.wait_for_timeout(3000)

            # Wait for the page to load
            self.logger.info("Proceeding to edit Drafter Field tab")

            await page.wait_for_selector("//button[@data-id='Status_of_holding__c']", timeout=1000)
            await page.locator("//button[@data-id='Status_of_holding__c']").click()

            # Take screenshot after navigation
            await self.take_screenshot_and_upload(page, "after_drafter_nav")

            self.logger.info("Successfully navigated to Drafter Field tab")
            return True

        except Exception as e:
            self.logger.error(f"Failed to navigate to Drafter Field tab: {e}")
            await self.take_screenshot_and_upload(page, "drafter_nav_error")
            return False

    async def process_drafter_fields(self, page: Page, json_handler) -> bool:
        """Process drafter fields using ONLY S3 extracted data with manual input for missing fields"""
        try:
            self.logger.info("Starting drafter field processing with S3-only data")

            # **LOAD ONLY from S3 extracted analysis**
            case_number = json_handler.case_number
            combined_data = self.load_combined_analysis_data(case_number)
            
            if combined_data and (combined_data != self.get_default_drafter_template()):
                self.logger.info("✅ Using combined AI analysis data (image + document) for field filling")
                # Convert combined data to proper drafter format
                data = self.convert_combined_to_drafter_format(combined_data)
                
                # Upload converted data to S3 for reference
                self.s3_manager.upload_file(data, 'json_data', 'drafter_field_converted_data.json')
            else:
                self.logger.warning("⚠️ No combined analysis data found, using default template")
                data = self.get_default_drafter_template()

            # Upload initial input data to S3
            self.s3_manager.upload_file(data, 'json_data', f'drafter_field_input_data_{case_number}.json')

            # Get drafter field data
            d = data.get("drafter_field", {})
            blank_fields=self.find_blank_fields(d)

            # **PHASE 1: AI FILLS ALL AVAILABLE FIELDS**
            self.logger.info("🤖 PHASE 1: AI filling all available fields...")

            # Process general fields
            self.logger.info("Processing general fields...")
            general_fields = [ 
                ('Document Provided for Valuation', d.get('Document Provided for Valuation')),
                ('Flats(on each floor)', d.get('Flats(on each floor)')),
                ('Occupancy percent', d.get('Occupancy percent')),
                ('Residual age of Property (years)', d.get('Residual age of Property (years)')),
                ('Request From/Allocated By', d.get('Request From/Allocated By')),
            ]

            ai_filled_count = 0
            for label, value in general_fields:
                if await self.fill_field(page, label, value):
                    ai_filled_count += 1
            # Process dropdown fields
            self.logger.info("Processing dropdown fields...")
            if await self.select_dropdown(page, 'Status of holding', d.get('Status of holding')):
                ai_filled_count += 1
            if await self.select_dropdown(page, 'Type of Property As per document', d.get('Type of Property As per document')):
                ai_filled_count += 1
            if await self.select_dropdown(page, 'Property situated', d.get('Property situated')):
                ai_filled_count += 1


            # Process address fields
            self.logger.info("Processing address fields...")
            address_fields = [
                ('Plot No/House No', d.get('Plot No/House No')),
                ('Floor No.', d.get('Floor No.')),
                ('Building/Wing Name', d.get('Building/Wing Name')),
                ('Street No./Road Name', d.get('Street No./Road Name')),
                ('Scheme Name', d.get('Scheme Name')),
                ('Village/City', d.get('Village/City')),
                ('Locality', d.get('Locality'))
            ]
            for field in address_fields:
                if await self.fill_field(page, field, d.get(field), delay=500):
                    ai_filled_count += 1
            address=d.get('Plot No/House No')+ d.get('Floor No.')+ d.get('Building/Wing Name')+ d.get('Street No./Road Name')+ d.get('Scheme Name')+ d.get('Village/City')+ d.get('Locality')
            await page.get_by_label("Address as per Identifier Docs").fill(address)

            # #pincode.
            self.logger.info("Processing pincode")
            pincode=d.get('Pincode')
            if pincode == "" or pincode == "NA" or not pincode:
                self.logger.warning("Pincode is empty, skipping pincode field")
            else:
                        # Locate the selected item within the Pincode field's combobox
                label = page.locator("label:has-text('Pincode')")
                pincode_input = label.locator("xpath=following::input[1]")

                # Extract current value
                value = await pincode_input.get_attribute("data-value")
                if not value :
                    await page.get_by_label("Pincode").click()
                    await page.get_by_label("Pincode").fill(pincode)

                                # # Step 2: Scope locator to the combobox container that follows the "Pincode" label
                    combobox_container = page.locator("label:has-text('Pincode')").locator("..").locator("lightning-base-combobox")

                                # # Step 3: Find the option inside this specific combobox
                    option_locator = combobox_container.locator("lightning-base-combobox-item")

                                # # Step 4: Wait for the first option to become visible and click it
                    await option_locator.first.wait_for(state="visible", timeout=2000)
                    await option_locator.first.click()
                    await page.wait_for_timeout(2000)

                    print("completed")

                else:
                    self.logger.info("Pincode filled...")

                
            # Process locality fields
            self.logger.info("Processing locality fields...")

            if await self.select_dropdown(page, 'Class of Locality', d.get('Class of Locality')):
                ai_filled_count += 1
            if await self.select_dropdown(page, 'Property usage', d.get('Property usage')):
                ai_filled_count += 1
            if await self.select_dropdown(page, 'Unit for Dimension (Doc)', "ft"):
                ai_filled_count += 1

            # Process boundary fields
            self.logger.info("Processing boundary fields...")
            boundary_fields = [
                ('East - As Per Document(Boundary)', d.get('East - As Per Document(Boundary)')),
                ('West - As Per Document(Boundary)', d.get('West - As Per Document(Boundary)')),
                ('North - As per Document(Boundary)', d.get('North - As per Document(Boundary)')),
                ('south - As per Document(Boundary)', d.get('south - As per Document(Boundary)')),
                ('Setbacks As per Rule-Front', d.get('Setbacks As per Rule-Front')),
                ('Setbacks As per Rule-Back', d.get('Setbacks As per Rule-Back')),
                ('Setbacks As per Rule-Side 1', d.get('Setbacks As per Rule-Side 1')),
                ('Setbacks As per Rule-Side 2', d.get('Setbacks As per Rule-Side 2'))
            ]
            for label, value in boundary_fields:
                if await self.fill_field(page, label, value):
                    ai_filled_count += 1

            # Process dimension fields
            self.logger.info("Processing dimension fields...")
            if await self.select_dropdown(page, 'Unit for Dimension (Doc)', d.get('Unit for Dimension (Doc)')):
                ai_filled_count += 1

            dimension_fields = [
                ('East - As per Docs(Dimension)', d.get('East - As per Docs(Dimension)')),
                ('West - As per Docs(Dimension)', d.get('West - As per Docs(Dimension)')),
                ('North - As per Docs(Dimension)', d.get('North - As per Docs(Dimension)')),
                ('South - As per Docs(Dimension)', d.get('South - As per Docs(Dimension)')),
            ]
            for label, value in dimension_fields:
                if await self.fill_field(page, label, value):
                    ai_filled_count += 1

            # Process amenities fields
            self.logger.info("Processing amenities fields...")
            amenities_fields = [
                ('Maintenance Levels', "Average"),
            ]
            for label, value in amenities_fields:
                if await self.fill_field(page, label, value):
                    ai_filled_count += 1

            if await self.select_dropdown(page, 'Basic amenities available? (Water, Road)', "Yes"):
                ai_filled_count += 1

            self.logger.info(f"🤖 AI filled {ai_filled_count} fields successfully")

            # Take screenshot after AI processing
            await self.take_screenshot_and_upload(page, f"after_ai_processing_{case_number}")
            # # Click save button
            await page.get_by_role("button", name="Save").click()
            await page.wait_for_timeout(2000)

            # Take screenshot after saving
            await self.take_screenshot_and_upload(page, f"after_save_{case_number}")

            self.logger.info("✅ Drafter field AI processing completed successfully")
            return blank_fields

        except PlaywrightTimeoutError as te:
            self.logger.error(f"Timeout occurred during drafter field processing: {str(te)}")
            await self.take_screenshot_and_upload(page, f"timeout_error_{case_number}")
            return False
        except Exception as e:
            self.logger.error(f"Error in drafter field processing: {e}")
            await self.take_screenshot_and_upload(page, f"processing_error_{case_number}")
            return False

# MAIN FUNCTION - Updated to work with S3-only data
async def drafter_field_main(page: Page, json_handler, s3_manager: UnifiedS3Manager) -> bool:
    """
    Main drafter field automation function - S3-only data source

    Args:
        page: Playwright page object
        json_handler: JSON handler for case number only
        s3_manager: Unified S3 manager instance

    Returns:
        bool: True if successful, False otherwise
    """

    # Initialize drafter field automation
    automation = DrafterFieldAutomation(s3_manager)

    try:
        automation.logger.info("Starting Drafter Field automation workflow with S3-only data")

        # Upload initial status
        initial_status = {
            "status": "started",
            "process_uuid": s3_manager.process_uuid,
            "start_time": datetime.now().isoformat(),
            "data_source": "s3_extracted_analysis_only"
        }
        s3_manager.upload_file(initial_status, 'json_data', 'drafter_field_start_status.json')

        # Step 1: Navigate to Drafter Field tab
        nav_success = await automation.navigate_to_drafter_field(page)
        if not nav_success:
            raise Exception("Failed to navigate to Drafter Field tab")

        # Step 2: Process drafter fields using S3 data only
        #returning data as process_success to pass into drafter_manual
        process_success = await automation.process_drafter_fields(page, json_handler)
        if not process_success:
            raise Exception("Failed to process drafter fields")

        # Upload completion status
        completion_status = {
            "status": "completed",
            "process_uuid": s3_manager.process_uuid,
            "completion_time": datetime.now().isoformat(),
            "data_source": "s3_extracted_analysis_only"
        }
        s3_manager.upload_file(completion_status, 'json_data', 'drafter_field_completion_status.json')

        automation.logger.info("Drafter Field automation completed successfully using S3 data")
        return process_success 

    except Exception as e:
        automation.logger.error(f"Drafter Field automation failed: {str(e)}")

        # Upload error report
        error_report = {
            "status": "failed",
            "error": str(e),
            "process_uuid": s3_manager.process_uuid,
            "failure_time": datetime.now().isoformat(),
            "error_type": type(e).__name__,
            "data_source": "s3_extracted_analysis_only"
        }
        s3_manager.upload_file(error_report, 'json_data', 'drafter_field_error_report.json')

        # Take final error screenshot
        try:
            await automation.take_screenshot_and_upload(page, "final_error")
        except:
            pass

        return False

    finally:
        # Save all logs
        automation.logger.save_logs()
