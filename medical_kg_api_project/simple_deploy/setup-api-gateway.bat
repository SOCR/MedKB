@echo off
echo Setting up API Gateway for Medical-KG-API-Simple...

REM Create HTTP API
echo Creating HTTP API...
for /f "tokens=*" %%i in ('aws apigatewayv2 create-api --name "Medical-KG-API" --protocol-type HTTP --query "ApiId" --output text') do set API_ID=%%i
echo API ID: %API_ID%

REM Get Lambda function ARN
echo Getting Lambda function ARN...
for /f "tokens=*" %%i in ('aws lambda get-function --function-name Medical-KG-API-Simple --query "Configuration.FunctionArn" --output text') do set LAMBDA_ARN=%%i
echo Lambda ARN: %LAMBDA_ARN%

REM Create integration
echo Creating integration...
for /f "tokens=*" %%i in ('aws apigatewayv2 create-integration --api-id %API_ID% --integration-type AWS_PROXY --integration-uri %LAMBDA_ARN% --payload-format-version "2.0" --query "IntegrationId" --output text') do set INTEGRATION_ID=%%i
echo Integration ID: %INTEGRATION_ID%

REM Create catch-all route
echo Creating routes...
aws apigatewayv2 create-route --api-id %API_ID% --route-key "ANY /{proxy+}" --target "integrations/%INTEGRATION_ID%"
aws apigatewayv2 create-route --api-id %API_ID% --route-key "ANY /" --target "integrations/%INTEGRATION_ID%"

REM Create default stage
echo Creating stage...
aws apigatewayv2 create-stage --api-id %API_ID% --stage-name "default" --auto-deploy

REM Add Lambda permission for API Gateway
echo Adding Lambda permission...
aws lambda add-permission --function-name Medical-KG-API-Simple --statement-id apigateway-invoke --action lambda:InvokeFunction --principal apigateway.amazonaws.com --source-arn "arn:aws:execute-api:us-east-1:*:%API_ID%/*/*"

REM Get the API endpoint
echo.
echo API Gateway setup complete!
echo API Endpoint: https://%API_ID%.execute-api.us-east-1.amazonaws.com/default
echo.
echo Test your API with:
echo curl -X POST https://%API_ID%.execute-api.us-east-1.amazonaws.com/default/query -H "Content-Type: application/json" -d "{\"question\": \"What is diabetes?\"}"
echo.
pause 