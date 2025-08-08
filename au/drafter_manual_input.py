import asyncio
from datetime import datetime
from playwright.async_api import Page
from typing import Dict, List, Any
from static.unified_s3_manager import UnifiedS3Manager
from static.unified_logger import UnifiedLogger
import json

class DrafterManualInputAssistant:
    """
    Handles manual input for missing drafter fields after AI processing
    """

    def __init__(self, s3_manager: UnifiedS3Manager):
        self.s3_manager = s3_manager
        self.logger = UnifiedLogger(s3_manager, "drafter_manual_input")
        self.empty_fields = []
        self.field_metadata = {}

    def get_all_drafter_fields(self) -> Dict[str, Dict[str, Any]]:
        """
        Define all drafter fields with their metadata
        Returns: Dict with field_key -> {label, type, required, category}
        """
        return {
            # General Information
            'Document Provided for Valuation': {
                'label': 'Document Provided for Valuation',
                'type': 'text',
                'required': True,
                'category': 'General'
            },
            'Property situated': {
                'label': 'Property situated',
                'type': 'dropdown',
                'required': True,
                'category': 'General',
                'options':['Metro', 'Urban', 'Semi Urban or Rural (G P Limit)', 'City Limit', 'Development Authority Limit', 'MC Limit', 'GP Limit', 'Nagar Panchayat Limit','Nagar Palika/Parishad/Nigam Limit','Outside MC Limits','Lal dora','Rural']
            },
            'Type of Property As per document': {
                'label': 'Type of Property As per document',
                'type': 'dropdown',
                'required': True,
                'category': 'General',
                'options':['Residential', 'Commercial', 'Non Converted', 'Industrial', 'Mix Uses']
            },
            'Status of holding': {
                'label': 'Status of holding',
                'type': 'dropdown',
                'required': True,
                'category': 'General',
                'options': ['Free Hold', 'Lease Hold']
            },
            'Doc address match as per actual address': {
                'label': 'Doc address match as per actual address',
                'type': 'dropdown',
                'required': False,
                'category': 'Property Condition',
                'options': ['Yes', 'No']
            },
            'Flats(on each floor)': {
                'label': 'Flats(on each floor)',
                'type': 'text',
                'required': True,
                'category': 'Property Condition'
            },
            'Class of Locality': {
                'label': 'Class of Locality',
                'type': 'dropdown',
                'required': True,
                'category': 'Property Condition',
                'options': ['High', 'Middle', 'Low', 'Urban','Mixed', 'Rural', 'Semi Urban','Residential', 'Commercial', 'Industrial','Agriculture & Mixed']
            },
            'Property usage': {
                'label': 'Property usage',
                'type': 'dropdown',
                'required': False,
                'category': 'Property Condition',
                'options': ['Commercial office', 'Commercial shop','Complete Commercial', 'Vacant land', 'Residential', 'Industrial', 'Mix Uses','Non Converted','Plot','Under Construction','Other']
            },
            'Occupancy percent': {
                'label': 'Occupancy percent',
                'type': 'text',
                'required': False,
                'category': 'Property Condition'
            },
            'Residual age of Property (years)': {
                'label': 'Residual age of Property (years)',
                'type': 'text',
                'required': False,
                'category': 'Property Condition'
            },
            'Request From/Allocated By': {
                'label': 'Request From/Allocated By',
                'type': 'text',
                'required': False,
                'category': 'Property Condition'
            },
            #Documented Address
            'Plot No/House No': {
                'label': 'Plot No/House No',
                'type': 'text',
                'required': False,
                'category': 'Documented Address'
            },
          
            'Floor No.': {
                'label': 'Floor No.',
                'type': 'text',
                'required': False,
                'category': 'Documented Address'
            },
            'Building/Wing Name': {
                'label': 'Building/Wing Name',
                'type': 'text',
                'required': False,
                'category': 'Documented Address'
            },
            'Street No./Road Name': {
                'label': 'Street No./Road Name',
                'type': 'text',
                'required': False,
                'category': 'Documented Address'
            },
            'Scheme Name': {
                'label': 'Scheme Name',
                'type': 'text',
                'required': False,
                'category': 'Documented Address'
            },
            'Village/City': {
                'label': 'Village/City',
                'type': 'text',
                'required': False,
                'category': 'Documented Address'
            },
            'Pincode': {
                'label': 'Pincode',
                'type': 'text',
                'required': False,
                'category': 'Documented Address'
            },
            'Locality': {
                'label': 'Locality',
                'type': 'text',
                'required': False,
                'category': 'Documented Address'
            },
            'Address as per Identifier Docs': {
                'label': 'Address as per Identifier Docs',
                'type': 'text',
                'required': False,
                'category': 'Documented Address'
            },
            #Locality Information
            'Class of Locality': {
                'label': 'Class of Locality',
                'type': 'dropdown',
                'required': True,
                'category': 'Locality Information',
                'options': ['High', 'Middle', 'Low', 'Urban','Mixed', 'Rural', 'Semi Urban','Residential', 'Commercial', 'Industrial','Agriculture & Mixed']
            },
            'Property usage': {
                'label': 'Property usage',
                'type': 'dropdown',
                'required': False,
                'category': 'Locality Information',
                'options': ['Commercial office', 'Commercial shop','Complete Commercial', 'Vacant land', 'Residential', 'Industrial', 'Mix Uses','Non Converted','Plot','Under Construction','Other']
            },
            'Any Negative Locality': {
                'label': 'Any Negative Locality',
                'type': 'dropdown',
                'required': True,
                'category': 'Locality Information',
                'options': ['Crematoriums','Slums', 'gases', 'Mining site','riot prone' , 'High Tension Lines' , 'chemical hazards' 'Waste Dump Site' , 'No']
            },
            'Location- As per DLC Portal': {
                'label': 'Location- As per DLC Portal',
                'type': 'text',
                'required': False,
                'category': 'Locality Information'
            },

            # Boundary Information
            'East - As Per Document(Boundary)': {
                'label': 'East - As Per Document(Boundary)',
                'type': 'text',
                'required': True,
                'category': 'Boundary'
            },
            'West - As Per Document(Boundary)': {
                'label': 'West - As Per Document(Boundary)',
                'type': 'text',
                'required': True,
                'category': 'Boundary'
            },
            'North - As per Document(Boundary)': {
                'label': 'North - As per Document(Boundary)',
                'type': 'text',
                'required': True,
                'category': 'Boundary'
            },
            'south - As per Document(Boundary)': {
                'label': 'south - As per Document(Boundary)',
                'type': 'text',
                'required': True,
                'category': 'Boundary'
            },
            'Basic amenities available? (Water, Road)': {
                'label': 'Basic amenities available? (Water, Road)',
                'type': 'dropdown',
                'required': True,
                'category': 'Boundary',
                'options': ['Yes', 'No']
            },
            'Maintenance Levels': {
                'label': 'Maintenance Levels',
                'type': 'text',
                'required': False,
                'category': 'Boundary'
            },
            'Deviation For AU-Remark': {
                'label': 'Deviation For AU-Remark',
                'type': 'text',
                'required': False,
                'category': 'Boundary'
            },

            # Dimension Information
            'Unit for Dimension (Doc)': {
                'label': 'Unit for Dimension (Doc)',
                'type': 'dropdown',
                'required': True,
                'category': 'Dimension',
                'options': ['ft', 'mt']
            },
            'East - As per Docs(Dimension)': {
                'label': 'East - As per Docs(Dimension)',
                'type': 'text',
                'required': True,
                'category': 'Dimension'
            },
            'West - As per Docs(Dimension)': {
                'label': 'West - As per Docs(Dimension)',
                'type': 'text',
                'required': True,
                'category': 'Dimension'
            },
            'North - As per Docs(Dimension)': {
                'label': 'North - As per Docs(Dimension)',
                'type': 'text',
                'required': True,
                'category': 'Dimension'
            },
            'South - As per Docs(Dimension)': {
                'label': 'South - As per Docs(Dimension)',
                'type': 'text',
                'required': True,
                'category': 'Dimension'
            },

            'Setbacks As per Rule-Front': {
                'label': 'Setbacks As per Rule-Front',
                'type': 'text',
                'required': True,
                'category': 'Dimension'
            },
            'Setbacks As per Rule-Back': {
                'label': 'Setbacks As per Rule-Back',
                'type': 'text',
                'required': True,
                'category': 'Dimension'
            },
            'Setbacks As per Rule-Side 1': {
                'label': 'Setbacks As per Rule-Side 1',
                'type': 'text',
                'required': True,
                'category': 'Dimension'
            },
            'Setbacks As per Rule-Side 2': {
                'label': 'Setbacks As per Rule-Side 2',
                'type': 'text',
                'required': True,
                'category': 'Dimension'
            }
        }

    def validate_and_transform_empty_fields(self, empty_fields: List) -> List[Dict[str, Any]]:
        """
        Validate and transform empty_fields into the correct format (list of dictionaries).
        If empty_fields contains strings, map them to their metadata from get_all_drafter_fields.
        """
        all_fields = self.get_all_drafter_fields()
        validated_fields = []

        for field in empty_fields:
            if isinstance(field, str):
                # If field is a string (field_key), map it to its metadata
                if field in all_fields:
                    validated_fields.append({
                        'key': field,
                        'label': all_fields[field]['label'],
                        'type': all_fields[field]['type'],
                        'required': all_fields[field]['required'],
                        'category': all_fields[field]['category'],
                        'options': all_fields[field].get('options', [])
                    })
                else:
                    self.logger.warning(f"Unknown field key: {field}")
            elif isinstance(field, dict) and all(key in field for key in ['key', 'label', 'type', 'required', 'category']):
                # If field is already a dictionary with required keys, use it as is
                validated_fields.append(field)
            else:
                self.logger.warning(f"Invalid field format: {field}")

        return validated_fields

    def categorize_empty_fields(self, empty_fields: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Categorize empty fields by type and priority
        """
        categories = {
            'Required': [],
            'Optional': [],
            'By_Category': {}
        }

        for field in empty_fields:
            # Ensure field is a dictionary
            if not isinstance(field, dict):
                self.logger.error(f"Invalid field format in categorize_empty_fields: {field}")
                continue

            # Separate by requirement
            if field['required']:
                categories['Required'].append(field)
            else:
                categories['Optional'].append(field)

            # Group by category
            category = field['category']
            if category not in categories['By_Category']:
                categories['By_Category'][category] = []
            categories['By_Category'][category].append(field)

        return categories


    async def fill_manual_inputs(self, page: Page, manual_inputs: Dict[str, str]) -> bool:
        """Fill the manually entered inputs into the form"""

        try:
            all_fields = self.get_all_drafter_fields()
            success_count = 0

            for field_key, value in manual_inputs.items():
                if field_key in all_fields:
                    field_info = all_fields[field_key]
                    label = field_info['label']
                    field_type = field_info['type']

                    try:
                        if field_type == 'dropdown':
                            # Fill dropdown
                            await page.get_by_role("combobox", name=label).click()
                            await page.wait_for_timeout(300)
                            await page.get_by_role("option", name=value).click()
                        else:
                            # Fill text field
                            await page.get_by_label(label).fill(str(value))
                            await page.wait_for_timeout(300)

                        success_count += 1
                        self.logger.info(f"✅ Filled manual input: {label} = {value}")

                    except Exception as e:
                        self.logger.error(f"❌ Failed to fill manual input {label}: {e}")

            self.logger.info(f"Successfully filled {success_count}/{len(manual_inputs)} manual inputs")
            await page.get_by_role("button", name="Save").click()
            await page.wait_for_timeout(2000)

            return success_count > 0


        except Exception as e:
            self.logger.error(f"Error filling manual inputs: {e}")
            return False

    async def save_manual_input_report(self, case_number: str, empty_fields: List[Dict[str, Any]], manual_inputs: Dict[str, str]):
        """Save a report of the manual input process"""
        try:
            # Validate and transform empty_fields
            validated_fields = self.validate_and_transform_empty_fields(empty_fields)

            report = {
                "case_number": case_number,
                "timestamp": datetime.now().isoformat(),
                "empty_fields_count": len(validated_fields),
                "manual_inputs_count": len(manual_inputs),
                "empty_fields": validated_fields,
                "manual_inputs": manual_inputs,
                "categorized_summary": self.categorize_empty_fields(validated_fields)
            }

            filename = f"drafter_manual_input_report_{case_number}.json"
            self.s3_manager.upload_file(report, 'json_data', filename)

            self.logger.info(f"Manual input report saved: {filename}")

        except Exception as e:
            self.logger.error(f"Error saving manual input report: {e}")