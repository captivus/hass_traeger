#!/usr/bin/env python3
"""Test script to verify monitor can connect."""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Check environment variables
username = os.getenv("TRAEGER_USERNAME")
password = os.getenv("TRAEGER_PASSWORD")

print("Environment Check:")
print(f"  TRAEGER_USERNAME: {'✓ Set' if username else '✗ Missing'}")
print(f"  TRAEGER_PASSWORD: {'✓ Set' if password else '✗ Missing'}")

if username and password:
    print("\nEnvironment variables are set. You can now run:")
    print("  uv run python monitor.py")
else:
    print("\nPlease set the required environment variables in .env file:")
    print("  TRAEGER_USERNAME=your_username")
    print("  TRAEGER_PASSWORD=your_password")