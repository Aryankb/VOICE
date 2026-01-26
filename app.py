import base64
import json
import asyncio
import logging
from datetime import datetime
from typing import Dict, Optional, Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Response, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Start, Stream, Dial, Say
from config import settings
import tempfile
import subprocess
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Twilio Voice AI Assistant")

# Initialize Twilio client
twilio_client = Client(settings.twilio_account_sid, settings.twilio_auth_token)

# Store active call sessions
active_sessions: Dict[str, dict] = {}

# Create TTS output directory if it doesn't exist
import pathlib
tts_output_path = pathlib.Path(settings.tts_output_dir)
tts_output_path.mkdir(parents=True, exist_ok=True)


async def add_voice_response(
    response: VoiceResponse,
    text: str,
    voice: str = "Polly.Joanna",
    language: str = "en-US"
) -> VoiceResponse:
    """
    Add voice response to TwiML - uses local TTS if enabled, otherwise Twilio TTS

    Args:
        response: TwiML VoiceResponse object
        text: Text to speak
        voice: Twilio voice name (used only if local TTS disabled)
        language: Language code

    Returns:
        Updated VoiceResponse object
    """
    if settings.use_local_tts:
        try:
            from local_tts_client import get_tts_client
            tts_client = get_tts_client()

            # Generate audio file
            audio_file = await tts_client.generate_speech(text, language, voice)

            # Get filename from path
            filename = pathlib.Path(audio_file).name

            # Use public URL to serve the file
            audio_url = f"{settings.public_url}/tts/{filename}"

            logger.info(f"Using local TTS: {audio_url}")

            # Play the generated audio
            response.play(audio_url)

        except Exception as e:
            logger.error(f"Local TTS failed: {e}. Falling back to Twilio TTS.")
            # Fallback to Twilio TTS
            response.say(text, voice=voice, language=language)
    else:
        # Use Twilio's built-in TTS
        response.say(text, voice=voice, language=language)

    return response


# class AudioBuffer:
#     """Buffers audio chunks and detects silence"""
    
#     def __init__(self, call_sid: str, silence_threshold: float = 4.0):
#         self.call_sid = call_sid
#         self.silence_threshold = silence_threshold
#         self.audio_chunks = []
#         self.last_audio_timestamp = None
#         self.is_speaking = False
#         self.silence_start_time = None
        
#     def add_chunk(self, audio_data: bytes, timestamp: float):
#         """Add audio chunk to buffer"""
#         self.audio_chunks.append(audio_data)
#         self.last_audio_timestamp = timestamp
        
#         # Detect speech (simple energy-based detection)
#         # In production, use a proper VAD (Voice Activity Detection) library
#         is_silent = self._is_silence(audio_data)
        
#         if not is_silent:
#             self.is_speaking = True
#             self.silence_start_time = None
#         elif self.is_speaking and is_silent:
#             if self.silence_start_time is None:
#                 self.silence_start_time = timestamp
                
#     def _is_silence(self, audio_data: bytes) -> bool:
#         """Basic silence detection based on audio energy"""
#         # Convert bytes to integers and calculate RMS energy
#         if len(audio_data) == 0:
#             return True
            
#         # Simple energy threshold (you may want to adjust this)
#         energy = sum(abs(b - 128) for b in audio_data) / len(audio_data)
#         return energy < 10  # Threshold for silence
        
#     def check_silence_duration(self, current_time: float) -> bool:
#         """Check if silence threshold has been reached"""
#         if self.silence_start_time is None:
#             return False
            
#         silence_duration = current_time - self.silence_start_time
#         return silence_duration >= self.silence_threshold
        
#     def get_buffered_audio(self) -> bytes:
#         """Get all buffered audio as bytes"""
#         return b''.join(self.audio_chunks)
        
#     def clear_buffer(self):
#         """Clear the audio buffer"""
#         self.audio_chunks = []
#         self.is_speaking = False
#         self.silence_start_time = None


@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "ok",
        "message": "Twilio Voice AI Assistant is running",
        "active_sessions": len(active_sessions),
        "public_url": settings.public_url,
        "local_llm_enabled": settings.use_local_llm,
        "local_tts_enabled": settings.use_local_tts
    }


@app.get("/health/local")
async def health_check_local():
    """Health check for local LLM and TTS"""
    status = {
        "llm": {"enabled": settings.use_local_llm, "healthy": False, "error": None},
        "tts": {"enabled": settings.use_local_tts, "healthy": False, "error": None}
    }

    # Check LLM
    if settings.use_local_llm:
        try:
            from local_llm_client import get_llm_client
            llm_client = get_llm_client()
            status["llm"]["healthy"] = await llm_client.health_check()
            status["llm"]["model"] = settings.ollama_model
        except Exception as e:
            status["llm"]["error"] = str(e)

    # Check TTS
    if settings.use_local_tts:
        try:
            from local_tts_client import get_tts_client
            tts_client = get_tts_client()
            status["tts"]["healthy"] = await tts_client.health_check()
            status["tts"]["engine"] = settings.tts_engine
        except Exception as e:
            status["tts"]["error"] = str(e)

    return status


@app.get("/tts/{filename}")
async def serve_tts_file(filename: str):
    """Serve generated TTS audio files"""
    file_path = tts_output_path / filename

    # Security: Only serve files from TTS output directory
    if not file_path.exists() or not str(file_path).startswith(str(tts_output_path)):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        file_path,
        media_type="audio/wav",
        headers={"Content-Disposition": f"inline; filename={filename}"}
    )


@app.get("/sessions")
async def get_sessions():
    """Get active call sessions"""
    return {
        "active_sessions": len(active_sessions),
        "sessions": {
            call_sid: {
                "to": session.get("to"),
                "from": session.get("from"),
                "started_at": session.get("started_at"),
                "message_count": len(session.get("conversation_history", []))
            }
            for call_sid, session in active_sessions.items()
        }
    }


@app.get("/session/{call_sid}")
async def get_session(call_sid: str):
    """Get specific call session details"""
    if call_sid not in active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return active_sessions[call_sid]


# @app.post("/voice/incoming")
# async def incoming_call(request: Request):
#     """Handle incoming calls - return TwiML to start streaming"""
#     form_data = await request.form()
#     call_sid = form_data.get("CallSid")
#     from_number = form_data.get("From")
    
#     logger.info(f"Incoming call from {from_number}, CallSid: {call_sid}")
    
#     # Create TwiML response with Stream
#     response = VoiceResponse()
#     # fetch custom intro from database or config if needed
#     response.say("Hello! I'm your AI assistant. What is your preference language?", voice="Polly.Joanna", language="en-US")
    
#     # Start streaming audio to our WebSocket
#     start = Start()
#     stream = Stream(url=f"wss://{settings.public_url.replace('https://', '')}/media")
#     stream.parameter(name="call_sid", value=call_sid)
#     start.append(stream)
#     response.append(start)
    
#     # Keep the call alive
#     response.pause(length=60)
    
#     return Response(content=str(response), media_type="application/xml")


@app.post("/voice/outbound")
async def outbound_call_twiml(request: Request):
    """TwiML for outbound calls - initial greeting with agent data loading"""
    form_data = await request.form()
    call_sid = form_data.get("CallSid")

    # Get agent_id from query params
    agent_id = request.query_params.get("agent_id")

    logger.info(f"Outbound call answered: {call_sid}, agent: {agent_id}")

    response = VoiceResponse()

    # Default values (fallback if DynamoDB disabled or agent not found)
    greeting = "Hello! I'm your AI assistant. What is your preference language?"
    voice = "Polly.Joanna"
    language = "en-US"
    gather_language = "hi-IN"

    try:
        # FETCH ONCE - Load agent data and past conversations if DynamoDB enabled
        if settings.enable_dynamodb and agent_id:
            from agent_manager import get_agent
            from call_manager import fetch_past_conversations, create_call_record

            # Fetch agent configuration
            agent_data = await get_agent(agent_id)

            # Get recipient phone from session or form data
            recipient_phone = form_data.get("To") or active_sessions.get(call_sid, {}).get("to")

            # Fetch past conversations for this agent-recipient pair
            past_conversations = await fetch_past_conversations(
                agent_id=agent_id,
                recipient_phone=recipient_phone,
                limit=5
            )

            # Create initial call record in database
            await create_call_record(
                call_sid=call_sid,
                agent_id=agent_id,
                recipient_phone=recipient_phone,
                caller_phone=form_data.get("From") or settings.twilio_phone_number,
                status="in-progress"
            )

            # UPDATE SESSION with all fetched data
            if call_sid in active_sessions:
                active_sessions[call_sid].update({
                    "agent_id": agent_id,
                    "agent_data": agent_data.model_dump(),  # Store as dict for JSON serialization
                    "past_conversations": [pc.model_dump() for pc in past_conversations],
                    "data_collected": {},
                    "message_count": 0,
                    "last_sync_count": 0,
                    "no_input_count": 0
                })

                # Use agent's configuration for greeting
                greeting = agent_data.greeting
                voice = agent_data.voice
                language = agent_data.language
                gather_language = agent_data.language

                logger.info(
                    f"Loaded agent data for {call_sid}: {agent_data.name}, "
                    f"past_conversations={len(past_conversations)}"
                )

    except Exception as e:
        logger.error(f"Error loading agent data for {call_sid}: {e}")
        # Continue with defaults (graceful degradation)

    # Initial greeting
    response.say(greeting, voice=voice, language=language)

    # Use Gather to capture speech input
    gather = response.gather(
        input="speech",
        action=f"{settings.public_url}/voice/process-speech",
        method="POST",
        speech_timeout=3,  # Wait 3 seconds of silence before processing
        language=gather_language,
        hints="help, information, question, support",
        speech_model="experimental_conversations",  # Better conversation model
        enhanced=True  # Enhanced speech recognition
    )

    # If no input is received
    response.say(
        "I didn't hear anything. Please try again or hang up.",
        voice=voice
    )
    response.redirect(f"{settings.public_url}/voice/outbound?agent_id={agent_id}")

    return Response(content=str(response), media_type="application/xml")


@app.post("/make-call")
async def make_call(request: Request):
    """
    Initiate an outbound call

    Request body:
        agent_id: Agent identifier (REQUIRED)
        to_number: Phone number to call (E.164 format, e.g., +1234567890)
        from_number: Optional Twilio number to call from (defaults to configured number)
        initial_message: Optional custom greeting message (overrides agent greeting)
    """
    try:
        body = await request.json()
        agent_id = body.get("agent_id")
        to_number = body.get("to_number")
        from_number = body.get("from_number") or settings.twilio_phone_number
        initial_message = body.get("initial_message")

        # Validate required fields
        if not agent_id:
            raise HTTPException(status_code=400, detail="agent_id is required")
        if not to_number:
            raise HTTPException(status_code=400, detail="to_number is required")

        # Validate agent exists (only if DynamoDB is enabled)
        if settings.enable_dynamodb:
            from agent_manager import get_agent
            try:
                agent = await get_agent(agent_id)
                logger.info(f"Validated agent {agent_id}: {agent.name}")
            except Exception as e:
                logger.error(f"Agent validation failed: {e}")
                raise HTTPException(
                    status_code=404,
                    detail=f"Agent {agent_id} not found or invalid"
                )

        # Store initial message in session if provided
        session_data = {}
        if initial_message:
            session_data["initial_message"] = initial_message

        # Create call with TwiML URL (pass agent_id as query param)
        call = twilio_client.calls.create(
            to=to_number,
            from_=from_number,
            url=f"{settings.public_url}/voice/outbound?agent_id={agent_id}",
            status_callback=f"{settings.public_url}/call-status",
            status_callback_event=["initiated", "ringing", "answered", "completed"],
            machine_detection="DetectMessageEnd",  # Detect answering machines
            record=True
        )

        # Store minimal session data (full data loaded in /voice/outbound)
        active_sessions[call.sid] = {
            "agent_id": agent_id,
            "to": to_number,
            "from": from_number,
            "conversation_history": [],
            "started_at": datetime.now().isoformat(),
            **session_data
        }

        logger.info(f"Call initiated: {call.sid} to {to_number} with agent {agent_id}")

        return {
            "success": True,
            "call_sid": call.sid,
            "status": call.status,
            "to": to_number,
            "from": from_number,
            "agent_id": agent_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error making call: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/voice/process-speech")
async def process_speech(request: Request):
    """Process speech input from caller with conversation management"""
    form_data = await request.form()
    call_sid = form_data.get("CallSid")
    speech_result = form_data.get("SpeechResult", "")
    confidence = form_data.get("Confidence", "0.0")
    recording_url = form_data.get("RecordingUrl", "")  # Audio file URL
    recording_sid = form_data.get("RecordingSid", "")  # Recording ID

    logger.info(f"Speech from {call_sid}: '{speech_result}' (confidence: {confidence})")

    response = VoiceResponse()

    # ACCESS SESSION (no DB fetch - data already loaded in /voice/outbound)
    if call_sid not in active_sessions:
        logger.error(f"Session not found for {call_sid}")
        response.say("I'm sorry, session expired. Goodbye.", voice="Polly.Joanna")
        response.hangup()
        return Response(content=str(response), media_type="application/xml")

    session = active_sessions[call_sid]

    # Get agent data from session (already loaded)
    agent_data = session.get("agent_data", {})
    voice = agent_data.get("voice", "Polly.Joanna")
    language = agent_data.get("language", "en-US")

    # Handle empty input
    if not speech_result:
        session["no_input_count"] = session.get("no_input_count", 0) + 1

        # Check if we have all required data
        data_to_fill = agent_data.get("data_to_fill", {})
        data_collected = session.get("data_collected", {})
        all_data_collected = all(field in data_collected for field in data_to_fill.keys())

        # SMART TIMEOUT: Check if we have all data before ending
        if session["no_input_count"] >= 3:
            logger.info(f"System timeout for {call_sid}: 3 failed inputs, data_complete={all_data_collected}")

            if all_data_collected:
                # We have all the data, offer graceful exit
                response.say(
                    "I'm having trouble hearing you. We have all the information we need. "
                    "If there's anything else I can help with, please let me know. Otherwise, have a great day! Goodbye.",
                    voice=voice
                )
            else:
                # Missing data, but can't hear user - be helpful
                response.say(
                    "I'm having trouble hearing you clearly. "
                    "If you need assistance, please try calling back when you're in a quieter location. "
                    "Goodbye for now.",
                    voice=voice
                )

            response.hangup()
            session["ended_by"] = "system_timeout"
            return Response(content=str(response), media_type="application/xml")

        # First or second failed attempt - encourage user
        if session["no_input_count"] == 1:
            response.say("I didn't hear anything. Please speak a bit louder.", voice=voice)
        else:
            response.say("I'm still having trouble hearing you. Could you speak more clearly?", voice=voice)

        response.redirect(f"{settings.public_url}/voice/process-speech")
        return Response(content=str(response), media_type="application/xml")

    # Reset no_input_count on successful input
    session["no_input_count"] = 0

    # CHECK CONFIDENCE LEVEL
    CONFIDENCE_THRESHOLD = 0.6
    if float(confidence) < CONFIDENCE_THRESHOLD:
        logger.warning(f"Low confidence ({confidence}) for: '{speech_result}'")
        session["low_confidence_count"] = session.get("low_confidence_count", 0) + 1

        # If consistently low confidence, ask user to speak clearer
        if session["low_confidence_count"] >= 2:
            response.say(
                "I'm having a bit of trouble understanding you clearly. "
                "Could you please speak a bit louder or find a quieter location? "
                "What did you say?",
                voice=voice
            )
            session["low_confidence_count"] = 0  # Reset after asking
            response.redirect(f"{settings.public_url}/voice/process-speech")
            return Response(content=str(response), media_type="application/xml")
    else:
        # Reset low confidence count on good input
        session["low_confidence_count"] = 0

    # DETECT GOODBYE INTENT
    from session_manager import detect_goodbye_intent, is_data_collection_complete

    if detect_goodbye_intent(speech_result):
        logger.info(f"Goodbye intent detected for {call_sid}")
        response.say("Thank you for calling. Have a great day! Goodbye.", voice=voice)
        response.hangup()
        session["ended_by"] = "user"

        # Sync final state to DB
        if settings.enable_dynamodb:
            from session_manager import sync_session_to_db
            await sync_session_to_db(call_sid, active_sessions, force=True)

        return Response(content=str(response), media_type="application/xml")

    # APPEND USER MESSAGE to conversation history
    from decimal import Decimal
    user_message = {
        "role": "user",
        "content": speech_result,
        "timestamp": datetime.now().isoformat(),
        "confidence": float(confidence),  # Keep as float in memory
        "recording_url": recording_url,
        "recording_sid": recording_sid
    }
    session["conversation_history"].append(user_message)
    session["message_count"] = session.get("message_count", 0) + 1

    # Generate AI response
    try:
        ai_response = await generate_ai_response_sync(
            user_input=speech_result,
            call_sid=call_sid,
            session=session
        )

        # APPEND AI RESPONSE to conversation history
        assistant_message = {
            "role": "assistant",
            "content": ai_response,
            "timestamp": datetime.now().isoformat()
        }
        session["conversation_history"].append(assistant_message)
        session["message_count"] = session.get("message_count", 0) + 1

        # PERIODIC SYNC to DynamoDB every N messages
        if settings.enable_dynamodb:
            from session_manager import sync_session_to_db

            if session["message_count"] % settings.session_sync_frequency == 0:
                logger.info(f"Periodic sync triggered for {call_sid} at {session['message_count']} messages")
                await sync_session_to_db(call_sid, active_sessions)

        # CHECK DATA COLLECTION COMPLETION
        # Don't auto-hangup - let conversation flow naturally
        # Just track that data is complete for graceful exit options
        if is_data_collection_complete(session):
            if not session.get("data_complete_announced"):
                logger.info(f"Data collection complete for {call_sid} - marking for graceful exit")
                session["data_complete_announced"] = True

        # Speak the response
        response.say(ai_response, voice=voice)

        # Wait for more input
        gather = response.gather(
            input="speech",
            action=f"{settings.public_url}/voice/process-speech",
            method="POST",
            speech_timeout=3,
            language=language,
            hints="help, information, question, support, goodbye, thanks",
            speech_model="experimental_conversations",
            enhanced=True
        )

        # If no more input
        response.say("Is there anything else I can help you with?", voice=voice)
        response.redirect(f"{settings.public_url}/voice/process-speech")

    except Exception as e:
        logger.error(f"Error processing speech: {str(e)}", exc_info=True)
        response.say(
            "I'm sorry, I encountered an error. Please try again.",
            voice="Polly.Joanna"
        )
        response.hangup()
        session["ended_by"] = "error"

    return Response(content=str(response), media_type="application/xml")


@app.post("/call-status")
async def call_status(request: Request):
    """Webhook for call status updates with finalization and S3 upload"""
    form_data = await request.form()
    call_sid = form_data.get("CallSid")
    call_status = form_data.get("CallStatus")
    answered_by = form_data.get("AnsweredBy")  # human or machine
    recording_url = form_data.get("RecordingUrl")
    recording_sid = form_data.get("RecordingSid")
    call_duration = form_data.get("CallDuration")

    logger.info(f"Call {call_sid} status: {call_status}, answered_by: {answered_by}")

    # Handle answering machine detection
    if answered_by == "machine_start":
        logger.info(f"Call {call_sid} answered by machine")

    # Finalize call when it ends
    if call_status in ["completed", "failed", "busy", "no-answer", "canceled"]:
        if call_sid in active_sessions:
            session = active_sessions[call_sid]

            # Calculate duration
            duration_seconds = None
            if call_duration:
                try:
                    duration_seconds = int(call_duration)
                except ValueError:
                    pass

            if not duration_seconds and session.get("started_at"):
                try:
                    started_at = datetime.fromisoformat(session["started_at"])
                    duration_seconds = int((datetime.now() - started_at).total_seconds())
                except Exception:
                    pass

            # Download recording to S3 if enabled
            s3_url = None
            if settings.enable_dynamodb and settings.enable_s3_upload and recording_url:
                try:
                    from s3_uploader import s3_uploader
                    logger.info(f"Uploading recording to S3 for {call_sid}")
                    s3_url = await s3_uploader.download_and_upload_recording(
                        recording_url=recording_url,
                        call_sid=call_sid
                    )
                    if s3_url:
                        logger.info(f"Recording uploaded to S3: {s3_url}")
                except Exception as e:
                    logger.error(f"Failed to upload recording to S3: {e}")

            # Finalize call in database
            if settings.enable_dynamodb:
                try:
                    from call_manager import finalize_call
                    from models import ConversationMessage

                    # Convert conversation_history to ConversationMessage objects
                    conversation_history = [
                        ConversationMessage(**msg) if isinstance(msg, dict) else msg
                        for msg in session.get("conversation_history", [])
                    ]

                    await finalize_call(
                        call_sid=call_sid,
                        status=call_status,
                        ended_at=datetime.now().isoformat(),
                        duration_seconds=duration_seconds,
                        ended_by=session.get("ended_by", "unknown"),
                        conversation_history=conversation_history,
                        call_recording_url=recording_url,
                        call_recording_sid=recording_sid,
                        s3_recording_url=s3_url,
                        data_collected=session.get("data_collected", {}),
                        answered_by=answered_by
                    )

                    logger.info(
                        f"Finalized call {call_sid} in DB: "
                        f"status={call_status}, duration={duration_seconds}s, "
                        f"messages={len(conversation_history)}"
                    )

                except Exception as e:
                    logger.error(f"Failed to finalize call {call_sid} in DB: {e}")

            # Log conversation history before cleanup
            logger.info(
                f"Call {call_sid} completed: "
                f"{len(session.get('conversation_history', []))} messages, "
                f"ended_by={session.get('ended_by', 'unknown')}"
            )

            # Cleanup session from memory
            del active_sessions[call_sid]
            logger.info(f"Cleaned up session for call {call_sid}")

    return {"status": "ok"}


# @app.websocket("/media")
# async def websocket_endpoint(websocket: WebSocket):
#     """WebSocket endpoint for receiving Twilio media streams"""
#     await websocket.accept()
#     logger.info("WebSocket connection accepted")
    
#     call_sid = None
#     audio_buffer = None
    
#     try:
#         while True:
#             message = await websocket.receive_text()
#             data = json.loads(message)
            
#             event_type = data.get("event")
            
#             if event_type == "connected":
#                 logger.info(f"Connected event: {data}")
                
#             elif event_type == "start":
#                 logger.info(f"Start event: {data}")
#                 call_sid = data.get("start", {}).get("callSid")
                
#                 if call_sid:
#                     # Initialize audio buffer for this call
#                     audio_buffer = AudioBuffer(
#                         call_sid=call_sid,
#                         silence_threshold=settings.silence_threshold_seconds
#                     )
#                     active_sessions[call_sid] = {
#                         "websocket": websocket,
#                         "buffer": audio_buffer,
#                         "stream_sid": data.get("start", {}).get("streamSid"),
#                         "started_at": datetime.now().isoformat()
#                     }
#                     logger.info(f"Session created for call {call_sid}")
                    
#             elif event_type == "media":
#                 if audio_buffer is None:
#                     continue
                    
#                 # Get the base64 encoded audio payload
#                 payload = data.get("media", {}).get("payload")
#                 timestamp = data.get("media", {}).get("timestamp", 0)
                
#                 if payload:
#                     # Decode the audio chunk
#                     audio_chunk = base64.b64decode(payload)
                    
#                     # Add to buffer
#                     audio_buffer.add_chunk(audio_chunk, float(timestamp) / 1000.0)
                    
#                     # Check if silence threshold is reached
#                     current_time = float(timestamp) / 1000.0
#                     if audio_buffer.check_silence_duration(current_time):
#                         logger.info(f"Silence detected for {settings.silence_threshold_seconds}s")
                        
#                         # Get buffered audio
#                         buffered_audio = audio_buffer.get_buffered_audio()
                        
#                         # Process the audio (transcribe + generate response)
#                         await process_audio_and_respond(
#                             call_sid=call_sid,
#                             audio_data=buffered_audio,
#                             websocket=websocket
#                         )
                        
#                         # Clear buffer
#                         audio_buffer.clear_buffer()
                        
#             elif event_type == "stop":
#                 logger.info(f"Stop event: {data}")
#                 break
                
#     except WebSocketDisconnect:
#         logger.info("WebSocket disconnected")
#     except Exception as e:
#         logger.error(f"WebSocket error: {str(e)}", exc_info=True)
#     finally:
#         if call_sid and call_sid in active_sessions:
#             del active_sessions[call_sid]
#             logger.info(f"Session cleaned up for call {call_sid}")


# async def process_audio_and_respond(call_sid: str, audio_data: bytes, websocket: WebSocket):
#     """
#     Process the buffered audio, generate a response, and play it back
    
#     Args:
#         call_sid: The Twilio call SID
#         audio_data: Raw audio bytes (mulaw @ 8kHz)
#         websocket: WebSocket connection to send updates
#     """
#     logger.info(f"Processing {len(audio_data)} bytes of audio for call {call_sid}")
    
#     try:
#         # TODO: Integrate with speech-to-text service
#         # For now, we'll use a placeholder
#         transcription = await transcribe_audio(audio_data)
#         logger.info(f"Transcription: {transcription}")
        
#         # TODO: Generate AI response based on transcription
#         response_text = await generate_ai_response(transcription)
#         logger.info(f"AI Response: {response_text}")
        
#         # TODO: Convert response text to speech using MeloTTS
#         response_audio_url = await generate_tts(response_text)
#         logger.info(f"TTS audio URL: {response_audio_url}")
        
#         # Update the call to play the response
#         await play_audio_on_call(call_sid, response_audio_url)
        
#     except Exception as e:
#         logger.error(f"Error processing audio: {str(e)}", exc_info=True)


# async def transcribe_audio(audio_data: bytes) -> str:
#     """
#     Transcribe audio to text
    
#     TODO: Integrate with a speech-to-text service:
#     - Google Cloud Speech-to-Text
#     - Amazon Transcribe
#     - Azure Speech Services
#     - OpenAI Whisper
#     """
#     # Placeholder implementation
#     await asyncio.sleep(0.1)
#     return "[Transcription placeholder - integrate STT service here]"


# async def generate_ai_response(transcription: str) -> str:
#     """
#     Generate AI response based on transcription
    
#     TODO: Integrate with LLM service:
#     - OpenAI GPT
#     - Anthropic Claude
#     - Local LLM
#     """
#     # Placeholder implementation
#     await asyncio.sleep(0.1)
#     return "Thank you for your message. I'm processing your request."


async def generate_ai_response_sync(
    user_input: str,
    call_sid: str,
    session: Optional[Dict[str, Any]] = None
) -> str:
    """
    Generate AI response based on user input with full context

    Args:
        user_input: The user's speech input
        call_sid: Call SID for logging
        session: Session dict with agent_data, conversation_history, past_conversations

    Returns:
        AI-generated response text
    """
    # Get session data
    if session is None:
        session = active_sessions.get(call_sid, {})

    # Get agent configuration
    agent_data = session.get("agent_data", {})
    agent_prompt = agent_data.get("prompt", "You are a helpful AI assistant.")
    few_shot = agent_data.get("few_shot", [])
    data_to_fill = agent_data.get("data_to_fill", {})
    agent_language = agent_data.get("language", "en-US")

    # Get conversation context
    conversation_history = session.get("conversation_history", [])
    past_conversations = session.get("past_conversations", [])
    data_collected = session.get("data_collected", {})

    # USE OPENAI IF ENABLED
    if settings.use_openai and settings.openai_api_key:
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=settings.openai_api_key)

            # Build context from past conversations
            context_summary = ""
            if past_conversations:
                context_summary = f"\n\nContext: Customer has called {len(past_conversations)} time(s) before."
                if past_conversations[0].get("data_collected"):
                    context_summary += f" We have their contact info: {past_conversations[0]['data_collected']}"

            # Add data collection requirements
            data_context = ""
            if data_to_fill:
                missing_fields = [name for name in data_to_fill.keys() if name not in data_collected]
                if missing_fields:
                    data_context = f"\n\nIMPORTANT: After helping the customer, collect: {', '.join(missing_fields)}"
                    data_context += f"\nAlready collected: {list(data_collected.keys())}"

            # Build messages for OpenAI
            messages = [
                {"role": "system", "content": f"{agent_prompt}{context_summary}{data_context}"}
            ]

            # Add few-shot examples
            for example in few_shot:
                messages.append({"role": "user", "content": example.get("user", "")})
                messages.append({"role": "assistant", "content": example.get("assistant", "")})

            # Add conversation history (last 10 messages for context)
            for msg in conversation_history[-10:]:
                messages.append({
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", "")
                })

            # Add current user input
            messages.append({"role": "user", "content": user_input})

            # Call OpenAI
            logger.info(f"Calling OpenAI {settings.openai_model} for {call_sid}")
            response = await client.chat.completions.create(
                model=settings.openai_model,
                messages=messages,
                temperature=0.7,
                max_tokens=150  # Keep responses concise for phone calls
            )

            ai_response = response.choices[0].message.content
            logger.info(f"OpenAI response for {call_sid}: {ai_response[:100]}...")

            # Check if response contains data - try to extract it
            if data_to_fill:
                for field_name in data_to_fill.keys():
                    if field_name not in data_collected:
                        # Simple extraction - look for the field name in user input
                        if field_name.lower() in user_input.lower():
                            # Use OpenAI to extract the value
                            extraction_messages = [
                                {"role": "system", "content": f"Extract only the {field_name} from the user's message. Return ONLY the value, nothing else. If not found, return 'NOT_FOUND'."},
                                {"role": "user", "content": user_input}
                            ]
                            extraction_response = await client.chat.completions.create(
                                model="gpt-3.5-turbo",  # Use cheaper model for extraction
                                messages=extraction_messages,
                                temperature=0,
                                max_tokens=50
                            )
                            extracted_value = extraction_response.choices[0].message.content.strip()

                            if extracted_value != "NOT_FOUND" and len(extracted_value) > 0:
                                data_collected[field_name] = extracted_value
                                session["data_collected"] = data_collected
                                logger.info(f"Extracted {field_name}: {extracted_value}")

            return ai_response

        except Exception as e:
            logger.error(f"OpenAI error: {e}. Falling back to local LLM.")
            # Fall through to local LLM logic below

    # USE LOCAL LLM IF ENABLED
    if settings.use_local_llm:
        try:
            from local_llm_client import get_llm_client
            llm_client = get_llm_client()

            # Build context from past conversations
            context_summary = ""
            if past_conversations:
                context_summary = f"\n\nContext: Customer has called {len(past_conversations)} time(s) before."
                if past_conversations[0].get("data_collected"):
                    context_summary += f" We have their contact info: {past_conversations[0]['data_collected']}"

            # Add data collection requirements
            data_context = ""
            if data_to_fill:
                missing_fields = [name for name in data_to_fill.keys() if name not in data_collected]
                if missing_fields:
                    data_context = f"\n\nIMPORTANT: After helping the customer, collect: {', '.join(missing_fields)}"
                    data_context += f"\nAlready collected: {list(data_collected.keys())}"

            # Build messages for local LLM (same format as OpenAI)
            messages = [
                {"role": "system", "content": f"{agent_prompt}{context_summary}{data_context}"}
            ]

            # Add few-shot examples
            for example in few_shot:
                messages.append({"role": "user", "content": example.get("user", "")})
                messages.append({"role": "assistant", "content": example.get("assistant", "")})

            # Add conversation history (last 10 messages for context)
            for msg in conversation_history[-10:]:
                messages.append({
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", "")
                })

            # Add current user input
            messages.append({"role": "user", "content": user_input})

            # Call local LLM
            logger.info(f"Calling local LLM {settings.ollama_model} for {call_sid}")
            ai_response = await llm_client.chat(
                messages=messages,
                temperature=0.7,
                max_tokens=150  # Keep responses concise for phone calls
            )

            logger.info(f"Local LLM response for {call_sid}: {ai_response[:100]}...")

            # Check if response contains data - try to extract it
            if data_to_fill:
                for field_name in data_to_fill.keys():
                    if field_name not in data_collected:
                        # Simple extraction - look for the field name in user input
                        if field_name.lower() in user_input.lower():
                            # Use local LLM to extract the value
                            extracted_value = await llm_client.extract_field(user_input, field_name)

                            if extracted_value != "NOT_FOUND" and len(extracted_value) > 0:
                                data_collected[field_name] = extracted_value
                                session["data_collected"] = data_collected
                                logger.info(f"Extracted {field_name}: {extracted_value}")

            return ai_response

        except Exception as e:
            logger.error(f"Local LLM error: {e}. Falling back to placeholder responses.")
            # Fall through to placeholder logic below

    # FALLBACK: Placeholder responses if no LLM is enabled
    # TODO: Integrate with LLM (OpenAI, Claude, etc.)
    # Pass full context to LLM:
    # - agent_prompt: System prompt
    # - few_shot: Few-shot examples
    # - past_conversations: Previous calls with this user
    # - conversation_history: Current conversation
    # - data_to_fill: Data collection requirements
    # - data_collected: Data collected so far

    # For now, return contextual responses based on input
    user_lower = user_input.lower()

    # Check if we need to collect specific data
    for field_name, field_config in data_to_fill.items():
        if field_name not in data_collected:
            # Try to extract data from user input
            # TODO: Use LLM to extract structured data
            # For now, simple keyword matching
            if field_name.lower() in user_lower:
                data_collected[field_name] = user_input
                session["data_collected"] = data_collected
                logger.info(f"Collected data for {field_name}: {user_input}")

                # Ask for next required field
                next_field = next(
                    (name for name, cfg in data_to_fill.items() if name not in data_collected),
                    None
                )
                if next_field:
                    next_prompt = data_to_fill[next_field].get("prompt", f"Please provide your {next_field}")
                    return next_prompt
                else:
                    return "Thank you! I have all the information I need."

    # Get agent's language for responses
    agent_language = agent_data.get("language", "en-US")
    is_hindi = "hi" in agent_language.lower()

    # Default responses (placeholder until LLM integration)
    if "help" in user_lower:
        if is_hindi:
            return "मैं आपकी जानकारी, सवालों के जवाब या आपकी ज़रूरतों में मदद कर सकता हूँ। आप क्या जानना चाहेंगे?"
        else:
            return "I can help you with information, answer questions, or assist with your needs. What would you like to know?"
    elif "weather" in user_lower:
        if is_hindi:
            return "मैं एक AI सहायक हूँ। मौसम की जानकारी के लिए, कृपया मौसम की वेबसाइट देखें या मौसम सेवा से पूछें।"
        else:
            return "I'm an AI assistant. For weather information, please check a weather website or service."
    elif "time" in user_lower:
        now = datetime.now()
        if is_hindi:
            return f"वर्तमान समय {now.strftime('%I:%M %p')} है।"
        else:
            return f"The current time is {now.strftime('%I:%M %p')}."
    elif "date" in user_lower:
        now = datetime.now()
        if is_hindi:
            return f"आज {now.strftime('%A, %B %d, %Y')} है।"
        else:
            return f"Today is {now.strftime('%A, %B %d, %Y')}."
    elif any(word in user_lower for word in ["hello", "hi", "hey"]):
        if is_hindi:
            return "नमस्ते! मैं आज आपकी कैसे मदद कर सकता हूँ?"
        else:
            return "Hello! How can I help you today?"
    else:
        # Generic response with context awareness
        if is_hindi:
            return f"मैंने सुना कि आपने कहा: {user_input}। मैं मदद के लिए यहाँ हूँ। क्या आप कृपया अधिक विवरण दे सकते हैं?"
        else:
            return f"I heard you say: {user_input}. I'm here to help. Could you please provide more details or ask a specific question?"


async def generate_tts(text: str) -> str:
    """
    Generate speech from text using MeloTTS or other TTS service
    
    TODO: Integrate with MeloTTS:
    - Use the MeloTTS library in this project
    - Generate audio file
    - Upload to accessible URL (S3, etc.)
    - Return public URL
    """
    # Placeholder - return a Twilio demo URL
    await asyncio.sleep(0.1)
    return "http://demo.twilio.com/docs/voice.xml"


async def play_audio_on_call(call_sid: str, audio_url: str):
    """
    Update an active call to play audio
    
    Args:
        call_sid: The call SID to update
        audio_url: URL of the audio file to play
    """
    try:
        # Create TwiML to play the audio
        response = VoiceResponse()
        response.play(audio_url)
        response.pause(length=1)
        
        # Update the call with new TwiML
        call = twilio_client.calls(call_sid).update(
            twiml=str(response)
        )
        
        logger.info(f"Updated call {call_sid} to play audio: {audio_url}")
        
    except Exception as e:
        logger.error(f"Error updating call: {str(e)}", exc_info=True)


@app.post("/interrupt-call/{call_sid}")
async def interrupt_call(call_sid: str):
    """
    Interrupt/pause any audio currently playing on a call
    
    This endpoint can be called when the user starts speaking again
    """
    try:
        if call_sid not in active_sessions:
            raise HTTPException(status_code=404, detail="Call session not found")
        
        # Update call to stop current TwiML and listen
        response = VoiceResponse()
        response.pause(length=1)
        
        call = twilio_client.calls(call_sid).update(
            twiml=str(response)
        )
        
        logger.info(f"Interrupted call {call_sid}")
        
        return {"success": True, "call_sid": call_sid}
        
    except Exception as e:
        logger.error(f"Error interrupting call: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:app",
        host=settings.server_host,
        port=settings.server_port,
        reload=True,
        log_level="info"
    )
