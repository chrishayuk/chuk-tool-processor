.PHONY: clean test run build publish

# Remove Python bytecode, __pycache__ directories, and build artifacts.
clean:
	@echo "Cleaning project..."
	@find . -type f -name '*.pyc' -delete
	@find . -type d -name '__pycache__' -delete
	@rm -rf build/ dist/ *.egg-info
	@echo "Clean complete."

# Run the server launcher.
run:
	@echo "Running server..."
	PYTHONPATH=src python3 -m chuk_protocol_server.server_launcher

# Build the project using the pyproject.toml configuration.
build:
	@echo "Building project..."
	python3 -m build
	@echo "Build complete. Distributions are in the 'dist' folder."

# Publish the package to PyPI using twine.
# This target uploads only the most recent artifact in the 'dist' folder.
publish: build
	@echo "Publishing package..."
	@last_build=$$(ls -t dist/* | head -n 1); \
	echo "Uploading $$last_build"; \
	twine upload $$last_build
	@echo "Publish complete."