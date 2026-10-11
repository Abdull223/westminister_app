"""Pen-pad signature capture built as an inline Custom Components v2 element."""

import base64

import streamlit as st

_HTML = """
<div class="pad">
  <canvas id="sig-canvas" width="440" height="150"></canvas>
  <div class="bar">
    <span id="sig-hint">Draw the partner signature with mouse or touch</span>
    <button id="sig-clear" type="button">Clear</button>
  </div>
</div>
"""

_CSS = """
.pad { font-family: var(--st-font, sans-serif); }
#sig-canvas {
  display: block; background: #FFFFFF; border: 1px dashed var(--st-primary-color, #C9A24F);
  border-radius: 8px; touch-action: none; cursor: crosshair; max-width: 100%;
}
.bar { display: flex; align-items: center; justify-content: space-between; margin-top: 6px; }
#sig-hint { color: var(--st-secondary-text-color, #8FA3B8); font-size: 12px; }
#sig-clear {
  background: transparent; color: var(--st-text-color, #E8EDF2); border: 1px solid var(--st-border-color, #1E3A57);
  border-radius: 6px; padding: 3px 12px; font-size: 12px; cursor: pointer;
}
#sig-clear:hover { border-color: var(--st-primary-color, #C9A24F); }
"""

_JS = """\
export default function (component) {
  const { data, parentElement, setStateValue } = component
  const canvas = parentElement.querySelector("#sig-canvas")
  const clearBtn = parentElement.querySelector("#sig-clear")
  if (!canvas || !clearBtn) return

  const ctx = canvas.getContext("2d")
  const W = canvas.width, H = canvas.height
  const dpr = window.devicePixelRatio || 1
  canvas.width = W * dpr
  canvas.height = H * dpr
  canvas.style.width = W + "px"
  canvas.style.height = H + "px"
  ctx.scale(dpr, dpr)
  ctx.lineWidth = 2.5
  ctx.lineCap = "round"
  ctx.lineJoin = "round"
  ctx.strokeStyle = "#101820"

  const existing = data && data.png
  if (existing) {
    const img = new Image()
    img.onload = () => ctx.drawImage(img, 0, 0, W, H)
    img.src = existing
  }

  let drawing = false
  let last = null
  const pos = (e) => {
    const r = canvas.getBoundingClientRect()
    return { x: e.clientX - r.left, y: e.clientY - r.top }
  }

  canvas.addEventListener("pointerdown", (e) => {
    drawing = true
    last = pos(e)
    canvas.setPointerCapture(e.pointerId)
    e.preventDefault()
  })
  canvas.addEventListener("pointermove", (e) => {
    if (!drawing) return
    const p = pos(e)
    ctx.beginPath()
    ctx.moveTo(last.x, last.y)
    ctx.lineTo(p.x, p.y)
    ctx.stroke()
    last = p
  })
  const commit = () => {
    if (!drawing) return
    drawing = false
    setStateValue("png", canvas.toDataURL("image/png"))
  }
  canvas.addEventListener("pointerup", commit)
  canvas.addEventListener("pointercancel", commit)
  clearBtn.addEventListener("click", () => {
    ctx.clearRect(0, 0, W, H)
    setStateValue("png", null)
  })
}
"""

_MOUNT = st.components.v2.component("wc_signature_pad", html=_HTML, css=_CSS, js=_JS)


def signature_pad(key: str = "partner_signature") -> bytes | None:
    """Render the pen pad; returns PNG bytes of the signature, or None."""
    state = st.session_state.get(key, {})
    result = _MOUNT(
        key=key,
        data={"png": state.get("png")},
        on_png_change=lambda: None,
    )
    if result.png:
        return base64.b64decode(result.png.split(",", 1)[1])
    return None
