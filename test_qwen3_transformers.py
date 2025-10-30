"""
Test Qwen3-32B with transformers library
"""
import sys
import time
from pathlib import Path

print("=" * 60)
print("Testing Qwen3-32B with transformers...")
print("=" * 60)

# Test 1: Check dependencies
try:
    import torch
    print(f"✅ PyTorch {torch.__version__}")
    print(f"✅ CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"   GPU: {torch.cuda.get_device_name(0)}")
        print(f"   VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
except ImportError:
    print("❌ PyTorch not installed")
    sys.exit(1)

try:
    import transformers
    print(f"✅ transformers {transformers.__version__}")
    if transformers.__version__ < "4.51.0":
        print("⚠️  WARNING: transformers < 4.51.0 detected")
        print("   Upgrading to support Qwen3...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "--upgrade", "transformers"])
        print("✅ transformers upgraded")
except ImportError:
    print("❌ transformers not installed")
    sys.exit(1)

# Check for quantization libraries
try:
    import bitsandbytes
    has_bnb = True
    print(f"✅ bitsandbytes (for 4-bit quantization)")
except ImportError:
    has_bnb = False
    print("⚠️  bitsandbytes not installed (will use fp16 - requires more VRAM)")

try:
    import accelerate
    print(f"✅ accelerate")
except ImportError:
    print("⚠️  accelerate not installed (installing...)")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "accelerate"])
    print("✅ accelerate installed")

print("\n" + "=" * 60)
print("Loading Qwen3-32B model...")
print("=" * 60)

from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

model_name = "Qwen/Qwen3-32B"

# Load tokenizer
print(f"\n🔄 Loading tokenizer from {model_name}...")
tokenizer = AutoTokenizer.from_pretrained(model_name)
print("✅ Tokenizer loaded")

# Load model with 4-bit quantization
print(f"\n🔄 Loading model (4-bit quantized)...")
print("   This will download ~20GB and take 5-10 minutes on first run...")

if has_bnb:
    # Use 4-bit quantization to save VRAM
    quantization_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
        bnb_4bit_quant_type="nf4"
    )
    
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        quantization_config=quantization_config,
        device_map="auto",
        trust_remote_code=True
    )
    print("✅ Model loaded with 4-bit quantization")
else:
    # Fallback to fp16 (uses more VRAM)
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        torch_dtype=torch.float16,
        device_map="auto",
        trust_remote_code=True
    )
    print("✅ Model loaded with fp16 (no quantization)")

# Check VRAM usage
if torch.cuda.is_available():
    vram_used = torch.cuda.memory_allocated(0) / 1024**3
    vram_reserved = torch.cuda.memory_reserved(0) / 1024**3
    print(f"\n📊 VRAM Usage:")
    print(f"   Allocated: {vram_used:.2f} GB")
    print(f"   Reserved: {vram_reserved:.2f} GB")

print("\n" + "=" * 60)
print("Testing inference (Medical Entity Extraction)...")
print("=" * 60)

# Test medical entity extraction
test_prompt = """Extract medical entities from this text and return as JSON:

"The patient presented with acute myocardial infarction and was administered aspirin 325mg and atorvastatin 80mg. Blood pressure was 140/90 mmHg. ECG showed ST-segment elevation."

Return JSON with this structure:
{
  "entities": [
    {
      "entity_name": "name",
      "entity_type": "type",
      "entity_description": "description"
    }
  ],
  "relationships": [
    {
      "source_entity_name": "source",
      "target_entity_name": "target",
      "relation_type": "type",
      "relationship_description": "description"
    }
  ]
}"""

# Prepare chat template (disable thinking mode for faster response)
messages = [{"role": "user", "content": test_prompt}]

text = tokenizer.apply_chat_template(
    messages,
    tokenize=False,
    add_generation_prompt=True,
    enable_thinking=False  # Disable thinking for entity extraction (faster)
)

print(f"\n📝 Prompt prepared ({len(text)} chars)")
print("\n🧪 Generating response...")

# Tokenize
model_inputs = tokenizer([text], return_tensors="pt").to(model.device)
input_length = model_inputs.input_ids.shape[1]

print(f"   Input tokens: {input_length}")

# Generate
start_time = time.time()

with torch.no_grad():
    generated_ids = model.generate(
        **model_inputs,
        max_new_tokens=2048,
        temperature=0.7,
        top_p=0.8,
        top_k=20,
        do_sample=True,
        pad_token_id=tokenizer.pad_token_id,
        eos_token_id=tokenizer.eos_token_id
    )

elapsed = time.time() - start_time

# Decode output
output_ids = generated_ids[0][input_length:].tolist()
content = tokenizer.decode(output_ids, skip_special_tokens=True).strip()

# Calculate metrics
output_tokens = len(output_ids)
tokens_per_sec = output_tokens / elapsed

print(f"\n✅ Generation completed!")
print(f"\n📊 Performance Metrics:")
print(f"   Time: {elapsed:.2f}s")
print(f"   Output tokens: {output_tokens}")
print(f"   Speed: {tokens_per_sec:.1f} tokens/sec")

if tokens_per_sec > 60:
    print("   ✅ Excellent speed (GPU acceleration working!)")
elif tokens_per_sec > 30:
    print("   ✅ Good speed")
else:
    print("   ⚠️  Slow - check GPU usage")

print(f"\n📤 Generated Response:")
print("-" * 60)
print(content[:1000])  # Print first 1000 chars
if len(content) > 1000:
    print("...(truncated)")
print("-" * 60)

print("\n" + "=" * 60)
print("🎉 All tests passed! Qwen3-32B is ready to use.")
print("=" * 60)

print("\n💡 Next steps:")
print("   1. Compare this vs Claude Bedrock quality")
print("   2. Integrate into run_pipeline.py with --use-local-llm flag")
print("   3. Run on test data to compare speed and accuracy")

print(f"\n⚡ Expected pipeline speedup:")
print(f"   Current (Claude): ~10-15s per chunk")
print(f"   With Qwen3: ~{elapsed/1.5:.1f}s per chunk (estimated)")
print(f"   Speedup: ~{(12.5 / (elapsed/1.5)):.1f}x")

