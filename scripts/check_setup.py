"""Stage 0 smoke test: is the environment ready for the crew?

Checks three things and prints the real error if one fails:
  1. the OpenAI key is set and one tiny LLM call works through CrewAI's LLM wrapper,
  2. the Serper key for web search is set (warning only: Stage 1 can run without it),
  3. if it is set, one real search returns results.

Run from the project root:
    .venv\\Scripts\\python scripts/check_setup.py
"""

import sys
from pathlib import Path

# Let this script import the `launchscout` package from the project root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from launchscout.config import ConfigError, get_llm, get_model_name, get_serper_key  # noqa: E402


def check_llm() -> bool:
    try:
        llm = get_llm()
    except ConfigError as err:
        print(f"[FAIL] {err}")
        return False
    print("OpenAI key : found in environment (value hidden)")

    try:
        reply = llm.call("Reply with exactly: LaunchScout is ready.")
    except Exception as err:  # show the real reason: bad key, unknown model, no credit...
        print(f"[FAIL] LLM call failed: {type(err).__name__}: {err}")
        return False
    print(f"LLM says   : {str(reply).strip()}")
    return True


def check_search() -> bool:
    if not get_serper_key():
        print("[WARN] SERPER_API_KEY is not set. The research agents need it for live web search.")
        print("       Get a free key (2,500 searches) at https://serper.dev and add it to .env.")
        return True  # not fatal for Stage 0

    from crewai_tools import SerperDevTool

    try:
        result = SerperDevTool(n_results=3).run(search_query="millet meal box Coimbatore")
    except Exception as err:
        print(f"[FAIL] Serper search failed: {type(err).__name__}: {err}")
        return False
    print(f"Serper     : search works ({len(str(result))} characters of results)")
    return True


def main() -> int:
    import crewai

    print(f"Python     : {sys.version.split()[0]}")
    print(f"CrewAI     : {crewai.__version__}")
    print(f"Model      : {get_model_name()}")

    ok = check_llm() and check_search()
    print("[OK] Setup works. Ready for Stage 1." if ok else "[FAIL] Fix the problem above, then run again.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
