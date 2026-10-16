# YOUR SETUP — PhantomAPI (raw ChatGPT chat as an API key)

Prepared by Igris for Devraj. This turns ChatGPT's free web chat (Luna) into an
OpenAI-compatible API you can plug into Cursor, Cline, n8n, or any OpenAI client.

## Luna mode — how this build behaves

- **API key: any string works.** Send any `Authorization: Bearer <anything>` —
  `sk-test`, `hello`, whatever. Only a missing/empty key is rejected.
  (Your `secure.env` key from Drive still works too; it's just no longer special.)
- **Model: any string = Luna.** Request `gpt-4o`, `luna`, `anything-at-all` —
  every request is served by GPT-5.6 Luna (the free web chat). `/v1/models`
  lists `gpt-5.6-luna` and `luna`.
- **Endpoints are randomized.** Nothing lives at a guessable path. On startup
  the server generates a 24-char hex prefix (e.g. `/9f3a…`) and saves it to
  `.env` as `ENDPOINT_PREFIX`, so it stays stable across restarts. The real
  paths are:
  - API base: `http://127.0.0.1:7777/<prefix>/v1` ← use this in Cursor/Cline/n8n
  - Chat GUI: `http://127.0.0.1:7777/<prefix>/gui`
  - The prefix is printed in the server logs at startup and in `.env`.
  - `/v1/...`, `/gui`, `/docs` at the root all return 404.
- **No real authentication.** Anyone who can reach your machine's port can use
  it — keep `HOST=127.0.0.1` in `.env` so only your own computer can connect.

## Your secure.env (optional now)

Your personal key lives in **`secure.env` on your Google Drive**.
Since any string works as the key, this file is now just a convenience —
use its key or any string you like. It is NOT in this repo. After cloning:

```bash
cp /path/to/secure.env .env
```

Base URL once running: `http://127.0.0.1:7777/<prefix>/v1`
(find `<prefix>` in the server startup logs or `.env` as `ENDPOINT_PREFIX`)

## Run it on YOUR computer (it cannot run on the sandbox — see Limits)

Prerequisites: Python 3.10+, Google Chrome installed.

```bash
git clone https://github.com/mrshibly/PhantomAPI.git
cd PhantomAPI
pip install -r requirements.txt
cp .env.example .env
# put the API key above into .env as API_SECRET_KEY
python run.py
```

Open http://localhost:7777/gui to test in the built-in chat UI.

## Plug into your tools

- **Cursor / Cline / any OpenAI client:** Base URL `http://127.0.0.1:7777/v1`,
  API Key = the key above. Model name can be anything (e.g. `gpt-4o`) —
  the gateway ignores it and uses the free web chat.
- **n8n:** Credentials → New → OpenAI API → Base URL
  `http://127.0.0.1:7777/v1`, API Key = the key above.

## Honest limits (read once)

- It drives the **free web tier** (Luna) through a real browser. Free text chats
  are unlimited per OpenAI, but hammering it like a datacenter bot can trip
  abuse detection — it processes **one request at a time**.
- **Anonymous session**: no login needed, but no Plus features either.
- **It must run on your own machine/network.** Verified 2026-10-16: the sandbox
  network blocks chatgpt.com entirely (ERR_TUNNEL_CONNECTION_FAILED), and
  OpenAI flags datacenter IPs as "unusual activity". Your home network is
  where this works.
- Upstream repo: https://github.com/mrshibly/PhantomAPI (MIT).
