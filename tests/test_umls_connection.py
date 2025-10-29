#!/usr/bin/env python3
"""
Test script for UMLS PostgreSQL database connection and synonym lookup functionality.
Run this after loading the MRCONSO data to verify everything is working.
"""

import psycopg2
import os
from typing import List, Dict, Any

# Database configuration (matches utils.py)
UMLS_DB_CONFIG = {
    'dbname': os.getenv("UMLS_DB_NAME", "umls"),
    'user': os.getenv("UMLS_DB_USER", "postgres"),
    'password': os.getenv("UMLS_DB_PASSWORD", "qwerty123"),  # UPDATE THIS WITH YOUR ACTUAL PASSWORD
    'host': os.getenv("UMLS_DB_HOST", "localhost"),
    'port': os.getenv("UMLS_DB_PORT", "5432")
}

def test_connection():
    """Test basic database connection."""
    try:
        conn = psycopg2.connect(**UMLS_DB_CONFIG)
        cursor = conn.cursor()
        
        # Test basic connectivity
        cursor.execute("SELECT version();")
        version = cursor.fetchone()[0]
        print(f"✅ Connected to PostgreSQL: {version}")
        
        # Check if MRCONSO table exists and has data
        cursor.execute("SELECT COUNT(*) FROM mrconso;")
        count = cursor.fetchone()[0]
        print(f"✅ MRCONSO table contains {count:,} records")
        
        # Test index usage
        cursor.execute("SELECT COUNT(DISTINCT CUI) FROM mrconso WHERE LAT = 'ENG';")
        cui_count = cursor.fetchone()[0]
        print(f"✅ Found {cui_count:,} unique English concepts")
        
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False

def get_synonyms_improved(ontology_id: str) -> List[str]:
    """
    Enhanced synonym lookup function that replaces the placeholder in utils.py
    Handles SNOMED CT, RxNorm, and fallback IDs.
    """
    try:
        conn = psycopg2.connect(**UMLS_DB_CONFIG)
        cursor = conn.cursor()
        
        synonyms = []
        
        # Parse the ontology ID to determine lookup strategy
        if ontology_id.startswith("SNOMEDCT:"):
            # Extract SNOMED code
            snomed_code = ontology_id.replace("SNOMEDCT:", "")
            
            # Look up CUI using SNOMED code
            cursor.execute("""
                SELECT DISTINCT CUI 
                FROM mrconso 
                WHERE CODE = %s AND SAB = 'SNOMEDCT_US'
                LIMIT 1
            """, (snomed_code,))
            
            result = cursor.fetchone()
            if result:
                cui = result[0]
                
                # Get all English synonyms for this CUI
                cursor.execute("""
                    SELECT DISTINCT STR
                    FROM mrconso 
                    WHERE CUI = %s 
                      AND LAT = 'ENG' 
                      AND SUPPRESS = 'N'
                    ORDER BY STR
                """, (cui,))
                
                synonyms = [row[0] for row in cursor.fetchall()]
        
        elif ontology_id.startswith("RXNORM:"):
            # Extract RxNorm code
            rxnorm_code = ontology_id.replace("RXNORM:", "")
            
            # Look up CUI using RxNorm code
            cursor.execute("""
                SELECT DISTINCT CUI 
                FROM mrconso 
                WHERE CODE = %s AND SAB = 'RXNORM'
                LIMIT 1
            """, (rxnorm_code,))
            
            result = cursor.fetchone()
            if result:
                cui = result[0]
                
                # Get all English synonyms for this CUI
                cursor.execute("""
                    SELECT DISTINCT STR
                    FROM mrconso 
                    WHERE CUI = %s 
                      AND LAT = 'ENG' 
                      AND SUPPRESS = 'N'
                    ORDER BY STR
                """, (cui,))
                
                synonyms = [row[0] for row in cursor.fetchall()]
        
        elif ontology_id.startswith("BIOGRAPH:"):
            # This is a fallback ID - no UMLS synonyms available
            # Return empty list or could implement custom synonym logic
            synonyms = []
        
        else:
            # Unknown format - try direct CUI lookup
            cursor.execute("""
                SELECT DISTINCT STR
                FROM mrconso 
                WHERE CUI = %s 
                  AND LAT = 'ENG' 
                  AND SUPPRESS = 'N'
                ORDER BY STR
            """, (ontology_id,))
            
            synonyms = [row[0] for row in cursor.fetchall()]
        
        cursor.close()
        conn.close()
        
        return synonyms[:20]  # Limit to 20 synonyms to avoid overwhelming the system
        
    except Exception as e:
        print(f"Error getting synonyms for {ontology_id}: {e}")
        return []

def test_synonym_lookup():
    """Test the synonym lookup with some example concepts."""
    # Test cases - you'll need real SNOMED/RxNorm codes from your data
    test_cases = [
        ("SNOMEDCT:38341003", "Hypertension"),  # Example SNOMED code
        ("RXNORM:5640", "Ibuprofen"),          # Example RxNorm code
        ("C0020538", "Direct CUI lookup"),      # Direct CUI example
    ]
    
    print("\n🔍 Testing Synonym Lookup:")
    for ontology_id, description in test_cases:
        synonyms = get_synonyms_improved(ontology_id)
        print(f"\n{description} ({ontology_id}):")
        if synonyms:
            for i, synonym in enumerate(synonyms[:5], 1):  # Show first 5
                print(f"  {i}. {synonym}")
            if len(synonyms) > 5:
                print(f"  ... and {len(synonyms) - 5} more synonyms")
        else:
            print("  No synonyms found")

def show_database_stats():
    """Show useful database statistics."""
    try:
        conn = psycopg2.connect(**UMLS_DB_CONFIG)
        cursor = conn.cursor()
        
        print("\n📊 Database Statistics:")
        
        # Total records
        cursor.execute("SELECT COUNT(*) FROM mrconso;")
        total = cursor.fetchone()[0]
        print(f"  Total MRCONSO records: {total:,}")
        
        # English records
        cursor.execute("SELECT COUNT(*) FROM mrconso WHERE LAT = 'ENG';")
        english = cursor.fetchone()[0]
        print(f"  English records: {english:,}")
        
        # Top vocabularies
        print("\n  Top vocabularies:")
        cursor.execute("""
            SELECT SAB, COUNT(*) as count
            FROM mrconso 
            WHERE LAT = 'ENG'
            GROUP BY SAB 
            ORDER BY COUNT(*) DESC 
            LIMIT 10
        """)
        
        for sab, count in cursor.fetchall():
            print(f"    {sab}: {count:,} terms")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Error getting database stats: {e}")

if __name__ == "__main__":
    print("🧪 UMLS Database Connection Test")
    print("=" * 40)
    
    print("\nUPDATE THE PASSWORD IN UMLS_DB_CONFIG FIRST!")
    print("Edit this file and set your PostgreSQL password.")
    
    if test_connection():
        show_database_stats()
        test_synonym_lookup()
        print("\n✅ All tests completed successfully!")
        print("\nNext: Update the get_synonyms() function in utils.py with the improved version.")
    else:
        print("\n❌ Database connection failed. Please check your configuration.")
