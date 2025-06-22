#!/usr/bin/env python3
"""Test monitor functionality for 30 seconds."""

import time
import signal
import sys
from monitor import main, TraegerMonitor
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def timeout_handler(signum, frame):
    print("\n✓ Test completed - monitor ran for 30 seconds")
    sys.exit(0)

def test_monitor():
    """Test monitor with timeout."""
    # Set timeout
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(30)  # 30 second timeout
    
    print("Starting monitor test (will run for 30 seconds)...")
    print("-" * 50)
    
    try:
        main()
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
    except Exception as e:
        print(f"\n✗ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    test_monitor()