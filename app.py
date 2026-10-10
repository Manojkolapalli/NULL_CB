import logging
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request
from groq import APIConnectionError, APIStatusError, Groq, GroqError

PROJECT_DIR = Path(__file__).resolve().parent
load_dotenv(PROJECT_DIR / ".env")
load_dotenv(PROJECT_DIR / ".venv" / ".env")

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

api_key = os.getenv("GROQ_API_KEY")
configured_model = os.getenv("GROQ_MODEL")
client = (
    Groq(api_key=api_key)
    if api_key
    else None
)
selected_model = configured_model
MODEL_PREFERENCE = (
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "meta-llama/llama-4-maverick-17b-128e-instruct",
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "qwen/qwen3-32b",
)


def get_chat_model() -> str:
    global selected_model
    if selected_model:
        return selected_model
    if client is None:
        raise RuntimeError("GROQ_API_KEY is not configured.")

    available_models = {item.id for item in client.models.list().data}
    selected_model = next(
        (model_id for model_id in MODEL_PREFERENCE if model_id in available_models),
        None,
    )
    if selected_model is None:
        raise RuntimeError(
            "No supported Groq chat model was found for this account. "
            "Set GROQ_MODEL to an available chat model."
        )
    return selected_model


@app.get("/")
def index() -> str:
    return render_template("index.html")


@app.post("/api/chat")
def chat() -> Response | tuple[Response, int]:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not isinstance(payload.get("messages"), list):
        return jsonify(error="Send a messages list to start a chat."), 400

    conversation = payload["messages"]
    if not conversation:
        return jsonify(error="Send at least one message."), 400

    messages: list[dict[str, str]] = [
        {
            "role": "system",
            "content": (
                "You are NULL, a helpful and reliable AI assistant. Answer the user's "
                "actual question directly. Be accurate, clear, and appropriately concise: "
                "keep simple answers brief and explain complex topics in enough detail. "
                "Use Markdown that renders cleanly: use headings and bullets only when "
                "they improve readability, and use tables for comparisons only when a "
                "table is clearer than prose. Never wrap an entire answer in a code fence; "
                "fence only actual code. Avoid unnecessary introductions, repetition, and "
                "malformed tables. For technical explanations, give ordered steps when "
                "requested. For coding questions, provide working, relevant code in fenced "
                "code blocks and briefly explain important details. Do not invent facts, API "
                "limits, or model capabilities. If a fact may be outdated or uncertain, "
                "state that uncertainty and distinguish it from verified information."
            ),
        }
    ]
    for message in conversation:
        if (
            not isinstance(message, dict)
            or message.get("role") not in {"user", "assistant"}
            or not isinstance(message.get("content"), str)
            or not message["content"].strip()
        ):
            return (
                jsonify(error="Messages must have a user or assistant role and non-empty text."),
                400,
            )
        messages.append(
            {"role": message["role"], "content": message["content"]}
        )

    if conversation[-1].get("role") != "user":
        return jsonify(error="The latest message must be from the user."), 400

    if client is None:
        app.logger.warning("Groq API key is not configured")
        return (
            jsonify(error="GROQ_API_KEY is not configured. Add it to your .env file."),
            503,
        )

    model = configured_model or "the automatically selected model"
    try:
        model = get_chat_model()
        completion = client.chat.completions.create(
            model=model,
            messages=messages,
        )
    except APIConnectionError as exc:
        cause = exc.__cause__
        cause_type = type(cause).__name__ if cause is not None else type(exc).__name__
        app.logger.warning("Groq API connection failed (%s)", cause_type)
        return (
            jsonify(error="Could not connect to Groq. Check your internet connection and try again."),
            502,
        )
    except APIStatusError as exc:
        remote_error = ""
        remote_message = ""
        try:
            response_body = exc.response.json()
            if isinstance(response_body, dict):
                error_detail = response_body.get("error", "")
                if isinstance(error_detail, str):
                    remote_message = error_detail
                elif isinstance(error_detail, dict):
                    message = error_detail.get("message", "")
                    if isinstance(message, str):
                        remote_message = message
        except ValueError:
            pass

        remote_error = remote_message.casefold()
        safe_remote_message = " ".join(remote_message.split())
        if api_key:
            safe_remote_message = safe_remote_message.replace(api_key, "[redacted]")
        safe_remote_message = re.sub(
            r"(?i)\bBearer\s+\S+|\bgsk_[A-Za-z0-9_-]+\b",
            "[redacted]",
            safe_remote_message,
        )[:500]
        app.logger.warning(
            "Groq API returned HTTP %s%s",
            exc.status_code,
            f": {safe_remote_message}" if safe_remote_message else "",
        )

        if exc.status_code in {401, 403} or any(
            marker in remote_error for marker in ("invalid api key", "incorrect api key")
        ):
            error = "Groq rejected the API key. Check that GROQ_API_KEY is valid and active."
        elif exc.status_code == 404:
            error = f"The model '{model}' is unavailable for this account. Set GROQ_MODEL to an available chat model."
        elif exc.status_code == 429:
            error = "Groq's request limit or account quota was reached. Please try again later."
        elif exc.status_code == 400:
            error = f"Groq rejected the request. Check that '{model}' is a model your account supports."
        else:
            error = f"Groq returned an API error (HTTP {exc.status_code}). Please try again."
        if safe_remote_message:
            error = f"{error} Details: {safe_remote_message}"
        return jsonify(error=error), 502
    except RuntimeError as exc:
        app.logger.warning("Groq chat is unavailable: %s", exc)
        return jsonify(error=str(exc)), 503
    except GroqError as exc:
        app.logger.error("Groq API request failed (%s)", type(exc).__name__)
        return jsonify(error="Groq couldn't respond right now. Please try again."), 502

    if not completion.choices:
        app.logger.error("Groq API returned no choices")
        return jsonify(error="Groq returned an empty response. Please try again."), 502

    reply = completion.choices[0].message.content
    if not reply:
        app.logger.error("Groq API returned an empty response")
        return jsonify(error="Groq returned an empty response. Please try again."), 502

    return jsonify(reply=reply)


if __name__ == "__main__":
    app.run(debug=False)
