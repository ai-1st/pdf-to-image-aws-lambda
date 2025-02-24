#!/bin/bash
set -e

# Clean up any existing layer directory
rm -rf layer || true
rm -f libraries.txt || true

# Create a temporary Dockerfile for building the layer
cat > Dockerfile << 'EOF'
FROM public.ecr.aws/lambda/python:3.13-arm64

# Install system packages and dependencies
RUN dnf install -y \
    poppler \
    poppler-utils \
    zlib-devel \
    libjpeg-devel \
    freetype-devel \
    lcms2-devel \
    libwebp-devel \
    libpng-devel \
    openjpeg2-devel \
    openjpeg2 \
    nss \
    nss-util \
    nspr \
    harfbuzz \
    && dnf clean all

# Create directories
RUN mkdir -p /opt/python/lib/python3.13/site-packages/

# Copy requirements.txt
COPY requirements.txt .

# Install Python packages with pip
RUN pip install --platform manylinux_2_28_aarch64 --only-binary=:all: --target /opt/python/lib/python3.13/site-packages/ -r requirements.txt

# List all files in /usr/lib64 with symlink information
RUN echo "=== Shared Libraries in /usr/lib64 ===" > /tmp/libraries.txt && \
    echo "Format: [permissions] [links] [owner] [group] [size] [date] [name] -> [target if symlink]" >> /tmp/libraries.txt && \
    echo "--------------------------------------------------------------------------------" >> /tmp/libraries.txt && \
    ls -la /usr/lib64/*.so* >> /tmp/libraries.txt && \
    echo "--------------------------------------------------------------------------------" >> /tmp/libraries.txt

# Copy system libraries and binaries
RUN mkdir -p /opt/bin && \
    cp /usr/bin/pdfinfo /opt/bin/ && \
    cp /usr/bin/pdftoppm /opt/bin/ && \
    cp /usr/bin/pdftocairo /opt/bin/ && \
    mkdir -p /opt/lib && \
    cp -P /usr/lib64/libfreetype.so* /opt/lib/ && \
    cp -P /usr/lib64/libjpeg.so* /opt/lib/ && \
    cp -P /usr/lib64/libpng*.so* /opt/lib/ && \
    cp -P /usr/lib64/libtiff.so* /opt/lib/ && \
    cp -P /usr/lib64/libz.so* /opt/lib/ && \
    cp -P /usr/lib64/libfontconfig.so* /opt/lib/ && \
    cp -P /usr/lib64/liblcms2.so* /opt/lib/ && \
    cp -P /usr/lib64/libwebp.so* /opt/lib/ && \
    cp -P /usr/lib64/libopenjp*.so* /opt/lib/ && \
    cp -P /usr/lib64/libsmime3.so* /opt/lib/ && \
    cp -P /usr/lib64/libnss3.so* /opt/lib/ && \
    cp -P /usr/lib64/libnspr4.so* /opt/lib/ && \
    cp -P /usr/lib64/libnssutil3.so* /opt/lib/ && \
    cp -P /usr/lib64/libfreebl3.so* /opt/lib/ && \
    cp -P /usr/lib64/libsoftokn3.so* /opt/lib/ && \
    cp -P /usr/lib64/libsqlite3.so* /opt/lib/ && \
    cp -P /usr/lib64/libpoppler.so* /opt/lib/ && \
    cp -P /usr/lib64/libplc4.so* /opt/lib/ && \
    cp -P /usr/lib64/libplds4.so* /opt/lib/ && \
    cp -P /usr/lib64/libharfbuzz.so* /opt/lib/ && \
    cp -P /usr/lib64/libgraphite2.so* /opt/lib/ && \
    cp -P /usr/lib64/libbrotli*.so* /opt/lib/ && \
    cp -P /usr/lib64/libjbig.so* /opt/lib/ && \
    cp -P /usr/lib64/pkcs11/p11-kit-trust.so /opt/lib/libnssckbi.so 

# Clean up unnecessary files
RUN find /opt/python/lib/python3.13/site-packages -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true && \
    find /opt/python/lib/python3.13/site-packages -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

CMD ["/bin/bash"]
EOF

# Build the Docker image
docker build -t lambda-layer .

# Create a container and copy the files
docker create --name temp lambda-layer

# Create layer directory and copy files
mkdir -p layer
docker cp temp:/opt/python/. layer/python/
docker cp temp:/opt/bin/. layer/bin/
docker cp temp:/opt/lib/. layer/lib/
docker cp temp:/tmp/libraries.txt .

# Fix permissions
chmod -R 755 layer

# Clean up
docker rm temp
rm Dockerfile

echo "Layer has been built in the layer directory"
echo "Library list has been saved to libraries.txt"
