"""
Example usage of the Twilio Voice AI Assistant API
"""
import requests
import json


# Configuration
BASE_URL = "http://localhost:8000"
TO_NUMBER = "+917600566015"  # Your number


def make_outbound_call():
    """Example: Make an outbound call"""
    print("Making outbound call...")

    response = requests.post(
        f"{BASE_URL}/make-call",
        json={
            "agent_id": "my-agent-f5d024e8",  # Your personal agent
            "to_number": TO_NUMBER,
        }
    )
    
    if response.status_code == 200:
        data = response.json()
        print(f"✓ Call initiated successfully!")
        print(f"  Call SID: {data['call_sid']}")
        print(f"  Status: {data['status']}")
        print(f"  To: {data['to']}")
        print(f"  From: {data['from']}")
        return data['call_sid']
    else:
        print(f"✗ Error: {response.text}")
        return None


def interrupt_call(call_sid):
    """Example: Interrupt an active call"""
    print(f"\nInterrupting call {call_sid}...")
    
    response = requests.post(f"{BASE_URL}/interrupt-call/{call_sid}")
    
    if response.status_code == 200:
        print("✓ Call interrupted successfully!")
    else:
        print(f"✗ Error: {response.text}")



def check_health():
    """Example: Check if server is running"""
    print("Checking server health...")
    
    response = requests.get(f"{BASE_URL}/")
    
    if response.status_code == 200:
        data = response.json()
        print(f"✓ Server is running: {data['message']}")
    else:
        print("✗ Server is not responding")


if __name__ == "__main__":
    print("=== Twilio Voice AI Assistant - Examples ===\n")
    
    # 1. Check health
    check_health()
    
    # 2. Make a call
    print("\n" + "="*50)
    call_sid = make_outbound_call()
    
    # 3. Wait for user input to interrupt
    # if call_sid:
        # print("\n" + "="*50)
        # input("Press Enter to interrupt the call...")
        # interrupt_call(call_sid)
    
    print("\n=== Examples completed ===")
