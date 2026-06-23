# De-risk findings — Qwiic + EEPROM variant

Three questions answered orthogonally to the routing/schematic work: does the EEPROM
actually work with the badge firmware, what are the real parts, and does the board fit.
Verified 2026-06-22 by file inspection + adversarial cross-check (firmware read from the
real `emfcamp/badge-2024-software`, not the README).

## 1. EEPROM premise — CONFIRMED works (high confidence)

A **CAT24C512 at I²C `0x50` works** with the badge's identify / read / install-software path.

- **16-bit word addressing, end to end.** A lone `0x50` device makes `detect_eeprom_addr()`
  return `addr_len = 2`; that flows through every read/write/install call (`addrsize = addr_len*8 = 16`),
  so the **full 64 KB is reachable**. The 8-bit path fires only when all of `0x50–0x57` answer
  (a self-aliasing small part like M24C16) — which a 512 kbit part never does.
- **Largest supported single chip.** `T24C512 = 65536` is the top of the driver whitelist and
  sits exactly at the `2**16` boundary (clamp uses strict `>`), so it survives un-truncated.
  Anything strictly larger than 64 KB would be only partially addressable.
- **`0x50` strap is clean.** No I²C mux on the per-slot hexpansion bus (the only `0x70/0x77`
  references are inert comments on a different bus). `WP→GND` = write-enabled, which the
  firmware needs to format the LittleFS image and install the app.

**Action before provisioning (firmware-side, not a board change):**
- `modules/scripts/prepare_eeprom.py` defaults to `header = header_m24c16`. Switch it to
  `header = header_cat24c512` and set the I²C `port`. The shipped `header_cat24c512` template
  (`page_size=128`, `total_size=65536`) matches the real part — use as-is.
- Run a one-off on-badge smoke test (`prepare_eeprom.py` → `mount_hexpansions.py`): CAT24C512 is
  supported and templated but **less exercised** than the small defaults, so format+mount it once
  before committing the design.

## 2. Parts — locked, with one README correction

Orderable table with MPN + LCSC + Basic/Extended and datasheet-verified pinouts:
**`codemyriad-protogon-qwiic-bom.csv`**.

- U1 **CAT24C512WI-GT3** (LCSC **C79986**, Extended) — pinout matches the board's pad-nets exactly.
- R1/R2 **10 k 0603** (C25804, Basic) · C1 **100 n 0603 X7R** (C14663, Basic).
- J3 **SM04B-SRSS-TB** (C160404, Extended) — confirmed the correct **side-entry SMD** Qwiic mate
  (not the vertical or THT variant). JLCPCB flags "assembly fixture needed."

> **Correction for the variant README:** it lists **ZD24C64A-XGMT** as a "footprint-compatible"
> smaller alternate. That part is **TSSOP-8 (0.65 mm pitch), NOT SOIC-8** — it will not fit U1's
> pads. The correct SOIC/SOP-8 drop-ins are **Zetta ZD24C64A-SSGMB** (C2837682) or **Microchip
> AT24C512C-SSHD-T** (C12371). Wiring is the same 24Cxx; only the package was misstated.

Live-check before order: U1 and J3 are JLCPCB **Extended** — confirm stock + per-part loading fee
on the day; J3 may need an assembly fixture.

## 3. Mechanical fit — automated verdict WALKED BACK; physical test still required

An automated envelope check first returned "doesn't fit (ear ~17.6 mm past the envelope)".
**That verdict is not trustworthy** and is corrected here:

- It compared the board to the **standard "Hextension template"** outline and **dismissed the
  "Hextension hextended — not recommended to exceed this area"** outline — which is precisely the
  envelope that governs **radial** growth, and this ear grows radially.
- Its big numbers **conflate inherited geometry with the rework.** Measured fact: the qwiic
  `Edge.Cuts` is the base board's outline (both `x[100..148]`, `y[81.679..118.320]`, `h=36.641 mm`)
  **plus a 6 mm radial ear** (right edge 148 → 154 mm). **The only mechanical change this variant
  introduces is +6 mm radial.** The hex body is byte-for-byte the proven base outline.

What the files **cannot** settle: whether the board (base hex body + 6 mm ear) sits inside the
"hextended" max envelope. There is a ~11 mm discrepancy between the board's radial length and the
standard template's that on-screen registration/scale uncertainty can't resolve — and it applies to
the **base board too** (hex body inherited; the base board's own fit-test is a documented pending
gate, not a qwiic regression).

**Decisive check (always the gate — now scoped):** print
`../official-hexpansion-paper-template.svg` at **1:1** and lay the real board (or a 1:1 board print)
on it, registered on the edge connector. Confirm:
1. the **hex body** sits within the maroon **"template"** outline → validates the base design;
2. the **6 mm ear** stays within the light-blue **"hextended"** outline and clears a neighbour slot
   on a populated badge → validates the qwiic delta.

Two minutes, and it resolves what the on-screen check cannot.
