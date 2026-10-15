# NULL

A simple web chatbot built with Flask and the Groq API.

## Features
- Multi-turn chat: the conversation history is sent with each request
- Automatic model selection: picks the best available Groq model
  (preference: gpt-oss-120b, gpt-oss-20b, Llama 4, Llama 3.3, Qwen)
- Optional `GROQ_MODEL` setting to force a specific model
- Friendly error handling for invalid keys, rate limits and connection failures
- API keys are redacted from logged error messages

## Setup
```
pip install -r requirements.txt
cp .env.example .env     # then add your GROQ_API_KEY
python app.py
```

## Environment variables
| Variable | Purpose |
|---|---|
| `GROQ_API_KEY` | Your Groq API key (required) |
| `GROQ_MODEL` | Force a specific model (optional) |

## Tech
Python, Flask, Groq SDK, HTML/CSS/JS
