"""
prompts.py — Prompt templates and reference data for the Suno generator.

All long-form LLM templates live here, separated from the orchestration in core.py.
This makes templates easier to A/B-test and keeps core.py focused on logic.

Templates:
    PHASE0_TEMPLATE        Pre-clarification (vague intent → missing axes)
    PHASE1_ANALYSIS        Style analysis (JSON output)
    PHASE3A_STYLE          Title + style descriptor (JSON output)
    PHASE3B_LYRICS         Lyrics with rich brackets (JSON output)
    COMPOSITION_SYSTEM     System prompt shared by Phase 3A/3B

Reference data:
    FEW_SHOTS              {(vocal_presence, genre_family): list[example_dict]}
    SUNO_BRACKETS_TABLE    Canonical meta-tag vocabulary injected in Phase 3B
    LYRICS_CLICHES         Banned phrases scanned during validation
    STOPWORDS_BY_LANG      Language detection helper for validation
    CANONICAL_SECTIONS     Section-name normalization map (FR↔EN)
"""

from __future__ import annotations


# ============================================================
# SYSTEM PROMPT (composition phases)
# ============================================================

COMPOSITION_SYSTEM = """\
You are a professional songwriter and music producer specializing in Suno AI prompt engineering.
Your outputs are fed directly into Suno AI — every word you write becomes literal instruction to the music model.
You write complete, production-ready songs with precise bracket instructions.

Strict rules at all times:
- Never include any artist names, band names, or song titles anywhere in your output.
  Suno's moderation strips them and corrupts the result. Translate any artist reference into its sonic DNA
  (e.g. "Nirvana-style" → "loud-quiet-loud dynamics, distorted grunge guitar, raw male vocals").
- Never use filler words ("with", "featuring", "various", "etc.").
- Never use generic imagery clichés ("broken wings", "tears in my eyes", "set me free", "neon lights",
  "endless night", "shadows fall", "rise and fall", "fade away").
- Never use ellipses (...) or em-dashes (—) inside lyric lines.
- Always think in terms of Suno's rendering engine: brackets control instrumentation,
  sections control energy arcs, word choice controls emotion.
- Produce exactly what is asked — no commentary, no alternatives, no meta-text.
- When the response format is JSON, return ONLY the JSON object — no markdown fences, no commentary."""


# ============================================================
# PHASE 0 — PRE-CLARIFICATION
# ============================================================

PHASE0_TEMPLATE = """\
The user described what they want to create:
---
{user_intent}
---

Quickly assess whether this description is rich enough to write a Suno song from.
A "rich" description names at least: a genre/subgenre, an instrument or vocal cue, and a mood or era.

Return a JSON object with this exact shape:
{{
  "is_vague": true | false,
  "missing_axes": [],
  "best_guess_filling": {{}}
}}

Allowed missing_axes values (include only what is genuinely absent):
  "genre", "mood", "era", "instrumentation", "vocal_style", "language"

best_guess_filling is a dict mapping any of the above axes to a single concise best guess
(2-5 words max), even when is_vague is false — this seeds Phase 1.

Return ONLY the JSON object."""


# ============================================================
# PHASE 1 — STYLE ANALYSIS (JSON output)
# ============================================================

PHASE1_ANALYSIS = """\
You are an expert musicologist specialized in music production and Suno AI prompt engineering.

The user described what they want to create:
---
{user_intent}
---

{phase0_hint}

Analyze the description and return a JSON object with this exact shape:

{{
  "intent": {{
    "mood": "",                    /* short evocative phrase, e.g. "wistful and resolute" */
    "energy": "low|medium|peak|dynamic",
    "era": "",                     /* e.g. "early 2000s", "late 70s", "contemporary" */
    "instrumentation": [],         /* 4-8 specific items, e.g. "fingerpicked acoustic guitar" */
    "vocal_style": "",             /* e.g. "raspy male baritone with vibrato", or "instrumental" */
    "language": ""                 /* English, French, Spanish, Portuguese, Japanese, instrumental, etc. */
  }},
  "vocal_presence": "NONE|MINIMAL|MODERATE|FULL",
  "vocal_delivery": "",            /* precise: "breathy falsetto alternating with chest belt", not "smooth" */
  "song_structure": [],            /* ordered list of section names, e.g. ["Intro","Verse","Chorus","Verse","Chorus","Bridge","Chorus","Outro"] */
  "rhyme_pattern": "AABB|ABAB|ABBA|free|n/a",
  "lyrical_tone": "",              /* tone and vocabulary, e.g. "introspective and concrete" — "n/a" if NONE/MINIMAL */
  "sonic_identity": [],            /* 6-12 Suno-compatible production tags, see rules below */
  "detected_language": "",         /* same as intent.language */
  "questions": [
    {{
      "id": "theme",
      "type": "single|multi|free",
      "prompt": "",                /* French, ends with "?" */
      "options": [],               /* 3-5 concise options, empty list if type=free */
      "impact": "theme|imagery|energy_arc|vocal_register|language_switch|section_focus"
    }}
  ]
}}

VOCAL_PRESENCE scale:
- NONE: purely instrumental (techno, EDM, ambient, classical, jazz instrumental)
- MINIMAL: a single repeated hook, a sampled phrase, or a brief spoken element only
- MODERATE: vocals present but not dominant, long instrumental sections
- FULL: vocals are the main focus throughout (pop, rap, metal, singer-songwriter, R&B)

SONIC_IDENTITY guidelines:
- 6-12 specific tags, NOT vague single words.
- Good: "down-tuned palm-muted power chords", "snapping snare with gated reverb", "gang vocal hooks"
- Bad: "guitar", "energetic", "atmospheric"
- Include tempo/BPM when characteristic ("relentless 200BPM tremolo picking", "mid-tempo 90BPM groove").
- Include spatial character ("cavernous hall reverb", "dry intimate close-mic'd", "lo-fi tape warmth").

QUESTIONS guidelines:
- All prompts in French — mandatory.
- Maximum 3 questions. Skip any question whose answer is already in the description.
- Each question's impact MUST be one of: theme, imagery, energy_arc, vocal_register, language_switch, section_focus.
- Drop questions you cannot tie to a specific Phase 3 axis.
- For type="single" or "multi", provide 3-5 short concrete options the user can pick.
- For type="free", omit options (empty list).
- Prefer concrete questions: "De quoi parle le premier couplet ?" not "Quel est le thème ?".
- Examples:
  Techno (NONE): {{ "id":"arc", "type":"single", "prompt":"Quel arc énergétique ?",
                  "options":["montée hypnotique","peak-time sans relâche","minimal nocturne"], "impact":"energy_arc" }}
  Rap (FULL):   {{ "id":"sujet", "type":"single", "prompt":"De quoi parle le morceau ?",
                  "options":["histoire personnelle","flex","commentaire social"], "impact":"theme" }}

Return ONLY the JSON object."""


# ============================================================
# PHASE 3A — TITLE + STYLE (JSON output)
# ============================================================

PHASE3A_STYLE = """\
--- USER'S CREATIVE INTENT ---
{user_intent}

--- STYLE ANALYSIS ---
Vocal presence: {vocal_presence}
Vocal delivery: {vocal_delivery}
Sonic identity: {sonic_identity}
Lyrical tone: {lyrical_tone}
Era: {era}
Mood: {mood}
Lyrics language: {lyrics_language}

--- USER DIRECTION ---
{user_context}
{previous_gen_hint}
---

Your task: produce a Suno-ready TITLE and STYLE descriptor.

Return a JSON object:
{{
  "title": "",      /* short, evocative, 2-6 words, no quotation marks */
  "style": ""       /* 25-45 words, dense comma-separated Suno descriptors — see rules */
}}

STYLE rules:
- Start with subgenre + production era (no artist names ever).
- Name key sonic signatures: instruments + textures + spatial character.
- Specify vocal texture precisely (or "no vocals" if instrumental).
- Include one mood/energy descriptor.
- End with tempo feel if characteristic (e.g. "relentless 180BPM", "mid-tempo groove").
- 25-45 words. Descriptors only, no full sentences. No filler words ("with", "featuring").

STYLE EXAMPLES — study the difference:

WEAK (never write this):
"rock music with guitar, bass and drums, energetic vocals, intense"
Why it fails: no subgenre, no era, no texture — Suno will produce clichéd output.

STRONG:
"early 2000s post-hardcore, palm-muted downtuned guitars, explosive loud-quiet-loud dynamics,
raw shouted-sung male vocals, crashing cymbal-heavy drumming, gritty lo-fi studio texture,
anthemic mid-tempo build"

STRONG (instrumental):
"minimal deep techno, hypnotic kick-heavy four-on-the-floor at 132BPM, subtle acid bassline,
granular pad washes, cold industrial atmosphere, sparse hi-hat rolls, no vocals"

TITLE rules:
- 2-6 words. Concrete imagery or a strong noun phrase.
- No quotation marks, no question marks, no exclamation marks.
- Must NOT contain artist or band names.

Return ONLY the JSON object."""


# ============================================================
# PHASE 3B — LYRICS (JSON output)
# ============================================================

PHASE3B_LYRICS = """\
--- USER'S CREATIVE INTENT ---
{user_intent}

--- STYLE ANALYSIS ---
Vocal presence: {vocal_presence}
Vocal delivery: {vocal_delivery}
Typical song structure: {song_structure}
Rhyme pattern: {rhyme_pattern}
Lyrical tone: {lyrical_tone}
Sonic identity: {sonic_identity}
Lyrics language: {lyrics_language}

--- TITLE (already fixed) ---
{title}

--- STYLE (already fixed) ---
{style}

--- USER DIRECTION ---
{user_context}
{previous_gen_hint}
---

{few_shot_block}

Your task: write Suno-ready LYRICS that match the title, style, and analysis above.

Return a JSON object:
{{
  "lyrics": ""    /* full lyrics including bracket section instructions — see rules */
}}

SUNO BRACKET / META-TAG VOCABULARY — use these literal labels:
{brackets_table}

VOCAL PRESENCE — follow strictly:

IF NONE: Write ONLY bracketed musical structure instructions (no sung/rapped text).
  Each bracket describes instrumentation, energy, transitions. Build an arc:
  intro → build → peak → breakdown → resolution. 6-10 bracketed sections.

IF MINIMAL: Write only the one hook/phrase this style uses, preceded by its bracket.
  Fill all other sections with detailed bracketed instructions only.
  Do NOT add verses/choruses that don't belong to this style.

IF MODERATE: Write vocal sections where they naturally occur, each preceded by its bracket.
  Use detailed brackets for instrumental-dominant sections.

IF FULL: Write complete lyrics. Use the authentic structure for this style — do NOT default to
  generic Verse/Chorus/Bridge unless that is genuinely how this style works.
  Every section starts with a rich bracket instruction.

BRACKET QUALITY — the single biggest driver of Suno output quality.

WEAK brackets (Suno guesses everything, produces generic output):
  [Verse 1]  [Chorus]  [Bridge - softer]  [Intro]

STRONG brackets (Suno has enough specificity to render the intended sound):
  [Intro - fingerpicked acoustic guitar with reverb tail, no vocals, sparse, building tension]
  [Verse 1 - hushed male vocals close-mic'd, sparse piano and brushed snare, melancholic, low energy]
  [Chorus - double-tracked shouted-sung lead, layered gang backing vocals, distorted bass, peak energy]
  [Bridge - single fingerpicked guitar, hushed spoken word, intimate, hanging silence]
  [Outro - feedback drone, no drums, dissolving reverb, peaceful resolution]

Every bracket must contain:
  1. Primary instrument(s) for that section
  2. Vocal type and delivery (or "no vocals" for instrumental sections)
  3. Energy level: "low" / "building" / "peak" / "resolving" / "sustained"
  4. Mood/atmosphere word that matches the section's lyrical content
  Target 8-20 words per bracket.

BPM placement rule:
  - BPM goes ONCE — either in the style descriptor (preferred) OR inside the [Intro - ..., NNNBPM] bracket.
  - Never in both. Never in every section.

Mid-song language switch:
  When the user requested code-switching, declare it explicitly:
  [Verse 2 - sung in <language>, ...] or [Verse 2 - rapped in <language>, ...]

Vocal layering (FULL only):
  Every chorus must declare layering: "double-tracked lead", "harmonized backing vocals",
  "gang vocal hooks", "ad-lib overdubs", etc.

LYRICAL SPECIFICITY — the enemy of a good Suno song is the generic phrase:
- BANNED clichés (never use in any form):
  "broken wings", "heart of gold", "burning like a fire", "tears in my eyes",
  "the world is crumbling", "reach for the stars", "rise and fall", "fade away",
  "neon lights", "endless night", "shadows fall", "set me free", "lost in time",
  "carry on", "stand tall", "break the chains".
- Instead of abstract emotion, write the PHYSICAL OBJECT or CONCRETE SCENE that carries it:
  NOT "I feel lost and alone" → "the last train leaves at 2AM and no one's waiting at my stop"
  NOT "the city is alive" → "diesel exhaust and scaffolding, jackhammers at 7AM, coffee in a paper cup"
- Every verse must contain at least ONE image specific enough to belong only to THIS song.
- Chorus lines: SHORT (4-6 words), MEMORABLE, CONCRETE — they are hooks, not explanations.
- Apply the identified rhyme scheme exactly — do NOT default to AABB unless that IS the analyzed scheme.

SONG LENGTH AND SECTION COUNT — Suno generates ~1:45-2:30 per generation:
- FULL: 2 verses + 2 choruses + 1 bridge + outro = optimal. A 3rd verse pads the song.
- MODERATE: 1-2 vocal sections + substantial instrumental sections.
- MINIMAL: 1 hook section + detailed instrumental architecture.
- NONE: 6-10 bracketed sections describing a complete arc.
- Each verse: 4-8 lines. Below 4 lines = Suno clips the delivery.
- Each chorus: 2-6 lines max — choruses repeat, so brevity = memorability.

FORBIDDEN in lyrics:
- Artist or band names anywhere.
- Ellipses (...).
- Em-dashes (—) inside lyric lines (square brackets only).
- Parenthetical stage directions inside lyric lines (use square brackets).
- Lines longer than 12 words.

LANGUAGE:
- Write ALL lyrics strictly in: {lyrics_language}
- No mixing unless the user explicitly requested code-switching.

Return ONLY the JSON object."""


# ============================================================
# SUNO BRACKETS — canonical vocabulary
# ============================================================

SUNO_BRACKETS_TABLE = """\
Structural sections:
  [Intro] [Verse 1] [Verse 2] [Pre-Chorus] [Chorus] [Post-Chorus]
  [Bridge] [Instrumental] [Build-up] [Drop] [Hook] [Refrain] [Outro] [End]

Vocal effects (inline within a bracket's description, or standalone):
  [whisper] [shouted] [spoken] [harmonized] [double-tracked] [layered vocals]
  [ad-lib] [backing vocals] [reverb tail] [telephone filter] [auto-tuned]

Transitions and dynamics:
  [Break] [Drop] [Build] [Fill] [Stop] [Silence — 1 bar] [Tempo change]

Examples of correctly enriched brackets:
  [Intro - sparse fingerpicked acoustic, no drums, reverb tail, brooding, low energy]
  [Verse 1 - close-mic'd raspy male vocals, brushed snare and double bass, intimate, building]
  [Chorus - double-tracked lead, harmonized backing vocals, distorted guitar wall, peak energy]
  [Bridge - single piano, whispered spoken word, dry recording, hanging silence, resolving]
"""


# ============================================================
# FEW-SHOT LIBRARY
# Compact examples (≤120 words each) per (vocal_presence, genre_family).
# Injection: pick the most relevant one for the current song.
# ============================================================

FEW_SHOTS: dict[tuple[str, str], dict] = {
    ("FULL", "rock_metal"): {
        "title": "Diesel Hymns",
        "style": "early 2000s post-hardcore, palm-muted downtuned guitars, loud-quiet-loud dynamics, "
                 "raw shouted-sung male vocals, crashing cymbals, gritty lo-fi studio texture, "
                 "anthemic mid-tempo build",
        "lyrics": (
            "[Intro - fingerpicked clean guitar with reverb tail, no drums, sparse, brooding]\n"
            "[Verse 1 - hushed male vocals close-mic'd, sparse piano and brushed snare, melancholic, building]\n"
            "The neon sign at Mike's still flickers blue\n"
            "The freight train shakes the bathroom mirror loose\n"
            "[Pre-Chorus - rising tremolo guitar, kick drum entering, vocals tightening, building]\n"
            "Count the bottles on the dresser\n"
            "[Chorus - double-tracked shouted-sung lead, layered gang backing vocals, distorted bass, peak energy]\n"
            "Diesel hymns at midnight\n"
            "Burn the highway out of sight\n"
            "[Bridge - single fingerpicked guitar, hushed spoken word, intimate, hanging silence]\n"
            "I don't write letters anymore\n"
            "[Outro - feedback drone, no drums, dissolving reverb, peaceful resolution]"
        ),
    },
    ("FULL", "hiphop_rap"): {
        "title": "Block 17 Forecast",
        "style": "boom-bap east-coast rap, dusty sampled jazz keys, swung kick-snare at 88BPM, "
                 "muted upright bass, double-tracked male vocals dry close-mic'd, vinyl crackle, "
                 "smoky basement atmosphere",
        "lyrics": (
            "[Intro - vinyl crackle, looped piano phrase, no vocals, sustained]\n"
            "[Verse 1 - rapped close-mic'd dry vocals, boom-bap drums and bassline, confident, sustained]\n"
            "Plastic bag on the chain-link, January grey\n"
            "Bus 21 missing again on Saturday\n"
            "Cousin called from the courthouse phone, fifteen minute clock\n"
            "Said the lawyer ain't read the file, just nodded a lot\n"
            "[Hook - double-tracked vocals with ad-lib overdubs, sample drop, peak energy]\n"
            "Block seventeen forecast cold\n"
            "Same news, different mold\n"
            "[Verse 2 - same delivery, slightly tighter flow, building]\n"
            "...\n"
            "[Outro - sample fades, drums drop, vinyl crackle resolves]"
        ),
    },
    ("FULL", "pop_rnb"): {
        "title": "Late Cab Receipt",
        "style": "contemporary alt-pop, glossy plucked synth, deep sub-bass, snappy programmed drums "
                 "at 102BPM, breathy female lead double-tracked, harmonized backing vocals, "
                 "wide-spread reverb, nocturnal mood",
        "lyrics": (
            "[Intro - plucked synth and sub-bass, no drums, atmospheric, low energy]\n"
            "[Verse 1 - breathy female vocals close-mic'd, sparse synth and finger snaps, intimate, building]\n"
            "Twenty-dollar bill folded in my coat\n"
            "Driver hums along to a song I don't know\n"
            "[Pre-Chorus - kick entering, vocals tightening, harmonies layering, building]\n"
            "Address spelled out twice\n"
            "[Chorus - double-tracked breathy lead, harmonized backing vocals, full beat, peak energy]\n"
            "Late cab receipt in my hand\n"
            "Wrong street, right plan\n"
            "[Bridge - vocals only, layered harmonies, no drums, intimate, resolving]\n"
            "[Outro - synth pad fade, single snap, dissolving reverb]"
        ),
    },
    ("FULL", "folk_singer_songwriter"): {
        "title": "Apple Crate Sundays",
        "style": "intimate folk singer-songwriter, fingerpicked nylon guitar, brushed snare, "
                 "upright bass, soft male tenor vocals dry close-mic'd, room-sound recording, "
                 "warm and reflective, 78BPM",
        "lyrics": (
            "[Intro - fingerpicked nylon guitar, no drums, room sound, low energy]\n"
            "[Verse 1 - soft male tenor vocals close-mic'd, fingerpicked guitar only, reflective, sustained]\n"
            "Apple crates stacked on the porch in September\n"
            "Dad smoked Marlboros and counted the change\n"
            "[Verse 2 - brushed snare and upright bass enter, vocals doubled, warm, building]\n"
            "Mom kept the radio low so the baby could sleep\n"
            "We took the Buick to the lake on Sundays\n"
            "[Chorus - vocals harmonized in thirds, full trio, intimate, sustained peak]\n"
            "Apple crate Sundays\n"
            "Half the world away\n"
            "[Outro - guitar only, dry, peaceful resolution]"
        ),
    },
    ("MODERATE", "indie_postrock"): {
        "title": "Tower Crane Lullaby",
        "style": "atmospheric indie post-rock, clean tremolo-picked guitar with delay, "
                 "spacious tom-heavy drums, swelling bass synth, occasional male vocals "
                 "moderate-reverb, cinematic build, 84BPM",
        "lyrics": (
            "[Intro - clean tremolo guitar with long delay, sparse drums, no vocals, building, 84BPM]\n"
            "[Verse - moderate male vocals with hall reverb, swelling synth bass, brushed cymbals, melancholic, building]\n"
            "Crane lights blink red over the river\n"
            "Concrete dust on the windowsill\n"
            "[Instrumental - layered tremolo guitars, tom rolls, no vocals, peak energy]\n"
            "[Bridge - vocals return spoken word, reverb tail, restrained, resolving]\n"
            "We measured the apartment in steps\n"
            "[Outro - guitar feedback fade, single tom hit, peaceful resolution]"
        ),
    },
    ("MINIMAL", "house_electro"): {
        "title": "Subterrain Loop",
        "style": "minimal deep house, hypnotic four-on-the-floor kick at 124BPM, "
                 "filtered disco sample loop, rolling sub-bass, sparse hi-hat shuffles, "
                 "single chopped female vocal hook, smoky club atmosphere",
        "lyrics": (
            "[Intro - filtered disco sample loop only, no kick, sustained, atmospheric, 124BPM]\n"
            "[Build - kick enters, hi-hat shuffles, sub-bass rolling, building]\n"
            "[Hook - chopped female vocal hook looped, layered with effects, sustained]\n"
            "Underground\n"
            "[Drop - full kick-bass-sample stack, hi-hat opens, peak energy]\n"
            "[Break - sample isolated with reverb, kick drops out, atmospheric]\n"
            "[Build - kick re-enters with filter sweep, building]\n"
            "[Drop - peak return, full stack, sustained]\n"
            "[Outro - kick drops, sample dissolves into reverb, resolving]"
        ),
    },
    ("NONE", "electronic_techno"): {
        "title": "Cold Forge Sequence",
        "style": "minimal industrial techno, relentless kick-heavy four-on-the-floor at 138BPM, "
                 "acid 303 bassline modulating, granular pad washes, cold metallic percussion, "
                 "cavernous warehouse reverb, no vocals",
        "lyrics": (
            "[Intro - granular pad wash only, no kick, atmospheric, sustained, low energy, 138BPM]\n"
            "[Build 1 - kick enters minimal, sparse hi-hat, building, no vocals]\n"
            "[Peak 1 - full kick-bass stack, acid 303 modulating, peak energy, sustained]\n"
            "[Break - kick drops, pad wash with reverb, metallic percussion ticks, atmospheric]\n"
            "[Build 2 - kick returns with filter sweep, acid line opening, building]\n"
            "[Peak 2 - acid line fully open, kick relentless, peak energy, sustained]\n"
            "[Breakdown - all elements wash through long reverb, no kick, atmospheric, resolving]\n"
            "[Outro - single granular pad fade, no percussion, peaceful resolution]"
        ),
    },
    ("FULL", "latin_reggaeton"): {
        "title": "Tinta Mojada",
        "style": "modern reggaeton-trap fusion at 92BPM, dembow rhythm, deep sub-bass slides, "
                 "syncopated trap hi-hats, smooth male Spanish vocals double-tracked, "
                 "ad-lib overdubs, hot Latin night atmosphere",
        "lyrics": (
            "[Intro - dembow rhythm, sub-bass slide, no vocals, atmospheric, building, 92BPM]\n"
            "[Verse 1 - sung in Spanish, smooth male vocals close-mic'd, dembow + trap hats, confident, building]\n"
            "Tinta mojada en el papel\n"
            "Tu nombre escrito sobre la piel\n"
            "[Pre-Chorus - vocals tightening, ad-libs entering, building]\n"
            "Bajo la lluvia\n"
            "[Chorus - sung in Spanish, double-tracked lead, ad-lib overdubs, full dembow, peak energy]\n"
            "Tinta mojada, corazón nuevo\n"
            "Vuelvo al barrio donde te llevo\n"
            "[Outro - dembow softens, sub-bass slide, vocals fade, resolving]"
        ),
    },
}


def pick_few_shot(vocal_presence: str, hints: list[str]) -> dict | None:
    """Pick the most relevant few-shot example.

    Matches first by vocal_presence, then by overlap of `hints` (lowercase tokens)
    with the genre_family slug. Returns None if no candidate matches.
    """
    vp = (vocal_presence or "").upper().strip()
    candidates = [(k, v) for k, v in FEW_SHOTS.items() if k[0] == vp]
    if not candidates:
        # Fallback: ignore vocal_presence
        candidates = list(FEW_SHOTS.items())
    if not candidates:
        return None
    if not hints:
        return candidates[0][1]
    hint_str = " ".join(h.lower() for h in hints if h)
    best = None
    best_score = -1
    for (vp_k, family), example in candidates:
        score = 0
        for token in family.split("_"):
            if token in hint_str:
                score += 1
        if score > best_score:
            best_score = score
            best = example
    return best


def render_few_shot_block(example: dict | None) -> str:
    """Render one few-shot example as a labelled prompt block, or empty string."""
    if not example:
        return ""
    return (
        "REFERENCE EXAMPLE — match this level of bracket specificity and lyrical concreteness "
        "(do NOT copy the words or imagery):\n\n"
        f"TITLE: {example['title']}\n"
        f"STYLE: {example['style']}\n"
        f"LYRICS:\n{example['lyrics']}\n\n"
        "End of reference example.\n"
    )


# ============================================================
# VALIDATION REFERENCE DATA
# ============================================================

LYRICS_CLICHES: list[str] = [
    # Original list (from previous prompt)
    "broken wings",
    "heart of gold",
    "burning like a fire",
    "tears in my eyes",
    "the world is crumbling",
    "reach for the stars",
    "rise and fall",
    "fade away",
    # Common Suno-era offenders
    "neon lights",
    "endless night",
    "shadows fall",
    "set me free",
    "lost in time",
    "carry on",
    "stand tall",
    "break the chains",
    "feel alive",
    "find my way",
    "light the way",
    "burning bright",
]


# Top-N stopwords per language, used as a lightweight detector during validation.
STOPWORDS_BY_LANG: dict[str, set[str]] = {
    "english": {
        "the", "and", "a", "an", "of", "to", "in", "on", "at", "for", "with", "from",
        "is", "are", "was", "were", "be", "been", "being", "i", "you", "he", "she",
        "we", "they", "this", "that", "these", "those", "my", "your", "his", "her",
    },
    "french": {
        "le", "la", "les", "un", "une", "des", "et", "ou", "mais", "donc", "ni", "car",
        "de", "du", "dans", "sur", "avec", "pour", "par", "sans", "sous", "vers",
        "je", "tu", "il", "elle", "nous", "vous", "ils", "elles", "mon", "ton", "son",
        "ma", "ta", "sa", "ce", "cette", "ces", "qui", "que", "quoi", "où", "quand",
    },
    "spanish": {
        "el", "la", "los", "las", "un", "una", "y", "o", "pero", "de", "del", "en",
        "con", "por", "para", "sin", "sobre", "yo", "tú", "él", "ella", "nosotros",
        "mi", "tu", "su", "este", "esta", "esto", "que", "qué", "cómo", "cuando",
    },
    "portuguese": {
        "o", "a", "os", "as", "um", "uma", "e", "ou", "mas", "de", "do", "da",
        "em", "no", "na", "com", "por", "para", "sem", "sobre", "eu", "tu", "ele",
        "ela", "nós", "meu", "teu", "seu", "este", "esta", "isto", "que", "como",
    },
    "italian": {
        "il", "lo", "la", "i", "gli", "le", "un", "uno", "una", "e", "o", "ma",
        "di", "da", "in", "su", "con", "per", "tra", "fra", "io", "tu", "egli",
        "noi", "voi", "loro", "mio", "tuo", "suo", "questo", "quello", "che",
    },
    "german": {
        "der", "die", "das", "den", "dem", "des", "ein", "eine", "einen", "und",
        "oder", "aber", "von", "zu", "in", "auf", "mit", "für", "ohne", "über",
        "ich", "du", "er", "sie", "wir", "ihr", "mein", "dein", "sein", "was", "wer",
    },
    "japanese": set(),  # Use char-class heuristic instead
}


# Section name canonical form (FR/EN variants → normalized name).
CANONICAL_SECTIONS: dict[str, str] = {
    "intro":            "intro",
    "introduction":     "intro",
    "verse":            "verse",
    "verse 1":          "verse",
    "verse 2":          "verse",
    "verse 3":          "verse",
    "couplet":          "verse",
    "couplet 1":        "verse",
    "couplet 2":        "verse",
    "pre-chorus":       "pre-chorus",
    "prechorus":        "pre-chorus",
    "pre-refrain":      "pre-chorus",
    "chorus":           "chorus",
    "refrain":          "chorus",
    "post-chorus":      "post-chorus",
    "post-refrain":     "post-chorus",
    "bridge":           "bridge",
    "pont":             "bridge",
    "instrumental":     "instrumental",
    "instrumental break": "instrumental",
    "solo":             "instrumental",
    "hook":             "hook",
    "build":            "build",
    "build-up":         "build",
    "buildup":          "build",
    "drop":             "drop",
    "break":            "break",
    "breakdown":        "break",
    "outro":            "outro",
    "end":              "outro",
    "fin":              "outro",
}


def canonical_section(name: str) -> str:
    """Map a section name (FR/EN, possibly numbered) to its canonical form."""
    if not name:
        return ""
    s = name.strip().lower()
    # Strip trailing numbers ("verse 2" handled by exact key, but "verse 17"?)
    if s in CANONICAL_SECTIONS:
        return CANONICAL_SECTIONS[s]
    # Try without trailing digits
    import re as _re
    s_no_num = _re.sub(r"\s*\d+$", "", s).strip()
    return CANONICAL_SECTIONS.get(s_no_num, s_no_num)
