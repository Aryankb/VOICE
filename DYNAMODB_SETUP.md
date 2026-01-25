# DynamoDB Integration Setup Guide

This guide walks you through setting up DynamoDB integration for the Twilio Voice AI Assistant.

## Prerequisites

1. **AWS Account** with DynamoDB access
2. **AWS Credentials** configured (IAM user or role with DynamoDB permissions)
3. **Python 3.11+** with dependencies installed
4. **Twilio Account** already set up

## Step 1: Configure AWS Credentials

### Option A: Using AWS CLI (Recommended)

```bash
# Install AWS CLI
pip install awscli

# Configure credentials (creates ~/.aws/credentials)
aws configure
```

Enter your:
- AWS Access Key ID
- AWS Secret Access Key
- Default region (e.g., us-east-1)
- Default output format (json)

### Option B: Using Environment Variables

Add to your `.env` file:

```env
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=your_access_key_here
AWS_SECRET_ACCESS_KEY=your_secret_key_here
```

## Step 2: Install Dependencies

```bash
# Using uv (recommended)
uv sync

# Or using pip
pip install aioboto3 boto3 botocore
```

## Step 3: Configure DynamoDB Settings

Update your `.env` file with DynamoDB configuration:

```env
# DynamoDB Configuration
DYNAMODB_TABLE_AGENTS=VoiceAssistant_Agents
DYNAMODB_TABLE_CALLS=VoiceAssistant_Calls
DYNAMODB_TABLE_PHONE_NUMBERS=VoiceAssistant_PhoneNumbers

# S3 Configuration (for recording storage)
S3_BUCKET_RECORDINGS=voice-assistant-recordings
S3_RECORDINGS_PREFIX=recordings/

# Feature Flags
ENABLE_DYNAMODB=true
ENABLE_S3_UPLOAD=true

# Session Management
SESSION_SYNC_FREQUENCY=5
AGENT_CACHE_TTL_SECONDS=300
```

## Step 4: Create DynamoDB Tables

Run the table creation script:

```bash
python scripts/create_tables.py
```

Expected output:
```
============================================================
DynamoDB Table Creation Script
============================================================
Region: us-east-1
Agent Table: VoiceAssistant_Agents
Calls Table: VoiceAssistant_Calls
Phone Numbers Table: VoiceAssistant_PhoneNumbers
============================================================

--- Creating Tables ---
✓ Creating table: VoiceAssistant_Agents
✓ Table VoiceAssistant_Agents created successfully!
✓ Creating table: VoiceAssistant_Calls
✓ Table VoiceAssistant_Calls created successfully!
✓ Creating table: VoiceAssistant_PhoneNumbers
✓ Table VoiceAssistant_PhoneNumbers created successfully!

--- Verifying Tables ---
✓ VoiceAssistant_Agents: ACTIVE
✓ VoiceAssistant_Calls: ACTIVE
✓ VoiceAssistant_PhoneNumbers: ACTIVE

============================================================
✓ All tables created and active!
============================================================
```

## Step 5: Create S3 Bucket for Recordings

```bash
# Create S3 bucket
aws s3 mb s3://voice-assistant-recordings --region us-east-1

# Enable encryption
aws s3api put-bucket-encryption \
    --bucket voice-assistant-recordings \
    --server-side-encryption-configuration '{
        "Rules": [{
            "ApplyServerSideEncryptionByDefault": {
                "SSEAlgorithm": "AES256"
            }
        }]
    }'

# Enable versioning (optional but recommended)
aws s3api put-bucket-versioning \
    --bucket voice-assistant-recordings \
    --versioning-configuration Status=Enabled
```

## Step 6: Seed Test Data

Create sample agents for testing:

```bash
python scripts/seed_data.py
```

This creates 4 sample agents:
- `customer-support-001`: English customer support agent
- `sales-001`: English sales agent
- `hindi-support-001`: Hindi language agent
- `default`: Default fallback agent

## Step 7: Run Integration Tests

Verify everything works:

```bash
python scripts/test_integration.py
```

Expected output shows tests for all 4 phases passing.

## Step 8: Test with API Call

Make a test call using an agent:

```bash
curl -X POST http://localhost:8000/make-call \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "customer-support-001",
    "to_number": "+1234567890"
  }'
```

## Table Schemas

### Agents Table

**Primary Key:** `agent_id` (String)

**GSI-1 (StatusIndex):**
- PK: `status`
- SK: `created_at`

**Key Attributes:**
- `agent_id`: Unique identifier
- `name`: Human-readable name
- `prompt`: System prompt for AI
- `few_shot`: Few-shot examples (list)
- `voice`: Twilio voice (e.g., "Polly.Joanna")
- `language`: Language code (e.g., "en-US")
- `greeting`: Initial greeting message
- `data_to_fill`: Data collection requirements (map)
- `status`: Agent status (active/inactive/archived)

### Calls Table

**Primary Key:** `call_sid` (String)

**GSI-1 (AgentRecipientIndex):**
- PK: `agent_id`
- SK: `agent_recipient_key` (composite: `agent_id#recipient_phone#started_at`)

**GSI-2 (RecipientIndex):**
- PK: `recipient_phone`
- SK: `started_at`

**GSI-3 (StatusIndex):**
- PK: `status`
- SK: `started_at`

**Key Attributes:**
- `call_sid`: Twilio call SID
- `agent_id`: Agent used for this call
- `recipient_phone`: Phone number called
- `caller_phone`: Phone number calling from
- `status`: Call status
- `started_at`, `ended_at`: Timestamps
- `duration_seconds`: Call duration
- `ended_by`: Who ended the call
- `conversation_history`: Full conversation (list)
- `call_recording_url`: Twilio recording URL
- `s3_recording_url`: S3 archived recording URL
- `data_collected`: Collected data (map)

## Architecture Overview

### Call Flow with DynamoDB

1. **User initiates call** via `/make-call` with `agent_id`
2. **Agent validation**: Check agent exists in DynamoDB
3. **Twilio creates call** → POST to `/voice/outbound?agent_id=X`
4. **Single-fetch optimization**:
   - Fetch agent data from DynamoDB
   - Fetch past conversations (last 5 calls)
   - Create initial call record in DynamoDB
   - Store ALL data in `active_sessions` (in-memory)
5. **Conversation loop** via `/voice/process-speech`:
   - Access session data (NO DB queries)
   - Append messages to conversation history
   - Periodic sync every 5 messages to DynamoDB
   - Check termination conditions
6. **Call completion** via `/call-status`:
   - Download recording from Twilio
   - Upload recording to S3
   - Finalize call record in DynamoDB
   - Cleanup session from memory

### Key Optimizations

- **Single-fetch**: Agent data and past conversations fetched ONCE at call start
- **Hybrid storage**: In-memory for speed, periodic DB sync for persistence
- **Graceful degradation**: Falls back to defaults if DynamoDB unavailable
- **Agent caching**: 5-minute TTL cache for frequently used agents

## IAM Permissions Required

Your AWS IAM user/role needs these permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:CreateTable",
        "dynamodb:DescribeTable",
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:DeleteItem",
        "dynamodb:Query",
        "dynamodb:BatchWriteItem"
      ],
      "Resource": [
        "arn:aws:dynamodb:*:*:table/VoiceAssistant_*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:DeleteObject"
      ],
      "Resource": [
        "arn:aws:s3:::voice-assistant-recordings/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::voice-assistant-recordings"
      ]
    }
  ]
}
```

## Monitoring and Debugging

### View Active Sessions

```bash
curl http://localhost:8000/sessions
```

### View Specific Call Session

```bash
curl http://localhost:8000/session/{call_sid}
```

### Query DynamoDB Directly

```bash
# Get agent
aws dynamodb get-item \
    --table-name VoiceAssistant_Agents \
    --key '{"agent_id": {"S": "customer-support-001"}}'

# Get call record
aws dynamodb get-item \
    --table-name VoiceAssistant_Calls \
    --key '{"call_sid": {"S": "CA123..."}}'

# Query past conversations for agent+recipient
aws dynamodb query \
    --table-name VoiceAssistant_Calls \
    --index-name AgentRecipientIndex \
    --key-condition-expression "agent_id = :agent_id" \
    --expression-attribute-values '{":agent_id": {"S": "customer-support-001"}}'
```

### Check S3 Recordings

```bash
# List recordings
aws s3 ls s3://voice-assistant-recordings/recordings/

# Download recording
aws s3 cp s3://voice-assistant-recordings/recordings/CA123.mp3 ./recording.mp3
```

## Troubleshooting

### Error: "Agent not found"

- Verify agent exists in DynamoDB: `aws dynamodb scan --table-name VoiceAssistant_Agents`
- Check agent status is "active"
- Clear agent cache: Restart the server

### Error: "Failed to upload to S3"

- Verify S3 bucket exists: `aws s3 ls s3://voice-assistant-recordings`
- Check IAM permissions for S3
- Verify `ENABLE_S3_UPLOAD=true` in .env

### Error: "Session not found"

- This can happen if server restarted mid-call
- Sessions are in-memory only during active calls
- Check DynamoDB for call record: Query by call_sid

### Performance Issues

- Check DynamoDB query latency in CloudWatch
- Verify agent caching is working (check logs for "Cache hit")
- Adjust `SESSION_SYNC_FREQUENCY` if syncing too often
- Consider increasing `AGENT_CACHE_TTL_SECONDS` for stable agents

## Cost Estimation

### DynamoDB (PAY_PER_REQUEST)

- **Agents table**: ~$0.00025 per read, $0.00125 per write
  - Typical: 1 read per call (cached), minimal writes
- **Calls table**: ~$0.00025 per read, $0.00125 per write
  - Typical: 2 reads + 3 writes per call
- **Estimated cost**: <$0.01 per call for DynamoDB

### S3 Storage

- **Storage**: $0.023 per GB/month (Standard tier)
- **PUT requests**: $0.005 per 1000 requests
- **Typical recording**: ~1-2 MB per call
- **Estimated cost**: <$0.001 per call for S3

### Total Estimated Cost

- **Per call**: <$0.02 (DynamoDB + S3 + transfer)
- **1000 calls/month**: ~$20
- **10,000 calls/month**: ~$200

## Production Checklist

- [ ] Tables created with proper names
- [ ] S3 bucket created with encryption
- [ ] IAM permissions configured
- [ ] AWS credentials configured securely (not in .env)
- [ ] Test agent created and validated
- [ ] Made test call successfully
- [ ] Verified conversation saved to DynamoDB
- [ ] Verified recording uploaded to S3
- [ ] CloudWatch alarms configured for errors
- [ ] Backup strategy planned for DynamoDB
- [ ] Cost alerts set up

## Next Steps

1. **Integrate LLM**: Replace placeholder responses in `generate_ai_response_sync()`
2. **Add analytics**: Create endpoints to query call history and metrics
3. **Build admin UI**: Create interface to manage agents and view calls
4. **Set up monitoring**: Configure CloudWatch dashboards
5. **Implement data extraction**: Use LLM to extract structured data from conversations

## Support

For issues or questions:
- Check application logs: `tail -f app.log`
- Check AWS CloudWatch logs
- Review Twilio console for call details
- See CLAUDE.md for architecture overview
