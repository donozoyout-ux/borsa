import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

BASE_DIR = Path(__file__).resolve().parent
ALERTS_FILE = BASE_DIR / "data" / "alerts.json"

ConditionType = Literal["above", "below"]


@dataclass
class Alert:
    id: str
    symbol: str
    target_price: float
    condition: ConditionType
    near_percent: float
    note: str
    active: bool
    created_at: str
    near_sent: bool = False
    hit_sent: bool = False


def _ensure_data_dir() -> None:
    ALERTS_FILE.parent.mkdir(exist_ok=True)


def load_alerts() -> list[dict]:
    _ensure_data_dir()
    if not ALERTS_FILE.exists():
        ALERTS_FILE.write_text("[]", encoding="utf-8")
        return []
    try:
        return json.loads(ALERTS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def save_alerts(alerts: list[dict]) -> None:
    _ensure_data_dir()
    ALERTS_FILE.write_text(json.dumps(alerts, ensure_ascii=False, indent=2), encoding="utf-8")


def create_alert(
    symbol: str,
    target_price: float,
    condition: ConditionType,
    near_percent: float,
    note: str = "",
) -> dict:
    alert = Alert(
        id=str(uuid4()),
        symbol=symbol.strip().upper().replace(".IS", ""),
        target_price=float(target_price),
        condition=condition,
        near_percent=float(near_percent),
        note=note.strip(),
        active=True,
        created_at=datetime.now().isoformat(timespec="seconds"),
    )
    alerts = load_alerts()
    alerts.append(asdict(alert))
    save_alerts(alerts)
    return asdict(alert)


def delete_alert(alert_id: str) -> bool:
    alerts = load_alerts()
    new_alerts = [a for a in alerts if a.get("id") != alert_id]
    save_alerts(new_alerts)
    return len(new_alerts) != len(alerts)


def set_alert_flags(alert_id: str, *, near_sent: bool | None = None, hit_sent: bool | None = None, active: bool | None = None) -> None:
    alerts = load_alerts()
    for alert in alerts:
        if alert.get("id") == alert_id:
            if near_sent is not None:
                alert["near_sent"] = near_sent
            if hit_sent is not None:
                alert["hit_sent"] = hit_sent
            if active is not None:
                alert["active"] = active
            break
    save_alerts(alerts)


def is_near(price: float, target: float, near_percent: float) -> bool:
    if target <= 0:
        return False
    diff_percent = abs(price - target) / target * 100
    return diff_percent <= near_percent


def is_hit(price: float, target: float, condition: ConditionType) -> bool:
    if condition == "above":
        return price >= target
    if condition == "below":
        return price <= target
    return False
