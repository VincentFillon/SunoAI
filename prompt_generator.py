import os
import sys
import time
import json
import re
import datetime
from dotenv import load_dotenv
from google import genai

# ============================================================
# CONFIGURATION
# ============================================================

GEMINI_MODEL    = "gemini-2.5-flash"   # ou gemini-2.5-pro pour plus de qualité
API_RETRY_COUNT = 3
API_RETRY_DELAY = 2                    # secondes, exponentiel (2s, 4s)
OUTPUTS_DIR     = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")

# ============================================================
# INIT
# ============================================================

load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    print("GEMINI_API_KEY not found in environment or .env file.")
    sys.exit(1)

client = genai.Client(api_key=API_KEY)

REQUIRED_ANALYSIS_FIELDS = [
    "VOCAL_PRESENCE", "VOCAL_DELIVERY", "SONG_STRUCTURE",
    "RHYME_PATTERN", "LYRICAL_TONE", "SONIC_IDENTITY", "LANGUAGE", "QUESTIONS"
]
VALID_VOCAL_PRESENCE = {"NONE", "MINIMAL", "MODERATE", "FULL"}

# ============================================================
# DISPLAY HELPERS
# ============================================================

def print_header(text):
    width = 62
    print("\n" + "=" * width)
    print("  " + text)
    print("=" * width)

def print_section(label, content):
    print(f"\n  {label}")
    print(f"  {content}")

def print_status(text):
    print(f"\n  > {text}")

def print_analysis(session):
    print_header("ANALYSE DU STYLE")
    labels = [
        ("Vocal presence",  session["vocal_presence"]),
        ("Vocal delivery",  session["vocal_delivery"]),
        ("Song structure",  session["song_structure"]),
        ("Rhyme pattern",   session["rhyme_pattern"]),
        ("Lyrical tone",    session["lyrical_tone"]),
        ("Sonic identity",  session["sonic_identity"]),
        ("Language",        session["detected_language"]),
    ]
    for label, value in labels:
        if value and value.lower() not in ("n/a", ""):
            print(f"  {label:<18}: {value}")

def display_result(session):
    print_header(f"GÉNÉRATION #{session['generation_count']}")
    print(f"\nTITLE\n{session['title']}\n")
    print(f"STYLE\n{session['style_prompt']}\n")
    print(f"LYRICS\n{session['lyrics']}")
    print()

# ============================================================
# GEMINI WRAPPER
# ============================================================

def call_gemini_with_retry(prompt, label="API"):
    for attempt in range(1, API_RETRY_COUNT + 1):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt
            )
            text = (response.text or "").strip()
            if not text:
                raise ValueError("Empty response from API")
            return text
        except Exception as e:
            if attempt < API_RETRY_COUNT:
                wait = API_RETRY_DELAY ** attempt
                print(f"  [{label}] Tentative {attempt} échouée: {e}. Retry dans {wait}s...")
                time.sleep(wait)
            else:
                raise RuntimeError(f"[{label}] Échec après {API_RETRY_COUNT} tentatives: {e}")

# ============================================================
# PARSERS
# ============================================================

def parse_analysis(text):
    result = {}
    # Strip any residual markdown bold markers
    cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    for field in REQUIRED_ANALYSIS_FIELDS:
        value = ""
        for line in cleaned.splitlines():
            line_stripped = line.strip()
            if line_stripped.upper().startswith(field + ":"):
                value = line_stripped[len(field) + 1:].strip()
                break
        result[field] = value

    missing = [f for f in REQUIRED_ANALYSIS_FIELDS if not result[f]]
    if missing:
        raise ValueError(f"Champs manquants dans l'analyse: {missing}")

    vp = result["VOCAL_PRESENCE"].upper().split()[0]  # handle "FULL - ..." etc.
    if vp not in VALID_VOCAL_PRESENCE:
        raise ValueError(f"VOCAL_PRESENCE invalide: '{vp}'. Attendu: {VALID_VOCAL_PRESENCE}")
    result["VOCAL_PRESENCE"] = vp

    return result


def parse_composition(text):
    """
    Extracts TITLE, STYLE, LYRICS sections from composition output.
    Uses a line-by-line state machine.
    """
    sections = {"TITLE": [], "STYLE": [], "LYRICS": []}
    current = None
    markers = {"TITLE", "STYLE", "LYRICS"}

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.upper() in markers:
            current = stripped.upper()
        elif current:
            sections[current].append(line)

    result = {k: "\n".join(v).strip() for k, v in sections.items()}
    missing = [k for k, v in result.items() if not v]
    if missing:
        raise ValueError(f"Sections manquantes dans la composition: {missing}")

    return result["TITLE"], result["STYLE"], result["LYRICS"]

# ============================================================
# SESSION
# ============================================================

def init_session():
    session_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return {
        "id": session_id,
        "style": "",
        "artist": "",
        "reference": "",
        # Phase 1
        "vocal_presence": "",
        "vocal_delivery": "",
        "song_structure": "",
        "rhyme_pattern": "",
        "lyrical_tone": "",
        "sonic_identity": "",
        "detected_language": "",
        "questions_raw": "",
        # Phase 2
        "lyrics_language": "",
        "answers": [],
        # Output
        "title": "",
        "style_prompt": "",
        "lyrics": "",
        "generation_count": 0,
    }


def get_user_reference(session):
    style  = input("\nStyle musical désiré (optionnel) : ").strip()
    artist = input("Artiste de référence (optionnel) : ").strip()

    if not style and not artist:
        print("Vous devez fournir au moins un style ou un artiste.")
        sys.exit(1)

    session["style"]  = style
    session["artist"] = artist

    if style and artist:
        session["reference"] = f"Musical style: {style}. Reference artist: {artist}."
    elif style:
        session["reference"] = f"Musical style: {style}."
    else:
        session["reference"] = f"Reference artist: {artist}."

# ============================================================
# PHASE 1 — STYLE ANALYSIS
# ============================================================

ANALYSIS_PROMPT_TEMPLATE = """\
Return PLAIN TEXT ONLY — no markdown, no bold, no asterisks, no backticks.
Each field on its own line. No blank lines between fields.

You are an expert musicologist specialized in music production and song structure.

{reference}

Analyze this style/artist and return a structured analysis using EXACTLY this format (no extra text, no explanations):

VOCAL_PRESENCE: <NONE|MINIMAL|MODERATE|FULL>
VOCAL_DELIVERY: <description of how vocals are delivered, or "n/a" if NONE>
SONG_STRUCTURE: <description of the typical song structure for this style/artist>
RHYME_PATTERN: <typical rhyme scheme, or "n/a" if NONE or MINIMAL>
LYRICAL_TONE: <tone and vocabulary style, or "n/a" if NONE or MINIMAL>
SONIC_IDENTITY: <key production elements, tempo feel, instruments, atmosphere>
LANGUAGE: <the natural language for lyrics in this style/artist, e.g. "English", "Spanish", "French", "Portuguese", "Japanese", or "instrumental" if NONE>
QUESTIONS: <2 to 3 personalization questions specific to this exact style/artist, separated by " | ">

VOCAL_PRESENCE scale:
- NONE: purely instrumental (techno, EDM, ambient, most electronic genres, classical, jazz instrumental)
- MINIMAL: a single repeated hook, a sampled phrase, or a brief spoken element only (house, electro swing, some lo-fi)
- MODERATE: vocals present but not dominant, alternating with long instrumental sections (trip-hop, post-rock, some indie)
- FULL: vocals are the main focus throughout (pop, rap, metal, singer-songwriter, R&B)

QUESTIONS guidelines:
- Ask only what is genuinely relevant to THIS style/artist — do not use generic questions
- For purely instrumental styles: ask about mood, energy arc, or specific sonic texture
- For vocal styles: ask about lyrical theme/subject, emotional angle, or specific imagery
- Questions should help personalize the composition, not just describe the genre
- Each question should be short, concrete, and optionally suggest example answers in parentheses
- Example for techno: "Energy arc of the track? (relentless peak-time / slow hypnotic build / late-night minimal)"
- Example for rap: "What should the track be about? (e.g. a personal story, a flex, a social commentary)"
{correction}"""


def run_phase1_analysis(session):
    print_status("Analyse du style en cours...")
    correction = ""
    last_error = None

    for attempt in range(1, API_RETRY_COUNT + 1):
        prompt = ANALYSIS_PROMPT_TEMPLATE.format(
            reference=session["reference"],
            correction=correction
        )
        try:
            text = call_gemini_with_retry(prompt, label="Phase 1")
            parsed = parse_analysis(text)
            # Store results
            session["vocal_presence"]   = parsed["VOCAL_PRESENCE"]
            session["vocal_delivery"]   = parsed["VOCAL_DELIVERY"]
            session["song_structure"]   = parsed["SONG_STRUCTURE"]
            session["rhyme_pattern"]    = parsed["RHYME_PATTERN"]
            session["lyrical_tone"]     = parsed["LYRICAL_TONE"]
            session["sonic_identity"]   = parsed["SONIC_IDENTITY"]
            session["detected_language"] = parsed["LANGUAGE"] or "English"
            session["questions_raw"]    = parsed["QUESTIONS"]
            return
        except (ValueError, RuntimeError) as e:
            last_error = e
            if attempt < API_RETRY_COUNT:
                correction = f"\n\nATTENTION: Ta réponse précédente était mal formée ({e}). Respecte EXACTEMENT le format demandé."
                print(f"  [Phase 1] Reformatage requis, tentative {attempt + 1}...")
            else:
                print(f"\nErreur fatale Phase 1: {last_error}")
                sys.exit(1)

# ============================================================
# LANGUAGE CONFIRMATION
# ============================================================

def confirm_language(session):
    vp = session["vocal_presence"]
    lang = session["detected_language"]

    if vp == "NONE" or lang.lower() == "instrumental":
        session["lyrics_language"] = "instrumental"
    else:
        print(f"\n  Langue détectée pour les paroles : {lang}")
        override = input(f"  Langue à utiliser (Entrée pour garder '{lang}') : ").strip()
        session["lyrics_language"] = override if override else lang

# ============================================================
# PHASE 2 — QUESTIONS
# ============================================================

def run_phase2_questions(session, tweak_mode=False):
    questions_raw = session["questions_raw"]
    questions = [q.strip() for q in questions_raw.split("|") if q.strip()] if questions_raw else []

    if not questions:
        if session["vocal_presence"] in ("NONE", "MINIMAL"):
            questions = ["Mood ou atmosphère du track ?"]
        else:
            questions = ["Thème ou sujet de la chanson ?"]

    print()
    new_answers = []
    for i, question in enumerate(questions):
        # In tweak mode, show previous answer as default
        prev = session["answers"][i][1] if tweak_mode and i < len(session["answers"]) else ""
        if tweak_mode and prev:
            answer = input(f"  {question}\n  [précédent: {prev}] (Entrée pour garder) : ").strip()
            new_answers.append((question, answer if answer else prev))
        else:
            answer = input(f"  {question} (optionnel, Entrée pour ignorer) : ").strip()
            new_answers.append((question, answer))

    session["answers"] = new_answers

# ============================================================
# PHASE 3 — COMPOSITION
# ============================================================

COMPOSITION_PROMPT_TEMPLATE = """\
You are a professional songwriter and music producer specialized in creating songs optimized for Suno AI.

--- REFERENCE ---
{reference}

--- STYLE ANALYSIS ---
Vocal presence: {vocal_presence}
Vocal delivery: {vocal_delivery}
Typical song structure: {song_structure}
Rhyme pattern: {rhyme_pattern}
Lyrical tone: {lyrical_tone}
Sonic identity: {sonic_identity}
Lyrics language: {lyrics_language}

--- USER DIRECTION ---
{user_context}
{previous_gen_hint}
---

Your task: compose a complete Suno-ready song that authentically reproduces the style/artist above.

Rules:

1. The output must contain EXACTLY three sections in this order, each label on its own line:
TITLE
STYLE
LYRICS

2. STYLE section — write ONE optimized style prompt for Suno AI:
   - Start with the subgenre and named production era/artist if relevant
   - Name key sonic signatures (e.g. "harmonized guitars", "808 bass", "four-on-the-floor kick")
   - Specify vocal texture precisely (e.g. "gritty male vocals alternating clean and screamed")
   - Include one energy or mood descriptor ("dark and cinematic", "euphoric and driving")
   - End with tempo feel if important ("mid-tempo groove", "relentless 180BPM")
   - Target 25-45 words — dense, comma-separated descriptors, no filler words like "with" or "featuring"
   - NO full sentences. Descriptors only.

3. LYRICS section — follow the vocal presence level strictly:

IF NONE: Write ONLY bracketed musical structure instructions (no sung/rapped text).
  Focus on arrangement, energy, transitions. Example: [Intro - sparse kick and bass], [Build - layered synths rising], [Drop - full beat], [Breakdown - pads only], [Outro - fade]

IF MINIMAL: Write only the one hook/phrase this style uses. Fill the rest with bracketed musical structure instructions.
  Do NOT add verses or choruses that don't belong.

IF MODERATE: Write vocal sections only where they naturally occur. Use bracketed instructions for instrumental-dominant sections.

IF FULL: Write complete lyrics. Use the authentic structure for this style — do NOT default to generic Verse/Chorus/Bridge unless that is genuinely how this style works.

Vocal delivery (when vocals present):
- Rapping: respect flow, breath breaks, syllable density
- Screaming/metal: raw, intense phrasing
- Spoken word: natural speech rhythm
- Mixed: annotate per section (e.g. [Verse - rapped], [Chorus - sung])

Lyrical authenticity (when lyrics present):
- Write ALL lyrics strictly in the specified lyrics language — no exceptions, no mixing languages unless the user explicitly requested it
- Match the vocabulary, imagery, and tone from the analysis
- Apply the identified rhyme scheme (or lack thereof)
- Write like the artist would write

Suno compatibility — STRICTLY FORBIDDEN:
- Ellipses mid-line (...)
- Em-dashes (—) inside lyric lines
- Parenthetical stage directions inside lyric lines (use square brackets instead)
- Generic section labels alone: NEVER write just [Verse 1] or [Chorus] — always annotate: [Verse 1 - sung, building], [Chorus - anthemic, full band]
- Lines longer than 12 words

Output rules:
Return ONLY the final result. No explanations, no comments, no extra formatting.

The format MUST be exactly:

TITLE
(title)

STYLE
(style description)

LYRICS
(lyrics and/or musical structure instructions with bracketed labels)"""


def run_composition(session):
    context_lines = [
        f"{q} -> {a}" for q, a in session["answers"] if a
    ]
    user_context = "\n".join(context_lines) if context_lines else "No additional direction — use your best judgment."

    previous_gen_hint = ""
    if session["generation_count"] > 0:
        previous_gen_hint = f"""
--- PREVIOUS GENERATION (for reference — DO NOT repeat) ---
Previous title: {session['title']}
Generate something MEANINGFULLY DIFFERENT — different title, different angle on the theme, different imagery.
"""

    prompt = COMPOSITION_PROMPT_TEMPLATE.format(
        reference=session["reference"],
        vocal_presence=session["vocal_presence"],
        vocal_delivery=session["vocal_delivery"],
        song_structure=session["song_structure"],
        rhyme_pattern=session["rhyme_pattern"],
        lyrical_tone=session["lyrical_tone"],
        sonic_identity=session["sonic_identity"],
        lyrics_language=session["lyrics_language"],
        user_context=user_context,
        previous_gen_hint=previous_gen_hint,
    )

    print_status("Génération de la chanson...")
    correction = ""

    for attempt in range(1, API_RETRY_COUNT + 1):
        full_prompt = prompt + correction
        try:
            text = call_gemini_with_retry(full_prompt, label="Phase 3")
            title, style_prompt, lyrics = parse_composition(text)
            session["title"]        = title
            session["style_prompt"] = style_prompt
            session["lyrics"]       = lyrics
            session["generation_count"] += 1
            return
        except (ValueError, RuntimeError) as e:
            if attempt < API_RETRY_COUNT:
                correction = f"\n\nATTENTION: Ta réponse précédente était mal formée ({e}). Respecte EXACTEMENT le format avec les trois sections TITLE / STYLE / LYRICS chacune sur sa propre ligne."
                print(f"  [Phase 3] Reformatage requis, tentative {attempt + 1}...")
            else:
                print(f"\nErreur fatale Phase 3: {e}")
                sys.exit(1)

# ============================================================
# SAVE
# ============================================================

def save_session(session):
    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    filepath = os.path.join(OUTPUTS_DIR, f"{session['id']}.md")

    # Session metadata comment (machine-readable, at top of file on first write)
    meta = {
        "id": session["id"],
        "style": session["style"],
        "artist": session["artist"],
        "vocal_presence": session["vocal_presence"],
        "lyrics_language": session["lyrics_language"],
        "answers": session["answers"],
    }

    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ref_parts = []
    if session["style"]:
        ref_parts.append(session["style"])
    if session["artist"]:
        ref_parts.append(session["artist"])
    ref_display = " / ".join(ref_parts)

    answers_md = "\n".join(
        f"- {q} -> {a}" for q, a in session["answers"] if a
    ) or "- (aucune réponse fournie)"

    block = f"""
---

## Generation #{session['generation_count']} — {ts}

**Reference:** {ref_display}
**Language:** {session['lyrics_language']}

### User Answers
{answers_md}

### TITLE
{session['title']}

### STYLE
{session['style_prompt']}

### LYRICS
{session['lyrics']}

*Model: {GEMINI_MODEL}*
"""

    # Write metadata header only on first generation
    if not os.path.exists(filepath):
        header = f"<!-- session_data: {json.dumps(meta, ensure_ascii=False)} -->\n\n# Suno Generation — {session['id']}\n"
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(header)

    with open(filepath, "a", encoding="utf-8") as f:
        f.write(block)

    return filepath

# ============================================================
# POST-GENERATION LOOP
# ============================================================

def post_generation_loop(session):
    while True:
        print_header("QUE FAIRE ?")
        print("  [R]  Régénérer     — mêmes inputs, nouvelle composition")
        print("  [T]  Tweaker       — modifier les réponses, régénérer (Phase 1 ignorée)")
        print("  [Q]  Quitter")
        choice = input("\n  > ").strip().upper()

        if choice == "R":
            run_composition(session)
            display_result(session)
            filepath = save_session(session)
            print(f"  Sauvegardé : {filepath}")

        elif choice == "T":
            print_header("TWEAK — Modifie tes réponses")
            run_phase2_questions(session, tweak_mode=True)
            run_composition(session)
            display_result(session)
            filepath = save_session(session)
            print(f"  Sauvegardé : {filepath}")

        elif choice == "Q":
            print("\n  Au revoir !\n")
            break

        else:
            print("  Choix non reconnu. Utilise R, T ou Q.")

# ============================================================
# MAIN
# ============================================================

def main():
    session = init_session()

    # --- Input ---
    get_user_reference(session)

    # --- Phase 1 ---
    run_phase1_analysis(session)
    print_analysis(session)

    # --- Language ---
    confirm_language(session)

    # --- Questions ---
    print_header("PERSONNALISATION")
    run_phase2_questions(session)

    # --- Composition ---
    run_composition(session)

    # --- Display ---
    display_result(session)

    # --- Auto-save ---
    filepath = save_session(session)
    print(f"  Sauvegardé : {filepath}")

    # --- Loop ---
    post_generation_loop(session)


if __name__ == "__main__":
    main()
