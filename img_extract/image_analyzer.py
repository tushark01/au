import os
import base64
import json
import asyncio
import time
from typing import List, Dict, Optional
from openai import OpenAI
from pathlib import Path
import google.generativeai as genai
from tenacity import retry, stop_after_attempt, wait_exponential

class ImageAnalyzer:

    def __init__(self):
        self.openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

        # Configure Gemini
        genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
        self.gemini_model = genai.GenerativeModel('gemini-2.5-pro')

        # Rate limiting
        self.last_openai_call = 0
        self.openai_delay = 1.0  # Minimum delay between calls

    def encode_image_to_base64(self, image_path: str) -> str:
        """Encode image to base64 for OpenAI API"""
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')

    def is_site_plan_image(self, image_path: str) -> bool:
        """Identify if image is a site plan/map that should use Gemini"""
        filename = Path(image_path).name.lower()
        site_plan_keywords = [
            'site_plan', 'site plan', 'siteplan',
            'map', 'road_map', 'hybrid_map',
            'layout', 'plot', 'survey',
            'boundary', 'dimension', 'plan'
        ]

        return any(keyword in filename for keyword in site_plan_keywords)

    def identify_map_images(self, image_paths: List[str]) -> List[str]:
        """Identify Google Maps/satellite images (not site plans)"""
        map_images = []

        for image_path in image_paths:
            filename = Path(image_path).name.lower()
            # Only satellite/aerial maps, not site plans
            if any(keyword in filename for keyword in ['satellite', 'aerial', 'google']) and not self.is_site_plan_image(image_path):
                map_images.append(image_path)

        return map_images

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=8, max=30))
    async def analyze_with_openai_rate_limited(self, image_path: str) -> Dict:
        """OpenAI analysis with enhanced rate limiting"""
        try:
            # ENHANCED rate limiting - increased delays
            current_time = time.time()
            time_since_last_call = current_time - self.last_openai_call
            min_delay = 3.0  # Increased from 1.0 to 3.0 seconds

            if time_since_last_call < min_delay:
                await asyncio.sleep(min_delay - time_since_last_call)

            # Encode image
            base64_image = self.encode_image_to_base64(image_path)

            # Your existing prompt here...
            prompt = """Analyze this property image and return ONLY a JSON with these exact keys:
{
  "FlatsOnEachFloor": "[number of flats/units visible per floor, or NA if unclear]",
  "OccupancyPercent": "[Value will be '0' if the property is individual i.e. not a flat, else leave blank]",
  "PropertyUsage":  ['Commercial office', 'Commercial shop','Complete Commercial', 'Vacant land', 'Residential', 'Industrial', 'Mix Uses','Non Converted','Plot','Under Construction','Other'],
}

Analysis Rules:
- **Flats Count**: Count visible doors, balconies, windows patterns per floor
- **Occupancy Percent**: If individual property, set to '0'.
- **Property Usage**: Use dropdown options, choose best fit based on visible features.

Use exact values from brackets only."""

            # Call OpenAI API with CORRECT model name
            response = await asyncio.to_thread(
                self.openai_client.chat.completions.create,
                model="gpt-4o-mini",  # ✅ FIXED: Correct model name
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}",
                                    "detail": "low"  # ✅ REDUCED: Lower detail to save tokens
                                }
                            }
                        ]
                    }
                ],
                max_tokens=250,  # ✅ REDUCED: From 300 to 250 tokens
                temperature=0.1
            )

            self.last_openai_call = time.time()

            # Rest of your parsing logic...
            content = response.choices[0].message.content.strip()

            if content.startswith('```json'):
                content = content.replace('```json', '').replace('```', '')
            elif content.startswith('```'):
                content = content.replace('```', '')

            result = json.loads(content)

            print(f"✅ OpenAI analyzed: {Path(image_path).name}")
            return result

        except Exception as e:
            print(f"❌ OpenAI analysis failed for {image_path}: {e}")
            return {
                "FlatsOnEachFloor": "NA",
                "OccupancyPercent": "NA",
                "PropertyUsage": "NA"
            }

    async def analyze_site_plan_with_gemini(self, image_path: str) -> Dict:
        """Analyze site plan/map images using Gemini 2.5 Pro with English-only output"""
        try:
            # Read image file
            with open(image_path, 'rb') as image_file:
                image_data = image_file.read()

            # Create image part for Gemini
            image_part = {
                "mime_type": "image/jpeg",
                "data": image_data
            }

            # Enhanced site plan analysis prompt with strict English requirement
            prompt = """Analyze this site plan/map image and extract boundary and dimension information.

IMPORTANT: Return ONLY a JSON with these exact keys and TRANSLATE ALL TEXT TO ENGLISH:

{
  "eastAsPerDocument": "[boundary description in ENGLISH ONLY like 'House of Mr Ram' or 'Road' or 'NA']",
  "westAsPerDocument": "[boundary description in ENGLISH ONLY like 'House of Mr Ram' or 'Road' or 'NA']",
  "northAsPerDocument": "[boundary description in ENGLISH ONLY like 'House of Mr Ram' or 'Road' or 'NA']",
  "southAsPerDocument": "[boundary description in ENGLISH ONLY like 'House of Mr Ram' or 'Road' or 'NA']",
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

MANDATORY: All boundary descriptions must be in English. Do not include any Hindi, regional language, or non-English text in the output."""

            # Generate content with Gemini
            response = await asyncio.to_thread(
                self.gemini_model.generate_content,
                [prompt, image_part]
            )

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

            print(f"✅ Gemini analyzed site plan (English-only): {Path(image_path).name}")
            return result

        except Exception as e:
            print(f"❌ Gemini analysis failed for {image_path}: {e}")
            # Return fallback values
            return {
                "eastAsPerDocument": "NA",
                "westAsPerDocument": "NA",
                "northAsPerDocument": "NA",
                "southAsPerDocument": "NA",
            }

    def _ensure_english_output(self, result: Dict) -> Dict:
        """Post-process to ensure all boundary descriptions are in English"""

        # Translation mapping for common Hindi/local terms
        translation_map = {
            "गांगा जी मेडी": "Field of Ganga Ji",
            "चंचलमत का घर": "House of Chanchalmat",
            "रास्ता": "Road",
            "घर": "House",
            "मेडी": "Field",
            "का": "of",
            "जी": "Ji"
        }

        boundary_keys = ["eastAsPerDocument", "westAsPerDocument", "northAsPerDocument", "southAsPerDocument"]

        for key in boundary_keys:
            if key in result and result[key] != "NA":
                original_text = result[key]

                # Check if contains non-English characters
                if any(ord(char) > 127 for char in original_text):
                    # Try to translate using mapping
                    translated = original_text
                    for hindi_term, english_term in translation_map.items():
                        translated = translated.replace(hindi_term, english_term)

                    # If still contains non-English, use generic description
                    if any(ord(char) > 127 for char in translated):
                        if "घर" in original_text or "House" in translated:
                            result[key] = "Adjacent House"
                        elif "रास्ता" in original_text or "Road" in translated:
                            result[key] = "Road"
                        elif "मेडी" in original_text or "Field" in translated:
                            result[key] = "Adjacent Field"
                        else:
                            result[key] = "Adjacent Property"
                    else:
                        result[key] = translated

        return result

    async def analyze_property_images(self, image_paths: List[str]) -> Dict:
        """Analyze all images with smart routing and rate limiting"""
        try:
            print(f"🔍 Analyzing {len(image_paths)} images with smart routing...")

            # Separate site plans from regular property images
            site_plan_images = [img for img in image_paths if self.is_site_plan_image(img)]
            regular_images = [img for img in image_paths if not self.is_site_plan_image(img)]

            print(f"📋 Found {len(site_plan_images)} site plans, {len(regular_images)} regular images")

            # Analyze regular images with OpenAI (with rate limiting)
            regular_results = []
            if regular_images:
                print("🖼️ Analyzing regular property images with OpenAI...")

                # Process in smaller batches to avoid rate limits
                batch_size = 2  # ✅ REDUCED: From 3 to 2 images per batch
                for i in range(0, len(regular_images), batch_size):
                    batch = regular_images[i:i + batch_size]
                    batch_tasks = [self.analyze_with_openai_rate_limited(img) for img in batch]
                    batch_results = await asyncio.gather(*batch_tasks)
                    regular_results.extend(batch_results)

                    # Add longer delay between batches
                    if i + batch_size < len(regular_images):
                        print(f"⏳ Rate limiting: waiting 5 seconds before next batch...")
                        await asyncio.sleep(5)  # ✅ INCREASED: From 2 to 5 seconds

            # Analyze site plans with Gemini
            site_plan_results = []
            if site_plan_images:
                print("🗺️ Analyzing site plans with Gemini...")
                site_plan_tasks = [self.analyze_site_plan_with_gemini(img) for img in site_plan_images]
                site_plan_results = await asyncio.gather(*site_plan_tasks)

            # Aggregate regular image results
            regular_analysis = self._aggregate_regular_results(regular_results)

            # Aggregate site plan results
            site_plan_analysis = self._aggregate_site_plan_results(site_plan_results)

            # Combine results
            combined_results = {**regular_analysis, **site_plan_analysis}

            print(f"📊 Analysis complete: {len(regular_results)} regular + {len(site_plan_results)} site plans")
            return combined_results

        except Exception as e:
            print(f"❌ Failed to analyze images: {e}")
            return self._get_fallback_results()

    def _aggregate_regular_results(self, results: List[Dict]) -> Dict:
        if not results:
            return {
                "FlatsOnEachFloor": "NA",
                "OccupancyPercent": "NA",
                "PropertyUsage": "NA"
            }

        # Extract values
        flats_counts = []
        occupancy_percentages = []
        property_usages = []

        for result in results:
            if result["FlatsOnEachFloor"] != "NA":
                try:
                    flats = int(result["FlatsOnEachFloor"])
                    flats_counts.append(flats)
                except (ValueError, TypeError):
                    pass
            if result.get("OccupancyPercent") != "NA":
                try:
                    completion = int(result["OccupancyPercent"])
                    occupancy_percentages.append(completion)
                except (ValueError, TypeError):
                    pass
            if result.get("PropertyUsage") != "NA":
                try:
                    completion = int(result["PropertyUsage"])
                    property_usages.append(completion)
                except (ValueError, TypeError):
                    pass

        def get_average_completion(completions):
            if not completions:
                return "NA"
            avg = sum(completions) / len(completions)
            # Round to nearest multiple of 5
            rounded = round(avg / 5) * 5
            return str(int(rounded))

        return {
            "FlatsOnEachFloor": str(max(flats_counts)) if flats_counts else "NA",
            "OccupancyPercent": get_average_completion(occupancy_percentages),
            "PropertyUsage": max(set(property_usages), key=property_usages.count) if property_usages else "NA"
        }

    def _aggregate_site_plan_results(self, results: List[Dict]) -> Dict:
        """Aggregate results from site plan images"""
        if not results:
            return {
                "eastAsPerDocument": "NA",
                "westAsPerDocument": "NA",
                "northAsPerDocument": "NA",
                "southAsPerDocument": "NA",
            }

        # Take the best non-NA values from all site plans
        aggregated = {
            "eastAsPerDocument": "NA",
            "westAsPerDocument": "NA",
            "northAsPerDocument": "NA",
            "southAsPerDocument": "NA",
        }

        # Merge non-NA values
        for result in results:
            for key in aggregated.keys():
                if key in result and result[key] != "NA" and aggregated[key] == "NA":
                    aggregated[key] = result[key]

        return aggregated

    def _get_fallback_results(self) -> Dict:
        """Return fallback results when analysis fails"""
        return {
            "FlatsOnEachFloor": "NA",
            "OccupancyPercent": "NA",
            "PropertyUsage": "NA",
        }
