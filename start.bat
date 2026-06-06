@echo off
echo Activating virtual environment and starting Plum HQ API server...
call .venv\Scripts\activate.bat
uvicorn backend.main:app --reload
