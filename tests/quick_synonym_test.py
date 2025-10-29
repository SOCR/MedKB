#!/usr/bin/env python3
"""
Quick test of the UMLS synonym functionality.
Run this to verify your database setup is working correctly.
"""

import psycopg2

# Update this with your actual PostgreSQL password
POSTGRES_PASSWORD = "qwerty123"

def test_synonyms_quick():
    """Quick test of synonym lookup functionality."""
    
    # Database connection
    try:
        conn = psycopg2.connect(
            dbname="umls",
            user="postgres", 
            password=POSTGRES_PASSWORD,
            host="localhost",
            port="5432"
        )
        cursor = conn.cursor()
        print("✅ Connected to UMLS database")
        
        # Test 1: Find a common medical concept by searching for "hypertension"
        print("\n🔍 Test 1: Finding synonyms for 'hypertension'")
        cursor.execute("""
            SELECT DISTINCT CUI, STR
            FROM mrconso 
            WHERE UPPER(STR) LIKE '%HYPERTENSION%'
              AND LAT = 'ENG'
              AND SUPPRESS = 'N'
            LIMIT 5
        """)
        
        results = cursor.fetchall()
        if results:
            cui_example = results[0][0]  # Get the first CUI
            print(f"  Found concept: {results[0][1]} (CUI: {cui_example})")
            
            # Get all synonyms for this CUI
            cursor.execute("""
                SELECT DISTINCT STR
                FROM mrconso 
                WHERE CUI = %s 
                  AND LAT = 'ENG' 
                  AND SUPPRESS = 'N'
                ORDER BY STR
                LIMIT 10
            """, (cui_example,))
            
            synonyms = [row[0] for row in cursor.fetchall()]
            print(f"  Synonyms found: {len(synonyms)}")
            for i, synonym in enumerate(synonyms[:5], 1):
                print(f"    {i}. {synonym}")
            if len(synonyms) > 5:
                print(f"    ... and {len(synonyms) - 5} more")
        
        # Test 2: Test SNOMED CT lookup
        print("\n🔍 Test 2: Testing SNOMED CT code lookup")
        cursor.execute("""
            SELECT DISTINCT CODE, CUI, STR
            FROM mrconso 
            WHERE SAB = 'SNOMEDCT_US'
              AND LAT = 'ENG'
              AND STR LIKE '%diabetes%'
            LIMIT 3
        """)
        
        snomed_results = cursor.fetchall()
        for code, cui, term in snomed_results:
            print(f"  SNOMED Code: {code} -> {term}")
        
        # Test 3: Test RxNorm lookup  
        print("\n🔍 Test 3: Testing RxNorm code lookup")
        cursor.execute("""
            SELECT DISTINCT CODE, CUI, STR
            FROM mrconso 
            WHERE SAB = 'RXNORM'
              AND LAT = 'ENG'
              AND STR LIKE '%insulin%'
            LIMIT 3
        """)
        
        rxnorm_results = cursor.fetchall()
        for code, cui, term in rxnorm_results:
            print(f"  RxNorm Code: {code} -> {term}")
        
        # Summary
        cursor.execute("SELECT COUNT(*) FROM mrconso WHERE LAT = 'ENG' AND SUPPRESS = 'N'")
        total_terms = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(DISTINCT CUI) FROM mrconso WHERE LAT = 'ENG' AND SUPPRESS = 'N'")
        unique_concepts = cursor.fetchone()[0]
        
        print(f"\n📊 Database Summary:")
        print(f"  Total English terms: {total_terms:,}")
        print(f"  Unique concepts: {unique_concepts:,}")
        print(f"  Average synonyms per concept: {total_terms/unique_concepts:.1f}")
        
        cursor.close()
        conn.close()
        
        print("\n✅ All tests passed! Your UMLS database is ready for synonym lookup.")
        print("\nNext steps:")
        print("1. Update POSTGRES_PASSWORD in this script with your actual password")
        print("2. Update UMLS_DB_PASSWORD in utils.py") 
        print("3. Your get_synonyms() function is now fully functional!")
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        if "authentication failed" in str(e).lower():
            print("💡 Hint: Update POSTGRES_PASSWORD in this script")
        elif "could not connect" in str(e).lower():
            print("💡 Hint: Make sure PostgreSQL is running")
        return False

if __name__ == "__main__":
    print("🧪 Quick UMLS Synonym Database Test")
    print("=" * 40)
    print("\n⚠️  IMPORTANT: Update POSTGRES_PASSWORD before running!")
    
    if POSTGRES_PASSWORD == "your_postgres_password_here":
        print("❌ Please update POSTGRES_PASSWORD in this script first!")
    else:
        test_synonyms_quick()
