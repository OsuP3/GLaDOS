#!/usr/bin/env python3
"""
Test script to verify the media control server is working
"""

import requests
import json
import time

PI_IP = "192.168.1.244"
PORT = 8766

def test_ping():
    """Test the ping endpoint"""
    try:
        url = f"http://{PI_IP}:{PORT}/ping"
        response = requests.get(url, timeout=5)
        print(f"Ping Response: {response.status_code}")
        print(f"Content: {json.dumps(response.json(), indent=2)}")
        return True
    except Exception as e:
        print(f"Ping failed: {e}")
        return False

def test_status():
    """Test the status endpoint"""
    try:
        url = f"http://{PI_IP}:{PORT}/status"
        response = requests.get(url, timeout=5)
        print(f"Status Response: {response.status_code}")
        print(f"Content: {json.dumps(response.json(), indent=2)}")
        return True
    except Exception as e:
        print(f"Status failed: {e}")
        return False

def test_toggle():
    """Test triggering a toggle command"""
    try:
        url = f"http://{PI_IP}:{PORT}/toggle"
        response = requests.post(url, timeout=5)
        print(f"Toggle Response: {response.status_code}")
        print(f"Content: {json.dumps(response.json(), indent=2)}")
        return True
    except Exception as e:
        print(f"Toggle failed: {e}")
        return False

if __name__ == "__main__":
    print(f"Testing Media Control Server at {PI_IP}:{PORT}")
    print("=" * 50)
    
    print("\n1. Testing ping endpoint...")
    test_ping()
    
    print("\n2. Testing status endpoint...")
    test_status()
    
    print("\n3. Testing toggle command...")
    test_toggle()
    
    print("\n4. Testing ping after toggle (should show toggle=true)...")
    time.sleep(1)
    test_ping()
    
    print("\n5. Testing ping again (should show toggle=false)...")
    time.sleep(1)
    test_ping()
