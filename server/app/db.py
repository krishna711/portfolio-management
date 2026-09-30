from sqlmodel import SQLModel, create_engine, Session, select
from sqlalchemy import inspect, text
from .config import settings
from .models import User, Strategy, Account, Holding, Transaction, PasswordResetAttempt


engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False, "timeout": 30} if settings.database_url.startswith("sqlite") else {},
)

if settings.database_url.startswith("sqlite"):
    # WAL allows concurrent readers during long writes (e.g. hourly metrics refresh)
    with engine.begin() as _conn:
        _conn.execute(text("PRAGMA journal_mode=WAL"))
        _conn.execute(text("PRAGMA busy_timeout=30000"))


def init_db() -> None:
    SQLModel.metadata.create_all(engine)

    insp = inspect(engine)

    def ensure_column(table: str, col: str, ddl: str) -> None:
        try:
            cols = [c.get("name") for c in insp.get_columns(table)]
        except Exception:
            cols = []
        if col in cols:
            return
        with engine.begin() as conn:
            conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN {ddl}'))

    # Lightweight migrations for existing SQLite DBs
    ensure_column("user", "must_change_password", "must_change_password INTEGER NOT NULL DEFAULT 0")
    ensure_column("user", "is_admin", "is_admin INTEGER NOT NULL DEFAULT 0")
    ensure_column("ipo", "bse_symbol", "bse_symbol TEXT")
    ensure_column("transaction", "strategy_id", "strategy_id INTEGER")
    ensure_column("transaction", "notes", "notes TEXT")

    # ipohourlymetrics: older deployments created it with only close/supertrend_up
    ensure_column("ipohourlymetrics", "open", "open REAL")
    ensure_column("ipohourlymetrics", "high", "high REAL")
    ensure_column("ipohourlymetrics", "low", "low REAL")
    ensure_column("ipohourlymetrics", "ema21", "ema21 REAL")
    ensure_column("ipohourlymetrics", "ema50", "ema50 REAL")
    ensure_column("ipohourlymetrics", "ema100", "ema100 REAL")
    ensure_column("ipohourlymetrics", "above_ema21", "above_ema21 INTEGER")
    ensure_column("ipohourlymetrics", "above_ema50", "above_ema50 INTEGER")
    ensure_column("ipohourlymetrics", "above_ema100", "above_ema100 INTEGER")
    ensure_column("ipohourlymetrics", "supertrend_10_3_up", "supertrend_10_3_up INTEGER")

    # Ensure default 'Swing' strategy exists per user and map any existing txns to it
    with Session(engine) as session:
        users = session.exec(select(User).order_by(User.id)).all()
        if users and not any(bool(getattr(u, "is_admin", False)) for u in users):
            users[0].is_admin = True
            session.add(users[0])
            session.commit()
        for u in users:
            if u.id is None:
                continue
            swing = session.exec(
                select(Strategy).where(Strategy.user_id == u.id, Strategy.name == "Swing")
            ).first()
            if not swing:
                swing = Strategy(user_id=u.id, name="Swing")
                session.add(swing)
                session.commit()
                session.refresh(swing)

            acct_ids = [a.id for a in session.exec(select(Account).where(Account.user_id == u.id)).all() if a.id is not None]
            if not acct_ids:
                continue
            holding_ids = [h.id for h in session.exec(select(Holding).where(Holding.account_id.in_(acct_ids))).all() if h.id is not None]
            if not holding_ids:
                continue
            txns = session.exec(
                select(Transaction).where(Transaction.holding_id.in_(holding_ids), Transaction.strategy_id.is_(None))
            ).all()
            if not txns:
                continue
            for t in txns:
                t.strategy_id = swing.id
                session.add(t)
            session.commit()


def get_session():
    with Session(engine) as session:
        yield session
