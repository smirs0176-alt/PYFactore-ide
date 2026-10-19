import pytest

from pyfactor.core.web import pyg

pytestmark = pytest.mark.skipif(not pyg.available(), reason="нет Pygments")


def _tokens(code, path):
    return [(code[s:e], t) for s, e, t in pyg.spans_for_path(code, path)]


def test_json_tokens_and_offsets_match_source():
    code = '{\n  "name": "PyFactor", "n": 42, "ok": true\n}\n'
    toks = _tokens(code, "a.json")
    assert ('"PyFactor"', "string") in toks and ("42", "number") in toks
    for s, e, _t in pyg.spans_for_path(code, "a.json"):
        assert 0 <= s < e <= len(code)


def test_markdown_yaml_toml_sh_have_spans():
    assert any(t == "cls" for _v, t in _tokens("# Title\n\ntext\n", "r.md"))
    assert any(t == "comment" for _v, t in _tokens("a: 1  # c\n", "c.yml"))
    assert any(t == "comment" for _v, t in _tokens("[x]\na = 1 # c\n", "p.toml"))
    assert any(t == "kw" for _v, t in _tokens("if true; then echo hi; fi\n", "s.sh"))


def test_unknown_ext_empty_and_oversized_skipped():
    assert pyg.spans_for_path("x", "a.unknownext") == []
    assert pyg.spans_for_path("x", None) == []
    assert pyg.spans_for_path("{}" + " " * pyg.MAX_CHARS, "a.json") == []


def test_works_without_pygments(monkeypatch):
    monkeypatch.setattr(pyg, "available", lambda: False)
    assert pyg.spans_for_path('{"a": 1}', "a.json") == []


def test_unicode_offsets():
    code = '{"имя": "мир"}'
    assert ('"мир"', "string") in _tokens(code, "u.json")
