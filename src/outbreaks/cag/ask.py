from __future__ import annotations

import argparse
import json

from outbreaks.cag.engine import CAGEngine


def main() -> None:
    parser = argparse.ArgumentParser(description="Ask the bundled CAG assistant a question.")
    parser.add_argument("--question", required=True, help="Question to answer.")
    parser.add_argument("--region", dest="region_key", help="Optional region-specific cache key.")
    parser.add_argument("--json", action="store_true", help="Emit a JSON response.")
    args = parser.parse_args()

    answer = CAGEngine().ask(args.question, args.region_key)
    if args.json:
        print(
            json.dumps(
                {
                    "answer": answer.answer,
                    "used_region": answer.used_region,
                    "cache_type": answer.cache_type,
                }
            )
        )
        return

    print(answer.answer)


if __name__ == "__main__":
    main()
