"""Lightweight engine tests: template constants match the original scripts,
layout builds without crashing, motion is sane."""
from shotcreator_engine import DEFAULT_TEMPLATE, layout, motion
from shotcreator_engine.template import Template


def test_default_template_matches_reference():
    t = DEFAULT_TEMPLATE
    assert (t.width, t.height, t.fps) == (1080, 1920, 30)
    assert t.bg_color == (11, 21, 38)
    assert t.text_color == (255, 255, 255)
    assert (t.card_x, t.card_y, t.card_w, t.card_h) == (48, 400, 984, 1120)
    assert t.card_radius == 30
    assert (t.top_y, t.top_start_size) == (96, 88)
    assert (t.bot_y, t.bot_start_size) == (1568, 62)
    assert t.dwell_top == 2.0 and t.dwell_bot == 2.0
    assert t.pan_frac == 0.75
    assert t.crf == 20 and t.preset == "medium"


def test_background_builds():
    t = Template()
    bg = layout.make_background(t, ["OBAT LELAH PALING AJAIB"], ["PELUK ANAKMU"])
    assert bg.size == (t.width, t.height)
    assert bg.mode == "RGB"


def test_motion_offsets_monotonic_and_sized():
    offs = list(motion.iter_offsets(2.0, 5.0, 2.0, 300, 30))
    assert len(offs) == 60 + 150 + 60
    assert offs[0] == 0
    assert offs[-1] == 300
    assert all(b >= a for a, b in zip(offs, offs[1:]))


def test_ease_in_out_endpoints():
    assert motion.ease_in_out(0.0) == 0.0
    assert motion.ease_in_out(1.0) == 1.0
    assert 0.0 < motion.ease_in_out(0.5) < 1.0
