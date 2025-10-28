@echo off
echo 🚀 Building Medical KB Lambda Layer with Latest Versions...

REM Build the Docker image
echo 📦 Building Docker image...
docker build -f build_layer_latest.dockerfile -t medical-kb-layer-latest .

if %ERRORLEVEL% neq 0 (
    echo ❌ Docker build failed!
    exit /b 1
)

REM Create container and copy files
echo 📥 Extracting layer files...
docker create --name temp-layer-latest medical-kb-layer-latest
docker cp temp-layer-latest:/opt/layer ./layer_deps_latest

REM Cleanup container
docker rm temp-layer-latest

REM Create ZIP file
echo 📦 Creating layer ZIP...
cd layer_deps_latest
powershell -Command "Compress-Archive -Path python -DestinationPath ../medical-kb-layer-latest.zip -Force"
cd ..

REM Show file size
echo ✅ Layer created successfully!
for %%I in (medical-kb-layer-latest.zip) do echo 📏 Size: %%~zI bytes (%%~z0I)

echo 🎉 Latest layer ready: medical-kb-layer-latest.zip
echo 📋 Next steps:
echo    1. Upload this layer to AWS Lambda
echo    2. Update your Lambda function to use the new layer
echo    3. Test with the latest OpenAI v1.91.0 API! 