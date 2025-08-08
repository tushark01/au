import logging
import os
import json
import base64
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from dotenv import load_dotenv
from dlc_src.rate_ex import extract_with_alternative_prompt, enhanced_extract_dlc_rate_with_fallback, clean_and_validate_rate, smart_extract_dlc_rate_with_openai, extract_dlc_rate_from_page_smart
from dlc_src.captcha_utils import solve_captcha_process
import boto3
from io import BytesIO

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

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

if not OPENAI_API_KEY:
    logger.error("OPENAI_API_KEY not found in environment variables. Please set it in your .env file.")

# S3 Upload Helper (from in-memory bytes)
def upload_bytes_to_s3(byte_data, s3_key):
    """Upload byte data to S3 bucket"""
    try:
        s3 = boto3.client(
            "s3",
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            region_name=os.getenv("AWS_REGION"),
        )
        bucket = os.getenv("S3_BUCKET")
        s3.upload_fileobj(BytesIO(byte_data), bucket, s3_key)
        logger.info(f"Uploaded to S3: s3://{bucket}/{s3_key}")
        return f"s3://{bucket}/{s3_key}"
    except Exception as e:
        logger.error(f"Error uploading to S3: {e}")
        return None

def take_full_page_screenshot(page, json_handler, filename_prefix='dlc_final'):
    """Saves a full-page screenshot to S3 instead of local storage."""
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        client_ref = json_handler.get_client_reference()
        s3_key = f"screenshots/{client_ref}/{filename_prefix}_screenshot_{timestamp}.png"
        
        # Capture screenshot as bytes
        byte_data = page.screenshot(full_page=True)
        
        # Upload to S3
        s3_url = upload_bytes_to_s3(byte_data, s3_key)
        if s3_url:
            logger.info(f"Full-page screenshot uploaded to S3: {s3_url}")
        else:
            logger.error("Failed to upload full-page screenshot to S3")
        
        return s3_url
    except Exception as e:
        logger.error(f"Failed to capture/upload full-page screenshot: {str(e)}")
        return None

def take_screenshot(page, json_handler, full_page=False):
    """Captures and uploads screenshot to S3 for error reporting."""
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        client_ref = json_handler.get_client_reference()
        s3_key = f"screenshots/{client_ref}/dlc_error_screenshot_{timestamp}.png"
        
        # Capture screenshot as bytes
        byte_data = page.screenshot(full_page=full_page)
        
        # Upload to S3
        s3_url = upload_bytes_to_s3(byte_data, s3_key)
        if s3_url:
            logger.info(f"Error screenshot uploaded to S3: {s3_url}")
        else:
            logger.error("Failed to upload error screenshot to S3")
        
        return s3_url
    except Exception as e:
        logger.error(f"Failed to capture/upload screenshot: {e}")
        return None

def extract_dlc_rate_from_page(page, classification, json_handler):
    try:
        # Normalize classification for comparison
        classification = classification.strip().lower()
        logger.info(f"Trying to extract DLC rate for classification: '{classification}'")

        # Use a robust selector to find the results table by its unique header text
        results_table_selector = "table:has-text('Plot Wise Rate')"
        table = page.locator(results_table_selector)

        # Fallback if the primary selector fails
        if not table.is_visible():
            logger.warning(f"Results table not found with selector '{results_table_selector}'. Trying fallback: last table on page.")
            all_tables = page.locator("table")
            if all_tables.count() > 0:
                table = all_tables.last
            else:
                logger.error("No tables found on the page.")
                take_screenshot(page, json_handler)
                return None

        rows = table.locator("tr")
        logger.info(f"Located results table with {rows.count()} rows.")

        # Start from 1 to skip the header row
        for i in range(1, rows.count()):
            row = rows.nth(i)
            columns = row.locator("td")

            # A valid data row should have enough columns
            if columns.count() < 5:
                continue

            # Column indices based on the screenshot: 3 = 'Type Of Land', 4 = 'Exterior' rate
            row_classification = columns.nth(3).inner_text().strip().lower()
            exterior_rate = columns.nth(4).inner_text().strip()

            # If no classification is specified, return the rate from the first valid data row
            if not classification:
                logger.info(f"No classification specified. Extracted rate from first data row: {exterior_rate}")
                return exterior_rate

            # If a specific classification is provided, find the matching row
            if classification in row_classification:
                logger.info(f"Found matching classification '{classification}'. Extracted Exterior Rate: {exterior_rate}")
                return exterior_rate

        logger.warning(f"No matching data row found for classification '{classification}' in the results table.")
        take_screenshot(page, json_handler)
        return None

    except Exception as e:
        logger.error(f"An unexpected error occurred during DLC rate extraction: {e}")
        take_screenshot(page, json_handler)
        return None

def select_from_dropdown_targeted(page, dropdown_name, option_value, json_handler):
    if not option_value:
        logger.warning(f"No {dropdown_name} value provided, skipping selection")
        return False

    logger.info(f"Selecting {dropdown_name}: {option_value}")

    try:
        page.wait_for_timeout(3000)

        dropdown_found = False

        def get_container(tag):
            return page.locator(f"tr:has-text('{tag}'), td:has-text('{tag}'), div:has-text('{tag}')")

        def handle_dropdown(container):
            nonlocal dropdown_found
            dropdown = container.locator(".chosen-container .chosen-single")
            if dropdown.count() > 0 and dropdown.first.is_visible():
                dropdown_found = True
                dropdown.first.click()
                page.wait_for_timeout(1000)

                search_inputs = container.locator(".chosen-search input[type='text']")
                if search_inputs.count() != 1:
                    logger.warning(f"Expected one search input for {dropdown_name}, found {search_inputs.count()}. Skipping...")
                    page.keyboard.press("Escape")
                    return False

                search_input = search_inputs.nth(0)
                if search_input.is_visible():
                    search_input.fill("")
                    search_input.type(option_value, delay=100)
                    logger.info(f"Typed '{option_value}' into {dropdown_name} search")
                    page.wait_for_timeout(3000)

                    if select_option_from_results(page, option_value, dropdown_name):
                        return True

                page.keyboard.press("Escape")
            return False

        # --- SRO Dropdown ---
        if dropdown_name.lower() == "sro":
            logger.info("Looking for SRO dropdown specifically...")
            sro_containers = get_container("SRO")
            for i in range(sro_containers.count()):
                container = sro_containers.nth(i)
                if handle_dropdown(container):
                    return True

        # --- Village Dropdown ---
        elif dropdown_name.lower() == "village":
            logger.info("Looking for Village dropdown specifically...")
            village_containers = get_container("Village")
            for i in range(village_containers.count()):
                container = village_containers.nth(i)
                if handle_dropdown(container):
                    return True

            # Fallback: Try 2nd dropdown if specific container not found
            if not dropdown_found:
                logger.info("No Village container found, trying fallback to second dropdown...")
                all_dropdowns = page.locator(".chosen-container .chosen-single")
                if all_dropdowns.count() >= 2:
                    village_dropdown = all_dropdowns.nth(1)
                    village_dropdown.click()
                    page.wait_for_timeout(1000)

                    search_input = page.locator(".chosen-search input[type='text']").first
                    if search_input.is_visible():
                        search_input.fill("")
                        search_input.type(option_value, delay=100)
                        page.wait_for_timeout(3000)
                        if select_option_from_results(page, option_value, dropdown_name):
                            return True
                    page.keyboard.press("Escape")

        # --- Colony Dropdown ---
        elif dropdown_name.lower() == "colony":
            logger.info("Looking for Colony dropdown specifically...")
            colony_containers = get_container("Colony")
            for i in range(colony_containers.count()):
                container = colony_containers.nth(i)
                if handle_dropdown(container):
                    return True

            # Fallback: Try 3rd dropdown if specific container not found
            if not dropdown_found:
                logger.info("No Colony container found, trying fallback to third dropdown...")
                all_dropdowns = page.locator(".chosen-container .chosen-single")
                if all_dropdowns.count() >= 3:
                    colony_dropdown = all_dropdowns.nth(2)
                    colony_dropdown.click()
                    page.wait_for_timeout(1000)

                    search_input = page.locator(".chosen-search input[type='text']").first
                    if search_input.is_visible():
                        search_input.fill("")
                        search_input.type(option_value, delay=100)
                        page.wait_for_timeout(3000)
                        if select_option_from_results(page, option_value, dropdown_name):
                            return True
                    page.keyboard.press("Escape")

        # Fallback: Select "All" for village if specific one isn't found
        if dropdown_name.lower() == "village":
            logger.warning(f"Village '{option_value}' not found. Trying fallback 'All'")
            return select_all_fallback(page, "village")

        logger.error(f"All strategies failed for selecting {dropdown_name}: {option_value}")
        return False

    except Exception as e:
        logger.error(f"Fatal error during selection of {dropdown_name}: {e}")
        take_screenshot(page, json_handler)
        return False

def select_option_from_results(page, option_value, dropdown_name):
    """Helper function to select option from dropdown results"""
    try:
        # Look for options in results
        option_selectors = [
            ".chosen-results li",
            ".chosen-drop li",
            ".dropdown-menu li"
        ]
        
        for option_selector in option_selectors:
            all_options = page.locator(option_selector)
            options_count = all_options.count()
            
            if options_count > 0:
                logger.info(f"Found {options_count} options for {dropdown_name}")
                
                # Try exact match first
                for j in range(options_count):
                    option = all_options.nth(j)
                    try:
                        option_text = option.inner_text().strip()
                        if option_text.upper() == option_value.upper():
                            option.click()
                            logger.info(f"Selected exact match for {dropdown_name}: {option_text}")
                            page.wait_for_timeout(2000)
                            return True
                    except:
                        continue
                
                # Try partial match
                for j in range(options_count):
                    option = all_options.nth(j)
                    try:
                        option_text = option.inner_text().strip()
                        if option_value.upper() in option_text.upper():
                            option.click()
                            logger.info(f"Selected partial match for {dropdown_name}: {option_text}")
                            page.wait_for_timeout(2000)
                            return True
                    except:
                        continue
                break
        
        return False
        
    except Exception as e:
        logger.error(f"Error selecting option from results: {e}")
        return False

def select_all_fallback(page, dropdown_name):
    """Fallback to select 'All' option when specific option not found"""
    try:
        # Find the appropriate dropdown and select 'All'
        if dropdown_name.lower() == "village":
            all_dropdowns = page.locator(".chosen-container .chosen-single")
            
            # Try the second dropdown (Village dropdown)
            if all_dropdowns.count() >= 2:
                village_dropdown = all_dropdowns.nth(1)
                
                if village_dropdown.is_visible():
                    village_dropdown.click()
                    page.wait_for_timeout(1000)
                    
                    all_option = page.locator(".chosen-results li:has-text('All')")
                    if all_option.count() > 0:
                        all_option.first.click()
                        logger.info("Selected 'All' for Village")
                        page.wait_for_timeout(2000)
                        return True
                    
                    # Close dropdown
                    page.keyboard.press("Escape")
        
        return False
        
    except Exception as e:
        logger.error(f"Could not select 'All' for {dropdown_name}: {e}")
        return False

def find_dlc_rate(data, json_handler):
    logger.info("Starting DLC Rate finding process with CAPTCHA solving")
    script_dir = os.path.dirname(os.path.abspath(__name__))
    classification = data.get("propertyAreaAndValuation", {}).get("classificationOfLand", "").strip().lower()

    # Updated to use technical_field instead of technicalInfo
    technical_field = data.get("technical_field", {})
    
    # Extract data from the technical_field section
    district_name = technical_field.get("district")
    typeoflocation = technical_field.get("typeoflocation")
    sro_name = technical_field.get("sro")
    village_name = technical_field.get("Village")
    colony_name = technical_field.get("Colony")

    # Log the extracted data for debugging
    logger.info(f"Extracted data from technical_field:")
    logger.info(f"  District: {district_name}")
    logger.info(f"  Type of location: {typeoflocation}")
    logger.info(f"  SRO: {sro_name}")
    logger.info(f"  Village: {village_name}")
    logger.info(f"  Colony: {colony_name}")

    if not district_name:
        logger.error("Could not find 'district' in the 'technical_field' section of the provided JSON data. Please check 'demo.json'.")
        return False
    if not typeoflocation:
        logger.warning("Could not find 'typeoflocation' in the 'technical_field' section of the provided JSON data. Area type selection will be skipped.")

    dlc_district_url = "https://epanjiyan.rajasthan.gov.in/dlcdistrict.aspx"
    find_dlc_rate_url = "https://epanjiyan.rajasthan.gov.in/FindDlcRate.aspx"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-notifications"])
        context = browser.new_context()
        page = context.new_page()

        try:
            logger.info(f"Navigating to DLC District selection page: {dlc_district_url}")
            page.goto(dlc_district_url, wait_until="load")

            # --- District Selection with Enhanced Dropdown ---
            search_input_selector = ".chosen-container input[type='text']"
            enhanced_dropdown_selector = ".chosen-container .chosen-single"
            option_selector = lambda district: f".chosen-results li:has-text('{district}')"

            page.wait_for_selector(enhanced_dropdown_selector, state="visible", timeout=30000)
            logger.info("Enhanced dropdown anchor is visible.")
            page.click(enhanced_dropdown_selector)
            logger.info("Clicked the enhanced dropdown anchor to open options.")

            page.wait_for_selector(search_input_selector, state="visible", timeout=10000)
            logger.info("Search input within dropdown is visible.")

            logger.info(f"Typing District: '{district_name}' into the search box.")
            page.locator(search_input_selector).type(district_name)
            logger.info(f"Typed '{district_name}'.")

            page.wait_for_selector(option_selector(district_name), state="visible", timeout=10000)
            logger.info(f"Specific district option '{district_name}' is visible.")
            page.click(option_selector(district_name))
            logger.info(f"Clicked the district option '{district_name}'.")

            # --- Clicking the Submit Button ---
            submit_button_locator = page.locator("input[value='Submit']")
            if not submit_button_locator.count():
                submit_button_locator = page.get_by_role("button", name="Submit")

            submit_button_locator.wait_for(state="visible", timeout=10000)
            logger.info("Submit button is visible.")
            
            logger.info("Clicking Submit button and waiting for navigation to FindDlcRate.aspx...")
            submit_button_locator.click()
            page.wait_for_url(find_dlc_rate_url, timeout=30000)
            logger.info(f"Successfully navigated to {find_dlc_rate_url}")

            # --- On the FindDlcRate.aspx page ---
            page.wait_for_load_state("networkidle", timeout=30000)
            logger.info("Page load completed.")

            # --- Area Type Selection (Urban/Rural) ---
            logger.info("Searching for area type radio buttons...")
            
            try:
                page.wait_for_selector("input[type='radio']", timeout=10000)
                if typeoflocation:
                    logger.info(f"Selecting Area Type: {typeoflocation}")
                    all_radios = page.locator("input[type='radio']")
                    radio_count = all_radios.count()
                    logger.info(f"Found {radio_count} radio buttons")
                    
                    for i in range(radio_count):
                        radio = all_radios.nth(i)
                        try:
                            parent_text = radio.locator("..").inner_text().lower()
                            value = radio.get_attribute("value") or ""
                            all_context = f"{value} {parent_text}".lower()
                            
                            if (typeoflocation.lower() == "urban" and "urban" in all_context) or \
                               (typeoflocation.lower() == "rural" and "rural" in all_context):
                                radio.click()
                                logger.info(f"Clicked '{typeoflocation}' radio button")
                                page.wait_for_timeout(3000)
                                break
                        except Exception as e:
                            logger.warning(f"Error checking radio button {i}: {e}")
                            continue
            except Exception as e:
                logger.error(f"Error in area type selection: {e}")

            
            if typeoflocation and 'urban' in typeoflocation.lower():
                # --- URBAN PATH: Click Colony radio and select Colony ---
                logger.info("Urban location selected. Proceeding with Colony selection.")
                
                # --- Click Colony Radio Button ---
                logger.info("Looking for Colony radio button...")
                try:
                    page.wait_for_timeout(2000)
                    all_radios = page.locator("input[type='radio']")
                    
                    for i in range(all_radios.count()):
                        radio = all_radios.nth(i)
                        try:
                            parent_text = radio.locator("..").inner_text().lower()
                            if "colony" in parent_text:
                                radio.click()
                                logger.info("Clicked 'Colony' radio button")
                                page.wait_for_timeout(5000) # Wait for Colony dropdown to load
                                break
                        except:
                            continue
                except Exception as e:
                    logger.error(f"Error clicking Colony radio button: {e}")

                # --- Colony Selection ---
                if colony_name:
                    logger.info(f"Attempting to select Colony: {colony_name}")
                    select_from_dropdown_targeted(page, "Colony", colony_name, json_handler)

            else:
                # --- RURAL/DEFAULT PATH: Click SRO radio and select SRO/Village ---
                logger.info("Rural or unspecified location. Proceeding with SRO/Village selection.")

                # --- Click SRO Radio Button ---
                logger.info("Looking for SRO radio button...")
                try:
                    page.wait_for_timeout(2000)
                    all_radios = page.locator("input[type='radio']")
                    
                    for i in range(all_radios.count()):
                        radio = all_radios.nth(i)
                        try:
                            parent_text = radio.locator("..").inner_text().lower()
                            if "sro" in parent_text:
                                radio.click()
                                logger.info("Clicked 'SRO' radio button")
                                page.wait_for_timeout(5000)  # Wait longer for SRO dropdown
                                break
                        except:
                            continue
                            
                except Exception as e:
                    logger.error(f"Error clicking SRO radio button: {e}")

                # --- SRO Name Selection ---
                if sro_name:
                    logger.info(f"Attempting to select SRO: {sro_name}")
                    sro_success = select_from_dropdown_targeted(page, "SRO", sro_name, json_handler)
                    if sro_success:
                        logger.info("SRO selection successful, waiting for Village dropdown...")
                        page.wait_for_timeout(8000)  # Wait for Village dropdown to load

                # --- Village Name Selection ---
                if village_name:
                    logger.info(f"Attempting to select Village: {village_name}")
                    select_from_dropdown_targeted(page, "Village", village_name, json_handler)

            # --- CAPTCHA Solving ---
            if not solve_captcha_process(page, json_handler, OPENAI_API_KEY):
                logger.error("CAPTCHA solving process failed")
                return False

            # --- Wait for Results ---
            logger.info("Waiting for results to load...")
            page.wait_for_timeout(10000)

            logger.info("Taking final full-page screenshot of results...")
            take_full_page_screenshot(page, json_handler, 'dlc_final_results')
            
            page.wait_for_timeout(5000)

            dlc_value = extract_dlc_rate_from_page_smart(page, classification, json_handler)
            if dlc_value:
                json_handler.update_field("technical_field.DLC Rate", dlc_value)
                logger.info(f"Successfully extracted and inserted DLC Rate: '{dlc_value}'")
            else:
                logger.warning("DLC Rate could not be extracted from the page.")

            browser.close()
            
            return True

        except PlaywrightTimeoutError as te:
            logger.error(f"Timeout occurred during DLC process: {str(te)}")
            take_screenshot(page, json_handler)
            return False
        except Exception as e:
            logger.error(f"An error occurred during DLC process: {str(e)}")
            take_screenshot(page, json_handler)
            return False
        finally:
            logger.info("DLC process completed. Browser window remains open for review.")

# ---------- Main execution block ----------
if __name__ == "__main__":
    logger.info("Script execution started for DLC Rate finding with CAPTCHA solving.")
    try:
        from cua_poc1.static.json_utils import JSONHandler
        json_handler = JSONHandler("demo.json")
        data = json_handler.load_json()
        if not data:
            logger.error("Failed to load data from demo.json. Exiting.")
        else:
            success = find_dlc_rate(data, json_handler)
            if success:
                logger.info("DLC process executed successfully with CAPTCHA solved.")
            else:
                logger.error("DLC process encountered an error.")
    except Exception as e:
        logger.error(f"An unexpected error occurred in the main execution: {str(e)}")
    finally:
        logger.info("Script execution finished.")
