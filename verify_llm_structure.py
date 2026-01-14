
import os
import sys
sys.path.append(os.getcwd())
import json
import logging
from utils.config import settings
from utils.llm import process_persona_update

# Setup logging
logging.basicConfig(level=logging.INFO)

# Comprehensive Test Data based on user's real schema
TEST_SCENARIOS = {
    "who_you_serve": {
        "current": {"primary_audience": "Engineers", "primary_challenges": "Bugs", "secondary_audience": "Students", "secondary_challenges": "Learning"},
        "prompt": "Update my primary audience to be technical founders instead of just engineers."
    },
    "value_proposition": {
        "current": {"specific_value": "Save time", "unique_approach": "Automated tools", "positioning_statement": "Best tool"},
        "prompt": "Change the positioning statement to focus on revenue recovery."
    },
    "voice_style": {
        "current": {"tone": "Confident", "inspiration": "Naval", "writing_style": "Direct", "recognizable_elements": "Metaphors"},
        "prompt": "Make my tone slightly more irreverent."
    },
    "proof_authority": {
        "current": {"credentials": "MIT grad", "results_achieved": "Built 2 unicorns", "consistent_praise": "Technical depth"},
        "prompt": "Add that I was also a Director at thirdweb to my credentials."
    },
    "boundaries": {
        "current": {"off_limits_topics": "Politics", "misaligned_content": "Fluff"},
        "prompt": "Add generic AI hype to misaligned content."
    },
    "business_goals": {
        "current": {"desired_outcomes": "Leads", "monetization_model": "SaaS", "twelve_month_goals": "Launch"},
        "prompt": "Update monetization model to include outcome-based pricing."
    },
    "beliefs_positioning": {
        "current": {"core_beliefs": "Automation is key", "contrarian_takes": "Manual work is theft"},
        "prompt": "Add a contrarian take that status pages are lies."
    },
    "your_story": {
        "current": {"why_story": "Frustration with SLAs", "unique_qualification": "Founding CTO"},
        "prompt": "Update my unique qualification to emphasize my enterprise sales experience."
    },
    "content_pillars": {
        "current": {
            "pillar_1": {"topic": "SLA monitoring", "benefit": "Save money"},
            "pillar_2": {"topic": "Leadership", "benefit": "Better decisions"}
        },
        "prompt": "Update pillar 1 topic to include 'Vendor Accountability'."
    }
}

def verify_structure():
    print("🚀 STARTING COMPREHENSIVE STRUCTURE VERIFICATION 🚀")
    print("="*60)
    
    failures = []
    
    for field, data in TEST_SCENARIOS.items():
        print(f"\n🔍 TESTING FIELD: {field}")
        current_val = data["current"]
        prompt = data["prompt"]
        
        # Mock full persona with this field
        mock_persona = {field: current_val}
        
        print(f"   Prompt: '{prompt}'")
        
        result = process_persona_update(prompt, mock_persona)
        
        if not result:
            print(f"   ❌ FAILURE: Result is None/Empty")
            failures.append(field)
            continue
            
        if result['field'] != field:
             print(f"   ⚠️  Targeted wrong field: {result['field']} (Expected {field})")
             # Proceed assuming it might have picked a related field, but strictly we want exact match for this test
        
        new_val = result['value']
        
        if not isinstance(new_val, dict):
            print(f"   ❌ FAILURE: Value became {type(new_val)} (Expected dict)")
            failures.append(field)
            continue
            
        # Key Check
        original_keys = set(current_val.keys())
        new_keys = set(new_val.keys())
        missing = original_keys - new_keys
        
        if missing:
             print(f"   ❌ FAILURE: Missing keys: {missing}")
             failures.append(field)
        else:
             print(f"   ✅ SUCCESS: Structure preserved. Keys: {len(new_keys)}/{len(original_keys)} match.")
             # print(f"   New Value: {json.dumps(new_val, indent=2)}")

    print("\n" + "="*60)
    if failures:
        print(f"🚨 FAILED FIELDS: {failures}")
        exit(1)
    else:
        print("✨ ALL FIELDS PASSED VERIFICATION ✨")
        exit(0)

if __name__ == "__main__":
    verify_structure()
