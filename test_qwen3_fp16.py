"""
Test Qwen3-32B WITHOUT quantization (FP16) to check if bitsandbytes is the bottleneck
"""
import sys
import time
import torch

print("=" * 60)
print("Testing Qwen3-32B with FP16 (NO quantization)...")
print("=" * 60)

# Check PyTorch and CUDA
print(f"✅ PyTorch {torch.__version__}")
print(f"✅ CUDA available: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"   GPU: {torch.cuda.get_device_name(0)}")
    print(f"   VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
    print(f"   Compute Capability: sm_{torch.cuda.get_device_capability(0)[0]}{torch.cuda.get_device_capability(0)[1]}")

print("\n" + "=" * 60)
print("Loading Qwen3-32B model (FP16, NO quantization)...")
print("=" * 60)

from transformers import AutoModelForCausalLM, AutoTokenizer

model_name = "Qwen/Qwen3-32B"

# Load tokenizer
print(f"\n🔄 Loading tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(model_name)
print("✅ Tokenizer loaded")

# Load model WITHOUT quantization (pure FP16)
print(f"\n🔄 Loading model (FP16, no quantization)...")
print("   This will use ~28-30GB VRAM (you have 31.8GB)")

model = AutoModelForCausalLM.from_pretrained(
    model_name,
    torch_dtype=torch.float16,  # FP16 instead of 4-bit
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

print("\n" + "=" * 60)
print("Testing inference speed...")
print("=" * 60)

# Simple medical test
test_prompt = """Extract medical entities from this text:

"The patient presented with acute myocardial infarction and was administered aspirin 325mg."

Return JSON with entities array."""

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

# Warm-up run (compiling kernels)
print("   (Warming up GPU kernels...)")
with torch.no_grad():
    _ = model.generate(
        **model_inputs,
        max_new_tokens=50,
        temperature=0.7,
        do_sample=True,
    )

# Actual timed run
print("   (Running timed test...)")
torch.cuda.synchronize()
start_time = time.time()

with torch.no_grad():
    generated_ids = model.generate(
        **model_inputs,
        max_new_tokens=500,
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
print(f"\n📊 Performance Metrics (FP16):")
print(f"   Time: {elapsed:.2f}s")
print(f"   Output tokens: {output_tokens}")
print(f"   Speed: {tokens_per_sec:.1f} tokens/sec")

if tokens_per_sec > 70:
    print("   ✅ EXCELLENT! This is the expected speed for RTX 5090")
    print("   → Problem: bitsandbytes 4-bit is not optimized for sm_120")
    print("   → Solution: Use FP16 (you have enough VRAM)")
elif tokens_per_sec > 30:
    print("   ✅ Good speed, but should be faster")
    print("   → May need PyTorch optimization for sm_120")
else:
    print("   ⚠️  Still slow - deeper issue")
    print("   → Check GPU usage in nvidia-smi")

print(f"\n📤 Sample Output:")
print("-" * 60)
print(content[:500])
print("-" * 60)

print("\n" + "=" * 60)
print("Diagnosis:")
print("=" * 60)
print(f"4-bit speed: 8.6 tok/s (from previous test)")
print(f"FP16 speed:  {tokens_per_sec:.1f} tok/s (this test)")
print(f"Speedup:     {tokens_per_sec / 8.6:.1f}x")

if tokens_per_sec > 50:
    print("\n✅ SOLUTION: Use FP16 instead of 4-bit quantization")
    print("   - You have 31.8GB VRAM (plenty for FP16)")
    print("   - bitsandbytes not optimized for RTX 5090 yet")
    print("   - FP16 will be 5-10x faster")
else:
    print("\n⚠️  Issue may be elsewhere - check nvidia-smi during inference")

