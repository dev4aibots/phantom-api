# YOUR SETUP — PhantomAPI (raw ChatGPT chat as an API key)

Prepared by Igris for Devraj. This turns ChatGPT's free web chat (Luna) into an
OpenAI-compatible API you can plug into Cursor, Cline, n8n, or any OpenAI client.

## Your API key

Your personal key lives in **`secure.env` on your Google Drive** (link below) —
it is NOT in this repo. After cloning:

```bash
cp /path/to/secure.env .env
```

(`secure.env` content = the `.env` this gateway needs, including your
`API_SECRET_KEY`. Keep it private — anyone with it can use your gateway.)

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
