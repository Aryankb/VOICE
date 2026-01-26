# Local LLM & TTS Setup Guide

**Hardware:** 32GB VRAM GPU
**Status:** Ready to install

---

## Part 1: Install Ollama + Qwen 2.5 Coder 32B

### Step 1: Download and Install Ollama

**Windows:**
```powershell
# Download from official site
# Visit: https://ollama.ai/download/windows

# Or use winget
winget install Ollama.Ollama
```

**Verify installation:**
```powershell
ollama --version
```

### Step 2: Pull Qwen 2.5 Coder 32B Model

```powershell
# Pull the model (Q4 quantized, ~20GB download)
ollama pull qwen2.5-coder:32b-instruct-q4_K_M

# Alternative models if you want to try:
# ollama pull qwen2.5:32b              # General purpose
# ollama pull llama3.3:70b-instruct-q4_K_M  # Larger, needs more VRAM
# ollama pull mistral-small:24b        # Alternative option
```

**Wait time:** 10-15 minutes depending on internet speed

### Step 3: Test the Model

```powershell
# Test basic inference
ollama run qwen2.5-coder:32b-instruct-q4_K_M "Hello, can you help me troubleshoot a laptop issue?"

# Check GPU usage
# Should show ~20GB VRAM usage
```

**Expected output:** Model should respond in ~1-2 seconds

### Step 4: Verify GPU is Being Used

```powershell
# Check GPU memory usage while model is running
nvidia-smi

# You should see ollama using 18-22GB VRAM
```

---

## Part 2: Install Local TTS

### Option A: XTTS-v2 (Best Quality, Voice Cloning)

**Install:**
```powershell
# Install Coqui TTS
pip install coqui-tts

# Download XTTS-v2 model
tts --model_name tts_models/multilingual/multi-dataset/xtts_v2 --text "Hello world" --out_path test.wav
```

**Features:**
- Voice cloning with 6-second sample
- 17 languages (including Hindi, English)
- <200ms latency with streaming
- **License:** Non-commercial only (Coqui Public Model License)

**Test:**
```powershell
# Test English
tts --model_name tts_models/multilingual/multi-dataset/xtts_v2 --text "Hello, how can I help you today?" --language_idx en --out_path test_en.wav

# Test Hindi
tts --model_name tts_models/multilingual/multi-dataset/xtts_v2 --text "नमस्ते, मैं आपकी कैसे मदद कर सकता हूं?" --language_idx hi --out_path test_hi.wav
```

### Option B: MeloTTS (Fastest, MIT License)

**Install:**
```powershell
pip install melotts
```

**Features:**
- Faster than XTTS
- Works well on CPU
- MIT license (commercial use OK)
- Supports English, Hindi, and more

**Test:**
```python
from melotts import MeloTTS
tts = MeloTTS(language='EN')
audio = tts.tts_to_file("Hello, how can I help you?", "test.wav")
```

---

## Part 3: Update Project Dependencies

Add to `pyproject.toml`:

```toml
[project]
dependencies = [
    # ... existing dependencies ...
    "ollama>=0.1.0",           # Ollama Python client
    "coqui-tts>=0.22.0",       # XTTS-v2 (Option A)
    # OR
    "melotts>=0.1.0",          # MeloTTS (Option B)
]
```

Install:
```powershell
uv sync
```

---

## Part 4: Configuration

Add to `.env`:

```env
# Local LLM Configuration
USE_LOCAL_LLM=true
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=qwen2.5-coder:32b-instruct-q4_K_M

# Local TTS Configuration
USE_LOCAL_TTS=true
TTS_ENGINE=xtts  # Options: xtts, melo
TTS_OUTPUT_DIR=./tts_output

# Disable OpenAI (no longer needed)
USE_OPENAI=false
```

---

## Performance Expectations

### LLM (Qwen 2.5 Coder 32B)
- **Inference speed:** 40-50 tokens/second on 32GB GPU
- **Response time:** 1-3 seconds for typical responses
- **VRAM usage:** 18-22GB
- **Context window:** 32K tokens
- **Quality:** Excellent for customer support conversations

### TTS (XTTS-v2)
- **Latency:** 150-250ms (streaming mode)
- **Quality:** Near-human voice quality
- **VRAM usage:** ~2-3GB (can use same GPU as LLM)
- **Total pipeline latency:** ~2-5 seconds (LLM + TTS)

### Combined System
- **Total VRAM:** ~23-25GB (fits in 32GB with headroom)
- **End-to-end latency:** 2-5 seconds per response
- **Cost:** $0 (no API fees!)

---

## Troubleshooting

### Ollama not using GPU
```powershell
# Set environment variable
$env:OLLAMA_GPU_DRIVER="cuda"

# Restart Ollama service
Restart-Service Ollama
```

### VRAM out of memory
```powershell
# Try smaller model
ollama pull qwen2.5:14b-instruct-q4_K_M

# Or use 7B model
ollama pull qwen2.5-coder:7b-instruct-q4_K_M
```

### TTS too slow
- Use MeloTTS instead of XTTS
- Enable streaming mode
- Pre-cache common phrases

### Ollama connection refused
```powershell
# Check if Ollama is running
Get-Process ollama

# Start Ollama
ollama serve
```

---

## Next Steps

After installation:
1. ✅ Verify Ollama + Qwen model works
2. ✅ Verify TTS generates audio
3. ✅ Update `app.py` to use local models
4. ✅ Test with real phone call

---

## Quick Test Script

Create `test_local_setup.py`:

```python
import asyncio
import ollama

async def test_llm():
    print("Testing Ollama LLM...")
    response = await ollama.chat(
        model='qwen2.5-coder:32b-instruct-q4_K_M',
        messages=[
            {'role': 'user', 'content': 'Hello! Can you help me troubleshoot a laptop that won\'t start?'}
        ]
    )
    print(f"LLM Response: {response['message']['content']}")
    print("✅ LLM working!")

def test_tts():
    print("\nTesting TTS...")
    from TTS.api import TTS
    tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2")
    tts.tts_to_file(
        text="Hello, I'm your AI assistant. How can I help you today?",
        file_path="test_output.wav",
        language="en"
    )
    print("✅ TTS working! Check test_output.wav")

if __name__ == "__main__":
    asyncio.run(test_llm())
    test_tts()
    print("\n🎉 All systems ready!")
```

Run:
```powershell
python test_local_setup.py
```

---

**Ready to proceed?**
1. Install Ollama: https://ollama.ai/download/windows
2. Pull model: `ollama pull qwen2.5-coder:32b-instruct-q4_K_M`
3. Install TTS: `pip install coqui-tts`
4. Run test script above
5. Come back when ready for code integration! 🚀
