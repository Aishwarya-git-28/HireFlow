"""python check_limits.py: which models can this account actually use, and how big are the limits?"""
import logging
import time

import openai

import config

logging.disable(logging.CRITICAL)


def client(provider: str) -> openai.OpenAI:
    p = config._PROVIDERS[provider]
    return openai.OpenAI(base_url=p["base_url"], api_key=p["key"], max_retries=0)


def probe(provider: str, model: str) -> str:
    try:
        raw = client(provider).chat.completions.with_raw_response.create(
            model=model, messages=[{"role": "user", "content": "Reply with: pong"}], max_tokens=200)
        h = raw.headers
        return (f"OK   tokens/min limit: {h.get('x-ratelimit-limit-tokens', '?')} | "
                f"requests/day limit: {h.get('x-ratelimit-limit-requests', '?')}")
    except openai.RateLimitError as e:
        return "429  " + str(e)[:260].replace("\n", " ")
    except Exception as e:
        return f"FAIL {type(e).__name__}: {str(e)[:160]}"


print("GROQ")
for m in ("openai/gpt-oss-120b", "qwen/qwen3.8-27b", "openai/gpt-oss-20b"):
    print(f"  {m:24} {probe('groq', m)}")

print("\nGEMINI (Flash models only, one tiny call each)")
if not config._PROVIDERS["gemini"]["key"]:
    print("  no GEMINI_API_KEY in .env")
else:
    skip = ("tts", "image", "embed", "live", "audio", "robotics", "computer", "native", "veo", "imagen")
    ids = sorted({m.id.removeprefix("models/") for m in client("gemini").models.list().data})
    flash = [i for i in ids if "flash" in i and not any(s in i for s in skip)][:10]
    for m in flash:
        print(f"  {m:34} {probe('gemini', m)}")
        time.sleep(5)