from __future__ import annotations

import pandas as pd


class KiwoomWebSocketClient:
    """Placeholder for a future real-time market data adapter."""

    def stream_current_prices(self, codes: list[str]) -> pd.DataFrame:
        # TODO: Replace REST polling with Kiwoom WebSocket subscriptions after
        # confirming the latest official WebSocket endpoints, auth flow, and
        # message schema. Keep the returned columns identical to market_data.
        raise NotImplementedError("WebSocket streaming is planned after the REST polling MVP.")
