# Portfolio Management System

## Features
- **Authentication**: Register/Login with JWT.
- **Accounts**: Multiple accounts per user (Zerodha, Upstox, Dhan, Fyers, IIFL).
- **Holdings**: Auto-updated on buy/sell with average price and total cost.
- **Transactions**: Buy/Sell with optional transaction date; realized P/L tracked.
- **Market Data**: Yahoo Finance latest price and previous close; historical for equity curve.
- **Dashboard**: Portfolio Value, Total Profit, Daily Change, Equity Curve, Account-wise metrics.
- **UI**: React + Vite + Tailwind, charts via Recharts.

## Tech
- Backend: FastAPI, SQLModel (SQLite), yfinance
- Frontend: React (Vite + Tailwind)

## Setup

### 1) Backend
```
python3 -m venv .venv
source .venv/bin/activate  # on Windows: .venv\\Scripts\\activate
pip install -r server/requirements.txt
# Optional: set environment
# echo "SECRET_KEY=change-me" > server/.env
uvicorn app.main:app --reload --port 8000 --app-dir server
```
Backend runs at http://localhost:8000

### 2) Frontend
```
cd client
npm install
npm run dev
```
Frontend runs at http://localhost:5173

## Usage Flow
- **Register** a user, then you are logged in.
- **Create Accounts** in `Accounts`.
- **Add Transactions** in `Transactions` (Buy/Sell; optional date).
- **View Dashboard** for portfolio value, profit, daily change, equity curve, and account-wise metrics.

## Notes
- Use Yahoo-compatible symbols (e.g., `TCS.NS`, `RELIANCE.NS`).
- CORS allows `http://localhost:5173` by default.
- SQLite db file: `server/portfolio.db`.
