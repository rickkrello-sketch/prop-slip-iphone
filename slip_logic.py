from typing import List, Dict, Any, Tuple
import math

def _safe_float(x, default=None):
    try:
        return float(x)
    except:
        return default

def filter_props(
    props: List[Dict[str, Any]],
    sports_allowed: List[str],
    demons_blocked: bool = True,
) -> List[Dict[str, Any]]:
    allowed = [s.upper() for s in sports_allowed] if sports_allowed else []
    out = []
    for p in props:
        sport = (p.get("sport") or "").upper()
        if allowed and sport and sport not in allowed:
            continue
        if demons_blocked and bool(p.get("is_demon", False)):
            continue
        out.append(p)
    return out

def decide_side_from_last5(prop: Dict[str, Any]) -> Tuple[str, int, int]:
    """
    Returns (recommended_side, hits_more, hits_less) using last5 vs line.
    If last5 missing, returns ("PASS", 0, 0).
    """
    last5 = prop.get("last5") or []
    line = _safe_float(prop.get("line"), None)
    if not isinstance(last5, list) or len(last5) != 5 or line is None:
        return ("PASS", 0, 0)

    hits_more = sum(1 for v in last5 if _safe_float(v, -999) > line)
    hits_less = sum(1 for v in last5 if _safe_float(v, 999) < line)

    # Choose by higher hit rate; tie-breaker by avg distance
    if hits_more > hits_less:
        return ("MORE", hits_more, hits_less)
    if hits_less > hits_more:
        return ("LESS", hits_more, hits_less)

    avg = sum(float(v) for v in last5) / 5.0
    if avg >= line:
        return ("MORE", hits_more, hits_less)
    return ("LESS", hits_more, hits_less)

def score_prop_aggression1(prop: Dict[str, Any]) -> float:
    """
    Conservative score:
    - Must have last5 to be strong.
    - 4/5 or 5/5 hit-rate gets boosted heavily.
    - Demons removed upstream (usually).
    """
    side, hits_more, hits_less = decide_side_from_last5(prop)
    if side == "PASS":
        return 0.0

    hits = hits_more if side == "MORE" else hits_less
    line = float(prop.get("line", 0))
    last5 = prop.get("last5") or []
    avg = sum(float(v) for v in last5) / 5.0
    diff = abs(avg - line)

    score = 50.0
    score += hits * 8.0            # up to +40
    score += min(diff * 6.0, 18.0) # cushion bonus (capped)
    if prop.get("is_goblin"):
        score += 6.0               # goblin = safer alt often
    if prop.get("is_demon"):
        score -= 30.0              # extra penalty (even if allowed)

    # slight market risk adjustments
    market = (prop.get("market") or "").lower()
    if any(k in market for k in ["goals", "3pt", "steals", "blocks", "aces"]):
        score -= 4.0
    if any(k in market for k in ["rebounds", "passes", "minutes", "assists", "pra"]):
        score += 2.0

    return round(max(0.0, min(100.0, score)), 2)

def score_props(props: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    scored = []
    for p in props:
        side, hm, hl = decide_side_from_last5(p)
        p2 = dict(p)
        p2["recommended"] = side
        p2["hits_more"] = hm
        p2["hits_less"] = hl
        p2["score"] = score_prop_aggression1(p)
        scored.append(p2)
    return scored

def min_bet_allowed() -> float:
    return 5.0  # PrizePicks minimum

def recommended_slip_size(bankroll: float) -> int:
    # With $5 min:
    # < $85 => 2-pick only (one slip/day)
    # >= $85 => 3-pick allowed
    return 2 if bankroll < 85 else 3

def build_recommendation_aggression1(scored: List[Dict[str, Any]], bankroll: float) -> Dict[str, Any]:
    """
    Returns PLAY/SKIP + slip + stake.
    Agg=1 rules:
      - bankroll < 85 -> only 2-pick flex, one $5 slip max/day
      - demons blocked upstream
      - requires strong board: top legs must have last5 + high score
    """
    # Only playable legs: must have last5 + recommended != PASS + offered side exists
    playable = []
    for p in scored:
        if p.get("recommended") not in ("MORE", "LESS"):
            continue
        if not isinstance(p.get("last5"), list) or len(p["last5"]) != 5:
            continue
        offered = p.get("offered_sides") or ["MORE", "LESS"]
        if p["recommended"] not in offered:
            continue
        playable.append(p)

    playable.sort(key=lambda x: x.get("score", 0), reverse=True)

    size = recommended_slip_size(bankroll)

    # SKIP logic (you requested YES)
    if len(playable) < size:
        return {"action": "SKIP", "reason": f"Not enough strong picks with last5 to build a {size}-pick."}

    # Strength thresholds
    top = playable[:size]
    if size == 2:
        # both should be strong
        if not (top[0]["score"] >= 74 and top[1]["score"] >= 70):
            return {"action": "SKIP", "reason": "Top 2 picks aren’t strong enough for bankroll mode (Agg1)."}
    else:
        # 3-pick: all should be decent
        if not all(x["score"] >= 68 for x in top):
            return {"action": "SKIP", "reason": "Top 3 picks aren’t strong enough for bankroll mode (Agg1)."}

    # Stake: with bankroll < 85, total daily exposure must be exactly $5 max
    stake = min_bet_allowed()
    if bankroll >= 165:
        # allow $10 total on elite boards later; v1 keeps it at $5 primary anyway
        stake = 5.0

    slip_type = f"{size}-PICK FLEX"
    legs = []
    for p in top:
        legs.append({
            "player": p.get("player",""),
            "sport": p.get("sport",""),
            "market": p.get("market",""),
            "line": p.get("line"),
            "recommended": p.get("recommended"),
            "score": p.get("score"),
            "last5": p.get("last5"),
            "hits_more": p.get("hits_more"),
            "hits_less": p.get("hits_less"),
            "is_goblin": bool(p.get("is_goblin", False)),
            "is_demon": bool(p.get("is_demon", False)),
        })

    return {
        "action": "PLAY",
        "slip_type": slip_type,
        "stake": stake,
        "legs": legs,
        "reason": "Aggression 1 bankroll mode: one slip/day, demons blocked, SKIP if not strong.",
    }