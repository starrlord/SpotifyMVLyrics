# ── Spotify OAuth ─────────────────────────────────────────────────────────────
# Credentials are stored in .credentials.json (never committed).
# Set them via right-click → Spotify Credentials… inside the overlay.
SPOTIFY_REDIRECT_URI = "http://127.0.0.1:8888/callback"
SPOTIFY_SCOPES       = "user-read-currently-playing user-read-playback-state"

# ── Polling ────────────────────────────────────────────────────────────────────
POLL_INTERVAL_MS = 1000   # How often to ask Spotify what's playing (ms)

# ── Overlay appearance ─────────────────────────────────────────────────────────
OVERLAY_WIDTH         = 860   # px
OVERLAY_HEIGHT        = 260   # px
OVERLAY_LINES_BEFORE  = 2     # Dimmed lines above current
OVERLAY_LINES_AFTER   = 2     # Dimmed lines below current
OVERLAY_BG_ALPHA      = 175   # 0-255 background transparency
OVERLAY_FONT_FAMILY   = "Segoe UI"
OVERLAY_FONT_SIZE_PX  = 22    # Current-line font size
OVERLAY_FONT_SMALL_PX = 16    # Surrounding-line font size
