#!/usr/bin/env python3
"""
Test script for the new hybrid synonym lookup system.
Demonstrates how the system now handles both standardized and non-standardized entities.
"""

import psycopg2
import sys
import os

# Add the current directory to the path so we can import utils
sys.path.append('.')
from utils import get_synonyms, get_synonyms_from_text_search

# Database configuration
POSTGRES_PASSWORD = "qwerty123"  # Update this with your password

def connect_to_umls():
    """Connect to the UMLS database."""
    try:
        conn = psycopg2.connect(
            dbname="umls",
            user="postgres",
            password=POSTGRES_PASSWORD,
            host="localhost",
            port="5432"
        )
        return conn.cursor(), conn
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return None, None

def test_hybrid_synonym_lookup():
    """Test the hybrid synonym lookup with various entity types."""
    
    cursor, conn = connect_to_umls()
    if not cursor:
        return
    
    print("🧪 HYBRID SYNONYM LOOKUP TEST")
    print("=" * 50)
    
    # Test cases representing different scenarios
    test_cases = [
        {
            "description": "✅ STANDARDIZED Entity (should use ontology ID lookup)",
            "ontology_id": "SNOMEDCT:38341003",  # Hypertension
            "original_name": "high blood pressure",
            "entity_type": "Disease"
        },
        {
            "description": "✅ STANDARDIZED Medication (should use RxNorm lookup)",
            "ontology_id": "RXNORM:5640",  # Ibuprofen
            "original_name": "ibuprofen",
            "entity_type": "Medication"
        },
        {
            "description": "🔍 FALLBACK Entity (should use text-based search)",
            "ontology_id": "BIOGRAPH:DISEASE:abc123",  # Fake fallback ID
            "original_name": "chronic fatigue syndrome",
            "entity_type": "Disease"
        },
        {
            "description": "🔍 FALLBACK Entity - Rare condition",
            "ontology_id": "BIOGRAPH:GENETIC_DISORDER:def456",
            "original_name": "neurofibromatosis",
            "entity_type": "Genetic_Disorder"
        },
        {
            "description": "🔍 FALLBACK Entity - Common symptom",
            "ontology_id": "BIOGRAPH:SYMPTOM:ghi789",
            "original_name": "chest pain",
            "entity_type": "Symptom"
        },
        {
            "description": "🔍 FALLBACK Entity - Medical procedure",
            "ontology_id": "BIOGRAPH:TREATMENT:jkl012",
            "original_name": "physical therapy",
            "entity_type": "Treatment"
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{i}. {test_case['description']}")
        print(f"   Entity: '{test_case['original_name']}' ({test_case['entity_type']})")
        print(f"   Ontology ID: {test_case['ontology_id']}")
        
        # Call the hybrid synonym function
        synonyms = get_synonyms(
            ontology_id=test_case['ontology_id'],
            umls_cursor=cursor,
            original_entity_name=test_case['original_name'],
            entity_type=test_case['entity_type']
        )
        
        if synonyms:
            print(f"   ✅ Found {len(synonyms)} synonyms:")
            for j, synonym in enumerate(synonyms[:7], 1):  # Show first 7
                print(f"      {j}. {synonym}")
            if len(synonyms) > 7:
                print(f"      ... and {len(synonyms) - 7} more")
        else:
            print("   ❌ No synonyms found")
        
        print("-" * 50)
    
    # Test direct text search function separately
    print("\n🔍 DIRECT TEXT SEARCH EXAMPLES")
    print("=" * 50)
    
    text_search_examples = [
        ("diabetes", "Disease"),
        ("insulin", "Medication"),
        ("broken bone", "Pathological_Finding"),
        ("genetic mutation", "Gene"),
        ("kidney transplant", "Treatment")
    ]
    
    for entity_name, entity_type in text_search_examples:
        print(f"\nSearching for: '{entity_name}' ({entity_type})")
        synonyms = get_synonyms_from_text_search(entity_name, entity_type, cursor, max_results=10)
        
        if synonyms:
            print(f"✅ Found {len(synonyms)} synonyms via direct text search:")
            for j, synonym in enumerate(synonyms[:5], 1):
                print(f"  {j}. {synonym}")
            if len(synonyms) > 5:
                print(f"  ... and {len(synonyms) - 5} more")
        else:
            print("❌ No synonyms found via text search")
    
    cursor.close()
    conn.close()
    
    print("\n" + "=" * 50)
    print("🎉 HYBRID SYNONYM SYSTEM TEST COMPLETE!")
    print("\nKey Benefits Demonstrated:")
    print("📊 PRECISION: Standardized entities get exact UMLS synonyms")
    print("🔍 COVERAGE: Fallback entities get text-based synonyms")
    print("🎯 QUALITY: Multiple search strategies with vocabulary prioritization")
    print("💡 RESULT: Much higher synonym coverage across all entity types!")

def show_coverage_comparison():
    """Show the improvement in synonym coverage."""
    cursor, conn = connect_to_umls()
    if not cursor:
        return
        
    print("\n📈 COVERAGE IMPROVEMENT ANALYSIS")
    print("=" * 50)
    
    # Simulate old vs new approach
    old_system_entities = [
        ("hypertension", "Disease", "SNOMEDCT:38341003"),      # Would get synonyms
        ("insulin", "Medication", "RXNORM:5640"),             # Would get synonyms
        ("rare disease", "Disease", "BIOGRAPH:DISEASE:123"),  # Would get NO synonyms
        ("gene therapy", "Treatment", "BIOGRAPH:TREATMENT:456"), # Would get NO synonyms
    ]
    
    print("OLD SYSTEM (ontology ID only):")
    old_with_synonyms = 0
    for entity_name, entity_type, ontology_id in old_system_entities:
        if ontology_id.startswith(("SNOMEDCT:", "RXNORM:")):
            synonyms = get_synonyms(ontology_id, cursor)
            print(f"✅ {entity_name}: {len(synonyms)} synonyms")
            old_with_synonyms += 1
        else:
            print(f"❌ {entity_name}: 0 synonyms")
    
    print(f"\nOLD SYSTEM COVERAGE: {old_with_synonyms}/{len(old_system_entities)} entities ({old_with_synonyms/len(old_system_entities)*100:.0f}%)")
    
    print("\nNEW HYBRID SYSTEM:")
    new_with_synonyms = 0
    for entity_name, entity_type, ontology_id in old_system_entities:
        synonyms = get_synonyms(ontology_id, cursor, entity_name, entity_type)
        if synonyms:
            print(f"✅ {entity_name}: {len(synonyms)} synonyms")
            new_with_synonyms += 1
        else:
            print(f"❌ {entity_name}: 0 synonyms")
    
    print(f"\nNEW SYSTEM COVERAGE: {new_with_synonyms}/{len(old_system_entities)} entities ({new_with_synonyms/len(old_system_entities)*100:.0f}%)")
    
    improvement = (new_with_synonyms - old_with_synonyms) / len(old_system_entities) * 100
    print(f"IMPROVEMENT: +{improvement:.0f}% more entities now have synonyms!")
    
    cursor.close()
    conn.close()

if __name__ == "__main__":
    if POSTGRES_PASSWORD == "your_postgres_password_here":
        print("❌ Please update POSTGRES_PASSWORD in this script first!")
        sys.exit(1)
    
    test_hybrid_synonym_lookup()
    show_coverage_comparison()

