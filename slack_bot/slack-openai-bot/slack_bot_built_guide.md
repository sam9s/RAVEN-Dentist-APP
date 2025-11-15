# Slack Bot 4 RAVENs

# **Objective**

- Build a Slack bot (Socket Mode) that:
    - Receives user messages in Slack.
    - Calls a backend Answer API over HTTP with the text and context.
    - Returns a concise, friendly reply to Slack with optional follow-up.

# **Inputs and Config**

- Slack app setup:
    - Enable Socket Mode.
    - Generate:
        - Bot token.
        - App-level token.
        - Signing secret (not used in Socket Mode but keep it).
    - Scopes:
        - app_mentions:read
        - chat:write
        - im:history
        - im:write
        - channels:history (if needed)
- Environment variables:
    - SLACK_BOT_TOKEN=...
    - SLACK_APP_TOKEN=...
    - SLACK_SIGNING_SECRET=...
    - RACEN_ANSWER_URL=[**http://127.0.0.1**](http://127.0.0.1/):8000/answer
    - OPENAI_API_KEY=... (if the bot does any local LLM work; optional if only the backend answers)
- Backend Answer API contract (HTTP):
    - POST RACEN_ANSWER_URL with JSON:
        - { "q": "user message", "conversation_id": "...", "user_id": "U123", "channel_id": "C123" }
    - Response JSON:
        - { "answer": "text to post", "citations": [ {"url":"...", "start_line":1, "end_line":10} ] }

# **Architecture and Flow**

- Event flow:
    - Socket Mode connects WebSocket to Slack.
    - Listen to:
        - app_mention events
        - message.im (direct messages)
    - For each event:
        - Extract user text, user ID, channel, thread_ts.
        - Call Answer API with the text.
        - Post the Answer API response back to Slack in the same channel/thread.
- Delivery guarantees:
    - Idempotency: ignore bot’s own messages.
    - Use thread_ts when replying to mentions to keep threads clean.

# **Node.js Skeleton (like our current app.js)**

`javascript

// app.jsrequire('dotenv').config();const { App, LogLevel, SocketModeReceiver } = require('@slack/bolt');const fetch = require('node-fetch');const receiver = new SocketModeReceiver({  appToken: process.env.SLACK_APP_TOKEN,  logLevel: LogLevel.INFO,});const app = new App({  token: process.env.SLACK_BOT_TOKEN,  signingSecret: process.env.SLACK_SIGNING_SECRET,  receiver,  logLevel: LogLevel.INFO,});const ANSWER_URL = process.env.RACEN_ANSWER_URL || 'http://127.0.0.1:8000/answer';async function askBackend(q, user, channel, thread_ts) {  const body = { q, user_id: user, channel_id: channel, thread_ts };  const resp = await fetch(ANSWER_URL, {    method: 'POST',    headers: { 'Content-Type': 'application/json' },    body: JSON.stringify(body),  });  if (!resp.ok) throw new Error(`Answer API ${resp.status}`);  return await resp.json();}function isFromBot(message) {  return message.subtype === 'bot_message' || !!message.bot_id;}app.event('app_mention', async ({ event, client, logger }) => {  try {    if (isFromBot(event)) return;    const text = event.text.replace(/<@[^>]+>/g, '').trim();    const data = await askBackend(text, event.user, event.channel, event.thread_ts || event.ts);    await client.chat.postMessage({      channel: event.channel,      text: data.answer || 'Sorry, I had trouble answering.',      thread_ts: event.thread_ts || event.ts,      unfurl_links: false,      unfurl_media: false,    });  } catch (e) {    logger.error(e);  }});app.message(async ({ message, client, logger }) => {  try {    if (isFromBot(message)) return;    // Handle DMs or channel messages (optional: restrict to DMs only)    const text = message.text || '';    const data = await askBackend(text, message.user, message.channel, message.thread_ts || message.ts);    await client.chat.postMessage({      channel: message.channel,      text: data.answer || 'Sorry, I had trouble answering.',      thread_ts: message.thread_ts || message.ts,      unfurl_links: false,      unfurl_media: false,    });  } catch (e) {    logger.error(e);  }});(async () => {  await app.start();  console.log('Slack OpenAI bot is running.');})();`

# **Backend Answer API (Python FastAPI example)**

- Endpoint: POST /answer
- Input: JSON with q, user_id, channel_id, thread_ts
- Output: JSON with answer, citations

`python

# scripts/answer_api.pyfrom fastapi import FastAPIfrom pydantic import BaseModelfrom racen.step4_answer import answer_query  # your retrieval+LLMapp = FastAPI()class Ask(BaseModel):    q: str    user_id: str | None = None    channel_id: str | None = None    thread_ts: str | None = Noneclass Ans(BaseModel):    answer: str    citations: list[dict] = []@app.post("/answer", response_model=Ans)def answer(a: Ask):    text, cits = answer_query(a.q, top_k=6)    return {"answer": text, "citations": [c.__dict__ for c in cits]}`

# **Security and Reliability**

- Store tokens in .env; never hardcode.
- Use Socket Mode to avoid public HTTP endpoints in dev.
- Rate limit: minimal (Bolt handles retries; keep Answer API fast).
- Error handling:
    - If backend fails, reply: “Sorry, I couldn’t fetch that. Want me to try again?”
- Logging:
    - Log event type, user, channel, and latency.
- Timeouts:
    - Set 10–20s timeout on backend call; fail gracefully.

# **Local run**

- Node bot:
    - npm install slack/bolt node-fetch
    - node app.js
- Answer API:
    - uvicorn scripts.answer_api:app --host 127.0.0.1 --port 8000 --reload
- .env (example):
    - SLACK_BOT_TOKEN=xoxb-...
    - SLACK_APP_TOKEN=xapp-1-...
    - SLACK_SIGNING_SECRET=...
    - RACEN_ANSWER_URL=[**http://127.0.0.1**](http://127.0.0.1/):8000/answer

# **Testing Checklist**

- DM the bot: “hi” → bot replies via /answer.
- mention in a public channel → replies in thread.
- Short bursts of messages → no duplicate replies; no bot loops.
- Backend down → user gets graceful apology.

# **Notes to Codex**

- Mirror our current behavior:
    - Socket Mode connection.
    - Post to Answer API with the raw user text.
    - Keep replies short, friendly, and threaded.
    - Avoid Slack-side business rules; keep logic in backend.
    - Use env vars for all tokens and URLs.