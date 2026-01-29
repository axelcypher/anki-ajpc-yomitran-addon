import re

try:
    from pykakasi import kakasi as _kakasi  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    _kakasi = None


def _simple_hepburn(text: str) -> str:
    if not text:
        return ""

    def to_hiragana(s: str) -> str:
        out = []
        for ch in s:
            code = ord(ch)
            if 0x30A1 <= code <= 0x30F6:
                out.append(chr(code - 0x60))
            else:
                out.append(ch)
        return "".join(out)

    text = to_hiragana(text)

    digraphs = {
        "??": "kya", "??": "kyu", "??": "kyo",
        "??": "sha", "??": "shu", "??": "sho",
        "??": "cha", "??": "chu", "??": "cho",
        "??": "nya", "??": "nyu", "??": "nyo",
        "??": "hya", "??": "hyu", "??": "hyo",
        "??": "mya", "??": "myu", "??": "myo",
        "??": "rya", "??": "ryu", "??": "ryo",
        "??": "gya", "??": "gyu", "??": "gyo",
        "??": "ja", "??": "ju", "??": "jo",
        "??": "bya", "??": "byu", "??": "byo",
        "??": "pya", "??": "pyu", "??": "pyo",
        "??": "ti", "??": "di",
        "??": "wi", "??": "we", "??": "wo",
        "??": "fa", "??": "fi", "??": "fe", "??": "fo", "??": "fyu",
        "??": "va", "??": "vi", "??": "ve", "??": "vo", "??": "vyu",
    }

    singles = {
        "?": "a", "?": "i", "?": "u", "?": "e", "?": "o",
        "?": "ka", "?": "ki", "?": "ku", "?": "ke", "?": "ko",
        "?": "sa", "?": "shi", "?": "su", "?": "se", "?": "so",
        "?": "ta", "?": "chi", "?": "tsu", "?": "te", "?": "to",
        "?": "na", "?": "ni", "?": "nu", "?": "ne", "?": "no",
        "?": "ha", "?": "hi", "?": "fu", "?": "he", "?": "ho",
        "?": "ma", "?": "mi", "?": "mu", "?": "me", "?": "mo",
        "?": "ya", "?": "yu", "?": "yo",
        "?": "ra", "?": "ri", "?": "ru", "?": "re", "?": "ro",
        "?": "wa", "?": "o",
        "?": "n",
        "?": "ga", "?": "gi", "?": "gu", "?": "ge", "?": "go",
        "?": "za", "?": "ji", "?": "zu", "?": "ze", "?": "zo",
        "?": "da", "?": "ji", "?": "zu", "?": "de", "?": "do",
        "?": "ba", "?": "bi", "?": "bu", "?": "be", "?": "bo",
        "?": "pa", "?": "pi", "?": "pu", "?": "pe", "?": "po",
        "?": "vu",
        "?": "a", "?": "i", "?": "u", "?": "e", "?": "o",
        "?": "ya", "?": "yu", "?": "yo",
    }

    res = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "?":
            if i + 1 < len(text):
                nxt = text[i + 1 : i + 3]
                nxt2 = text[i + 1 : i + 2]
                roma = digraphs.get(nxt) or singles.get(nxt2, "")
                if roma.startswith("ch"):
                    res.append("t")
                elif roma:
                    res.append(roma[0])
            i += 1
            continue
        if ch == "?":
            if res:
                m = re.search(r"[aeiou]", res[-1][::-1])
                if m:
                    res.append(m.group(0))
            i += 1
            continue

        pair = text[i : i + 2]
        if pair in digraphs:
            res.append(digraphs[pair])
            i += 2
            continue
        if ch in singles:
            res.append(singles[ch])
        else:
            res.append(ch)
        i += 1

    out = "".join(res)
    # Handle n before vowels or y
    out = re.sub(r"n(?=[aeiouy])", "n'", out)
    return out


def to_hepburn(text: str) -> str:
    if not text:
        return ""
    if _kakasi is None:
        return _simple_hepburn(text)

    try:
        conv = _kakasi()
        conv.setMode("H", "a")
        conv.setMode("K", "a")
        conv.setMode("J", "a")
        conv.setMode("r", "Hepburn")
        converter = conv.getConverter()
        return converter.do(text)
    except Exception:
        return _simple_hepburn(text)
