import os
import sys
import time
import re

# Unset ALL_PROXY to avoid connection issues (keep http/https proxy for T430)
for var in ("ALL_PROXY", "all_proxy"):
    os.environ.pop(var, None)

from dotenv import load_dotenv
import anthropic

load_dotenv()

# --- Phoenix cloud tracing setup ---
os.environ["PHOENIX_CLIENT_HEADERS"] = f"api_key={os.getenv('PHOENIX_API_KEY')}"
os.environ["PHOENIX_COLLECTOR_ENDPOINT"] = "https://app.phoenix.arize.com/s/linkedInArticleGen"
os.environ["PHOENIX_PROJECT_NAME"] = "linkedInArticleGen"

from phoenix.otel import register
register(project_name="linkedInArticleGen", auto_instrument=True)

from openinference.instrumentation.anthropic import AnthropicInstrumentor
AnthropicInstrumentor().instrument()

from opentelemetry import trace
tracer = trace.get_tracer(__name__)

MODEL = "claude-opus-4-5-20251101"
NUM_BATCHES = 3
DELAY_BETWEEN_BATCHES = 10


def read_prompt(filename):
    path = os.path.join(os.path.dirname(__file__), "prompts", filename)
    with open(path, "r") as f:
        return f.read()


def get_multiline_input(prompt_text):
    print(prompt_text)
    print("(Press Enter twice when done)\n")
    lines = []
    empty_count = 0
    while True:
        line = input()
        if line == "":
            empty_count += 1
            if empty_count >= 2:
                break
            lines.append(line)
        else:
            empty_count = 0
            lines.append(line)
    return "\n".join(lines).rstrip()


def extract_final_pitches(output):
    marker = "## Final Pitches"
    idx = output.find(marker)
    if idx != -1:
        return output[idx + len(marker):].strip()
    # Fallback: try case-insensitive
    match = re.search(r"##\s*Final\s*Pitches", output, re.IGNORECASE)
    if match:
        return output[match.end():].strip()
    return output.strip()


def extract_pitch_by_number(supervisor_output, number):
    pattern = rf"\[{number}\]\s*\(from Batch \d+\)\s*\n(.*?)(?=\n\[\d+\]\s*\(from Batch|\Z)"
    match = re.search(pattern, supervisor_output, re.DOTALL)
    if match:
        return f"[{number}] " + match.group(0).split("\n", 1)[-1].strip() if "\n" in match.group(0) else match.group(1).strip()
    # Fallback: grab everything after [N] until next [N] or end
    pattern2 = rf"\[{number}\].*?\n(.*?)(?=\n\[\d+\]|\Z)"
    match2 = re.search(pattern2, supervisor_output, re.DOTALL)
    if match2:
        return match2.group(1).strip()
    return None


def run_pitch_modification(client, system_prompt, current_pitch, feedback, raw_material=None):
    if raw_material:
        user_content = (
            f"## Current Pitch\n\n{current_pitch}\n\n"
            f"## Feedback\n\n{feedback}\n\n"
            f"## Raw Material\n\n{raw_material}"
        )
    else:
        user_content = (
            f"## Current Pitch\n\n{current_pitch}\n\n"
            f"## Feedback\n\n{feedback}"
        )

    message = client.messages.create(
        model=MODEL,
        max_tokens=16000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
    )

    return message.content[0].text


def run_angle_proposal(client, system_prompt, raw_material, batch_num):
    print(f"\n{'='*60}")
    print(f"  BATCH {batch_num}")
    print(f"{'='*60}\n")

    message = client.messages.create(
        model=MODEL,
        max_tokens=16000,
        system=system_prompt,
        messages=[{"role": "user", "content": raw_material}],
    )

    output = message.content[0].text
    print(output)
    return output


def run_supervisor(client, system_prompt, combined_pitches):
    print(f"\n{'='*60}")
    print(f"  SUPERVISOR ANALYSIS")
    print(f"{'='*60}\n")

    message = client.messages.create(
        model=MODEL,
        max_tokens=16000,
        system=system_prompt,
        messages=[{"role": "user", "content": combined_pitches}],
    )

    output = message.content[0].text
    print(output)
    return output


def main():
  with tracer.start_as_current_span("article_generation_pipeline"):
    client = anthropic.Anthropic()

    angle_prompt = read_prompt("angleProposalPrompt1.md")
    supervisor_prompt = read_prompt("supervisorPrompt1.5.md")

    raw_material = get_multiline_input("Paste your raw material below:")

    if not raw_material.strip():
        print("No material provided. Exiting.")
        sys.exit(1)

    # --- Run 3 angle proposal batches ---
    print(f"\nRunning {NUM_BATCHES} angle proposal batches...")

    batch_outputs = []
    extracted_pitches = []

    for i in range(1, NUM_BATCHES + 1):
        if i > 1:
            print(f"\nWaiting {DELAY_BETWEEN_BATCHES}s before batch {i}...")
            time.sleep(DELAY_BETWEEN_BATCHES)

        with tracer.start_as_current_span(f"angle_proposal_batch_{i}"):
            output = run_angle_proposal(client, angle_prompt, raw_material, i)
            batch_outputs.append(output)
            extracted_pitches.append(extract_final_pitches(output))

    # --- Combine extracted pitches ---
    combined = ""
    for i, pitches in enumerate(extracted_pitches, 1):
        combined += f"## Batch {i}\n\n{pitches}\n\n"

    print(f"\n{'='*60}")
    print(f"  COMBINED FINAL PITCHES")
    print(f"{'='*60}\n")
    print(combined)

    # --- Run supervisor ---
    print("Running supervisor analysis...")
    with tracer.start_as_current_span("supervisor_analysis"):
        supervisor_output = run_supervisor(client, supervisor_prompt, combined)

    # --- Ask user to pick ---
    print(f"\n{'='*60}")
    choice = input("\nPick an angle by number: ")
    print(f"\nYou selected angle [{choice}].")

    selected_pitch = extract_pitch_by_number(supervisor_output, choice)
    if not selected_pitch:
        print(f"Could not extract pitch [{choice}] from supervisor output.")
        print("Using full supervisor output as selected pitch.")
        selected_pitch = supervisor_output

    # --- Pitch modification loop ---
    pitch_mod_prompt = read_prompt("pitchModPrompt1.4.md")
    current_pitch = selected_pitch
    revision_count = 0

    while True:
        print(f"\n{'='*60}")
        print(f"  SELECTED PITCH")
        print(f"{'='*60}\n")
        print(current_pitch)
        print(f"\n{'='*60}")
        feedback = input("\nAny changes? (type 'next' to proceed): ")

        if feedback.strip().lower() == "next":
            break

        revision_count += 1
        print("\nRevising pitch...")
        with tracer.start_as_current_span("pitch_modification"):
            if revision_count == 1:
                current_pitch = run_pitch_modification(
                    client, pitch_mod_prompt, current_pitch, feedback, raw_material
                )
            else:
                current_pitch = run_pitch_modification(
                    client, pitch_mod_prompt, current_pitch, feedback
                )

    final_pitch = current_pitch
    print(f"\n{'='*60}")
    print(f"  FINAL PITCH")
    print(f"{'='*60}\n")
    print(final_pitch)


if __name__ == "__main__":
    main()
