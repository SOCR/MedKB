@echo off
setlocal

:: =================================================================
:: Configuration
:: =================================================================
SET FUNCTION_NAME=SOCRMedicalKnowledgeGraphAPI
SET REGION=us-east-1
SET TIMEOUT_SECONDS=30
SET MEMORY_MB=1024

echo 🚀 Updating Lambda function configuration for %FUNCTION_NAME%...

echo.
echo    [INFO] New Timeout: %TIMEOUT_SECONDS% seconds
echo    [INFO] New Memory:  %MEMORY_MB% MB
echo.

aws lambda update-function-configuration ^
    --function-name %FUNCTION_NAME% ^
    --region %REGION% ^
    --timeout %TIMEOUT_SECONDS% ^
    --memory-size %MEMORY_MB%

if %ERRORLEVEL% neq 0 (
    echo ❌ ERROR: Failed to update Lambda configuration.
    echo    Please check your AWS CLI setup and permissions.
    exit /b 1
)

echo.
echo ✅ Lambda function configuration updated successfully!
echo.
echo 💡 Please wait a minute for the changes to apply, then test the endpoints again.

endlocal 