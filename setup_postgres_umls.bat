@echo off
REM =============================================================================
REM PostgreSQL UMLS Database Setup Script for Windows
REM This script helps automate the database creation process
REM =============================================================================

echo Starting UMLS PostgreSQL Database Setup...
echo.

REM Check if PostgreSQL is in PATH
where psql >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: psql command not found in PATH
    echo Please add PostgreSQL bin directory to your PATH or run this from PostgreSQL installation folder
    echo Example: C:\Program Files\PostgreSQL\15\bin\
    pause
    exit /b 1
)

echo Step 1: Creating UMLS database...
psql -U postgres -c "CREATE DATABASE umls;"
if %ERRORLEVEL% NEQ 0 (
    echo Warning: Database might already exist or there was an error
)

echo Step 2: Setting up table structure...
psql -U postgres -d umls -f setup_umls_database.sql

echo.
echo Setup complete! Next steps:
echo 1. Edit load_mrconso_data.sql and replace 'REPLACE_WITH_YOUR_MRCONSO_PATH' with your actual MRCONSO.RRF file path
echo 2. Run: psql -U postgres -d umls -f load_mrconso_data.sql
echo 3. Wait for the data to load (this may take several minutes)
echo.
pause
