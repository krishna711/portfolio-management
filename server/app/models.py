import datetime
from typing import Optional
from enum import Enum
from sqlalchemy import UniqueConstraint
from sqlmodel import SQLModel, Field


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    hashed_password: str
    must_change_password: bool = Field(default=False, nullable=False)
    is_admin: bool = Field(default=False, nullable=False)
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow, nullable=False)


class PasswordResetAttempt(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("email_hash", "for_date", name="uix_reset_email_date"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    email_hash: str = Field(index=True)
    for_date: datetime.date = Field(index=True)
    count: int = 0
    first_attempt_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow, nullable=False)
    last_attempt_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow, nullable=False)


# ---- Screeners ----
class ScreenerSnapshot(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("scanner_key", "for_date", name="uix_scanner_date"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    scanner_key: str = Field(index=True)  # e.g. 'ha-daily-buy-ipo'
    for_date: datetime.date = Field(index=True)
    fetched_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow, nullable=False)
    row_count: int = 0


class ScreenerRow(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("snapshot_id", "symbol", name="uix_snapshot_symbol"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    snapshot_id: int = Field(foreign_key="screenersnapshot.id", index=True)
    sr: Optional[int] = None
    stock_name: Optional[str] = None
    symbol: Optional[str] = Field(default=None, index=True)
    pf_url: Optional[str] = None
    fa_url: Optional[str] = None
    chg_pct: Optional[float] = None
    price: Optional[float] = None
    volume: Optional[int] = None


class Strategy(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("user_id", "name", name="uix_user_strategy"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    name: str = Field(index=True)
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow, nullable=False)


class Broker(str, Enum):
    Zerodha = "Zerodha"
    Upstox = "Upstox"
    Dhan = "Dhan"
    Fyers = "Fyers"
    IIFL = "IIFL"
    Definedge = "Definedge"
    Groww = "Groww"
    FivePaisa = "5Paisa"
    Shoonya = "Shoonya"
    mStock = "mStock"
    PayTM = "PayTM"
    KotakNeo = "KotakNeo"
    KotakSecurities = "Kotak Securities"
    ICICIDirect = "ICICI Direct"


class Account(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    name: str
    broker: Optional[Broker] = Field(default=None)
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    access_token: Optional[str] = None
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow, nullable=False)


class Holding(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("account_id", "symbol", name="uix_account_symbol"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    account_id: int = Field(foreign_key="account.id", index=True)
    symbol: str = Field(index=True)
    quantity: float = 0
    average_price: float = 0
    total_cost: float = 0
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow, nullable=False)
    updated_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow, nullable=False)


class HoldingMeta(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    holding_id: int = Field(foreign_key="holding.id", index=True, unique=True)
    sl_price: float = 0.0


class TransactionType(str, Enum):
    BUY = "Buy"
    SELL = "Sell"


class Transaction(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    holding_id: int = Field(foreign_key="holding.id", index=True)
    strategy_id: Optional[int] = Field(default=None, foreign_key="strategy.id", index=True)
    transaction_type: TransactionType
    quantity: float
    price: float
    total: float
    transaction_date: datetime.date = Field(default_factory=lambda: datetime.datetime.utcnow().date(), index=True)
    realized_profit: float = 0.0
    notes: Optional[str] = None
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow, nullable=False)


class UserPreference(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("user_id", "key", name="uix_user_pref"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    key: str = Field(index=True)
    value: str
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow, nullable=False)
    updated_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow, nullable=False)


class IpoBoard(str, Enum):
    mainboard = "mainboard"
    sme = "sme"


class IpoListingOn(str, Enum):
    nse = "nse"
    bse = "bse"
    both = "both"


class IpoRowColor(str, Enum):
    none = "none"
    green = "green"
    orange = "orange"
    yellow = "yellow"
    red = "red"


class IPO(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("symbol", name="uix_ipo_symbol"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    symbol: str = Field(index=True)
    bse_symbol: Optional[str] = Field(default=None, index=True)
    board: IpoBoard = Field(default=IpoBoard.mainboard)
    ipo_price: Optional[float] = None
    listing_price: Optional[float] = None
    lot_size: Optional[int] = None
    total_subscription: Optional[float] = None
    qib_subscription: Optional[float] = None
    retail_subscription: Optional[float] = None
    open_date: Optional[datetime.date] = Field(default=None, index=True)
    closing_date: Optional[datetime.date] = Field(default=None, index=True)
    listing_date: Optional[datetime.date] = Field(default=None, index=True)
    listing_on: Optional[IpoListingOn] = Field(default=None)
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow, nullable=False)
    updated_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow, nullable=False)


class IpoQuote(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("symbol", name="uix_ipoquote_symbol"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    symbol: str = Field(index=True)
    last: Optional[float] = None
    fetched_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow, nullable=False)


class IpoDailyMetrics(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("symbol", "for_date", name="uix_ipodaily_symbol_date"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    symbol: str = Field(index=True)
    for_date: datetime.date = Field(index=True)
    close: Optional[float] = None
    ema21: Optional[float] = None
    ema50: Optional[float] = None
    ema100: Optional[float] = None
    above_ema21: Optional[bool] = None
    above_ema50: Optional[bool] = None
    above_ema100: Optional[bool] = None
    supertrend_10_3_up: Optional[bool] = None
    computed_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow, nullable=False)


class IpoHourlyMetrics(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("symbol", "for_hour", name="uix_ipohourly_symbol_hour"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    symbol: str = Field(index=True)
    for_hour: datetime.datetime = Field(index=True)
    close: Optional[float] = None
    supertrend_up: Optional[bool] = None
    computed_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow, nullable=False)


class IpoUserTag(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("user_id", "ipo_id", name="uix_ipotag_user_ipo"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    ipo_id: int = Field(foreign_key="ipo.id", index=True)
    color: IpoRowColor = Field(default=IpoRowColor.none)
    updated_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow, nullable=False)
