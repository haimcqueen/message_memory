import os
import sys
sys.path.append(os.getcwd())

from dotenv import load_dotenv
from utils.llm import generate_embedding
from workers.database import search_memories

load_dotenv()

user_id = "fb86dc17-f4c6-43e1-bad7-2cf1b7dcdea8"

queries = [
    "make up",
    "makeup", 
    "cosmetics",
    "not wearing makeup",
    "beauty products"
]

print("Testing different queries:\n")
for query in queries:
    print(f"Query: '{query}'")
    embedding = generate_embedding(query)
    results = search_memories(user_id, embedding, limit=3)
    
    if results:
        for r in results:
            print(f"  ✓ Found: {r['content'][:80]}... (similarity: {r['similarity']:.3f})")
    else:
        print(f"  ✗ No results")
    print()
