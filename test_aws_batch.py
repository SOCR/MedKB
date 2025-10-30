#!/usr/bin/env python3
"""
Test script to debug AWS Comprehend Medical batch processing.
Tests different text formats to see what works best.
"""

import boto3
import json

# Initialize AWS client
aws_client = boto3.client('comprehendmedical', region_name='us-east-1')

# Test entities
test_entities = [
    "Weight Gain",
    "Body Weight",
    "Amylase",
    "Liver",
    "Aspirin",
    "Diabetes"
]

print("="*60)
print("AWS COMPREHEND MEDICAL BATCH TEST")
print("="*60)

# Test 1: Individual calls
print("\n📋 TEST 1: Individual API Calls (baseline)")
print("-" * 60)
for entity in test_entities:
    try:
        response = aws_client.infer_snomedct(Text=entity)
        entities = response.get('Entities', [])
        if entities:
            concepts = entities[0].get('SNOMEDCTConcepts', [])
            if concepts:
                best = max(concepts, key=lambda c: c.get('Score', 0))
                print(f"  ✅ {entity:20s} → SNOMED:{best['Code']} (conf: {best['Score']:.2f})")
            else:
                print(f"  ⚠️  {entity:20s} → No concepts")
        else:
            print(f"  ❌ {entity:20s} → No entities recognized")
    except Exception as e:
        print(f"  ❌ {entity:20s} → Error: {e}")

# Test 2: Newline-separated list (current approach)
print("\n📋 TEST 2: Newline-separated list")
print("-" * 60)
combined_text_newlines = "\n".join(test_entities)
print(f"Sending: {repr(combined_text_newlines[:100])}")
try:
    response = aws_client.infer_snomedct(Text=combined_text_newlines)
    entities = response.get('Entities', [])
    print(f"  Received {len(entities)} entities")
    for entity in entities:
        text = entity.get('Text', '')
        concepts = entity.get('SNOMEDCTConcepts', [])
        if concepts:
            best = max(concepts, key=lambda c: c.get('Score', 0))
            print(f"  ✅ {text:20s} → SNOMED:{best['Code']} (conf: {best['Score']:.2f})")
        else:
            print(f"  ⚠️  {text:20s} → No concepts")
except Exception as e:
    print(f"  ❌ Error: {e}")

# Test 3: Comma-separated list
print("\n📋 TEST 3: Comma-separated list")
print("-" * 60)
combined_text_commas = ", ".join(test_entities)
print(f"Sending: {repr(combined_text_commas)}")
try:
    response = aws_client.infer_snomedct(Text=combined_text_commas)
    entities = response.get('Entities', [])
    print(f"  Received {len(entities)} entities")
    for entity in entities:
        text = entity.get('Text', '')
        concepts = entity.get('SNOMEDCTConcepts', [])
        if concepts:
            best = max(concepts, key=lambda c: c.get('Score', 0))
            print(f"  ✅ {text:20s} → SNOMED:{best['Code']} (conf: {best['Score']:.2f})")
        else:
            print(f"  ⚠️  {text:20s} → No concepts")
except Exception as e:
    print(f"  ❌ Error: {e}")

# Test 4: Full sentences (with context)
print("\n📋 TEST 4: Full sentences with context")
print("-" * 60)
sentences = [f"The patient has {entity}." for entity in test_entities]
combined_text_sentences = " ".join(sentences)
print(f"Sending: {repr(combined_text_sentences[:100])}...")
try:
    response = aws_client.infer_snomedct(Text=combined_text_sentences)
    entities = response.get('Entities', [])
    print(f"  Received {len(entities)} entities")
    for entity in entities:
        text = entity.get('Text', '')
        concepts = entity.get('SNOMEDCTConcepts', [])
        if concepts:
            best = max(concepts, key=lambda c: c.get('Score', 0))
            print(f"  ✅ {text:20s} → SNOMED:{best['Code']} (conf: {best['Score']:.2f})")
        else:
            print(f"  ⚠️  {text:20s} → No concepts")
except Exception as e:
    print(f"  ❌ Error: {e}")

# Test 5: Clinical note format
print("\n📋 TEST 5: Clinical note format")
print("-" * 60)
clinical_note = f"Clinical findings include: {', '.join(test_entities)}. Patient presented with these conditions."
print(f"Sending: {repr(clinical_note[:100])}...")
try:
    response = aws_client.infer_snomedct(Text=clinical_note)
    entities = response.get('Entities', [])
    print(f"  Received {len(entities)} entities")
    for entity in entities:
        text = entity.get('Text', '')
        concepts = entity.get('SNOMEDCTConcepts', [])
        if concepts:
            best = max(concepts, key=lambda c: c.get('Score', 0))
            print(f"  ✅ {text:20s} → SNOMED:{best['Code']} (conf: {best['Score']:.2f})")
        else:
            print(f"  ⚠️  {text:20s} → No concepts")
except Exception as e:
    print(f"  ❌ Error: {e}")

# Test 6: Raw response inspection
print("\n📋 TEST 6: Raw response inspection (single entity)")
print("-" * 60)
test_entity = "Weight Gain"
print(f"Testing: {test_entity}")
try:
    response = aws_client.infer_snomedct(Text=test_entity)
    print("\nFull Response:")
    print(json.dumps(response, indent=2, default=str))
except Exception as e:
    print(f"  ❌ Error: {e}")

print("\n" + "="*60)
print("SUMMARY & RECOMMENDATIONS")
print("="*60)
print("""
Based on the test results above:
- Individual calls: Baseline for comparison
- Newline-separated: Our current approach
- Comma-separated: Alternative list format
- Full sentences: Natural language context
- Clinical note: Medical document style

AWS Comprehend Medical expects CLINICAL TEXT, not just lists of terms.
The API is designed to extract entities from real medical notes/documents.

Recommendations will be shown based on which format works best.
""")

