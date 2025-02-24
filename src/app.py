import pdf2image
import json
import logging
import os
import uuid
import boto3
import hashlib
from io import BytesIO
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

def calculate_sha256(data):
    """Calculate SHA256 hash of binary data."""
    return hashlib.sha256(data).hexdigest()

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
            
            # Upload each image with SHA256 checksum as filename
            image_urls = []
            for img in images:
                # Convert image to bytes and calculate SHA256
                img_byte_arr = BytesIO()
                img.save(img_byte_arr, format='PNG')
                img_byte_arr = img_byte_arr.getvalue()
                
                # Calculate SHA256 of the image data
                img_hash = calculate_sha256(img_byte_arr)
                img_key = f'pages/{img_hash}.png'
                
                try:
                    # Check if image already exists
                    try:
                        s3_client.head_object(Bucket=BUCKET_NAME, Key=img_key)
                        logger.info(f"Image {img_key} already exists, skipping upload")
                    except ClientError as e:
                        if e.response['Error']['Code'] == '404':
                            # Upload only if image doesn't exist
                            s3_client.put_object(
                                Bucket=BUCKET_NAME,
                                Key=img_key,
                                Body=img_byte_arr,
                                ContentType='image/png'
                            )
                            logger.info(f"Uploaded new image {img_key}")
                        else:
                            raise
                    
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