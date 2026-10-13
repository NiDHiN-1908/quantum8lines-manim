"""
CLI diagnostic tool to verify LLM connectivity and measure response latency.
Follows SPEC.md Section 21 and Milestone M5a Step 5.

Usage:
    python -m agents.llm.check --provider ollama --model <name>
"""

import argparse
import time
import sys
from pathlib import Path

from agents.llm.config import get_role_config, create_provider
from agents.llm.base import LLMProvider


def main() -> None:
    parser = argparse.ArgumentParser(description="Check LLM provider connectivity and measure latency.")
    parser.add_argument("--provider", default="ollama", help="Provider name (ollama, gemini, mock)")
    parser.add_argument("--model", default=None, help="Model name (overrides config/llm.json)")
    parser.add_argument("--prompt", default="What is an eigenvector in one concise sentence?", help="Prompt to test")
    parser.add_argument("--role", default="default", help="Role in config/llm.json to look up")

    args = parser.parse_args()

    # Determine effective model
    model_name = args.model
    if not model_name:
        try:
            cfg = get_role_config(args.role, check_model=False)
            if cfg.provider == args.provider and cfg.model and cfg.model != "<fill-in>":
                model_name = cfg.model
        except Exception:
            pass

    if not model_name or model_name == "<fill-in>":
        print(
            f"Provider '{args.provider}' model is unset in config/llm.json (placeholder '<fill-in>'). "
            "To test connectivity, provide an explicit model with '--model <name>' or update config/llm.json."
        )
        return

    print(f"Connecting to provider '{args.provider}' with model '{model_name}'...")
    try:
        provider = create_provider(args.provider)
    except Exception as e:
        print(f"Error initializing provider '{args.provider}': {e}", file=sys.stderr)
        sys.exit(1)

    start_time = time.perf_counter()
    try:
        reply = provider.complete(
            system="You are a helpful mathematical assistant. Be brief.",
            user=args.prompt,
            model=model_name,
            timeout=60.0,
        )
        latency = time.perf_counter() - start_time
        print(f"\n[Response Received in {latency:.2f}s]:")
        print(reply.strip())
        print(f"\nLatency: {latency:.4f} seconds")
    except Exception as e:
        latency = time.perf_counter() - start_time
        print(f"\nError communicating with {args.provider} after {latency:.2f}s: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
