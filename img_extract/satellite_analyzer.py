import os
import base64
import json
import asyncio
import time
from typing import List, Dict
from openai import OpenAI

class SatelliteAnalyzer:
    """Analyze satellite/Google Maps images with enhanced rate limiting"""

    def __init__(self):
        self.client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.last_call_time = 0
        self.min_delay = 3.0  # 3 seconds between calls

    def encode_image_to_base64(self, image_path: str) -> str:
        """Encode image to base64 for OpenAI API"""
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')

    async def analyze_satellite_image(self, image_path: str) -> Dict:
        """Analyze satellite/map image with rate limiting"""
        try:
            # Rate limiting
            current_time = time.time()
            time_since_last_call = current_time - self.last_call_time
            if time_since_last_call < self.min_delay:
                await asyncio.sleep(self.min_delay - time_since_last_call)

            base64_image = self.encode_image_to_base64(image_path)

            prompt = """Analyze this satellite map image and return ONLY a JSON with these exact keys:
{
  "ClassOfLocality": ['High', 'Middle', 'Low', 'Urban','Mixed', 'Rural', 'Semi Urban','Residential', 'Commercial', 'Industrial','Agriculture & Mixed'],
}
"""

            response = await asyncio.to_thread(
                self.client.chat.completions.create,
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{base64_image}",
                                    "detail": "low"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=200,
                temperature=0.1
            )

            self.last_call_time = time.time()

            content = response.choices[0].message.content.strip()

            # Clean JSON response
            if content.startswith("```json"):
                content = content.replace("```json", '').replace("```", '')
            elif content.startswith("```"):
                content = content.replace("```", '')

            result = json.loads(content)
            print(f"✅ Analyzed satellite image: {os.path.basename(image_path)}")
            return result

        except Exception as e:
            print(f"❌ Failed to analyze satellite image {image_path}: {e}")
            return {
                "ClassOfLocality": "Middle",
            }

    async def analyze_satellite_images(self, image_paths: List[str]) -> Dict:
        """Analyze satellite images with sequential processing to avoid rate limits"""
        if not image_paths:
            return {}

        try:
            print(f"🛰️ Analyzing {len(image_paths)} satellite images sequentially...")

            # Process images sequentially instead of concurrently
            results = []
            for i, image_path in enumerate(image_paths):
                print(f"🛰️ Processing satellite image {i+1}/{len(image_paths)}")
                result = await self.analyze_satellite_image(image_path)
                results.append(result)

                # Add delay between images
                if i < len(image_paths) - 1:
                    await asyncio.sleep(2)

            if results:
                occupancy_values = [r.get("ClassOfLocality", "Middle") for r in results]

                aggregated = {
                    "ClassOfLocality": max(set(occupancy_values), key=occupancy_values.count)
                }

                print(f"🗺️ Satellite analysis complete: {aggregated}")
                return aggregated

            return {}

        except Exception as e:
            print(f"❌ Failed to analyze satellite images: {e}")
            return {}
