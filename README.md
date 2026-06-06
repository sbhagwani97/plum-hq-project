# plum-hq-project

This project uses a FastAPI backend that also serves the frontend templates.

## Option 1: Run via Docker (Recommended)

You can run the entire application easily using Docker Compose.

### Prerequisites
- Docker Desktop installed and running.

### 1. Environment Variables

Create a `.env` file in the `backend` directory and add the necessary API keys (e.g., `TOGETHER_API_KEY`).
```env
TOGETHER_API_KEY=your_api_key_here
```

### 2. Build and Start

Execute the following command from the root of the project:
```bash
docker-compose up --build
```

The application will be built and started in a container, accessible at:
- **Frontend Dashboard:** [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- **API Documentation:** [http://127.0.0.1:8000/api/docs](http://127.0.0.1:8000/api/docs)

Environment variables will be automatically loaded from `backend/.env`.

---

## Option 2: Run Locally

If you prefer not to use Docker, you can run the application directly using Python.

### Prerequisites
- Python 3.9+ 

### 1. Setup Virtual Environment

Create and activate a virtual environment:

**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**macOS/Linux:**
```bash
python -m venv .venv
source .venv/bin/activate
```

### 2. Install Dependencies

Install the required Python packages from the backend directory:
```bash
pip install -r backend/requirements.txt
```

### 3. Environment Variables

Create a `.env` file in the `backend` directory and add the necessary API keys (e.g., `TOGETHER_API_KEY`).
```env
TOGETHER_API_KEY=your_api_key_here
```

### 4. Start the Application

Run the FastAPI server using `uvicorn` from the root directory of the project:
```bash
uvicorn backend.main:app --reload
```

The application will be available at:
- **Frontend Dashboard:** [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- **API Documentation:** [http://127.0.0.1:8000/api/docs](http://127.0.0.1:8000/api/docs)
