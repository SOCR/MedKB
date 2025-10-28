@echo off
echo =================================================================
echo DEPLOYING SIMPLIFIED MEDICAL KB API (ZIP DEPLOYMENT - FIXED)
echo =================================================================

REM Set function name and environment variables
set FUNCTION_NAME=medical-kb-api-simple
set AWS_ACCOUNT_ID=471112775480
set NEO4J_URL=neo4j+s://762ccb39.databases.neo4j.io
set NEO4J_USERNAME=neo4j
set NEO4J_PASSWORD=cEI8uUJQ3o1ChpEtbSGfPujn4cKynxVv_Yj8iPAfZo8
set OPENAI_API_KEY=

echo [1] Creating deployment package...
if exist deployment rmdir /s /q deployment
mkdir deployment

REM Copy application files
copy main_simple.py deployment\
copy lambda_handler_simple.py deployment\

REM Create a requirements file with specific versions that work well in Lambda
echo [2] Creating compatible requirements...
echo fastapi==0.104.1 > deployment\requirements.txt
echo mangum==0.17.0 >> deployment\requirements.txt
echo neo4j==5.15.0 >> deployment\requirements.txt
echo openai==1.3.8 >> deployment\requirements.txt
echo pydantic==2.5.0 >> deployment\requirements.txt
echo starlette==0.27.0 >> deployment\requirements.txt
echo uvicorn==0.24.0 >> deployment\requirements.txt

REM Install dependencies in deployment folder
echo [3] Installing dependencies...
cd deployment
pip install -r requirements.txt -t .
cd ..

REM Create deployment zip
echo [4] Creating deployment zip...
cd deployment
powershell -Command "Compress-Archive -Path * -DestinationPath ..\deployment.zip -Force"
cd ..

echo [5] Deploying Lambda function...
aws lambda delete-function --function-name %FUNCTION_NAME% 2>nul

aws lambda create-function ^
    --function-name %FUNCTION_NAME% ^
    --runtime python3.11 ^
    --role arn:aws:iam::%AWS_ACCOUNT_ID%:role/lambda-execution-role ^
    --handler lambda_handler_simple.lambda_handler ^
    --zip-file fileb://deployment.zip ^
    --timeout 30 ^
    --memory-size 512 ^
    --environment Variables="{NEO4J_URL=%NEO4J_URL%,NEO4J_USERNAME=%NEO4J_USERNAME%,NEO4J_PASSWORD=%NEO4J_PASSWORD%,OPENAI_API_KEY=%OPENAI_API_KEY%}"

if %ERRORLEVEL% neq 0 (
    echo ERROR: Failed to create Lambda function
    pause
    exit /b 1
)

echo [5a] Creating Function URL...
aws lambda create-function-url-config ^
    --function-name %FUNCTION_NAME% ^
    --auth-type NONE ^
    --cors AllowCredentials=false,AllowHeaders=*,AllowMethods=*,AllowOrigins=*

echo [5b] Adding Function URL permissions...
aws lambda add-permission ^
    --function-name %FUNCTION_NAME% ^
    --statement-id FunctionURLAllowPublicAccess ^
    --action lambda:InvokeFunctionUrl ^
    --principal "*" ^
    --function-url-auth-type NONE

echo [6] Testing API...
timeout /t 5 /nobreak >nul
for /f "tokens=*" %%i in ('aws lambda get-function-url-config --function-name %FUNCTION_NAME% --query "FunctionUrl" --output text') do set FUNCTION_URL=%%i

echo =================================================================
echo DEPLOYMENT COMPLETED SUCCESSFULLY
echo =================================================================
echo Function Name: %FUNCTION_NAME%
echo Function URL: %FUNCTION_URL%
echo =================================================================
echo Testing API...
curl -s "%FUNCTION_URL%" | echo.

echo Cleaning up...
rmdir /s /q deployment
del deployment.zip

pause 