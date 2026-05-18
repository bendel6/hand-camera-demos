# hand-camera-demos

Two single-file browser demos that turn your webcam into something other than a video chat.

Both are pure HTML — no build step, no dependencies to install. Open them via a
local HTTP server (camera APIs need a secure context; `localhost` counts as
secure, so plain `http://` works).

## Demos

### `camera-themes.html`
The webcam feed is rendered as a low-resolution, color-quantized pixel field
behind the page — you're not recognizable, but your **motion** drives the UI.
Eight themes (minimal, glass, cyberpunk, CRT, brutalism, vaporwave, noir,
arcade), each with its own palette and pixel grain. Frame-to-frame luminance
diff feeds CSS variables that shift the title, pulse the brand light, and tilt
the chrome.

### `pinch-scroll.html`
Use your hand as a mouse. MediaPipe Hands runs in the browser (via jsDelivr CDN).
- **Thumb + index** pinch and move up/down → scroll the page.
- **Index finger** alone → moves a virtual on-screen cursor.
- **Thumb + middle** pinch → click whatever the cursor is over (fires real
  `mousedown` / `mouseup` / `click` events via `document.elementFromPoint`).

Engage / release uses hysteresis to avoid flicker. Scroll is decoupled from the
~30 fps detection loop via a rAF lerp so motion stays smooth. Tuning knobs are
named consts at the top of the script.

## Run

```bash
python3 -m http.server 8000
# then open one of:
#   http://localhost:8000/camera-themes.html
#   http://localhost:8000/pinch-scroll.html
```

Use Chrome or Safari. Grant camera permission when prompted. Everything runs
client-side; no frames leave the device.
