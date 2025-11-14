import dotenv from "dotenv";
import path from "path";
import { fileURLToPath } from "url";

import boltPkg from "@slack/bolt";

const { App } = boltPkg;

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Load env vars from the main RAAS project root
dotenv.config({ path: path.resolve(__dirname, "..", "..", ".env") });

const app = new App({
  token: process.env.SLACK_BOT_TOKEN,
  appToken: process.env.SLACK_APP_TOKEN,
  socketMode: true,
  signingSecret: process.env.SLACK_SIGNING_SECRET,
});

const RAAS_API_URL = (process.env.RAAS_API_URL || process.env.RACEN_ANSWER_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

function isFromBot(event) {
  return Boolean(event.bot_id) || event.subtype === "bot_message";
}

function resolveSessionId(channel, user) {
  if (channel) {
    return `slack:${channel}`;
  }
  return `slack-user:${user}`;
}

async function callRaasChat({ text, user, channel }) {
  const body = {
    session_id: resolveSessionId(channel, user),
    channel: "slack",
    user_id: user,
    message_text: text ?? "",
  };

  const response = await fetch(`${RAAS_API_URL}/chat`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    throw new Error(`RAAS chat API failed with status ${response.status}`);
  }

  const data = await response.json().catch(() => null);
  if (!data || typeof data.reply_to_user !== "string") {
    throw new Error("RAAS chat API returned invalid payload");
  }
  return data;
}

async function postReply({ client, channel, thread_ts, text }) {
  await client.chat.postMessage({
    channel,
    text,
    thread_ts,
    unfurl_links: false,
    unfurl_media: false,
  });
}

app.event("app_mention", async ({ event, client, logger }) => {
  try {
    if (isFromBot(event)) {
      return;
    }
    const text = (event.text || "").replace(/<@[^>]+>/g, "").trim();
    const data = await callRaasChat({
      text,
      user: event.user,
      channel: event.channel,
    });

    await postReply({
      client,
      channel: event.channel,
      thread_ts: event.thread_ts || event.ts,
      text: data.reply_to_user,
    });
  } catch (error) {
    logger.error(error);
    await postReply({
      client,
      channel: event.channel,
      thread_ts: event.thread_ts || event.ts,
      text: "Sorry, I had trouble handling that.",
    });
  }
});

app.message(async ({ message, client, logger }) => {
  try {
    if (isFromBot(message)) {
      return;
    }
    const text = message.text ?? "";
    const data = await callRaasChat({
      text,
      user: message.user,
      channel: message.channel,
    });

    await postReply({
      client,
      channel: message.channel,
      thread_ts: message.thread_ts || message.ts,
      text: data.reply_to_user,
    });
  } catch (error) {
    logger.error(error);
    await postReply({
      client,
      channel: message.channel,
      thread_ts: message.thread_ts || message.ts,
      text: "Sorry, I had trouble handling that.",
    });
  }
});

app.start(process.env.PORT || 3000).then(() => {
  console.log("Slack RAAS bot is running.");
});
