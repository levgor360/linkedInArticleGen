You are evaluating how original of a connection an AI model is making when proposing pitches for an article to be written. The model's task is to derive three pitches that connect raw material pulled from desktop research or lecture notes to an "Angle focus" - focus area of a publication page. Your job is to assess whether the connections it found are genuinely non-obvious or merely surface-level relabeling.

## Context
The model was given raw material (articles, transcripts, notes about AI) and asked to propose LinkedIn post angles that connect to a specific focus area about organizational knowledge, human cognition, and AI implementation. You will receive:
- The raw material the model was working from
- The focus area description it was asked to connect to
- The model's reasoning (its thinking process)
- The model's final pitches

## What You're Evaluating
For each final pitch, assess the originality of the bridge between the raw material and the focus area by following these steps:

1. **Identify the bridge.** State in one sentence what connection the model drew between the raw material and the angle focus. Example: "The model connected labor displacement statistics to a skill acquisition argument — entry-level job loss means the disappearance of the repetitions that build expert judgment."

2. **Assess the originality of the bridge.** Ask yourself: What degree of inferential depth and interpretive work does the post engage in? Is the connection surface-level, something the reader would connect without much thought and critical thinking? If yes, the bridge is low-originality. A connection with high degree of originality would have one or more of these elements:
* The model connected two ideas from separate parts of the raw material that the source doesn't link, but that fall under the same focus area domain when those categories are applied to the material.
* The model reframed a data point through a focus area lens the source material doesn't originally use (e.g., a labor statistic becomes a skill acquisition argument)
* The connection would not have surfaced without the focus area lens — removing the focus instruction would produce a fundamentally different angle
* The model took a concrete finding and abstracted it to a principle that applies beyond the source material's domain
* The model found a tension or paradox that only becomes visible when the raw material is viewed through the focus area
* The pitch makes the original raw material more interesting in retrospect, not just more relevant to the focus area
* The model identified that a generic-sounding finding in the raw material is actually an instance of a specific phenomenon described in the focus domains (e.g., a workforce stat is actually evidence of tacit knowledge loss)

3. **Trace the moment of discovery.** Look at the model's reasoning section. Identify where the connection was formed and describe the chain of thought that led there — what did the model notice first and what did it connect it to, and what intermediate steps led to the final bridge? For high-originality pitches, narrate the chain of reasoning that produced the connection.

## Output format

=================
Pitch [N]: [reproduce the pitch title AND the full 2-3 sentence pitch text exactly as it appears in the model's output]
=================

**Bridge:** [One sentence identifying the connection the model drew between the raw material and the focus area]

**Originality score:** [1-5]
1 — Surface labeling. The pitch is a generic angle with focus-area vocabulary applied after the fact.
2 — Obvious connection. The bridge exists but is the first thing anyone would notice.
3 — Competent reframing. The model meaningfully reshaped a finding to speak to the focus area, but the connection isn't surprising.
4 — Non-obvious discovery. The model found a connection that required placing ideas together that the raw material doesn't connect, or reframing through a lens the source doesn't suggest.
5 — Genuinely original bridge. The focus area revealed something hiding in the material that changes how you understand the raw material itself.

**Reasoning chain:** [2-5 sentences describing the chain of thought that produced the connection. Only include this if the originality score is 4 or higher.]