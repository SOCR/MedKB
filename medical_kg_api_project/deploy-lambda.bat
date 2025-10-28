@echo off
setlocal enabledelayedexpansion

REM =================================================================
REM AWS Lambda Container Deployment Script
REM This script builds, pushes, and deploys your FastAPI app to AWS Lambda
REM =================================================================

echo Starting AWS Lambda deployment process...

REM Configuration Variables - MODIFY THESE VALUES
set AWS_ACCOUNT_ID=471112775480
set AWS_REGION=us-east-1
set ECR_REPO_NAME=medical-kg-api
set LAMBDA_FUNCTION_NAME=MedicalKnowledgeGraphAPI
set LAMBDA_ROLE_NAME=lambda-medical-kg-role

REM Environment Variables - HARDCODED VALUES
set NEO4J_URL=neo4j+s://762ccb39.databases.neo4j.io
set NEO4J_USERNAME=neo4j
set NEO4J_PASSWORD=cEI8uUJQ3o1ChpEtbSGfPujn4cKynxVv_Yj8iPAfZo8
set NEO4J_DATABASE=neo4j
set OPENAI_API_KEY=
REM Derived variables
set ECR_URI=%AWS_ACCOUNT_ID%.dkr.ecr.%AWS_REGION%.amazonaws.com
set FULL_IMAGE_URI=%ECR_URI%/%ECR_REPO_NAME%:latest

echo.
echo Configuration:
echo - AWS Account: %AWS_ACCOUNT_ID%
echo - Region: %AWS_REGION%
echo - ECR Repository: %ECR_REPO_NAME%
echo - Lambda Function: %LAMBDA_FUNCTION_NAME%
echo - Full Image URI: %FULL_IMAGE_URI%
echo.

pause

REM =================================================================
REM Step 1: Create ECR Repository
REM =================================================================
echo [STEP 1] Creating ECR repository...
aws ecr create-repository --repository-name %ECR_REPO_NAME% --region %AWS_REGION% 2>nul
if %errorlevel% equ 0 (
    echo ECR repository created successfully.
) else (
    echo ECR repository already exists or creation failed. Continuing...
)

REM =================================================================
REM Step 2: Docker Login to ECR
REM =================================================================
echo [STEP 2] Logging into ECR...
for /f "tokens=*" %%i in ('aws ecr get-login-password --region %AWS_REGION%') do set ECR_PASSWORD=%%i
echo %ECR_PASSWORD% | docker login --username AWS --password-stdin %ECR_URI%
if %errorlevel% neq 0 (
    echo ERROR: Failed to login to ECR
    pause
    exit /b 1
)
echo Successfully logged into ECR.

REM =================================================================
REM Step 3: Clean up and Build Docker Image
REM =================================================================
echo [STEP 3] Cleaning up existing images and building new Docker image...

REM Remove existing local images to avoid conflicts
docker rmi %ECR_REPO_NAME%:latest 2>nul
docker rmi %FULL_IMAGE_URI% 2>nul

REM Force remove all dangling images
docker image prune -f 2>nul

REM Build image with Docker manifest format (not OCI) for Lambda compatibility
set DOCKER_BUILDKIT=0
docker build -t %ECR_REPO_NAME% .
if %errorlevel% neq 0 (
    echo ERROR: Failed to build Docker image
    pause
    exit /b 1
)
echo Docker image built successfully.

REM Inspect the built image for debugging
echo [STEP 3.1] Inspecting Docker image architecture...
docker inspect %ECR_REPO_NAME%:latest --format="Architecture: {{.Architecture}}"
docker inspect %ECR_REPO_NAME%:latest --format="OS: {{.Os}}"
docker inspect %ECR_REPO_NAME%:latest --format="Platform: {{.Os}}/{{.Architecture}}"

REM =================================================================
REM Step 4: Tag and Push Image
REM =================================================================
echo [STEP 4] Tagging and pushing image to ECR...
docker tag %ECR_REPO_NAME%:latest %FULL_IMAGE_URI%
if %errorlevel% neq 0 (
    echo ERROR: Failed to tag image
    pause
    exit /b 1
)

docker push %FULL_IMAGE_URI%
if %errorlevel% neq 0 (
    echo ERROR: Failed to push image to ECR
    pause
    exit /b 1
)
echo Image pushed successfully to ECR.

REM =================================================================
REM Step 4.5: Verify image in ECR
REM =================================================================
echo [STEP 4.5] Verifying image exists in ECR...
aws ecr describe-images --repository-name %ECR_REPO_NAME% --region %AWS_REGION% --image-ids imageTag=latest
if %errorlevel% neq 0 (
    echo WARNING: Image verification failed. Continuing anyway...
) else (
    echo Image verified in ECR successfully.
)

REM =================================================================
REM Step 5: Create IAM Role and Policy
REM =================================================================
echo [STEP 5] Creating IAM role and policy...

REM Create trust policy file
echo { > trust-policy.json
echo   "Version": "2012-10-17", >> trust-policy.json
echo   "Statement": [ >> trust-policy.json
echo     { >> trust-policy.json
echo       "Effect": "Allow", >> trust-policy.json
echo       "Principal": { >> trust-policy.json
echo         "Service": "lambda.amazonaws.com" >> trust-policy.json
echo       }, >> trust-policy.json
echo       "Action": "sts:AssumeRole" >> trust-policy.json
echo     } >> trust-policy.json
echo   ] >> trust-policy.json
echo } >> trust-policy.json

REM Create the role
aws iam create-role --role-name %LAMBDA_ROLE_NAME% --assume-role-policy-document file://trust-policy.json 2>nul
if %errorlevel% equ 0 (
    echo IAM role created successfully.
) else (
    echo IAM role already exists or creation failed. Continuing...
)

REM Create permissions policy file
echo { > lambda-policy.json
echo   "Version": "2012-10-17", >> lambda-policy.json
echo   "Statement": [ >> lambda-policy.json
echo     { >> lambda-policy.json
echo       "Effect": "Allow", >> lambda-policy.json
echo       "Action": "logs:CreateLogGroup", >> lambda-policy.json
echo       "Resource": "arn:aws:logs:%AWS_REGION%:%AWS_ACCOUNT_ID%:*" >> lambda-policy.json
echo     }, >> lambda-policy.json
echo     { >> lambda-policy.json
echo       "Effect": "Allow", >> lambda-policy.json
echo       "Action": [ >> lambda-policy.json
echo         "logs:CreateLogStream", >> lambda-policy.json
echo         "logs:PutLogEvents" >> lambda-policy.json
echo       ], >> lambda-policy.json
echo       "Resource": [ >> lambda-policy.json
echo         "arn:aws:logs:%AWS_REGION%:%AWS_ACCOUNT_ID%:log-group:/aws/lambda/%LAMBDA_FUNCTION_NAME%:*" >> lambda-policy.json
echo       ] >> lambda-policy.json
echo     }, >> lambda-policy.json
echo     { >> lambda-policy.json
echo       "Effect": "Allow", >> lambda-policy.json
echo       "Action": [ >> lambda-policy.json
echo         "ecr:GetDownloadUrlForLayer", >> lambda-policy.json
echo         "ecr:BatchGetImage", >> lambda-policy.json
echo         "ecr:BatchCheckLayerAvailability" >> lambda-policy.json
echo       ], >> lambda-policy.json
echo       "Resource": [ >> lambda-policy.json
echo         "arn:aws:ecr:%AWS_REGION%:%AWS_ACCOUNT_ID%:repository/%ECR_REPO_NAME%" >> lambda-policy.json
echo       ] >> lambda-policy.json
echo     }, >> lambda-policy.json
echo     { >> lambda-policy.json
echo       "Effect": "Allow", >> lambda-policy.json
echo       "Action": [ >> lambda-policy.json
echo         "ecr:GetAuthorizationToken" >> lambda-policy.json
echo       ], >> lambda-policy.json
echo       "Resource": "*" >> lambda-policy.json
echo     } >> lambda-policy.json
echo   ] >> lambda-policy.json
echo } >> lambda-policy.json

REM Attach the policy
aws iam put-role-policy --role-name %LAMBDA_ROLE_NAME% --policy-name lambda-medical-kg-policy --policy-document file://lambda-policy.json
if %errorlevel% neq 0 (
    echo ERROR: Failed to attach policy to role
    pause
    exit /b 1
)
echo IAM policy attached successfully.

REM =================================================================
REM Step 6: Wait for role propagation and Create Lambda Function
REM =================================================================
echo [STEP 6] Creating Lambda function (waiting 10 seconds for role propagation)...
timeout /t 10 /nobreak > nul

aws lambda create-function ^
  --function-name %LAMBDA_FUNCTION_NAME% ^
  --role arn:aws:iam::%AWS_ACCOUNT_ID%:role/%LAMBDA_ROLE_NAME% ^
  --code ImageUri=%FULL_IMAGE_URI% ^
  --package-type Image ^
  --timeout 60 ^
  --memory-size 1024 ^
  --environment "Variables={NEO4J_URL=%NEO4J_URL%,NEO4J_USERNAME=%NEO4J_USERNAME%,NEO4J_PASSWORD=%NEO4J_PASSWORD%,NEO4J_DATABASE=%NEO4J_DATABASE%,OPENAI_API_KEY=%OPENAI_API_KEY%}" ^
  --region %AWS_REGION%

if %errorlevel% neq 0 (
    echo ERROR: Failed to create Lambda function
    echo Trying to update existing function instead...
    
    REM Try to update existing function
    aws lambda update-function-code ^
      --function-name %LAMBDA_FUNCTION_NAME% ^
      --image-uri %FULL_IMAGE_URI% ^
      --region %AWS_REGION%
    
    aws lambda update-function-configuration ^
      --function-name %LAMBDA_FUNCTION_NAME% ^
      --timeout 60 ^
      --memory-size 1024 ^
      --environment "Variables={NEO4J_URL=%NEO4J_URL%,NEO4J_USERNAME=%NEO4J_USERNAME%,NEO4J_PASSWORD=%NEO4J_PASSWORD%,NEO4J_DATABASE=%NEO4J_DATABASE%,OPENAI_API_KEY=%OPENAI_API_KEY%}" ^
      --region %AWS_REGION%
    
    if %errorlevel% neq 0 (
        echo ERROR: Failed to update Lambda function
        pause
        exit /b 1
    )
    echo Lambda function updated successfully.
) else (
    echo Lambda function created successfully.
)

REM =================================================================
REM Step 7: Create Function URL (for easy HTTP access)
REM =================================================================
echo [STEP 7] Creating Lambda Function URL...
aws lambda create-function-url-config ^
  --function-name %LAMBDA_FUNCTION_NAME% ^
  --auth-type NONE ^
  --cors AllowMethods=["*"],AllowOrigins=["*"],AllowHeaders=["*"] ^
  --region %AWS_REGION%

if %errorlevel% neq 0 (
    echo WARNING: Failed to create function URL (might already exist)
) else (
    echo Function URL created successfully.
)

REM =================================================================
REM Step 8: Get Function URL
REM =================================================================
echo [STEP 8] Getting Function URL...
for /f "tokens=2 delims=," %%i in ('aws lambda get-function-url-config --function-name %LAMBDA_FUNCTION_NAME% --region %AWS_REGION% --query "FunctionUrl" --output text 2^>nul') do set FUNCTION_URL=%%i

if defined FUNCTION_URL (
    echo.
    echo ===============================================
    echo DEPLOYMENT COMPLETED SUCCESSFULLY!
    echo ===============================================
    echo.
    echo Your API is available at:
    echo %FUNCTION_URL%
    echo.
    echo Test your API with:
    echo curl "%FUNCTION_URL%"
    echo curl "%FUNCTION_URL%search/nodes?q=diabetes"
    echo.
) else (
    echo.
    echo ===============================================
    echo DEPLOYMENT COMPLETED!
    echo ===============================================
    echo.
    echo Lambda function created successfully.
    echo You can test it in the AWS Console or create an API Gateway.
    echo.
)

REM Cleanup temporary files
del trust-policy.json 2>nul
del lambda-policy.json 2>nul

echo Press any key to exit...
pause >nul