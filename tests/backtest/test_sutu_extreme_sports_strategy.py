from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pandas as pd


STRATEGY_PATH = (
    Path(__file__).resolve().parents[2]
    / "backtest"
    / "freqtrade_single_pair"
    / "user_data"
    / "strategies"
    / "sutu_extreme_sports.py"
)


PARAMS_5M = {
    "fast_length": 1,
    "slow_length": 3,
    "long_length": 10,
    "n_ini": 5,
    "n_add": 10,
    "loss_atr": 6,
    "open_loss_atr": 2,
    "slip": 1,
    "add": 2,
}


def load_strategy_module():
    spec = spec_from_file_location("sutu_extreme_sports", STRATEGY_PATH)
    assert spec is not None and spec.loader is not None, "strategy module spec should load"
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module



def build_sample_dataframe() -> pd.DataFrame:
    rows = []
    price = 1.0
    for i in range(600):
        if i < 220:
            price += 0.0012
        elif i < 320:
            price += 0.004
        elif i < 420:
            price -= 0.0032
        elif i < 520:
            price -= 0.001
        else:
            price += 0.0025
        rows.append(
            {
                "date": pd.Timestamp("2026-01-01") + pd.Timedelta(minutes=5 * i),
                "open": price * 0.997,
                "high": price * 1.006,
                "low": price * 0.994,
                "close": price,
                "volume": 1000 + (i % 20) * 25 + (300 if 230 <= i <= 360 or 430 <= i <= 520 else 0),
            }
        )
    return pd.DataFrame(rows)



def create_strategy(module):
    return module.SutuExtremeSportsStrategy(config={"stake_currency": "USDT", "dry_run": True})



def test_strategy_file_exists_and_exports_freqtrade_class():
    assert STRATEGY_PATH.exists(), f"strategy file missing: {STRATEGY_PATH}"
    module = load_strategy_module()
    assert hasattr(module, "SutuExtremeSportsStrategy")



def test_strategy_matches_reference_5m_defaults():
    module = load_strategy_module()
    strategy = create_strategy(module)

    assert strategy.can_short is True
    assert strategy.timeframe == "5m"
    assert strategy.sutu_params == PARAMS_5M



def test_strategy_populates_reference_indicators_and_signals():
    module = load_strategy_module()
    strategy = create_strategy(module)
    dataframe = build_sample_dataframe()

    indicators = strategy.populate_indicators(dataframe.copy(), {})
    assert {
        "avgvalue1",
        "avgvalue2",
        "avgvalue3",
        "atr_sutu",
        "hh",
        "ll",
        "long_breakout",
        "short_breakout",
        "higher_tf_avgvalue1",
        "higher_tf_avgvalue3",
        "higher_tf_long_filter",
        "higher_tf_short_filter",
    }.issubset(indicators.columns)

    entries = strategy.populate_entry_trend(indicators.copy(), {})
    exits = strategy.populate_exit_trend(indicators.copy(), {})

    assert {"enter_long", "enter_short"}.issubset(entries.columns)
    assert {"exit_long", "exit_short"}.issubset(exits.columns)
    assert entries[["enter_long", "enter_short"]].fillna(0).isin([0, 1]).all().all()
    assert exits[["exit_long", "exit_short"]].fillna(0).isin([0, 1]).all().all()



def test_entry_requires_4h_trend_filter_alignment():
    module = load_strategy_module()
    strategy = create_strategy(module)
    dataframe = build_sample_dataframe()
    indicators = strategy.populate_indicators(dataframe.copy(), {})
    row = indicators.index[-1]

    indicators.loc[row, ["volume_ok", "long_breakout", "long_trend_filter", "higher_tf_long_filter"]] = [True, True, True, False]
    indicators.loc[row, ["short_breakout", "short_trend_filter", "higher_tf_short_filter"]] = [False, False, False]
    filtered_entries = strategy.populate_entry_trend(indicators.copy(), {})
    assert filtered_entries.loc[row, "enter_long"] != 1

    indicators.loc[row, ["long_breakout", "long_trend_filter", "higher_tf_long_filter"]] = [True, True, True]
    aligned_entries = strategy.populate_entry_trend(indicators.copy(), {})
    assert aligned_entries.loc[row, "enter_long"] == 1
