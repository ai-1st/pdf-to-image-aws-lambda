.PHONY: build-layer clean-layer build-LambdaLayer clean

# Default target
all: build-layer

# Target expected by AWS SAM
build-LambdaLayer: build-layer
	@echo "Copying layer files to build directory..."
	mkdir -p $(ARTIFACTS_DIR)
	cp -r layer/* $(ARTIFACTS_DIR)/

# Build the Lambda layer
build-layer:
	@echo "Building Lambda layer..."
	./build_layer.sh

# Clean the Lambda layer
clean-layer:
	@echo "Cleaning Lambda layer..."
	rm -rf layer

# Clean all build artifacts
clean: clean-layer
	@echo "Cleaning all build artifacts..."
	rm -f libraries.txt
	rm -f Dockerfile
