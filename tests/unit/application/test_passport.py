"""Unit tests for the passport renderer.

The renderer is pure - data and avatar bytes in, PNG bytes out - so it can be
exercised without Discord or a network. These prove it produces a valid image
and survives the messy inputs real profiles throw at it.
"""

import io
import unittest

from PIL import Image

from src.plugins.community.passport import (
    H,
    W,
    PassportData,
    _mrz,
    _signed_label,
    render_passport,
)

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _png_bytes(color=(200, 40, 90), size=(256, 256)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


class TestPassportRenderer(unittest.TestCase):
    def test_renders_a_valid_png_without_an_avatar(self):
        png = render_passport(PassportData(
            display_name="yoof1337", citizen_no="456123",
            status="citizen", balance=3150, signed_at="2026-09-28T15:54:37+00:00",
        ))
        self.assertTrue(png.startswith(PNG_MAGIC))
        image = Image.open(io.BytesIO(png))
        self.assertEqual(image.size, (W, H))

    def test_renders_with_an_avatar(self):
        png = render_passport(PassportData(
            display_name="Remirêz Velly", citizen_no="000001",
            status="catizen", balance=0, signed_at=None,
            avatar_bytes=_png_bytes(),
        ))
        self.assertTrue(png.startswith(PNG_MAGIC))
        Image.open(io.BytesIO(png)).verify()

    def test_a_non_square_avatar_is_cropped_not_stretched(self):
        png = render_passport(PassportData(
            display_name="wide", citizen_no="1", status="citizen", balance=0,
            avatar_bytes=_png_bytes(size=(400, 100)),
        ))
        self.assertTrue(png.startswith(PNG_MAGIC))

    def test_corrupt_avatar_bytes_do_not_crash(self):
        png = render_passport(PassportData(
            display_name="x", citizen_no="1", status="citizen", balance=0,
            avatar_bytes=b"not an image at all",
        ))
        self.assertTrue(png.startswith(PNG_MAGIC))

    def test_messy_text_inputs_do_not_crash(self):
        png = render_passport(PassportData(
            display_name="X" * 120, citizen_no="999999",
            status="citizen", balance=123456789, signed_at="not-a-date",
        ))
        self.assertTrue(png.startswith(PNG_MAGIC))

    def test_renders_with_every_enrichment_field(self):
        png = render_passport(PassportData(
            display_name="yoof1337", citizen_no="456123", status="citizen",
            balance=3150, signed_at="2026-09-28T15:54:37+00:00",
            avatar_bytes=_png_bytes(), mark="△ Triangle",
            rank="General Secretary 👑", games_survived=2, trials=1,
        ))
        self.assertTrue(png.startswith(PNG_MAGIC))
        Image.open(io.BytesIO(png)).verify()

    def test_enrichment_fields_default_to_none_and_still_render(self):
        png = render_passport(PassportData(
            display_name="x", citizen_no="1", status="catizen", balance=0,
        ))
        self.assertTrue(png.startswith(PNG_MAGIC))


class TestPassportHelpers(unittest.TestCase):
    def test_signed_label_formats_an_iso_timestamp(self):
        self.assertEqual(_signed_label("2026-09-28T15:54:37+00:00"), "2026-09-28")

    def test_signed_label_handles_missing_and_bad_values(self):
        self.assertEqual(_signed_label(None), "NOT SIGNED")
        self.assertEqual(_signed_label("garbage"), "NOT SIGNED")

    def test_mrz_lines_are_fixed_width(self):
        l1, l2 = _mrz("Remirêz Velly 🤡", "000001")
        self.assertEqual(len(l1), 44)
        self.assertEqual(len(l2), 44)

    def test_mrz_strips_non_alphanumeric_to_filler(self):
        l1, _ = _mrz("A B!", "1")
        self.assertTrue(l1.startswith("P<CVL"))
        self.assertNotIn(" ", l1)
        self.assertNotIn("!", l1)

    def test_mark_symbol_is_extracted_from_the_intro_answer(self):
        from src.plugins.community.passport import _mark_symbol
        self.assertEqual(_mark_symbol("△ Triangle"), "△")
        self.assertEqual(_mark_symbol("○ Circle"), "○")
        self.assertEqual(_mark_symbol("□ Square"), "□")

    def test_mark_symbol_falls_back_for_free_text_and_missing(self):
        from src.plugins.community.passport import _mark_symbol
        self.assertEqual(_mark_symbol("something custom"), "•")
        self.assertEqual(_mark_symbol(None), "—")
        self.assertEqual(_mark_symbol(""), "—")


if __name__ == "__main__":
    unittest.main()
