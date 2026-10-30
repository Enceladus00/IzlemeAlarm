import math
from datetime import datetime, time, timedelta
from statistics import median

from backend.detection.metadata import ParameterSpec


def calendar_window_start(as_of: datetime, days: int) -> datetime:
    return datetime.combine(
        as_of.date() - timedelta(days=days - 1),
        time.min,
    )


def prior_day_start(as_of: datetime, days: int) -> datetime:
    return datetime.combine(as_of.date() - timedelta(days=days), time.min)


def median_and_mad(values: list[float]) -> tuple[float, float]:
    center = median(values)
    return center, median([abs(value - center) for value in values])


def log_sum_exp(log_values: list[float]) -> float:
    if not log_values:
        return float("-inf")
    maximum = max(log_values)
    if maximum == float("-inf"):
        return maximum
    return maximum + math.log(sum(math.exp(value - maximum) for value in log_values))


def distribution_survival(
    n: int, mean: float, variance: float
) -> float:
    if n <= 0:
        return 1.0
    if mean <= 0:
        mean = 0.5

    if variance <= mean:
        log_mass = lambda k: -mean + k * math.log(mean) - math.lgamma(k + 1)
        ratio = lambda k: mean / (k + 1)
    else:
        dispersion = mean * mean / (variance - mean)
        probability = dispersion / (dispersion + mean)
        log_mass = lambda k: (
            math.lgamma(k + dispersion)
            - math.lgamma(dispersion)
            - math.lgamma(k + 1)
            + dispersion * math.log(probability)
            + k * math.log1p(-probability)
        )
        ratio = lambda k: ((k + dispersion) / (k + 1)) * (1 - probability)

    upper = max(n + 100, int(mean + 20 * math.sqrt(max(variance, mean)) + 100))
    upper = min(upper, n + 100000)
    logs = []
    current_log = log_mass(n)
    for k in range(n, upper):
        logs.append(current_log)
        current_log += math.log(max(ratio(k), 1e-300))
        if k > mean and current_log < -745:
            break
    return max(1e-300, min(1.0, math.exp(log_sum_exp(logs))))
