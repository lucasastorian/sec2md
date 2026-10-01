"""Tests for utility functions (utils.py)."""

from unittest.mock import patch

from sec2md.utils import count_tokens, flatten_note, is_edgar_url, is_url


class TestCountTokens:
    def test_counts_tokens(self):
        assert count_tokens("hello world") == 2

    def test_chars_over_four_when_tiktoken_cannot_load(self):
        """Offline, tiktoken cannot fetch its BPE file on first use: count, don't fail."""
        count_tokens.cache_clear()
        try:
            with patch("sec2md.utils._encoding", return_value=None):
                assert count_tokens("forty characters of text, give or take!!") == 10
                assert count_tokens("hi") == 1
        finally:
            count_tokens.cache_clear()

    def test_chars_over_four_when_encoding_raises(self):
        """tiktoken refuses text holding a special token."""
        text = "<|endoftext|> appears in a filing"
        assert count_tokens(text) == len(text) // 4


class TestIsUrl:
    def test_valid_urls(self):
        assert is_url("http://example.com") is True
        assert is_url("https://example.com") is True

    def test_non_urls(self):
        assert is_url("just a string") is False
        assert is_url("<html><body>content</body></html>") is False
        assert is_url("") is False
        assert is_url("ftp://files.example.com") is False


class TestIsEdgarUrl:
    def test_sec_gov_url(self):
        assert is_edgar_url("https://www.sec.gov/Archives/edgar/data/123/filing.htm") is True

    def test_non_edgar_url(self):
        assert is_edgar_url("https://example.com") is False

    def test_case_insensitive(self):
        assert is_edgar_url("https://WWW.SEC.GOV/filing") is True


class TestFlattenNote:
    def test_basic_flatten(self):
        html = """<html><body>
        <table><tr><td><p>Note content here</p></td></tr></table>
        </body></html>"""
        result = flatten_note(html)
        assert result is not None
        assert "Note content" in result

    def test_no_table_returns_none(self):
        assert flatten_note("<html><body><p>No table here</p></body></html>") is None

    def test_multiple_rows_flattened(self):
        html = """<html><body>
        <table>
            <tr><td>Row 1</td></tr>
            <tr><td>Row 2</td></tr>
        </table>
        </body></html>"""
        result = flatten_note(html)
        assert "Row 1" in result
        assert "Row 2" in result
