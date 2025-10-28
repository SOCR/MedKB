import os
from dotenv import load_dotenv
import openai

# Load environment variables from .env file
load_dotenv()

def test_openai_initialization():
    """Test OpenAI client initialization."""
    print("=" * 60)
    print("🔬 TESTING: OpenAI Client Initialization")
    print("=" * 60)
    
    # Get API key from environment
    api_key = os.getenv("OPENAI_API_KEY")
    print(f"✅ API Key loaded: {'Yes' if api_key else 'No'}")
    print(f"✅ API Key length: {len(api_key) if api_key else 0}")
    print(f"✅ API Key prefix: {api_key[:10] + '...' if api_key else 'None'}")
    
    # Check OpenAI version
    print(f"✅ OpenAI library version: {openai.__version__}")
    
    # Test client initialization (matching Lambda approach)
    try:
        # Set environment variable (as done in Lambda)
        os.environ["OPENAI_API_KEY"] = api_key
        
        # Official initialization method
        from openai import OpenAI
        client = OpenAI()
        print("✅ OpenAI client initialized successfully!")
        return client
    except Exception as e:
        print(f"❌ OpenAI client initialization failed: {e}")
        print(f"❌ Exception type: {type(e)}")
        return None

def test_simple_chat(client):
    """Test a simple chat completion."""
    print("\n" + "=" * 60)
    print("🔬 TESTING: Simple Chat Completion")
    print("=" * 60)
    
    if not client:
        print("❌ SKIPPED: No client available")
        return
    
    try:
        response = client.chat.completions.create(
            model="gpt-4.1",
            messages=[
                {"role": "user", "content": "Say hello in one word."}
            ],
            temperature=0
        )
        
        print("✅ Chat completion successful!")
        print(f"✅ Response: {response.choices[0].message.content}")
        print(f"✅ Model used: {response.model}")
        print(f"✅ Total tokens: {response.usage.total_tokens}")
        return True
        
    except Exception as e:
        print(f"❌ Chat completion failed: {e}")
        print(f"❌ Exception type: {type(e)}")
        
        # Try with gpt-4o as fallback
        try:
            print("\n🔄 Trying with gpt-4o as fallback...")
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "user", "content": "Say hello in one word."}
                ],
                temperature=0
            )
            
            print("✅ Chat completion with gpt-4o successful!")
            print(f"✅ Response: {response.choices[0].message.content}")
            print(f"✅ Model used: {response.model}")
            return True
            
        except Exception as e2:
            print(f"❌ Fallback also failed: {e2}")
            return False

def test_cypher_generation(client):
    """Test Cypher query generation (matching Lambda function)."""
    print("\n" + "=" * 60)
    print("🔬 TESTING: Cypher Query Generation")
    print("=" * 60)
    
    if not client:
        print("❌ SKIPPED: No client available")
        return
    
    prompt = """
Task: Generate a Cypher statement to query a graph database.
Instructions:
1. Use only the provided relationship types and properties in the schema.
2. For all string property checks, use `toLower()` for case-insensitive matching.
3. Use non-directional relationships like `-[r]-`.
4. Return name and description of nodes and relationships.
5. Return ONLY the Cypher statement, no explanations.

Schema:
Node labels: Disease, Symptom, Medication, Treatment
Relationships: HAS_SYMPTOM, TREATED_BY, INTERACTS_WITH
Properties: name, description, uuid

Question: What are the symptoms of Migraine?
"""

    try:
        # Try gpt-4.1 first
        response = client.chat.completions.create(
            model="gpt-4.1",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        
        cypher_query = response.choices[0].message.content.strip()
        print("✅ Cypher generation successful!")
        print(f"✅ Generated Cypher:\n{cypher_query}")
        print(f"✅ Model used: {response.model}")
        return True
        
    except Exception as e:
        print(f"❌ Cypher generation failed with gpt-4.1: {e}")
        
        # Try fallback to gpt-4o
        try:
            print("\n🔄 Trying with gpt-4o...")
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                temperature=0
            )
            
            cypher_query = response.choices[0].message.content.strip()
            print("✅ Cypher generation with gpt-4o successful!")
            print(f"✅ Generated Cypher:\n{cypher_query}")
            print(f"✅ Model used: {response.model}")
            return True
            
        except Exception as e2:
            print(f"❌ Fallback cypher generation also failed: {e2}")
            return False

def test_synonym_generation(client):
    """Test synonym generation (matching Lambda function)."""
    print("\n" + "=" * 60)
    print("🔬 TESTING: Synonym Generation")
    print("=" * 60)
    
    if not client:
        print("❌ SKIPPED: No client available")
        return
    
    query = "hypertension"
    prompt = f"""
You are an expert in medical terminology. Generate synonyms and related keywords for this medical term.
Include the original term, common names, scientific names, and abbreviations.
Return terms separated by '^' symbol.

Example:
QUERY: high blood pressure  
KEYWORDS: Hypertension^HBP^High blood pressure

QUERY: {query}
KEYWORDS:
"""

    try:
        # Try gpt-4.1 first
        response = client.chat.completions.create(
            model="gpt-4.1", 
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        
        keywords = response.choices[0].message.content.strip()
        keyword_list = [k.strip() for k in keywords.split("^") if k.strip()]
        
        print("✅ Synonym generation successful!")
        print(f"✅ Generated keywords: {keyword_list}")
        print(f"✅ Model used: {response.model}")
        return True
        
    except Exception as e:
        print(f"❌ Synonym generation failed with gpt-4.1: {e}")
        
        # Try fallback to gpt-4o
        try:
            print("\n🔄 Trying with gpt-4o...")
            response = client.chat.completions.create(
                model="gpt-4o", 
                messages=[{"role": "user", "content": prompt}],
                temperature=0
            )
            
            keywords = response.choices[0].message.content.strip()
            keyword_list = [k.strip() for k in keywords.split("^") if k.strip()]
            
            print("✅ Synonym generation with gpt-4o successful!")
            print(f"✅ Generated keywords: {keyword_list}")
            print(f"✅ Model used: {response.model}")
            return True
            
        except Exception as e2:
            print(f"❌ Fallback synonym generation also failed: {e2}")
            return False

def main():
    """Run all OpenAI tests."""
    print("🚀 STARTING LOCAL OPENAI TESTS 🚀")
    
    # Test 1: Client initialization
    client = test_openai_initialization()
    
    if not client:
        print("\n❌ Cannot proceed with further tests - client initialization failed")
        return
    
    # Test 2: Simple chat
    simple_success = test_simple_chat(client)
    
    # Test 3: Cypher generation (medical KB use case)
    cypher_success = test_cypher_generation(client)
    
    # Test 4: Synonym generation (medical KB use case)
    synonym_success = test_synonym_generation(client)
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)
    print(f"✅ Client initialization: {'PASS' if client else 'FAIL'}")
    print(f"✅ Simple chat: {'PASS' if simple_success else 'FAIL'}")
    print(f"✅ Cypher generation: {'PASS' if cypher_success else 'FAIL'}")
    print(f"✅ Synonym generation: {'PASS' if synonym_success else 'FAIL'}")
    
    if all([client, simple_success, cypher_success, synonym_success]):
        print("\n🎉 ALL TESTS PASSED! OpenAI integration is working locally.")
        print("💡 The issue is likely in the Lambda environment or function configuration.")
    else:
        print("\n⚠️  Some tests failed. Check the errors above for debugging.")

if __name__ == "__main__":
    main() 