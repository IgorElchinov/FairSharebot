from __future__ import annotations

import json


def render_link_page(*, token: str) -> str:
    """Self-contained HTML+JS page - no CDN scripts, so this never depends on
    a third-party host being reachable or trustworthy. Talks to the browser
    wallet directly via window.ethereum's JSON-RPC methods (no ethers.js
    needed) and to this same app's /api/link/* endpoints for everything
    chain-specific (permit typed data, verification)."""
    token_json = json.dumps(token)
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Link your wallet - FairSharebot</title>
<style>
  body {{ font-family: -apple-system, system-ui, sans-serif; max-width: 480px; margin: 40px auto; padding: 0 16px; color: #1a1a1a; }}
  button {{ font-size: 16px; padding: 10px 16px; margin: 8px 0; cursor: pointer; }}
  #status {{ margin-top: 16px; white-space: pre-wrap; }}
  .error {{ color: #b00020; }}
  .success {{ color: #146c2e; }}
  code {{ word-break: break-all; }}
</style>
</head>
<body>
<h2>Link your wallet to FairSharebot</h2>
<p>This grants FairSharebot's Settlement contract a standing allowance so
token-mode trips can settle automatically. You'll sign two messages in your
wallet - no gas required.</p>
<button id="connectBtn">Connect Wallet</button>
<div id="status"></div>

<script>
const TOKEN = {token_json};
const statusEl = document.getElementById("status");

function setStatus(text, cls) {{
  statusEl.textContent = text;
  statusEl.className = cls || "";
}}

function textToHex(text) {{
  const bytes = new TextEncoder().encode(text);
  return "0x" + Array.from(bytes).map(b => b.toString(16).padStart(2, "0")).join("");
}}

async function run() {{
  if (!window.ethereum) {{
    setStatus("No wallet extension found. Open this page in a browser with MetaMask (or similar) installed.", "error");
    return;
  }}

  const challengeResp = await fetch(`/api/link/${{TOKEN}}`);
  if (!challengeResp.ok) {{
    setStatus("This link is invalid, expired, or already used. Run /linkwallet again for a fresh one.", "error");
    return;
  }}
  const challenge = await challengeResp.json();

  setStatus("Connecting wallet...");
  const accounts = await window.ethereum.request({{ method: "eth_requestAccounts" }});
  const address = accounts[0];

  setStatus(`Connected: ${{address}}\\n\\nSigning ownership proof...`);
  const ownershipSig = await window.ethereum.request({{
    method: "personal_sign",
    params: [textToHex(challenge.nonce_message), address],
  }});

  setStatus(`Connected: ${{address}}\\n\\nFetching permit details...`);
  const typedDataResp = await fetch(`/api/link/${{TOKEN}}/typed-data?address=${{address}}`);
  if (!typedDataResp.ok) {{
    setStatus("Could not prepare the allowance permit. Try again.", "error");
    return;
  }}
  const {{ typed_data }} = await typedDataResp.json();

  setStatus(`Connected: ${{address}}\\n\\nSigning allowance permit (no gas, just a signature)...`);
  const permitSig = await window.ethereum.request({{
    method: "eth_signTypedData_v4",
    params: [address, JSON.stringify(typed_data)],
  }});

  setStatus(`Connected: ${{address}}\\n\\nSubmitting...`);
  const completeResp = await fetch(`/api/link/${{TOKEN}}/complete`, {{
    method: "POST",
    headers: {{ "Content-Type": "application/json" }},
    body: JSON.stringify({{
      address: address,
      ownership_signature: ownershipSig,
      permit_signature: permitSig,
    }}),
  }});

  if (!completeResp.ok) {{
    const body = await completeResp.json().catch(() => ({{}}));
    setStatus(`Linking failed: ${{body.detail || completeResp.statusText}}`, "error");
    return;
  }}

  const result = await completeResp.json();
  if (result.status === "linked") {{
    setStatus(`Wallet linked: ${{address}}\\n\\nYou can close this page - FairSharebot will confirm in Telegram.`, "success");
  }} else {{
    setStatus(`Wallet verified: ${{address}}\\n\\nThe allowance transaction is still confirming - FairSharebot will let you know shortly.`, "success");
  }}
}}

document.getElementById("connectBtn").addEventListener("click", () => {{
  document.getElementById("connectBtn").disabled = true;
  run().catch(err => setStatus(`Error: ${{err.message || err}}`, "error"));
}});
</script>
</body>
</html>
"""
