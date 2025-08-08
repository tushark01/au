import os
import streamlit as st

def get_latest_zip_filename(s3_manager, case_number):
    """Get the latest zip filename from S3 downloads folder"""
    try:
        # List all files in the downloads folder
        downloads_prefix = f"{s3_manager.base_path}/downloads/"
        
        response = s3_manager.s3_client.list_objects_v2(
            Bucket=s3_manager.bucket,
            Prefix=downloads_prefix
        )
        
        if 'Contents' not in response:
            return None
        
        # Filter for zip files and sort by last modified
        zip_files = []
        for obj in response['Contents']:
            if obj['Key'].endswith('.zip'):
                zip_files.append({
                    'key': obj['Key'],
                    'filename': os.path.basename(obj['Key']),
                    'last_modified': obj['LastModified']
                })
        
        if not zip_files:
            return None
        
        # Sort by last modified (most recent first)
        zip_files.sort(key=lambda x: x['last_modified'], reverse=True)
        
        # Return the most recent zip filename
        latest_zip = zip_files[0]['filename']        
        return latest_zip
        
    except Exception as e:
        st.error(f"Error finding zip file: {str(e)}")
        return None
    
def get_pdf_files_from_s3(s3_manager, case_number):
    """Get PDF files from S3 extracted_files folder with better error handling"""
    try:
        # List all files in the extracted_files folder
        extracted_prefix = f"{s3_manager.base_path}/extracted_files/"
                
        response = s3_manager.s3_client.list_objects_v2(
            Bucket=s3_manager.bucket,
            Prefix=extracted_prefix
        )
        
        if 'Contents' not in response:
            st.warning(f"📁 No files found in: {extracted_prefix}")
            return []
        
        # Filter for PDF files
        pdf_files = []
        all_files = []
        
        for obj in response['Contents']:
            filename = os.path.basename(obj['Key'])
            all_files.append(filename)
            
            if obj['Key'].lower().endswith('.pdf'):
                pdf_files.append({
                    'key': obj['Key'],
                    'filename': filename,
                    'full_s3_path': f"s3://{s3_manager.bucket}/{obj['Key']}",
                    'size': obj['Size']
                })
                
        return pdf_files
        
    except Exception as e:
        st.error(f"❌ Error finding PDF files: {str(e)}")
        return []