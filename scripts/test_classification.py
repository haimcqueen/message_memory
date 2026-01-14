import sys
import os
sys.path.append(os.getcwd())

from dotenv import load_dotenv
load_dotenv()

from utils.llm import classify_message, summarize_fact

test_message = "cannot stand finance bros"

print(f"Testing: '{test_message}'\n")

classification = classify_message(test_message)
print(f"Classification: {classification}")

if classification == "fact":
    summary = summarize_fact(test_message)
    print(f"Fact summary: {summary}")
elif classification == "persona":
    print("Would update persona")
else:
    print("No action taken")
