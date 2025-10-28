#!/usr/bin/env python3
"""
Quick test to verify SQL fixes work for synonym lookup.
"""

import psycopg2

POSTGRES_PASSWORD = "qwerty123"

def test_sql_fixes():
    try:
        conn = psycopg2.connect(
            dbname="umls",
            user="postgres",
            password=POSTGRES_PASSWORD,
            host="localhost",
            port="5432"
        )
        conn.autocommit = True  # Prevent transaction issues
        cursor = conn.cursor()
        
        print("🔍 Testing Fixed SQL Queries:")
        print("=" * 40)
        
        # Test 1: Simple synonym lookup for a known concept
        print("\n1. Testing basic synonym lookup for diabetes...")
        cursor.execute("""
            SELECT DISTINCT CUI, STR
            FROM mrconso 
            WHERE UPPER(STR) = UPPER('diabetes')
              AND LAT = 'ENG' 
              AND SUPPRESS = 'N'
            LIMIT 5
        """)
        results = cursor.fetchall()
        if results:
            print(f"   ✅ Found {len(results)} matches")
            cui = results[0][0]
            
            # Test the fixed ORDER BY query
            print(f"\n2. Testing fixed ORDER BY query for CUI {cui}...")
            cursor.execute("""
                SELECT DISTINCT STR, TTY, LENGTH(STR) as str_length,
                       CASE WHEN TTY = 'PT' THEN 1 ELSE 2 END as tty_priority
                FROM mrconso 
                WHERE CUI = %s 
                  AND LAT = 'ENG' 
                  AND SUPPRESS = 'N'
                ORDER BY tty_priority, str_length
                LIMIT 10
            """, (cui,))
            
            synonyms = cursor.fetchall()
            print(f"   ✅ Found {len(synonyms)} synonyms:")
            for i, (synonym, tty, length, priority) in enumerate(synonyms[:5], 1):
                print(f"      {i}. {synonym} ({tty})")
        else:
            print("   ❌ No matches found")
        
        # Test 2: Text search with partial matching
        print(f"\n3. Testing partial match query...")
        cursor.execute("""
            SELECT DISTINCT CUI, STR, SAB, LENGTH(STR) as str_length,
                   CASE WHEN SAB = 'SNOMEDCT_US' THEN 1 
                        WHEN SAB = 'RXNORM' THEN 2
                        WHEN SAB = 'MSH' THEN 3
                        ELSE 4 END as sab_priority
            FROM mrconso 
            WHERE UPPER(STR) LIKE UPPER('%insulin%')
              AND LAT = 'ENG' 
              AND SUPPRESS = 'N'
              AND LENGTH(STR) - LENGTH('insulin') <= 10
            ORDER BY sab_priority, str_length
            LIMIT 5
        """)
        
        partial_results = cursor.fetchall()
        print(f"   ✅ Found {len(partial_results)} partial matches:")
        for i, (cui, term, sab, length, priority) in enumerate(partial_results, 1):
            print(f"      {i}. {term} ({sab})")
        
        cursor.close()
        conn.close()
        
        print(f"\n🎉 All SQL queries work correctly!")
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Quick SQL Fixes Test")
    test_sql_fixes()
