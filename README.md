# TouchSight

**Turns a textbook diagram into a print-ready tactile graphic, with simplified shapes, distinct textures and braille labels, that a blind student can read with their fingers.**

Built for Banana Hacks 2026 (image AI).

---

## The problem

Blind students in science, maths and geography usually get a sentence in place of a diagram: *"a cell with a nucleus in the middle."* That loses what the diagram is for: position, shape, connection, proportion.

The tool that works is a **tactile graphic**: a raised-line drawing produced on swell paper, an embosser or a 3D printer. But a tactile graphic is not the original with the lines raised. Fingers resolve far less detail than eyes, so a trained transcriber has to redraw it:
- remove clutter
- keep every element at least ¼″ and at least ⅛″ apart
- give neighbouring areas clearly different textures
- leave blank space around labels
- replace print with braille, moving to a key when a label won't fit

Simple images take 10–15 minutes by hand and complex ones take hours ([TactileNet, 2025](https://arxiv.org/abs/2504.04722)). Most textbook figures never get converted.

TouchSight produces a **guideline-following first draft in seconds**, for a teacher or transcriber to review and adjust.

## How it works

```
 image ──► 1 Understand ──► 2 Trace ──► 3 Design for touch ──► 4 Check + auto-fix ──► 5 Export
           vision-language   colour-patch   physical layout,       readability rules,     print SVG (A4, 1:1)
           model reads it    assignment,    textures, braille,     score, repairs         3D-print STL
           like a            GrabCut        key, dead zones                               height map, description
           transcriber       fallback
```

1. **Understand** (`touchsight/vlm.py`). A vision-language model (Gemini, with Qwen VL on Groq as fallback) is prompted as a tactile transcriber. It returns the diagram type, the parts a student needs with bounding boxes and nesting, the printed text to erase, and *what it left out and why*. Every field is validated and sanitised before use, and answers are cached by image hash.
2. **Trace** (`touchsight/segment.py`). Printed labels and hairline leader lines are inpainted away. The image is split into flat-colour patches, and each patch is assigned to the *smallest* model box that contains it. That rebuilds shaded structures from their gradient bands and stops neighbouring parts competing for the same pixels. GrabCut seeded with the box is the fallback. Thin parts such as wires and axes are traced as stroke skeletons.
3. **Design for touch** (`touchsight/tactile.py`). Shapes move onto a physical A4 page in millimetres and are simplified and smoothed. Nesting the model missed is inferred from geometry.
   - **Textures:** assigned by graph colouring over a region-adjacency graph, so neighbours never share one and one texture always means one thing. Large containers stay plain.
   - **Dead zones:** blank space is kept around outlines, nested parts and labels.
   - **Labels:** uncontracted braille (UEB grade 1, with the grade-1 indicator on standalone letters) is drawn as physical dots. Labels go inside a shape when they fit and otherwise become key letters with a braille key.
4. **Check and auto-fix.** A validator checks size, spacing, overlap, label collisions, texture reuse and clutter, then repairs what it can:
   - enlarging small parts, or replacing them with a minimum-size symbol
   - trimming to open gaps
   - moving parts inward
   - dropping optional detail

   It scores the first draft and the fixed page on the same checks and lists anything a person still needs to look at.
5. **Export** (`touchsight/export.py`). A print SVG at true scale for swell paper or embossers, a watertight STL tile for 3D printing, a height map, and a plain-language description for screen-reader users.

A teacher can then untick parts in the **Parts** tab and rebuild instantly. The earlier reading is reused, so there's no second model call.

## Touch, listen and ask

The printed sheet is half of the experience. The other half is audio, following the talking-tactile approach used in tools like the Talking Tactile Tablet:

- **Touch and listen.** Tap any part of the page on a phone or tablet to hear what it is, where it sits ("inside the cell membrane, towards the top right"), what it feels like and what its braille label says. Slide a finger to hear names as you cross parts. On a laptop, Tab moves between parts and Enter reads one. Smaller nested parts always win the hit test. This runs on the browser's built-in speech, at no cost and with no API key.
- **Guided tour.** The page is read aloud in a sensible order: title, summary, then containers before contents and big parts before small ones. Each part is highlighted as it's described.
- **Ask the diagram.** Press the microphone and ask "where is the nucleus compared to the vacuole?" or "what was left out?". The answer is spoken. Answers about *position, size, texture and labels* are grounded in layout facts computed from the actual page geometry (directions, distances in cm and finger-widths, containment), never guessed. The model adds subject knowledge only to explain what a part does. Typed questions work in every browser; voice input needs Chrome, Edge or Safari.
- **Take a photo of a page.** The camera button opens the phone camera directly. Uploads are identified from their bytes, not their filename, then normalised: PNG, JPEG, WebP, HEIC/HEIF (iPhone), AVIF, GIF, BMP and TIFF are all accepted. Phone EXIF rotation is applied, the first frame of animations is used, transparency is flattened and large photos are shrunk, first in the browser where it can decode the image and always on the server.

## What's different

| | Hand transcription | Generative approach (e.g. TactileNet) | TouchSight |
|---|---|---|---|
| Input | the teacher's diagram | a prompt or class name | the teacher's diagram |
| Output fidelity | exact | a *new* image of the concept | the same diagram, simplified |
| Braille + key | yes | no | yes, generated and placed |
| Guideline checks | the transcriber's judgement | human review afterwards | enforced in code, scored, auto-fixed |
| Time | minutes to hours | seconds | seconds, plus review |

Earlier research tools (e.g. the University of Washington Tactile Graphics Assistant) automated text removal and braille labelling with classical image processing. What's new here is **semantic simplification**: a model that understands the subject decides what matters to a student and explains what it dropped. Rule-checked layout code sits on top so the result stays within the tactile guidelines.

## What has been verified

Verification happens at two levels.

**1. The live AI calls.** In normal use, Gemini (with Groq as backup) reads every new diagram and answers every question. These were checked against real models:
- `scripts/check_keys.py` sends a synthetic diagram whose true shapes are known and measures how well each model locates them. Gemini scored 97–99% box accuracy and Qwen on Groq 77–92%.
- Real Wikimedia diagrams were run end to end in the app (results below), and spoken questions were answered by Gemini in the browser.

**2. Our own code, with an automated test suite.** `pytest` runs 52 tests. During these tests the model call is replaced by a saved model answer, so the tests are repeatable, take about 20 seconds, cost nothing and don't use the free-tier quota. They check everything our code does with a model's answer:
- **Braille:** the letters a–z, numbers, decimals and the grade-1 indicator match UEB grade 1; dot and cell spacing match the standard dimensions.
- **Physical output:** the print SVG is A4 at 1 unit = 1 mm and contains no non-tactile ink; the STL is watertight (every edge shared by exactly two triangles) and A4-sized.
- **Layout rules:** small parts are detected and enlarged, neighbouring textures always differ, nesting is inferred, scores count only unfixed issues.
- **Model output handling:** markup, script injection, bad boxes and unknown kinds are neutralised; ids are rewritten.
- **API:** non-images and oversized images are rejected, sample names are whitelisted, the rate limit works, sample upload is off by default, and the convert → redesign → download path works.
- **Image intake:** every accepted format, including HEIC and AVIF, becomes an upright RGB PNG; EXIF rotation, CMYK, animation, transparency and downscaling are all covered; output is deterministic.
- **Spatial language:** spoken descriptions state containment correctly, facts never describe a part as "above" its own container, and the hit test picks the smallest region under the finger. Questions are answered from the page's layout facts, and replies are cleaned for speech.

Manually checked on real Wikimedia diagrams: plant cell and animal cell (clean, first draft scored 64–76 and 100 after auto-fix), heart (recognisable, busier), eye (readable but rough). Box accuracy against known shapes: Gemini 97–99%, Qwen 77–92%.

**Not yet verified:** reading by blind students or review by a certified transcriber. That's the most important next step, and nothing here claims to replace either.

## Security

- **Model output is untrusted.** It's normalised: ids rewritten, text stripped of markup and control characters, values clamped. The SVG is built only from those values, with attributes quoted. The prompt tells the model to ignore instructions written inside images.
- **Uploads** are capped at 12 MB. The image header is checked *before decoding*: PNG, JPEG or WebP only, at most 40 MP, which stops decompression bombs.
- **No user input reaches the filesystem.** Samples are looked up in a whitelist. The sample-authoring endpoint is off unless `ALLOW_SAMPLE_UPLOAD=1`, which only `dev.sh` sets.
- **Rate limits and CORS:** a per-client rate limit on conversions protects the API quota. CORS is restricted to configured origins.
- **Errors** return a reference id. Details only appear when `DEBUG_ERRORS=1` (local dev).
- **Secrets** live in `.env`, which is git-ignored, and are excluded from the settings `repr` so they can't leak into logs.
- **The container** runs as a non-root user. Dependencies are pinned. The Next.js app sends security headers (no framing, no MIME sniffing, strict referrer); its permissions policy allows the microphone and camera for this page only, for voice questions and photos.

## Run it locally

Requirements: Python 3.10+ (tested on 3.11) and Node.js 20+.

```bash
cp .env.example .env      # add GEMINI_API_KEY and/or GROQ_API_KEY
bash setup.sh             # venv, dependencies, provider check
bash dev.sh               # engine on :8000, web app on http://localhost:3000
```

Run the tests with `source .venv/bin/activate && pytest`.

Voice questions need Chrome, Edge or Safari and microphone permission. If the browser reports the mic as blocked, allow it in the site settings (the icon left of the address bar) and, on macOS, under System Settings → Privacy & Security → Microphone. Typed questions always work.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `GEMINI_API_KEY`, `GROQ_API_KEY` | (none) | vision providers; at least one is required |
| `GEMINI_MODEL` | newest usable Flash model | pin a Gemini model |
| `GROQ_MODEL` | `qwen/qwen3.8-27b` | Groq vision model |
| `ALLOWED_ORIGINS` | `http://localhost:3000` | CORS origins, comma-separated |
| `RATE_LIMIT_PER_MIN` | `12` | conversions per client per minute |
| `VLM_TIMEOUT_S` | `90` | provider timeout |
| `CACHE_DIR` | `./cache` | cached readings |
| `ALLOW_SAMPLE_UPLOAD`, `DEBUG_ERRORS` | off | local-development conveniences only |
| `BACKEND_URL` (frontend) | `http://127.0.0.1:8000` | where Next.js proxies `/api` |

## Deploying

- **Engine:** `Dockerfile` (Python 3.11, non-root, `$PORT` aware). Works on Render, Fly.io, Railway or Hugging Face Spaces. Set the API keys and `ALLOWED_ORIGINS` to the frontend URL.
- **Web app:** deploy `frontend/` to Vercel with `BACKEND_URL` set to the engine URL.

## Project layout

```
app.py                    HTTP API: convert, redesign, ask, downloads, rate limits, job store
touchsight/config.py      settings from the environment
touchsight/vlm.py         vision-language reading, provider fallback, validation, cache
touchsight/segment.py     image checks, text removal, colour-patch tracing, GrabCut, skeletons
touchsight/tactile.py     physical layout, nesting, textures, braille labels, validator, auto-fix
touchsight/braille.py     UEB grade 1 with real dot geometry
touchsight/export.py      print/preview SVG, height map, STL
touchsight/intake.py      upload normalisation (HEIC, AVIF, EXIF rotation, size caps)
touchsight/spatial.py     spatial language: spoken descriptions, guided tour, layout facts for Q&A
touchsight/pipeline.py    orchestration and the report the UI renders
frontend/                 Next.js app (tactile page, touch and listen, ask by voice, three.js relief, parts editor)
samples/                  demo diagrams (credits in samples/CREDITS.md)
cache/                    cached readings for the samples, so demos run without API calls
tests/                    pytest suite and offline fixtures
scripts/check_keys.py     provider smoke test with box-accuracy report
```

## Limitations and next steps

- **Testing with blind readers** and review by certified transcribers.
- **Contracted braille (UEB grade 2)** via liblouis. Labels are currently uncontracted.
- **Diagram types:** 3D or perspective originals are flagged but not redrawn as flat views. Dense or photographic figures trace poorly. Charts should be re-plotted from extracted data rather than traced.
- **Learned segmentation:** model-generated pixel masks were tried and were too slow and inconsistent on the free tier to use (over 80 s and partial results). A local promptable segmenter is the natural upgrade path inside `segment_box`.
- **Multi-page output** (key on its own page) and embosser-specific formats.

## Credits

- Vision models: Google Gemini API; Qwen VL served by Groq.
- Libraries: OpenCV, scikit-image, Shapely, NetworkX, NumPy, numpy-stl, Pillow, FastAPI, Next.js, React, three.js.
- Typeface: Atkinson Hyperlegible, designed by the Braille Institute.
- Design rules: BANA *Guidelines and Standards for Tactile Graphics*; tactilegraphics.org design principles.
- Sample diagrams: Wikimedia Commons. Heart by Wapcaplet (CC BY-SA 3.0); eye by Rhcastilhos and Jmarchn (CC BY-SA 3.0); simple animal and plant cells by domdomegg (CC BY 4.0). Full credits in `samples/CREDITS.md`.
- Related work: TactileNet (arXiv:2504.04722); University of Washington Tactile Graphics Assistant.
- Generative AI disclosure: Claude (Anthropic) was used as a coding assistant during the hackathon.
