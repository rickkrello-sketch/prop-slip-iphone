from typing import List, Dict, Any, Tuple
import math

# iPhone-friendly dropdown list
DEFAULT_MARKETS = [
    "Points",
    "Rebounds",
    "Assists",
    "PRA",
    "PR",
    "RA",
    "3PT Made",
    "Shots",
    "Shots on Target",
    "Passes Attempted",
    "Goalie Saves",
    "Goals",
    "Fantasy Score",
    "Other",
]

MIN_BET = 5.0  # PrizePicks minimum

def normalize_last5(s: str) -> List[float]:
    """
    Accept: '13 14 16 9 9' or '13,14,16,9,9'
    Return list of 5 floats or [].
    """
    if not s or not isinstance(s, str):
        return []
    s = s.replace(",", " ").replace("|", " ")
    parts = [p.strip() for p in s.split() if p.strip()]
    vals = []
    for p in parts:
        try:
            vals.append(float(p))
        except:
            pass
    if len(vals) != 5:
        return []
    return vals

def decide_more_less(last5: List[float], line: float) -> Tuple[str, int, int]:
    """
    Returns (pick, hits_more, hits_less).
    """
    if not last5 or len(last5) != 5:
        return ("PASS", 0, 0)

    hits_more = sum(1 for v in last5 if v > line)
    hits_less = sum(1 for v in last5 if v < line)

    if hits_more > hits_less:
        return ("MORE", hits_more, hits_less)
    if hits_less > hits_more:
        return ("LESS", hits_more, hits_less)

    # tie-breaker: avg vs line
    avg = sum(last5) / 5.0
    return ("MORE", hits_more, hits_less) if avg >= line else ("LESS", hits_more, hits_less)

def score_prop(prop: Dict[str, Any], demons_blocked: bool = True) -> Dict[str, Any]:
    """
    Conservative scoring tuned for Aggression 1.
    - Requires last5 to be considered strong.
    - Strong boost for 4/5 or 5/5 hits.
    - Penalize demon (and can be blocked entirely in recommendations).
    """
    player = prop.get("player", "")
    market = prop.get("market", "")
    line = float(prop.get("line", 0.0))
    last5 = prop.get("last5") or []
    is_goblin = bool(prop.get("is_goblin", False))
    is_demon = bool(prop.get("is_demon", False))

    pick, hm, hl = decide_more_less(last5, line)

    score = 0.0
    reasons = []

    if line <= 0:
        return {
            **prop,
            "pick": "PASS",
            "hits_more": 0,
            "hits_less": 0,
            "avg_last5": None,
            "score": 0.0,
            "grade": "FADE",
            "why": "Invalid line.",
        }

    if not last5 or len(last5) != 5:
        # Missing last5 = we do NOT trust it in bankroll mode
        return {
            **prop,
            "pick": "PASS",
            "hits_more": 0,
            "hits_less": 0,
            "avg_last5": None,
            "score": 0.0,
            "grade": "FADE",
            "why": "Missing last5 data (required).",
        }

    avg = sum(last5) / 5.0
    diff = abs(avg - line)

    # Base
    score = 50.0

    hits = hm if pick == "MORE" else hl
    score += hits * 8.0  # +0..+40

    # Cushion bonus (cap)
    score += min(diff * 6.0, 18.0)

    # Goblin tends to be a safer alt; small bonus
    if is_goblin:
        score += 6.0
        reasons.append("Goblin bonus")

    # Demon penalty (even if allowed)
    if is_demon:
        score -= 30.0
        reasons.append("Demon penalty")

    # Market risk adjustments
    m = (market or "").lower()
    if any(k in m for k in ["goals", "3pt", "steals", "blocks", "aces"]):
        score -= 4.0
        reasons.append("High-variance market penalty")
    if any(k in m for k in ["rebounds", "passes", "minutes", "assists", "pra", "fantasy"]):
        score += 2.0
        reasons.append("Volume-market bonus")

    # Clamp
    score = max(0.0, min(100.0, score))

    # Grade (tight)
    grade = "FADE"
    if score >= 78:
        grade = "ELITE"
    elif score >= 70:
        grade = "STRONG"
    elif score >= 62:
        grade = "OK"

    why = f"{pick} | hits={hits}/5 | avg={avg:.2f} vs line={line:.2f} | " + ("; ".join(reasons) if reasons else "standard")

    return {
        **prop,
        "pick": pick,
        "hits_more": hm,
        "hits_less": hl,
        "avg_last5": round(avg, 2),
        "score": round(score, 2),
        "grade": grade,
        "why": why,
    }

# -----------------------------
# LOCKED BANKROLL GATES
# -----------------------------
def _gates(bankroll: float) -> Dict[str, Any]:
    """
    Returns locked gate rules given bankroll.
    """
    if bankroll < 50:
        return {
            "max_slips": 1,
            "allowed_sizes": [2],  # default
            "allow_3_if_elite": True,
            "allow_4": False,
            "allow_6": False,
            "stake_per_slip": MIN_BET,
            "max_daily_risk": MIN_BET,
        }
    if bankroll < 85:
        return {
            "max_slips": 1,
            "allowed_sizes": [3, 2],  # primary 3, fallback 2
            "allow_3_if_elite": True,
            "allow_4": False,
            "allow_6": False,
            "stake_per_slip": MIN_BET,
            "max_daily_risk": MIN_BET,
        }
    if bankroll < 150:
        return {
            "max_slips": 2,
            "allowed_sizes": [3, 2],
            "allow_3_if_elite": True,
            "allow_4": True,   # rare, only if elite
            "allow_6": False,
            "stake_per_slip": MIN_BET,
            "max_daily_risk": MIN_BET * 2,
        }
    # 150+
    return {
        "max_slips": 2,
        "allowed_sizes": [3, 4, 5, 2],
        "allow_3_if_elite": True,
        "allow_4": True,
        "allow_6": True,   # unlocked but only if insane board + counts as slip #2
        "stake_per_slip": MIN_BET,
        "max_daily_risk": MIN_BET * 2,
    }

def _eligible(scored_props: List[Dict[str, Any]], demons_blocked: bool) -> List[Dict[str, Any]]:
    out = []
    for p in scored_props:
        if p.get("pick") not in ("MORE", "LESS"):
            continue
        if demons_blocked and bool(p.get("is_demon", False)):
            continue
        out.append(p)
    out.sort(key=lambda x: x.get("score", 0.0), reverse=True)
    return out

def _is_elite_for_size(props: List[Dict[str, Any]], size: int) -> bool:
    """
    Very strict thresholds for bankroll mode.
    """
    if len(props) < size:
        return False
    top = props[:size]
    if size == 2:
        return top[0]["score"] >= 74 and top[1]["score"] >= 70
    if size == 3:
        return all(p["score"] >= 70 for p in top) and sum(1 for p in top if p["score"] >= 78) >= 1
    if size == 4:
        return all(p["score"] >= 78 for p in top)
    if size == 5:
        return all(p["score"] >= 80 for p in top)
    if size == 6:
        return all(p["score"] >= 82 for p in top)
    return False

def _build_slip(props: List[Dict[str, Any]], size: int, slip_type: str, stake: float) -> Dict[str, Any]:
    top = props[:size]
    legs = []
    for p in top:
        legs.append({
            "player": p.get("player",""),
            "sport": p.get("sport",""),
            "market": p.get("market",""),
            "line": p.get("line",""),
            "pick": p.get("pick",""),
            "score": p.get("score",""),
            "grade": p.get("grade",""),
            "last5": p.get("last5", []),
        })
    return {"slip_type": slip_type, "stake": stake, "legs": legs}

def build_recommendations_locked(
    scored_props: List[Dict[str, Any]],
    bankroll: float,
    demons_blocked: bool,
    slips_already_saved: int,
) -> Dict[str, Any]:
    """
    Returns either SKIP or PLAY recommendations (one or two slips) under locked bankroll gates.

    Your choices:
    - Allow 2 slips when board is strong (B), but only when bankroll gates allow.
    - 6-pick only when bankroll >= 150 AND board is insane.
    """
    if bankroll <= 0:
        return {"action": "SKIP", "reason": "Bankroll is $0."}

    g = _gates(bankroll)

    # hard lock on daily slip count
    if slips_already_saved >= g["max_slips"]:
        return {"action": "SKIP", "reason": "Daily slip limit reached (locked)."}

    elig = _eligible(scored_props, demons_blocked=demons_blocked)

    # Not enough data
    if len(elig) < 2:
        return {"action": "SKIP", "reason": "Not enough eligible props with last5 data."}

    slips = []
    stake = g["stake_per_slip"]

    # Determine primary size
    primary_size = g["allowed_sizes"][0]  # default preference by gate (2 or 3)
    # For bankroll < 50, default 2-pick unless elite 3 exists
    if bankroll < 50 and g["allow_3_if_elite"]:
        if _is_elite_for_size(elig, 3):
            primary_size = 3

    # For 50–84, prefer 3, but if not elite enough, fallback to 2 or skip
    if 50 <= bankroll < 85:
        if not _is_elite_for_size(elig, 3):
            # allow 2 if elite, else skip
            if _is_elite_for_size(elig, 2):
                primary_size = 2
            else:
                return {"action": "SKIP", "reason": "Board not strong enough for bankroll mode today."}

    # For >=85, prefer 3; if not strong, fallback to 2 or skip
    if bankroll >= 85:
        if not _is_elite_for_size(elig, 3):
            if _is_elite_for_size(elig, 2):
                primary_size = 2
            else:
                return {"action": "SKIP", "reason": "Board not strong enough for bankroll mode today."}

    primary_type = f"{primary_size}-PICK FLEX"
    slips.append(_build_slip(elig, primary_size, primary_type, stake))

    # Optional second slip (your choice B) — only if gates allow AND board strong enough
    # We require at least 2*size eligible picks and elite thresholds again.
    if g["max_slips"] >= 2 and slips_already_saved == 0:
        remaining = elig[primary_size:]  # avoid duplicating legs
        # second slip should be at least 2-pick elite or 3-pick strong depending on bankroll
        if bankroll >= 85:
            # Prefer second 3-pick if remaining is elite
            if _is_elite_for_size(remaining, 3):
                slips.append(_build_slip(remaining, 3, "3-PICK FLEX (2nd slip)", stake))
            # else maybe second 2-pick if elite
            elif _is_elite_for_size(remaining, 2):
                slips.append(_build_slip(remaining, 2, "2-PICK FLEX (2nd slip)", stake))

    # Bonus 6-pick rule: only bankroll >= 150 AND insane board
    # AND it counts as slip #2, so only show it if we have capacity and first slip exists.
    if g["allow_6"] and bankroll >= 150 and len(slips) == 1 and g["max_slips"] >= 2:
        # Use the top 6 overall only if insane; do NOT force it.
        if _is_elite_for_size(elig, 6):
            # Offer 6-pick as second slip (still $5 stake)
            slips.append(_build_slip(elig, 6, "6-PICK FLEX (BONUS — INSANE BOARD)", stake))

    # Enforce max daily risk
    total_risk = sum(s["stake"] for s in slips)
    if total_risk > g["max_daily_risk"]:
        # Trim to fit
        slips = slips[: max(1, int(g["max_daily_risk"] // stake))]

    summary = f"{len(slips)} slip(s) • Stake total ${sum(s['stake'] for s in slips):.2f} • Gates: max {g['max_slips']} slip/day"
    return {
        "action": "PLAY",
        "summary": summary,
        "reason": "Locked bankroll mode: plays only when board meets elite thresholds; otherwise SKIP.",
        "slips": slips,
    }