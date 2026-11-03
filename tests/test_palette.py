import re

import pytest

from mapkit import palette as P

# These tests work whatever your six colours are, so they also pass in copies
# of the template that picked different ones.


def test_six_categorical_colours_in_a_fixed_order():
    assert len(P.CATEGORICAL) == len(P.CATEGORICAL_NAMES) == 6
    assert len(set(P.CATEGORICAL)) == 6
    assert all(re.fullmatch(r"#[0-9a-fA-F]{6}", c) for c in P.CATEGORICAL)
    assert P.categorical(3) == P.CATEGORICAL[:3]
    assert P.categorical(6) == P.CATEGORICAL


def test_categorical_refuses_more_than_six():
    with pytest.raises(ValueError):
        P.categorical(7)


def test_highlight_and_alert_are_two_of_the_six():
    assert P.HIGHLIGHT in P.CATEGORICAL
    assert P.ALERT in P.CATEGORICAL
    assert P.HIGHLIGHT != P.ALERT


def test_ramps_keep_their_end_colours():
    for name, stops in P.RAMPS.items():
        assert len(stops) == 7
        five = P.ramp(name, 5)
        assert len(five) == 5
        assert five[0] == stops[0] and five[-1] == stops[-1]


def test_diverging_has_neutral_middle():
    assert P.diverging(7)[3] == P.MIDDLE
    assert P.diverging(5)[2] == P.MIDDLE


def test_text_colour_picks_the_readable_one():
    assert P.text_on("#ffffff") == P.INK
    assert P.text_on("#ffd400") == P.INK      # a light yellow
    assert P.text_on("#000000") == P.CREAM
    assert P.text_on("#5e3aa8") == P.CREAM    # a dark purple


def test_css_variables_include_palette():
    css = P.css_variables()
    for name, hex_ in zip(P.CATEGORICAL_NAMES, P.CATEGORICAL):
        assert f"--{name}: {hex_};" in css
    assert f"--highlight: {P.HIGHLIGHT};" in css
    assert f"--on-highlight: {P.text_on(P.HIGHLIGHT)};" in css
    assert f"--alert: {P.ALERT};" in css
    assert f"--sunrise-7: {P.RAMPS['sunrise'][6]};" in css
