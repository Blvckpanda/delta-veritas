"""
Niger Delta Environmental Risk Observatory — Portfolio Map Generator.

Produces publication-quality static maps with:
- OSM context layers: state boundaries, major roads, settlements
- NOSDRA spill incidents overlaid
- Dark theme cartography

Usage:
    python src/analysis/map_report.py
    python src/analysis/map_report.py --spills data/processed/nosdra_clean_*.geojson
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "etl"))
import config

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger("map_report")


# ── Style constants ───────────────────────────────────────────────────────
FIG_WIDTH, FIG_HEIGHT = 18, 14
BG_COLOR = "#1a1a2e"
GRID_COLOR = "#333355"
TEXT_COLOR = "#e0e0e0"
AXIS_COLOR = "#666688"
BOUNDARY_COLOR = "#4a4a6a"
BOUNDARY_WIDTH = 0.8
ROAD_COLORS = {
    "trunk": "#ffcc44",
    "primary": "#ee8844",
    "secondary": "#886644",
    "default": "#665544",
}
ROAD_WIDTHS = {
    "trunk": 0.6,
    "primary": 0.4,
    "secondary": 0.25,
    "default": 0.15,
}
SETTLEMENT_SIZES = {
    "city": 80,
    "town": 40,
    "village": 15,
    "default": 10,
}
SETTLEMENT_COLOR = "#88bbdd"
SPILL_COLORS = {
    "crude": "#ff6b35",
    "oil": "#ff6b35",
    "condensate": "#4ecdc4",
    "default": "#888888",
}


def load_geojson(path: Path) -> dict:
    """Load a GeoJSON file."""
    with open(path) as f:
        return json.load(f)


def find_latest(pattern: str, directory: Path) -> Path | None:
    """Find the most recent file matching a glob pattern."""
    files = sorted(directory.glob(pattern))
    return files[-1] if files else None


def _get_spill_color(spill_type: str) -> str:
    """Map spill type to color."""
    st = (spill_type or "").lower()
    return SPILL_COLORS.get(st, SPILL_COLORS["default"])


def _get_road_style(highway: str) -> tuple:
    """Get (color, linewidth) for a road type."""
    hw = (highway or "").lower()
    color = ROAD_COLORS.get(hw, ROAD_COLORS["default"])
    width = ROAD_WIDTHS.get(hw, ROAD_WIDTHS["default"])
    return color, width


def _get_settlement_size(place: str) -> int:
    """Get marker size for settlement type."""
    pl = (place or "").lower()
    return SETTLEMENT_SIZES.get(pl, SETTLEMENT_SIZES["default"])


# ── Drawing functions ─────────────────────────────────────────────────────

def draw_boundaries(ax, boundaries_fc: dict):
    """Draw state boundary polygons/lines."""
    labeled_states = set()
    for feat in boundaries_fc.get("features", []):
        geom = feat.get("geometry")
        if not geom:
            continue
        name = feat["properties"].get("name", "")
        # Skip non-Niger-Delta states
        if name not in ["Akwa Ibom", "Bayelsa", "Cross River", "Delta",
                         "Edo", "Imo", "Ondo", "Rivers"]:
            continue

        coords = _extract_coords(geom)
        for ring in coords:
            xs, ys = zip(*ring, strict=False) if ring else ([], [])
            ax.plot(xs, ys, color=BOUNDARY_COLOR, linewidth=BOUNDARY_WIDTH,
                    linestyle="-", alpha=0.7, zorder=2)

        # Label centroid — only once per state
        if name not in labeled_states and coords:
            ring = coords[int(len(coords) / 2)]  # use middle ring
            cx = sum(p[0] for p in ring) / len(ring)
            cy = sum(p[1] for p in ring) / len(ring)
            ax.text(cx, cy, name, fontsize=9, color=TEXT_COLOR,
                    alpha=0.7, ha="center", va="center", zorder=3,
                    style="italic", fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.15", facecolor=BG_COLOR,
                              edgecolor=BOUNDARY_COLOR, alpha=0.6))
            labeled_states.add(name)


def draw_roads(ax, roads_fc: dict, max_features: int = 500):
    """Draw major roads (sample if too many)."""
    features = roads_fc.get("features", [])
    if len(features) > max_features:
        import random
        random.seed(42)
        features = random.sample(features, max_features)
        total = len(roads_fc["features"])
        logger.info("  Sampled %d/%d roads for performance", max_features, total)

    for feat in features:
        geom = feat.get("geometry")
        if not geom or geom.get("type") != "LineString":
            continue
        coords = geom.get("coordinates", [])
        if len(coords) < 2:
            continue
        xs, ys = zip(*coords, strict=False)
        highway = feat["properties"].get("highway", "")
        color, width = _get_road_style(highway)
        ax.plot(xs, ys, color=color, linewidth=width, alpha=0.35, zorder=1)


def draw_settlements(ax, settlements_fc: dict, max_features: int = 200):
    """Draw settlement points (filter by size)."""
    features = settlements_fc.get("features", [])
    # Sort by settlement size (city first), take top N
    def _place_rank(f):
        p = (f["properties"].get("place") or "").lower()
        ranks = {"city": 0, "town": 1, "village": 2}
        return ranks.get(p, 3)
    features.sort(key=_place_rank)
    features = features[:max_features]

    for feat in features:
        geom = feat.get("geometry")
        if not geom or geom.get("type") != "Point":
            continue
        coords = geom.get("coordinates", [None, None])
        if None in coords:
            continue
        place = feat["properties"].get("place", "")
        name = feat["properties"].get("name", "")
        size = _get_settlement_size(place)
        ax.scatter(coords[0], coords[1], s=size, color=SETTLEMENT_COLOR,
                   alpha=0.5, edgecolors="white", linewidth=0.2, zorder=3)

        # Label cities and towns
        if place in ("city", "town") and name:
            ax.text(coords[0] + 0.02, coords[1] + 0.02, name, fontsize=7,
                    color=TEXT_COLOR, alpha=0.7, zorder=4,
                    bbox=dict(boxstyle="round,pad=0.1", facecolor=BG_COLOR,
                              edgecolor="none", alpha=0.6))


def draw_spills(ax, spills_fc: dict):
    """Draw spill incident points, colored by type, sized by quantity."""
    features = spills_fc.get("features", [])
    if not features:
        logger.warning("No spill features to plot")
        return

    lons, lats, colors, sizes = [], [], [], []
    for feat in features:
        geom = feat.get("geometry")
        if not geom or geom.get("type") != "Point":
            continue
        coords = geom.get("coordinates", [None, None])
        if None in coords:
            continue
        p = feat["properties"]
        spill_type = p.get("spill_type", p.get("contaminant", ""))

        lons.append(coords[0])
        lats.append(coords[1])
        colors.append(_get_spill_color(spill_type))

        qty = p.get("quantity_spilled") or 0
        # Size: 20–180 px based on quantity
        size = max(20, min(180, (qty / 100) * 30 + 20))
        sizes.append(size)

    ax.scatter(lons, lats, s=sizes, c=colors, alpha=0.75,
               edgecolors="white", linewidth=0.5, zorder=5)


def draw_legend(ax):
    """Add a custom map legend using proxy artists."""
    from matplotlib.patches import Circle

    legend_elements = [
        # Road types
        Line2D([0], [0], color=ROAD_COLORS["trunk"], linewidth=2.5,
               label="Trunk road"),
        Line2D([0], [0], color=ROAD_COLORS["primary"], linewidth=2,
               label="Primary road"),
        Line2D([0], [0], color=ROAD_COLORS["secondary"], linewidth=1.5,
               label="Secondary road"),
        # Spills
        Circle((0, 0), radius=6, facecolor=SPILL_COLORS["crude"],
               edgecolor="white", linewidth=0.5, label="Oil spill"),
        Circle((0, 0), radius=6, facecolor=SPILL_COLORS["condensate"],
               edgecolor="white", linewidth=0.5, label="Condensate spill"),
        # Settlements
        Circle((0, 0), radius=4, facecolor=SETTLEMENT_COLOR, alpha=0.6,
               edgecolor="white", linewidth=0.3, label="Settlement"),
        # Admin
        Line2D([0], [0], color=BOUNDARY_COLOR, linewidth=1.5, linestyle="-",
               label="State boundary"),
    ]
    legend = ax.legend(
        handles=legend_elements, loc="lower left", framealpha=0.85,
        facecolor="#222244", edgecolor="#444466", labelcolor=TEXT_COLOR,
        fontsize=8, title="Map Legend", title_fontsize=9,
        ncol=2,  # two columns for compactness
    )
    legend.get_title().set_color(TEXT_COLOR)


def _extract_coords(geom: dict) -> list[list[tuple]]:
    """Extract coordinate rings from any geometry type."""
    gtype = geom.get("type", "")
    coords = geom.get("coordinates", [])

    if gtype == "Polygon":
        return [[(c[0], c[1]) for c in ring] for ring in coords]
    elif gtype == "MultiPolygon":
        rings = []
        for polygon in coords:
            for ring in polygon:
                rings.append([(c[0], c[1]) for c in ring])
        return rings
    return []


# ── Main map generation ───────────────────────────────────────────────────

def generate_portfolio_map(
    spills_path: Path | None = None,
    boundaries_path: Path | None = None,
    roads_path: Path | None = None,
    settlements_path: Path | None = None,
    output_dir: Path | None = None,
) -> Path | None:
    """Generate a portfolio-quality static map with all context layers."""
    data_dir = config.DATA_PROCESSED
    if output_dir is None:
        output_dir = data_dir

    # Find input files
    spills_path = spills_path or find_latest("nosdra_clean_*.geojson", data_dir)
    boundaries_path = boundaries_path or find_latest("osm_boundaries_*.geojson", data_dir)
    roads_path = roads_path or find_latest("osm_roads_*.geojson", data_dir)
    settlements_path = settlements_path or find_latest("osm_settlements_*.geojson", data_dir)

    missing = []
    for name, p in [("Spills", spills_path), ("Boundaries", boundaries_path),
                     ("Roads", roads_path), ("Settlements", settlements_path)]:
        if p is None or not p.exists():
            missing.append(name)

    if missing:
        logger.error("Missing input files: %s", ", ".join(missing))
        logger.info("Run src/etl/osm_pipeline.py and src/etl/nosdra_pipeline.py first")
        return None

    logger.info("Loading data layers:")
    spills_fc = load_geojson(spills_path)
    logger.info("  Spills: %s (%d features)", spills_path.name,
                len(spills_fc.get("features", [])))
    boundaries_fc = load_geojson(boundaries_path)
    logger.info("  Boundaries: %s (%d features)", boundaries_path.name,
                len(boundaries_fc.get("features", [])))
    roads_fc = load_geojson(roads_path)
    logger.info("  Roads: %s (%d features)", roads_path.name,
                len(roads_fc.get("features", [])))
    settlements_fc = load_geojson(settlements_path)
    logger.info("  Settlements: %s (%d features)", settlements_path.name,
                len(settlements_fc.get("features", [])))

    # ── Create figure ─────────────────────────────────────────────────
    fig, ax = plt.subplots(1, 1, figsize=(FIG_WIDTH, FIG_HEIGHT))
    fig.patch.set_facecolor(BG_COLOR)
    ax.set_facecolor(BG_COLOR)

    # ── Draw layers (bottom to top) ───────────────────────────────────
    logger.info("Drawing boundaries...")
    draw_boundaries(ax, boundaries_fc)

    logger.info("Drawing roads...")
    draw_roads(ax, roads_fc)

    logger.info("Drawing settlements...")
    draw_settlements(ax, settlements_fc)

    logger.info("Drawing spills...")
    draw_spills(ax, spills_fc)

    # ── Map extent ────────────────────────────────────────────────────
    # Focus on core Niger Delta
    ax.set_xlim(4.5, 9.0)
    ax.set_ylim(4.0, 7.0)
    ax.set_aspect("equal")

    # ── Grid and axes styling ─────────────────────────────────────────
    ax.set_xlabel("Longitude", color=AXIS_COLOR, fontsize=10)
    ax.set_ylabel("Latitude", color=AXIS_COLOR, fontsize=10)
    ax.tick_params(colors=AXIS_COLOR, labelsize=8)
    ax.grid(True, color=GRID_COLOR, linewidth=0.3, alpha=0.5)

    for spine in ax.spines.values():
        spine.set_color(GRID_COLOR)

    # ── Scale bar ─────────────────────────────────────────────────────
    # Approx: at 5°N, 1° longitude ≈ 111km
    scale_bar_km = 50
    scale_bar_deg = scale_bar_km / 111.0
    sb_x, sb_y = 4.7, 4.15
    ax.plot([sb_x, sb_x + scale_bar_deg], [sb_y, sb_y],
            color=TEXT_COLOR, linewidth=2, zorder=10)
    ax.plot([sb_x, sb_x], [sb_y - 0.02, sb_y + 0.02],
            color=TEXT_COLOR, linewidth=1.5, zorder=10)
    ax.plot([sb_x + scale_bar_deg, sb_x + scale_bar_deg],
            [sb_y - 0.02, sb_y + 0.02], color=TEXT_COLOR, linewidth=1.5, zorder=10)
    ax.text(sb_x + scale_bar_deg / 2, sb_y - 0.07, f"{scale_bar_km} km",
            ha="center", color=TEXT_COLOR, fontsize=8, zorder=10)

    # ── North arrow ───────────────────────────────────────────────────
    na_x, na_y = 8.7, 6.8
    ax.annotate("", xy=(na_x, na_y + 0.3), xytext=(na_x, na_y),
                arrowprops=dict(arrowstyle="->", color=TEXT_COLOR, lw=2),
                zorder=10)
    ax.text(na_x, na_y + 0.35, "N", ha="center", va="bottom",
            color=TEXT_COLOR, fontsize=10, fontweight="bold", zorder=10)

    # ── Legend ────────────────────────────────────────────────────────
    draw_legend(ax)

    # ── Titles ────────────────────────────────────────────────────────
    ax.set_title(
        "Niger Delta — Oil Spill Incidents & Infrastructure Context",
        color=TEXT_COLOR, fontsize=16, fontweight="bold", pad=12,
    )

    # Subtitle / metadata block
    timestamp = datetime.now().strftime("%B %Y")
    num_spills = len([f for f in spills_fc.get("features", [])
                     if f.get("geometry")])
    summary_text = (
        f"Generated by Niger Delta Environmental Risk Observatory\n"
        f"{timestamp}  |  {num_spills} spill incidents mapped\n"
        f"Data: NOSDRA, OpenStreetMap  |  Built from Port Harcourt"
    )
    fig.text(
        0.15, 0.02, summary_text, ha="left", color=AXIS_COLOR, fontsize=7,
        fontfamily="monospace",
    )

    # Ethical note
    fig.text(
        0.85, 0.02, "Context layers: settlements, roads, boundaries only",
        ha="right", color=AXIS_COLOR, fontsize=6, fontstyle="italic",
    )

    fig.tight_layout(rect=[0, 0.04, 1, 1])

    # ── Save ──────────────────────────────────────────────────────────
    out_path = output_dir / f"portfolio_map_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    fig.savefig(out_path, dpi=200, bbox_inches="tight", facecolor=BG_COLOR)
    file_size_kb = out_path.stat().st_size / 1024
    logger.info("Map saved: %s (%.0f KB, %ddpi)", out_path, file_size_kb, 200)
    plt.close(fig)
    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate portfolio map")
    parser.add_argument("--spills", type=Path, help="Spill GeoJSON")
    parser.add_argument("--boundaries", type=Path, help="Boundary GeoJSON")
    parser.add_argument("--roads", type=Path, help="Road GeoJSON")
    parser.add_argument("--settlements", type=Path, help="Settlement GeoJSON")
    parser.add_argument("--output", type=Path, help="Output directory")
    args = parser.parse_args()

    result = generate_portfolio_map(
        spills_path=args.spills,
        boundaries_path=args.boundaries,
        roads_path=args.roads,
        settlements_path=args.settlements,
        output_dir=args.output,
    )
    if result:
        logger.info("Done." if result else "Failed.")
