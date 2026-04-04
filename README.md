# What Color Is This?

I'm colorblind. This is the question everyone asks me when they find out.

So I built an app that answers it. Point your camera at anything (a dress, a paint swatch, a sunset) and get the color's name instantly. It matches against 30,000 named colors using CIEDE2000 perceptual distance, which means the results actually correspond to how humans see color, not just how computers store it.

**[whatcoloristhis.one](https://whatcoloristhis.one)** · **[whatcoloristhat.one](https://whatcoloristhat.one)**

## What you get

Every color gets three tiers of identification:

- **Family**: the broad category (red, blue, teal, gray)
- **Descriptor**: a qualified label ("light muted blue", "vivid orange", "very dark gray")
- **Named match**: the closest of 30,000 named colors, ranked by perceptual distance

## Features

- **Camera sampling** with 7x7 pixel averaging and white balance calibration
- **Image upload** — drop a photo, tap anywhere to sample
- **Color matches** — complementary, analogous, triadic, split-complementary
- **Accessible palettes** — colorblind-safe swatches (Wong 2011), high-contrast pairs, CVD simulation (protanopia, deuteranopia, tritanopia via Brettel 1997)
- **Personal vision settings** — set your color vision type for personalized results
- **Save and label** — build a personal color library with notes, exportable as JSON
- **Random colors** — browse 30,000 named colors one at a time
- **Installable PWA** — works offline, add to home screen on any device

## API

```
POST /api/match        {"hex": "#C93F38"}
GET  /api/match/C93F38
```
Returns family, descriptor, top 5 named matches with CIEDE2000 distance, and color harmonies.

```
POST /api/accessible   {"hex": "#C93F38", "cvd_type": "deuteranopia"}
```
Returns CVD simulations, universal-safe palette, high-contrast pairs. Optional `cvd_type` personalizes the response.

```
GET  /api/random
```
Random named color with descriptor and family.

## Run locally

```bash
pip install flask flask-cors
python api.py
```

Runs on port 5010. Needs the color database — symlink or copy `colornames.json` (29,956 named colors, each `{"name": "...", "hex": "#RRGGBB"}`).

## Color math

All color matching is pure Python with no external dependencies:

- sRGB → linear RGB → XYZ (D65) → CIELAB
- CIEDE2000 for perceptual distance (Sharma, Wu, Dalal 2005)
- Brettel 1997 CVD simulation via LMS cone response matrices
- HSL-based color family classification with lightness/saturation modifiers

## Author

**Luke Steuber** — [lukesteuber.com](https://lukesteuber.com) · [Bluesky](https://bsky.app/profile/lukesteuber.com) · [datapoems.io](https://datapoems.io)
