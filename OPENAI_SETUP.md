# OpenAI Integration Setup

**Status:** ✅ Code is ready, just need API key!

---

## Quick Setup (2 minutes)

### Step 1: Get OpenAI API Key

1. Go to https://platform.openai.com/api-keys
2. Sign up or log in
3. Click "Create new secret key"
4. Copy the key (starts with `sk-...`)

### Step 2: Add to `.env`

Open `D:\Code\Startup\VOICE\.env` and uncomment/add:

```env
# LLM Configuration (OpenAI)
OPENAI_API_KEY=sk-proj-your-actual-key-here
USE_OPENAI=true
OPENAI_MODEL=gpt-4
```

**Note:** Use `gpt-3.5-turbo` instead of `gpt-4` for lower cost (~10x cheaper)

### Step 3: Install OpenAI Package

```powershell
uv sync
# This will install openai>=1.0.0
```

### Step 4: Restart Server

```powershell
# Stop server (CTRL+C)
python app.py
```

### Step 5: Test!

```powershell
Invoke-RestMethod -Uri http://localhost:8000/make-call -Method POST -ContentType "application/json" -Body '{"agent_id": "customer-support-001", "to_number": "+91600566015"}'
```

---

## What Changed?

**Before (Placeholder Logic):**
- User: "My laptop is not working"
- AI: "I heard you say: My laptop is not working. Could you provide more details?"
- ❌ Generic, unhelpful

**After (OpenAI GPT-4):**
- User: "My laptop is not working"
- AI: "I'd be happy to help! Can you tell me what happens when you try to start your laptop? Do you see any lights, hear any sounds, or does nothing happen at all?"
- ✅ Conversational, helpful, asks clarifying questions

---

## Features

### 1. **Context-Aware Responses**
- Uses agent's custom prompt
- Includes few-shot examples
- Remembers past conversations
- Knows what data is already collected

### 2. **Smart Data Extraction**
- User: "My name is Manas"
- Extracts: `{"name": "Manas"}` ✅
- (Not: `{"name": "My name is Manas"}` ❌)

### 3. **Conversation Flow**
1. First helps with the issue
2. Then asks for contact info
3. Natural, human-like conversation

### 4. **Multi-language Support**
- Automatically responds in agent's language
- English agents → English responses
- Hindi agents → Hindi responses

---

## Cost Estimates

### GPT-4
- **Input:** $0.03 per 1K tokens (~$0.006 per call)
- **Output:** $0.06 per 1K tokens (~$0.009 per call)
- **Total:** ~$0.015 per call

### GPT-3.5-Turbo (Recommended for testing)
- **Input:** $0.0015 per 1K tokens (~$0.0003 per call)
- **Output:** $0.002 per 1K tokens (~$0.0004 per call)
- **Total:** ~$0.0007 per call

**Recommendation:** Start with `gpt-3.5-turbo`, upgrade to `gpt-4` for production.

---

## Configuration Options

```env
# Model selection
OPENAI_MODEL=gpt-4                  # Best quality
OPENAI_MODEL=gpt-4-turbo            # Faster, cheaper
OPENAI_MODEL=gpt-3.5-turbo          # Cheapest, still good

# Feature flag
USE_OPENAI=true                     # Enable OpenAI
USE_OPENAI=false                    # Use placeholder responses
```

---

## Testing the Difference

### Test 1: Laptop Issue

**Call with:**
```powershell
Invoke-RestMethod -Uri http://localhost:8000/make-call -Method POST -ContentType "application/json" -Body '{"agent_id": "customer-support-001", "to_number": "+91600566015"}'
```

**Say:** "My laptop won't start"

**Expected (OpenAI):** Detailed troubleshooting steps

**Fallback (Placeholder):** Generic response

---

### Test 2: Data Collection

**Say:** "My name is Manas and my email is manas@example.com"

**Expected (OpenAI):**
- Extracts: `name: "Manas"`, `email: "manas@example.com"`
- Responds: "Thank you, Manas! I have your email. How else can I help?"

**Fallback (Placeholder):**
- Stores full sentence
- Generic response

---

## Troubleshooting

### Error: "Invalid API key"
```
OpenAI error: Error code: 401 - {'error': {'message': 'Incorrect API key provided'}}
```
**Fix:** Check your API key in `.env` - should start with `sk-`

### Error: "Rate limit exceeded"
```
OpenAI error: Error code: 429 - {'error': {'message': 'Rate limit reached'}}
```
**Fix:**
- Wait a minute
- Or upgrade your OpenAI account
- Or switch to `gpt-3.5-turbo`

### Error: "Model not found"
```
OpenAI error: Error code: 404 - {'error': {'message': 'The model `gpt-4` does not exist'}}
```
**Fix:**
- Check if you have GPT-4 access (requires paid account)
- Use `gpt-3.5-turbo` instead

### OpenAI not being used (fallback to placeholder)
**Check:**
1. `USE_OPENAI=true` in `.env`
2. `OPENAI_API_KEY` is set
3. Server restarted after changing `.env`
4. Check logs: Should see "Calling OpenAI gpt-4"

---

## Logs to Verify It's Working

```
INFO:app:Calling OpenAI gpt-4 for CA123...
INFO:app:OpenAI response for CA123: I'd be happy to help! Can you tell me what happens when...
```

If you see these logs, OpenAI is working! ✅

If you see: `OpenAI error: ... Falling back to placeholder responses.`
Then it's using fallback (check troubleshooting above).

---

## Next Steps

Once OpenAI is working:

1. **Improve agent prompts** - Update in DynamoDB
2. **Add confidence threshold** - Ignore low-quality speech
3. **Test different models** - Compare gpt-4 vs gpt-3.5-turbo
4. **Monitor costs** - Check https://platform.openai.com/usage

---

## Alternative: Use Local Ollama (FREE)

Don't want to pay for OpenAI? Use Ollama locally:

```powershell
# Install Ollama
# Download from: https://ollama.ai

# Pull model
ollama pull llama2

# Update code to call Ollama instead
# (Not implemented yet - let me know if you want this!)
```

---

**Ready to test!** 🚀

1. Get API key: https://platform.openai.com/api-keys
2. Add to `.env`: `OPENAI_API_KEY=sk-...` and `USE_OPENAI=true`
3. Run: `uv sync`
4. Restart: `python app.py`
5. Test call and see the magic! ✨
