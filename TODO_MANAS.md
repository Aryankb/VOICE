# TODO - Manas

Implementation tasks for integrating database schema, agent management, and enhanced call handling.

---

## 1. Database Schema & GSI Logic

### Tasks
- [ ] **Understand Database Schema**
  - Review database tables structure (agents, calls, recipients)
  - Understand primary keys (PK) and sort keys (SK)
  - Document relationships between tables

- [ ] **Understand GSI (Global Secondary Index) Logic**
  - Identify which GSIs exist on each table
  - Understand query patterns using GSIs
  - Document when to use GSI vs primary key queries

- [ ] **Document Schema**
  - Create schema diagram showing table relationships
  - Document field types and constraints
  - Note indexes and their use cases

**Questions to Answer:**
- What fields exist in `agents` table?
- What fields exist in `calls` table?
- What fields exist in `recipients` table (if separate)?
- Which GSIs are configured and what do they enable?

---

## 2. Twilio Client Call Creation

### Task
- [ ] **Understand `twilio_client.calls.create()` Parameters**

**Current Implementation (from app.py:213-221):**
```python
call = twilio_client.calls.create(
    to=to_number,
    from_=from_number,
    url=f"{settings.public_url}/voice/outbound",
    status_callback=f"{settings.public_url}/call-status",
    status_callback_event=["initiated", "ringing", "answered", "completed"],
    machine_detection="DetectMessageEnd",
    record=True
)
```

**Parameters to Research:**
- [ ] `to` - Recipient phone number (E.164 format)
- [ ] `from_` - Caller ID / Twilio number
- [ ] `url` - TwiML webhook URL for call instructions
- [ ] `status_callback` - Webhook for call status updates
- [ ] `status_callback_event` - Which events trigger status callback
- [ ] `machine_detection` - Options: "Enable", "DetectMessageEnd", "Premium" (what's the difference?)
- [ ] `record` - Boolean, records the call audio
- [ ] **Additional Parameters to Explore:**
  - `timeout` - Seconds before timing out
  - `status_callback_method` - GET or POST
  - `fallback_url` - Backup URL if primary fails
  - `recording_status_callback` - Webhook when recording is ready
  - `send_digits` - Send DTMF tones after connect
  - `machine_detection_timeout` - Timeout for AMD
  - `machine_detection_silence_timeout` - Silence threshold for AMD
  - `machine_detection_speech_threshold` - Speech duration threshold
  - `machine_detection_speech_end_threshold` - End of speech detection

**Documentation:**
- [ ] Read Twilio Docs: https://www.twilio.com/docs/voice/api/call-resource#create-a-call-resource
- [ ] Document each parameter's purpose and acceptable values
- [ ] Note which parameters are optional vs required

---

## 3. Focus on Three Key Endpoints

### Endpoints to Master
1. `/voice/outbound` - Initial TwiML response when call is answered
2. `/call-status` - Call lifecycle events (initiated, ringing, answered, completed)
3. `/voice/process-speech` - Process user speech and continue conversation

**Tasks:**
- [ ] Trace full call flow through these three endpoints
- [ ] Understand data passed between them
- [ ] Document the webhook sequence and timing
- [ ] Identify optimization opportunities

---

## 4. Implement `/voice/outbound` with Agent & Recipient Data Fetching

### Current State (app.py:149-185)
Currently uses hardcoded greeting and no database integration.

### Required Changes
- [ ] **Fetch Agent Data from `agents` Table**
  ```python
  # Fetch using agent_id (how to get agent_id? from URL param? from calls table?)
  agent_data = {
      "prompt": "",          # System prompt for AI
      "few_shot": [],        # Few-shot examples
      "mcp": {},             # MCP configuration
      "s3_file_paths": [],   # S3 audio/document paths
      "data_to_fill": {}     # Data fields to collect
  }
  ```

- [ ] **Fetch Recipient Data from `calls` Table**
  ```python
  recipient_data = {
      "name": "",
      "phone_number": "",
      "preferences": {},
      "previous_calls": []
  }
  ```

- [ ] **Store Fetched Data in Session**
  ```python
  active_sessions[call_sid] = {
      "to": to_number,
      "from": from_number,
      "agent_id": agent_id,
      "agent_data": agent_data,        # Store once
      "recipient_data": recipient_data, # Store once
      "conversation_history": [],
      "data_collected": {},            # Track data_to_fill progress
      "started_at": datetime.now().isoformat()
  }
  ```

- [ ] **Use Agent Prompt in Initial Greeting**
  ```python
  # Use agent's custom greeting instead of hardcoded one
  greeting = agent_data.get("greeting") or "Hello! I'm your AI assistant..."
  response.say(greeting, voice=agent_data.get("voice", "Polly.Joanna"))
  ```

**Implementation Steps:**
1. [ ] Determine how to pass `agent_id` to `/voice/outbound` (query param? session lookup?)
2. [ ] Implement database query function: `fetch_agent_data(agent_id)`
3. [ ] Implement database query function: `fetch_recipient_data(phone_number, agent_id)`
4. [ ] Store fetched data in `active_sessions[call_sid]`
5. [ ] Use agent data to customize TwiML response
6. [ ] Handle database query errors gracefully

---

## 5. Implement `/voice/process-speech` with Optimized Data Access

### Current State (app.py:249-347)
Currently processes speech but has no agent/recipient context.

### Required Changes
- [ ] **Reuse Data from Session (Don't Re-fetch)**
  ```python
  # Get data already fetched in /voice/outbound
  if call_sid in active_sessions:
      agent_data = active_sessions[call_sid].get("agent_data")
      recipient_data = active_sessions[call_sid].get("recipient_data")
      past_conversations = active_sessions[call_sid].get("past_conversations")

      # No need to fetch again!
  ```

- [ ] **Use Agent Context in AI Response Generation**
  ```python
  async def generate_ai_response_sync(user_input: str, call_sid: str) -> str:
      session = active_sessions[call_sid]

      # Use agent's system prompt
      system_prompt = session["agent_data"]["prompt"]

      # Include few-shot examples
      few_shot = session["agent_data"]["few_shot"]

      # Include conversation history
      history = session["conversation_history"]

      # Include past conversations for context
      past_conversations = session.get("past_conversations", [])

      # Generate response with full context
      # ...
  ```

- [ ] **Track Data Collection Progress**
  ```python
  # If agent needs to collect specific data
  data_to_fill = session["agent_data"]["data_to_fill"]
  data_collected = session["data_collected"]

  # Update collected data based on user response
  # Check if all required data is collected
  ```

**Implementation Steps:**
1. [ ] Access session data instead of re-fetching
2. [ ] Integrate agent prompt into `generate_ai_response_sync()`
3. [ ] Use few-shot examples for better responses
4. [ ] Implement data collection tracking logic
5. [ ] Test with various agent configurations

---

## 6. Fetch Previous Call Data (Past Conversations)

### Task
Fetch past conversation history for this agent + recipient pair, store once in global session.

### Implementation
- [ ] **Create Database Query Function**
  ```python
  async def fetch_past_conversations(agent_id: str, recipient_number: str, limit: int = 5):
      """
      Fetch previous calls between this agent and recipient
      Query calls table using GSI: agent_id + recipient_number
      Return last N completed calls with their conversation history
      """
      # Query using GSI
      # Filter by completed status
      # Order by created_at DESC
      # Limit to recent N calls
      return past_calls
  ```

- [ ] **Fetch Once in `/voice/outbound`**
  ```python
  # In /voice/outbound endpoint
  past_conversations = await fetch_past_conversations(
      agent_id=agent_id,
      recipient_number=to_number,
      limit=5  # Last 5 calls
  )

  # Store in session (fetch once, reuse everywhere)
  active_sessions[call_sid]["past_conversations"] = past_conversations
  ```

- [ ] **Reuse in `/voice/process-speech`**
  ```python
  # Access from session - no re-fetching needed
  past_conversations = active_sessions[call_sid].get("past_conversations", [])

  # Use in AI context
  context = f"Previous conversations: {past_conversations}"
  ```

**Database Considerations:**
- [ ] Ensure GSI exists on `calls` table for (agent_id, recipient_number) queries
- [ ] Index by timestamp for ordering
- [ ] Consider performance implications of fetching large conversation histories
- [ ] Implement pagination if needed

**Questions:**
- What's the GSI structure? PK=agent_id, SK=recipient_number+timestamp?
- How much history to include? (5 calls? 10 calls? All?)
- Should we summarize old conversations to reduce token usage?

---

## 7. Call Termination & Data Persistence

### Task
Handle call ending from both user and system side, save metadata to database.

### 7.1 User-Initiated Call End
- [ ] **Detect Goodbye Intent**
  ```python
  async def detect_goodbye_intent(user_input: str) -> bool:
      """Detect if user wants to end call"""
      goodbye_phrases = ["goodbye", "bye", "thank you", "that's all", "hang up"]
      return any(phrase in user_input.lower() for phrase in goodbye_phrases)
  ```

- [ ] **End Call Gracefully**
  ```python
  # In /voice/process-speech
  if await detect_goodbye_intent(speech_result):
      response.say("Thank you for calling. Goodbye!", voice="Polly.Joanna")
      response.hangup()

      # Mark end time (will be finalized in /call-status)
      if call_sid in active_sessions:
          active_sessions[call_sid]["ended_by"] = "user"
  ```

### 7.2 System-Initiated Call End
- [ ] **Implement Timeout Logic**
  ```python
  # End call after N failed attempts or timeout
  if session.get("no_input_count", 0) >= 3:
      response.say("I haven't heard from you. Ending the call. Goodbye!")
      response.hangup()

      active_sessions[call_sid]["ended_by"] = "system_timeout"
  ```

- [ ] **End After Data Collection Complete**
  ```python
  # If agent collected all required data
  if all_data_collected(session):
      response.say("I have all the information I need. Thank you!")
      response.hangup()

      active_sessions[call_sid]["ended_by"] = "system_complete"
  ```

### 7.3 Save Call Data in `/call-status` Webhook
- [ ] **Update `calls` Table on Completion**
  ```python
  # In /call-status endpoint (app.py:350-374)
  if call_status in ["completed", "failed", "busy", "no-answer", "canceled"]:
      if call_sid in active_sessions:
          session = active_sessions[call_sid]

          # Calculate duration
          started_at = datetime.fromisoformat(session["started_at"])
          ended_at = datetime.now()
          duration = (ended_at - started_at).total_seconds()

          # Save to database
          await save_call_to_database(
              call_sid=call_sid,
              agent_id=session["agent_id"],
              recipient_number=session["to"],
              started_at=started_at,
              ended_at=ended_at,
              duration=duration,
              status=call_status,
              ended_by=session.get("ended_by", "unknown"),
              conversation_history=session["conversation_history"],
              recording_url=form_data.get("RecordingUrl"),
              data_collected=session.get("data_collected", {})
          )

          # Clean up session
          del active_sessions[call_sid]
  ```

### 7.4 Database Function
- [ ] **Implement `save_call_to_database()`**
  ```python
  async def save_call_to_database(
      call_sid: str,
      agent_id: str,
      recipient_number: str,
      started_at: datetime,
      ended_at: datetime,
      duration: float,
      status: str,
      ended_by: str,
      conversation_history: list,
      recording_url: str,
      data_collected: dict
  ):
      """Save completed call data to calls table"""
      # Insert into calls table with all metadata
      # PK = call_sid or agent_id, SK = timestamp?
      pass
  ```

**Implementation Steps:**
1. [ ] Implement goodbye intent detection
2. [ ] Add hangup logic in `/voice/process-speech`
3. [ ] Implement timeout tracking
4. [ ] Create `save_call_to_database()` function
5. [ ] Update `/call-status` to save data on call completion
6. [ ] Test various call ending scenarios

**Database Schema for `calls` Table:**
```
calls_table = {
    "PK": "call_sid" or "agent_id",  # TBD
    "SK": "timestamp" or "call_sid", # TBD
    "agent_id": str,
    "recipient_number": str,
    "started_at": timestamp,
    "ended_at": timestamp,
    "duration": float,
    "status": str,  # completed, failed, etc.
    "ended_by": str,  # user, system_timeout, system_complete
    "conversation_history": list[dict],
    "recording_url": str,
    "recording_sid": str,
    "data_collected": dict,
    "created_at": timestamp,
    "updated_at": timestamp
}
```

---

## 8. Save Conversation & Recording in `calls` Table

### Task
Persist conversation transcripts and audio recordings.

### Implementation
- [ ] **Conversation History Format**
  ```python
  conversation_history = [
      {
          "role": "assistant",
          "content": "Hello! How can I help you?",
          "timestamp": "2024-01-25T14:30:00Z"
      },
      {
          "role": "user",
          "content": "I need information",
          "timestamp": "2024-01-25T14:30:05Z",
          "confidence": 0.95,
          "recording_url": "https://..."
      }
  ]
  ```

- [ ] **Recording Data**
  ```python
  recording_data = {
      "recording_url": form_data.get("RecordingUrl"),
      "recording_sid": form_data.get("RecordingSid"),
      "recording_duration": form_data.get("RecordingDuration"),
      "recording_status": "available"  # or "processing"
  }
  ```

- [ ] **Save Both Together**
  ```python
  # In save_call_to_database()
  call_record = {
      # ... other fields ...
      "conversation_history": json.dumps(conversation_history),  # Serialize for DB
      "recording_url": recording_url,
      "recording_sid": recording_sid,
      "recording_duration": recording_duration
  }
  ```

**Considerations:**
- [ ] Should conversation_history be stored as JSON string or separate table?
- [ ] Should recordings be downloaded and stored in S3, or just store Twilio URLs?
- [ ] How long do Twilio recordings persist? Need to archive?
- [ ] Implement webhook for `recording_status_callback` to know when recording is ready?

---

## 9. Keep Running Conversation in Global Variable / Call Table

### Task
Decide where to store live conversation state during active calls.

### Option A: In-Memory Global Variable (Current)
**Pros:**
- Fast access
- Simple implementation
- Already implemented in `active_sessions`

**Cons:**
- Lost on server restart
- Not scalable to multiple servers
- No persistence during call

**Current Implementation:**
```python
active_sessions[call_sid] = {
    "to": "+1234567890",
    "from": "+0987654321",
    "conversation_history": [...],
    "agent_data": {...},
    # ... everything in memory
}
```

### Option B: Store in Database During Call
**Pros:**
- Persisted immediately
- Survives server restarts
- Scalable across multiple servers

**Cons:**
- Database write overhead on every message
- Slightly slower
- Need to handle concurrent updates

**Implementation:**
```python
# After each speech exchange
await update_call_conversation(
    call_sid=call_sid,
    new_messages=[user_message, assistant_message]
)

# Fetch on each request
conversation = await get_call_conversation(call_sid)
```

### Option C: Hybrid Approach (Recommended)
**Strategy:**
- Keep `active_sessions` in memory for fast access during call
- Periodically sync to database (every N messages or every M seconds)
- Full save on call completion

**Implementation:**
```python
# In-memory for speed
active_sessions[call_sid] = {...}

# Periodic sync (every 5 messages or 60 seconds)
if len(session["conversation_history"]) % 5 == 0:
    await sync_session_to_database(call_sid)

# Full save on completion in /call-status
```

**Decision Needed:**
- [ ] Choose approach: A, B, or C?
- [ ] If C, define sync frequency
- [ ] Implement chosen approach

---

## 10. ~~Post-Call Data Processing~~ (IGNORE FOR NOW)

**Note:** This section is marked as "IGNORE NOW" but documented for future reference.

### Future Task
After call ends, process `data_to_fill` and save to separate analytics/dashboard table.

**Planned Schema:**
```
dashboard_table = {
    "PK": "agent_id",
    "SK": "recipient_number",
    "data_collected": {
        "name": "John Doe",
        "email": "john@example.com",
        "issue": "billing question"
    },
    "last_call_timestamp": timestamp,
    "total_calls": int,
    "updated_at": timestamp
}
```

**Future Implementation:**
```python
# After call completion
if call_status == "completed":
    await update_dashboard_data(
        agent_id=session["agent_id"],
        recipient_number=session["to"],
        data_collected=session["data_collected"]
    )
```

---

## Implementation Priority Order

### Phase 1: Foundation (Do First)
1. ✅ Understand DB schema & GSI logic
2. ✅ Understand `twilio_client.calls.create()` parameters
3. ✅ Master three key endpoints

### Phase 2: Agent Integration
4. ☐ Implement `/voice/outbound` with agent data fetching
5. ☐ Implement `/voice/process-speech` with session reuse
6. ☐ Fetch past conversations (optimization)

### Phase 3: Call Lifecycle Management
7. ☐ Implement call termination logic
8. ☐ Save conversation & recordings to database
9. ☐ Decide on and implement conversation storage strategy

### Phase 4: Future Enhancements (Later)
10. ~~Post-call data processing to dashboard table~~ (IGNORE NOW)

---

## Questions to Resolve

### Database Schema
- [ ] What is the exact structure of `agents` table? (PK, SK, fields)
- [ ] What is the exact structure of `calls` table? (PK, SK, fields)
- [ ] What GSIs exist and what queries do they enable?
- [ ] Is there a separate `recipients` table or is data in `calls`?

### Agent ID Passing
- [ ] How is `agent_id` passed to `/voice/outbound`?
  - Option A: Query parameter in URL: `/voice/outbound?agent_id=123`
  - Option B: Store in `calls` table when creating call in `/make-call`
  - Option C: Custom parameter via Twilio Stream

### Conversation Storage Strategy
- [ ] In-memory only, database only, or hybrid?
- [ ] If hybrid, what's the sync frequency?

### Recording Management
- [ ] Store Twilio URLs or download to S3?
- [ ] How long to retain recordings?
- [ ] Need transcript of recordings?

---

## Files to Modify

- `app.py` - Main changes to endpoints
- `config.py` - Add database connection settings
- Create `database.py` - Database query functions
- Create `agent_manager.py` - Agent data management
- Create `call_manager.py` - Call lifecycle management
- Update `.env` - Add database credentials

---

## Testing Checklist

- [ ] Test fetching agent data for valid agent_id
- [ ] Test fetching agent data for invalid agent_id (error handling)
- [ ] Test fetching past conversations
- [ ] Test session data reuse (no duplicate fetches)
- [ ] Test user-initiated call end
- [ ] Test system-initiated call end (timeout)
- [ ] Test conversation saving to database
- [ ] Test recording URL storage
- [ ] Verify call duration calculation
- [ ] Test with multiple concurrent calls
- [ ] Test server restart (conversation recovery if applicable)

---

## Notes & Considerations

- Ensure all database queries are async for performance
- Handle database connection failures gracefully
- Implement retry logic for critical database operations
- Log all important events for debugging
- Consider rate limiting on database queries
- Implement caching for frequently accessed agent data
- Monitor database query performance
- Plan for horizontal scaling (if using in-memory sessions, need Redis or similar)

---

**Created:** 2026-01-25
**Last Updated:** 2026-01-25
**Status:** Initial Draft
