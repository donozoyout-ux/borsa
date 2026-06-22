import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

BASE_DIR = Path(__file__).resolve().parent
PORTFOLIO_FILE = BASE_DIR / "data" / "portfolio.json"


@dataclass
class PortfolioItem:
    id: str
    symbol: str
    quantity: float
    avg_cost: float
    note: str
    created_at: str


def _ensure_data_dir() -> None:
    PORTFOLIO_FILE.parent.mkdir(exist_ok=True)


def load_portfolio() -> list[dict]:
    _ensure_data_dir()
    if not PORTFOLIO_FILE.exists():
        PORTFOLIO_FILE.write_text("[]", encoding="utf-8")
        return []
    try:
        return json.loads(PORTFOLIO_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def save_portfolio(items: list[dict]) -> None:
    _ensure_data_dir()
    PORTFOLIO_FILE.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def add_item(symbol: str, quantity: float, avg_cost: float, note: str = "") -> dict:
    item = PortfolioItem(
        id=str(uuid4()),
        symbol=symbol.strip().upper().replace(".IS", ""),
        quantity=float(quantity),
        avg_cost=float(avg_cost),
        note=note.strip(),
        created_at=datetime.now().isoformat(timespec="seconds"),
    )
    items = load_portfolio()
    items.append(asdict(item))
    save_portfolio(items)
    return asdict(item)


def delete_item(item_id: str) -> bool:
    items = load_portfolio()
    new_items = [i for i in items if i.get("id") != item_id]
    save_portfolio(new_items)
    return len(new_items) != len(items)


def update_item(item_id: str, **kwargs) -> bool:
    items = load_portfolio()
    for item in items:
        if item.get("id") == item_id:
            for k, v in kwargs.items():
                if v is not None:
                    item[k] = v
            save_portfolio(items)
            return True
    return False
