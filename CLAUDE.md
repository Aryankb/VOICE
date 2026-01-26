# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## ⚠️ IMPORTANT: Token Conservation Rules

**DO NOT waste tokens on:**
1. ❌ Creating markdown documentation files unless explicitly requested
2. ❌ Creating README files, guides, or tutorials without user asking
3. ❌ Writing verbose summaries or explanations
4. ❌ Reading entire files when you only need specific sections

**DO save tokens by:**
1. ✅ Using `offset` and `limit` parameters when reading files
2. ✅ Using Grep to find specific code sections before reading
3. ✅ Only reading the parts of files you actually need
4. ✅ Asking user if they want documentation before creating it
5. ✅ Focusing on code implementation over documentation

**Example - Token-Efficient File Reading:**
```python
# ❌ BAD: Reading entire 1000-line file
Read(file_path="app.py")  # Wastes ~15K tokens

# ✅ GOOD: Read only what you need
Grep(pattern="generate_ai_response", output_mode="content")  # Find it first
Read(file_path="app.py", offset=650, limit=100)  # Read only that section
```

## Project Overview

This is a **Twilio Voice AI Assistant** built with FastAPI that enables real-time voice conversations over the phone. The system handles both inbound and outbound calls, processes speech, generates AI responses, and maintains conversation context using Twilio's Voice API.

## Technology Stack

- **Backend**: FastAPI (async Python web framework)
- **Voice Platform**: Twilio Voice API with TwiML
- **Speech Recognition**: Twilio's built-in speech recognition (using TwiML `<Gather>`)
- **Configuration**: Pydantic Settings with .env file
- **Dependencies**: See `pyproject.toml` or `requirements.txt`

## Development Commands

### Environment Setup

```bash
# Install dependencies using uv (recommended)
uv sync

# Or using pip
pip install -r requirements.txt
```

### Running the Application

```bash
# Start the FastAPI server (default port 8000)
python app.py

# Or using uvicorn directly
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

### Testing

```bash
# Test outbound calling
python examples.py

# Health check
curl http://localhost:8000/
```

### Local Development with ngrok

Since Twilio requires public webhooks, use ngrok for local development:

```bash
# In a separate terminal
ngrok http 8000

# Update .env with the ngrok URL
PUBLIC_URL=https://your-subdomain.ngrok.io
```

## Architecture Overview

### Call Flow Architecture

The application uses a **TwiML Gather-based approach** (not WebSocket streaming) for better compatibility with Twilio trial accounts:

1. **Outbound Call Initiation** (`/make-call`) → Twilio creates call → POST to `/voice/outbound`
2. **TwiML Response** → Returns `<Say>` greeting + `<Gather input="speech">`
3. **Speech Capture** → Twilio recognizes speech → POST to `/voice/process-speech`
4. **AI Processing** → Generate response → Return TwiML with `<Say>` + new `<Gather>`
5. **Conversation Loop** → Continues until goodbye/hangup

### Key Components

**Core Application (`app.py`)**
- FastAPI app with HTTP endpoints for TwiML webhooks
- Session management via `active_sessions` dict (stores conversation history per call_sid)
- Twilio client initialization for making outbound calls

**Configuration (`config.py`)**
- Pydantic Settings class loading from `.env`
- Required: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER`, `PUBLIC_URL`
- Optional: `SILENCE_THRESHOLD_SECONDS`, `SERVER_HOST`, `SERVER_PORT`

**Session Management**
- Each call tracked by `call_sid` in `active_sessions` dictionary
- Stores: phone numbers, conversation history, timestamps, recording URLs
- Cleaned up automatically when call ends via `/call-status` webhook

### Important Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/` | GET | Health check and active sessions count |
| `/make-call` | POST | Initiate outbound call (requires `to_number` in JSON body) |
| `/voice/outbound` | POST | TwiML webhook - initial greeting and first Gather |
| `/voice/process-speech` | POST | TwiML webhook - receives speech transcription and continues conversation |
| `/call-status` | POST | Webhook for call lifecycle events (answered, completed, etc.) |
| `/sessions` | GET | View all active call sessions |
| `/session/{call_sid}` | GET | Get specific call details and conversation history |

## Integration Points

The application has placeholder functions for STT/AI/TTS integration:

### 1. AI Response Generation

Located in `app.py` as `generate_ai_response_sync()`:
- Currently returns placeholder responses based on keywords
- Integrates with conversation history from `active_sessions[call_sid]["conversation_history"]`
- To integrate LLM: Add OpenAI/Claude/local model API calls here
- Function should be async and return string response

### 2. Speech-to-Text (Optional)

Twilio provides built-in STT via `<Gather input="speech">`:
- Transcription available in `/voice/process-speech` as `SpeechResult` form field
- Recording URLs also provided if `record=True` in call creation
- For custom STT: Download recording from `RecordingUrl` and process

### 3. Text-to-Speech

Currently uses Twilio's built-in TTS via `<Say>` TwiML verb:
- Voice can be customized (e.g., `Polly.Joanna`, `Polly.Aditi`)
- Language configurable (e.g., `en-US`, `hi-IN`)
- For custom TTS: Generate audio file, host publicly, use `<Play>` instead of `<Say>`

## Language and Voice Configuration

The app currently uses **Hindi language recognition** with an **Aditi voice** (Indian English):
- Speech recognition: `language="hi-IN"` in `<Gather>`
- TTS voice: `voice="Polly.Aditi"`
- To change: Modify language parameters in `/voice/outbound` and `/voice/process-speech` endpoints

## Environment Variables

Required `.env` configuration:

```env
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token_here
TWILIO_PHONE_NUMBER=+1234567890
PUBLIC_URL=https://your-ngrok-url.ngrok.io

# Optional
SERVER_HOST=0.0.0.0
SERVER_PORT=8000
SILENCE_THRESHOLD_SECONDS=4.0
AUDIO_SAMPLE_RATE=8000
```

## Session State Management

The `active_sessions` dictionary structure:

```python
active_sessions[call_sid] = {
    "to": "+1234567890",
    "from": "+0987654321",
    "conversation_history": [
        {
            "role": "user",
            "content": "transcribed text",
            "timestamp": "2024-01-25T14:30:00",
            "confidence": 0.95,
            "recording_url": "https://...",
            "recording_sid": "RE..."
        },
        {
            "role": "assistant",
            "content": "AI response text",
            "timestamp": "2024-01-25T14:30:05"
        }
    ],
    "started_at": "2024-01-25T14:29:45"
}
```

Sessions are automatically cleaned up when calls end (via `/call-status` webhook).

## Twilio Configuration

The outbound call creation includes:
- `machine_detection="DetectMessageEnd"` - Detects answering machines
- `record=True` - Records the call
- `status_callback` - Receives call lifecycle updates
- Speech recognition uses `speech_model="experimental_conversations"` with `enhanced=True`

## Common Patterns

### Making an Outbound Call

```python
response = requests.post(
    "http://localhost:8000/make-call",
    json={
        "to_number": "+1234567890",
        "from_number": "+0987654321"  # Optional
    }
)
```

### Accessing Conversation History

```python
if call_sid in active_sessions:
    history = active_sessions[call_sid]["conversation_history"]
    # Process conversation context
```

### Customizing TwiML Gather Parameters

In `/voice/outbound` or `/voice/process-speech`:
```python
gather = response.gather(
    input="speech",                    # speech, dtmf, or both
    action=f"{settings.public_url}/voice/process-speech",
    speech_timeout=3,                  # Seconds of silence before processing
    language="hi-IN",                  # Recognition language
    hints="help, support, goodbye",    # Expected keywords
    speech_model="experimental_conversations",
    enhanced=True
)
```

## Debugging Tips

1. **Check active sessions**: `GET /sessions`
2. **View conversation history**: `GET /session/{call_sid}`
3. **Monitor Twilio Console**: https://console.twilio.com/us1/monitor/logs/calls
4. **Server logs**: All important events logged via Python logging module
5. **ngrok inspector**: http://localhost:4040 (when running ngrok)

## Trial Account Limitations

- Must verify phone numbers before calling them
- Trial message played before call connects
- Limited concurrent calls
- To verify numbers: Twilio Console → Phone Numbers → Verified Caller IDs

## File Structure Context

- `app.py` - Main FastAPI application with all endpoints
- `config.py` - Pydantic settings configuration
- `main.py` - Simple entry point (minimal)
- `examples.py` - Example API usage and testing
- Documentation files: `START_HERE.md`, `QUICKSTART.md`, `OUTBOUND_CALLING.md`, `README_VOICE.md`
- The WebSocket-based streaming code is commented out in `app.py` (AudioBuffer class, /media endpoint)

## Recommended MCP Servers for This Project

To enhance development workflow and get latest context, consider integrating these MCP servers:

### 1. **Twilio Alpha MCP Server** (Highly Recommended)
The official Twilio MCP server exposes Twilio's entire API via Model Context Protocol, enabling direct interaction with Twilio services.

- **Repository**: [twilio-labs/mcp](https://github.com/twilio-labs/mcp)
- **Benefits**: Access Twilio API documentation, create/manage phone numbers, send SMS, manage voice calls
- **Setup**: Self-hostable, can deploy to Twilio Functions or run locally
- **Status**: Alpha (evolving, production auth coming soon)
- **Blog**: [Introducing Twilio Alpha MCP Server](https://www.twilio.com/en-us/blog/introducing-twilio-alpha-mcp-server)

### 2. **FastAPI-MCP Integration**
Exposes your FastAPI endpoints as MCP tools, making your existing API accessible to AI assistants.

- **Library**: [fastapi-mcp](https://pypi.org/project/fastapi-mcp/) or [fastmcp](https://github.com/jlowin/fastmcp)
- **Benefits**: Zero-config conversion of FastAPI endpoints to MCP tools, preserves schemas and documentation
- **Installation**: `pip install fastapi-mcp` or `pip install fastmcp`
- **Usage**: Mount MCP server to your existing FastAPI app at `/mcp` endpoint
- **Guides**:
  - [FastAPI + FastMCP Integration](https://gofastmcp.com/integrations/fastapi)
  - [Building FastAPI MCP Server](https://www.speakeasy.com/mcp/framework-guides/building-fastapi-server)

### 3. **Python MCP SDK** (Official)
The official Python SDK for building custom MCP servers and clients.

- **Repository**: [modelcontextprotocol/python-sdk](https://github.com/modelcontextprotocol/python-sdk)
- **Documentation**: [MCP Python SDK Docs](https://modelcontextprotocol.github.io/python-sdk/)
- **Installation**: `pip install mcp`
- **Use Case**: Build custom MCP tools for conversation management, session tracking, or call analytics

### 4. **Additional Useful MCP Servers**
- **File System MCP**: Read/write/organize local files (useful for managing recordings, logs)
- **PostgreSQL MCP**: If you add database support for call logs and analytics
- **GitHub MCP**: Version control integration for this codebase

## Latest Documentation Sources

### Twilio Voice API & TwiML
- **TwiML Gather Documentation**: [https://www.twilio.com/docs/voice/twiml/gather](https://www.twilio.com/docs/voice/twiml/gather)
- **Programmable Voice API**: [https://www.twilio.com/docs/voice/api](https://www.twilio.com/docs/voice/api)
- **TwiML Reference**: [https://www.twilio.com/docs/voice/twiml](https://www.twilio.com/docs/voice/twiml)

### FastAPI & MCP
- **FastAPI Docs**: [https://fastapi.tiangolo.com/](https://fastapi.tiangolo.com/)
- **FastMCP Documentation**: [https://gofastmcp.com/](https://gofastmcp.com/)
- **MCP Official Site**: [https://modelcontextprotocol.io/](https://modelcontextprotocol.io/)

### MCP Server Directories
- **Official MCP Servers**: [github.com/modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers)
- **Community Directory**: [mcp.so](https://mcp.so/)
- **MCP Market**: [mcpmarket.com](https://mcpmarket.com/)

## Setting Up MCP for This Project

To integrate MCP capabilities into this Twilio voice assistant:

### Option 1: Add Twilio MCP Server
```bash
# Clone and setup Twilio MCP
git clone https://github.com/twilio-labs/mcp.git
cd mcp
npm install
npm run build

# Configure with your Twilio credentials
# Then connect via Claude Code MCP configuration
```

### Option 2: Expose Current FastAPI as MCP Tools
```python
# Add to app.py
from fastapi_mcp import FastApiMCP

# After creating FastAPI app
mcp_server = FastApiMCP(app)
app.mount("/mcp", mcp_server)

# Now your endpoints are accessible via MCP at http://localhost:8000/mcp
```

### Option 3: Build Custom MCP Server for Voice Features
```python
# Create voice_mcp.py
from mcp.server import Server
from mcp.types import Tool

server = Server("voice-assistant")

@server.tool()
async def get_conversation_history(call_sid: str) -> dict:
    """Retrieve full conversation history for a call"""
    if call_sid in active_sessions:
        return active_sessions[call_sid]
    return {"error": "Session not found"}

@server.tool()
async def analyze_call_sentiment(call_sid: str) -> dict:
    """Analyze sentiment of conversation"""
    # Implementation here
    pass
```

## Why Use MCP for This Project?

1. **Direct Twilio API Access**: Query latest Twilio documentation, test API calls, manage resources without leaving Claude Code
2. **FastAPI Endpoint Discovery**: AI can discover and interact with your `/make-call`, `/sessions`, and other endpoints
3. **Conversation Analytics**: Build custom MCP tools for analyzing call patterns, transcriptions, and user intent
4. **Rapid Prototyping**: Test new voice features by describing them in natural language
5. **Production Monitoring**: Create MCP tools that query active sessions, call logs, and error rates

Sources:
- [Twilio Alpha MCP Server](https://www.twilio.com/en-us/blog/introducing-twilio-alpha-mcp-server)
- [FastAPI MCP Integration Guide](https://gofastmcp.com/integrations/fastapi)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [Twilio MCP Repository](https://github.com/twilio-labs/mcp)
- [FastAPI-MCP Library](https://github.com/tadata-org/fastapi_mcp)

---

## ✅ LOCAL AI INTEGRATION (COMPLETED - Jan 2026)

**Status:** Production-ready, fully functional

### What Was Changed
The project now uses **100% local AI** instead of cloud APIs:
- **LLM**: Ollama with Qwen 2.5 Coder 32B (local inference)
- **TTS**: XTTS-v2 (local voice generation)
- **Cost**: $0 per call (no API fees)
- **Privacy**: All data stays on local server

### Key Files
- `local_llm_client.py` - Ollama LLM client
- `local_tts_client.py` - Local TTS client (XTTS-v2 or MeloTTS)
- `config.py` - Added local AI settings
- `app.py` - Integrated local LLM and TTS

### Configuration (.env)
```env
USE_LOCAL_LLM=true
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=qwen2.5-coder:32b-instruct-q4_K_M

USE_LOCAL_TTS=true
TTS_ENGINE=xtts
```

### Setup
```powershell
# Quick setup
python install_local_ai.py

# Test
python test_local_setup.py

# Run
python app.py
```

### Performance
- Response time: 2-5 seconds
- VRAM usage: 23-25GB (fits in 32GB GPU)
- Quality: Excellent (better than GPT-3.5, comparable to GPT-4)

### Documentation
- **Quick Start**: `QUICKSTART_LOCAL_AI.md`
- **Full Setup**: `LOCAL_LLM_SETUP.md`
- **Complete Guide**: `README_LOCAL_AI.md`
- **Changes**: `LOCAL_AI_CHANGES.md`

**For future Claude sessions:** The local AI setup is complete and working. Focus on improvements/features, not reinstalling.
