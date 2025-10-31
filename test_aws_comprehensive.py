"""
Comprehensive AWS Comprehend Medical input format testing.
Tests multiple entity types with multiple examples each.
"""

import boto3
import time

# Initialize AWS Comprehend Medical
comprehend_client = boto3.client('comprehendmedical', region_name='us-east-1')

# Comprehensive test cases covering all major node types
test_cases = {
    "Disease": [
        "Diabetes", "Hypertension", "Cirrhosis", "Pneumonia", 
        "Asthma", "Tuberculosis", "Malaria", "COPD",
        "Heart Failure", "Stroke"
    ],
    "Pathological_Finding": [
        "Gallstones", "Kidney Stones", "Tumors", "Nodules",
        "Inflammation", "Scarring", "Calcification", "Edema"
    ],
    "Anatomy": [
        "Pancreas", "Liver", "Heart", "Kidney",
        "Common bile duct", "Aorta", "Spleen", "Gallbladder"
    ],
    "Medication": [
        "Aspirin", "Metformin", "Lisinopril", "Insulin",
        "Amoxicillin", "Ibuprofen", "Warfarin", "Atorvastatin"
    ],
    "Symptom": [
        "Headache", "Nausea", "Dizziness", "Fatigue",
        "Chest pain", "Shortness of breath", "Fever", "Cough"
    ],
    "Clinical_Finding": [
        "Hypertension", "Tachycardia", "Hypotension", "Fever",
        "Elevated blood sugar", "Anemia", "Jaundice"
    ],
    "Diagnostic_Procedure": [
        "CT scan", "MRI", "Ultrasound", "X-ray",
        "Blood test", "Biopsy", "ECG", "Colonoscopy"
    ],
    "Biomarker": [
        "HbA1c", "PSA", "Troponin", "Creatinine",
        "Blood pressure", "Cholesterol", "Glucose", "White blood cell count"
    ],
}

def format_1_just_name(name, entity_type):
    return name

def format_2_name_and_type(name, entity_type):
    return f"{name} ({entity_type})"

def format_3_clinical_sentence(name, entity_type):
    templates = {
        "Disease": f"Patient diagnosed with {name}.",
        "Pathological_Finding": f"Patient presents with {name}.",
        "Symptom": f"Patient reports {name}.",
        "Clinical_Finding": f"Examination reveals {name}.",
        "Medication": f"Patient prescribed {name}.",
        "Diagnostic_Procedure": f"Patient underwent {name}.",
        "Anatomy": f"Examination of patient's {name}.",
        "Biomarker": f"Patient lab test: {name}.",
    }
    return templates.get(entity_type, f"Clinical assessment: {name}.")

def test_aws_comprehend(text, api="snomed"):
    """Call AWS Comprehend Medical"""
    try:
        if api == "snomed":
            response = comprehend_client.infer_snomedct(Text=text)
            concept_key = 'SNOMEDCTConcepts'
        else:
            response = comprehend_client.infer_rx_norm(Text=text)
            concept_key = 'RxNormConcepts'
        
        entities = response.get('Entities', [])
        
        if not entities:
            return None, 0.0
        
        best_score = 0.0
        best_concept = None
        for entity in entities:
            for concept in entity.get(concept_key, []):
                if concept['Score'] > best_score:
                    best_score = concept['Score']
                    best_concept = concept
        
        return best_concept, best_score
    except Exception as e:
        return None, 0.0

def main():
    print("=" * 100)
    print("COMPREHENSIVE AWS COMPREHEND MEDICAL INPUT FORMAT TEST")
    print("=" * 100)
    print()
    
    all_results = []
    type_winners = {1: 0, 2: 0, 3: 0}
    
    for entity_type, entity_list in test_cases.items():
        print(f"\n{'='*100}")
        print(f"📦 ENTITY TYPE: {entity_type}")
        print(f"{'='*100}\n")
        
        type_results = []
        
        for name in entity_list:
            print(f"  Testing: {name}")
            
            # Determine which API to use
            api = "rxnorm" if entity_type == "Medication" else "snomed"
            
            # Test all 3 formats
            text_1 = format_1_just_name(name, entity_type)
            concept_1, score_1 = test_aws_comprehend(text_1, api)
            
            time.sleep(0.1)  # Rate limiting
            
            text_2 = format_2_name_and_type(name, entity_type)
            concept_2, score_2 = test_aws_comprehend(text_2, api)
            
            time.sleep(0.1)
            
            text_3 = format_3_clinical_sentence(name, entity_type)
            concept_3, score_3 = test_aws_comprehend(text_3, api)
            
            time.sleep(0.1)
            
            scores = [score_1, score_2, score_3]
            max_score = max(scores)
            winner_idx = scores.index(max_score) + 1 if max_score > 0 else 0
            
            winner_emoji = ["❌", "1️⃣", "2️⃣", "3️⃣"][winner_idx]
            
            print(f"    Format 1: {score_1:.2f} | Format 2: {score_2:.2f} | Format 3: {score_3:.2f} → {winner_emoji}")
            
            if winner_idx > 0:
                type_winners[winner_idx] += 1
            
            type_results.append({
                "entity": name,
                "type": entity_type,
                "score_1": score_1,
                "score_2": score_2,
                "score_3": score_3,
                "winner": winner_idx,
            })
        
        # Type summary
        type_wins = [0, 0, 0, 0]
        for r in type_results:
            if r["winner"] > 0:
                type_wins[r["winner"]] += 1
        
        print(f"\n  📊 {entity_type} Summary:")
        print(f"    Format 1 wins: {type_wins[1]}")
        print(f"    Format 2 wins: {type_wins[2]}")
        print(f"    Format 3 wins: {type_wins[3]}")
        
        if type_wins[1] > max(type_wins[2], type_wins[3]):
            print(f"    ✅ BEST for {entity_type}: Format 1 (Just name)")
        elif type_wins[2] > max(type_wins[1], type_wins[3]):
            print(f"    ✅ BEST for {entity_type}: Format 2 (Name + Type)")
        elif type_wins[3] > max(type_wins[1], type_wins[2]):
            print(f"    ✅ BEST for {entity_type}: Format 3 (Clinical sentence)")
        else:
            print(f"    ⚠️  {entity_type}: Mixed results")
        
        all_results.extend(type_results)
    
    # Overall summary
    print("\n" + "=" * 100)
    print("OVERALL SUMMARY")
    print("=" * 100)
    print(f"\nTotal entities tested: {len(all_results)}")
    print(f"Format 1 (Just name) wins:       {type_winners[1]}")
    print(f"Format 2 (Name + type) wins:     {type_winners[2]}")
    print(f"Format 3 (Clinical sentence) wins: {type_winners[3]}")
    
    # Recommendation by entity type
    print("\n" + "=" * 100)
    print("RECOMMENDATIONS BY ENTITY TYPE")
    print("=" * 100)
    print()
    
    recommendations = {}
    for entity_type in test_cases.keys():
        type_results = [r for r in all_results if r["type"] == entity_type]
        type_wins = [0, 0, 0, 0]
        for r in type_results:
            if r["winner"] > 0:
                type_wins[r["winner"]] += 1
        
        max_wins = max(type_wins[1:])
        if max_wins == 0:
            best_format = 0
        else:
            best_format = type_wins.index(max_wins)
        
        recommendations[entity_type] = best_format
        
        format_name = ["No winner", "Just name", "Name + Type", "Clinical sentence"][best_format]
        print(f"  {entity_type:<25} → Format {best_format}: {format_name} ({type_wins[best_format]} wins)")
    
    # Final recommendation
    print("\n" + "=" * 100)
    print("FINAL RECOMMENDATION")
    print("=" * 100)
    print()
    print("✅ Use ENTITY-TYPE DEPENDENT formatting:")
    print()
    for entity_type, best_format in recommendations.items():
        format_name = ["Unknown", "Just name", "Name + Type", "Clinical sentence"][best_format]
        print(f"    {entity_type:<25} → {format_name}")

if __name__ == "__main__":
    main()

