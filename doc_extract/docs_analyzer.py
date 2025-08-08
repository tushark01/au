import os
import json
import asyncio
import time
import pathlib
from typing import List, Dict, Optional
from pathlib import Path
import google.generativeai as genai
from tenacity import retry, stop_after_attempt, wait_exponential

class DocumentAnalyzer:
    """Enhanced document analyzer with rate limiting, Gemini integration, and multi-document processing"""

    def __init__(self):
        # Configure Gemini
        genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
        self.gemini_model = genai.GenerativeModel('gemini-2.5-flash')
        
        # Rate limiting
        self.last_gemini_call = 0
        self.gemini_delay = 2.0  # Minimum delay between calls

    def is_real_estate_document(self, document_path: str) -> bool:
        """All PDFs are treated as property documents"""
        return True

    def identify_document_type(self, document_path: str) -> str:
        """All documents are treated as property documents"""
        return "property_document"

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=4, max=20))
    async def analyze_real_estate_document_with_gemini(self, document_path: str) -> Dict:
        """Analyze property documents using Gemini 2.5 Flash with enhanced rate limiting"""
        try:
            # Enhanced rate limiting
            current_time = time.time()
            time_since_last_call = current_time - self.last_gemini_call
            min_delay = 3.0  # 3 seconds between calls
            
            if time_since_last_call < min_delay:
                await asyncio.sleep(min_delay - time_since_last_call)

            # Upload PDF file to Gemini
            uploaded_file = await asyncio.to_thread(genai.upload_file, document_path)

            # Enhanced property document analysis prompt
            prompt = """You are an AI-powered OCR post-processor for Hindi-language Indian real-estate documents. 
            Your job is to read the raw OCR text of a single property document and output exactly one clean JSON object 
            containing only the fields listed below, with no extra keys or surrounding text.

            IMPORTANT: Return ONLY a JSON with these exact keys and TRANSLATE ALL TEXT TO ENGLISH:
            {
            "Document_Type": "[only exact title like'Copy of Sale Deed' or 'Lease Agreement' or 'Site Plan']",
            "Owner_Name": "[full name as written like 'Mrs Geeta Devi' or 'Mr Bhopalram Boyal w/o Mrs Geeta Devi']",
            "Type_of_Property_As_per_document":"[exactly one of these only: 'Residential'or 'Commercial' or 'Non Converted' or 'Industrial' or 'Mix Uses']",
            "Property_Situated":"[exactly one of these only: 'Metro', 'Urban', 'Semi Urban or Rural (G P Limit)', 'City Limit', 'Development Authority Limit', 'MC Limit', 'GP Limit', 'Nagar Panchayat Limit','Nagar Palika/Parishad/Nigam Limit','Outside MC Limits','Lal dora','Rural']",
            "Property_Jurisdiction": "[one of these only: 'Gram Panchayat', 'Nagar Palika', 'Housing Society', 'Housing Board', 'Development Authority', 'Private Land' or specific Colony/Layout Name]",
            "Title_of_Property": "Value of Property_Jurisdiction and add Limits at last. Example:  If Property_Jurisdiction is 'Gram Panchayat' then Title_of_Property should be 'GP Limits'",
            "Holding_status": "[exactly 'Free Hold' or 'Lease Hold' only, default to 'Lease Hold' if unclear]",
            "property_address": "[full postal address]",
            "Plot_No/House_No": "[exactly as written in document, Plot No, House No, Flat No, etc.]",
            "Floor_No": "[exactly as written in document, Khasra No if not mentioned, leave blank]",
            "Building/Wing_Name": "[exactly as written in document, if not mentioned, leave blank]",
            "Street_No/Road_Name": "[exactly as written in document, if not mentioned, leave blank]",
            "Scheme_Name": "[exactly as written in document, if not mentioned, leave blank]",
            "Village/City": "[exactly as written in document, if not mentioned, leave blank]",
            "Locality": "[exactly as written in document, Tehsil Name, if not mentioned, leave blank]",
            "District": "[exactly as written in document, if not mentioned, leave blank]",
            "State": "[exactly as written in document, if not mentioned, leave blank]",
            "pincode":"6-digit PIN code",
            "setbacks":{
                "Setbacks As per Rule-Front": "[measurement like 3m or 10 ft or NA]",
                "Setbacks As per Rule-Back": "[measurement like 3m or 10 ft or NA]",
                "Setbacks As per Rule-Side 1": "[measurement like 3m or 10 ft or NA]",
                "Setbacks As per Rule-Side 2": "[measurement like 3m or 10 ft or NA]"
            },
            "property_boundaries": {
                "north": "[boundary description in ENGLISH like 'House of Mr Ram' or 'Road' or 'NA']",
                "south": "[boundary description in ENGLISH like 'House of Mr Ram' or 'Road' or 'NA']",
                "east": "[boundary description in ENGLISH like 'House of Mr Ram' or 'Road' or 'NA']",
                "west": "[boundary description in ENGLISH like 'House of Mr Ram' or 'Road' or 'NA']"
            },
            "property_dimensions": {
                "unit": "[unit of measurement like 'mt' or 'ft']",
                "north": "[length of northern side like '30' or 'NA']",
                "south": "[length of southern side like '35' or 'NA']",
                "east": "[length of eastern side like '25' or 'NA']",
                "west": "[length of western side like '48' or 'NA']"
            }
            }

            STRICT TRANSLATION RULES:
            - If you see "गांगा जी मेडी" → translate to "Field of Ganga Ji"
            - If you see "चंचलमत का घर" → translate to "House of Chanchalmat"
            - If you see "रास्ता" → translate to "Road"
            - If you see any Hindi/local language text → MUST translate to English
            - If text is unclear → use descriptive English like "Adjacent Property" or "Neighboring House"
            - Numbers can stay as numbers (15, 30, etc.)

            BOUNDARY DESCRIPTION EXAMPLES:
            - "House of Mr [Name]"
            - "Road" or "[Width] ft Road"
            - "Adjacent Property"
            - "Neighboring Building"
            - "Open Land"
            - "Government Land"

            DIMENSION EXTRACTION:
            - Look for numbers followed by 'ft', 'feet', or measurement indicators
            - Extract only the numeric value (e.g., "15 ft" → "15")
            - If no clear dimension visible, use "NA"

            CRITICAL RULES:
            - Strict Extraction: No inference. Include only exactly what is written.
            - JSON Output Only: Response must be one valid JSON object.
            - Verbatim & Transliteration: Copy text exactly. If text is in Devanagari, translate it into English.
            - Every key value pair should be in English.
            - Ignore all other data unless it falls under one of the fields above."""

            # Generate content with Gemini
            response = await asyncio.to_thread(
                self.gemini_model.generate_content,
                [uploaded_file, prompt],
                generation_config=genai.GenerationConfig(
                    temperature=0,
                    response_mime_type="application/json"
                )
            )

            self.last_gemini_call = time.time()

            # Parse response
            content = response.text.strip()
            
            # Clean JSON response
            if content.startswith('```json'):
                content = content.replace('```json', '').replace('```', '')
            elif content.startswith('```'):
                content = content.replace('```', '')

            result = json.loads(content)
            
            # Post-process to ensure English-only output
            result = self._ensure_english_output(result)
            
            print(f"✅ Gemini analyzed document: {Path(document_path).name}")
            return result

        except Exception as e:
            print(f"❌ Gemini analysis failed for {document_path}: {e}")
            return self._get_fallback_document_result()

    def _ensure_english_output(self, result: Dict) -> Dict:
        """Post-process to ensure all text fields are in English"""
        
        # Translation mapping for common Hindi/local terms
        translation_map = {
            "गांगा जी मेडी": "Field of Ganga Ji",
            "चंचलमत का घर": "House of Chanchalmat",
            "रास्ता": "Road",
            "घर": "House",
            "मेडी": "Field",
            "का": "of",
            "जी": "Ji",
            "श्री": "Mr",
            "श्रीमती": "Mrs",
            "डॉ": "Dr"
        }

        # Fields that need translation
        text_fields = ["Document_Type", "Owner_Name", "Property_Jurisdiction","Title_of_Property", "property_address"]

        # Translate main text fields
        for field in text_fields:
            if field in result and result[field] != "NA":
                original_text = result[field]
                
                # Check if contains non-English characters
                if any(ord(char) > 127 for char in original_text):
                    # Try to translate using mapping
                    translated = original_text
                    for hindi_term, english_term in translation_map.items():
                        translated = translated.replace(hindi_term, english_term)
                    
                    result[field] = translated

        # Translate boundary descriptions
        if "property_boundaries" in result:
            boundary_keys = ["north", "south", "east", "west"]
            for key in boundary_keys:
                if key in result["property_boundaries"] and result["property_boundaries"][key] != "NA":
                    original_text = result["property_boundaries"][key]
                    
                    if any(ord(char) > 127 for char in original_text):
                        translated = original_text
                        for hindi_term, english_term in translation_map.items():
                            translated = translated.replace(hindi_term, english_term)
                        
                        # If still contains non-English, use generic description
                        if any(ord(char) > 127 for char in translated):
                            if "घर" in original_text or "House" in translated:
                                result["property_boundaries"][key] = "Adjacent House"
                            elif "रास्ता" in original_text or "Road" in translated:
                                result["property_boundaries"][key] = "Road"
                            elif "मेडी" in original_text or "Field" in translated:
                                result["property_boundaries"][key] = "Adjacent Field"
                            else:
                                result["property_boundaries"][key] = "Adjacent Property"
                        else:
                            result["property_boundaries"][key] = translated

        return result

    async def analyze_property_documents(self, document_paths: List[str]) -> Dict:
        """Analyze multiple property documents with smart routing and rate limiting"""
        try:
            print(f"📄 Analyzing {len(document_paths)} property documents...")

            # All documents are treated as property documents
            property_results = []
            
            if document_paths:
                print("🏘️ Analyzing property documents with Gemini...")
                
                # Process in batches to avoid rate limits
                batch_size = 1  # Process one document at a time for better rate limiting
                for i in range(0, len(document_paths), batch_size):
                    batch = document_paths[i:i + batch_size]
                    batch_tasks = [self.analyze_real_estate_document_with_gemini(doc) for doc in batch]
                    batch_results = await asyncio.gather(*batch_tasks)
                    property_results.extend(batch_results)

                    # Add delay between batches
                    if i + batch_size < len(document_paths):
                        print(f"⏳ Rate limiting: waiting 4 seconds before next document...")
                        await asyncio.sleep(4)

            # Aggregate results
            aggregated_results = self._aggregate_document_results(property_results)

            print(f"📊 Document analysis complete: {len(property_results)} documents processed")
            return aggregated_results

        except Exception as e:
            print(f"❌ Failed to analyze documents: {e}")
            return self._get_fallback_document_result()

    def _aggregate_document_results(self, results: List[Dict]) -> Dict:
        """Aggregate results from multiple document analyses"""
        if not results:
            return self._get_fallback_document_result()

        # If only one document, return it directly
        if len(results) == 1:
            return results[0]

        # For multiple documents, take the most complete information
        aggregated = self._get_fallback_document_result()

        # Priority order: Sale Deed > Lease Agreement > Survey > Others
        priority_order = ["Copy of Sale Deed", "Sale Deed", "Lease Agreement", "Survey Document"]

        # Find the highest priority document
        primary_doc = None
        for priority_type in priority_order:
            for result in results:
                if priority_type.lower() in result.get("Document_Type", "").lower():
                    primary_doc = result
                    break
            if primary_doc:
                break

        # If no priority document found, use the first one
        if not primary_doc:
            primary_doc = results

        # Start with primary document
        aggregated.update(primary_doc)

        # Fill in missing information from other documents
        for result in results:
            if result == primary_doc:
                continue

            # Fill in missing fields
            for key, value in result.items():
                if key in aggregated and aggregated[key] == "NA" and value != "NA":
                    aggregated[key] = value
                elif key == "property_boundaries" and isinstance(value, dict):
                    for boundary_key, boundary_value in value.items():
                        if (boundary_key in aggregated["property_boundaries"] and 
                            aggregated["property_boundaries"][boundary_key] == "NA" and 
                            boundary_value != "NA"):
                            aggregated["property_boundaries"][boundary_key] = boundary_value
                elif key == "property_dimensions" and isinstance(value, dict):
                    for dim_key, dim_value in value.items():
                        if (dim_key in aggregated["property_dimensions"] and 
                            aggregated["property_dimensions"][dim_key] == "NA" and 
                            dim_value != "NA"):
                            aggregated["property_dimensions"][dim_key] = dim_value

        return aggregated

    def _get_fallback_document_result(self) -> Dict:
        """Return fallback results when document analysis fails"""
        return {
            "Document_Type": "NA",
            "Owner_Name": "NA",
            "Property_Jurisdiction": "NA",
            "Title_of_Property": "NA",
            "Type_of_Property_As_per_document": "NA",
            "Property_Situated": "NA",
            "Plot_No/House_No": "NA",
            "Floor_No": "NA",
            "Building/Wing_Name": "NA",
            "Street_No/Road_Name": "NA",
            "Scheme_Name": "NA",
            "Village/City": "NA",
            "Locality": "NA",
            "pincode": "000000",
            "setbacks": {
                "Setbacks As per Rule-Front": "NA",
                "Setbacks As per Rule-Back": "NA",
                "Setbacks As per Rule-Side 1": "NA",
                "Setbacks As per Rule-Side 2": "NA"
            },
            "Holding_status": "Free hold",
            "property_address": "NA",
            "property_boundaries": {
                "north": "NA",
                "south": "NA",
                "east": "NA",
                "west": "NA"
            },
            "property_dimensions": {
                "unit": "NA",
                "north": "NA",
                "south": "NA",
                "east": "NA",
                "west": "NA"
            }
        }

    async def extract_single_document(self, document_path: str) -> Dict:
        """Extract data from a single document - convenience method"""
        return await self.analyze_real_estate_document_with_gemini(document_path)

# Usage example
if __name__ == "__main__":
    import sys
    
    async def main():
        analyzer = DocumentAnalyzer()
        
        if len(sys.argv) > 1:
            # Single document analysis
            document_path = sys.argv
            result = await analyzer.extract_single_document(document_path)
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            # Multiple document analysis example
            document_paths = [
                "path/to/document1.pdf",
                "path/to/document2.pdf"
            ]
            result = await analyzer.analyze_property_documents(document_paths)
            print(json.dumps(result, indent=2, ensure_ascii=False))
    
    asyncio.run(main())
