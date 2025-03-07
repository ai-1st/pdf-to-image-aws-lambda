import pdf2image
import json
import logging
import os
import uuid
import boto3
import hashlib
import base58
from io import BytesIO
from PIL import Image
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)
s3_client = boto3.client('s3')
BUCKET_NAME = os.environ['BUCKET_NAME']

def create_response(status_code, body):
    return {
        "statusCode": status_code,
        "body": json.dumps(body) if isinstance(body, (dict, list)) else body
    }

def calculate_file_hash(data):
    """Calculate MD5 hash of binary data and encode it in base58."""
    md5_hash = hashlib.md5(data).digest()
    return base58.b58encode(md5_hash).decode('utf-8')

def generate_presigned_url(object_name, expiration=3600):
    try:
        url = s3_client.generate_presigned_url('put_object',
                                             Params={
                                                 'Bucket': BUCKET_NAME,
                                                 'Key': object_name,
                                                 'ContentType': 'application/pdf'
                                             },
                                             ExpiresIn=expiration)
    except ClientError as e:
        logger.error(e)
        return None
    return url

def lambda_handler(event, context):
    try:
        request_type = event.get('queryStringParameters', {}).get('type')
        
        if request_type == 'get_upload_url':
            file_id = str(uuid.uuid4())
            object_name = f'uploads/{file_id}/original.pdf'
            
            upload_url = generate_presigned_url(object_name)
            if not upload_url:
                return create_response(500, {'error': 'Failed to generate upload URL'})
            
            return create_response(200, {
                'uploadUrl': upload_url,
                'fileId': file_id
            })
            
        elif request_type == 'process':
            file_id = event.get('queryStringParameters', {}).get('fileId')
            if not file_id:
                return create_response(400, {'error': 'Missing fileId parameter'})
            
            # Download PDF from S3
            pdf_key = f'uploads/{file_id}/original.pdf'
            try:
                pdf_obj = s3_client.get_object(Bucket=BUCKET_NAME, Key=pdf_key)
                pdf_content = pdf_obj['Body'].read()
            except ClientError as e:
                logger.error(f"Error downloading PDF: {e}")
                return create_response(404, {'error': 'PDF file not found'})
            
            # Convert PDF to images
            try:
                images = pdf2image.convert_from_bytes(pdf_content)
            except Exception as e:
                logger.error(f"Error converting PDF: {e}")
                return create_response(500, {'error': 'Failed to convert PDF'})
            
            # Upload each image with MD5+Base58 hash as filename
            image_urls = []
            for img in images:
                # Convert image to bytes and calculate hash
                img_byte_arr = BytesIO()
                img.save(img_byte_arr, format='PNG')
                img_byte_arr = img_byte_arr.getvalue()
                
                # Calculate MD5 of the image data and encode in base58
                img_hash = calculate_file_hash(img_byte_arr)
                img_key = f'pages/{img_hash}.png'
                preview_key = f'pages/{img_hash}-preview.png'
                
                # Create preview image
                preview_size = (300, 300)  # Adjust size as needed
                preview_img = img.copy()
                preview_img.thumbnail(preview_size, Image.LANCZOS)
                preview_byte_arr = BytesIO()
                preview_img.save(preview_byte_arr, format='PNG')
                preview_byte_arr = preview_byte_arr.getvalue()
                
                try:
                    # Check if images already exist
                    images_exist = True
                    try:
                        s3_client.head_object(Bucket=BUCKET_NAME, Key=img_key)
                        s3_client.head_object(Bucket=BUCKET_NAME, Key=preview_key)
                        logger.info(f"Images {img_key} and {preview_key} already exist, skipping upload")
                    except ClientError as e:
                        if e.response['Error']['Code'] == '404':
                            images_exist = False
                    
                    if not images_exist:
                        # Upload only if images don't exist
                        s3_client.put_object(
                            Bucket=BUCKET_NAME,
                            Key=img_key,
                            Body=img_byte_arr,
                            ContentType='image/png'
                        )
                        s3_client.put_object(
                            Bucket=BUCKET_NAME,
                            Key=preview_key,
                            Body=preview_byte_arr,
                            ContentType='image/png'
                        )
                    
                    # Generate public URL for the image
                    url = f"https://{BUCKET_NAME}.s3.amazonaws.com/{img_key}"
                    image_urls.append(url)
                    
                except Exception as e:
                    logger.error(f"Error uploading image: {e}")
                    return create_response(500, {'error': 'Failed to upload image'})
            
            # Clean up the original PDF
            try:
                s3_client.delete_object(Bucket=BUCKET_NAME, Key=pdf_key)
            except ClientError as e:
                logger.warning(f"Failed to delete original PDF: {e}")
            
            return create_response(200, {'imageUrls': image_urls})
            
        else:
            return create_response(400, {'error': 'Invalid request type'})
            
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return create_response(500, {'error': str(e)})