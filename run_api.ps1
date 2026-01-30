# Run API Server
$env:PYTHONPATH = $PSScriptRoot
cd $PSScriptRoot
.\venv\Scripts\Activate.ps1
python -c "import sys; sys.path.insert(0, '.'); import uvicorn; from api.main import app; uvicorn.run(app, host='0.0.0.0', port=8080)"

