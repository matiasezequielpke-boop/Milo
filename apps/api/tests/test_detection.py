"""Detector rules, one behavior per test. Pure functions — no DB, no keys."""
from datetime import date, timedelta
from decimal import Decimal

from app.detection import Txn, detect, find_recurring, merchant_key

TODAY = date(2026, 10, 16)


def t(id, days_ago, amount, name, merchant=None, pending=False):
    return Txn(
        id=id,
        date=TODAY - timedelta(days=days_ago),
        amount=Decimal(str(amount)),
        name=name,
        merchant_name=merchant,
        pending=pending,
    )


def baseline():
    """Ordinary spending for a retired person: groceries, pharmacy, utility."""
    rows = []
    for i in range(12):
        rows.append(t(f"g{i}", 5 + i * 7, 62.40 + i, "SAFEWAY #1234", "Safeway"))
        rows.append(t(f"p{i}", 6 + i * 7, 18.99 + (i % 3) * 7.5, "CVS PHARMACY 0042", "CVS"))
    return rows


def kinds(result):
    return sorted(f.kind for f in result.findings)


def test_ordinary_spending_raises_nothing():
    assert detect(baseline(), today=TODAY).findings == []


def test_gift_card_purchase_is_high_severity_scam_pattern():
    result = detect(baseline() + [t("x", 1, 500, "GIFT CARD MALL #3", None)], today=TODAY)
    [finding] = result.findings
    assert finding.kind == "scam_pattern"
    assert finding.severity == "high"
    assert finding.transaction_id == "x"
    assert "Gift card" in finding.title


def test_small_app_store_purchase_is_not_flagged():
    assert detect(baseline() + [t("x", 1, 9.99, "GOOGLE PLAY APPS")], today=TODAY).findings == []


def test_crypto_atm_and_wire_are_flagged():
    rows = baseline() + [
        t("c", 2, 2000, "BITCOIN DEPOT ATM"),
        t("w", 3, 1500, "WESTERN UNION 0182"),
    ]
    result = detect(rows, today=TODAY)
    assert kinds(result) == ["scam_pattern", "scam_pattern"]
    assert {f.transaction_id for f in result.findings} == {"c", "w"}


def test_large_charge_from_new_merchant():
    result = detect(baseline() + [t("n", 1, 1299, "TECH SOLUTIONS ONLINE", "Tech Solutions")], today=TODAY)
    [finding] = result.findings
    assert finding.kind == "new_merchant_large"
    assert finding.severity == "high"
    assert any("First time" in r for r in finding.reasons)


def test_old_history_outside_lookback_is_context_not_alert():
    result = detect(baseline() + [t("old", 90, 1299, "TECH SOLUTIONS ONLINE")], today=TODAY)
    assert result.findings == []


def test_unusual_amount_at_known_merchant():
    result = detect(baseline() + [t("big", 1, 480, "SAFEWAY #1234", "Safeway")], today=TODAY)
    assert kinds(result) == ["unusual_amount"]


def test_duplicate_charge_within_three_days():
    rows = baseline() + [
        t("d1", 3, 74.50, "COMCAST CABLE", "Comcast"),
        t("d2", 1, 74.50, "COMCAST CABLE", "Comcast"),
    ]
    result = detect(rows, today=TODAY)
    assert kinds(result) == ["duplicate_charge"]
    assert result.findings[0].transaction_id == "d2"


def test_inflows_are_ignored():
    assert detect(baseline() + [t("r", 1, -2500, "SOCIAL SECURITY DEP")], today=TODAY).findings == []


def test_monthly_subscription_is_detected_with_cadence():
    rows = [t(f"n{i}", 10 + 30 * i, 15.49, "NETFLIX.COM 866-579", "Netflix") for i in range(5)]
    [stream] = find_recurring(rows)
    assert stream.cadence_days == 30
    assert stream.charge_count == 5
    assert stream.average_amount == Decimal("15.49")


def test_new_subscription_alert_only_when_recently_started():
    new = [t(f"s{i}", 5 + 30 * i, 29.99, "PRIME VIDEO TRIAL", "Prime Video") for i in range(2)]
    old = [t(f"o{i}", 5 + 30 * i, 10.99, "SPOTIFY", "Spotify") for i in range(8)]
    result = detect(baseline() + new + old, today=TODAY)
    new_subs = [f for f in result.findings if f.kind == "new_subscription"]
    assert [f.dedupe_key for f in new_subs] == [merchant_key(new[0])]


def test_long_running_weekly_subscription_is_not_new():
    weekly = [t(f"w{i}", 2 + 7 * i, 4.99, "NYTIMES DIGITAL", "NYTimes") for i in range(52)]
    result = detect(weekly, today=TODAY)
    assert "new_subscription" not in kinds(result)


def test_price_increase_on_recurring_charge():
    rows = [t(f"h{i}", 1 + 30 * i, 15.49 if i else 22.99, "HULU", "Hulu") for i in range(4)]
    result = detect(rows, today=TODAY)
    [increase] = [f for f in result.findings if f.kind == "price_increase"]
    assert "15.49" in increase.title and "22.99" in increase.title


def test_irregular_charges_are_not_a_subscription():
    rows = [t(f"r{i}", d, 40, "SHELL OIL", "Shell") for i, d in enumerate([3, 11, 40, 47, 90])]
    assert find_recurring(rows) == []


def test_merchant_key_collapses_reference_noise():
    a = Txn("a", TODAY, Decimal("1"), "NETFLIX.COM 866-579-7172 CA")
    b = Txn("b", TODAY, Decimal("1"), "Netflix.com")
    assert merchant_key(a) == merchant_key(b) == "netflix"


def test_alerts_are_stable_across_reruns():
    rows = baseline() + [t("x", 1, 500, "GIFT CARD MALL #3")]
    first = detect(rows, today=TODAY).findings
    second = detect(rows, today=TODAY).findings
    assert [(f.kind, f.dedupe_key) for f in first] == [(f.kind, f.dedupe_key) for f in second]


def test_recurring_utility_is_a_bill_not_a_subscription():
    rows = [t(f"u{i}", 5 + 30 * i, 80 + i, "CONED UTILITY PMT", "ConEd") for i in range(4)]
    [stream] = find_recurring(rows)
    assert stream.kind == "bill"
    rows = [t(f"x{i}", 5 + 30 * i, 120, "STATE FARM", "State Farm", ) for i in range(3)]
    plaid_categorized = [Txn(r.id, r.date, r.amount, r.name, r.merchant_name, category="RENT_AND_UTILITIES") for r in rows]
    assert find_recurring(plaid_categorized)[0].kind == "bill"


def test_new_bill_does_not_raise_new_subscription_alert():
    old = [t(f"o{i}", 5 + 30 * i, 10.99, "SPOTIFY", "Spotify") for i in range(8)]
    utility = [t(f"u{i}", 5 + 30 * i, 64.10, "NATIONAL GRID ELECTRIC") for i in range(2)]
    result = detect(old + utility, today=TODAY)
    assert "new_subscription" not in kinds(result)
