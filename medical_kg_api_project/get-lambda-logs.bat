@echo off
setlocal

:: =================================================================
:: Configuration
:: =================================================================
SET FUNCTION_NAME=SOCRMedicalKnowledgeGraphAPI
SET REGION=us-east-1
SET LOG_GROUP_NAME="/aws/lambda/%FUNCTION_NAME%"

echo 🚀 Fetching latest logs for %FUNCTION_NAME%...

:: Get the latest log stream
FOR /F "tokens=*" %%i IN ('aws logs describe-log-streams --log-group-name %LOG_GROUP_NAME% --region %REGION% --order-by LastEventTime --descending --max-items 1 --query "logStreams[0].logStreamName" --output text') DO (
    SET LATEST_LOG_STREAM=%%i
)

if not defined LATEST_LOG_STREAM (
    echo ❌ ERROR: Could not find any log streams for the function.
    echo    Has the function been invoked recently?
    exit /b 1
)

echo.
echo    [INFO] Found latest log stream: %LATEST_LOG_STREAM%
echo.

echo 📄 Displaying latest log events (most recent first):
echo ----------------------------------------------------
aws logs get-log-events ^
    --log-group-name %LOG_GROUP_NAME% ^
    --log-stream-name %LATEST_LOG_STREAM% ^
    --limit 25 ^
    --region %REGION% ^
    --query "events[*].message" --output text

echo ----------------------------------------------------

endlocal 