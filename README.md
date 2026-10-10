# TouchSight

**Turn any textbook diagram into a tactile graphic a blind student can read with their fingers.**

Blind students usually get a sentence instead of a diagram ("a cell with a nucleus in the middle"). Real tactile graphics (raised-line drawings on swell paper or embossed) work far better, but each one is redrawn by hand by a specialist: simple images take 10–15 minutes and complex ones take hours. Most textbook figures never get one.

TouchSight produces a guideline-following first draft in seconds, for a transcriber or teacher to review.

## What it does

1. **Understand.** A vision-language model (Gemini, with open-source Qwen VL on Groq as automatic fallback) reads the diagram the way a tactile transcriber would. It decides which parts a student needs, finds where they are, reads the printed labels, and lists what to leave out and why.
2. **Trace.** The image is split into flat-colour patches, and each patch is assigned to the smallest box the model drew that contains it. Shaded structures are rebuilt from their gradient bands and neighbouring parts can't overlap. Box-prompted GrabCut is the fallback. Printed text and hairline leader lines are inpainted away first. Masks become vector outlines, simplified and smoothed at real physical scale.
3. **Design for touch.** The tactile rules are enforced in code:
   - elements at least ¼″ (6.35 mm), with at least ⅛″ (3.175 mm) between them
   - neighbouring areas get clearly different textures, assigned by graph colouring on a region-adjacency graph; one texture always means one thing
   - blank "dead zones" around outlines, nested parts and labels
   - Grade 1 braille labels drawn as physical dots, falling back to key letters plus a braille key when a word doesn't fit
4. **Check and auto-fix.** A readability validator scores the page and fixes what it can by enlarging, trimming, moving or dropping optional detail. It reports everything else for a human to check.
5. **Export** a print-ready A4 SVG for swell paper or an embosser, a 3D-printable STL tile, and a height map. The web app shows the result as a lit 3D relief.

## Run it locally

Requirements: Python 3.10+, Node.js 20+.

```bash
cp .env.example .env      # add GEMINI_API_KEY and GROQ_API_KEY
bash setup.sh             # Python venv + dependencies + key check
bash dev.sh               # engine on :8000, web app on http://localhost:3000
```

## Project layout

```
app.py                  FastAPI engine API (convert, downloads)
touchsight/vlm.py       vision-language analysis (Gemini → Groq fallback, on-disk cache)
touchsight/segment.py   text/leader removal, box-prompted segmentation, skeleton tracing
touchsight/tactile.py   physical layout, textures, braille labels, validator + auto-fix
touchsight/braille.py   Grade 1 braille with real dot geometry
touchsight/export.py    SVG, height map, STL
frontend/               Next.js web app (three.js relief viewer)
samples/                demo diagrams (credits in samples/CREDITS.md)
tests/fixtures/         test images with stored analyses for offline runs
```

## Built with and credits

- Vision models: Google Gemini API; Qwen VL served by Groq
- Computer vision and geometry: OpenCV (GrabCut, inpainting), scikit-image (skeletonisation), Shapely, NetworkX, NumPy, numpy-stl
- Web: FastAPI, Next.js, React, three.js
- Typeface: Atkinson Hyperlegible, designed by the Braille Institute
- Sample diagrams: Wikimedia Commons (heart by Wapcaplet, CC BY-SA 3.0; eye by Rhcastilhos and Jmarchn, CC BY-SA 3.0; simple animal and plant cells by domdomegg, CC BY 4.0). Full credits in `samples/CREDITS.md`
- Design rules: BANA *Guidelines and Standards for Tactile Graphics*; tactilegraphics.org design principles
- Related work: TactileNet (2025, arXiv:2504.04722) generates tactile-style images with diffusion models for fixed object classes. TouchSight instead converts the specific diagram a teacher already has, adds braille and a key, and enforces the size and spacing rules in code.
- Generative AI disclosure: Claude (Anthropic) was used as a coding assistant during the hackathon.

## Limits

TouchSight produces a draft, not a finished transcription. Uncontracted braille only. It has not yet been tested with blind readers, and that is the next step.
