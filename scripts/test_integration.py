"""
Integration tests for DynamoDB integration

Usage:
    python scripts/test_integration.py
"""

import sys
import os
import asyncio
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import db_client
from models import AgentConfig, CallRecord, ConversationMessage, DataCollectionField
from agent_manager import get_agent, create_agent, get_default_agent_config
from call_manager import (
    create_call_record,
    fetch_past_conversations,
    sync_conversation_to_db,
    finalize_call
)
from session_manager import detect_goodbye_intent, is_data_collection_complete
from config import settings


class TestRunner:
    """Test runner with colored output"""

    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.tests = []

    def assert_true(self, condition: bool, message: str):
        """Assert condition is true"""
        if condition:
            print(f"  ✓ {message}")
            self.passed += 1
        else:
            print(f"  ✗ {message}")
            self.failed += 1
        self.tests.append((message, condition))

    def assert_equal(self, actual, expected, message: str):
        """Assert two values are equal"""
        condition = actual == expected
        if condition:
            print(f"  ✓ {message}")
            self.passed += 1
        else:
            print(f"  ✗ {message} (expected: {expected}, got: {actual})")
            self.failed += 1
        self.tests.append((message, condition))

    def print_summary(self):
        """Print test summary"""
        print("\n" + "=" * 60)
        print(f"Test Summary: {self.passed} passed, {self.failed} failed")
        if self.failed == 0:
            print("✓ All tests passed!")
        else:
            print(f"✗ {self.failed} test(s) failed")
        print("=" * 60)
        return self.failed == 0


async def test_phase1_database():
    """Test Phase 1: Database Foundation"""
    print("\n" + "=" * 60)
    print("Phase 1: Database Foundation Tests")
    print("=" * 60)

    runner = TestRunner()

    # Test 1: Database operations
    print("\n[Test 1] Basic database operations")
    try:
        test_item = {
            "agent_id": "test-agent-db",
            "name": "Test Agent",
            "status": "active",
            "created_at": datetime.now().isoformat()
        }

        await db_client.put_item(settings.dynamodb_table_agents, test_item)
        runner.assert_true(True, "Put item succeeded")

        result = await db_client.get_item(
            settings.dynamodb_table_agents,
            {"agent_id": "test-agent-db"}
        )
        runner.assert_true(result is not None, "Get item succeeded")
        runner.assert_equal(result.get("name"), "Test", "Item name matches")

        # Cleanup
        await db_client.delete_item(
            settings.dynamodb_table_agents,
            {"agent_id": "test-agent-db"}
        )

    except Exception as e:
        runner.assert_true(False, f"Database operations failed: {e}")

    # Test 2: Model validation
    print("\n[Test 2] Model validation")
    try:
        agent = AgentConfig(
            agent_id="test-model",
            name="Test Model Agent",
            prompt="Test prompt",
            voice="Polly.Joanna",
            language="en-US"
        )
        runner.assert_equal(agent.voice, "Polly.Joanna", "Agent voice matches")
        runner.assert_equal(agent.language, "en-US", "Agent language matches")
        runner.assert_equal(agent.status, "active", "Default status is active")

    except Exception as e:
        runner.assert_true(False, f"Model validation failed: {e}")

    return runner.print_summary()


async def test_phase2_agent_integration():
    """Test Phase 2: Agent Integration"""
    print("\n" + "=" * 60)
    print("Phase 2: Agent Integration Tests")
    print("=" * 60)

    runner = TestRunner()

    # Test 1: Create and retrieve agent
    print("\n[Test 1] Create and retrieve agent")
    try:
        test_agent = AgentConfig(
            agent_id="test-agent-integration",
            name="Integration Test Agent",
            prompt="You are a test assistant",
            greeting="Hello from test!",
            voice="Polly.Matthew",
            language="en-US"
        )

        await create_agent(test_agent)
        runner.assert_true(True, "Agent created successfully")

        # Retrieve agent
        retrieved_agent = await get_agent("test-agent-integration", use_cache=False)
        runner.assert_equal(
            retrieved_agent.name,
            "Integration Test Agent",
            "Agent name matches"
        )
        runner.assert_equal(
            retrieved_agent.greeting,
            "Hello from test!",
            "Agent greeting matches"
        )

    except Exception as e:
        runner.assert_true(False, f"Agent creation/retrieval failed: {e}")

    # Test 2: Agent caching
    print("\n[Test 2] Agent caching")
    try:
        # First call (cache miss)
        agent1 = await get_agent("test-agent-integration", use_cache=True)

        # Second call (cache hit)
        agent2 = await get_agent("test-agent-integration", use_cache=True)

        runner.assert_true(True, "Agent caching works")

    except Exception as e:
        runner.assert_true(False, f"Agent caching failed: {e}")

    # Test 3: Call record creation
    print("\n[Test 3] Call record creation")
    try:
        call_record = await create_call_record(
            call_sid="CA_test_123",
            agent_id="test-agent-integration",
            recipient_phone="+1234567890",
            caller_phone="+0987654321",
            status="in-progress"
        )

        runner.assert_equal(call_record.call_sid, "CA_test_123", "Call SID matches")
        runner.assert_equal(
            call_record.agent_id,
            "test-agent-integration",
            "Agent ID matches"
        )

        # Verify in database
        retrieved = await db_client.get_item(
            settings.dynamodb_table_calls,
            {"call_sid": "CA_test_123"}
        )
        runner.assert_true(retrieved is not None, "Call record saved to DB")

    except Exception as e:
        runner.assert_true(False, f"Call record creation failed: {e}")

    # Test 4: Fetch past conversations
    print("\n[Test 4] Fetch past conversations")
    try:
        # Create a second call for the same agent-recipient pair
        await create_call_record(
            call_sid="CA_test_456",
            agent_id="test-agent-integration",
            recipient_phone="+1234567890",
            caller_phone="+0987654321",
            status="completed"
        )

        # Fetch past conversations
        past_calls = await fetch_past_conversations(
            agent_id="test-agent-integration",
            recipient_phone="+1234567890",
            limit=5
        )

        runner.assert_true(len(past_calls) >= 1, f"Found {len(past_calls)} past calls")

    except Exception as e:
        runner.assert_true(False, f"Fetch past conversations failed: {e}")

    return runner.print_summary()


async def test_phase3_conversation_management():
    """Test Phase 3: Conversation Management"""
    print("\n" + "=" * 60)
    print("Phase 3: Conversation Management Tests")
    print("=" * 60)

    runner = TestRunner()

    # Test 1: Conversation syncing
    print("\n[Test 1] Conversation syncing")
    try:
        test_call_sid = "CA_test_sync"

        # Create call record
        await create_call_record(
            call_sid=test_call_sid,
            agent_id="test-agent-integration",
            recipient_phone="+1234567890",
            caller_phone="+0987654321"
        )

        # Create conversation history
        conversation = [
            ConversationMessage(
                role="user",
                content="Hello",
                confidence=0.95
            ),
            ConversationMessage(
                role="assistant",
                content="Hi! How can I help?"
            ),
            ConversationMessage(
                role="user",
                content="I need help",
                confidence=0.92
            )
        ]

        # Sync to DB
        success = await sync_conversation_to_db(
            call_sid=test_call_sid,
            conversation_history=conversation,
            data_collected={"name": "John"}
        )

        runner.assert_true(success, "Conversation synced successfully")

        # Verify in DB
        call_record = await db_client.get_item(
            settings.dynamodb_table_calls,
            {"call_sid": test_call_sid}
        )

        runner.assert_true(
            len(call_record.get("conversation_history", [])) >= 3,
            f"Conversation history saved ({len(call_record.get('conversation_history', []))} messages)"
        )

    except Exception as e:
        runner.assert_true(False, f"Conversation syncing failed: {e}")

    # Test 2: Goodbye intent detection
    print("\n[Test 2] Goodbye intent detection")
    test_cases = [
        ("goodbye", True),
        ("bye", True),
        ("thank you", True),
        ("that's all", True),
        ("hello", False),
        ("help me", False)
    ]

    for user_input, expected in test_cases:
        result = detect_goodbye_intent(user_input)
        runner.assert_equal(
            result,
            expected,
            f"Goodbye detection for '{user_input}'"
        )

    # Test 3: Data collection completion check
    print("\n[Test 3] Data collection completion")
    try:
        # Session with incomplete data
        session_incomplete = {
            "agent_data": {
                "data_to_fill": {
                    "name": {"required": True},
                    "email": {"required": True}
                }
            },
            "data_collected": {"name": "John"}
        }
        result = is_data_collection_complete(session_incomplete)
        runner.assert_equal(result, False, "Incomplete data detected correctly")

        # Session with complete data
        session_complete = {
            "agent_data": {
                "data_to_fill": {
                    "name": {"required": True},
                    "email": {"required": True}
                }
            },
            "data_collected": {"name": "John", "email": "john@example.com"}
        }
        result = is_data_collection_complete(session_complete)
        runner.assert_equal(result, True, "Complete data detected correctly")

    except Exception as e:
        runner.assert_true(False, f"Data collection check failed: {e}")

    return runner.print_summary()


async def test_phase4_call_finalization():
    """Test Phase 4: Call Termination & Persistence"""
    print("\n" + "=" * 60)
    print("Phase 4: Call Termination & Persistence Tests")
    print("=" * 60)

    runner = TestRunner()

    # Test 1: Call finalization
    print("\n[Test 1] Call finalization")
    try:
        test_call_sid = "CA_test_finalize"

        # Create call record
        await create_call_record(
            call_sid=test_call_sid,
            agent_id="test-agent-integration",
            recipient_phone="+1234567890",
            caller_phone="+0987654321"
        )

        # Create conversation
        conversation = [
            ConversationMessage(role="user", content="Hello"),
            ConversationMessage(role="assistant", content="Hi!")
        ]

        # Finalize call
        success = await finalize_call(
            call_sid=test_call_sid,
            status="completed",
            ended_at=datetime.now().isoformat(),
            duration_seconds=120,
            ended_by="user",
            conversation_history=conversation,
            data_collected={"name": "John", "email": "john@example.com"}
        )

        runner.assert_true(success, "Call finalized successfully")

        # Verify in DB
        call_record = await db_client.get_item(
            settings.dynamodb_table_calls,
            {"call_sid": test_call_sid}
        )

        runner.assert_equal(call_record.get("status"), "completed", "Status is completed")
        runner.assert_equal(call_record.get("ended_by"), "user", "Ended by user")
        runner.assert_equal(call_record.get("duration_seconds"), 120, "Duration is 120s")
        runner.assert_true(
            "data_collected" in call_record,
            "Data collected saved"
        )

    except Exception as e:
        runner.assert_true(False, f"Call finalization failed: {e}")

    return runner.print_summary()


async def cleanup_test_data():
    """Clean up all test data"""
    print("\n" + "=" * 60)
    print("Cleaning up test data")
    print("=" * 60)

    test_items = [
        (settings.dynamodb_table_agents, "test-agent-db"),
        (settings.dynamodb_table_agents, "test-agent-integration"),
        (settings.dynamodb_table_calls, "CA_test_123"),
        (settings.dynamodb_table_calls, "CA_test_456"),
        (settings.dynamodb_table_calls, "CA_test_sync"),
        (settings.dynamodb_table_calls, "CA_test_finalize")
    ]

    for table_name, key_value in test_items:
        try:
            # Determine key name based on table
            if "Agents" in table_name:
                key = {"agent_id": key_value}
            else:
                key = {"call_sid": key_value}

            await db_client.delete_item(table_name, key)
            print(f"✓ Deleted {key_value} from {table_name}")
        except Exception as e:
            print(f"⚠ Could not delete {key_value}: {e}")


async def main():
    """Main test runner"""
    if not settings.enable_dynamodb:
        print("⚠ DynamoDB is disabled. Enable it in .env to run tests.")
        return 1

    print("\n" + "=" * 60)
    print("DynamoDB Integration Test Suite")
    print("=" * 60)
    print(f"Region: {settings.aws_region}")
    print(f"Agents Table: {settings.dynamodb_table_agents}")
    print(f"Calls Table: {settings.dynamodb_table_calls}")
    print("=" * 60)

    all_passed = True

    # Run test phases
    try:
        phase1_passed = await test_phase1_database()
        all_passed = all_passed and phase1_passed

        phase2_passed = await test_phase2_agent_integration()
        all_passed = all_passed and phase2_passed

        phase3_passed = await test_phase3_conversation_management()
        all_passed = all_passed and phase3_passed

        phase4_passed = await test_phase4_call_finalization()
        all_passed = all_passed and phase4_passed

    except Exception as e:
        print(f"\n✗ Test suite failed with error: {e}")
        all_passed = False

    finally:
        # Cleanup
        await cleanup_test_data()

    # Final summary
    print("\n" + "=" * 60)
    if all_passed:
        print("✓ ALL PHASES PASSED!")
        print("=" * 60)
        return 0
    else:
        print("✗ SOME TESTS FAILED")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
