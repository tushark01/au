import os
import asyncio
import google.generativeai as genai
from typing import Optional

class GeminiVisionOCR:
    """Gemini Pro Vision for OCR with enhanced accuracy"""
    
    def __init__(self):
        genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
        self.model = genai.GenerativeModel('gemini-2.5-pro')
    
    async def extract_text_from_image(self, image_path: str) -> str:
        """Extract text using Gemini Pro Vision"""
        try:
            # Read image file
            with open(image_path, 'rb') as image_file:
                image_data = image_file.read()
            
            # Create image part for Gemini
            image_part = {
                "mime_type": "image/png",
                "data": image_data
            }
            
            prompt = """Perform highly accurate OCR on this document image. Extract ALL visible text with maximum precision.

REQUIREMENTS:
- Extract every word, number, punctuation mark, and symbol
- Maintain exact formatting, indentation, and line breaks
- Include all headers, subheadings, body text, and footnotes
- Capture signatures, stamps, handwritten annotations
- Preserve document structure and layout
- Handle multiple columns, tables, and complex layouts
- If text is blurry or damaged, provide best interpretation
- Return ONLY the extracted text with no additional commentary

This is a critical legal/property document requiring 100% accuracy in text extraction."""

            # Generate content with Gemini
            response = await asyncio.to_thread(
                self.model.generate_content,
                [prompt, image_part]
            )
            
            extracted_text = response.text.strip()
            print(f"✅ Gemini Pro Vision: {len(extracted_text)} chars extracted")
            return extracted_text
            
        except Exception as e:
            print(f"❌ Gemini Vision extraction failed: {e}")
            return ""
