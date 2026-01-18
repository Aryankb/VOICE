import base64
import json
import asyncio
import logging
from datetime import datetime
from typing import Dict, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Response, HTTPException
from fastapi.responses import HTMLResponse
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
        "public_url": settings.public_url
    }


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
    """TwiML for outbound calls - initial greeting"""
    form_data = await request.form()
    call_sid = form_data.get("CallSid")
    
    logger.info(f"Outbound call answered: {call_sid}")
    
    response = VoiceResponse()
    
    # Initial greeting
    response.say(
        "Hello! I'm your AI assistant. What is your preference language?",
        voice="Polly.Joanna",
        language="en-US"
    )
    
    # Use Gather to capture speech input
    gather = response.gather(
        input="speech",
        action=f"{settings.public_url}/voice/process-speech",
        method="POST",
        speech_timeout=3,  # Wait 3 seconds of silence before processing
        language="hi-IN",
        hints="help, information, question, support",
        speech_model="experimental_conversations",  # Better conversation model
        enhanced=True  # Enhanced speech recognition
    )
    
    # If no input is received
    response.say(
        "I didn't hear anything. Please try again or hang up.",
        voice="Polly.Joanna"
    )
    response.redirect(f"{settings.public_url}/voice/outbound")
    
    return Response(content=str(response), media_type="application/xml")


@app.post("/make-call")
async def make_call(request: Request):
    """
    Initiate an outbound call
    
    Request body:
        to_number: Phone number to call (E.164 format, e.g., +1234567890)
        from_number: Optional Twilio number to call from (defaults to configured number)
        initial_message: Optional custom greeting message
    """
    try:
        body = await request.json()
        to_number = body.get("to_number")
        from_number = body.get("from_number") or settings.twilio_phone_number
        initial_message = body.get("initial_message")
        
        if not to_number:
            raise HTTPException(status_code=400, detail="to_number is required")
        
        # Store initial message in session if provided
        session_data = {}
        if initial_message:
            session_data["initial_message"] = initial_message
            
        # Create call with TwiML URL
        call = twilio_client.calls.create(
            to=to_number,
            from_=from_number,
            url=f"{settings.public_url}/voice/outbound",
            status_callback=f"{settings.public_url}/call-status",
            status_callback_event=["initiated", "ringing", "answered", "completed"],
            machine_detection="DetectMessageEnd",  # Detect answering machines
            record=True
        )
        
        # Store session data
        active_sessions[call.sid] = {
            "to": to_number,
            "from": from_number,
            "conversation_history": [],
            "started_at": datetime.now().isoformat(),
            **session_data
        }
        
        logger.info(f"Call initiated: {call.sid} to {to_number}")
        
        return {
            "success": True,
            "call_sid": call.sid,
            "status": call.status,
            "to": to_number,
            "from": from_number
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error making call: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/voice/process-speech")
async def process_speech(request: Request):
    """Process speech input from caller"""
    form_data = await request.form()
    call_sid = form_data.get("CallSid")
    speech_result = form_data.get("SpeechResult", "")
    confidence = form_data.get("Confidence", "0.0")
    recording_url = form_data.get("RecordingUrl", "")  # Audio file URL
    recording_sid = form_data.get("RecordingSid", "")  # Recording ID
    
    logger.info(f"Speech from {call_sid}: '{speech_result}' (confidence: {confidence})")
    logger.info(f"Recording URL: {recording_url}, SID: {recording_sid}")
    
    response = VoiceResponse()
    import requests

    # Download and play the audio recording
    # if recording_url:
    #     # Add .mp3 to get MP3 format (or .wav for WAV)
    #     audio_response = requests.get(f"{recording_url}.mp3")
    #     audio_data = audio_response.content
        
    #     # Save temporarily and play the audio
        
    #     with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_audio:
    #         temp_audio.write(audio_data)
    #         temp_audio_path = temp_audio.name
    #         print(f"Saved temporary audio to {temp_audio_path}")
        
    #     try:
    #         # Play audio using system player (works on most systems)
    #         if os.name == 'posix':  # Linux/Mac
    #             subprocess.Popen(['mpg123', temp_audio_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    #             # Or use: subprocess.Popen(['afplay', temp_audio_path])  # Mac only
    #         elif os.name == 'nt':  # Windows
    #             subprocess.Popen(['start', '', temp_audio_path], shell=True)
    #     except Exception as e:
    #         logger.error(f"Error playing audio: {str(e)}")
        
    #     # Now process the actual audio file for STT, saving, etc.
    
    # Store conversation in session
    if call_sid in active_sessions:
        active_sessions[call_sid]["conversation_history"].append({
            "role": "user",
            "content": speech_result,
            "timestamp": datetime.now().isoformat(),
            "confidence": float(confidence),
            "recording_url": recording_url,
            "recording_sid": recording_sid
        })
    
    # Generate AI response
    try:
        ai_response = await generate_ai_response_sync(speech_result, call_sid)
        
        # Store AI response in conversation history
        if call_sid in active_sessions:
            active_sessions[call_sid]["conversation_history"].append({
                "role": "assistant",
                "content": ai_response,
                "timestamp": datetime.now().isoformat()
            })
        
        # Speak the response
        response.say(
            ai_response,
            voice="Polly.Aditi",
            # language="hi-IN"
        )
        
        # Wait for more input
        gather = response.gather(
            input="speech",
            action=f"{settings.public_url}/voice/process-speech",
            method="POST",
            speech_timeout=3,  # Wait 3 seconds of silence
            language="hi-IN",
            hints="help, information, question, support, goodbye, thanks",
            speech_model="experimental_conversations",
            enhanced=True
        )
        
        # If no more input
        response.say(
            "Is there anything else I can help you with?",
            voice="Polly.Aditi"
        )
        response.redirect(f"{settings.public_url}/voice/process-speech")
        
    except Exception as e:
        logger.error(f"Error processing speech: {str(e)}", exc_info=True)
        response.say(
            "I'm sorry, I encountered an error. Please try again.",
            voice="Polly.Joanna"
        )
        response.hangup()
    
    return Response(content=str(response), media_type="application/xml")


@app.post("/call-status")
async def call_status(request: Request):
    """Webhook for call status updates"""
    form_data = await request.form()
    call_sid = form_data.get("CallSid")
    call_status = form_data.get("CallStatus")
    answered_by = form_data.get("AnsweredBy")  # human or machine
    
    logger.info(f"Call {call_sid} status: {call_status}, answered_by: {answered_by}")
    
    # Handle answering machine detection
    if answered_by == "machine_start":
        logger.info(f"Call {call_sid} answered by machine")
        # You can leave a voicemail or handle differently
    
    # Clean up session when call ends
    if call_status in ["completed", "failed", "busy", "no-answer", "canceled"]:
        if call_sid in active_sessions:
            # Log conversation history before cleanup
            session = active_sessions[call_sid]
            logger.info(f"Call {call_sid} conversation: {len(session.get('conversation_history', []))} messages")
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


async def generate_ai_response_sync(user_input: str, call_sid: str) -> str:
    """
    Generate AI response based on user input with conversation context
    
    Args:
        user_input: The user's speech input
        call_sid: Call SID to retrieve conversation history
    
    Returns:
        AI-generated response text
    """
    # Get conversation history
    conversation_history = []
    if call_sid in active_sessions:
        conversation_history = active_sessions[call_sid].get("conversation_history", [])
    
    # Check for goodbye/exit intents
    goodbye_phrases = ["goodbye", "bye", "thank you", "thanks", "that's all", "nothing else"]
    if any(phrase in user_input.lower() for phrase in goodbye_phrases):
        return "Thank you for calling. Have a great day! Goodbye."
    
    # TODO: Integrate with LLM (OpenAI, Claude, etc.)
    # For now, return contextual responses based on input
    
    user_lower = user_input.lower()
    
    if "help" in user_lower:
        return "मैं आपकी जानकारी, सवालों के जवाब या आपकी ज़रूरतों में मदद कर सकता हूँ। आप क्या जानना चाहेंगे?"
    elif "weather" in user_lower:
        return "मैं एक AI सहायक हूँ। मौसम की जानकारी के लिए, कृपया मौसम की वेबसाइट देखें या मौसम सेवा से पूछें।"
    elif "time" in user_lower:
        now = datetime.now()
        return f"वर्तमान समय {now.strftime('%I:%M %p')} है।"
    elif "date" in user_lower:
        now = datetime.now()
        return f"आज {now.strftime('%A, %B %d, %Y')} है।"
    elif any(word in user_lower for word in ["hello", "hi", "hey"]):
        return "नमस्ते! मैं आज आपकी कैसे मदद कर सकता हूँ?"
    else:
        # Generic response
        return f"मैंने सुना कि आपने कहा: {user_input}। मैं मदद के लिए यहाँ हूँ। क्या आप कृपया अधिक विवरण दे सकते हैं या कोई विशेष प्रश्न पूछ सकते हैं?"


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
