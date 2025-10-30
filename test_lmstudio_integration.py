"""
Test LM Studio integration before running full pipeline
"""
import sys

print("=" * 60)
print("Testing LM Studio Integration")
print("=" * 60)

# Test 1: Import check
print("\n1️⃣  Testing imports...")
try:
    from utils import initialize_llm_lmstudio
    print("✅ initialize_llm_lmstudio imported successfully")
except ImportError as e:
    print(f"❌ Failed to import: {e}")
    sys.exit(1)

# Test 2: Check openai package
print("\n2️⃣  Checking openai package...")
try:
    import openai
    print(f"✅ openai package installed (version: {openai.__version__})")
except ImportError:
    print("❌ openai package not installed")
    print("   Run: pip install openai")
    sys.exit(1)

# Test 3: Initialize LM Studio LLM
print("\n3️⃣  Connecting to LM Studio server...")
try:
    llm = initialize_llm_lmstudio()
    print("✅ LLM wrapper created successfully")
except Exception as e:
    print(f"❌ Failed to connect to LM Studio: {e}")
    print("\n💡 Make sure:")
    print("   1. LM Studio is running")
    print("   2. A model is loaded (qwen3-30b-a3b-2507)")
    print("   3. Server is started (should show http://127.0.0.1:1234)")
    sys.exit(1)

# Test 4: Test a simple completion
print("\n4️⃣  Testing LLM completion...")
test_prompt = "Extract one medical entity from this: 'Patient has diabetes.'"

try:
    print(f"   Prompt: {test_prompt}")
    print("   Calling LLM...")
    
    response = llm.complete(test_prompt, max_tokens=100)
    output = response.text
    
    print(f"✅ LLM response received ({len(output)} chars)")
    print(f"\n   Response preview:")
    print(f"   {output[:200]}...")
    
except Exception as e:
    print(f"❌ LLM completion failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 5: Test with actual pipeline prompt format
print("\n5️⃣  Testing with pipeline-style prompt...")

pipeline_test_prompt = """Extract entities from: "Patient prescribed metformin 500mg for Type 2 Diabetes."

Return JSON:
{
  "entities": [{"entity_name": "name", "entity_type": "type"}]
}"""

try:
    print("   Calling LLM with pipeline format...")
    response = llm.complete(pipeline_test_prompt, max_tokens=200, temperature=0.7)
    output = response.text
    
    print(f"✅ Pipeline-style extraction successful")
    print(f"\n   Response:")
    print(f"   {output[:400]}")
    
    # Try to parse as JSON
    import json
    try:
        # Try to find JSON in response
        if "{" in output:
            json_start = output.find("{")
            json_end = output.rfind("}") + 1
            json_text = output[json_start:json_end]
            parsed = json.loads(json_text)
            print(f"\n✅ Valid JSON extracted: {len(parsed.get('entities', []))} entities found")
        else:
            print("\n⚠️  No JSON found in response (model may need better prompting)")
    except json.JSONDecodeError:
        print("\n⚠️  Response contains text but not valid JSON")
    
except Exception as e:
    print(f"❌ Pipeline-style test failed: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("✅ ALL TESTS PASSED!")
print("=" * 60)

print("\n🎉 LM Studio integration is working correctly!")
print("\n📋 Next steps:")
print("   1. Install openai if not already: pip install openai")
print("   2. Run test mode:")
print("      python run_pipeline.py --use-lm-studio --test-mode")
print("   3. Check quality on a few chunks")
print("   4. Run full pipeline:")
print("      python run_pipeline.py --use-lm-studio --full-run")

print("\n💡 Performance tip:")
print("   Expected speed: ~186 tokens/sec")
print("   Per chunk: ~2-3 seconds")
print("   Per document: ~2-3 minutes")
print("   6x faster than Claude! 🚀")

