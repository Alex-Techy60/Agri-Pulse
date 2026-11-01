"""The UI text tables merge over English, so a key that is a string in one language and a function in English crashes the page
(seen 1 Nov 2026: a diagnosis label named `steps` replaced the trace panel's `steps(n)` function in Tamil)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

I18N = Path(__file__).resolve().parents[2] / "frontend" / "src" / "i18n.js"

JS = r"""
const fs = require("fs");
const src = fs.readFileSync(process.argv[1], "utf8").replace(/^export const uiText.*$/m, "").replace(/export /g, "");
const { UI_TEXT, CORE } = new Function(src + "\nreturn { UI_TEXT, CORE };")();
const en = UI_TEXT.en, bad = [];
for (const [l, o] of [...Object.entries(UI_TEXT), ...Object.entries(CORE)]) for (const k of Object.keys(o)) if (k in en && typeof en[k] !== typeof o[k]) bad.push(l + "." + k);
console.log(JSON.stringify({ bad, languages: [...new Set([...Object.keys(UI_TEXT), ...Object.keys(CORE)])].sort() }));
"""


@pytest.mark.skipif(not shutil.which("node"), reason="node is not installed")
def test_translated_keys_keep_the_type_of_the_english_key():
    out = json.loads(subprocess.run(["node", "-e", JS, str(I18N)], capture_output=True, text=True, check=True, timeout=30).stdout)
    assert out["bad"] == []
    from app.domain.farm import DOMAIN
    assert set(out["languages"]) == set(DOMAIN.languages)  # every language the API answers in has UI text
