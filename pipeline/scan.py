import os
import json
from pathlib import Path

QUEUE_FILE = "queue.json"
INCOMING_DIR = "incoming"

def main():
    with open(QUEUE_FILE, "r") as f:
        queue = json.load(f)
    existing = {v["filename"] for v in queue["videos"]}
    for fpath in Path(INCOMING_DIR).glob("*.mp4"):
        fname = fpath.name
        if fname not in existing:
            queue["videos"].append({
                "filename": fname,
                "status": "pending_approval",
                "uploaded_at": None,
                "processed_at": None
            })
            print(f"Added to queue: {fname}")
    with open(QUEUE_FILE, "w") as f:
        json.dump(queue, f, indent=2)

if __name__ == "__main__":
    main()
