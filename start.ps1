Write-Host "Activating virtual environment and starting Plum HQ API server..."
.\.venv\Scripts\Activate.ps1
uvicorn backend.main:app --reload
