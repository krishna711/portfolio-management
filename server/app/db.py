from sqlmodel import SQLModel, create_engine, Session, select
from sqlalchemy import inspect, text
from .config import settings
from .models import User, Strategy, Account, Holding, Transaction, PasswordResetAttempt


engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
)


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
