from __future__ import annotations

from sector_board import create_app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8502, debug=True)
