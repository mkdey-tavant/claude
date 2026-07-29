"""Tests for ticker normalisation and candidate ordering."""

from __future__ import annotations

import pytest

from stock_analysis_mcp.data import tickers


def test_normalise_strips_suffix_and_aliases():
    assert tickers.normalise_base("reliance") == "RELIANCE"
    assert tickers.normalise_base("RELIANCE.NS") == "RELIANCE"
    assert tickers.normalise_base("infosys") == "INFY"
    assert tickers.normalise_base("state bank") == "SBIN"


def test_candidates_default_nse_first():
    cands = tickers.candidate_tickers("TCS", preferred_market="NSE")
    assert cands[0] == "TCS.NS"
    assert "TCS.BO" in cands


def test_candidates_bse_first_when_requested():
    cands = tickers.candidate_tickers("TCS", preferred_market="BSE")
    assert cands[0] == "TCS.BO"
    assert "TCS.NS" in cands


def test_explicit_suffix_takes_priority():
    cands = tickers.candidate_tickers("INFY.BO", preferred_market="NSE")
    assert cands[0] == "INFY.BO"


def test_empty_symbol_raises():
    with pytest.raises(ValueError):
        tickers.candidate_tickers("   ")


def test_no_duplicate_candidates():
    cands = tickers.candidate_tickers("WIPRO.NS", preferred_market="NSE")
    assert len(cands) == len(set(cands))
