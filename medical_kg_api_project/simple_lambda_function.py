import json
import os
import urllib.request
import urllib.parse
import urllib.error

def lambda_handler(event, context):
    """
    Simplified Medical KB API that works without external dependencies
    """
    
    # Extract HTTP method and path
    http_method = event.get('requestContext', {}).get('http', {}).get('method', 'GET')
    path = event.get('rawPath', '/')
    query_params = event.get('queryStringParameters') or {}
    
    # CORS headers
    headers = {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type'
    }
    
    try:
        # Handle OPTIONS requests (CORS preflight)
        if http_method == 'OPTIONS':
            return {
                'statusCode': 200,
                'headers': headers,
                'body': json.dumps({'message': 'CORS preflight'})
            }
        
        # Health check endpoint
        if path == '/' and http_method == 'GET':
            return {
                'statusCode': 200,
                'headers': headers,
                'body': json.dumps({
                    'status': 'ok',
                    'version': '1.0.0-simplified',
                    'message': 'Medical Knowledge Graph API - Simplified Version',
                    'endpoints': [
                        'GET / - Health check',
                        'GET /test - Test endpoint',
                        'POST /query - Natural language query (placeholder)'
                    ]
                })
            }
        
        # Test endpoint
        elif path == '/test' and http_method == 'GET':
            return {
                'statusCode': 200,
                'headers': headers,
                'body': json.dumps({
                    'message': 'Test endpoint working!',
                    'environment_vars_available': {
                        'NEO4J_URL': bool(os.getenv('NEO4J_URL')),
                        'NEO4J_USERNAME': bool(os.getenv('NEO4J_USERNAME')),
                        'NEO4J_PASSWORD': bool(os.getenv('NEO4J_PASSWORD')),
                        'OPENAI_API_KEY': bool(os.getenv('OPENAI_API_KEY'))
                    }
                })
            }
        
        # Simple query endpoint placeholder
        elif path == '/query' and http_method == 'POST':
            try:
                body = json.loads(event.get('body', '{}'))
                question = body.get('question', 'No question provided')
                
                return {
                    'statusCode': 200,
                    'headers': headers,
                    'body': json.dumps({
                        'question': question,
                        'answer': 'This is a simplified version. The full Neo4j and OpenAI integration is available in the complete version.',
                        'note': 'To enable full functionality, deploy with proper dependencies.'
                    })
                }
            except json.JSONDecodeError:
                return {
                    'statusCode': 400,
                    'headers': headers,
                    'body': json.dumps({'error': 'Invalid JSON in request body'})
                }
        
        # Unknown endpoint
        else:
            return {
                'statusCode': 404,
                'headers': headers,
                'body': json.dumps({
                    'error': 'Endpoint not found',
                    'available_endpoints': ['/', '/test', '/query']
                })
            }
    
    except Exception as e:
        # Error handling
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps({
                'error': 'Internal server error',
                'details': str(e)
            })
        } 