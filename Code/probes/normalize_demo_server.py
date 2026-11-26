"""Text-only demo server for the TTS text normalizer."""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from batch.text_normalize import SUPPORTED_LANGS, normalize

LANGS = [
    ("en", "English"), ("hi", "Hindi"), ("mr", "Marathi"), ("ta", "Tamil"),
    ("te", "Telugu"), ("kn", "Kannada"), ("ml", "Malayalam"),
]

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Arsenal Text Normalizer</title>
<style>
  :root{--bg:#0b0d10;--card:#14181d;--line:#252b33;--fg:#e8edf3;--mut:#8b96a5;--acc:#5eead4}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
  .wrap{max-width:1000px;margin:0 auto;padding:32px 20px 60px}
  h1{font-size:22px;margin:0 0 4px}
  p.sub{margin:0 0 24px;color:var(--mut);font-size:13px}
  .card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px}
  .row{display:flex;gap:12px;flex-wrap:wrap;align-items:center;margin-bottom:14px}
  label{color:var(--mut);font-size:12px;text-transform:uppercase;letter-spacing:.08em}
  select,textarea,button{font:inherit;color:var(--fg);background:#0f1318;border:1px solid var(--line);border-radius:10px}
  select{padding:8px 10px}
  textarea{width:100%;min-height:130px;padding:14px;resize:vertical;outline:none}
  textarea:focus{border-color:var(--acc)}
  button{padding:9px 16px;cursor:pointer;background:#1b222a}
  button:hover{border-color:var(--acc)}
  button.primary{background:var(--acc);color:#06201c;border-color:var(--acc);font-weight:600}
  .examples{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 16px}
  .examples button{font-size:12px;padding:6px 10px;background:transparent;color:var(--mut)}
  .examples button:hover{color:var(--fg)}
  .out{white-space:pre-wrap;word-break:break-word;background:#0f1318;border:1px solid var(--line);border-radius:10px;padding:14px;min-height:80px}
  .meta{display:flex;gap:16px;color:var(--mut);font-size:12px;margin-top:10px}
  .err{color:#fda4af}
  .grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}
  @media(max-width:760px){.grid{grid-template-columns:1fr}}
  h2{font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:var(--mut);margin:0 0 8px}
</style>
</head>
<body>
<div class="wrap">
  <h1>Arsenal Text Normalizer</h1>
  <p class="sub">Text only. No audio. This shows exactly what the TTS engine receives.</p>
  <div class="card">
    <div class="row">
      <label for="lang">Language</label>
      <select id="lang">__OPTIONS__</select>
      <span style="flex:1"></span>
      <button id="run" class="primary">Normalize</button>
    </div>
    <div class="examples" id="examples"></div>
    <div class="grid">
      <div>
        <h2>Input</h2>
        <textarea id="input" placeholder="Type text with numbers, currency, dates, times, phone numbers...">Rs. 1,502.50 paid on 12/03/2025 at 5:00 pm. Call +91 98765 43210.</textarea>
      </div>
      <div>
        <h2>Spoken output</h2>
        <div class="out" id="output"></div>
        <div class="meta"><span id="chars"></span><span id="ms"></span></div>
      </div>
    </div>
  </div>
</div>
<script>
const UNIVERSAL = [
  "Rs. 1,502.50 paid on 12/03/2025.",
  "Call +91 98765 43210, OTP is 482916.",
  "$5 Million, 50% off, 3.14.",
  "Items 1,2,3. Pay 500, then 600.",
  "Dr. Rao will call at 5:00 pm.",
  "Flat A-203, GST123, 2BHK, 3G.",
  "It is -5°C. Room 5-6.",
  "Visit www.example.com/pay or mail test@gmail.com.",
  "₹500-₹800, 9:00 am-5:00 pm.",
  "1/2, 24/7, 3:1.",
  "Use UPI or ATM. ₹2 Lakh.",
  "Score is 3.5. 1st, 2nd, 21st.",
];
const BY_LANG = {
  en: [
    "Your balance is ₹1,502.50.",
    "Pay ₹1,502, thanks.",
    "at 9:05",
    "10-12 days",
  ],
  hi: [
    "मेरा balance ₹1,502 है",
    "मैंने 500 दिए।",
    "आज 24 तारीख है",
    "मेरा नंबर 98765 43210 है",
    "OTP 482916 है",
    "शाम 5:00 बजे मिलेंगे",
    "9:05 पर आना",
    "₹5 लाख और ₹2.5 करोड़",
    "3.5, 50%, 1,2,3",
    "Mr. Sharma ने ₹500 दिए",
    "डॉक्टर को 1,50,000 रुपये",
    "-5°C ठंड है",
  ],
  mr: [
    "मी 500 दिले.",
    "मेरा नंबर 98765 43210 आहे",
    "₹1,502.50",
    "5:00 वाजता भेटू",
    "₹5 लाख",
    "3.5, 50%",
  ],
  ta: [
    "நான் 500 கொடுத்தேன்.",
    "ரூ. 1,502.50",
    "98765 43210",
    "நேரம் 5:00",
    "₹5 லட்சம்",
    "3.5, 50%",
  ],
  te: [
    "నేను 500 ఇచ్చాను.",
    "₹1,502.50",
    "98765 43210",
    "సమయం 5:00",
    "₹5 లక్ష",
    "3.5, 50%",
  ],
  kn: [
    "ನಾನು 500 ಕೊಟ್ಟೆ.",
    "₹1,502.50",
    "98765 43210",
    "ಸಮಯ 5:00",
    "₹5 ಲಕ್ಷ",
    "3.5, 50%",
  ],
  ml: [
    "ഞാൻ 500 കൊടുത്തു.",
    "₹1,502.50",
    "98765 43210",
    "സമയം 5:00",
    "₹5 ലക്ഷം",
    "3.5, 50%",
  ],
};
const input = document.getElementById('input');
const out = document.getElementById('output');
const lang = document.getElementById('lang');
const chars = document.getElementById('chars');
const ms = document.getElementById('ms');
const ex = document.getElementById('examples');
function renderExamples() {
  ex.innerHTML = '';
  const samples = UNIVERSAL.concat(BY_LANG[lang.value] || []);
  for (const s of samples) {
    const b = document.createElement('button');
    b.textContent = s.length > 40 ? s.slice(0, 38) + '…' : s;
    b.title = s;
    b.onclick = () => { input.value = s; run(); };
    ex.appendChild(b);
  }
}
function endpoint() {
  let base = location.pathname;
  if (!base.endsWith('/')) base += '/';
  return base + 'normalize';
}
async function run() {
  out.className = 'out';
  out.textContent = '...';
  const t0 = performance.now();
  try {
    const r = await fetch(endpoint(), {
      method: 'POST',
      headers: {'content-type': 'application/json'},
      body: JSON.stringify({text: input.value, lang: lang.value}),
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || 'request failed');
    out.textContent = data.output || '(empty)';
    chars.textContent = data.output.length + ' chars';
    ms.textContent = Math.round(performance.now() - t0) + ' ms';
  } catch (e) {
    out.className = 'out err';
    out.textContent = String(e.message || e);
    chars.textContent = '';
    ms.textContent = '';
  }
}
lang.addEventListener('change', () => { renderExamples(); run(); });
renderExamples();
document.getElementById('run').onclick = run;
input.addEventListener('keydown', e => { if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') run(); });
run();
</script>
</body>
</html>
""".replace("__OPTIONS__", "".join(f'<option value="{code}">{name}</option>' for code, name in LANGS))


class Handler(BaseHTTPRequestHandler):
    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            body = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("content-type", "text/html; charset=utf-8")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/favicon.ico":
            self.send_response(204)
            self.send_header("content-length", "0")
            self.end_headers()
        elif self.path == "/health":
            self._json(200, {"ok": True, "languages": list(SUPPORTED_LANGS)})
        else:
            self._json(404, {"detail": "not found"})

    def do_POST(self) -> None:
        if self.path != "/normalize":
            self._json(404, {"detail": "not found"})
            return
        try:
            length = int(self.headers.get("content-length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            text = str(payload.get("text") or "")
            lang = str(payload.get("lang") or "en")
            if lang not in SUPPORTED_LANGS:
                self._json(400, {"detail": "unsupported language"})
                return
            self._json(200, {"output": normalize(text, lang), "lang": lang})
        except Exception as exc:
            self._json(500, {"detail": str(exc)})

    def log_message(self, fmt: str, *args) -> None:
        print(f"{self.address_string()} {fmt % args}", flush=True)


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8090
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"normalize demo on http://0.0.0.0:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
