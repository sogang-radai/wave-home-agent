"""Render Mermaid diagrams for every LangGraph graph in app/graph/.

Usage:
    python scripts/render_graphs.py            # writes .mmd + .png to docs/graphs/
    python scripts/render_graphs.py --mmd-only  # skip PNG (no network call)
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.graph import report_turn_graph, turn_graph
from app.graph.tools import build_tools

OUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "graphs"

GRAPH_BUILDERS = {
    "turn_graph": lambda: turn_graph.build_chat_graph(build_tools(user_id=0)),
    "report_turn_graph": report_turn_graph.build,
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mmd-only", action="store_true", help="skip PNG rendering (no network call)")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, build in GRAPH_BUILDERS.items():
        drawable = build().get_graph()

        mmd_path = OUT_DIR / f"{name}.mmd"
        mmd_path.write_text(drawable.draw_mermaid())
        print(f"wrote {mmd_path}")

        if not args.mmd_only:
            png_path = OUT_DIR / f"{name}.png"
            png_path.write_bytes(drawable.draw_mermaid_png())
            print(f"wrote {png_path}")


if __name__ == "__main__":
    main()
