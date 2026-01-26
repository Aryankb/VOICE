# Local AI Setup Guide

**FULLY LOCAL** - No API keys needed, no usage costs, runs on your 32GB GPU!

This guide sets up:
- **Local LLM**: Qwen 2.5 Coder 32B via Ollama (20GB VRAM)
- **Local TTS**: XTTS-v2 or MeloTTS (2-3GB VRAM)
- **Total**: ~23-25GB VRAM (fits perfectly in 32GB)

---

## Quick Start (30 minutes)

### Option 1: Automated Installation (Recommended)

```powershell
# Run the installation script
python install_local_ai.py

# This will:
# 1. Install Ollama
# 2. Pull Qwen 2.5 Coder 32B model (~20GB download)
# 3. Install Python dependencies
# 4. Create .env file
```

### Option 2: Manual Installation

#### Step 1: Install Ollama

**Windows:**
1. Download from https://ollama.ai/download/windows
2. Run installer
3. Verify: `ollama --version`

**macOS:**
```bash
brew install ollama
```

**Linux:**
```bash
curl -fsSL https://ollama.ai/install.sh | sh
```

#### Step 2: Pull Model

```powershell
# Pull Qwen 2.5 Coder 32B (Q4 quantized, ~20GB)
ollama pull qwen2.5-coder:32b-instruct-q4_K_M

# Wait 10-15 minutes for download
```

#### Step 3: Install Python Dependencies

```powershell
# Install required packages
pip install httpx coqui-tts

# Or use uv
uv sync
```

#### Step 4: Update .env

```env
# Enable local LLM
USE_LOCAL_LLM=true
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=qwen2.5-coder:32b-instruct-q4_K_M

# Enable local TTS
USE_LOCAL_TTS=true
TTS_ENGINE=xtts
TTS_OUTPUT_DIR=./tts_output

# Disable OpenAI (not needed)
USE_OPENAI=false
```

---

## Test Your Setup

```powershell
# Run the test script
python test_local_setup.py
```

**Expected output:**
```
Testing Local LLM (Ollama)
✅ Ollama is running with model: qwen2.5-coder:32b-instruct-q4_K_M
✅ LLM conversation test passed!
✅ Data extraction test passed!

Testing Local TTS
✅ TTS file generated: ./tts_output/tts_abc123.wav
✅ Hindi TTS file generated

Testing Full Pipeline (LLM + TTS)
✅ Full pipeline test passed!

🎉 All systems ready for phone calls!
```

---

## Run the Application

### 1. Start ngrok

```powershell
ngrok http 8000
```

Copy the HTTPS URL (e.g., `https://abc123.ngrok.io`)

### 2. Update .env

```env
PUBLIC_URL=https://abc123.ngrok.io
```

### 3. Start Server

```powershell
python app.py
```

**Check health:**
```powershell
# Basic health check
Invoke-RestMethod http://localhost:8000/

# Local AI health check
Invoke-RestMethod http://localhost:8000/health/local
```

**Expected response:**
```json
{
  "llm": {
    "enabled": true,
    "healthy": true,
    "model": "qwen2.5-coder:32b-instruct-q4_K_M"
  },
  "tts": {
    "enabled": true,
    "healthy": true,
    "engine": "xtts"
  }
}
```

### 4. Make Test Call

```powershell
Invoke-RestMethod -Uri http://localhost:8000/make-call -Method POST -ContentType "application/json" -Body '{"agent_id": "customer-support-001", "to_number": "+your-phone-number"}'
```

---

## Performance Metrics

### LLM (Qwen 2.5 Coder 32B)
- **Inference speed:** 40-50 tokens/second
- **Response time:** 1-3 seconds
- **VRAM usage:** 18-22GB
- **Context window:** 32K tokens
- **Quality:** Excellent for customer support

### TTS (XTTS-v2)
- **Latency:** 150-250ms (streaming mode)
- **Quality:** Near-human voice
- **VRAM usage:** 2-3GB
- **Languages:** 17 (including Hindi, English)

### Full Pipeline
- **End-to-end latency:** 2-5 seconds per response
- **Total VRAM:** 23-25GB
- **Cost per call:** $0 (completely free!)

---

## Alternative Models

### Smaller LLM (if VRAM constrained)

```powershell
# 14B model (~9GB VRAM)
ollama pull qwen2.5-coder:14b-instruct-q4_K_M

# 7B model (~5GB VRAM)
ollama pull qwen2.5-coder:7b-instruct-q4_K_M

# Update .env
OLLAMA_MODEL=qwen2.5-coder:14b-instruct-q4_K_M
```

### Larger LLM (if 48GB+ VRAM)

```powershell
# 70B model (~40GB VRAM, better quality)
ollama pull llama3.3:70b-instruct-q4_K_M

# Update .env
OLLAMA_MODEL=llama3.3:70b-instruct-q4_K_M
```

### Alternative TTS

```powershell
# MeloTTS (faster, MIT license, commercial OK)
pip install melotts

# Update .env
TTS_ENGINE=melo
```

---

## Troubleshooting

### Ollama not found

```powershell
# Check if running
Get-Process ollama

# Start Ollama service (Windows)
# Should start automatically after install

# Test connection
Invoke-RestMethod http://localhost:11434/api/tags
```

### Model not found

```powershell
# List pulled models
ollama list

# Pull model again
ollama pull qwen2.5-coder:32b-instruct-q4_K_M
```

### Out of VRAM

```
Error: CUDA out of memory
```

**Solutions:**
1. Close other applications using GPU
2. Use smaller model (14B or 7B)
3. Restart computer to clear VRAM

### TTS import error

```
ImportError: No module named 'TTS'
```

**Fix:**
```powershell
pip install coqui-tts
```

### Low response quality

**Improve agent prompts:**
```powershell
# Update agent prompts with better examples
python scripts/update_agent_prompts.py
```

---

## Cost Comparison

### Local AI (This Setup)
- **LLM**: $0/call
- **TTS**: $0/call
- **Total**: $0/call
- **Upfront**: GPU hardware (~$1500-2000 for 32GB VRAM)

### OpenAI GPT-4 + Twilio TTS
- **LLM**: ~$0.015/call
- **TTS**: Free (Twilio built-in)
- **Total**: ~$0.015/call
- **100,000 calls**: $1,500

### Break-even: ~100,000 calls
After 100,000 calls, local AI pays for itself!

---

## Advantages of Local AI

✅ **No API costs** - Completely free after setup
✅ **Privacy** - All data stays on your server
✅ **No rate limits** - Unlimited calls
✅ **Offline capable** - Works without internet (except Twilio)
✅ **Customizable** - Full control over models and behavior
✅ **Low latency** - 2-5s vs 3-8s with cloud APIs

---

## Next Steps

1. ✅ Test with real calls
2. ✅ Update agent prompts for better conversations
3. ✅ Monitor performance metrics
4. ✅ Fine-tune temperature and max_tokens
5. ✅ Experiment with different models

---

## File Structure

```
VOICE/
├── app.py                      # Main FastAPI app
├── config.py                   # Settings (updated with local AI)
├── local_llm_client.py         # Ollama LLM client (NEW)
├── local_tts_client.py         # Local TTS client (NEW)
├── test_local_setup.py         # Test script (NEW)
├── install_local_ai.py         # Installation script (NEW)
├── .env                        # Config (update with local settings)
│
├── tts_output/                 # Generated TTS files (NEW)
│
└── scripts/
    └── update_agent_prompts.py # Better prompts for LLM
```

---

## Sources & References

- [Ollama VRAM Requirements Guide](https://localllm.in/blog/ollama-vram-requirements-for-local-llms)
- [Best Local LLMs 2026](https://iproyal.com/blog/best-local-llms/)
- [Coqui TTS Documentation](https://docs.coqui.ai/)
- [XTTS-v2 on Hugging Face](https://huggingface.co/coqui/XTTS-v2)

---

## Support

Having issues?
1. Run `python test_local_setup.py` for diagnostics
2. Check `http://localhost:8000/health/local`
3. Review logs in terminal
4. Open GitHub issue with error logs

---

**Happy calling! 📞🤖**
