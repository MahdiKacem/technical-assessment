# Football Highlight AI Pipeline — Project Context & Implementation Roadmap

**Project:** Imaginario AI — AI Internship Technical Assessment  
**Assessment brief:** *Imaginario AI - Technical Assessment Brief: AI Internship*, draft dated 11 November 2026  
**Prepared:** 21 November 2026  
**Repository:** https://github.com/MahdiKacem/technical-assessment

This document consolidates the assessment requirements, the architecture and implementation decisions discussed so far, the current implementation state, and the remaining work. It distinguishes requirements from the assessment brief, decisions made for this project, and items that still need verification against the actual repository/database.

---

## 1. Project goal

Build a small, batch-oriented pipeline that understands a full football broadcast and produces searchable, editable highlight moments.

The required user journey is:

1. A creative brief is provided.
2. The system searches the indexed match and proposes ranked moments that fit the brief, with start/end timestamps.
3. A person selects which moments to use.
4. The system assembles a rough cut.
5. A person approves or rejects the rough cut. Rejection sends the process back for another edit.
6. The approved cut is reframed from horizontal **16:9** to vertical **9:16**, tracking the ball as it moves.

Human approval at steps 3 and 5 is mandatory. A command-line prompt is sufficient, but selections and approvals must be logged.

The project should prioritize a reliable end-to-end implementation of the required parts over attempting too many optional features. The assessment says accuracy is more important than breadth.

### Required minimum

- **Tier 1 retrieval:** shot detection and search for goals, cards and celebrations, combining visual and audio evidence.
- **Verticalization:** reframe the approved rough cut from 16:9 to 9:16 and track the ball without jitter.

### Optional / extra-credit areas

- **Tier 2 — player identity:** read jersey numbers, map them to the supplied roster, and distinguish the two teams.
- **Tier 3 — nuanced moments:** near misses, fouls, scoreboard interpretation, replay detection and duplicate removal.
- **Bonus — no-action framing:** when the ball is out of play or not visible, frame the most relevant on-screen element.

The project has implemented or explored some Tier 3 functionality, but the required Tier 1 retrieval and verticalization should remain the priority.

---

## 2. Assessment requirements and hard constraints

The following are requirements from the supplied assessment brief, not optional architecture preferences.

### 2.1 Model and compute rules

- Computer-vision models must run locally on the user's computer and fit within **24 GB RAM**.
- Run processing locally. Do not use cloud compute, including Google Cloud CPUs or GPUs.
- The permitted cloud operations are language-model API calls and speech-to-text.
- Speech-to-text must use the candidate's own free **AssemblyAI** account/credits, for transcription only.
- Do **not** use AssemblyAI's LLM Gateway.
- LLMs must run in the cloud through API calls; do not run an LLM locally.
- The brief recommends:
  - **Gemini 3.8** for perception and indexing, and nothing below it.
  - **Claude Opus 5.5** or **Gemini 4 Argon** for reasoning and assembly.
- The brief prohibits Claude Fable models, all OpenAI models (including Astra), and other top-tier models above the recommended ones.
- The supplied Google key has a **$90** cap; the Anthropic key has a **$75** cap. Both expire on **25 November 2026**. Use only the allocated keys and do not share them.
- Report input/output token usage and transcription minutes.
- Time every pipeline stage, including precomputation and inference.
- Record CPU, GPU, RAM and operating system in the report.

**Important:** Do not guess model identifiers. Verify the exact allowed model IDs against the assessment instructions / provider configuration before making calls. Keep model names configurable. The brief mentions model names, but the exact API identifiers may differ.

### 2.2 Absolute no-video-to-LLM rule

**Never send a video file, video clip, video stream or video input to any language model.**

The pipeline may send:
- Text.
- Audio, if needed and permitted.
- Individual still frames selected by the local pipeline.

The local pipeline decides which individual frames to send, how many, and when. This frame-selection strategy is explicitly part of the assessment.

Therefore:
- Extract and select still images locally.
- Send selected individual JPEG/PNG frames as image inputs, never a clip.
- Include timestamps and textual/audio evidence as context.
- If more visual context is needed, locally extract additional still frames and send only those.
- Do not use a model API feature that silently packages a video as video input.

### 2.3 Match integrity rules

- Do not use outside information about the Barcelona vs Real Madrid match.
- Do not consult match reports, live text commentary, statistics sites, highlight videos or other sources describing what happened in the match or when.
- The roster file is the only match-specific information allowed besides the footage.
- Results must come from the pipeline analyzing the footage.
- Do not hardcode timestamps, player names or answers.
- Test labels may be created to measure the system, but they must not become hardcoded answers.
- Every presented result must be traceable in run logs.
- Be able to explain every part of the code, including AI-generated code.

### 2.4 Deliverables and evaluation

Deliverables listed in the brief:
1. Private code repository shared with the named assessors; commit throughout the week.
2. Clean-start setup instructions.
3. Technical documentation.
4. Architecture diagram with stages and models.
5. Test coverage report.
6. Outputs: Tier 1 ranked search results, any optional-tier results attempted, rough cut and vertical version.
7. Run logs for every reported run.
8. Report using the assessment template.

The report should cover candidate/hours, hardware, architecture, tools/models and rationale, results by tier, test set, error analysis, token/performance usage, processing time, AI tool use, limitations and next steps.

The brief gives:
- Submission: **Monday, 23 November 2026, end of day GMT (UK time)**.
- Presentation: **Tuesday, 24 November 2026**, 45 minutes.
- Presentation includes a 15-minute walkthrough, 10 minutes of unseen live queries, and 20 minutes of Q&A.
- The match must already be indexed before the presentation; queries should return in seconds.

---

## 3. Inputs and high-level architecture

The system has three principal inputs:

1. **Full match video** with commentary audio.
2. **Roster CSV** containing both teams, players and jersey numbers.
3. **Creative brief** describing the desired highlight edit.

The roster is context for player/team identification. It must not be used to invent identities when the footage does not support them.

### Proposed architecture

```text
                    ┌──────────────────────┐
                    │ Match video + audio  │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │ 1. Ingestion         │
                    │ metadata, audio,     │
                    │ shots, windows,      │
                    │ representative frames│
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │ 2. Signal extraction │
                    │ audio features, ASR, │
                    │ OCR, visual signals │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │ 3. Event extraction  │
                    │ candidates +        │
                    │ evidence fusion      │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │ 4. Embeddings and    │
                    │ indexing             │
                    └──────────┬───────────┘
                               │
      Creative brief + roster  │
               │               │
       ┌───────▼────────┐      │
       │ 5a. Brief      │      │
       │ interpretation│      │
       └───────┬────────┘      │
               └───────┬───────┘
                       ▼
             ┌────────────────────┐
             │ 5b. Search and     │
             │ candidate ranking │
             └─────────┬──────────┘
                       ▼
             ┌────────────────────┐
             │ Human selects     │
             │ moments           │
             └─────────┬──────────┘
                       ▼
             ┌────────────────────┐
             │ 6. Goal-sequence   │
             │ boundaries /       │
             │ highlight planning│
             └─────────┬──────────┘
                       ▼
             ┌────────────────────┐
             │ Rough cut          │
             └─────────┬──────────┘
                       ▼
             ┌────────────────────┐
             │ Human approval     │
             └─────────┬──────────┘
                       ▼
             ┌────────────────────┐
             │ 7. Verticalization │
             │ local ball tracking│
             │ and rendering      │
             └─────────┬──────────┘
                       ▼
             ┌────────────────────┐
             │ Final 9:16 video   │
             └────────────────────┘
```

The pipeline is batch/offline for V1. The match is preprocessed and indexed once; brief interpretation and retrieval should then be fast.

### Data and artifact principles

- SQLite is the structured source of truth.
- Store video, audio, frames, crops and generated media as filesystem artifacts.
- Store paths, timestamps, confidence, provenance and relationships in SQLite.
- JSON exports are useful for debugging, but should not replace database records.
- Keep stages modular and independently rerunnable.
- Preserve raw observations separately from derived semantic events.
- Use idempotent inserts/upserts and cache expensive model outputs.
- Record model/provider/prompt version and timing for derived artifacts.
- Avoid stale records when a rerun produces fewer rows: upserts alone do not delete old rows. A stage-replacement or versioned-run strategy may be needed.

---

## 4. Core data concepts

Keep these concepts distinct:

- **Shot:** one continuous camera view between visual cuts. Shot detection is a required foundation, and search results should be grounded at shot level.
- **Window:** a smaller processing interval inside a shot, used when a shot is long. Windows must not cross shot boundaries.
- **Keyframe:** a representative still image associated with a window/shot and timestamp.
- **Raw signal / observation:** OCR output, audio peak, transcript segment, visual detection, etc.
- **Event candidate:** a possible goal, card, celebration, near miss, etc., derived from one or more signals.
- **Confirmed/validated event:** an event that has passed the project's evidence and confidence rules.
- **Highlight sequence:** a broader editorial unit, such as buildup + goal + celebration. It can span multiple shots and windows.
- **Creative brief:** a request describing one desired output. It belongs to a generation/edit request, not permanently to the match; the same match can support multiple briefs.
- **Candidate selection / edit plan:** a traceable record of which events were proposed, ranked, selected and assembled for a particular brief.

Keep original event timestamps and evidence intact. Editorial boundaries should be stored separately from canonical event records.

---

## 5. Current implementation status

This section summarizes what has been reported as implemented or tested in the project conversations. It is not a fresh inspection of the current local repository, so verify filenames, schemas and exact interfaces before integrating new code.

### 5.1 Ingestion and indexing — implemented

Reported modules:

```text
pipeline/ingestion/
    metadata.py
    audio.py
    shots.py
    windows.py
    keyframes.py
```

Implemented functionality:
- FFprobe metadata extraction: filename, file size, duration, video codec, resolution, FPS, pixel format, audio codec, sample rate, channels and stream counts.
- FFmpeg audio extraction to mono 16 kHz PCM WAV.
- PySceneDetect `ContentDetector`, threshold 27 and minimum scene length 15 frames.
- A full-match run produced 717 shots; the user inspected and approved the result.
- Windowing defaults: 5-second duration, 1-second overlap, split threshold 10 seconds.
  - A shot of 10 seconds or less remains one window.
  - Longer shots are split into overlapping 5-second windows.
  - Windows do not cross shot boundaries.
- Midpoint representative keyframe per window, max width 960 px, JPEG quality 85.
- Keyframe metadata includes keyframe ID, window ID, shot ID, timestamp and image path.

Database:
- `pipeline/database.py` exposes connection and initialization helpers.
- Foreign keys are enabled.
- Tables reported: `matches`, `shots`, `windows`, `keyframes`, `model_runs`, with indexes.
- Insertion functions include `insert_match`, `insert_shots`, `insert_windows`, `insert_keyframes`, `persist_ingestion`.
- Parameterized SQL, `executemany`, `ON CONFLICT` updates and transactions are used.
- User confirmed database insertion works.

Potential issue to revisit:
- Upserts do not automatically remove stale rows if a rerun produces fewer shots/windows/keyframes. Consider stage-run IDs or replacing the rows belonging to a specific ingestion run.

### 5.2 Signal extraction — implemented in part

Reported components:
- `pipeline/analysis/audio_features.py`
  - Librosa audio loading.
  - 2-second frames, 1-second hop.
  - RMS, zero-crossing rate and spectral centroid.
- Audio peak detection was discussed using a rolling z-score:
  - baseline around 60 frames,
  - threshold around 2.5,
  - minimum distance around 5 seconds,
  - merge nearby peaks.
  Confirm whether this exact method is implemented and validated.
- Scoreboard OCR uses EasyOCR, `gpu=True`, sampling full frames every 2 seconds.
- OCR works on the user's footage and scoreboard information was parsed.
- Scoreboard position can vary (top-left, bottom-middle or absent); do not hardcode one ROI.
- A generic scoreboard observation/parser is preferable to a parser that only searches for card text.
- Transcription was initially tested with faster-whisper on GPU; a full match took around 6 minutes. However, the assessment specifies AssemblyAI for speech-to-text. Do not treat Whisper as compliant unless the assessment owner explicitly approved an exception.
- The transcription table was discussed with segment ID, match ID, start/end time and text; confirm the actual schema.

Signal interpretation:
- An audio peak is generic evidence. It could be commentary, crowd reaction, whistle or another sound. Do not label every peak as a crowd roar or a goal.
- Commentary can lag behind the actual action and cannot be the only event detector.
- A score change is strong goal evidence. The actual goal time lies between the last observation of the old score and the first observation of the new score; preserve that uncertainty interval.
- Card notifications on the scoreboard are strong evidence when present, but not every broadcast displays them.
- Use commentary and visual signals as supporting evidence for cards and other events.

### 5.3 Event extraction — implemented in part

Reported separate modules:

```text
pipeline/
    scoreboard_events.py
    audio_events.py
    transcription_events.py
    extract_events.py
```

`extract_events.py` orchestrates the signal-specific event extraction modules.

A database verification run after initial event extraction reported:
- 124 events
- 124 evidence rows
- 34 crowd-reaction candidates
- 64 goal candidates
- 6 red-card candidates
- 17 yellow-card candidates
- 3 substitution candidates

Near-miss detection was added later, but no final count or quality result was supplied.

Important next improvement:
- Implement/verify an **event-fusion and validation stage** that groups related observations into event candidates, combines independent evidence, handles repeated notifications and preserves uncertainty/provenance.
- Do not assume the reported candidate counts are final true-event counts.
- Ensure evidence records remain linked to the candidate/event that they support.
- Make event extraction idempotent.

Event logic already discussed:
- Goals: scoreboard score change is strongest evidence; commentary phrases, visual celebration and audio can support it. Do not require a crowd roar; away-team goals must still be detectable.
- Cards: scoreboard card notification is strong when available; commentary and visual context support it.
- Near misses: keep distinct from goals; avoid treating a shot/save or close attempt as a goal.
- Replays: must not be included in the final edit. Basic replay classification should be introduced early; more sophisticated event-level replay deduplication can follow if time permits.
- Preserve all valid detected events in the index. Apply the search quotas at retrieval time, not during detection.

### 5.4 Embeddings and indexing — implemented

Reported implementation:
- `multimodal_embeddings` table.
- `embedding_usage` table.
- Text and image document builders.
- Shared content hashes for caching.
- Provider-neutral vector persistence.
- Cosine similarity utility.
- Usage, latency and cost tracking.
- Keyframe-to-event linking.
- `build_multimodal_documents.py` script.

Verified by user:
- Gemini `gemini-embedding-2` text embeddings: 3072 dimensions.
- Gemini `gemini-embedding-2` image embeddings: 3072 dimensions.
- Two text vectors and two image vectors persisted.
- Second run reused all four cached vectors and persisted none.

Important validation still required:
- Equal vector dimensions do **not** prove text and image embeddings share a compatible cross-modal semantic space.
- Test text-to-image retrieval with known examples from the actual match.
- Verify the model's documented multimodal behavior and compare retrieval results.
- Do not claim cross-modal retrieval works solely because both outputs have 3072 dimensions.

### 5.5 Semantic and hybrid retrieval — implemented

Reported functionality:
- Gemini `gemini-embedding-2` query embeddings.
- Cosine-similarity reranking.
- SQL filters applied first.
- FTS fallback.
- Hybrid candidate merging by event ID.
- Hybrid score combining semantic similarity, confidence and status.
- Evidence and keyframe context in results.
- CLI support with `search_events.py --semantic`.

One reported CLI result:
- Confirmed `0–1` goal event.
- Semantic score: `0.695956`.
- Hybrid score: `0.787169`.
- Evidence and three keyframes included.

Retrieval quality still needs testing with diverse prompts:
- goals by either team, including away-team goals;
- dangerous attacks;
- red cards and yellow cards;
- goalkeeper saves;
- final 10 minutes;
- player/team-specific queries if Tier 2 is attempted.

Check that:
- hard SQL filters cannot be overridden by semantic similarity;
- low-confidence or rejected events cannot rank above valid events accidentally;
- score components are normalized and weights are justified;
- FTS fallback works when embeddings are unavailable;
- retrieval returns fewer than the requested maximum if there are not enough valid events.

### 5.6 Roster and creative brief inputs — partially designed

The system has three inputs: match video, roster CSV and creative brief.

Suggested database concepts:
- `teams`
- `players`
- `creative_briefs`

A creative brief should be associated with a generation/edit request, not directly with the match. One match can be used for multiple creative briefs.

Example brief requirements discussed:
- target duration (e.g. 60 seconds);
- vertical 9:16 output;
- include all goals;
- include the best two near misses;
- include red cards;
- prioritize the winning team;
- end with the winning goal;
- energetic pacing;
- exclude replays.

The LLM should convert free text into validated structured JSON. It must not invent players, teams, events or identities. Roster data can resolve a detected jersey number to a player, but only when the visual evidence supports that number.

---

## 6. Brief interpretation, search and candidate selection

This is the bridge between the indexed match and the final edit. It is one of the most important remaining areas to complete and validate.

### 6.1 Brief interpretation

**Goal:** convert the natural-language creative brief into a validated, machine-readable set of editing/search requirements.

Proposed module area:

```text
pipeline/
    briefs/
        models.py
        claude_client.py
        service.py
    search/
        brief_schema.py
        brief_parser.py
```

A prior implementation archive was prepared for Step 1 (`creative_brief_step1.zip`), but integration into the user's current local repository has not been confirmed. Do not assume it is already integrated.

The intended brief parser should:
1. Accept the raw creative brief.
2. Add only relevant context, such as known team names and roster data.
3. Call the approved cloud reasoning model through its API.
4. Ask for structured JSON matching a strict schema.
5. Validate and normalize the output with Pydantic or equivalent.
6. Persist the raw brief and parsed representation.
7. Cache identical requests to avoid repeated API spend.
8. Record model name, prompt/schema version, token usage, latency and errors.

Potential structured fields:
- target duration;
- output aspect ratio/orientation;
- requested event categories;
- per-category counts or constraints;
- team/player priorities;
- ranking preferences (best, earliest, latest, all);
- narrative/order constraints (e.g. end with winning goal);
- include/exclude constraints (especially exclude replays);
- requested buildup/goal/celebration components;
- tone/pacing preferences if they affect selection/editing;
- unresolved or ambiguous instructions.

The schema should distinguish:
- what is explicitly requested;
- what is a reasonable normalized interpretation;
- what could not be resolved and needs a human decision.

Do not let the LLM silently invent a missing duration, event count or player identity. Use defaults only when deliberately defined in the application and record when a default was applied.

### 6.2 Candidate search and selection

**Goal:** use the parsed brief to retrieve relevant events from SQLite and rank them into a candidate list for the user.

Proposed modules:

```text
pipeline/search/
    candidate_selector.py
    highlight_planner.py
```

A previous Step 2 archive was prepared (`candidate_selection_step2.zip`). It contains a candidate selector, CLI, SQL addition and tests. However, it assumes specific interfaces and schemas that have not been verified against the user's actual current code. In particular, it assumes a `search_events()` signature and certain `scoreboard_observations`, `teams` and `creative_briefs` columns. Treat it as a draft, not a confirmed drop-in patch.

The intended candidate-selection flow:

1. Load the parsed creative brief by `brief_id`.
2. Determine the event categories and constraints requested.
3. Apply hard SQL filters first:
   - match ID;
   - event type;
   - event status/confidence eligibility;
   - replay exclusion;
   - team/player filters where supported;
   - time constraints where specified.
4. Retrieve candidates using existing hybrid search (semantic + FTS + event confidence/status).
5. Merge duplicate retrieval hits by canonical event ID.
6. Rank candidates according to the brief:
   - relevance to the requested category/query;
   - event confidence and evidence quality;
   - requested team/player priority;
   - requested temporal preference (best/latest/earliest/all);
   - any explicit narrative requirements.
7. Apply per-category retrieval limits.
8. Return grounded results with event IDs, timestamps, confidence, evidence and keyframe references.
9. Persist the selection run and its parameters/results for traceability.
10. Present the ranked results to the human for selection.

Current agreed retrieval quotas (these are retrieval limits, **not detection limits**):
- Top **5** goals.
- Top **10** red cards.
- Top **10** yellow cards.
- Top **20** near misses.

Detect and store all valid events. Apply these caps when retrieving candidates. If fewer valid events exist, return fewer; do not fabricate results.

The previous selector draft considered `confirmed` and `likely` statuses eligible. Verify the project's actual status taxonomy and decide explicitly whether `likely` belongs in user-facing results. Never allow rejected/uncertain events to appear as confirmed.

### 6.3 Winner/team priority

A brief may ask to prioritize the winning team or end with the winning goal.

This requires reliable score/team interpretation:
- Read score observations from the actual database.
- Resolve home/away team names using the supplied roster/team data.
- Determine the winner only if the score evidence is sufficient.
- If the match is tied or the score is ambiguous, represent that explicitly rather than guessing.
- Do not hardcode Barcelona/Real Madrid outcomes or player identities.

The earlier Step 2 draft assumed particular scoreboard and team table columns. Inspect the real schema before implementing winner resolution.

### 6.4 Human selection

The assessment explicitly requires a person to choose which moments to use.

A command-line interface is sufficient:
- display ranked candidate events with category, timestamps, confidence and short evidence summary;
- allow selecting candidate IDs;
- log the chosen IDs, order and user decision;
- allow an empty or partial selection where appropriate.

Do not treat the LLM's proposed list as the final human selection.

### 6.5 Highlight planning

After selection, build an edit plan that translates selected events into clip sequences.

For goals, the final sequence should normally include:
- buildup;
- goal action;
- celebration.

These are editorial boundaries, not necessarily the same as the goal event timestamp. Keep the canonical event timestamp unchanged and store the chosen sequence boundaries separately.

The planner should:
- respect the brief's duration and ordering constraints;
- avoid overlapping duplicate clips;
- exclude replay footage;
- avoid cutting off the buildup, shot or celebration;
- produce a traceable edit decision list (EDL) or equivalent structured plan;
- report when the requested duration cannot be satisfied without violating event requirements.

Do not force every event into a fixed duration. Determine boundaries from evidence and refine them.

---

## 7. Goal sequence extraction — Step 3 design

This step focuses on identifying the full editorial sequence around a goal: buildup + goal + celebration.

**Critical constraint:** no video or clip is sent to the LLM. Only selected still frames, text and permitted audio/transcription context may be sent.

### 7.1 Agreed design

The user suggested selecting frames that are visually different rather than sending a naive fixed sample. We agreed to use local visual diversity, combined with temporal coverage and event relevance.

The user also correctly noted that buildup often uses the same wide tactical camera. Therefore:
- Do not make shot diversity a main scoring term.
- Shot boundaries may still provide candidate timestamps/hints.
- A sequence of different football actions can occur within one visually similar wide shot.
- Do not confuse a camera cut with a new semantic event.

Football-state extraction (player positions, team clustering, pitch homography, tactical/spatial state) was discussed but explicitly postponed. Do not add it to the current implementation scope.

### 7.2 Proposed local frame-selection pipeline

```text
pipeline/
    goal_sequences/
        candidate_generation.py
        visual_features.py
        event_guided_sampling.py
        frame_selector.py
        gemini_analyzer.py
        sequence_extractor.py
```

Keep the implementation simpler if the deadline requires it; these are conceptual responsibilities, not a requirement to create every file.

#### A. Candidate frame generation — local

Generate candidate timestamps from:
- existing keyframes;
- goal event timestamp and uncertainty interval;
- scoreboard change observations;
- transcript segment timestamps around the event;
- audio event timestamps;
- shot boundaries as optional hints;
- additional locally extracted frames around relevant evidence.

Candidate generation should cover the context before and after the goal. An initial search window discussed was approximately 30 seconds before and 20 seconds after, but this is a starting context window, **not** a final clip boundary and should be configurable/expanded when evidence requires it.

Deduplicate timestamps and avoid extracting the same frame repeatedly.

#### B. Local visual embeddings/features

Compute visual representations locally. Candidate approaches discussed:
- DINOv2;
- CLIP;
- SigLIP.

Do not assume a model choice without benchmarking. Choose a model that fits local hardware and the 24 GB RAM limit. The user's laptop has an RTX 3070, but previous CV work encountered GPU memory pressure, so use batching and fall back to CPU if needed.

For each candidate frame, store:
- timestamp;
- image path;
- local feature/embedding or a reference to it;
- feature model/version;
- extraction metadata.

Do not send these local feature vectors to the cloud LLM unless there is a specific justified use; their primary purpose is local frame selection.

#### C. Greedy diversity-aware frame selection

Use a greedy selection strategy:
1. Start with the most event-relevant candidate frame.
2. Evaluate each remaining frame against the already selected frames.
3. Prefer frames that add new visual information.
4. Reward temporal coverage so selected frames do not all cluster around one instant.
5. Preserve event-critical frames even when they are visually similar to an already selected frame.

Conceptual score:

```text
selection_score(frame) =
    w_event * event_relevance(frame)
  + w_temporal * temporal_coverage_gain(frame)
  + w_novelty * visual_novelty(frame, selected_frames)
```

Where:
- `event_relevance` comes from nearby scoreboard/transcript/audio/event evidence.
- `temporal_coverage_gain` rewards coverage of different parts of the buildup, goal and celebration interval.
- `visual_novelty` rewards a frame that contributes information not already represented.

No shot-diversity term is included in the main score.

A simple novelty measure can use cosine similarity between local visual embeddings. High similarity to selected frames suggests redundancy, but embeddings can miss action differences, so never let novelty suppress a critical timestamp.

Start with a configurable budget around **15–20 frames** as an initial experiment, not a hard requirement. Evaluate whether the selected set captures the sequence and adjust based on results and API budget.

#### D. Gemini analysis — still images only

Send the approved perception model:
- selected individual still frames;
- each frame's timestamp;
- relevant transcript excerpts;
- timestamped audio-event metadata;
- scoreboard observations and their uncertainty;
- the goal candidate's evidence summary.

Do not send a video file, clip, stream or video input.

Ask the model for structured, timestamp-grounded analysis such as:
- likely buildup start;
- goal-action interval / goal moment;
- celebration start and end;
- evidence supporting each boundary;
- possible replay indicators;
- uncertain intervals;
- confidence or abstention status.

The model should not invent timestamps outside the supplied evidence range. Require structured JSON and validate it.

#### E. Adaptive refinement

If the model reports an uncertain boundary:
1. Identify the uncertain timestamp interval.
2. Extract additional still frames locally within that interval.
3. Apply local visual selection to avoid redundant frames.
4. Send only the new still images and relevant text/audio evidence.
5. Update the boundary estimate and retain the analysis history.

Cache requests by event ID, selected frame IDs/content hashes, prompt version and model ID. Avoid resending identical frames unnecessarily.

### 7.3 Boundary and replay logic

- Buildup start should be based on meaningful context, not a fixed number of seconds before the goal.
- Goal timestamp should remain grounded in event evidence.
- Celebration should begin when the goal reaction becomes visible/audible and end when the sequence naturally transitions away.
- Replays must not be used in the final edit.
- A replay may show the same goal again from another camera angle. It is not a second goal event.
- Distinguish the live action and replay using available local visual/text/audio evidence; use human review when uncertain.
- Store replay classification separately from canonical goal identity and sequence boundaries.
- If replay detection is uncertain, exclude the suspect segment from automatic final assembly or request human review.

---

## 8. Rough cut, approval and verticalization

### 8.1 Rough cut

After the user selects moments and the planner has boundaries:
- create an edit decision list with source in/out timestamps and ordering;
- render a rough cut locally with FFmpeg or another local tool;
- preserve source timing and event references;
- log the render parameters and output path.

The rough cut should be reviewed by a person. Log approval/rejection and any requested changes. A rejection should trigger another planning/rendering pass.

### 8.2 Verticalization — required

The assessment explicitly requires:
- convert the approved 16:9 cut to 9:16;
- track the ball as it moves;
- keep the ball in frame without jitter.

This is local computer vision and local rendering.

Suggested high-level approach:
1. Detect the ball locally on source frames.
2. Track detections temporally.
3. Smooth the crop-center trajectory to avoid jitter.
4. Convert the desired crop center into a 9:16 crop window.
5. Handle missed detections with interpolation/short-term prediction and sensible fallback.
6. Render the vertical version locally.
7. Evaluate ball visibility and crop stability on representative clips.

The brief says following the ball is enough; tracking every player/action is not required. No-action framing is bonus and should be deferred unless the required tracking is already reliable.

---

## 9. Usage, observability, tests and quality measurement

### 9.1 Run logging

Every run should record:
- run ID and stage;
- match ID / brief ID / event IDs as applicable;
- start/end time and elapsed duration;
- configuration and thresholds;
- model/provider/version;
- prompt/schema version for LLM calls;
- input/output token counts;
- transcription minutes;
- cache hits/misses;
- errors and retry information;
- output artifact paths;
- hardware/runtime details where useful.

Every reported result must be traceable to logs.

### 9.2 Cost control

- Use the allocated Google and Anthropic keys only.
- Keep cloud calls selective.
- Use local CV for visual extraction and frame selection.
- Do not call the LLM for every shot or every frame.
- Cache embeddings and LLM responses by stable content/request identifiers.
- Batch ambiguous event/frame analysis where appropriate.
- Track token usage and latency per call.
- Avoid duplicate API calls when a result is already cached.

### 9.3 Evaluation

Create a small manually labeled test set from the footage for evaluation only. Do not hardcode the labels into production logic.

Measure:
- shot detection quality;
- goal/card/celebration retrieval precision and recall;
- ranking quality (e.g. whether true requested moments appear at the top);
- replay false-positive rate;
- near-miss quality if attempted;
- goal sequence boundary error;
- vertical ball-in-frame rate;
- crop jitter;
- processing time by stage;
- token use and transcription minutes.

Perform error analysis by failure type, for example:
- missed event;
- false event;
- incorrect event type;
- duplicate/replay;
- timestamp offset;
- incorrect sequence boundary;
- poor search ranking;
- wrong team/player attribution;
- ball lost from vertical crop.

Accuracy and honest explanation of limitations matter more than claiming every feature works.

---

## 10. Remaining implementation roadmap

The order below is designed to finish a defensible end-to-end system. Reassess scope against remaining time; do not build optional features at the expense of the required workflow.

### Priority 0 — inspect and stabilize the actual repository

Before integrating prepared patches:
- inspect current directory tree;
- inspect actual SQLite schema;
- inspect current `search_events.py` function signature and return structure;
- inspect `creative_briefs` and roster tables, if present;
- inspect event statuses and event/evidence relationships;
- identify which earlier Step 1 and Step 2 archive files are already integrated;
- run existing tests and a small end-to-end smoke test.

Do not rely on guessed table columns or function signatures.

### Priority 1 — complete the required retrieval workflow

1. Confirm the creative brief parser is integrated and works against the actual schema.
2. Validate its structured output and default behavior.
3. Confirm roster loading and team/player references.
4. Adapt candidate selection to the actual `search_events()` API.
5. Apply hard SQL filters before semantic ranking.
6. Apply the retrieval quotas at query time.
7. Verify replay exclusion and event status eligibility.
8. Persist selection runs and results.
9. Add a CLI to display ranked results.
10. Add the mandatory human selection prompt and audit log.

### Priority 2 — complete goal sequence planning

1. Inspect the actual event/evidence/keyframe schemas.
2. Implement local candidate timestamp generation.
3. Implement local visual features/embeddings for candidate frames.
4. Implement diversity + temporal coverage + event relevance selection.
5. Send selected still images and textual/audio context to the approved Gemini API only.
6. Validate structured boundary output.
7. Add adaptive frame refinement for uncertain boundaries.
8. Persist sequence boundaries and replay decisions separately from canonical events.
9. Test on multiple goal candidates, including an away-team goal if present.

### Priority 3 — rough cut and human approval

1. Generate an EDL from selected events and refined boundaries.
2. Render a rough cut locally.
3. Add a human approval/rejection CLI step.
4. Log decisions and support rerendering after rejection.

### Priority 4 — required verticalization

1. Choose/test a local ball detector suitable for the user's hardware.
2. Track the ball through approved rough-cut segments.
3. Smooth crop motion and handle missed detections.
4. Render 9:16 output.
5. Evaluate ball visibility and jitter.

### Priority 5 — polish and submission

- Add/finish tests for each stage.
- Run clean-start setup on a fresh environment if possible.
- Generate architecture diagram and technical documentation.
- Produce ranked Tier 1 results, rough cut and vertical video.
- Save logs and usage metrics.
- Complete report with measured results and limitations.
- Ensure the repository is committed throughout, private and accessible to assessors.
- Prepare unseen live-query demonstration; indexing must already be complete.

### Optional work only if the required pipeline is stable

- Improve near-miss and foul detection.
- Player jersey-number recognition and roster matching.
- Team identification from kit colors.
- More advanced replay deduplication.
- No-action framing.
- More advanced football-state extraction.

Football-state extraction (player positions, team clustering, pitch homography and tactical state) was explicitly deferred in the discussion and should remain out of the immediate plan.

---

## 11. Earlier implementation archives and integration cautions

Two code archives were prepared in earlier project work:

### Step 1 — creative brief parser

Previously prepared as `creative_brief_step1.zip`.

Intended contents included:
- Pydantic brief schema;
- Anthropic client wrapper;
- parsing/persistence service;
- CLI;
- schema additions for `creative_briefs` and `llm_usage`;
- tests for schema and SQLite behavior.

The archive was not confirmed as integrated into the current local repository. Check before copying files or applying SQL.

### Step 2 — candidate selection

Previously prepared as `candidate_selection_step2.zip`.

Intended contents included:
- `pipeline/selection/candidate_selector.py`;
- `select_candidates.py`;
- SQL additions for selection audit tables;
- tests and README.

It was built against assumed interfaces and schema names. In particular, it assumed a specific `search_events()` signature and scoreboard/team columns. It passed isolated tests and a stubbed smoke test, but it was not verified against the user's actual local database or live Gemini API. Treat it as a starting draft that must be adapted, not as an integrated/validated implementation.

No claim is made here that either archive has been merged into the repository or pushed to GitHub.

---

## 12. Decisions and scope boundaries agreed so far

- Build a batch/offline pipeline first.
- Prioritize precision over broad but unreliable event detection.
- Keep all valid event detections; apply quotas only during retrieval.
- Search should combine visual and audio-derived evidence; commentary alone is insufficient.
- Do not require crowd roar for a goal.
- Treat audio peaks as generic evidence, not automatically crowd reactions.
- Use SQLite as source of truth; filesystem for media/artifacts.
- Keep raw observations separate from derived events.
- Use one approved cloud reasoning model for brief interpretation/planning and one approved cloud perception model for selected-frame analysis, plus the embedding model. Avoid adding more LLMs.
- Local CV only; LLM API calls in cloud.
- No video input to any LLM, ever.
- Select individual still frames locally using event relevance, temporal coverage and visual novelty.
- Do not include shot diversity as a main frame-selection score because buildup often stays on one wide camera.
- Do not implement football-state extraction yet.
- Goals should include buildup + goal + celebration.
- Replays must be excluded from the final edit.
- Human selection and rough-cut approval are mandatory.
- Keep player identity/team recognition optional unless required stages are stable.
- Avoid overengineering; finish a working, explainable end-to-end system.

---

## 13. Key open questions to resolve from the actual code

1. What are the exact current SQLite table definitions and foreign-key relationships?
2. Is the Step 1 brief parser already integrated? What is its actual schema and CLI?
3. What is the real `search_events()` signature and return format?
4. What event status values are actually used (`confirmed`, `likely`, `uncertain`, etc.)?
5. How are replay labels represented, if at all?
6. Are event evidence and keyframes returned together by the current search API?
7. Does the embedding provider support a compatible text/image embedding space, and does cross-modal retrieval work empirically?
8. Are the scoreboard observations stored with score, timestamp, confidence and team-side information?
9. Which exact approved Gemini and Claude API model IDs are available in the allocated accounts?
10. Has AssemblyAI transcription replaced the earlier Whisper experiment, or is explicit approval for Whisper documented?
11. What local ball detector/tracker can run reliably within the available hardware limits?

These should be answered by inspecting the current repository, database and provider configuration—not by guessing.

---

## 14. Suggested final demo flow

A concise, reliable demonstration could be:

1. Show that the match has already been ingested, split into shots and indexed.
2. Load a creative brief and show its validated structured interpretation.
3. Run a natural-language/category search and show ranked results with timestamps, evidence and confidence.
4. Select moments manually and show the selection audit record.
5. Show one goal sequence with buildup, goal and celebration boundaries, explaining how locally selected still frames were sent to the cloud model.
6. Show that no video was sent to the LLM.
7. Render and play the rough cut.
8. Approve it through the human gate.
9. Render and play the 9:16 version, demonstrating ball tracking and crop stability.
10. Show run logs, stage timings, token/transcription usage and known limitations.

The match must already be indexed before the presentation. Prepare several unseen natural-language queries and run them live against the existing index.

---

## 15. Final principle

A smaller pipeline that is measurable, traceable and honest about uncertainty is stronger than a large collection of partially working models.

The immediate goal is not to build a complete football-understanding system. It is to deliver the required retrieval → human selection → rough cut → human approval → verticalization workflow, with a clear explanation of how the local CV, evidence fusion, embeddings and carefully controlled cloud LLM calls contribute to it.
