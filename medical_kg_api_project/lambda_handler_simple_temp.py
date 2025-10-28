import json
import os

def lambda_handler(event, context):
    """
    Temporary handler that works without dependencies
    """
    
    # Extract HTTP method and path
    http_method = event.get('requestContext', {}).get('http', {}).get('method', 'GET')
    path = event.get('rawPath', '/')
    
    # CORS headers
    headers = {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type'
    }
    
    try:
        # Health check endpoint
        if path == '/' and http_method == 'GET':
            return {
                'statusCode': 200,
                'headers': headers,
                'body': json.dumps({
                    'status': 'ok',
                    'version': '1.0.0-temp',
                    'message': 'Medical Knowledge Graph API - Working!',
                    'environment_check': {
                        'NEO4J_URL': bool(os.getenv('NEO4J_URL')),
                        'OPENAI_API_KEY': bool(os.getenv('OPENAI_API_KEY'))
                    },
                    'next_step': 'Add the custom layer to enable full functionality'
                })
            }
        
        # Test endpoint
        elif path == '/test' and http_method == 'GET':
            return {
                'statusCode': 200,
                'headers': headers,
                'body': json.dumps({
                    'message': 'Lambda function is working!',
                    'cold_start_time': 'Very fast without heavy dependencies'
                })
            }
        
        else:
            return {
                'statusCode': 404,
                'headers': headers,
                'body': json.dumps({'error': 'Endpoint not found'})
            }
    
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps({'error': str(e)})
        } 