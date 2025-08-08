import boto3
import asyncio
import json
import logging
import os
import re
from botocore.exceptions import NoCredentialsError, ClientError
from datetime import datetime
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from static.unified_s3_manager import UnifiedS3Manager

# --- Configuration and Logging ---
load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('salesforce_automation.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --- AWS S3 Data Management ---
class S3DataManager:
    """A centralized manager for all AWS S3 interactions."""
    def __init__(self, s3_manager=None):
        if s3_manager and hasattr(s3_manager, 's3_client'):
            # Use the existing UnifiedS3Manager instance
            self.s3_client = s3_manager.s3_client
            self.bucket = s3_manager.bucket
            self.base_path = s3_manager.base_path
            self.case_number = getattr(s3_manager, 'case_number', 'UNKNOWN')
            logger.info(f"S3DataManager initialized using UnifiedS3Manager for bucket: {self.bucket}")
        else:
            # Fallback to direct initialization
            try:
                self.s3_client = boto3.client(
                    's3',
                    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
                    region_name=os.getenv('AWS_REGION')
                )
                self.bucket = os.getenv('S3_BUCKET')
                self.base_path = None
                self.case_number = 'UNKNOWN'
                logger.info(f"S3DataManager initialized directly for bucket: {self.bucket}")
            except Exception as e:
                logger.error(f"Failed to initialize S3 client: {e}")
                raise

    def upload(self, data, key, content_type='application/json'):
        """Uploads data (dict or bytes) to a specific key in S3."""
        try:
            # Use base_path if available (from UnifiedS3Manager)
            full_key = f"{self.base_path}/{key}" if self.base_path else key
            
            body = json.dumps(data, indent=2) if isinstance(data, dict) else data
            self.s3_client.put_object(
                Bucket=self.bucket,
                Key=full_key,
                Body=body,
                ContentType=content_type
            )
            logger.info(f"Successfully uploaded to s3://{self.bucket}/{full_key}")
        except (NoCredentialsError, ClientError) as e:
            logger.error(f"S3 upload failed for key {key}: {e}")
            raise

async def take_screenshot_and_upload(page, s3_manager, client_ref):
    """Takes a screenshot and uploads it directly to the client's S3 folder."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    key = f"screenshots/mobile_app_error_{timestamp}.png"
    try:
        screenshot_bytes = await page.screenshot()
        s3_manager.upload(screenshot_bytes, key, content_type='image/png')
        logger.info(f"Screenshot uploaded: {key}")
    except Exception as e:
        logger.error(f"Failed to take and upload screenshot to {key}: {e}")

# --- Enhanced Data Access Functions ---
def get_extracted_data(json_handler, s3_manager):
    """Load image extraction data from S3"""
    try:
        case_number = getattr(json_handler, 'case_number', 'UNKNOWN')
        extracted_data = s3_manager.download_json(f"json_data/extracted_analysis_{case_number}.json")
        
        if extracted_data:
            logger.info(f"✅ Successfully loaded image extraction data from S3 for case: {case_number}")
            return extracted_data
        else:
            logger.warning(f"⚠️ No image extraction data found in S3 for case: {case_number}")
            return None
            
    except Exception as e:
        logger.error(f"❌ Error loading image extraction data from S3: {str(e)}")
        return None

def get_document_analysis_data(json_handler, s3_manager):
    """Load document analysis data from S3"""
    try:
        case_number = getattr(json_handler, 'case_number', 'UNKNOWN')
        doc_data = s3_manager.download_json(f"json_data/document_analysis_{case_number}.json")
        
        if doc_data:
            logger.info(f"✅ Successfully loaded document analysis data from S3 for case: {case_number}")
            return doc_data
        else:
            logger.warning(f"⚠️ No document analysis data found in S3 for case: {case_number}")
            return None
            
    except Exception as e:
        logger.error(f"❌ Error loading document analysis data from S3: {str(e)}")
        return None

def get_combined_analysis_data(json_handler, s3_manager):
    """Load and combine both image extraction and document analysis data"""
    try:
        logger.info("🔄 Loading combined analysis data for mobile app automation")
        
        # Load image extraction data
        image_data = get_extracted_data(json_handler, s3_manager)
        
        # Load document analysis data
        doc_data = get_document_analysis_data(json_handler, s3_manager)
        
        # Combine the data
        combined_data = {}
        
        if image_data:
            combined_data['image_analysis'] = image_data
            logger.info("✅ Image analysis data loaded for mobile app")
        
        if doc_data:
            combined_data['document_analysis'] = doc_data
            logger.info("✅ Document analysis data loaded for mobile app")
        
        if not combined_data:
            logger.warning("⚠️ No analysis data found for mobile app")
            return None
        
        # Upload combined data to S3 for reference
        case_number = getattr(json_handler, 'case_number', 'UNKNOWN')
        s3_data_manager = S3DataManager(s3_manager)
        s3_data_manager.upload(combined_data, f'json_data/mobile_app_combined_analysis_{case_number}.json')
        
        return combined_data
        
    except Exception as e:
        logger.error(f"❌ Error loading combined analysis data: {str(e)}")
        return None

def get_default_mobile_template():
    """Return default template structure for mobile app fields"""
    return {
                "Plot No/House No": "",
                "Floor No.": "",
                "Building/Wing Name": "",
                "Street No./Road Name": "",
                "Scheme Name": "",
                "Village/City": "",
                "Nearby Landmark": "",
                "Pincode": "",
                "District": "",
                "State": "",

                "Person Met At Site": "",
                "Occupancy Status": "",
                "Name of Property Owner": "",
                "If rented, Name and No of Occupants": "",
                "Condition of Approach Road": "",
                "Approach /Width of Road to the property": "",
                "Property Type": "",
                "Electricity Meter Status": "",
                "Electricty Meter No": "",
                "Type of Property As per Site": "",
                "Electricity Bill No": "",
                "Elec. Meter No. Matching with Elec. Bill": "",
                "Water Connection Status": "",
                "Gas Line Connection": "",
                "Sewer Connection": "",
                "Other Connection Remark": "",
                "Lift availability": "",
                "Structure Type": "",
                "Nature of Construction": "",
                "Flooring": "",
                "Type of Roof": "",
                "Quality of Construction": "",
                "Age of Property (years)": "",
                "Marketability": "",
                "Stage of Construction": "",
                "No of houses in village (Rural cases)": "",
                "Development in the scheme (in %)": "",
                "Is Property Identified ?": "",
                "Identifier Document": "",
                "Plot Demarcted at Site": "",

                "East - As per Actual(Boundary)": "",
                "West - As per Actual(Boundary)": "",
                "North - As per Actual(Boundary)": "",
                "South - As Per Actual(Boundary)": "",

                "Unit for Dimension (Actual)": "",
                "East - As per Actual(Dimension)": "",
                "West - As per Actual(Dimension)": "",
                "North - As per Actual(Dimension)": "",
                "South - As per Actual(Dimension)": "",

                "Setbacks As per Actual-Front": "",
                "Setbacks As per Actual-Back": "",
                "Setbacks As per Actual-Side 1": "",
                "Setbacks As per Actual-Side 2": "",

                "Local Dealer Name": "",
                "Local Dealer Contact": "",
                "Unit local dealer": "",
                "Min Rate local dealer": "",
                "Max rate local dealer": "",
                "Unit technical": "",
                "Min Rate Technical": "",
                "Max Rate Technical": "",
                "Valuation Remark": "",
    }

def convert_combined_to_mobile_format(combined_data):
    """Convert combined analysis data (image + document) to mobile app field format"""
    if not combined_data:
        return get_default_mobile_template()
    
    try:
        # Start with default template
        mobile_data = get_default_mobile_template()
        
        logger.info("🔄 Converting combined analysis data to mobile app format")
        
        # Process document analysis data first (higher priority for ownership/legal info)
        if 'document_analysis' in combined_data:
            doc_data = combined_data['document_analysis']
            logger.info("📄 Processing document analysis data for mobile app")
            
            # Map document fields to mobile app fields
            doc_field_mapping = {
                # Document-specific fields
                'Name of Property Owner': 'Owner_Name',
                'Identifier Document': 'Document_Type',
                
                # Address fields from document
                'Plot No/House No': 'Plot_No/House_No',
                'Village/City': 'Village/City',
                'Floor No.': 'Floor_No',
                'Building/Wing Name': "Building/Wing_Name",
                'Street No./Road Name': "Street_No/Road_Name",
                'Scheme Name': "Scheme_Name",
                'District': 'District',
                'State': 'State',
                'Pincode': 'pincode',
                
            }
            
            # Update mobile data with document analysis values
            for mobile_field, doc_field in doc_field_mapping.items():
                try:
                    if '.' in doc_field:
                        # Handle nested fields like property_boundaries.east
                        main_field, sub_field = doc_field.split('.')
                        if main_field in doc_data and isinstance(doc_data[main_field], dict):
                            if sub_field in doc_data[main_field] and doc_data[main_field][sub_field] != "NA":
                                mobile_data[mobile_field] = doc_data[main_field][sub_field]
                                logger.info(f"✅ Mapped document field {doc_field} -> {mobile_field}")
                    else:
                        # Handle top-level fields
                        if doc_field in doc_data and doc_data[doc_field] != "NA":
                            # Special handling for property_address - extract components
                            if mobile_field in ['Village/City', 'District', 'State', 'Pincode'] and doc_field == 'property_address':
                                address_value = doc_data[doc_field]
                                if address_value:
                                    # Extract specific components from address
                                    if mobile_field == 'Pincode':
                                        # Extract PIN code (6 digits)
                                        pin_match = re.search(r'\b\d{6}\b', address_value)
                                        if pin_match:
                                            mobile_data[mobile_field] = pin_match.group()
                                    elif mobile_field == 'State':
                                        # Extract state (look for common state names)
                                        state_keywords = ['gujarat', 'maharashtra', 'karnataka', 'tamil nadu', 'rajasthan', 'uttar pradesh']
                                        for state in state_keywords:
                                            if state in address_value.lower():
                                                mobile_data[mobile_field] = state.title()
                                                break
                                    # For other address fields, use the full address as fallback
                                    elif not mobile_data[mobile_field]:
                                        mobile_data[mobile_field] = address_value
                            else:
                                mobile_data[mobile_field] = doc_data[doc_field]
                                logger.info(f"✅ Mapped document field {doc_field} -> {mobile_field}")
                except Exception as field_error:
                    logger.warning(f"⚠️ Failed to map document field {doc_field}: {field_error}")
        
        # Process image analysis data second (fills in remaining fields)
        if 'image_analysis' in combined_data:
            image_data = combined_data['image_analysis']
            logger.info("🖼️ Processing image analysis data for mobile app")
            
            # Handle both nested drafter_field and top-level fields
            if isinstance(image_data, dict):
                if "drafter_field" in image_data:
                    drafter_data = image_data["drafter_field"]
                    
                    # Map from drafter fields to mobile fields
                    drafter_field_mappings = {
                        'East - As Per Actual(Boundary)': drafter_data.get('EastAsPerDocument(Boundary)', ''),
                        'West - As Per Actual(Boundary)': drafter_data.get('WestAsPerDocument(Boundary)', ''),
                        'North - As Per Actual(Boundary)': drafter_data.get('NorthAsPerDocument(Boundary)', ''),
                        'South - As Per Actual(Boundary)': drafter_data.get('SouthAsPerDocument(Boundary)', ''),
                        'East - As Per Actual(Dimension)': drafter_data.get('EastAsPerDocs(Dimension)', ''),
                        'West - As Per Actual(Dimension)': drafter_data.get('WestAsPerDocs(Dimension)', ''),
                        'North - As Per Actual(Dimension)': drafter_data.get('NorthAsPerDocs(Dimension)', ''),
                        'South - As Per Actual(Dimension)': drafter_data.get('SouthAsPerDocs(Dimension)', ''),
                        "Setbacks As per Actual-Front": drafter_data.get('SetbacksAsPerRule-Front', ''),
                        "Setbacks As per Actual-Back": drafter_data.get('SetbacksAsPerRule-Back', ''),
                        "Setbacks As per Actual-Side 1": drafter_data.get('SetbacksAsPerRule-Side 1', ''),
                        "Setbacks As per Actual-Side 2": drafter_data.get('SetbacksAsPerRule-Side 2', ''),
                        "Unit for Dimension (Actual)": "ft"
                    }
                    
                    # Update mobile data with image analysis values (only if not already set)
                    for mobile_field, value in drafter_field_mappings.items():
                        if (value and str(value).strip() and value != "NA" and 
                            not mobile_data.get(mobile_field)):
                            mobile_data[mobile_field] = value
                            logger.info(f"✅ Mapped image field -> {mobile_field}")
                
                                        
        # Remove empty values and clean up
        mobile_data = {k: v for k, v in mobile_data.items() if v and str(v).strip() and str(v).strip() != "NA"}
        
        logger.info(f"✅ Successfully converted combined analysis data to mobile format with {len(mobile_data)} populated fields")
        return mobile_data
        
    except Exception as e:
        logger.error(f"❌ Failed to convert combined analysis data to mobile format: {e}")
        return get_default_mobile_template()

def convert_extracted_to_mobile_format(extracted_data):
    """Convert extracted data to mobile app field format"""
    if not extracted_data:
        return get_default_mobile_template()
    
    try:
        # Start with default template
        mobile_data = get_default_mobile_template()
        
        # Map extracted data to mobile fields (same logic as Drafter Field)
        if isinstance(extracted_data, dict):
            # Check for drafter_field section first
            if "drafter_field" in extracted_data:
                drafter_data = extracted_data["drafter_field"]
                
                # Map from drafter fields to mobile fields
                field_mappings = {
                    'Plot No/House No': drafter_data.get('PlotNoHouseNo', ''),
                }
                
                # Update mobile data with mapped values
                for mobile_field, value in field_mappings.items():
                    if value and str(value).strip():
                        mobile_data[mobile_field] = value
                    
        # Remove empty values
        mobile_data = {k: v for k, v in mobile_data.items() if v and str(v).strip()}
        
        logger.info(f"✅ Successfully converted extracted data to mobile format with {len(mobile_data)} populated fields")
        return mobile_data
        
    except Exception as e:
        logger.error(f"❌ Failed to convert extracted data to mobile format: {e}")
        return get_default_mobile_template()

# --- Salesforce Automation Core Logic ---
async def checking_fields_filled_ornot(page):
    """Extracts data from the Mobile App section in Salesforce."""
    logger.info("Starting Salesforce field extraction.")
    data = {}
    try:
        # Navigate to Mobile App tab
        await page.locator("#flexipage_tab10__item").click()
        await page.mouse.wheel(0, 500)
        await page.wait_for_selector("//button[@data-id='Floor_No_1__c']", timeout=10000)
        await page.locator("//button[@data-id='Floor_No_1__c']").click()

        fields_to_extract = {
            'inputs': [
                'Name of Property Owner', 'Plot No/House No', 'Floor No.', 
                'Building/Wing Name', 'Street No./Road Name', 'Scheme Name',
                'Village/City','Pincode', 'District', 
                'East - As Per Actual(Boundary)', 'West - As Per Actual(Boundary)',
                'North - As Per Actual(Boundary)', 'South - As Per Actual(Boundary)', 
                'East - As Per Actual(Dimension)', 'West - As Per Actual(Dimension)', 
                'North - As Per Actual(Dimension)', 'South - As Per Actual(Dimension)', 
            ],
            'dropdowns': [
                'State', 
                'Property Type', 'Unit for Dimension (Actual)', 
                'Occupancy Status', 'Marketability', 'Stage of Construction', 
                'Development in the scheme (in %)', 'Plot Demarcted at Site'
            ]
        }

        # Extract input fields
        for label in fields_to_extract['inputs']:
            try:
                data[label] = await page.get_by_label("Mobile App Field").get_by_label(label).input_value(timeout=2000)
            except PlaywrightTimeoutError:
                logger.warning(f"Timeout extracting input: {label}")
                data[label] = ""

        # Extract dropdown fields
        for name in fields_to_extract['dropdowns']:
            try:
                value = await page.get_by_label("Mobile App Field").get_by_role("combobox", name=name).inner_text(timeout=2000)
                data[name] = "" if value in ["Select an Option", "--None--"] else value
            except PlaywrightTimeoutError:
                logger.warning(f"Timeout extracting dropdown: {name}")
                data[name] = ""
        
        logger.info("Successfully extracted all fields.")
        return data

    except Exception as e:
        logger.error(f"Critical error during field extraction: {e}", exc_info=True)
        return None

async def fill_blank_fields(page, blank_keys, source_data):
    """Fills only the blank fields on the Salesforce page using extracted data."""
    logger.info(f"Filling {len(blank_keys)} blank fields.")
    
    try:
        for field in blank_keys:
            # Get value from converted extracted data
            value = source_data.get(field)
            
            if value is None or str(value).strip() == "":
                logger.warning(f"No source data found for blank field: {field}")
                continue
            
            logger.info(f"Filling '{field}' with value: {value}")
            
            try:
                # Attempt to fill as an input field first
                await page.get_by_label("Mobile App Field").get_by_label(field).fill(str(value), timeout=3000)
                await page.wait_for_timeout(300)
            except PlaywrightTimeoutError:
                # If it fails, try to select as a dropdown
                try:
                    await page.get_by_label("Mobile App Field").get_by_role("combobox", name=field).click()
                    await page.wait_for_timeout(300)
                    await page.get_by_role("option", name=str(value), exact=True).click()
                    await page.wait_for_timeout(300)
                except Exception as e:
                    logger.error(f"Could not fill '{field}' as input or dropdown: {e}")
        
        # Save the form
        await page.get_by_label("Mobile App Field").get_by_role("button", name="Save").click()
        await page.wait_for_timeout(2000)
        logger.info("Successfully filled and saved blank fields.")
        return True
        
    except Exception as e:
        logger.error(f"Failed to fill blank fields: {e}", exc_info=True)
        return False

# --- AI and Utility Functions ---
async def correct_data_with_ai(data_dict):
    """Uses OpenAI to correct grammar and spelling in the data."""
    if not data_dict: 
        return {}
        
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, api_key=os.getenv("OPENAI_API_KEY"))
    prompt = f"""
    You are a grammar and spelling correction assistant.

    The following is a JSON object where each value represents user-entered text:
    {json.dumps(data_dict, ensure_ascii=False, indent=2)}

    Instructions:
    - Correct any spelling or grammatical errors in the values.
    - Do not modify values for the following fields: 'Pincode','State','Condition of Approach Road','Unit for Dimension (Actual)','Type of Property As per Site','Structure of Construction', 'Stage of Construction', and 'Plot Demarcted at Site'.
    - Capitalize the first letter of each word in the value, if not already capitalized.
    - Preserve the original keys and structure.
    - Return a valid JSON object only—no code blocks or additional text.
    """

    try:
        response = await llm.ainvoke(prompt)
        content = response.content.strip()
        content = re.sub(r"``````", "", content)
        corrected_json = json.loads(content)
        logger.info("Successfully corrected data with AI")
        return corrected_json
    except Exception as e:
        logger.error(f"AI correction failed: {e}. Returning original data.")
        return data_dict

def find_blank_keys(data):
    """Finds keys with empty or None values in a dictionary."""
    if not data: 
        return []
    return [key for key, value in data.items() if str(value).strip() == ""]

async def filling_fields_after_correction(page, corrected_data, s3_manager, client_ref):
    """Fill fields after AI correction with confirmation dialog."""
    logger.info(f"Filling fields after AI correction")

    # Define field mapping for different field types
    field_mapping = {
        'inputs': [
            'Plot No/House No', 'Floor No.', 'Building/Wing Name', 'Street No./Road Name',
            'Scheme Name', 'Village/City', 'Nearby Landmark', 'Pincode', 'District',
            'Person Met At Site', 'If rented, Name and No of Occupants', 'Approach /Width of Road to the property',
            'Electricty Meter No', 'Electricity Bill No', 'Lift availability',
            'Structure Type','No of houses in village (Rural cases)','Age of Property (years)',
            'East - As Per Actual(Boundary)', 'West - As Per Actual(Boundary)',
            'North - As Per Actual(Boundary)', 'South - As Per Actual(Boundary)',
            'East - As Per Actual(Dimension)', 'West - As Per Actual(Dimension)',
            'North - As Per Actual(Dimension)', 'South - As Per Actual(Dimension)',
            'Setbacks As per Actual-Front', 'Setbacks As per Actual-Back',
            'Setbacks As per Actual-Side 1', 'Setbacks As per Actual-Side 2',
            'Identifier Document', 'Local Dealer Name', 'Local Dealer Contact',
            'Min Rate local dealer', 'Max rate local dealer',
            'Min Rate Technical', 'Max Rate Technical', 'Valuation Remark'
        ],
        'dropdowns': [
            'State', 'Occupancy Status', 'Condition of Approach Road', 'Property Type',
            'Electricity Meter Status','Elec. Meter No. Matching with Elec. Bill', 'Water Connection Status',
            'Gas Line Connection', 'Sewer Connection', 'Other Connection Remark',
            'Nature of Construction','Flooring', 'Type of Roof',
            'Quality of Construction','Marketability','Stage of Construction',
            "Development in the scheme (in %)","Is Property Identified ?",
            'Plot Demarcted at Site'
        ],
        'special': [
            'Name of Property Owner'
        ]
    }

    try:
        # Fill all fields
        for field, value in corrected_data.items():
            try:
                # Input fields
                if field in field_mapping['inputs']:
                    await page.get_by_label("Mobile App Field").get_by_label(field).wait_for(timeout=3000)
                    await page.get_by_label("Mobile App Field").get_by_label(field).fill(str(value))
                    await page.wait_for_timeout(300)

                # Dropdown fields
                elif field in field_mapping['dropdowns']:
                    await page.get_by_label("Mobile App Field").get_by_role("combobox", name=field).click()
                    await page.wait_for_timeout(300)
                    await page.get_by_label("Mobile App Field").get_by_role("option", name=str(value), exact=True).click()
                    await page.wait_for_timeout(300)

                # Special fields
                elif field in field_mapping['special']:
                    if field == 'Name of Property Owner':
                        await page.get_by_label('Name of Property Owner').fill(str(value))
                        await page.wait_for_timeout(300)

                logger.info(f"Successfully filled '{field}'")
                await page.get_by_label("Mobile App Field").get_by_role("button", name="Save").click()
                await page.wait_for_timeout(500)
                return True

            except Exception as e:
                logger.error(f"Error filling field '{field}': {e}")
                await take_screenshot_and_upload(page, s3_manager, client_ref)
                continue


    except Exception as e:
        logger.error(f"Failed to fill fields after correction: {e}", exc_info=True)
        await take_screenshot_and_upload(page, s3_manager, client_ref)
        return False

# --- Main Workflow ---
async def mobileapp_main(page, json_handler, s3_manager):
    """The main automation workflow with unified S3 integration."""
    logger.info("--- Starting Mobile App Automation Workflow ---")
    
    # Initialize S3DataManager with the existing UnifiedS3Manager
    s3_data_manager = S3DataManager(s3_manager)
    
    # Extract case number from json_handler
    case_number = getattr(json_handler, 'case_number', 'UNKNOWN')

    try:
        # **FIXED: Load extracted data using s3_manager directly (same as Drafter Field)**
        logger.info("🔍 Attempting to load extracted data from S3...")
        combined_data = get_combined_analysis_data(json_handler, s3_manager)
        
        if combined_data and (combined_data.get('image_analysis') or combined_data.get('document_analysis')):
            logger.info("✅ Using combined AI analysis data (image + document) for mobile app automation")
            # Convert combined data to mobile app format
            source_data = convert_combined_to_mobile_format(combined_data)
            logger.info(f"✅ Converted combined analysis data to mobile format with {len(source_data)} fields")
        else:
            logger.warning("⚠️ No combined analysis data found, trying individual data sources")

        # extracted_data = get_extracted_data(json_handler, s3_manager)
        
        # if extracted_data:
        #     logger.info("✅ Using AI extracted data from S3 for mobile app automation")
        #     # Convert extracted data to mobile app format
        #     source_data = convert_combined_to_mobile_format(extracted_data)
        #     logger.info(f"✅ Converted extracted data to mobile format with {len(source_data)} fields")
        # else:
        #     logger.warning("⚠️ No extracted data found, using default template")
        #     # Use default template instead of trying to load non-existent JSON
        #     source_data = get_default_mobile_template()

        # Upload input data to S3
        s3_data_manager.upload(source_data, "json_data/mobile_indus_input_data.json")

        # Extract existing data from Salesforce
        logger.info("Extracting current field values from Salesforce")
        extracted_fields = await checking_fields_filled_ornot(page)
        if extracted_fields is None:
            raise Exception("Field extraction failed, aborting workflow.")
        
        # Upload extracted data to S3
        s3_data_manager.upload(extracted_fields, "json_data/mobile_indus_extracted_fields_initial.json")

        # Check for blank fields and decide the path
        blank_keys = find_blank_keys(extracted_fields)
        logger.info(f"Found {len(blank_keys)} blank fields: {blank_keys}")
        
        # Upload analysis report to S3
        s3_data_manager.upload({
            "blank_keys_found": blank_keys,
            "total_fields": len(extracted_fields),
            "blank_count": len(blank_keys),
            "completion_percentage": ((len(extracted_fields) - len(blank_keys)) / len(extracted_fields)) * 100,
            "combined_data_available": combined_data is not None,
            "source_data_fields": len(source_data),
            "data_sources_used": {
                "image_analysis": combined_data.get('image_analysis') is not None if combined_data else False,
                "document_analysis": combined_data.get('document_analysis') is not None if combined_data else False
            }
        }, "json_data/mobile_indus_analysis_report.json")

        if not blank_keys:
            logger.info("No blank fields found. Proceeding with grammar correction.")
            corrected_data = await correct_data_with_ai(extracted_fields)
            s3_data_manager.upload(corrected_data, "json_data/final_corrected_data.json")
            success = await filling_fields_after_correction(page, corrected_data, s3_data_manager, case_number)
            if success:
                logger.info("Fields filled successfully.")
            logger.info("All fields are filled and corrected. Process completed successfully.")

        else:
            logger.info(f"Found {len(blank_keys)} blank fields. Attempting to fill them.")
            success = await fill_blank_fields(page, blank_keys, source_data)
            if success:
                logger.info("Fields filled. Re-extracting and correcting final data.")
                final_data = await checking_fields_filled_ornot(page)
                corrected_final_data = await correct_data_with_ai(final_data)
                s3_data_manager.upload(corrected_final_data, "json_data/final_corrected_data.json")
                success = await filling_fields_after_correction(page, corrected_final_data, s3_data_manager, case_number)
                if success:
                    logger.info("Fields filled successfully.")
                logger.info("All fields are filled and corrected. Process completed successfully.")
            else:
                raise Exception("Failed to fill blank fields.")

        # Upload completion status
        s3_data_manager.upload({
            "status": "completed",
            "timestamp": datetime.now().isoformat(),
            "case_number": case_number,
            "fields_processed": len(extracted_fields),
            "blank_fields_filled": len(blank_keys) if blank_keys else 0,
            "combined_data_used": combined_data is not None,
            "data_sources": {
                "image_analysis": combined_data.get('image_analysis') is not None if combined_data else False,
                "document_analysis": combined_data.get('document_analysis') is not None if combined_data else False
            }
        }, "json_data/mobile_indus_completion_status.json")

        return True

    except Exception as e:
        logger.error(f"MOBILE INDUSIND WORKFLOW FAILED for case {case_number}: {e}", exc_info=True)
        await take_screenshot_and_upload(page, s3_data_manager, case_number)
        
        # Upload error report
        s3_data_manager.upload({
            "status": "failed",
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
            "case_number": case_number
        }, "json_data/mobile_indus_error_report.json")
        
        return False
        
    finally:
        logger.info("--- Mobile App Automation Workflow Completed ---")

# Entry point for testing
if __name__ == "__main__":
    print("mobileapp_indus.py - Mobile App Automation Module")
    print("This module uses S3 extracted analysis data with fallback to default template")