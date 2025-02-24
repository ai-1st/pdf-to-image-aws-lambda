import pdf2image
import json
import logging
import os
import uuid
import boto3
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

def process_pdf_to_images(pdf_key, file_id):
    try:
        # Download PDF from S3
        pdf_obj = s3_client.get_object(Bucket=BUCKET_NAME, Key=pdf_key)
        pdf_bytes = pdf_obj['Body'].read()
        
        # Convert PDF to images
        logger.info("Converting PDF to images")
        images = pdf2image.convert_from_bytes(pdf_bytes, dpi=200)
        logger.info(f"Converted PDF to {len(images)} images")
        
        # Upload images to S3 and collect URLs
        image_urls = []
        for i, image in enumerate(images):
            image_key = f"pages/{file_id}/page-{i + 1}.png"
            
            # Convert image to PNG bytes
            img_buffer = BytesIO()
            image.save(img_buffer, format='PNG')
            img_buffer.seek(0)
            img_bytes = img_buffer.read()
            
            # Upload image without ACL (using bucket policy instead)
            s3_client.put_object(Bucket=BUCKET_NAME,
                               Key=image_key,
                               Body=img_bytes,
                               ContentType='image/png')
            
            # Generate public URL
            url = f"https://{BUCKET_NAME}.s3.amazonaws.com/{image_key}"
            image_urls.append(url)
        
        return image_urls
        
    except Exception as e:
        logger.exception(f"Error during processing: {str(e)}")
        raise

def lambda_handler(event, context):
    try:
        # Get the request type from query parameters
        request_type = event.get('queryStringParameters', {}).get('type')
        
        if request_type == 'get_upload_url':
            # Generate unique ID and presigned URL for upload
            file_id = str(uuid.uuid4())
            pdf_key = f"uploads/{file_id}/original.pdf"
            presigned_url = generate_presigned_url(pdf_key)
            
            if presigned_url:
                return create_response(200, {
                    "uploadUrl": presigned_url,
                    "fileId": file_id
                })
            else:
                return create_response(500, "Failed to generate upload URL")
                
        elif request_type == 'process':
            # Get file ID from query parameters
            file_id = event.get('queryStringParameters', {}).get('fileId')
            if not file_id:
                return create_response(400, "Missing fileId parameter")
            
            # Process PDF and return image URLs
            pdf_key = f"uploads/{file_id}/original.pdf"
            image_urls = process_pdf_to_images(pdf_key, file_id)
            
            return create_response(200, {
                "imageUrls": image_urls
            })
            
        else:
            return create_response(400, "Invalid request type. Use 'type=get_upload_url' or 'type=process'")

    except Exception as e:
        logger.exception(f"Error during processing: {str(e)}")
        return create_response(500, str(e))