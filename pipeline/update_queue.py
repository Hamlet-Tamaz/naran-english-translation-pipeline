import argparse
import json
from datetime import datetime

QUEUE_FILE = "queue.json"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True)
    parser.add_argument("--status", required=True)
    args = parser.parse_args()
    with open(QUEUE_FILE, "r") as f:
        queue = json.load(f)
    for v in queue["videos"]:
        if v["filename"] == args.video:
            v["status"] = args.status
            v["processed_at"] = datetime.utcnow().isoformat()
            break
    with open(QUEUE_FILE, "w") as f:
        json.dump(queue, f, indent=2)
    print(f"Updated {args.video} -> {args.status}")

if __name__ == "__main__":
    main()
