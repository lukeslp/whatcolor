#!/usr/bin/env python3
"""What Color API - Flask backend for identifying closest named colors using CIELAB Delta E matching"""
import json
import math
import os
import random
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

app = Flask(__name__, static_folder='.')
CORS(app, origins=[
    "https://dr.eamer.dev",
    "https://whatcoloristhis.one",
    "https://whatcoloristhat.one",
    "https://whatcolouristhat.com",
])

# ---------------------------------------------------------------------------
# Color conversion utilities (pure Python, no external deps)
# ---------------------------------------------------------------------------

def hex_to_rgb(hex_str):
    """Convert hex color string to RGB tuple (0-255)."""
    hex_str = hex_str.lstrip('#')
    return (int(hex_str[0:2], 16), int(hex_str[2:4], 16), int(hex_str[4:6], 16))


def rgb_to_linear(c):
    """Gamma-decode a single sRGB channel (0-255) to linear RGB (0-1)."""
    c = c / 255.0
    if c > 0.04045:
        return ((c + 0.055) / 1.055) ** 2.4
    return c / 12.92


def rgb_to_xyz(r, g, b):
    """Convert sRGB (0-255) to CIE XYZ using D65 illuminant / sRGB matrix."""
    rl = rgb_to_linear(r)
    gl = rgb_to_linear(g)
    bl = rgb_to_linear(b)

    # sRGB to XYZ (D65) matrix — values scaled to 0-100 range
    x = (0.4124564 * rl + 0.3575761 * gl + 0.1804375 * bl) * 100.0
    y = (0.2126729 * rl + 0.7151522 * gl + 0.0721750 * bl) * 100.0
    z = (0.0193339 * rl + 0.1191920 * gl + 0.9503041 * bl) * 100.0
    return (x, y, z)


def xyz_to_lab(x, y, z):
    """Convert CIE XYZ to CIELAB using D65 white point."""
    # D65 reference white point
    xn, yn, zn = 95.047, 100.0, 108.883

    def f(t):
        delta = 6.0 / 29.0
        if t > delta ** 3:
            return t ** (1.0 / 3.0)
        return t / (3.0 * delta * delta) + 4.0 / 29.0

    fx = f(x / xn)
    fy = f(y / yn)
    fz = f(z / zn)

    L = 116.0 * fy - 16.0
    a = 500.0 * (fx - fy)
    b = 200.0 * (fy - fz)
    return (L, a, b)


def hex_to_lab(hex_str):
    """Convert hex color string directly to CIELAB."""
    r, g, b = hex_to_rgb(hex_str)
    x, y, z = rgb_to_xyz(r, g, b)
    return xyz_to_lab(x, y, z)


def delta_e_cie76(lab1, lab2):
    """CIE76 Delta E — Euclidean distance in CIELAB space."""
    return math.sqrt(
        (lab1[0] - lab2[0]) ** 2 +
        (lab1[1] - lab2[1]) ** 2 +
        (lab1[2] - lab2[2]) ** 2
    )


def delta_e_ciede2000(lab1, lab2):
    """CIEDE2000 Delta E — perceptually uniform color distance.

    Full implementation of the CIE DE2000 formula.
    Reference: Sharma, Wu, Dalal (2005) "The CIEDE2000 Color-Difference Formula"
    """
    L1, a1, b1 = lab1
    L2, a2, b2 = lab2

    # Step 1: Calculate Cab, hab
    C1 = math.sqrt(a1**2 + b1**2)
    C2 = math.sqrt(a2**2 + b2**2)
    Cab_mean = (C1 + C2) / 2.0

    G = 0.5 * (1.0 - math.sqrt(Cab_mean**7 / (Cab_mean**7 + 25.0**7)))
    a1p = a1 * (1.0 + G)
    a2p = a2 * (1.0 + G)

    C1p = math.sqrt(a1p**2 + b1**2)
    C2p = math.sqrt(a2p**2 + b2**2)

    h1p = math.degrees(math.atan2(b1, a1p)) % 360.0
    h2p = math.degrees(math.atan2(b2, a2p)) % 360.0

    # Step 2: Calculate delta values
    dLp = L2 - L1
    dCp = C2p - C1p

    if C1p * C2p == 0:
        dhp = 0.0
    elif abs(h2p - h1p) <= 180.0:
        dhp = h2p - h1p
    elif h2p - h1p > 180.0:
        dhp = h2p - h1p - 360.0
    else:
        dhp = h2p - h1p + 360.0

    dHp = 2.0 * math.sqrt(C1p * C2p) * math.sin(math.radians(dhp / 2.0))

    # Step 3: Calculate CIEDE2000
    Lp_mean = (L1 + L2) / 2.0
    Cp_mean = (C1p + C2p) / 2.0

    if C1p * C2p == 0:
        hp_mean = h1p + h2p
    elif abs(h1p - h2p) <= 180.0:
        hp_mean = (h1p + h2p) / 2.0
    elif h1p + h2p < 360.0:
        hp_mean = (h1p + h2p + 360.0) / 2.0
    else:
        hp_mean = (h1p + h2p - 360.0) / 2.0

    T = (1.0
         - 0.17 * math.cos(math.radians(hp_mean - 30.0))
         + 0.24 * math.cos(math.radians(2.0 * hp_mean))
         + 0.32 * math.cos(math.radians(3.0 * hp_mean + 6.0))
         - 0.20 * math.cos(math.radians(4.0 * hp_mean - 63.0)))

    SL = 1.0 + 0.015 * (Lp_mean - 50.0)**2 / math.sqrt(20.0 + (Lp_mean - 50.0)**2)
    SC = 1.0 + 0.045 * Cp_mean
    SH = 1.0 + 0.015 * Cp_mean * T

    RT_theta = 30.0 * math.exp(-((hp_mean - 275.0) / 25.0)**2)
    RC = 2.0 * math.sqrt(Cp_mean**7 / (Cp_mean**7 + 25.0**7))
    RT = -math.sin(math.radians(2.0 * RT_theta)) * RC

    dE = math.sqrt(
        (dLp / SL)**2 +
        (dCp / SC)**2 +
        (dHp / SH)**2 +
        RT * (dCp / SC) * (dHp / SH)
    )
    return dE


def quality_label(delta_e):
    """Human-readable match quality based on CIEDE2000 distance."""
    if delta_e < 1.0:
        return "exact"
    if delta_e < 3.0:
        return "very close"
    if delta_e < 6.0:
        return "close"
    if delta_e < 12.0:
        return "approximate"
    return "rough"


def rgb_to_hsl(r, g, b):
    """Convert RGB (0-255) to HSL. Returns (h: 0-360, s: 0-100, l: 0-100)."""
    r, g, b = r / 255.0, g / 255.0, b / 255.0
    cmax = max(r, g, b)
    cmin = min(r, g, b)
    delta = cmax - cmin

    # Lightness
    l = (cmax + cmin) / 2.0

    if delta == 0:
        h = 0.0
        s = 0.0
    else:
        # Saturation
        if l < 0.5:
            s = delta / (cmax + cmin)
        else:
            s = delta / (2.0 - cmax - cmin)

        # Hue
        if cmax == r:
            h = ((g - b) / delta) % 6
        elif cmax == g:
            h = (b - r) / delta + 2
        else:
            h = (r - g) / delta + 4
        h *= 60.0
        if h < 0:
            h += 360.0

    return (h, s * 100.0, l * 100.0)


def classify_color(r, g, b):
    """Three-tier color classification from RGB values.

    Returns dict with:
      - family: base hue family (12 categories)
      - descriptor: qualified human-readable label ("light muted blue")
      - hue, saturation, lightness: raw HSL values
    """
    h, s, l = rgb_to_hsl(r, g, b)

    # --- Tier 1: Base hue family (12 categories) ---
    # Achromatic
    if s < 8:
        if l > 92:
            family = "white"
        elif l < 12:
            family = "black"
        else:
            family = "gray"
        return {
            'family': family,
            'descriptor': _describe_achromatic(l),
        }

    # Chromatic hue families
    if h < 12 or h >= 348:
        family = "red"
    elif h < 38:
        family = "orange"
    elif h < 55:
        family = "yellow-orange"
    elif h < 73:
        family = "yellow"
    elif h < 105:
        family = "yellow-green"
    elif h < 160:
        family = "green"
    elif h < 195:
        family = "teal"
    elif h < 255:
        family = "blue"
    elif h < 290:
        family = "purple"
    elif h < 330:
        family = "magenta"
    else:
        family = "pink"

    # --- Tier 2: Qualified descriptor ---
    parts = []

    # Lightness modifier
    if l > 85:
        parts.append("very light")
    elif l > 70:
        parts.append("light")
    elif l < 15:
        parts.append("very dark")
    elif l < 30:
        parts.append("dark")

    # Saturation modifier
    if s < 20:
        parts.append("grayish")
    elif s < 40:
        parts.append("muted")
    elif s > 85:
        parts.append("vivid")

    parts.append(family)
    descriptor = " ".join(parts)

    return {
        'family': family,
        'descriptor': descriptor,
    }


def _describe_achromatic(l):
    """Describe achromatic (gray-scale) colors."""
    if l > 95:
        return "white"
    if l > 85:
        return "very light gray"
    if l > 70:
        return "light gray"
    if l > 55:
        return "medium light gray"
    if l > 40:
        return "medium gray"
    if l > 25:
        return "dark gray"
    if l > 12:
        return "very dark gray"
    return "black"


# ---------------------------------------------------------------------------
# Load and pre-process color database
# ---------------------------------------------------------------------------

COLORS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'colornames.json')
with open(COLORS_FILE) as f:
    COLORS_RAW = json.load(f)

# Pre-compute CIELAB values for every color in the database
COLOR_CACHE = []
for entry in COLORS_RAW:
    lab = hex_to_lab(entry['hex'])
    rgb = hex_to_rgb(entry['hex'])
    COLOR_CACHE.append({
        'name': entry['name'],
        'hex': entry['hex'],
        'lab': lab,
        'rgb': rgb,
    })

print(f"Loaded {len(COLOR_CACHE)} colors with CIELAB cache")


# ---------------------------------------------------------------------------
# Matching logic
# ---------------------------------------------------------------------------

def find_closest(hex_str, count=5):
    """Find the closest named colors using CIEDE2000 perceptual distance.

    Returns three-tier identification:
      - Tier 1 (family): base hue category ("blue", "red", "gray")
      - Tier 2 (descriptor): qualified label ("light muted blue")
      - Tier 3 (matches): closest named colors with distance and quality
    """
    hex_str = hex_str.strip().lstrip('#')
    if len(hex_str) != 6:
        return None

    try:
        int(hex_str, 16)
    except ValueError:
        return None

    hex_str = f"#{hex_str.lower()}"
    input_rgb = hex_to_rgb(hex_str)
    input_lab = hex_to_lab(hex_str)
    classification = classify_color(*input_rgb)

    # Calculate CIEDE2000 against every cached color
    distances = []
    for c in COLOR_CACHE:
        d = delta_e_ciede2000(input_lab, c['lab'])
        distances.append((d, c))

    # Sort by distance, take top N
    distances.sort(key=lambda x: x[0])
    matches = []
    for d, c in distances[:count]:
        matches.append({
            'name': c['name'],
            'hex': c['hex'],
            'distance': round(d, 2),
            'rgb': list(c['rgb']),
            'family': classify_color(*c['rgb'])['family'],
            'quality': quality_label(d),
        })

    # Compute color harmonies from the input color
    harmonies = compute_harmonies(input_rgb)

    return {
        'input': hex_str,
        'family': classification['family'],
        'descriptor': classification['descriptor'],
        'matches': matches,
        'harmonies': harmonies,
    }


def hsl_to_rgb(h, s, l):
    """Convert HSL (h: 0-360, s: 0-100, l: 0-100) back to RGB (0-255)."""
    s /= 100.0
    l /= 100.0

    c = (1.0 - abs(2.0 * l - 1.0)) * s
    x = c * (1.0 - abs((h / 60.0) % 2 - 1.0))
    m = l - c / 2.0

    if h < 60:
        r1, g1, b1 = c, x, 0
    elif h < 120:
        r1, g1, b1 = x, c, 0
    elif h < 180:
        r1, g1, b1 = 0, c, x
    elif h < 240:
        r1, g1, b1 = 0, x, c
    elif h < 300:
        r1, g1, b1 = x, 0, c
    else:
        r1, g1, b1 = c, 0, x

    return (
        max(0, min(255, round((r1 + m) * 255))),
        max(0, min(255, round((g1 + m) * 255))),
        max(0, min(255, round((b1 + m) * 255))),
    )


def rgb_to_hex(r, g, b):
    """Convert RGB to hex string."""
    return f"#{r:02x}{g:02x}{b:02x}"


def compute_harmonies(rgb):
    """Compute color harmonies: complementary, analogous, triadic, split-complementary.

    Returns dict of harmony types, each with a list of colors (hex + descriptor).
    """
    h, s, l = rgb_to_hsl(*rgb)

    def make_color(hue):
        hue = hue % 360
        r, g, b = hsl_to_rgb(hue, s, l)
        classification = classify_color(r, g, b)
        return {
            'hex': rgb_to_hex(r, g, b),
            'descriptor': classification['descriptor'],
            'family': classification['family'],
        }

    return {
        'complementary': [make_color(h + 180)],
        'analogous': [make_color(h - 30), make_color(h + 30)],
        'triadic': [make_color(h + 120), make_color(h + 240)],
        'split_complementary': [make_color(h + 150), make_color(h + 210)],
    }


# ---------------------------------------------------------------------------
# CVD simulation (Brettel 1997) — color vision deficiency
# ---------------------------------------------------------------------------

# RGB to LMS matrix (Hunt-Pointer-Estevez)
RGB_TO_LMS = [
    [0.31399022, 0.63951294, 0.04649755],
    [0.15537241, 0.75789446, 0.08670142],
    [0.01775239, 0.10944209, 0.87256922],
]

LMS_TO_RGB = [
    [5.47221206, -4.64196010, 0.16963708],
    [-1.12524190, 2.29317094, -0.16789520],
    [0.02980165, -0.19318073, 1.16364789],
]

# CVD simulation matrices (full severity)
PROTAN_SIM = [
    [0.0, 1.05118294, -0.05116099],
    [0.0, 1.0, 0.0],
    [0.0, 0.0, 1.0],
]

DEUTAN_SIM = [
    [1.0, 0.0, 0.0],
    [0.9513092, 0.0, 0.04866992],
    [0.0, 0.0, 1.0],
]

TRITAN_SIM = [
    [1.0, 0.0, 0.0],
    [0.0, 1.0, 0.0],
    [-0.86744736, 1.86727089, 0.0],
]

# Wong (2011) colorblind-safe palette
WONG_PALETTE = [
    '#000000',  # black
    '#E69F00',  # orange
    '#56B4E9',  # sky blue
    '#009E73',  # bluish green
    '#F0E442',  # yellow
    '#0072B2',  # blue
    '#D55E00',  # vermillion
    '#CC79A7',  # reddish purple
]


def matrix_multiply(mat, vec):
    return [sum(m * v for m, v in zip(row, vec)) for row in mat]


def linear_to_srgb(c):
    """Inverse gamma: linear (0-1) to sRGB (0-255)."""
    if c <= 0.0031308:
        s = 12.92 * c
    else:
        s = 1.055 * (c ** (1.0 / 2.4)) - 0.055
    return max(0, min(255, round(s * 255)))


def simulate_cvd(rgb, cvd_matrix):
    """Simulate color vision deficiency."""
    r, g, b = rgb
    lin = [rgb_to_linear(r), rgb_to_linear(g), rgb_to_linear(b)]
    lms = matrix_multiply(RGB_TO_LMS, lin)
    sim_lms = matrix_multiply(cvd_matrix, lms)
    sim_lin = matrix_multiply(LMS_TO_RGB, sim_lms)
    return (linear_to_srgb(sim_lin[0]), linear_to_srgb(sim_lin[1]), linear_to_srgb(sim_lin[2]))


# ---------------------------------------------------------------------------
# Shuffle-bag random color state
# ---------------------------------------------------------------------------

remaining_colors = []
last_color = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    """Serve the main HTML page with per-domain meta tags."""
    host = request.host.split(':')[0]
    if 'whatcoloristhat' in host or 'whatcolouristhat' in host:
        # Read and patch meta tags for the "that" domain
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'index.html')) as f:
            html = f.read()
        html = html.replace(
            '<title>What Color Is This?</title>',
            '<title>What Color Is That?</title>'
        ).replace(
            'og:title" content="What Color Is This?"',
            'og:title" content="What Color Is That?"'
        ).replace(
            'og:description" content="Aim your camera at a color',
            'og:description" content="No seriously, what color is that? I genuinely cannot tell. Aim your camera at a color'
        ).replace(
            'og-image-this.png',
            'og-image-that.png'
        ).replace(
            'whatcoloristhis.one/',
            'whatcoloristhat.one/'
        )
        return html, 200, {'Content-Type': 'text/html; charset=utf-8'}
    return send_from_directory('.', 'index.html')


@app.route('/health')
def health():
    """Health check endpoint for service monitoring"""
    return jsonify({'status': 'healthy'})


@app.route('/api/match', methods=['POST'])
def match_post():
    """Match a hex color via POST body: {"hex": "#RRGGBB"}"""
    data = request.get_json(silent=True)
    if not data or 'hex' not in data:
        return jsonify({'error': 'Missing "hex" field in request body'}), 400

    result = find_closest(data['hex'])
    if result is None:
        return jsonify({'error': 'Invalid hex color value'}), 400

    return jsonify(result)


@app.route('/api/match/<hex_value>')
def match_get(hex_value):
    """Match a hex color via GET: /api/match/C93F38 (no # prefix)"""
    result = find_closest(hex_value)
    if result is None:
        return jsonify({'error': 'Invalid hex color value'}), 400

    return jsonify(result)


@app.route('/api/random')
def random_color():
    global remaining_colors, last_color
    if not remaining_colors:
        remaining_colors = COLOR_CACHE.copy()
        random.shuffle(remaining_colors)
        if last_color and len(remaining_colors) > 1 and remaining_colors[0] == last_color:
            remaining_colors[0], remaining_colors[-1] = remaining_colors[-1], remaining_colors[0]
    color = remaining_colors.pop()
    last_color = color
    hex_upper = color['hex'].upper()
    classification = classify_color(*color['rgb'])
    return jsonify({
        'color': hex_upper,
        'name': color['name'],
        'rgb': list(color['rgb']),
        'family': classification['family'],
        'descriptor': classification['descriptor']
    })


@app.route('/api/accessible', methods=['POST'])
def accessible():
    data = request.get_json(silent=True)
    if not data or 'hex' not in data:
        return jsonify({'error': 'Missing "hex" field'}), 400

    cvd_type = data.get('cvd_type', 'none')
    hex_str = data['hex'].strip().lstrip('#')
    if len(hex_str) != 6:
        return jsonify({'error': 'Invalid hex color value'}), 400
    try:
        int(hex_str, 16)
    except ValueError:
        return jsonify({'error': 'Invalid hex color value'}), 400

    hex_str = f"#{hex_str.upper()}"
    input_rgb = hex_to_rgb(hex_str)
    input_lab = hex_to_lab(hex_str)

    # --- CVD simulations ---
    simulations = {}
    for name, mat in [('protanopia', PROTAN_SIM), ('deuteranopia', DEUTAN_SIM), ('tritanopia', TRITAN_SIM)]:
        sim_rgb = simulate_cvd(input_rgb, mat)
        sim_hex = rgb_to_hex(*sim_rgb).upper()
        sim_class = classify_color(*sim_rgb)
        simulations[name] = {
            'hex': sim_hex,
            'descriptor': sim_class['descriptor'],
        }

    # --- Wong palette distances ---
    wong_labs = []
    for w_hex in WONG_PALETTE:
        w_lab = hex_to_lab(w_hex)
        w_rgb = hex_to_rgb(w_hex)
        w_class = classify_color(*w_rgb)
        d = delta_e_ciede2000(input_lab, w_lab)
        wong_labs.append({
            'hex': w_hex.upper(),
            'lab': w_lab,
            'descriptor': w_class['descriptor'],
            'distance': d,
        })

    # --- Find closest Wong color and replace with input ---
    closest_idx = min(range(len(wong_labs)), key=lambda i: wong_labs[i]['distance'])
    input_class = classify_color(*input_rgb)
    palette = list(wong_labs)
    palette[closest_idx] = {
        'hex': hex_str,
        'lab': input_lab,
        'descriptor': input_class['descriptor'],
        'distance': 0.0,
    }

    # --- Select 5 most spread colors (greedy farthest-point) ---
    selected = [closest_idx]
    remaining = set(range(len(palette)))
    remaining.discard(closest_idx)
    while len(selected) < 5 and remaining:
        best_idx = None
        best_min_dist = -1
        for idx in remaining:
            min_dist = min(
                delta_e_ciede2000(palette[idx]['lab'], palette[s]['lab'])
                for s in selected
            )
            if min_dist > best_min_dist:
                best_min_dist = min_dist
                best_idx = idx
        selected.append(best_idx)
        remaining.discard(best_idx)

    universal_safe = []
    for i, idx in enumerate(selected):
        p = palette[idx]
        role = 'your color' if idx == closest_idx else 'safe pair'
        universal_safe.append({
            'hex': p['hex'],
            'descriptor': p['descriptor'],
            'role': role,
        })

    # --- High contrast pairs (2 Wong colors most distant from input) ---
    wong_by_dist = sorted(wong_labs, key=lambda w: w['distance'], reverse=True)
    high_contrast = []
    for w in wong_by_dist[:2]:
        high_contrast.append({
            'hex': w['hex'],
            'descriptor': w['descriptor'],
            'delta_e': round(w['distance'], 1),
        })

    # --- Personalized simulation if CVD type specified ---
    personal_sim = None
    if cvd_type in simulations:
        personal_sim = {
            'type': cvd_type,
            'hex': simulations[cvd_type]['hex'],
            'descriptor': simulations[cvd_type]['descriptor'],
        }

    return jsonify({
        'input': hex_str,
        'universal_safe': universal_safe,
        'high_contrast': high_contrast,
        'simulations': simulations,
        'personal': personal_sim,
    })


if __name__ == '__main__':
    print(f"What Color API starting on port 5010...")
    app.run(host='0.0.0.0', port=5010, debug=False)
