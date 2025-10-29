-- =============================================================================
-- Script to load MRCONSO.RRF data into PostgreSQL
-- Run this after creating the table structure
-- =============================================================================

-- Make sure you're connected to the umls database
\c umls;

-- Set client encoding to handle the MRCONSO.RRF file properly
SET CLIENT_ENCODING TO 'LATIN1';

-- Step 1: Load the MRCONSO.RRF file
-- IMPORTANT: Replace 'C:/path/to/your/MRCONSO.RRF' with the actual path to your file
-- Use forward slashes even on Windows, or escape backslashes (C:\\path\\to\\file)

-- If loading from a specific directory, use something like:
-- COPY mrconso FROM 'C:/Users/achus/Downloads/MRCONSO.RRF' 
\copy mrconso FROM 'MRCONSO.RRF' WITH (FORMAT csv, DELIMITER '|', NULL '', QUOTE E'\b');

-- Step 2: Verify the data was loaded correctly
SELECT 'Total records loaded:' as info, COUNT(*) as count FROM mrconso;
SELECT 'Unique concepts (CUIs):' as info, COUNT(DISTINCT CUI) as count FROM mrconso;
SELECT 'English terms:' as info, COUNT(*) as count FROM mrconso WHERE LAT = 'ENG';

-- Step 3: Show sample data
SELECT 'Sample MRCONSO records:' as info;
SELECT CUI, SAB, TTY, STR 
FROM mrconso 
WHERE LAT = 'ENG' 
LIMIT 10;

-- Step 4: Show vocabulary sources
SELECT 'Top vocabulary sources:' as info;
SELECT SAB, COUNT(*) as record_count
FROM mrconso 
GROUP BY SAB 
ORDER BY COUNT(*) DESC 
LIMIT 15;

-- Step 5: Update table statistics for query optimization
ANALYZE mrconso;

-- Optional: Create a view for easier synonym queries
CREATE OR REPLACE VIEW synonym_lookup AS
SELECT DISTINCT 
    CUI,
    STR as synonym,
    SAB as source_vocabulary,
    TTY as term_type
FROM mrconso 
WHERE LAT = 'ENG'      -- English only
  AND SUPPRESS = 'N'   -- Not suppressed
ORDER BY CUI, STR;

