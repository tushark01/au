from aiohttp import ClientError
import boto3
import streamlit as st
import os

def generate_presigned_url(bucket, key, expiry=3600):
    """Generate pre-signed URL with better error handling and proper configuration"""
    try:
        # Ensure proper AWS configuration
        s3_client = boto3.client(
            "s3",
            region_name="ap-south-1",  # Explicitly set region
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY")
        )
        
        # First check if the object exists
        s3_client.head_object(Bucket=bucket, Key=key)
        
        # Generate URL with proper parameters
        url = s3_client.generate_presigned_url(
            ClientMethod="get_object",
            Params={
                "Bucket": bucket, 
                "Key": key,
                "ResponseContentType": "image/jpeg"  # Explicitly set content type
            },
            ExpiresIn=expiry
        )
        return url
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == '404':
            st.warning(f"⚠️ S3 object not found: s3://{bucket}/{key}")
        elif error_code == '403':
            st.warning(f"⚠️ Access denied to S3 object: s3://{bucket}/{key}")
        else:
            st.warning(f"⚠️ S3 error for {key}: {e}")
        return None
    except Exception as e:
        st.warning(f"⚠️ Error generating pre-signed URL for {key}: {e}")
        return None