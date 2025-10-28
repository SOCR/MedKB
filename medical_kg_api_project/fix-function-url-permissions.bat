@echo off
setlocal enabledelayedexpansion

echo =================================================================
echo Fix Lambda Function URL Permissions
echo This will add the proper resource policy for public access
echo =================================================================

set LAMBDA_FUNCTION_NAME=MedicalKnowledgeGraphAPI
set AWS_REGION=us-east-1

echo [FIX 1] Adding resource-based policy for Function URL access...

REM Create the policy JSON
echo {> policy.json
echo   "Version": "2012-10-17",>> policy.json
echo   "Statement": [>> policy.json
echo     {>> policy.json
echo       "Effect": "Allow",>> policy.json
echo       "Principal": "*",>> policy.json
echo       "Action": "lambda:InvokeFunctionUrl",>> policy.json
echo       "Resource": "arn:aws:lambda:%AWS_REGION%:*:function:%LAMBDA_FUNCTION_NAME%",>> policy.json
echo       "Condition": {>> policy.json
echo         "StringEquals": {>> policy.json
echo           "lambda:FunctionUrlAuthType": "NONE">> policy.json
echo         }>> policy.json
echo       }>> policy.json
echo     }>> policy.json
echo   ]>> policy.json
echo }>> policy.json

echo Policy created. Adding to Lambda function...

aws lambda add-permission ^
  --function-name %LAMBDA_FUNCTION_NAME% ^
  --statement-id FunctionURLAllowPublicAccess ^
  --action lambda:InvokeFunctionUrl ^
  --principal "*" ^
  --function-url-auth-type NONE ^
  --region %AWS_REGION%

if %errorlevel% neq 0 (
    echo Note: Permission might already exist or there was an error
) else (
    echo Permission added successfully
)

echo.
echo [FIX 2] Checking current permissions...
aws lambda get-policy --function-name %LAMBDA_FUNCTION_NAME% --region %AWS_REGION% 2>nul || echo "No policy found (this might be normal)"

echo.
echo [FIX 3] Testing Function URL again...
echo Waiting 10 seconds for permission propagation...
timeout /t 10 /nobreak > nul

echo Testing Function URL:
curl https://f665vdcspxn2lkyed55jnaz6oi0pfxjv.lambda-url.us-east-1.on.aws/

echo.
echo =================================================================
echo PERMISSIONS FIX COMPLETED
echo =================================================================
echo.
echo If you still get 403 errors, the issue might be:
echo 1. Permission propagation delay (wait a few more minutes)
echo 2. Function not working internally (check CloudWatch logs)
echo 3. Need to recreate the Function URL entirely
echo.

echo Cleaning up...
del policy.json 2>nul

pause 