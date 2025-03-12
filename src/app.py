import pdf2image
import json
import logging
import os
import uuid
from pathlib import Path
import boto3
import hashlib
import base58
import shutil
import concurrent.futures
from PIL import Image
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)
s3_client = boto3.client('s3')
BUCKET_NAME = os.environ['BUCKET_NAME']

# Constants
TMP_DIR = '/tmp'
OUTPUT_FOLDER = '/tmp/pages'
THREAD_COUNT = 12
MAIN_IMAGE_SIZE = 2000
PREVIEW_IMAGE_SIZE = 300


def create_response(status_code, body):
    """Create a standardized API response"""
    return {
        "statusCode": status_code,
        "body": json.dumps(body) if isinstance(body, (dict, list)) else body,
        "headers": {
            "Content-Type": "application/json"
        }
    }


def calculate_file_hash(data):
    """Calculate MD5 hash of binary data and encode it in base58."""
    md5_hash = hashlib.md5(data).digest()
    return base58.b58encode(md5_hash).decode('utf-8')


def generate_presigned_url(object_name, expiration=3600):
    """Generate a presigned URL for uploading a file to S3"""
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


def download_pdf_from_s3(file_id):
    """Download PDF from S3 to local /tmp directory"""
    pdf_key = f'uploads/{file_id}.pdf'
    local_pdf_path = f'{TMP_DIR}/{file_id}.pdf'
    
    try:
        s3_client.download_file(BUCKET_NAME, pdf_key, local_pdf_path)
        logger.info(f"Downloaded PDF to {local_pdf_path}")
        return local_pdf_path, pdf_key
    except ClientError as e:
        logger.error(f"Error downloading PDF: {e}")
        raise


def check_cached_results(file_id):
    """Check if processing results are already cached in S3"""
    result_key = f'results/{file_id}.json'
    
    try:
        result_obj = s3_client.get_object(Bucket=BUCKET_NAME, Key=result_key)
        result_content = result_obj['Body'].read().decode('utf-8')
        return json.loads(result_content)
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            logger.info(f"No cached results found for {file_id}")
            return None
        else:
            logger.error(f"Error checking cached results: {e}")
            raise


def save_results_to_cache(file_id, results):
    """Save processing results to S3 cache"""
    result_key = f'results/{file_id}.json'
    
    try:
        s3_client.put_object(
            Bucket=BUCKET_NAME,
            Key=result_key,
            Body=json.dumps(results),
            ContentType='application/json'
        )
        logger.info(f"Saved results to cache: {result_key}")
    except ClientError as e:
        logger.error(f"Error saving results to cache: {e}")
        # Continue execution even if caching fails


def clean_tmp_directory():
    """Clean up the entire /tmp directory to free up space"""
    try:
        # Get all items in /tmp directory
        tmp_items = os.listdir(TMP_DIR)
        
        # Remove each item except for critical system files
        for item in tmp_items:
            item_path = os.path.join(TMP_DIR, item)
            try:
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path)
                    logger.info(f"Removed directory: {item_path}")
                else:
                    os.remove(item_path)
                    logger.info(f"Removed file: {item_path}")
            except Exception as e:
                # Log but continue if a particular file can't be removed
                logger.warning(f"Could not remove {item_path}: {e}")
        
        logger.info("Cleaned up /tmp directory")
    except Exception as e:
        logger.error(f"Error cleaning /tmp directory: {e}")
        # Continue execution even if cleanup fails


def prepare_output_directory():
    """Prepare the output directory for PDF pages"""
    try:
        # Remove the directory if it exists
        if os.path.exists(OUTPUT_FOLDER):
            shutil.rmtree(OUTPUT_FOLDER)
        
        # Create a fresh directory
        os.makedirs(OUTPUT_FOLDER)
        logger.info(f"Created output directory: {OUTPUT_FOLDER}")
    except Exception as e:
        logger.error(f"Error preparing output directory: {e}")
        raise


def convert_pdf_to_images(pdf_path):
    """Convert PDF to images using convert_from_path"""
    try:
        # Check if PDF exists
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
            
        prepare_output_directory()
        
        # Convert PDF to images
        logger.info(f"Converting PDF {pdf_path} to images in {OUTPUT_FOLDER}")
        images = pdf2image.convert_from_path(
            pdf_path,
            output_folder=OUTPUT_FOLDER,
            fmt="jpeg",  # This is the format we want, but pdf2image might use a different extension such as .jpg
            size=MAIN_IMAGE_SIZE,
            thread_count=6,
            output_file="page",  # Base filename for output
            paths_only=True     # Return PIL Image objects
        )
        
        # Verify images were created
        if not images:
            raise Exception("No images were generated from the PDF")
            
        logger.info(f"Successfully converted PDF to {len(images)} images")
        return images
    except Exception as e:
        logger.error(f"Error converting PDF: {e}")
        raise


def process_image(img_path, is_preview):
    """Process a single image to the specified size"""

    # Calculate hash based on file contents
    with open(img_path, 'rb') as f:
        img_hash = calculate_file_hash(f.read())
    
    processed_path = img_path
    suffix = ""
    if is_preview:
        suffix = "-preview"
        img = Image.open(img_path)
        img.thumbnail((PREVIEW_IMAGE_SIZE, PREVIEW_IMAGE_SIZE), Image.LANCZOS)
        # Save processed image
        processed_path = processed_path.replace(".jpg", f"{suffix}.jpg")
        img.save(processed_path, format="JPEG", quality=85, optimize=True)
    
    # Define S3 paths
    s3_key = f"pages/{img_hash}{suffix}.jpeg"

    logger.info(f"Processed {is_preview and 'preview' or 'main'} image: {processed_path}")
    return {
        'local_path': processed_path,
        's3_key': s3_key,
        'hash': img_hash
    }


def process_images_parallel(image_paths):
    """Process images in parallel to create main and preview versions"""
    with concurrent.futures.ThreadPoolExecutor(max_workers=THREAD_COUNT) as executor:
        main_results = list(executor.map(lambda path: process_image(path, False), image_paths))
        preview_results = list(executor.map(lambda path: process_image(path, True), image_paths))
    
    return main_results, preview_results


def check_if_image_exists(s3_key):
    """Check if an image already exists in S3"""
    try:
        s3_client.head_object(Bucket=BUCKET_NAME, Key=s3_key)
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            return False
        else:
            logger.error(f"Error checking if image exists: {e}")
            raise


def upload_image_to_s3(local_path, s3_key, source_ip=None):
    """Upload a single image to S3 with optional source IP tag"""
    try:
        logger.info(f"Uploading image to S3: {local_path} -> {s3_key}")
        # Check if image already exists
        if check_if_image_exists(s3_key):
            logger.info(f"Image {s3_key} already exists, skipping upload")
            return s3_key
        
        # Prepare extra args for upload
        extra_args = {'ContentType': 'image/jpeg'}
        
        # Add source IP as a tag if provided
        if source_ip:
            extra_args['Tagging'] = f"source_ip={source_ip}"
            logger.info(f"Adding source_ip tag: {source_ip} to {s3_key}")
        
        # Upload image
        s3_client.upload_file(
            local_path,
            BUCKET_NAME,
            s3_key,
            ExtraArgs=extra_args
        )
        
        logger.info(f"Uploaded image to {s3_key}")
        return s3_key
    except Exception as e:
        logger.error(f"Error uploading image: {e}")
        raise


def upload_images_parallel(images, source_ip=None):
    """Upload images to S3 in parallel with optional source IP tag"""
    uploaded_keys = []
    
    def upload_task(img):
        try:
            return upload_image_to_s3(img['local_path'], img['s3_key'], source_ip)
        except Exception as e:
            logger.error(f"Error in upload task: {e}")
            return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=THREAD_COUNT) as executor:
        uploaded_keys = list(executor.map(upload_task, images))
    
    return uploaded_keys



def process_pdf(file_id, source_ip=None):
    """Process a PDF file and convert it to images"""
    local_pdf_path = None
    pdf_key = None
    
    try:
        # Clean up the /tmp directory to ensure we have enough space
        clean_tmp_directory()
        
        # Check for cached results
        cached_results = check_cached_results(file_id)
        if cached_results:
            logger.info(f"Using cached results for {file_id}")
            return cached_results
        
        # Download PDF from S3
        local_pdf_path, pdf_key = download_pdf_from_s3(file_id)
        
        # Convert PDF to images
        convert_pdf_to_images(local_pdf_path)
        
        # Get paths of all converted images
        image_paths = os.listdir(OUTPUT_FOLDER)
        logger.info(f"Found {len(image_paths)} images: {image_paths}")
        
        # Sort the image paths based on the page number in the filename
        # Format is like 'page0001-14.jpg' where 14 is the page number
        try:
            image_paths = sorted(
                os.listdir(OUTPUT_FOLDER),
                key=lambda x: int(x.split('-')[1].split('.')[0]) if '-' in x else 0
            )
        except Exception as e:
            logger.warning(f"Error sorting image paths: {e}. Using unsorted paths.")
        
        if not image_paths:
            raise Exception(f"No image files found in {OUTPUT_FOLDER} after conversion")
        
        # Add full path to each image - handle both .jpg and .jpeg extensions
        image_paths = [os.path.join(OUTPUT_FOLDER, path) for path in image_paths 
                      if path.lower().endswith('.jpg') or path.lower().endswith('.jpeg')]
        
        logger.info(f"Processing {len(image_paths)} images: {image_paths}")
        
        # Process images in parallel
        main_images, preview_images = process_images_parallel(image_paths)
        
        # Upload images to S3 in parallel with source IP tag
        if source_ip:
            logger.info(f"Applying source IP tag: {source_ip} to uploaded images")
        main_keys = upload_images_parallel(main_images + preview_images, source_ip)
        
        # Generate URLs for the images
        image_urls = [f"https://{BUCKET_NAME}.s3.amazonaws.com/{key}" for key in main_keys if "-preview" not in key]
        
        # Create result object
        results = {
            'fileId': file_id,
            'imageUrls': image_urls,
            'pageCount': len(image_urls)
        }
        
        # Cache the results
        save_results_to_cache(file_id, results)
        
        return results
    except Exception as e:
        logger.error(f"Error processing PDF {file_id}: {e}")
        raise


def get_upload_url():
    """Generate a presigned URL for uploading a PDF"""
    file_id = str(uuid.uuid4())
    object_name = f'uploads/{file_id}.pdf'
    
    upload_url = generate_presigned_url(object_name)
    if not upload_url:
        raise Exception('Failed to generate upload URL')
    
    return {
        'uploadUrl': upload_url,
        'fileId': file_id
    }


def parse_path_parameters(path):
    """Parse path parameters from the request path"""
    if not path:
        return None, None
    
    # Log raw path for debugging
    logger.info(f"Parsing path: {path}")
    
    # Split path into parts and filter out empty strings
    parts = [p for p in path.split('/') if p]
    logger.info(f"Path parts: {parts}")
    
    # Handle root path
    if not parts:
        return None, None
    
    # Handle specific routes
    if parts[0] == 'upload_url':
        return 'upload_url', None
    elif parts[0] == 'process' and len(parts) > 1:
        return 'process', parts[1]
    
    # Log invalid path for debugging
    logger.info(f"Invalid path parts: {parts}")
    return None, None


def lambda_handler(event, context):
    """Main Lambda handler function"""
    try:
        # Get path parameters from Lambda Function URL event
        path = event.get('rawPath', '')
        logger.info(f"Raw path from event: {path}")
        logger.info(f"Full event: {json.dumps(event)}")
        
        resource, file_id = parse_path_parameters(path)
        logger.info(f"Parsed path: resource={resource}, file_id={file_id}")
        
        # Handle based on path
        if resource == 'upload_url':
            # GET /upload_url
            result = get_upload_url()
            return create_response(200, result)
            
        elif resource == 'process' and file_id:
            # GET /process/<file_id>
            # Extract source IP from request context
            source_ip = None
            if 'requestContext' in event and 'http' in event['requestContext'] and 'sourceIp' in event['requestContext']['http']:
                source_ip = event['requestContext']['http']['sourceIp']
                logger.info(f"Request from source IP: {source_ip}")
            
            result = process_pdf(file_id, source_ip)
            return create_response(200, result)
            
        else:
            # Invalid path
            return create_response(400, {
                'error': 'Invalid request path',
                'details': {
                    'received_path': path,
                    'parsed_resource': resource,
                    'valid_endpoints': ['/upload_url', '/process/<file_id>'],
                    'help': 'Make sure you are using one of the valid endpoints without any query parameters'
                }
            })
            
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            return create_response(404, {'error': 'PDF file not found'})
        else:
            logger.error(f"AWS error: {e}")
            return create_response(500, {'error': str(e)})
            
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return create_response(500, {'error': str(e)})