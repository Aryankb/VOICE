# Quick Start: DynamoDB Integration

Get started with persistent, multi-agent voice conversations in under 10 minutes.

## 1. Install Dependencies

```bash
uv sync
# or: pip install -r requirements.txt
```

## 2. Configure Environment

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

Required variables:
```env
# Twilio (required)
TWILIO_ACCOUNT_SID=ACxxxxx
TWILIO_AUTH_TOKEN=xxxxx
TWILIO_PHONE_NUMBER=+1234567890
PUBLIC_URL=https://your-ngrok-url.ngrok.io

# AWS (required for DynamoDB)
AWS_REGION=us-east-1
# AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY are optional if using AWS CLI credentials
```

## 3. Create DynamoDB Tables

```bash
python scripts/create_tables.py
```

This creates 3 tables:
- `VoiceAssistant_Agents` - Agent configurations
- `VoiceAssistant_Calls` - Call records and conversation history
- `VoiceAssistant_PhoneNumbers` - Phone number assignments

## 4. Create S3 Bucket

```bash
aws s3 mb s3://voice-assistant-recordings --region us-east-1
```

Update `.env` with your bucket name:
```env
S3_BUCKET_RECORDINGS=voice-assistant-recordings
```

## 5. Seed Test Agents

```bash
python scripts/seed_data.py
```

Creates 4 sample agents:
- `customer-support-001` - English customer support
- `sales-001` - English sales agent
- `hindi-support-001` - Hindi language agent
- `default` - Default fallback agent

## 6. Start the Server

```bash
# Terminal 1: Start ngrok
ngrok http 8000

# Terminal 2: Start FastAPI server
python app.py
```

Update `.env` with your ngrok URL:
```env
PUBLIC_URL=https://abc123.ngrok.io
```

Restart the server after updating PUBLIC_URL.

## 7. Make Your First Call

```bash
curl -X POST http://localhost:8000/make-call \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "customer-support-001",
    "to_number": "+1234567890"
  }'
```

Response:
```json
{
  "success": true,
  "call_sid": "CA123...",
  "status": "queued",
  "to": "+1234567890",
  "from": "+0987654321",
  "agent_id": "customer-support-001"
}
```

## 8. Monitor Your Call

### Check Active Sessions
```bash
curl http://localhost:8000/sessions
```

### View Conversation History
```bash
curl http://localhost:8000/session/CA123...
```

### Query DynamoDB
```bash
# Get call record
aws dynamodb get-item \
    --table-name VoiceAssistant_Calls \
    --key '{"call_sid": {"S": "CA123..."}}'
```

## How It Works

### Call Flow

1. **Initiate Call**: POST to `/make-call` with `agent_id` and `to_number`
2. **Agent Validation**: System fetches agent config from DynamoDB
3. **Call Connects**: Twilio calls `/voice/outbound`
4. **Data Loading** (happens ONCE):
   - Fetch agent configuration
   - Fetch past 5 conversations with this recipient
   - Create call record in DynamoDB
   - Store everything in memory for fast access
5. **Conversation Loop**: Each speech input triggers `/voice/process-speech`
   - Accesses data from memory (no DB queries)
   - Appends to conversation history
   - Syncs to DB every 5 messages
   - Checks for termination conditions
6. **Call Ends**: Twilio calls `/call-status`
   - Downloads recording from Twilio
   - Uploads recording to S3
   - Finalizes call record in DynamoDB
   - Cleans up memory

### Termination Conditions

The call automatically ends when:
- **User says goodbye**: "bye", "goodbye", "thanks", etc.
- **System timeout**: 3 consecutive failed speech inputs
- **Data collection complete**: All required fields collected

## Create Your Own Agent

Create a JSON file (e.g., `my_agent.json`):

```json
{
  "agent_id": "my-agent-001",
  "name": "My Custom Agent",
  "prompt": "You are a helpful assistant for my business...",
  "voice": "Polly.Matthew",
  "language": "en-US",
  "greeting": "Hello! How can I help you?",
  "data_to_fill": {
    "name": {
      "required": true,
      "prompt": "What's your name?"
    },
    "email": {
      "required": true,
      "prompt": "What's your email?"
    }
  },
  "status": "active"
}
```

Create the agent:
```bash
python scripts/manage_agents.py create --config my_agent.json
```

Make a call with your agent:
```bash
curl -X POST http://localhost:8000/make-call \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "my-agent-001",
    "to_number": "+1234567890"
  }'
```

## Testing

Run the integration test suite:

```bash
python scripts/test_integration.py
```

This verifies:
- Database operations
- Agent creation and retrieval
- Call record management
- Conversation syncing
- Termination logic

## Useful Commands

### List all agents
```bash
python scripts/manage_agents.py list
```

### Get agent details
```bash
python scripts/manage_agents.py get customer-support-001
```

### Deactivate agent
```bash
python scripts/manage_agents.py deactivate old-agent-001
```

### View all active calls
```bash
curl http://localhost:8000/sessions
```

## Next Steps

1. **Integrate LLM**: Replace placeholder AI responses
   - Edit `generate_ai_response_sync()` in `app.py`
   - Use agent's `prompt` and `few_shot` examples
   - Pass `conversation_history` and `past_conversations` for context

2. **Add data extraction**: Use LLM to extract structured data
   - Parse user responses to fill `data_to_fill` fields
   - Update `data_collected` in session

3. **Build analytics**: Query call history
   - Use GSI indexes to query by agent, recipient, or status
   - Calculate metrics: average duration, completion rate, etc.

4. **Monitor production**:
   - Set up CloudWatch alarms for errors
   - Monitor DynamoDB throttling
   - Track S3 storage costs

## Troubleshooting

### "Agent not found" error
- Run: `python scripts/manage_agents.py list`
- Verify agent status is "active"
- Check AWS credentials are configured

### "Session not found" error
- Session is in-memory only during active calls
- If server restarts, active calls lose session data
- Call record persists in DynamoDB

### DynamoDB connection issues
- Verify AWS credentials: `aws sts get-caller-identity`
- Check region in `.env` matches table region
- Ensure tables exist: `aws dynamodb list-tables`

### S3 upload failures
- Verify bucket exists: `aws s3 ls s3://voice-assistant-recordings`
- Check IAM permissions for S3 PutObject
- Set `ENABLE_S3_UPLOAD=false` to disable if not needed

## Support

See detailed documentation:
- **Setup Guide**: `DYNAMODB_SETUP.md`
- **Architecture**: `CLAUDE.md`
- **Original Quick Start**: `QUICKSTART.md`
