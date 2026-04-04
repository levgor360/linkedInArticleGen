import os
import sys
import json
from dotenv import load_dotenv

load_dotenv()

os.environ["PHOENIX_CLIENT_HEADERS"] = f"api_key={os.getenv('PHOENIX_API_KEY')}"
os.environ["PHOENIX_COLLECTOR_ENDPOINT"] = "https://app.phoenix.arize.com/s/linkedInArticleGen"

from phoenix.client import Client

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 export_trace.py <trace_id>")
        sys.exit(1)

    trace_id = sys.argv[1]
    client = Client()

    spans = client.spans.get_spans(
        project_identifier="linkedInArticleGen",
        trace_ids=[trace_id]
    )

    os.makedirs("exports", exist_ok=True)
    filepath = f"exports/trace_{trace_id}.json"

    with open(filepath, "w") as f:
        json.dump(spans, f, indent=2, default=str)

    print(f"Exported {len(spans)} spans to {filepath}")
    for span in spans:
        print(f"  - {span.get('name', 'unknown')}")

if __name__ == "__main__":
    main()
