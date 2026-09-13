import csv
import datetime
import re
import sys

from sqlmodel import Session, select

sys.path.insert(0, str(__file__).rsplit("\\", 2)[0])  # add <repo>/server to sys.path

from app.db import engine, init_db  # noqa: E402
from app.models import IPO, IpoBoard, IpoListingOn  # noqa: E402


def parse_date(value: str | None) -> datetime.date | None:
    s = (value or "").strip()
    if not s:
        return None
    try:
        return datetime.datetime.strptime(s, "%d-%b-%y").date()
    except Exception:
        return None


def parse_float(value: str | None) -> float | None:
    s = (value or "").strip().replace(",", "")
    if not s:
        return None
    try:
        return float(s)
    except Exception:
        return None


def parse_int(value: str | None) -> int | None:
    s = (value or "").strip().replace(",", "")
    if not s:
        return None
    try:
        return int(float(s))
    except Exception:
        return None


def parse_listing_on(value: str | None) -> IpoListingOn | None:
    v = (value or "").upper()
    if "NSE" in v and "BSE" in v:
        return IpoListingOn.both
    if "NSE" in v:
        return IpoListingOn.nse
    if "BSE" in v:
        return IpoListingOn.bse
    return None


def make_placeholder(company: str | None, bse_code: str | None) -> str:
    bse_code = (bse_code or "").strip()
    if bse_code:
        return f"BSE:{bse_code}"
    base = (company or "").strip().upper()
    base = re.sub(r"\[[^\]]*\]", "", base)
    base = re.sub(r"[^A-Z0-9]+", "", base)
    base = base[:22] if base else "IPO"
    return f"UP:{base}"


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python server/scripts/import_ipos_csv.py <path-to-csv>")
        raise SystemExit(2)

    path = sys.argv[1]
    init_db()

    inserted = 0
    updated = 0

    with Session(engine) as session:
        with open(path, newline="", encoding="utf-8-sig") as f:
            rdr = csv.DictReader(f)
            for row in rdr:
                company = (row.get("Company") or "").strip()
                nse = (row.get("NSE Symbol") or "").strip().upper()
                bse = (row.get("BSE Script Code") or "").strip()

                sym = nse or make_placeholder(company, bse)
                if not sym:
                    continue

                ipo_price = parse_float(row.get("Issue Price (Rs.)"))
                listing_price = parse_float(row.get("Listing Price"))
                lot = parse_int(row.get("Lot Size"))
                total_sub = parse_float(row.get("Total Subscription"))
                qib_sub = parse_float(row.get("Qib Subscription"))
                retail_sub = parse_float(row.get("Retail Subscription"))
                open_date = parse_date(row.get("Opening Date"))
                closing_date = parse_date(row.get("Closing Date"))
                listing_date = parse_date(row.get("Listing Date"))
                listing_on = parse_listing_on(row.get("Listing at"))

                existing = session.exec(select(IPO).where(IPO.symbol == sym)).first()
                now = datetime.datetime.utcnow()
                if not existing:
                    existing = IPO(
                        symbol=sym,
                        name=company or sym,
                        bse_symbol=bse or None,
                        board=IpoBoard.mainboard,
                        created_at=now,
                        updated_at=now,
                    )
                    inserted += 1
                else:
                    updated += 1

                if company:
                    existing.name = company
                if bse:
                    existing.bse_symbol = bse

                existing.board = IpoBoard.mainboard

                if ipo_price is not None:
                    existing.ipo_price = ipo_price
                if listing_price is not None:
                    existing.listing_price = listing_price
                if lot is not None:
                    existing.lot_size = lot
                if total_sub is not None:
                    existing.total_subscription = total_sub
                if qib_sub is not None:
                    existing.qib_subscription = qib_sub
                if retail_sub is not None:
                    existing.retail_subscription = retail_sub
                if open_date is not None:
                    existing.open_date = open_date
                if closing_date is not None:
                    existing.closing_date = closing_date
                if listing_date is not None:
                    existing.listing_date = listing_date
                if listing_on is not None:
                    existing.listing_on = listing_on

                existing.updated_at = now

                session.add(existing)

        session.commit()

    print(f"Imported IPOs. inserted={inserted} updated={updated}")


if __name__ == "__main__":
    main()
