"""
Script to seed test data into DynamoDB

Usage:
    python scripts/seed_data.py
"""

import sys
import os
import asyncio

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import AgentConfig, DataCollectionField
from agent_manager import create_agent
from config import settings


async def seed_agents():
    """Create sample agents for testing"""

    # Agent 1: Customer Support Agent
    customer_support_agent = AgentConfig(
        agent_id="customer-support-001",
        name="Customer Support Agent",
        prompt=(
            "You are a friendly and helpful customer support agent. "
            "Your goal is to assist customers with their questions and concerns. "
            "Be polite, patient, and provide clear answers. "
            "Collect the customer's name and email for follow-up."
        ),
        few_shot=[
            {
                "user": "I need help with my order",
                "assistant": "I'd be happy to help you with your order! May I have your name please?"
            },
            {
                "user": "My name is John",
                "assistant": "Thank you, John! And what's your email address so I can look up your order?"
            }
        ],
        voice="Polly.Joanna",
        language="en-US",
        greeting="Hello! Thank you for calling customer support. How can I help you today?",
        data_to_fill={
            "name": DataCollectionField(
                required=True,
                prompt="May I have your name, please?"
            ),
            "email": DataCollectionField(
                required=True,
                prompt="What's your email address?"
            ),
            "issue": DataCollectionField(
                required=False,
                prompt="Can you describe the issue you're experiencing?"
            )
        },
        status="active"
    )

    # Agent 2: Sales Agent
    sales_agent = AgentConfig(
        agent_id="sales-001",
        name="Sales Agent",
        prompt=(
            "You are an enthusiastic sales agent. "
            "Your goal is to understand the customer's needs and recommend appropriate products. "
            "Be friendly, listen carefully, and ask relevant questions."
        ),
        few_shot=[
            {
                "user": "I'm interested in your product",
                "assistant": "That's great! I'd love to help you find the perfect solution. What brings you here today?"
            }
        ],
        voice="Polly.Matthew",
        language="en-US",
        greeting="Hello! Thank you for your interest. I'm here to help you find the perfect solution. What can I help you with?",
        data_to_fill={
            "name": DataCollectionField(
                required=True,
                prompt="May I have your name?"
            ),
            "company": DataCollectionField(
                required=False,
                prompt="What company are you with?"
            )
        },
        status="active"
    )

    # Agent 3: Hindi Support Agent
    hindi_agent = AgentConfig(
        agent_id="hindi-support-001",
        name="Hindi Support Agent",
        prompt=(
            "आप एक सहायक AI सहायक हैं। "
            "आपका लक्ष्य उपयोगकर्ताओं की मदद करना है। "
            "विनम्र रहें और स्पष्ट उत्तर दें।"
        ),
        few_shot=[
            {
                "user": "मुझे मदद चाहिए",
                "assistant": "जी हाँ, मैं आपकी मदद करूँगा। आपका नाम क्या है?"
            }
        ],
        voice="Polly.Aditi",
        language="hi-IN",
        greeting="नमस्ते! मैं आपकी कैसे मदद कर सकता हूँ?",
        data_to_fill={
            "name": DataCollectionField(
                required=True,
                prompt="आपका नाम क्या है?"
            )
        },
        status="active"
    )

    # Agent 4: Default/Test Agent
    default_agent = AgentConfig(
        agent_id="default",
        name="Default Agent",
        prompt="You are a helpful AI assistant. Answer questions politely and concisely.",
        voice="Polly.Joanna",
        language="en-US",
        greeting="Hello! I'm your AI assistant. How can I help you today?",
        status="active"
    )

    # Create all agents
    agents = [customer_support_agent, sales_agent, hindi_agent, default_agent]

    print("=" * 60)
    print("Seeding Test Agents into DynamoDB")
    print("=" * 60)

    success_count = 0
    for agent in agents:
        try:
            await create_agent(agent)
            print(f"✓ Created agent: {agent.agent_id} ({agent.name})")
            success_count += 1
        except Exception as e:
            print(f"✗ Failed to create agent {agent.agent_id}: {e}")

    print("=" * 60)
    print(f"✓ Successfully created {success_count}/{len(agents)} agents")
    print("=" * 60)


async def main():
    """Main function"""
    if not settings.enable_dynamodb:
        print("⚠ DynamoDB is disabled in settings. Enable it in .env to seed data.")
        return 1

    await seed_agents()
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
