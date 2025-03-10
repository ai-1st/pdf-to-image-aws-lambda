# PDF to Image AWS Lambda

A serverless AWS Lambda function that converts PDF files to images. The function accepts PDF uploads, converts each page to an image (JPEG by default), and stores them in S3. It includes a web interface for easy testing and features path-based routing, caching of results, and source IP tagging.

## Features

- Convert PDF files to individual images (JPEG by default)
- Path-based API routing for better organization
- Caching of conversion results for improved performance
- Source IP tagging of uploaded images for tracking and analytics
- Web-based testing interface
- CORS-enabled for browser access
- Secure pre-signed URLs for direct S3 uploads
- Proper error handling and logging

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
│   ├── build_layer.sh       # Script to build Lambda layer with Poppler
│   └── requirements.txt      # Python dependencies
├── src
│   └── app.py               # Lambda function code
└── test_lambda.html         # Web testing interface
```

## API Endpoints

The Lambda function provides these endpoints through its Function URL:

1. **Get Upload URL** (`GET /upload_url`)
   - Returns a pre-signed URL for uploading PDF to S3
   - Response: `{ "uploadUrl": "...", "fileId": "..." }`

2. **Process PDF** (`GET /process/<file-id>`)
   - Converts the uploaded PDF to images
   - Response: `{ "fileId": "...", "imageUrls": ["...", "..."], "pageCount": N }`
   - The source IP of the request is automatically tagged to the uploaded images

## Image Processing and Caching

The function processes PDF files and converts them to images:
1. Each PDF page is converted to a JPEG image by default
2. Two versions of each image are created: main (full size) and preview (thumbnail)
3. Results are cached for faster retrieval on subsequent requests
4. Source IP of the requester is tagged to each uploaded image

## React Usage Example

Here's how to use the API in a React application:

```jsx
import { useState } from 'react';

const PdfConverter = () => {
  const [images, setImages] = useState([]);
  const [previews, setPreviews] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Replace with your Lambda Function URL
  const LAMBDA_URL = 'your-lambda-url-here';

  const handleFileChange = async (event) => {
    const file = event.target.files[0];
    if (!file || file.type !== 'application/pdf') {
      setError('Please select a PDF file');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      // Step 1: Get upload URL
      const urlResponse = await fetch(`${LAMBDA_URL}/upload_url`);
      if (!urlResponse.ok) throw new Error('Failed to get upload URL');
      const { uploadUrl, fileId } = await urlResponse.json();

      // Step 2: Upload PDF
      const uploadResponse = await fetch(uploadUrl, {
        method: 'PUT',
        body: file,
        headers: {
          'Content-Type': 'application/pdf'
        }
      });
      if (!uploadResponse.ok) throw new Error('Failed to upload PDF');

      // Step 3: Process PDF and get images
      await new Promise(resolve => setTimeout(resolve, 2000)); // Wait for S3 consistency
      const processResponse = await fetch(`${LAMBDA_URL}/process/${fileId}`);
      if (!processResponse.ok) throw new Error('Failed to process PDF');
      const { imageUrls, previewUrls } = await processResponse.json();

      setImages(imageUrls);
      setPreviews(previewUrls);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <input
        type="file"
        accept=".pdf"
        onChange={handleFileChange}
        disabled={loading}
      />
      
      {loading && <div>Converting PDF...</div>}
      {error && <div style={{ color: 'red' }}>{error}</div>}
      
      <div style={{ 
        display: 'grid', 
        gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
        gap: '1rem',
        padding: '1rem'
      }}>
        {previews.map((url, index) => (
          <a href={images[index]} target="_blank" rel="noopener noreferrer" key={url}>
            <img
              src={url}
              alt={`Page ${index + 1}`}
              style={{
                width: '100%',
                height: 'auto',
                boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
              }}
            />
          </a>
        ))}
      </div>
    </div>
  );
};

export default PdfConverter;
```

## Setup and Deployment

1. Install prerequisites:
   - AWS SAM CLI
   - Docker (for building the Lambda layer)
   - Git (for cloning the repository)

2. Clone this repository:
   ```bash
   git clone https://github.com/ai-1st/pdf-to-image-aws-lambda.git
   cd pdf-to-image-aws-lambda
   ```

3. Build the Lambda layer (see [Building the Lambda Layer](#building-the-lambda-layer) section for details):
   ```bash
   cd deps
   chmod +x build_layer.sh
   ./build_layer.sh
   cd ..
   ```

4. Deploy using SAM:
   ```bash
   sam build
   sam deploy --guided
   ```

## Building the Lambda Layer

Before deploying, you need to build the Lambda layer that contains Poppler and other dependencies. The layer is built using Docker to ensure compatibility with the Lambda environment.

### Prerequisites
- Docker installed and running
- AWS SAM CLI
- Bash shell

### Build Steps

1. Navigate to the `deps` directory:
   ```bash
   cd deps
   ```

2. Make the build script executable:
   ```bash
   chmod +x build_layer.sh
   ```

3. Run the build script:
   ```bash
   ./build_layer.sh
   ```

The script will:
- Create a Docker container based on the AWS Lambda Python 3.13 ARM64 image
- Install system packages including Poppler and its dependencies
- Install Python packages from requirements.txt
- Copy necessary binaries and shared libraries
- Create a layer directory with the correct structure
- Clean up temporary files

The resulting layer will be created in the `deps/layer` directory with the following structure:
```
layer/
├── bin/          # Poppler binaries (pdfinfo, pdftoppm, pdftocairo)
├── lib/          # Shared libraries
└── python/       # Python packages
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
