"""Offline trophy-rate forecasts; Python 3.13 standard library only."""
import json
from bisect import bisect_left
import math
import os
from datetime import datetime
from pathlib import Path

Z = (-1.645, -0.674, 0.0, 0.674, 1.645)
LEVELS = (0.05, 0.25, 0.5, 0.75, 0.95)
TAUS = (6, 12, 24, 48, 96, 192, 384)


def logit(rate):
    p = min(99.5, max(0.5, rate)) / 100.0
    return math.log(p / (1.0 - p))


def logistic(x):
    x = max(-35.0, min(35.0, x))
    return 100.0 / (1.0 + math.exp(-x))


def hours(s):
    return datetime.fromisoformat(s.replace('Z', '+00:00')).timestamp() / 3600.0


def regression(points, tau):
    """Fit y = a - b exp(-age/tau), with nonnegative growth."""
    origin = points[0][0]
    xs = [-math.exp(-(t - origin) / tau) for t, _ in points]
    ys = [y for _, y in points]
    xm, ym = sum(xs) / len(xs), sum(ys) / len(ys)
    var = sum((x - xm) ** 2 for x in xs)
    b = max(0.0, sum((x - xm) * (y - ym) for x, y in zip(xs, ys)) / var) if var > 1e-16 else 0.0
    a = ym - b * xm
    error = sum((y - (a + b * x)) ** 2 for x, y in zip(xs, ys))
    return a, b, error


def fit_curves(series, trophies):
    """Fit shared shape and tier/points growth pools for a history prefix."""
    eligible = [[(t, y) for t, y, _ in s] for s in series
                if len(s) >= 4 and s[-1][0] - s[0][0] >= 1.0
                and max(y for _, y, _ in s) - min(y for _, y, _ in s) > 0.01]
    tau = min(TAUS, key=lambda v: sum(regression(s, v)[2] for s in eligible)) if eligible else 48
    fits, pools = [], {}
    for trophy, s in zip(trophies, series):
        fit = None
        if len(s) >= 4 and s[-1][0] - s[0][0] >= 1.0:
            pts = [(t, y) for t, y, _ in s]
            a, b, err = regression(pts, tau)
            signal = max(y for _, y in pts) - min(y for _, y in pts)
            if b > 0 and signal > 0.01:
                rate = b * math.exp(-(s[-1][0] - s[0][0]) / tau) / tau
                fit = (rate, err, signal)
                pools.setdefault((trophy.get('tier'), trophy.get('points')), []).append(rate)
        fits.append(fit)
    rates = []
    for trophy, s, fit in zip(trophies, series, fits):
        group = pools.get((trophy.get('tier'), trophy.get('points')), [])
        pool_rate = sum(group) / len(group) if group else 0.0
        if fit:
            rate, err, signal = fit
            confidence = signal * signal / (signal * signal + 4.0 * err / len(s) + 0.0025)
            rates.append(confidence * rate + (1.0 - confidence) * pool_rate)
        else:
            rates.append(0.15 * pool_rate if len(s) < 4 else 0.0)
    return tau, rates


def curve_value(y, rate, tau, horizon):
    return min(logit(99.5), y + min(3.0, rate * tau * (1.0 - math.exp(-max(0.0, horizon) / tau))))


def forecast_case(case, name=None, diagnostics=None):
    history, trophies = case['history'], case['trophies']
    if not history or tuple(case['levels']) != LEVELS:
        raise ValueError('case requires history and the five standard levels')
    times = [hours(h['at']) for h in history]
    target = hours(case['target'])
    n = len(trophies)
    series = [[] for _ in trophies]
    # Reserve the last three valid cuts, and spread the others evenly.
    last_cut = len(history) - 2
    if last_cut <= 24:
        cuts = set(range(1, last_cut + 1))
    else:
        cuts = {1 + (last_cut - 1) * i // 20 for i in range(21)}
        cuts.update((last_cut - 2, last_cut - 1, last_cut))
    errors = [[] for _ in trophies]
    for k in range(len(history)):
        if k in cuts:
            tau, rates = fit_curves(series, trophies)
            # Binary-search the closest later read to each requested horizon.
            candidates = {len(history) - 1}
            for h in (1.0, 6.0, 24.0):
                pos = bisect_left(times, times[k] + h, k + 1)
                choices = [j for j in (pos - 1, pos) if k < j < len(history)]
                if choices:
                    candidates.add(min(choices, key=lambda j: (abs(times[j] - times[k] - h), j)))
            for j in sorted(candidates):
                horizon = times[j] - times[k]
                if horizon <= 0:
                    continue
                observed = history[j]['rates']
                for i, s in enumerate(series):
                    if not s or i >= len(observed) or observed[i] is None:
                        continue
                    y = s[-1][1]
                    actual = logit(observed[i])
                    # Predictions are made at the cut time, using only the
                    # last preceding observation and its true age.
                    elapsed = times[j] - s[-1][0]
                    curve = curve_value(y, rates[i], tau, elapsed)
                    errors[i].append((horizon, actual - curve, actual - y))
        for i, rate in enumerate(history[k]['rates'][:n]):
            if rate is not None:
                series[i].append((times[k], logit(rate), float(rate)))

    tau, rates = fit_curves(series, trophies)
    selected = []
    for records in errors:
        if records:
            # Use the longest quartile of available horizons, with ties.
            hs = sorted(r[0] for r in records)
            threshold = hs[(3 * len(hs)) // 4]
            long = [r for r in records if r[0] >= threshold]
            selected.append(sum(abs(r[1]) for r in long) < sum(abs(r[2]) for r in long))
        else:
            selected.append(False)
    if diagnostics is not None:
        diagnostics.update(curve=sum(selected), persistence=n-sum(selected))

    tier_errors = {}
    for trophy, records, use_curve in zip(trophies, errors, selected):
        tier_errors.setdefault(trophy.get('tier'), []).extend(
            (h, ec if use_curve else ep) for h, ec, ep in records)

    def spread(records, horizon):
        if not records:
            return None
        # Use the nearest horizons, including ties; sparse samples use all.
        if len(records) < 3:
            values = [abs(e) for _, e in records]
        else:
            ordered = sorted((abs(h - horizon), abs(e)) for h, e in records)
            limit = ordered[min(len(ordered) - 1, max(2, int(math.sqrt(len(ordered))) - 1))][0]
            values = [e for distance, e in ordered if distance <= limit]
        return 1.25 * sum(values) / len(values)

    rows = []
    for i, (trophy, s, use_curve) in enumerate(zip(trophies, series, selected)):
        if not s:
            rows.append({'id': trophy['id'], 'q': [0.0] * 5})
            continue
        last = s[-1][2]
        if last >= 99.9:
            rows.append({'id': trophy['id'], 'q': [100.0] * 5})
            continue
        horizon = max(0.0, target - s[-1][0])
        y = s[-1][1]
        center = curve_value(y, rates[i], tau, horizon) if use_curve else y
        own = [(h, ec if use_curve else ep) for h, ec, ep in errors[i]]
        sigma = spread(own, horizon)
        if sigma is None:
            sigma = spread(tier_errors.get(trophy.get('tier'), []), horizon)
        sigma = max(0.05, sigma if sigma is not None else 0.05)
        if last <= 0.0 and not use_curve:
            # Preserve a zero median while allowing a meaningful upper band.
            q = [0.0, 0.0, 0.0, logistic(center + Z[3] * sigma), logistic(center + Z[4] * sigma)]
        else:
            q = [logistic(center + z * sigma) for z in Z]
        rows.append({'id': trophy['id'], 'q': q})
    return {'trophies': rows}


def main():
    inputs = Path(os.environ.get('MAKEFUN_INPUT_DIR', '/input'))
    outputs = Path(os.environ.get('MAKEFUN_OUTPUT_DIR', '/output'))
    outputs.mkdir(parents=True, exist_ok=True)
    for path in sorted(inputs.glob('*.in')):
        with path.open(encoding='utf-8') as stream:
            case = json.load(stream)
        result = forecast_case(case, path.name)
        with (outputs / (path.stem + '.out')).open('w', encoding='utf-8') as stream:
            json.dump(result, stream, separators=(',', ':'), allow_nan=False)
            stream.write('\n')


if __name__ == '__main__':
    main()
