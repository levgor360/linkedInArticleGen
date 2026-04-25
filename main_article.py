import os
import sys
import time
import re

# Unset ALL_PROXY to avoid connection issues (keep http/https proxy for T430)
for var in ("ALL_PROXY", "all_proxy"):
    os.environ.pop(var, None)

from dotenv import load_dotenv
import anthropic
from openai import OpenAI

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
    # Isolate the Selected Pitches section so we don't match [N] references
    # scattered throughout the Analysis section.
    selected_match = re.search(
        r"##\s*Selected\s*Pitches\b", supervisor_output, re.IGNORECASE
    )
    if selected_match:
        search_region = supervisor_output[selected_match.end():]
    else:
        search_region = supervisor_output

    pattern = rf"(\[{number}\]\s*\(from Batch \d+\).*?)(?=\n\[\d+\]\s*\(from Batch|\Z)"
    match = re.search(pattern, search_region, re.DOTALL)
    if match:
        return match.group(1).strip()
    # Fallback: grab everything from [N] header line through body until next [N] or end
    pattern2 = rf"(\[{number}\].*?)(?=\n\[\d+\]|\Z)"
    match2 = re.search(pattern2, search_region, re.DOTALL)
    if match2:
        return match2.group(1).strip()
    return None


def run_pitch_modification(client, system_prompt, history):
    response = client.messages.create(
        model=MODEL,
        max_tokens=16000,
        system=system_prompt,
        messages=history,
    )
    assistant_reply = response.content[0].text
    history.append({"role": "assistant", "content": assistant_reply})
    return history


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


def run_originality_scorer(client, system_prompt, raw_material, angle_focus, batch_output):
    print(f"\n{'='*60}")
    print(f"  ORIGINALITY SCORING")
    print(f"{'='*60}\n")

    user_content = (
        f"## Raw Material\n\n{raw_material}\n\n"
        f"## Angle Focus\n\n{angle_focus}\n\n"
        f"## Model Output\n\n{batch_output}"
    )

    message = client.messages.create(
        model=MODEL,
        max_tokens=16000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
    )

    output = message.content[0].text
    print(output)
    return output


def run_fidelity_check(system_prompt, raw_material, selected_pitches):
    print(f"\n{'='*60}")
    print(f"  FIDELITY CHECK")
    print(f"{'='*60}\n")

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    user_content = (
        f"## Raw Material\n\n{raw_material}\n\n"
        f"## Selected Pitches\n\n{selected_pitches}"
    )

    response = client.chat.completions.create(
        model="gpt-5.2",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    )

    output = response.choices[0].message.content
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


def run_article_generator(client, system_prompt, final_pitch, raw_material):
    print(f"\n{'='*60}")
    print(f"  ARTICLE GENERATION")
    print(f"{'='*60}\n")

    user_content = (
        f"## Final Pitch\n\n{final_pitch}\n\n"
        f"## Raw Material\n\n{raw_material}"
    )

    message = client.messages.create(
        model=MODEL,
        max_tokens=16000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
    )

    output = message.content[0].text
    print(output)
    return output


def expand_shortcodes(user_input):
    SHORTCODE_EXPANSIONS = {
        "-v": (
            "Generate 3 variations of the following text. Retain the semantic meaning "
            "but vary the delivery — sentence structure, word choice, style. Each variation "
            "should explore a different direction for improvement, not three passes at the "
            "same adjustment. Keep variations about the same length as the original. Text: {text}"
        ),
        "-s": (
            "Offer a list of 5 synonyms for the following snippet. The alternatives should "
            "be more fitting in context, improve clarity, or improve stylistic delivery. "
            "Snippet: {text}"
        ),
        "-x": (
            "Expand the following text. It has the right idea but lacks context or descriptors "
            "for the reader to fully grasp what's being described. Draw from the raw material "
            "to fill in the conceptual gaps. Don't add anecdotes, commentary, or restatement. "
            "Just supply the specifics the reader needs. Return one version. Text: {text}"
        ),
        "-e": (
            "The following text makes a claim that needs a concrete example to land. Suggest "
            "one from the raw material, or mark an [EXAMPLE SLOT] if nothing fits. Return the "
            "sentence with the example integrated. Text: {text}"
        ),
        "-r": (
            "Reframe the following text. Find 3 completely different ways to make the same "
            "point — not variations in wording, but variations in the move the text makes. "
            "Shift the metaphor, perspective, scale, or emotional angle. Text: {text}"
        ),
        "-c": (
            "Continue the following text. Write 1-2 sentences that follow naturally, in the "
            "same voice and direction. Text: {text}"
        ),
        "-w": (
            "Rewrite the following section from scratch using the raw material. Throw out the "
            "current version and rebuild it, drawing on whichever details best serve the "
            "section's purpose. Ensure it connects naturally to what comes before and after "
            "in the draft. Return one version. Text: {text}"
        ),
    }

    HELP_TEXT = (
        "\n  Assembly Workbench Commands\n"
        "  -v [text]  Generate 3 variations of the text\n"
        "  -s [text]  Offer 5 synonyms for a snippet\n"
        "  -x [text]  Expand text with detail from raw material\n"
        "  -e [text]  Add a concrete example to a claim\n"
        "  -r [text]  Reframe text from 3 different angles\n"
        "  -c [text]  Continue text with 1-2 sentences\n"
        "  -w [text]  Rewrite section from scratch using raw material\n"
        "  -?         Show this help\n"
    )

    if re.search(r'-\?', user_input):
        print(HELP_TEXT)
        return None

    match = re.search(r'(-[vsxercw])\s*\[(.+?)\]', user_input, re.DOTALL)
    if match:
        code = match.group(1)
        text = match.group(2).strip()
        return SHORTCODE_EXPANSIONS[code].format(text=text)

    return user_input


def run_assemble_session(client, system_prompt, raw_material, article_versions):
    print(f"\n{'='*60}")
    print(f"  ASSEMBLY WORKBENCH")
    print(f"{'='*60}\n")
    print(article_versions)
    print(f"\n{'='*60}")
    print(f"  DRAFT VERSIONS END")
    print(f"{'='*60}\n")

    context_prefix = (
        f"# Raw Material\n\n{raw_material}\n\n"
        f"# Draft Versions\n\n{article_versions}\n\n"
        f"# Instructions\n\n"
    )

    history = []
    first_input = True

    while True:
        user_input = get_multiline_input(
            "Assembly workbench (type 'next' to proceed, '-?' for help):"
        )

        if user_input.strip().lower() == "next":
            break

        expanded = expand_shortcodes(user_input)
        if expanded is None:
            continue

        if first_input:
            message_content = context_prefix + expanded
            first_input = False
        else:
            message_content = expanded

        history.append({"role": "user", "content": message_content})

        response = client.messages.create(
            model=MODEL,
            max_tokens=16000,
            system=system_prompt,
            messages=history,
        )
        assistant_reply = response.content[0].text
        print(assistant_reply)

        history.append({"role": "assistant", "content": assistant_reply})

    last_message = history[-1]["content"]
    final_draft = re.sub(r"^#\s*Draft\s*\n+", "", last_message).strip()

    print(f"\n{'='*60}")
    print(f"  FINAL DRAFT")
    print(f"{'='*60}\n")
    print(final_draft)

    return final_draft


def main():
  with tracer.start_as_current_span("article_generation_pipeline"):
    client = anthropic.Anthropic()

    angle_prompt = read_prompt("angleProposalPrompt1.md")
    supervisor_prompt = read_prompt("supervisorPrompt1.5.md")

    # Extract Angle Focus section from the angle prompt
    af_match = re.search(r"# Angle Focus\s*\n(.*?)(?=# Process)", angle_prompt, re.DOTALL)
    angle_focus = af_match.group(1).strip() if af_match else ""
    print(f"Extracted Angle Focus ({len(angle_focus)} chars)")

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

    # --- Run originality scorer on each batch ---
    scorer_prompt = read_prompt("anglePromptOriginalityScoring1.2.md")
    scored_outputs = []
    for i, batch_output in enumerate(batch_outputs, 1):
        print(f"\nScoring batch {i} for originality...")
        with tracer.start_as_current_span(f"originality_scoring_batch_{i}"):
            scored = run_originality_scorer(
                client, scorer_prompt, raw_material, angle_focus, batch_output
            )
            scored_outputs.append(scored)

    # --- Combine scored outputs for supervisor ---
    scored_combined = ""
    for i, scored in enumerate(scored_outputs, 1):
        scored_combined += f"## Batch {i}\n\n{scored}\n\n"

    print(f"\n{'='*60}")
    print(f"  COMBINED SCORED PITCHES")
    print(f"{'='*60}\n")
    print(scored_combined)

    # --- Run supervisor ---
    print("Running supervisor analysis...")
    with tracer.start_as_current_span("supervisor_analysis"):
        supervisor_output = run_supervisor(client, supervisor_prompt, scored_combined)

    # --- Run fidelity check ---
    fidelity_prompt = read_prompt("fidelityTest1.6.md")
    print("\nRunning fidelity check...")
    with tracer.start_as_current_span("fidelity_check"):
        fidelity_output = run_fidelity_check(fidelity_prompt, raw_material, supervisor_output)

    # --- Ask user to pick ---
    print(f"\n{'='*60}")
    choice = input("\nPick an angle by number: ")
    print(f"\nYou selected angle [{choice}].")

    selected_pitch = extract_pitch_by_number(fidelity_output, choice)
    if not selected_pitch:
        print(f"Could not extract pitch [{choice}] from supervisor output.")
        print("Using full supervisor output as selected pitch.")
        selected_pitch = supervisor_output

    # --- Pitch modification loop ---
    pitch_mod_prompt = read_prompt("pitchModPrompt1.4.md")
    pitch_history = []
    first_pitch_input = True

    print(f"\n{'='*60}")
    print(f"  SELECTED PITCH")
    print(f"{'='*60}\n")
    print(selected_pitch)
    print(f"\n{'='*60}")

    while True:
        feedback = input("\nAny changes? (type 'next' to proceed): ")

        if feedback.strip().lower() == "next":
            break

        if first_pitch_input:
            message_content = (
                f"## Selected Pitch\n\n{selected_pitch}\n\n"
                f"## Raw Material\n\n{raw_material}\n\n"
                f"## Feedback\n\n{feedback}"
            )
            first_pitch_input = False
        else:
            message_content = feedback

        pitch_history.append({"role": "user", "content": message_content})

        print("\nRevising pitch...")
        with tracer.start_as_current_span("pitch_modification"):
            pitch_history = run_pitch_modification(
                client, pitch_mod_prompt, pitch_history
            )

        print(pitch_history[-1]["content"])

    # Extract final pitch from ## Current Pitch section of last assistant message
    if pitch_history:
        last_message = pitch_history[-1]["content"]
        parts = last_message.split("## Current Pitch")
        if len(parts) > 1:
            final_pitch = parts[-1].strip()
        else:
            final_pitch = last_message.strip()
    else:
        final_pitch = selected_pitch

    print(f"\n{'='*60}")
    print(f"  FINAL PITCH")
    print(f"{'='*60}\n")
    print(final_pitch)

    # --- Run article generator ---
    article_gen_prompt = read_prompt("articleGeneratePrompt2.md")
    print("\nGenerating article versions...")
    with tracer.start_as_current_span("article_generation"):
        article_versions = run_article_generator(
            client, article_gen_prompt, final_pitch, raw_material
        )

    # --- Assembly workbench ---
    assemble_prompt = read_prompt("assemblePrompt3.md")
    print("\nStarting assembly workbench...")
    with tracer.start_as_current_span("assembly_workbench"):
        final_draft = run_assemble_session(
            client, assemble_prompt, raw_material, article_versions
        )


if __name__ == "__main__":
    main()
