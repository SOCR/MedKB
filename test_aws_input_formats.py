"""
Test different input formats for AWS Comprehend Medical to find optimal approach.

Compares:
1. Just entity name (original)
2. Entity name + type in parentheses (previous)
3. Clinical sentence templates (current)
"""

import boto3
import os

# Initialize AWS Comprehend Medical
comprehend_client = boto3.client('comprehendmedical', region_name='us-east-1')

# Test entities from the pipeline logs that are failing
test_entities = [
    {"name": "Cirrhosis", "type": "Disease"},
    {"name": "Gallstones", "type": "Pathological_Finding"},
    {"name": "Tumors", "type": "Disease"},
    {"name": "Pancreas", "type": "Anatomy"},
    {"name": "Common bile duct", "type": "Anatomy"},
    {"name": "Diabetes", "type": "Disease"},
    {"name": "Hypertension", "type": "Disease"},
]

# Test formats
def format_1_just_name(name, entity_type):
    """Original: Just the entity name"""
    return name

def format_2_name_and_type(name, entity_type):
    """Previous: Name with type in parentheses"""
    return f"{name} ({entity_type})"

def format_3_clinical_sentence(name, entity_type):
    """Current: Clinical sentence templates"""
    templates = {
        "Disease": f"Patient diagnosed with {name}.",
        "Pathological_Finding": f"Patient presents with {name}.",
        "Anatomy": f"Examination of patient's {name}.",
    }
    return templates.get(entity_type, f"Clinical assessment: {name}.")

def test_aws_comprehend(text):
    """Call AWS Comprehend Medical SNOMED API"""
    try:
        response = comprehend_client.infer_snomedct(Text=text)
        entities = response.get('Entities', [])
        
        if not entities:
            return None, 0.0
        
        # Get best concept
        best_score = 0.0
        best_concept = None
        for entity in entities:
            for concept in entity.get('SNOMEDCTConcepts', []):
                if concept['Score'] > best_score:
                    best_score = concept['Score']
                    best_concept = concept
        
        return best_concept, best_score
    except Exception as e:
        return None, 0.0

def main():
    print("=" * 80)
    print("AWS COMPREHEND MEDICAL INPUT FORMAT COMPARISON")
    print("=" * 80)
    print()
    
    results = []
    
    for entity in test_entities:
        name = entity["name"]
        entity_type = entity["type"]
        
        print(f"\n📋 Testing: {name} ({entity_type})")
        print("-" * 80)
        
        # Format 1: Just name
        text_1 = format_1_just_name(name, entity_type)
        concept_1, score_1 = test_aws_comprehend(text_1)
        print(f"  1️⃣  Just name:      '{text_1}'")
        print(f"      → Confidence: {score_1:.2f}")
        if concept_1:
            print(f"      → SNOMED: {concept_1['Code']} - {concept_1['Description']}")
        
        # Format 2: Name + type
        text_2 = format_2_name_and_type(name, entity_type)
        concept_2, score_2 = test_aws_comprehend(text_2)
        print(f"  2️⃣  Name + type:   '{text_2}'")
        print(f"      → Confidence: {score_2:.2f}")
        if concept_2:
            print(f"      → SNOMED: {concept_2['Code']} - {concept_2['Description']}")
        
        # Format 3: Clinical sentence
        text_3 = format_3_clinical_sentence(name, entity_type)
        concept_3, score_3 = test_aws_comprehend(text_3)
        print(f"  3️⃣  Clinical sent: '{text_3}'")
        print(f"      → Confidence: {score_3:.2f}")
        if concept_3:
            print(f"      → SNOMED: {concept_3['Code']} - {concept_3['Description']}")
        
        # Determine winner
        scores = [score_1, score_2, score_3]
        max_score = max(scores)
        winner_idx = scores.index(max_score) + 1
        
        print(f"\n  🏆 WINNER: Format {winner_idx} (confidence: {max_score:.2f})")
        
        results.append({
            "entity": name,
            "type": entity_type,
            "score_1": score_1,
            "score_2": score_2,
            "score_3": score_3,
            "winner": winner_idx,
        })
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print()
    print(f"{'Entity':<25} {'Type':<20} {'Format 1':<12} {'Format 2':<12} {'Format 3':<12} {'Winner':<10}")
    print("-" * 95)
    
    for r in results:
        winner_mark = ["", "1️⃣", "2️⃣", "3️⃣"][r["winner"]]
        print(f"{r['entity']:<25} {r['type']:<20} {r['score_1']:<12.2f} {r['score_2']:<12.2f} {r['score_3']:<12.2f} {winner_mark:<10}")
    
    # Overall winner
    winner_counts = [0, 0, 0, 0]  # index 0 unused
    for r in results:
        winner_counts[r["winner"]] += 1
    
    print("\n" + "=" * 80)
    print("OVERALL WINNER")
    print("=" * 80)
    print(f"  Format 1 (Just name):       {winner_counts[1]} wins")
    print(f"  Format 2 (Name + type):     {winner_counts[2]} wins")
    print(f"  Format 3 (Clinical sentence): {winner_counts[3]} wins")
    
    overall_winner = winner_counts.index(max(winner_counts[1:]))
    print(f"\n  🏆 OVERALL WINNER: Format {overall_winner}")
    
    if overall_winner == 1:
        print("\n  ✅ RECOMMENDATION: Revert to just entity name (simplest and best!)")
    elif overall_winner == 2:
        print("\n  ✅ RECOMMENDATION: Use 'Name (Type)' format for context")
    else:
        print("\n  ✅ RECOMMENDATION: Keep clinical sentence templates")

if __name__ == "__main__":
    main()

