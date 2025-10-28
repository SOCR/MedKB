@echo off
REM Script to remove files with secrets from Git history

echo ========================================
echo Removing sensitive files from Git
echo ========================================
echo.

echo Step 1: Removing files from Git tracking...
git rm --cached med_kb_dev_old.ipynb
git rm --cached med_kb_dev.ipynb
git rm --cached medical_kg_api_project\med_kb_dev.ipynb
git rm --cached medical_kg_api_project\env-vars.json

echo.
echo Step 2: Committing removal...
git add .gitignore
git commit -m "Remove notebooks and config files with API keys from tracking"

echo.
echo Step 3: Cleaning Git history (this may take a minute)...
git filter-branch --force --index-filter "git rm --cached --ignore-unmatch med_kb_dev_old.ipynb med_kb_dev.ipynb medical_kg_api_project/med_kb_dev.ipynb medical_kg_api_project/env-vars.json" --prune-empty --tag-name-filter cat -- --all

echo.
echo Step 4: Force garbage collection...
git for-each-ref --format="delete %(refname)" refs/original | git update-ref --stdin
git reflog expire --expire=now --all
git gc --prune=now --aggressive

echo.
echo ========================================
echo Done! Now you can push:
echo   git push origin main --force
echo ========================================
echo.
echo WARNING: This rewrites Git history!
echo Make sure no one else is working on this repo.
echo.
pause

