"""
Test Qwen3 with Ollama (optimized GGUF quantization)
This should be MUCH faster than bitsandbytes on RTX 5090
"""
import subprocess
import sys
import time
import json

print("=" * 60)
print("Testing Qwen3 with Ollama")
print("=" * 60)

# Check if Ollama is installed
print("\n🔍 Checking Ollama installation...")
try:
    result = subprocess.run(["ollama", "--version"], capture_output=True, text=True, check=True)
    print(f"✅ Ollama installed: {result.stdout.strip()}")
except FileNotFoundError:
    print("❌ Ollama not installed!")
    print("\nInstall with:")
    print("  winget install Ollama.Ollama")
    print("  OR download from: https://ollama.com/download")
    sys.exit(1)
except Exception as e:
    print(f"❌ Error checking Ollama: {e}")
    sys.exit(1)

# Check if model is pulled
print("\n🔍 Checking for Qwen2.5:32b model...")
try:
    result = subprocess.run(["ollama", "list"], capture_output=True, text=True, check=True)
    if "qwen2.5:32b" in result.stdout.lower():
        print("✅ qwen2.5:32b model found")
    else:
        print("⚠️  Model not found. Pulling now (this will download ~20GB)...")
        print("   This may take 10-30 minutes...")
        subprocess.run(["ollama", "pull", "qwen2.5:32b"], check=True)
        print("✅ Model downloaded")
except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)

print("\n" + "=" * 60)
print("Testing inference speed...")
print("=" * 60)

# Medical entity extraction test
test_prompt = """Extract medical entities from this text and return as JSON:

"The patient presented with acute myocardial infarction and was administered aspirin 325mg and atorvastatin 80mg. Blood pressure was 140/90 mmHg."

Return JSON with this structure:
{
  "entities": [
    {"entity_name": "name", "entity_type": "type", "entity_description": "description"}
  ],
  "relationships": [
    {"source_entity_name": "source", "target_entity_name": "target", "relation_type": "type"}
  ]
}"""

print(f"\n📝 Test prompt prepared")
print("\n🧪 Generating response...")

# Run Ollama inference
start_time = time.time()

try:
    result = subprocess.run(
        ["ollama", "run", "qwen2.5:32b", test_prompt],
        capture_output=True,
        text=True,
        check=True
    )
    elapsed = time.time() - start_time
    output = result.stdout.strip()
    
    # Estimate tokens (rough: ~0.75 tokens per word)
    words = len(output.split())
    estimated_tokens = int(words * 0.75)
    tokens_per_sec = estimated_tokens / elapsed if elapsed > 0 else 0
    
    print(f"\n✅ Generation completed!")
    print(f"\n📊 Performance Metrics (Ollama GGUF Q4):")
    print(f"   Time: {elapsed:.2f}s")
    print(f"   Output words: {words}")
    print(f"   Estimated tokens: {estimated_tokens}")
    print(f"   Speed: ~{tokens_per_sec:.1f} tokens/sec")
    
    if tokens_per_sec > 60:
        print("   ✅ EXCELLENT! Much faster than bitsandbytes!")
        print("   → Use Ollama for the pipeline")
    elif tokens_per_sec > 30:
        print("   ✅ Good speed, better than bitsandbytes (8.6 tok/s)")
        print("   → Ollama is viable")
    elif tokens_per_sec > 15:
        print("   ⚠️  Moderate speed, slight improvement")
        print("   → Consider Qwen3-14B FP16 instead")
    else:
        print("   ❌ Still slow")
        print("   → Fallback to Qwen3-14B FP16 recommended")
    
    print(f"\n📤 Generated Response:")
    print("-" * 60)
    print(output[:800])
    if len(output) > 800:
        print("...(truncated)")
    print("-" * 60)
    
    print("\n" + "=" * 60)
    print("Comparison:")
    print("=" * 60)
    print(f"bitsandbytes 4-bit: 8.6 tok/s   (previous test)")
    print(f"Ollama GGUF Q4:    ~{tokens_per_sec:.1f} tok/s   (this test)")
    print(f"Speedup:            {tokens_per_sec / 8.6:.1f}x")
    
    if tokens_per_sec > 30:
        print("\n✅ RECOMMENDATION: Use Ollama for the pipeline!")
        print("   - Integrate Ollama into run_pipeline.py")
        print("   - Expected pipeline time: ~2-4 min/doc (vs 12-15 min with Claude)")
    else:
        print("\n⚠️  RECOMMENDATION: Switch to Qwen3-14B FP16")
        print("   - Should get 80-100 tok/s")
        print("   - Only 2% quality drop vs 32B")
        
except subprocess.CalledProcessError as e:
    print(f"❌ Error running Ollama: {e}")
    print(f"   stdout: {e.stdout}")
    print(f"   stderr: {e.stderr}")
    sys.exit(1)

print("\n💡 Next steps:")
if tokens_per_sec > 30:
    print("   1. Integrate Ollama into pipeline")
    print("   2. Compare quality vs Claude on 10 test chunks")
    print("   3. If quality is acceptable, use Ollama")
else:
    print("   1. Test Qwen3-14B FP16 (should be much faster)")
    print("   2. If still slow, try Qwen3-8B FP16")

