import os
import sys
import json
import asyncio
import tempfile
import shutil
from datetime import datetime
from dotenv import load_dotenv

# **FIX: Add proper path resolution for img_extract modules**
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

# **FIX: Use absolute imports with error handling**
try:
    from s3_downloader import S3Downloader
    from file_processor import FileProcessor
    from image_analyzer import ImageAnalyzer
    from satellite_analyzer import SatelliteAnalyzer
    from json_manager import JSONManager
except ImportError as e:
    print(f"❌ Import error: {e}")
    print(f"📁 Current directory: {current_dir}")
    print(f"📂 Python path: {sys.path}")
    raise ImportError(f"Failed to import required modules from img_extract directory: {e}")

# Load environment variables
load_dotenv()


class DocumentExtractionPipeline:
    """Enhanced pipeline with direct S3 processing and automatic cleanup"""
    
    def __init__(self):
        self.s3_downloader = S3Downloader()
        self.file_processor = FileProcessor()
        self.image_analyzer = ImageAnalyzer()
        self.satellite_analyzer = SatelliteAnalyzer()
        self.json_manager = JSONManager()
        
    async def process_s3_zip_direct(self, s3_url: str):
        """
        Process S3 zip file with temporary storage and automatic cleanup
        
        Args:
            s3_url: S3 URL like s3://dfautoindusind/processes/uuid/downloads/file.zip
        """
        # Create temporary directory for processing
        temp_dir = tempfile.mkdtemp(prefix="doc_extraction_")
        
        try:
            print(f"🚀 Starting direct S3 processing pipeline for: {s3_url}")
            print(f"📁 Using temporary directory: {temp_dir}")
            
            # Step 1: Download zip to temporary location
            print("📥 Downloading zip file from S3 to temporary storage...")
            local_zip_path = await self.s3_downloader.download_from_s3(s3_url, temp_dir)
            if not local_zip_path:
                raise Exception("Failed to download zip file from S3")
            
            # Step 2: Extract to temporary directory
            print("📂 Extracting files to temporary storage...")
            extract_dir = os.path.join(temp_dir, "extracted")
            images, pdfs, others = self.file_processor.unzip_and_categorize(local_zip_path, extract_dir)
            
            print(f"📊 Found: {len(images)} images, {len(pdfs)} PDFs, {len(others)} other files")
            
            # Step 3: Process images and upload results directly to S3
            result_json = self.json_manager.get_template()
            
            # Step 4: Process images for property analysis
            if images:
                print("🖼️ Analyzing images with interior completion assessment...")
                image_analysis = await self.image_analyzer.analyze_property_images(images)
                
                if image_analysis:
                    result_json["drafter_field"].update({
                        # Regular property analysis
                        "FlatOnEachFloor": image_analysis.get("FlatsOnEachFloor", ""),
                        "OccupancyPercent": image_analysis.get("OccupancyPercent", "")
                    })

                    # Site plan analysis
                    result_json["mobile_field"].update({
                        "East - As per Actual(Boundary)": image_analysis.get("eastAsPerDocument", ""),
                        "West - As per Actual(Boundary)": image_analysis.get("westAsPerDocument", ""),
                        "North - As per Actual(Boundary)": image_analysis.get("northAsPerDocument", ""),
                        "South - As per Actual(Boundary)": image_analysis.get("southAsPerDocument", ""),
                    })
                    print("✅ Image analysis complete with interior completion assessment.")
            
            # Step 5: Process satellite images
            print("🔍 Looking for satellite/map images...")
            satellite_images = []
            for img in images:
                filename = os.path.basename(img).lower()
                if any(keyword in filename for keyword in ['map', 'satellite', 'aerial', 'hybrid', 'road', 'location']):
                    satellite_images.append(img)

            print(f"🗺️ Found {len(satellite_images)} potential satellite images: {[os.path.basename(img) for img in satellite_images]}")

            if satellite_images:
                print("🛰️ Analyzing satellite images...")
                try:
                    satellite_analysis = await self.satellite_analyzer.analyze_satellite_images(satellite_images)
                    print(f"📊 Satellite analysis result: {satellite_analysis}")
                    
                    if satellite_analysis and any(satellite_analysis.values()):
                        result_json["drafter_field"].update({
                            "ClassOfLocality": satellite_analysis.get("ClassOfLocality", "Middle"),
                            "PropertyUsage": satellite_analysis.get("PropertyUsage", "Residential"),})
                        print("✅ Satellite data added to JSON")
                    else:
                        print("⚠️ Using fallback satellite values")
                        result_json["drafter_field"].update({
                            "ClassOfLocality": "Middle",
                        })
                except Exception as e:
                    print(f"❌ Satellite analysis failed: {e}")
                    result_json["drafter_field"].update({
                        "ClassOfLocality": "Middle",
                    })
            else:
                print("⚠️ No satellite images found, using default values")
                result_json["drafter_field"].update({
                    "ClassOfLocality": "Middle",
                })
            
            # Step 6: Upload final results directly to S3
            s3_result_key = self.s3_downloader.generate_s3_result_key(s3_url)
            await self.s3_downloader.upload_json_to_s3(
                result_json, 
                s3_result_key,
                metadata={
                    'extraction_timestamp': datetime.now().isoformat(),
                    'pipeline_version': '2.0',
                    'source_zip': s3_url
                }
            )
            
            print(f"✅ Processing completed! Results uploaded to S3: {s3_result_key}")
            print("🗑️ Cleaning up temporary files...")
            
            return result_json, s3_result_key
            
        except Exception as e:
            print(f"❌ Pipeline failed: {str(e)}")
            raise
            
        finally:
            # AUTOMATIC CLEANUP - Remove all temporary files
            try:
                shutil.rmtree(temp_dir)
                print(f"🧹 Temporary directory cleaned up: {temp_dir}")
            except Exception as cleanup_error:
                print(f"⚠️ Cleanup warning: {cleanup_error}")

    # Keep the old method for backward compatibility
    async def process_s3_zip(self, s3_url: str, output_dir: str = "extracted_data"):
        """
        Legacy method - redirects to direct S3 processing
        """
        print("⚠️ Using legacy method - redirecting to direct S3 processing...")
        result_json, s3_result_key = await self.process_s3_zip_direct(s3_url)
        
        # Optional: Save a local copy if needed for debugging
        if os.getenv('SAVE_LOCAL_COPY', 'false').lower() == 'true':
            os.makedirs(output_dir, exist_ok=True)
            output_json_path = os.path.join(output_dir, "extracted_data.json")
            self.json_manager.save_json(result_json, output_json_path)
            print(f"📄 Local copy saved to: {output_json_path}")
        
        return result_json

# **NEW: Main function for integration**
async def main(bucket_name, zip_key):
    """
    Main function for integration with the automation pipeline
    
    Args:
        bucket_name: S3 bucket name
        zip_key: S3 key path to the zip file
        
    Returns:
        dict: Extracted JSON data
    """
    s3_url = f"s3://{bucket_name}/{zip_key}"
    pipeline = DocumentExtractionPipeline()
    
    try:
        # Use direct S3 processing
        result, s3_result_key = await pipeline.process_s3_zip_direct(s3_url)
        
        print("🎉 Direct S3 processing completed successfully!")
        print(f"📤 Results uploaded to: {s3_result_key}")
        
        return result
        
    except Exception as e:
        print(f"💥 Pipeline failed: {e}")
        return None

# **Legacy main function for command line usage**
async def main_cli():
    """Main entry point with direct S3 processing"""
    if len(sys.argv) < 2:
        print("Usage: python main.py <s3_url>")
        print("Example: python main.py s3://dfautoindusind/processes/uuid/downloads/file.zip")
        return
    
    s3_url = sys.argv[1]
    pipeline = DocumentExtractionPipeline()
    
    try:
        # Use direct S3 processing
        result, s3_result_key = await pipeline.process_s3_zip_direct(s3_url)
        
        print("🎉 Direct S3 processing completed successfully!")
        print(f"📤 Results uploaded to: {s3_result_key}")
        print("🧹 No local files remain - everything processed and uploaded to S3!")
        print(f"📄 Extracted data preview:")
        print(json.dumps(result["drafter_field"], indent=2)[:500] + "...")
        
    except Exception as e:
        print(f"💥 Pipeline failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main_cli())
