import os


def get_risk_thresholds() -> tuple[int, int, int]:
    """Read inclusive upper bounds for Low, Medium, and High severity."""
    try:
        low_max = int(os.getenv("RISK_LOW_MAX", "4"))
        medium_max = int(os.getenv("RISK_MEDIUM_MAX", "9"))
        high_max = int(os.getenv("RISK_HIGH_MAX", "16"))
    except ValueError as error:
        raise RuntimeError("Risk score thresholds must be whole numbers.") from error

    if not 1 <= low_max < medium_max < high_max <= 24:
        raise RuntimeError("Risk score thresholds must be increasing values within the valid range.")

    return low_max, medium_max, high_max


def calculate_risk_assessment(likelihood: int, impact: int) -> dict[str, int | str]:
    """Calculate the application's numeric score and severity band."""
    score = likelihood * impact
    low_max, medium_max, high_max = get_risk_thresholds()

    if score <= low_max:
        severity = "Low"
    elif score <= medium_max:
        severity = "Medium"
    elif score <= high_max:
        severity = "High"
    else:
        severity = "Critical"

    return {
        "likelihood": likelihood,
        "impact": impact,
        "risk_score": score,
        "severity": severity,
    }
