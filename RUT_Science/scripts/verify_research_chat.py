"""Usage: python -m scripts.verify_research_chat outputs/chat_<session>."""
import argparse
import json
from pathlib import Path
from rut_science.chat_verification import verify_chat
from rut_science.planning_agent import session_lock


def main():
    parser = argparse.ArgumentParser(description='Verify completed research conversation without model calls')
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    with session_lock(args.output):
        print(json.dumps(verify_chat(args.output), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
