-- =============================================================================
-- UMLS Database Setup for MRCONSO.RRF
-- This script creates the database, table structure, and indexes needed
-- for synonym lookup in your Medical Knowledge Graph project
-- =============================================================================

-- Step 1: Create the UMLS database (run this as postgres superuser)
-- CREATE DATABASE umls;

-- Step 2: Connect to the umls database and create the table
-- \c umls;

-- Step 3: Create the MRCONSO table
-- MRCONSO.RRF contains the concept names and synonyms from UMLS
-- Format: CUI|LAT|TS|LUI|STT|SUI|ISPREF|AUI|SAUI|SCUI|SDUI|SAB|TTY|CODE|STR|SRL|SUPPRESS|CVF
DROP TABLE IF EXISTS mrconso;

CREATE TABLE mrconso (
    CUI VARCHAR(8) NOT NULL,           -- Concept Unique Identifier
    LAT CHAR(3) NOT NULL,              -- Language (ENG for English)
    TS CHAR(1) NOT NULL,               -- Term Status
    LUI VARCHAR(10) NOT NULL,          -- Lexical Unique Identifier
    STT VARCHAR(3) NOT NULL,           -- String Type
    SUI VARCHAR(10) NOT NULL,          -- String Unique Identifier
    ISPREF CHAR(1) NOT NULL,           -- Preferred flag
    AUI VARCHAR(9) NOT NULL,           -- Atom Unique Identifier
    SAUI VARCHAR(50),                  -- Source Atom Unique Identifier
    SCUI VARCHAR(100),                 -- Source Concept Unique Identifier
    SDUI VARCHAR(100),                 -- Source Descriptor Unique Identifier
    SAB VARCHAR(40) NOT NULL,          -- Source Abbreviation
    TTY VARCHAR(40) NOT NULL,          -- Term Type
    CODE VARCHAR(100) NOT NULL,        -- Concept Code
    STR TEXT NOT NULL,                 -- String (the actual term/synonym)
    SRL INTEGER NOT NULL,              -- Source Restriction Level
    SUPPRESS CHAR(1) NOT NULL,         -- Suppress flag
    CVF INTEGER,                       -- Content View Flag
    EXTRA_COL TEXT                     -- Handle trailing pipe character
);

-- Step 4: Create indexes for performance
CREATE INDEX idx_mrconso_cui ON mrconso(CUI);
CREATE INDEX idx_mrconso_str ON mrconso(STR);
CREATE INDEX idx_mrconso_code ON mrconso(CODE);
CREATE INDEX idx_mrconso_sab ON mrconso(SAB);
CREATE INDEX idx_mrconso_cui_sab ON mrconso(CUI, SAB);
CREATE INDEX idx_mrconso_cui_lat ON mrconso(CUI, LAT);

-- Create a composite index for the most common query pattern
-- (finding synonyms for a CUI in English)
CREATE INDEX idx_mrconso_cui_lat_suppress ON mrconso(CUI, LAT, SUPPRESS);

-- Add some basic statistics
ANALYZE mrconso;

-- Show table structure
\d mrconso;

-- Basic info queries you can run after loading data:
-- SELECT COUNT(*) FROM mrconso;
-- SELECT COUNT(DISTINCT CUI) FROM mrconso;
-- SELECT SAB, COUNT(*) FROM mrconso GROUP BY SAB ORDER BY COUNT(*) DESC LIMIT 10;

