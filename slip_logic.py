from typing import List, Dict, Any, Tuple

def filter_props(
    props: List[Dict[str, Any]],
    sports_allowed: List[str],
    demons_blocked: bool = True,
) -> List[Dict[str, Any]]:
    out = []
    for p in props:
        sport = (p.get("sport") or "").upper()
        if sports_allowed and sport not in [s.upper() for s in sports_allowed]:
            continue
        if demons_blocked and bool(p.get("is_demon", False)):
            continue
        out.append(p)
    return out

def score_props_simple(props: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Aggression=1 scoring: prioritize 'goblin' lines, avoid demons, and prefer props
    where recent history (if included in screenshot) often exceeds line (we don't have it yet).
    For now: goblin gets big boost, normal gets baseline.
    """
    scored = []
    for p in props:
        score = 50.0
        if p.get("is_goblin"):
            score += 25.0
        if p.get("is_demon"):
            score -= 30.0
        # Small preference: markets that are usually higher volume/less spiky (customize later)
        market = (p.get("market") or "").lower()
        if any(k in market for k in ["rebounds", "passes attempted", "minutes", "assists"]):
            score += 3.0
        if any(k in market for k in ["3pt", "blocks", "steals"]):
            score -= 2.0

        p2 = dict(p)
        p2["score"] = round(score, 2)
        scored.append(p2)
    return scored

def _pick_default_side(prop: Dict[str, Any]) -> str:
    """
    Without full stats inputs yet, default:
    - goblin props: More
    - otherwise: More for volume markets, Less for very spiky markets
    """
    if prop.get("is_goblin"):
        return "MORE"
    market = (prop.get("market") or "").lower()
    if any(k in market for k in ["3pt", "blocks", "steals", "goals"]):
        return "LESS"
    return "MORE"

def build_primary_slip_aggression_1(scored_props: List[Dict[str, Any]]) -> Dict[str, Any]:
    # Primary = best 3 props by score
    top = sorted(scored_props, key=lambda x: x.get("score", 0), reverse=True)[:3]
    legs = []
    for p in top:
        legs.append({
            "player": p.get("player", ""),
            "sport": p.get("sport", ""),
            "market": p.get("market", ""),
            "line": p.get("alt_line") if p.get("alt_line") is not None else p.get("line"),
            "recommended": _pick_default_side(p),
            "is_goblin": bool(p.get("is_goblin", False)),
            "is_demon": bool(p.get("is_demon", False)),
            "team": p.get("team", ""),
            "opponent": p.get("opponent", ""),
            "game_time": p.get("game_time", ""),
            "score": p.get("score", 0),
        })

    return {
        "slip_type": "3-PICK FLEX",
        "legs": legs,
        "notes": "Aggression=1: avoid demons, prefer goblins/safer lines. Always variance exists.",
    }

def recommend_stake_aggression_1(bankroll: float) -> Tuple[float, float]:
    """
    Aggression=1:
      - Primary stake = 2% bankroll (min $1)
      - Optional secondary = additional 2% bankroll (min $0 if bankroll too small)
      - Keep daily exposure <= 6%
    """
    if bankroll <= 0:
        return (0.0, 0.0)

    primary = max(1.0, round(bankroll * 0.02, 2))
    secondary = max(0.0, round(bankroll * 0.02, 2))

    # If bankroll is tiny, keep it 1 slip only
    if bankroll < 30:
        secondary = 0.0

    # Enforce max exposure 6%
    max_daily = max(2.0, round(bankroll * 0.06, 2))
    if primary + secondary > max_daily:
        secondary = max(0.0, max_daily - primary)

    return (primary, secondary)
