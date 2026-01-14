import sys
import os
sys.path.append(os.getcwd())

from dotenv import load_dotenv
load_dotenv()

from utils.llm import classify_message

test_cases = [
    "I really hate consultants",
    "I prefer tea over coffee",
    "I think remote work is overrated",
    "I love hiking on weekends",
    "Consultants are the worst",
    "My goal is to become a CEO",  # Should be persona
    "Hello there",  # Should be neither
]

print("Testing classification edge cases:\n")
for msg in test_cases:
    classification = classify_message(msg)
    print(f"'{msg}' → {classification}")
