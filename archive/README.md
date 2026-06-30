# Archive

Old work, kept for the record. None of this is the current design. The board you
want is at the [repo root](../).

* **`prototype-protoboard/`** — the original Protogon: a bare protoboard
  hexpansion with no EEPROM and no Qwiic connector. This is what shipped before
  the I²C block was added. Snapshot of the KiCad files only (it referenced the
  shared footprint libraries that now live at the repo root, so it won't open
  standalone without them).
* **`tools/`** — the scripts that built and rendered the prototype:
  `generate_protogon.py` produced the board programmatically (the current board
  is hand-edited in KiCad, so this is superseded), and
  `render_protogon_blender.py` + `render-on-roy.sh` drove a Blender GPU render
  pipeline. We render with `kicad-cli` now, which is truthful about the real
  stackup colors and a lot less trouble.
* **`renders/`** — the Blender output (turntable loop, stills, the EMF backdrop
  photo, the studio HDRI) and the early `kicad-cli` reference renders.
