"""
Test Qwen3-14B with FP16 (should fit entirely in 31.8GB VRAM)
This is the recommended fallback if Ollama 32B is still slow
"""
import sys
import time
import torch

print("=" * 60)
print("Testing Qwen3-14B with FP16...")
print("=" * 60)

# Check PyTorch and CUDA
print(f"✅ PyTorch {torch.__version__}")
print(f"✅ CUDA available: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"   GPU: {torch.cuda.get_device_name(0)}")
    print(f"   VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")

print("\n" + "=" * 60)
print("Loading Qwen3-14B model (FP16)...")
print("=" * 60)

from transformers import AutoModelForCausalLM, AutoTokenizer

model_name = "Qwen/Qwen3-14B"

# Load tokenizer
print(f"\n🔄 Loading tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(model_name)
print("✅ Tokenizer loaded")

# Load model with FP16 (should fit entirely in VRAM)
print(f"\n🔄 Loading model (FP16)...")
print("   This will use ~14-16GB VRAM (plenty of room in your 31.8GB)")

model = AutoModelForCausalLM.from_pretrained(
    model_name,
    torch_dtype=torch.float16,
    device_map="auto",
    trust_remote_code=True
)

print("✅ Model loaded with FP16")

# Check VRAM usage
if torch.cuda.is_available():
    vram_used = torch.cuda.memory_allocated(0) / 1024**3
    vram_reserved = torch.cuda.memory_reserved(0) / 1024**3
    print(f"\n📊 VRAM Usage:")
    print(f"   Allocated: {vram_used:.2f} GB")
    print(f"   Reserved: {vram_reserved:.2f} GB")
    
    if vram_used < 20:
        print("   ✅ Model fits entirely in VRAM (no CPU offload)")
    else:
        print("   ⚠️  Using more VRAM than expected")

print("\n" + "=" * 60)
print("Testing inference speed...")
print("=" * 60)

# Medical test
test_prompt = """Extract medical entities from this text and return as JSON:

"The patient presented with acute myocardial infarction and was administered aspirin 325mg and atorvastatin 80mg. Blood pressure was 140/90 mmHg. ECG showed ST-segment elevation."

Return JSON with this structure:
{
  "entities": [
    {"entity_name": "name", "entity_type": "type", "entity_description": "description"}
  ],
  "relationships": [
    {"source_entity_name": "source", "target_entity_name": "target", "relation_type": "type"}
  ]
}"""

messages = [{"role": "user", "content": test_prompt}]

text = tokenizer.apply_chat_template(
    messages,
    tokenize=False,
    add_generation_prompt=True,
    enable_thinking=False
)

print(f"\n📝 Prompt prepared")

# Tokenize
model_inputs = tokenizer([text], return_tensors="pt").to(model.device)
input_length = model_inputs.input_ids.shape[1]

print(f"   Input tokens: {input_length}")
print("\n🧪 Generating response...")

# Warm-up
print("   (Warming up GPU kernels...)")
with torch.no_grad():
    _ = model.generate(
        **model_inputs,
        max_new_tokens=50,
        temperature=0.7,
        do_sample=True,
    )

# Actual test
print("   (Running timed test...)")
torch.cuda.synchronize()
start_time = time.time()

with torch.no_grad():
    generated_ids = model.generate(
        **model_inputs,
        max_new_tokens=700,
        temperature=0.7,
        top_p=0.8,
        top_k=20,
        do_sample=True,
        pad_token_id=tokenizer.pad_token_id,
        eos_token_id=tokenizer.eos_token_id
    )

torch.cuda.synchronize()
elapsed = time.time() - start_time

# Decode
output_ids = generated_ids[0][input_length:].tolist()
content = tokenizer.decode(output_ids, skip_special_tokens=True).strip()
output_tokens = len(output_ids)
tokens_per_sec = output_tokens / elapsed

print(f"\n✅ Generation completed!")
print(f"\n📊 Performance Metrics (Qwen3-14B FP16):")
print(f"   Time: {elapsed:.2f}s")
print(f"   Output tokens: {output_tokens}")
print(f"   Speed: {tokens_per_sec:.1f} tokens/sec")

if tokens_per_sec > 70:
    print("   ✅ EXCELLENT! This is the expected speed for RTX 5090")
    print("   → Qwen3-14B FP16 is a great choice")
elif tokens_per_sec > 40:
    print("   ✅ Good speed, much better than 32B options")
    print("   → Qwen3-14B is viable")
else:
    print("   ⚠️  Slower than expected")
    print("   → May need to investigate further")

print(f"\n📤 Sample Output:")
print("-" * 60)
print(content[:800])
if len(content) > 800:
    print("...(truncated)")
print("-" * 60)

print("\n" + "=" * 60)
print("Comparison:")
print("=" * 60)
print(f"Qwen3-32B 4-bit (bitsandbytes): 8.6 tok/s")
print(f"Qwen3-32B FP16 (CPU offload):   VERY SLOW")
print(f"Qwen3-14B FP16 (this test):    {tokens_per_sec:.1f} tok/s")
print(f"Speedup vs 32B 4-bit:           {tokens_per_sec / 8.6:.1f}x")

print("\n" + "=" * 60)
print("Quality Estimate:")
print("=" * 60)
print("Claude Sonnet 4:  100%")
print("Qwen3-32B:         90-92%")
print("Qwen3-14B:         86-88%  (only 2-4% drop)")
print("Qwen3-8B:          82-85%  (moderate drop)")

if tokens_per_sec > 60:
    print("\n✅ RECOMMENDATION: Use Qwen3-14B FP16 for pipeline!")
    print("   - Fast enough (60+ tok/s)")
    print("   - Good quality (86-88%)")
    print("   - Fits entirely in VRAM")
    print(f"   - Expected pipeline: ~{2.5 * (12 / (tokens_per_sec / 8)):.1f} min/doc")
else:
    print("\n⚠️  Consider testing Qwen3-8B for max speed")

print("\n💡 Next steps:")
print("   1. Compare quality vs Claude on 5-10 test chunks")
print("   2. If quality acceptable, integrate into pipeline")
print("   3. Run full pipeline test")

