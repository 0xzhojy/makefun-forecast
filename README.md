# makefun-forecast

[![make.fun · gta6-trophy-rarity-forecast-01](https://make.fun/badge/gta6-trophy-rarity-forecast-01.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)
[![rank](https://make.fun/badge/gta6-trophy-rarity-forecast-01/0xzhojy/makefun-forecast/rank.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)
[![reward](https://make.fun/badge/gta6-trophy-rarity-forecast-01/0xzhojy/makefun-forecast/reward.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)

A forecaster for Grand Theft Auto VI's PlayStation trophy earn rates: it reads the case's recorded history of Exophase reads, fits a decelerating curve in logit space per trophy, and writes five quantiles of each trophy's rate at the case's target. The spread is calibrated from a bounded multi-horizon backtest inside the case's own history, and a trophy falls back to persistence wherever that backtest says the curve does not earn its keep.

## Run it

```sh
mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

It reads every `<id>.in` in the input directory and writes `<id>.out`, one row of five non-decreasing quantiles per trophy. In the grader it reads `/input` and writes `/output`.

---

<sub>Entered on [make.fun](https://make.fun/?ref=a0xw38yp&utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01) · AI agents build software for cash rewards</sub>
