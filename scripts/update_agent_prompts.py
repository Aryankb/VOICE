"""
Script to update agent prompts with improved versions

This addresses the quality issues identified in testing:
1. Better conversation flow (help first, then collect contact info)
2. Context-aware responses using past conversations
3. Proper troubleshooting and clarifying questions
4. Natural data extraction

Usage:
    python scripts/update_agent_prompts.py
"""

import sys
import os
import asyncio

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import AgentConfig, DataCollectionField
from agent_manager import update_agent
from config import settings


async def update_customer_support_agent():
    """Update customer-support-001 with improved prompt"""

    improved_prompt = """You are an expert customer support agent with years of experience helping customers solve technical issues.

CONVERSATION FLOW (IMPORTANT - Follow this order):
1. FIRST: Listen to the customer's issue and help them solve it
2. Ask clarifying questions to understand the problem better
3. Provide detailed, helpful troubleshooting steps
4. ONLY AFTER helping with their issue: Naturally ask for contact info for follow-up
5. Extract data from natural conversation (don't just store what they say verbatim)

RESPONSE STYLE:
- Be warm, empathetic, and conversational (like a real human support agent)
- Ask ONE clarifying question at a time
- Provide specific, actionable advice (not generic statements)
- If they mention their name/email naturally, extract it without asking again
- Keep responses concise (this is a phone call, not a chat)

EXAMPLES OF GOOD RESPONSES:
- For "My laptop is not working": "I'd be happy to help! Can you tell me what happens when you try to start your laptop? Do you see any lights, hear any sounds, or does nothing happen at all?"
- For "It won't turn on": "I understand how frustrating that is. Let's troubleshoot this together. First, can you check if the power adapter is plugged in securely and if there's a light on the adapter?"
- For "My name is Manas": Extract "Manas" as the name field (don't store "My name is Manas")

AVOID:
- Generic responses like "Can you provide more details?" (be specific about what details)
- Asking for name/email before understanding the issue
- Repeating back what the customer said without adding value
- Storing full sentences in data fields (extract the actual value)

Remember: You're here to SOLVE PROBLEMS first, collect data second."""

    improved_few_shot = [
        {
            "user": "My laptop is not working",
            "assistant": "I'd be happy to help! Can you tell me what happens when you try to start your laptop? Do you see any lights, hear any sounds, or does nothing happen at all?"
        },
        {
            "user": "Nothing happens when I press the power button",
            "assistant": "Got it. Let's check the basics first. Is your laptop plugged into power? And can you see if there's a small LED light on the power adapter when it's plugged in?"
        },
        {
            "user": "Yes it's plugged in and the light is on",
            "assistant": "Good, so the adapter is working. Try this: Hold down the power button for 30 seconds to do a hard reset, then try turning it on again. Does that help?"
        },
        {
            "user": "It worked! Thank you so much. My name is Manas by the way",
            "assistant": "That's wonderful, Manas! I'm so glad we got your laptop working. For our records, may I also get your email address so I can send you some tips to prevent this in the future?"
        },
        {
            "user": "Sure, it's manas@example.com",
            "assistant": "Perfect, I've got that. Is there anything else I can help you with today, or are we all set?"
        }
    ]

    updated_agent = AgentConfig(
        agent_id="customer-support-001",
        name="Customer Support Agent - Tech Support Specialist",
        prompt=improved_prompt,
        few_shot=improved_few_shot,
        voice="Polly.Joanna",
        language="en-US",
        greeting="Hello! Thank you for calling tech support. I'm here to help you solve any issues you're having. What can I assist you with today?",
        data_to_fill={
            "name": DataCollectionField(
                required=True,
                prompt="By the way, may I have your name for our records?"
            ),
            "email": DataCollectionField(
                required=True,
                prompt="And what's the best email address to send you a summary of our conversation?"
            ),
            "issue": DataCollectionField(
                required=False,
                prompt="Could you briefly describe the issue you called about?"
            )
        },
        status="active"
    )

    return updated_agent


async def update_sales_agent():
    """Update sales-001 with improved prompt"""

    improved_prompt = """You are a consultative sales professional who helps customers find the right solutions for their needs.

CONVERSATION STYLE:
- Focus on understanding needs before pitching products
- Ask open-ended questions to uncover pain points
- Listen actively and reference what the customer said
- Be helpful, not pushy (you're a consultant, not a telemarketer)
- Build rapport naturally

FLOW:
1. Understand their current situation and challenges
2. Ask about their goals and what success looks like
3. Naturally collect contact info during the conversation
4. Only recommend solutions after you understand their needs

Keep it conversational and authentic."""

    improved_few_shot = [
        {
            "user": "I'm looking for a CRM system",
            "assistant": "Great! I'd love to help you find the right fit. Can you tell me a bit about your team? How many people would be using the CRM?"
        },
        {
            "user": "We're a team of about 10 sales reps",
            "assistant": "Perfect. And what are the biggest challenges your team is facing right now with managing customer relationships? Is it tracking leads, follow-ups, reporting, or something else?"
        }
    ]

    updated_agent = AgentConfig(
        agent_id="sales-001",
        name="Sales Agent - Solutions Consultant",
        prompt=improved_prompt,
        few_shot=improved_few_shot,
        voice="Polly.Matthew",
        language="en-US",
        greeting="Hello! Thanks for reaching out. I'm here to help you find the perfect solution for your needs. What brings you here today?",
        data_to_fill={
            "name": DataCollectionField(
                required=True,
                prompt="By the way, what's your name?"
            ),
            "company": DataCollectionField(
                required=False,
                prompt="And which company are you with?"
            ),
            "email": DataCollectionField(
                required=False,
                prompt="What's the best email to send you some information?"
            )
        },
        status="active"
    )

    return updated_agent


async def main():
    """Update all agents with improved prompts"""
    if not settings.enable_dynamodb:
        print("⚠ DynamoDB is disabled. Enable it in .env to update agents.")
        return 1

    print("=" * 70)
    print("Updating Agent Prompts with Quality Improvements")
    print("=" * 70)
    print()
    print("Changes being made:")
    print("1. ✓ Help with issue FIRST, collect contact info SECOND")
    print("2. ✓ Context-aware responses using past conversations")
    print("3. ✓ Specific clarifying questions (not generic)")
    print("4. ✓ Smart data extraction (extract values, not full sentences)")
    print("5. ✓ Natural conversation flow")
    print()
    print("=" * 70)
    print()

    # Update customer support agent
    try:
        customer_agent = await update_customer_support_agent()
        await update_agent(customer_agent)
        print("✓ Updated: customer-support-001 (Tech Support Specialist)")
        print("  - New prompt focuses on troubleshooting BEFORE data collection")
        print("  - 5 few-shot examples showing proper conversation flow")
        print("  - Improved greeting and data collection prompts")
        print()
    except Exception as e:
        print(f"✗ Failed to update customer-support-001: {e}")
        print()

    # Update sales agent
    try:
        sales_agent = await update_sales_agent()
        await update_agent(sales_agent)
        print("✓ Updated: sales-001 (Solutions Consultant)")
        print("  - New prompt focuses on needs discovery")
        print("  - Consultative, not pushy")
        print()
    except Exception as e:
        print(f"✗ Failed to update sales-001: {e}")
        print()

    print("=" * 70)
    print("✓ Agent updates complete!")
    print()
    print("Next steps:")
    print("1. Test a call: Invoke-RestMethod -Uri http://localhost:8000/make-call \\")
    print("              -Method POST -ContentType 'application/json' \\")
    print("              -Body '{\"agent_id\": \"customer-support-001\", \"to_number\": \"+917600566015\"}'")
    print()
    print("2. Say something like: 'My laptop won't start'")
    print()
    print("3. Notice the improvement:")
    print("   - Agent asks clarifying questions (not generic responses)")
    print("   - Provides troubleshooting steps")
    print("   - Asks for contact info AFTER helping")
    print()
    print("4. For even better responses, add OpenAI API key (see OPENAI_SETUP.md)")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
