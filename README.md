# P-Median Optimizer

A beginner-friendly Streamlit website for solving the classical p-median facility-location problem.

## What it does
- Uploads an Excel workbook with sheets `Coûts aval` and `Clients`, including the provided SCM dataset.
- Uploads CSV in either:
  - Matrix format: first column is a facility name; remaining columns are customer names. The app asks you to enter demands.
  - Long format: columns `warehouse, customer, cost, demand`.
- Lets the user choose p, the number of facilities to open.
- Solves the binary optimization model with PuLP/CBC.
- Shows selected facilities, customer assignments, weighted cost, and CSV export.

## Important modeling note
This is the **classical p-median model**. For the supplied workbook it uses the downstream cost matrix (`Coûts aval`) and customer demands (`Clients`). It does not include supplier-to-warehouse costs, warehouse opening costs, or warehouse capacities. If your course exercise requires those constraints, the mathematical model must be extended.

## Run locally (Windows)
1. Install Python 3.11 or later from https://www.python.org/downloads/ if you don't already have it. During installation, tick **Add Python to PATH**.
2. Extract this project ZIP.
3. Open the extracted folder in VS Code.
4. In VS Code choose **Terminal → New Terminal**.
5. Run these commands one by one:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
streamlit run app.py
```

If PowerShell blocks activation, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` in that terminal, then activate again.

A browser tab should open with the website at `http://localhost:8501`.

## Docker (optional)
If Docker Desktop is installed and running, open a terminal in this folder and run:

```powershell
docker build -t p-median-optimizer .
docker run --rm -p 8501:8501 p-median-optimizer
```

Then open http://localhost:8501.

## Deploy online
For the simplest Streamlit deployment:
1. Create a GitHub repository and upload `app.py`, `requirements.txt`, and optionally `README.md`.
2. Go to https://share.streamlit.io/ and sign in.
3. Select the repository, branch, and `app.py` as the main file.
4. Deploy.

Deployment options and service availability may change; follow the hosting site's current instructions.
