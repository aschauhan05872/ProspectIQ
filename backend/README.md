# ProspectIQ backend

Python package `prospectiq`: domain, application services, infrastructure adapters, FastAPI API, and worker.

```powershell
pip install -e ".[dev]"
pytest
ruff check src tests
mypy
alembic upgrade head
uvicorn prospectiq.api.main:app --reload
python -m prospectiq.worker.main
```
