@echo off
setlocal enabledelayedexpansion

echo =================================================================
echo Fix Lambda Function URL Script
echo This will recreate the Function URL with proper settings
echo =================================================================

set LAMBDA_FUNCTION_NAME=MedicalKnowledgeGraphAPI
set AWS_REGION=us-east-1

echo [FIX 1] Deleting existing Function URL...
aws lambda delete-function-url-config --function-name %LAMBDA_FUNCTION_NAME% --region %AWS_REGION% 2>nul
echo Function URL deleted (if it existed)

echo.
echo [FIX 2] Creating new Function URL with proper configuration...
aws lambda create-function-url-config ^
  --function-name %LAMBDA_FUNCTION_NAME% ^
  --auth-type NONE ^
  --cors "AllowMethods=[\"*\"],AllowOrigins=[\"*\"],AllowHeaders=[\"*\"],MaxAge=300" ^
  --region %AWS_REGION%

if %errorlevel% neq 0 (
    echo ERROR: Failed to create Function URL
    pause
    exit /b 1
)

echo.
echo [FIX 3] Getting new Function URL...
for /f "tokens=*" %%i in ('aws lambda get-function-url-config --function-name %LAMBDA_FUNCTION_NAME% --region %AWS_REGION% --query "FunctionUrl" --output text') do set NEW_FUNCTION_URL=%%i

echo.
echo ===============================================
echo FUNCTION URL RECREATED SUCCESSFULLY!
echo ===============================================
echo.
echo Your new API URL is:
echo %NEW_FUNCTION_URL%
echo.
echo Test it with:
echo curl "%NEW_FUNCTION_URL%"
echo curl "%NEW_FUNCTION_URL%search/nodes?q=diabetes"
echo.

pause 