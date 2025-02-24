# PDF to Image AWS Lambda

A serverless AWS Lambda function that converts PDF files to PNG images. The function accepts PDF uploads, converts each page to a PNG image, and stores them in S3. It includes a web interface for easy testing.

## Features

- Convert PDF files to individual PNG images
- Store images in S3 with organized structure (`s3://<bucket-name>/pages/<file-id>/page-N.png`)
- Web-based testing interface
- CORS-enabled for browser access
- Secure pre-signed URLs for direct S3 uploads

## Architecture

### AWS Components
- **AWS Lambda**: Handles PDF processing and image conversion
- **Amazon S3**: Stores uploaded PDFs and converted images
- **Lambda Function URL**: Provides HTTP endpoint for the function

### File Structure
```
.
├── README.md
├── template.yaml             # SAM template for AWS resources
├── deps
│   └── requirements.txt      # Python dependencies
├── src
│   └── app.py               # Lambda function code
└── test_lambda.html         # Web testing interface
```

## API Endpoints

The Lambda function provides these endpoints through its Function URL:

1. **Get Upload URL** (`GET /?type=get_upload_url`)
   - Returns a pre-signed URL for uploading PDF to S3
   - Response: `{ "uploadUrl": "...", "fileId": "..." }`

2. **Process PDF** (`GET /?type=process&fileId=<file-id>`)
   - Converts the uploaded PDF to images
   - Response: `{ "imageUrls": ["...", "..."] }`

## Setup and Deployment

1. Install AWS SAM CLI
2. Clone this repository
3. Deploy using SAM:
   ```bash
   sam build
   sam deploy --guided
   ```

## Testing

1. Open `test_lambda.html` in a web browser
2. Enter your Lambda Function URL
3. Upload a PDF file
4. View the converted images in the grid layout

## Dependencies

- Python 3.8+
- pdf2image
- boto3
- Poppler (installed in Lambda layer)

## Environment Variables

- `BUCKET_NAME`: S3 bucket name for file storage

## Security

- CORS enabled for browser access
- Pre-signed URLs for secure S3 uploads
- Public Lambda Function URL with CORS controls

## Error Handling

The function includes comprehensive error handling for:
- Invalid file types
- Failed conversions
- S3 upload/download issues
- CORS and pre-signed URL issues

## Contributing

Feel free to open issues or submit pull requests for improvements.

## License

MIT License
