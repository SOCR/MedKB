"""
Test llama-cpp-python installation and GPU support
"""
import sys
from pathlib import Path

print("=" * 60)
print("Testing llama-cpp-python installation...")
print("=" * 60)

# Test 1: Import check
try:
    from llama_cpp import Llama
    print("✅ llama-cpp-python imported successfully")
except ImportError as e:
    print(f"❌ Failed to import llama-cpp-python: {e}")
    sys.exit(1)

# Test 2: Check for CUDA support
try:
    from llama_cpp import llama_supports_gpu_offload
    if llama_supports_gpu_offload():
        print("✅ GPU offload is supported (CUDA enabled)")
    else:
        print("⚠️  GPU offload not available (CPU only)")
except Exception as e:
    print(f"⚠️  Could not check GPU support: {e}")

print("\n" + "=" * 60)
print("Downloading test model (Qwen 3 32B 4-bit GGUF)...")
print("This will take a few minutes (~20GB download)")
print("=" * 60)

# Test 3: Download Qwen 3 32B model
model_dir = Path("./models")
model_dir.mkdir(exist_ok=True)

# Using huggingface_hub to download
try:
    from huggingface_hub import hf_hub_download
    print("✅ huggingface_hub available")
except ImportError:
    print("⚠️  Installing huggingface_hub...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "huggingface_hub"])
    from huggingface_hub import hf_hub_download
    print("✅ huggingface_hub installed")

# Download model
model_path = model_dir / "qwen3-32b-instruct-q4_k_m.gguf"

if model_path.exists():
    print(f"✅ Model already downloaded: {model_path}")
else:
    print("\n📥 Downloading Qwen 3 32B (Q4_K_M, ~20GB)...")
    print("This may take 10-20 minutes depending on your internet speed...")
    try:
        downloaded_path = hf_hub_download(
            repo_id="Qwen/Qwen2.5-32B-Instruct-GGUF",
            filename="qwen2.5-32b-instruct-q4_k_m.gguf",
            local_dir=str(model_dir),
            local_dir_use_symlinks=False
        )
        # Rename to our expected name
        Path(downloaded_path).rename(model_path)
        print(f"✅ Model downloaded to: {model_path}")
    except Exception as e:
        print(f"❌ Failed to download model: {e}")
        print("\nAlternative: Manually download from:")
        print("https://huggingface.co/Qwen/Qwen2.5-32B-Instruct-GGUF")
        sys.exit(1)

print("\n" + "=" * 60)
print("Loading model and testing inference...")
print("=" * 60)

# Test 4: Load model and run inference
try:
    print(f"\n🔄 Loading {model_path.name}...")
    print("This will use ~20GB of your VRAM...")
    
    llm = Llama(
        model_path=str(model_path),
        n_gpu_layers=-1,  # Offload all layers to GPU
        n_ctx=8192,       # Context window
        n_threads=8,      # CPU threads for prompt processing
        verbose=False
    )
    
    print("✅ Model loaded successfully!")
    print(f"   Context size: {llm.n_ctx()}")
    print(f"   GPU layers: All (-1)")
    
    # Test inference
    print("\n🧪 Testing inference with a medical extraction task...")
    
    test_prompt = """Extract medical entities from this text:

"The patient presented with hypertension and was prescribed lisinopril 10mg daily."

Return JSON with entities array containing entity_name and entity_type."""
    
    print(f"\n📝 Prompt: {test_prompt[:100]}...")
    
    import time
    start = time.time()
    
    response = llm(
        test_prompt,
        max_tokens=300,
        temperature=0.1,
        stop=["</s>", "\n\n\n"]
    )
    
    elapsed = time.time() - start
    
    print(f"\n✅ Inference completed in {elapsed:.2f}s")
    print(f"\n📤 Response:")
    print("-" * 60)
    print(response['choices'][0]['text'])
    print("-" * 60)
    
    # Calculate tokens per second
    tokens_generated = response['usage']['completion_tokens']
    tokens_per_sec = tokens_generated / elapsed
    
    print(f"\n📊 Performance:")
    print(f"   Tokens generated: {tokens_generated}")
    print(f"   Speed: {tokens_per_sec:.1f} tokens/sec")
    print(f"   Total time: {elapsed:.2f}s")
    
    if tokens_per_sec > 50:
        print("   ✅ Excellent speed (GPU acceleration working!)")
    elif tokens_per_sec > 20:
        print("   ✅ Good speed")
    else:
        print("   ⚠️  Slow - check GPU usage")
    
    print("\n" + "=" * 60)
    print("🎉 All tests passed! llama-cpp-python is ready to use.")
    print("=" * 60)
    
except Exception as e:
    print(f"❌ Error during inference test: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n💡 Next steps:")
print("   1. Run: python run_pipeline.py --use-local-llm --test-mode")
print("   2. Check GPU usage in another terminal: nvidia-smi -l 1")
print("   3. Compare speed vs Claude Bedrock")

