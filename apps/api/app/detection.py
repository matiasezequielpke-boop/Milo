"""Warden's detector: finds charges a family should look at.

Deterministic rules, not a model call, on purpose. Every alert has to be
explainable to a 75-year-old and to a regulator ("flagged because it's the
first time you've paid this merchant and it's 6x your usual purchase"),
cheap enough to run on every sync, and testable without an API key. The
agent (app/agent/) explains alerts in conversation; it doesn't create them.

Inputs are plain dataclasses so this module never touches the database —
app/monitoring.py loads transactions, calls `detect()`, and persists.

Sign convention follows Plaid: a positive amount is money leaving the
account. Inflows (refunds, deposits) are ignored by every rule here.
"""
from __future__ import annotations

import re
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

# Payment rails scammers ask older adults to use, because the money can't
# be pulled back. Thresholds keep a $15 app-store purchase from paging the
# family at midnight.
GIFT_CARD = re.compile(
    r"gift\s*card|giftcard|green\s*dot|vanilla\s*(visa|gift|mastercard)|one\s*vanilla|itunes|apple\s*gift|"
    r"google\s*play|steam\s*(games|wallet|card)|target\s*gift|ebay\s*gift|razer\s*gold"
)
MONEY_TRANSFER = re.compile(r"western\s*union|moneygram|wire\s*(transfer|out|to)|\bwire\b|ria\s*money|world\s*remit|remitly")
CRYPTO = re.compile(r"coinbase|binance|kraken|crypto|bitcoin|\bbtc\b|coinflip|bitcoin\s*depot|athena\s*bitcoin|coinme|gemini\s*trust")
P2P = re.compile(r"zelle|venmo|cash\s*app|\bsquare\s*cash\b|paypal")
CASH = re.compile(r"\batm\b|cash\s*withdrawal|withdrawal")
# Recurring charges that are bills, not subscriptions: nobody should be
# nudged to "cancel" the electricity. Matched on Plaid's category when
# present, otherwise on the merchant text.
ESSENTIAL_CATEGORIES = {"RENT_AND_UTILITIES", "LOAN_PAYMENTS", "GOVERNMENT_AND_NON_PROFIT", "BANK_FEES", "MEDICAL"}
ESSENTIAL = re.compile(
    r"util|electric|power|energy|con\s*ed|water|sewer|gas\s*(co|company|service)|insurance|mortgage|rent\b|"
    r"medicare|pharmacy|phone|wireless|verizon|at\s*t|t-mobile|comcast|xfinity|spectrum|internet|cable|property\s*tax"
)

_NOISE = re.compile(
    r"\b(pos|debit|credit|purchase|card|ach|payment|pmt|recurring|online|www|com|inc|llc|co|ref|id|des|indn|ppd|web)\b"
)
_NON_ALNUM = re.compile(r"[^a-z ]+")


@dataclass(frozen=True)
class Txn:
    id: str
    date: date
    amount: Decimal
    name: str
    merchant_name: str | None = None
    pending: bool = False
    category: str | None = None

    @property
    def label(self) -> str:
        return self.merchant_name or self.name

    @property
    def is_outflow(self) -> bool:
        return self.amount > 0


@dataclass
class Finding:
    kind: str
    dedupe_key: str
    severity: str  # "low" | "medium" | "high"
    title: str
    reasons: list[str]
    transaction_id: str | None = None


@dataclass
class RecurringStream:
    merchant_key: str
    merchant_name: str
    cadence_days: int
    amounts: list[Decimal]
    dates: list[date]
    # The first charge ever seen from this merchant, which can predate the
    # recent run in `dates` (that's capped at the last six charges).
    first_date: date
    charge_count: int
    transaction_ids: list[str] = field(default_factory=list)
    # "subscription" (can be cancelled) or "bill" (utilities, insurance...).
    kind: str = "subscription"

    @property
    def average_amount(self) -> Decimal:
        return (sum(self.amounts) / len(self.amounts)).quantize(Decimal("0.01"))

    @property
    def last_amount(self) -> Decimal:
        return self.amounts[-1]


@dataclass
class DetectionResult:
    findings: list[Finding]
    streams: list[RecurringStream]


def merchant_key(txn: Txn) -> str:
    """Stable grouping key: 'NETFLIX.COM 866-579' and 'Netflix' collapse
    together; reference numbers and card-network noise are dropped."""
    text = (txn.merchant_name or txn.name).lower()
    text = _NON_ALNUM.sub(" ", text)
    text = _NOISE.sub(" ", text)
    # Dropping short tokens also drops trailing state codes ("... CA").
    words = [w for w in text.split() if len(w) > 2]
    return " ".join(words[:4]) or text.strip() or "unknown"


def _money(value: Decimal) -> str:
    return f"${value:,.2f}"


# Cadences we recognize, with how far an interval may drift and still count.
_CADENCES: tuple[tuple[int, int, int], ...] = (
    (7, 6, 8),
    (14, 13, 16),
    (30, 26, 35),
    (91, 84, 98),
    (365, 350, 380),
)


def _cadence(intervals: list[int]) -> int | None:
    for cadence, low, high in _CADENCES:
        if all(low <= i <= high for i in intervals):
            return cadence
    return None


def _amounts_consistent(amounts: list[Decimal], tolerance: Decimal = Decimal("0.25")) -> bool:
    median = Decimal(str(statistics.median(amounts)))
    if median <= 0:
        return False
    return all(abs(a - median) / median <= tolerance for a in amounts)


def find_recurring(txns: list[Txn]) -> list[RecurringStream]:
    by_merchant: dict[str, list[Txn]] = defaultdict(list)
    for t in txns:
        if t.is_outflow and not t.pending:
            by_merchant[merchant_key(t)].append(t)

    streams = []
    for key, items in by_merchant.items():
        items.sort(key=lambda t: (t.date, t.id))
        # Same-day duplicates aren't a cadence; keep the first of each day.
        deduped: list[Txn] = []
        for t in items:
            if not deduped or t.date != deduped[-1].date:
                deduped.append(t)
        if len(deduped) < 2:
            continue
        # Look at the most recent run only (a cancelled-and-resumed
        # subscription shouldn't fail the cadence check on old gaps).
        recent = deduped[-6:]
        intervals = [(b.date - a.date).days for a, b in zip(recent, recent[1:])]
        cadence = _cadence(intervals)
        if cadence is None:
            continue
        amounts = [t.amount for t in recent]
        if len(recent) == 2:
            # Two charges are only a subscription if they're the same
            # amount on a monthly-or-longer rhythm.
            if cadence < 30 or abs(amounts[0] - amounts[1]) > max(Decimal("1.00"), amounts[0] * Decimal("0.01")):
                continue
        elif not _amounts_consistent(
            amounts[:-1] or amounts,
            # Weekly groceries look like a cadence; a real weekly or
            # biweekly subscription charges the same amount every time.
            Decimal("0.02") if cadence < 30 else Decimal("0.25"),
        ):
            continue
        last = recent[-1]
        essential = (last.category or "").upper() in ESSENTIAL_CATEGORIES or bool(
            ESSENTIAL.search(f"{last.name} {last.merchant_name or ''}".lower())
        )
        streams.append(
            RecurringStream(
                kind="bill" if essential else "subscription",
                merchant_key=key,
                merchant_name=recent[-1].label,
                cadence_days=cadence,
                amounts=amounts,
                dates=[t.date for t in recent],
                first_date=deduped[0].date,
                charge_count=len(deduped),
                transaction_ids=[t.id for t in recent],
            )
        )
    return streams


def _cadence_words(days: int) -> str:
    return {7: "every week", 14: "every two weeks", 30: "every month", 91: "every three months", 365: "every year"}.get(
        days, f"every {days} days"
    )


def detect(txns: list[Txn], *, today: date | None = None, lookback_days: int = 30) -> DetectionResult:
    """Run every rule. Only transactions within `lookback_days` of `today`
    can raise a per-charge alert; older history is context (what's normal
    for this person, which merchants they already know)."""
    today = today or date.today()
    window_start = today - timedelta(days=lookback_days)
    history = sorted(txns, key=lambda t: (t.date, t.id))
    outflows = [t for t in history if t.is_outflow]
    findings: list[Finding] = []

    typical = Decimal(str(statistics.median([t.amount for t in outflows]))) if outflows else Decimal("0")
    seen_before: dict[str, list[Txn]] = defaultdict(list)

    for t in outflows:
        key = merchant_key(t)
        prior = list(seen_before[key])
        seen_before[key].append(t)
        if t.date < window_start:
            continue
        text = f"{t.name} {t.merchant_name or ''}".lower()
        label = t.label

        if GIFT_CARD.search(text) and t.amount >= 50:
            findings.append(
                Finding(
                    kind="scam_pattern",
                    dedupe_key=t.id,
                    severity="high",
                    title=f"Gift card purchase: {_money(t.amount)} at {label}",
                    reasons=[
                        "Gift cards are the payment scammers ask for most often, because they can't be reversed.",
                        "No real company, bank, or government agency asks to be paid in gift cards.",
                    ],
                    transaction_id=t.id,
                )
            )
            continue
        if CRYPTO.search(text) and t.amount >= 100:
            findings.append(
                Finding(
                    kind="scam_pattern",
                    dedupe_key=t.id,
                    severity="high",
                    title=f"Cryptocurrency purchase: {_money(t.amount)} at {label}",
                    reasons=[
                        "Crypto ATMs and exchanges are a common way scammers move victims' money out of reach.",
                        "Once sent, crypto payments are almost impossible to recover.",
                    ],
                    transaction_id=t.id,
                )
            )
            continue
        if MONEY_TRANSFER.search(text) and t.amount >= 200:
            findings.append(
                Finding(
                    kind="scam_pattern",
                    dedupe_key=t.id,
                    severity="high",
                    title=f"Money transfer: {_money(t.amount)} via {label}",
                    reasons=[
                        "Wire and money-transfer payments usually can't be pulled back once sent.",
                        "Impostor and romance scams commonly ask for payment this way.",
                    ],
                    transaction_id=t.id,
                )
            )
            continue
        if P2P.search(text) and t.amount >= 500 and not prior:
            findings.append(
                Finding(
                    kind="scam_pattern",
                    dedupe_key=t.id,
                    severity="medium",
                    title=f"Large app payment to someone new: {_money(t.amount)} via {label}",
                    reasons=[
                        "First payment of this size through this app.",
                        "Payment-app transfers to strangers are rarely refunded by banks.",
                    ],
                    transaction_id=t.id,
                )
            )
            continue
        if CASH.search(text) and t.amount >= 500:
            findings.append(
                Finding(
                    kind="large_cash_withdrawal",
                    dedupe_key=t.id,
                    severity="medium",
                    title=f"Large cash withdrawal: {_money(t.amount)}",
                    reasons=["Scammers sometimes ask for cash to be withdrawn and handed to a courier or mailed."],
                    transaction_id=t.id,
                )
            )
            continue

        large_threshold = max(Decimal("200"), typical * 3)
        if not prior and t.amount >= large_threshold:
            reasons = [f"First time paying {label}."]
            if typical > 0:
                reasons.append(f"About {int(t.amount / typical)}x a typical purchase ({_money(typical)}).")
            findings.append(
                Finding(
                    kind="new_merchant_large",
                    dedupe_key=t.id,
                    severity="high" if t.amount >= 1000 else "medium",
                    title=f"Large charge from a new merchant: {_money(t.amount)} at {label}",
                    reasons=reasons,
                    transaction_id=t.id,
                )
            )
            continue

        if len(prior) >= 3:
            merchant_median = Decimal(str(statistics.median([p.amount for p in prior])))
            if merchant_median > 0 and t.amount >= 100 and t.amount >= merchant_median * 3:
                findings.append(
                    Finding(
                        kind="unusual_amount",
                        dedupe_key=t.id,
                        severity="medium",
                        title=f"Unusually large charge at {label}: {_money(t.amount)}",
                        reasons=[f"Usually about {_money(merchant_median)} here — this is {int(t.amount / merchant_median)}x that."],
                        transaction_id=t.id,
                    )
                )
                continue

        duplicate = next(
            (p for p in reversed(prior) if p.amount == t.amount and 0 <= (t.date - p.date).days <= 3 and p.id != t.id),
            None,
        )
        if duplicate is not None and not t.pending:
            findings.append(
                Finding(
                    kind="duplicate_charge",
                    dedupe_key=t.id,
                    severity="medium",
                    title=f"Possible double charge: {_money(t.amount)} at {label}",
                    reasons=[f"Same amount charged by {label} on {duplicate.date.isoformat()} and {t.date.isoformat()}."],
                    transaction_id=t.id,
                )
            )

    streams = find_recurring(history)
    history_start = history[0].date if history else today
    for s in streams:
        # A recently started subscription is the classic free-trial trap.
        # Only call it "new" if we've watched at least 60 days without it —
        # on a first bank connection everything would otherwise look new.
        if (
            s.kind == "subscription"
            and s.first_date >= today - timedelta(days=100)
            and (s.first_date - history_start).days >= 60
        ):
            findings.append(
                Finding(
                    kind="new_subscription",
                    dedupe_key=s.merchant_key,
                    severity="medium" if s.average_amount >= 50 else "low",
                    title=f"New recurring charge: {s.merchant_name}, {_money(s.last_amount)} {_cadence_words(s.cadence_days)}",
                    reasons=[
                        f"Started {s.first_date.isoformat()}; charged {s.charge_count} times so far.",
                        "Check that this is a service still wanted — free trials often turn into paid plans.",
                    ],
                    transaction_id=s.transaction_ids[-1],
                )
            )
        if len(s.amounts) >= 3:
            previous = Decimal(str(statistics.median(s.amounts[:-1])))
            if s.last_amount - previous > max(Decimal("1.00"), previous * Decimal("0.10")):
                findings.append(
                    Finding(
                        kind="price_increase",
                        dedupe_key=f"{s.merchant_key}:{s.dates[-1].isoformat()}",
                        severity="low",
                        title=f"{s.merchant_name} went up: {_money(previous)} → {_money(s.last_amount)}",
                        reasons=[f"The recurring charge increased by {_money(s.last_amount - previous)}."],
                        transaction_id=s.transaction_ids[-1],
                    )
                )
    return DetectionResult(findings=findings, streams=streams)
