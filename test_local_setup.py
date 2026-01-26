"""
Test script for local LLM and TTS setup
Run this to verify everything is working before making phone calls
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from local_llm_client import get_llm_client
from local_tts_client import get_tts_client
from config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_llm():
    """Test local LLM (Ollama)"""
    print("\n" + "=" * 60)
    print("Testing Local LLM (Ollama)")
    print("=" * 60)

    if not settings.use_local_llm:
        print("❌ Local LLM is disabled in config")
        print("   Set USE_LOCAL_LLM=true in .env")
        return False

    try:
        llm_client = get_llm_client()

        # Health check
        print(f"\n1. Checking if Ollama is running at {settings.ollama_host}...")
        healthy = await llm_client.health_check()

        if not healthy:
            print("❌ Ollama health check failed")
            print(f"   Make sure Ollama is running and model '{settings.ollama_model}' is pulled")
            print(f"\n   To fix:")
            print(f"   1. Install Ollama from https://ollama.ai")
            print(f"   2. Run: ollama pull {settings.ollama_model}")
            return False

        print(f"✅ Ollama is running with model: {settings.ollama_model}")

        # Test conversation
        print("\n2. Testing conversation...")
        messages = [
            {"role": "system", "content": "You are a helpful customer support agent."},
            {"role": "user", "content": "Hello! My laptop won't turn on. What should I do?"}
        ]

        response = await llm_client.chat(messages, temperature=0.7, max_tokens=150)

        print(f"\n   User: {messages[-1]['content']}")
        print(f"   AI: {response}")

        if len(response) > 10:
            print("\n✅ LLM conversation test passed!")
        else:
            print("\n❌ LLM returned very short response")
            return False

        # Test data extraction
        print("\n3. Testing data extraction...")
        extracted_name = await llm_client.extract_field(
            "My name is Manas and I need help",
            "name"
        )
        print(f"   Input: 'My name is Manas and I need help'")
        print(f"   Extracted name: {extracted_name}")

        if extracted_name and extracted_name != "NOT_FOUND":
            print("✅ Data extraction test passed!")
        else:
            print("⚠️ Data extraction returned NOT_FOUND (may need model tuning)")

        return True

    except Exception as e:
        print(f"\n❌ LLM test failed: {str(e)}")
        logger.error("LLM test error:", exc_info=True)
        return False


async def test_tts():
    """Test local TTS"""
    print("\n" + "=" * 60)
    print("Testing Local TTS")
    print("=" * 60)

    if not settings.use_local_tts:
        print("❌ Local TTS is disabled in config")
        print("   Set USE_LOCAL_TTS=true in .env")
        return False

    try:
        tts_client = get_tts_client()

        # Test generation
        print(f"\n1. Testing TTS generation (engine: {settings.tts_engine})...")
        print("   Generating: 'Hello, I am your AI assistant. How can I help you today?'")

        audio_file = await tts_client.generate_speech(
            "Hello, I am your AI assistant. How can I help you today?",
            language="en-US"
        )

        if Path(audio_file).exists():
            file_size = Path(audio_file).stat().st_size
            print(f"\n✅ TTS file generated: {audio_file}")
            print(f"   File size: {file_size:,} bytes")

            # Test Hindi
            print("\n2. Testing Hindi TTS...")
            hindi_file = await tts_client.generate_speech(
                "नमस्ते, मैं आपकी कैसे मदद कर सकता हूं?",
                language="hi-IN"
            )

            if Path(hindi_file).exists():
                print(f"✅ Hindi TTS file generated: {hindi_file}")
            else:
                print("⚠️ Hindi TTS file not found")

            return True
        else:
            print(f"❌ TTS file was not created")
            return False

    except ImportError as e:
        print(f"\n❌ TTS library not installed: {str(e)}")
        print(f"\n   To fix:")
        print(f"   pip install coqui-tts")
        return False
    except Exception as e:
        print(f"\n❌ TTS test failed: {str(e)}")
        logger.error("TTS test error:", exc_info=True)
        return False


async def test_full_pipeline():
    """Test full LLM + TTS pipeline"""
    print("\n" + "=" * 60)
    print("Testing Full Pipeline (LLM + TTS)")
    print("=" * 60)

    try:
        # Get clients
        llm_client = get_llm_client()
        tts_client = get_tts_client()

        # Generate response
        print("\n1. Generating AI response...")
        messages = [
            {"role": "system", "content": "You are a friendly voice assistant. Keep responses under 30 words."},
            {"role": "user", "content": "Can you help me with my order?"}
        ]
        ai_response = await llm_client.chat(messages, temperature=0.7, max_tokens=100)
        print(f"   AI: {ai_response}")

        # Convert to speech
        print("\n2. Converting response to speech...")
        audio_file = await tts_client.generate_speech(ai_response, language="en-US")
        print(f"   Audio: {audio_file}")

        print("\n✅ Full pipeline test passed!")
        print(f"\n🎉 All systems ready for phone calls!")
        return True

    except Exception as e:
        print(f"\n❌ Full pipeline test failed: {str(e)}")
        logger.error("Pipeline test error:", exc_info=True)
        return False


async def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("LOCAL AI SYSTEM TEST")
    print("=" * 60)
    print(f"\nConfiguration:")
    print(f"  - Ollama Host: {settings.ollama_host}")
    print(f"  - Ollama Model: {settings.ollama_model}")
    print(f"  - TTS Engine: {settings.tts_engine}")
    print(f"  - TTS Output: {settings.tts_output_dir}")

    results = {
        "llm": False,
        "tts": False,
        "pipeline": False
    }

    # Test LLM
    results["llm"] = await test_llm()

    # Test TTS
    results["tts"] = await test_tts()

    # Test full pipeline if both pass
    if results["llm"] and results["tts"]:
        results["pipeline"] = await test_full_pipeline()

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"  LLM:      {'✅ PASS' if results['llm'] else '❌ FAIL'}")
    print(f"  TTS:      {'✅ PASS' if results['tts'] else '❌ FAIL'}")
    print(f"  Pipeline: {'✅ PASS' if results['pipeline'] else '❌ FAIL'}")
    print("=" * 60)

    if all(results.values()):
        print("\n🎉 All tests passed! Ready to make calls.")
        print("\nNext steps:")
        print("  1. Start ngrok: ngrok http 8000")
        print("  2. Update PUBLIC_URL in .env")
        print("  3. Start server: python app.py")
        print("  4. Make test call!")
        return 0
    else:
        print("\n⚠️ Some tests failed. Check errors above.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
