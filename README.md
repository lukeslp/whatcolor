# What Color Is This?

Point your camera at anything and get its name. Three-tier color identification with CIEDE2000 perceptual matching against 30,000 named colors.

**[whatcoloristhis.one](https://whatcoloristhis.one)** | **[whatcoloristhat.one](https://whatcoloristhat.one)**

## How it works

1. Point your camera, drop an image, or paste a hex code
2. The app samples the color and converts it through sRGB to CIELAB color space
3. CIEDE2000 (the most perceptually accurate color distance formula) finds the closest matches from 30,000 named colors

Results come back in three tiers:

- **Family** -- base hue category (red, blue, teal, gray, etc.)
- **Descriptor** -- qualified label ("light muted blue", "vivid orange", "very dark gray")
- **Matches** -- the 5 closest named colors ranked by perceptual distance

## Features

- Camera, image upload, and hex input
- Color harmonies: complementary, analogous, triadic, split-complementary
- Color vision deficiency simulation (protanopia, deuteranopia, tritanopia)
- Colorblind-safe palette suggestions based on Wong (2011)
- Save and browse a personal color history
- Installable as a PWA on mobile and desktop
- Pure Python CIELAB/CIEDE2000 implementation with no external dependencies for color math

## API

```
POST /api/match        {"hex": "#C93F38"}
GET  /api/match/C93F38
```

Returns family, descriptor, top 5 named matches with CIEDE2000 distance, and color harmonies.

```
POST /api/accessible   {"hex": "#C93F38"}
```

Returns CVD simulations, universal-safe palette, and high-contrast pair suggestions.

```
GET  /api/random
```

Returns a random named color from the full database.

## Run locally

```bash
pip install flask flask-cors
python api.py
```

Opens on port 5010.

## Author

**Luke Steuber** -- [lukesteuber.com](https://lukesteuber.com)
