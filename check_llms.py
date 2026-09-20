import config

for role in config.ROLE_MODELS:
    if not config.role_available(role):
        print(f"{role:9} SKIP (no API key)")
        continue
    try:
        reply = config.build_llm(role).call("Reply with: pong")
        print(f"{role:9} OK   {config.ROLE_MODELS[role]} -> {str(reply).strip()[:40]}")
    except Exception as e:
        print(f"{role:9} FAIL {config.ROLE_MODELS[role]} -> {str(e)[:120]}")