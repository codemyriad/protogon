#!/usr/bin/env python3
"""Generate the Code Myriad Protogon KiCad board from the EMF template."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pcbnew


ROOT = Path(__file__).resolve().parents[1]
LOGO_JSON = Path(__file__).resolve().parent / "codemyriad-logo.json"
UPSTREAM = ROOT / "_upstream_badge_2024_hardware" / "hexpansion"
OUT = ROOT / "codemyriad-protogon"

BOARD_IN = UPSTREAM / "hexpansion.kicad_pcb"
BOARD_OUT = OUT / "codemyriad-protogon.kicad_pcb"


def mm(value: float) -> int:
    return pcbnew.FromMM(value)


def v(x: float, y: float) -> pcbnew.VECTOR2I:
    return pcbnew.VECTOR2I(mm(x), mm(y))


def net(board: pcbnew.BOARD, name: str) -> pcbnew.NETINFO_ITEM:
    item = board.FindNet(name)
    if item is None:
        item = pcbnew.NETINFO_ITEM(board, name)
        board.Add(item)
    return item


def clear_generated_items(board: pcbnew.BOARD) -> None:
    keep_refs = {"J1", "J2", "H1", "H2"}

    drawings_to_remove = list(board.GetDrawings())
    zones_to_remove = list(board.Zones())
    all_footprints = list(board.GetFootprints())
    for fp in all_footprints:
        if fp.GetReference() in {"H1", "H2"}:
            for pad in fp.Pads():
                pad.SetNetCode(0)
        if fp.GetReference() == "J1":
            # Hide the edge connector's TOP / BOTTOM / pin-1 silk text: it sits in
            # the connector wing (x~104) where the branding now goes. Orientation
            # stays obvious from the board shape and the PROTOGON/emblem branding.
            # Done here, where GetFootprints() still yields wrapped FOOTPRINT objects
            # (a later GetFootprints() call returns un-downcast SWIG pointers).
            fp.Reference().SetVisible(False)
            fp.Value().SetVisible(False)
            # Move (don't structurally remove -- that corrupts the SWIG board state
            # mid-iteration) the silk text off the silkscreen to a non-plotted layer.
            for item in list(fp.GraphicalItems()):
                if (isinstance(item, pcbnew.PCB_TEXT)
                        and item.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS)):
                    item.SetLayer(pcbnew.Cmts_User)
    footprints_to_remove = [
        fp for fp in all_footprints if fp.GetReference() not in keep_refs
    ]
    tracks_to_remove = stale_example_tracks(board)

    for drawing in drawings_to_remove:
        board.Remove(drawing)

    for zone in zones_to_remove:
        board.Remove(zone)

    seen = set()
    for track in tracks_to_remove:
        ident = id(track)
        if ident in seen:
            continue
        seen.add(ident)
        board.Remove(track)

    for fp in footprints_to_remove:
        board.Remove(fp)


def set_board_settings(board: pcbnew.BOARD) -> None:
    board.GetDesignSettings().SetBoardThickness(mm(1.0))
    board.SetTitleBlock(pcbnew.TITLE_BLOCK())
    title = board.GetTitleBlock()
    title.SetTitle("Code Myriad Protogon")
    title.SetCompany("Code Myriad")
    title.SetComment(0, "Functional protoboard hexpansion for EMF Tildagon / Spaceagon")
    title.SetComment(1, "Based on EMF badge-2024-hardware hexpansion template, CERN-OHL-P-2.0")
    title.SetComment(2, "Order as 1.0 mm FR4, ENIG, purple soldermask, white silkscreen")

    plot = board.GetPlotOptions()
    plot.SetOutputDirectory("fabrication/gerbers")
    plot.SetUseGerberProtelExtensions(True)
    plot.SetCreateGerberJobFile(True)
    plot.SetUseGerberX2format(True)
    plot.SetSubtractMaskFromSilk(True)


def set_detect_to_ground(board: pcbnew.BOARD) -> None:
    gnd = net(board, "/GND")
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetname() == "/HEXP_DET":
                pad.SetNet(gnd)
    for track in tracks(board):
        if track.GetNetname() == "/HEXP_DET":
            track.SetNet(gnd)


def stale_example_tracks(board: pcbnew.BOARD) -> list[pcbnew.PCB_TRACK]:
    # After deleting the example LED/resistor/jumper, remove dangling tracks that
    # only went to those footprints. Existing J1->J2 breakout tracks are kept.
    stale = []
    for track in tracks(board):
        name = track.GetNetname()
        sx, sy = track.GetStart().x / 1e6, track.GetStart().y / 1e6
        ex, ey = track.GetEnd().x / 1e6, track.GetEnd().y / 1e6
        if name in {"Net-(D1-A)"}:
            stale.append(track)
        if name == "/GND" and abs(sx - 106.25) < 0.02 and abs(ex - 106.25) < 0.02:
            # Ground stitching vias from the template depended on the removed
            # copper zone.
            stale.append(track)
        if name == "/GND" and (
            86.0 < sy < 87.2 or 86.0 < ey < 87.2 or 113.8 < sy < 115.2 or 113.8 < ey < 115.2
        ):
            # Mounting-hole ground spokes from the template zone.
            stale.append(track)
        if name == "/GND" and (
            abs(sx - 122.865) < 0.02 or abs(ex - 122.865) < 0.02
        ) and (89.0 < sy < 111.0 or 89.0 < ey < 111.0):
            # Local GND bus beside J2 blocks the 3V3 rail feed channel. The
            # remaining GND breakouts are still tied through the connector fanout
            # and the added bottom rail route.
            stale.append(track)
        if name == "/GND" and (sx > 127 or ex > 127) and (92.0 < sy < 99.5 or 92.0 < ey < 99.5):
            # Stale detect-jumper route after hard-tying HEXP_DET to GND.
            stale.append(track)
        if name == "/GND" and (
            (121.5 < sx < 123.0 and 103.6 < sy < 104.0)
            or (121.5 < ex < 123.0 and 103.6 < ey < 104.0)
        ) and abs(sy - ey) < 0.02:
            # Last stub from the removed template-local GND bus.
            stale.append(track)
        if name == "/GND" and (sx > 127 or ex > 127) and (99.5 < sy < 106 or 99.5 < ey < 106):
            # Example LED ground route.
            stale.append(track)
        if name == "/3V3" and (sx > 125 or ex > 125) and (102 < sy < 106 or 102 < ey < 106):
            # Example LED resistor supply route.
            stale.append(track)
        if name == "/3V3" and (sx > 121 or ex > 121) and (101.0 < sy < 103.2 or 101.0 < ey < 103.2):
            # Back-side LED resistor branch.
            stale.append(track)
    return stale


def tracks(board: pcbnew.BOARD) -> list[pcbnew.PCB_TRACK]:
    items = board.Tracks()
    return [items[i] for i in range(items.size())]


def add_line(board: pcbnew.BOARD, start: tuple[float, float], end: tuple[float, float],
             layer: int = pcbnew.Edge_Cuts, width: float = 0.05) -> None:
    shape = pcbnew.PCB_SHAPE(board)
    shape.SetShape(pcbnew.SHAPE_T_SEGMENT)
    shape.SetLayer(layer)
    shape.SetStart(v(*start))
    shape.SetEnd(v(*end))
    shape.SetWidth(mm(width))
    board.Add(shape)


def add_arc(board: pcbnew.BOARD, start: tuple[float, float], mid: tuple[float, float],
            end: tuple[float, float], layer: int = pcbnew.Edge_Cuts, width: float = 0.05) -> None:
    shape = pcbnew.PCB_SHAPE(board)
    shape.SetShape(pcbnew.SHAPE_T_ARC)
    shape.SetLayer(layer)
    shape.SetArcGeometry(v(*start), v(*mid), v(*end))
    shape.SetWidth(mm(width))
    board.Add(shape)


def add_text(board: pcbnew.BOARD, text: str, at: tuple[float, float],
             size: float = 1.0, layer: int = pcbnew.F_SilkS,
             angle: float = 0.0, bold: bool = False, align: str = "center") -> None:
    item = pcbnew.PCB_TEXT(board)
    item.SetText(text)
    item.SetLayer(layer)
    item.SetPosition(v(*at))
    item.SetTextAngle(pcbnew.EDA_ANGLE(angle, pcbnew.DEGREES_T))
    item.SetTextSize(v(size, size))
    item.SetTextThickness(mm(0.15 if not bold else 0.22))
    item.SetBold(bold)
    if align == "left":
        item.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_LEFT)
    elif align == "right":
        item.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_RIGHT)
    else:
        item.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER)
    item.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER)
    if layer in {pcbnew.B_SilkS, pcbnew.B_Cu, pcbnew.B_Mask}:
        item.SetMirrored(True)
    board.Add(item)


def add_circle(board: pcbnew.BOARD, center: tuple[float, float], radius: float,
               layer: int = pcbnew.F_SilkS, width: float = 0.2) -> None:
    shape = pcbnew.PCB_SHAPE(board)
    shape.SetShape(pcbnew.SHAPE_T_CIRCLE)
    shape.SetLayer(layer)
    shape.SetCenter(v(*center))
    shape.SetRadius(mm(radius))
    shape.SetWidth(mm(width))
    board.Add(shape)


def add_expanded_outline(board: pcbnew.BOARD) -> None:
    # Left side follows the official hexpansion template so it mates with the
    # edge connector footprint's tab/ears. The right side carries one integrated
    # 10x14 pad matrix, matching the Protoboard Hexpansion approach.
    x_right = 148.0
    y_top = 81.813472
    y_bottom = 118.186522

    add_line(board, (100.5, 90.473725), (115.499995, y_top))
    add_arc(board, (115.499995, y_top), (115.999995, 81.679497), (116.499995, y_top))
    add_line(board, (116.499995, y_top), (x_right, y_top))
    add_line(board, (x_right, y_top), (x_right, y_bottom))
    add_line(board, (x_right, y_bottom), (116.499995, y_bottom))
    add_arc(board, (116.499995, y_bottom), (115.999995, 118.320497), (115.499995, y_bottom))
    add_line(board, (115.499995, y_bottom), (100.5, 109.526269))
    add_arc(board, (100.5, 109.526269), (100.133975, 109.160243), (100.0, 108.660243))
    add_line(board, (100.0, 108.660243), (100.0, 106.25))
    add_arc(board, (100.0, 106.25), (100.073223, 106.073223), (100.25, 106.0), width=0.1)
    add_arc(board, (100.25, 94.0), (100.073223, 93.926777), (100.0, 93.75), width=0.1)
    add_line(board, (100.0, 93.75), (100.0, 91.33975))
    add_arc(board, (100.0, 91.33975), (100.133975, 90.83975), (100.5, 90.473725))


def make_pad(fp: pcbnew.FOOTPRINT, number: str, at: tuple[float, float],
             net_item: pcbnew.NETINFO_ITEM | None, shape: int = pcbnew.PAD_SHAPE_CIRCLE,
             size: float = 1.65, drill: float = 1.0) -> pcbnew.PAD:
    pad = pcbnew.PAD(fp)
    pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    pad.SetShape(shape)
    pad.SetSize(v(size, size))
    pad.SetDrillSize(v(drill, drill))
    pad.SetLayerSet(pcbnew.LSET.AllCuMask())
    pad.SetPosition(v(*at))
    pad.SetNumber(number)
    if net_item is not None:
        pad.SetNet(net_item)
    fp.Add(pad)
    return pad


def add_proto_grid(board: pcbnew.BOARD) -> None:
    gnd = net(board, "/GND")
    p3v3 = net(board, "/3V3")

    fp = pcbnew.FOOTPRINT(board)
    fp.SetReference("PROTO1")
    fp.SetValue("integrated 10x14 protoboard grid")
    fp.SetPosition(v(0, 0))
    fp.SetLayer(pcbnew.F_Cu)
    fp.SetAttributes(pcbnew.FP_THROUGH_HOLE)

    # J2 occupies columns 0-1 and rows 2-11 of the 10x14 matrix.
    x0 = 121.69
    y0 = 83.47
    pitch = 2.54
    idx = 1
    for row in range(14):
        for col in range(10):
            if row in range(2, 12) and col in {0, 1}:
                continue
            ni = None
            shape = pcbnew.PAD_SHAPE_CIRCLE
            if row == 0:
                ni = p3v3
                shape = pcbnew.PAD_SHAPE_OVAL
            elif row == 13:
                ni = gnd
                shape = pcbnew.PAD_SHAPE_OVAL
            make_pad(fp, str(idx), (x0 + col * pitch, y0 + row * pitch), ni, shape=shape)
            idx += 1

    board.Add(fp)

    rail_left = x0
    rail_right = x0 + 9 * pitch
    add_track(board, (rail_left, y0), (rail_right, y0), "/3V3", width=0.8, layer=pcbnew.F_Cu)
    add_track(board, (rail_left, y0 + 13 * pitch), (rail_right, y0 + 13 * pitch), "/GND", width=0.8, layer=pcbnew.F_Cu)

    # Connect rails to existing badge power nets through routing channels
    # between matrix pads.
    channel_x = x0 + 4.5 * pitch
    add_track(board, (121.69, 101.25), (121.69, 100.0), "/3V3", width=0.25, layer=pcbnew.F_Cu)
    add_track(board, (121.69, 100.0), (channel_x, 100.0), "/3V3", width=0.25, layer=pcbnew.F_Cu)
    add_track(board, (channel_x, 100.0), (channel_x, y0), "/3V3", width=0.25, layer=pcbnew.F_Cu)
    add_track(board, (channel_x, y0), (rail_left, y0), "/3V3", width=0.25, layer=pcbnew.F_Cu)

    add_track(board, (124.23, 111.41), (125.5, 112.68), "/GND", width=0.25, layer=pcbnew.B_Cu)
    add_track(board, (125.5, 112.68), (125.5, y0 + 13 * pitch), "/GND", width=0.25, layer=pcbnew.B_Cu)
    add_track(board, (125.5, y0 + 13 * pitch), (rail_left, y0 + 13 * pitch), "/GND", width=0.25, layer=pcbnew.B_Cu)

    # Tie the duplicate GND connector contacts together locally. The bus runs
    # between the J2 right column and the first free prototyping column, where
    # it clears both 1.65 mm pads at standard fab clearances.
    add_track(board, (125.5, 88.55), (125.5, y0 + 13 * pitch), "/GND", width=0.25, layer=pcbnew.B_Cu)
    add_track(board, (124.23, 88.55), (125.5, 88.55), "/GND", width=0.25, layer=pcbnew.B_Cu)
    add_track(board, (124.23, 98.71), (125.5, 98.71), "/GND", width=0.25, layer=pcbnew.B_Cu)
    add_track(board, (121.69, 96.17), (122.50, 97.45), "/GND", width=0.25, layer=pcbnew.B_Cu)
    add_track(board, (122.50, 97.45), (125.5, 97.45), "/GND", width=0.25, layer=pcbnew.B_Cu)
    add_track(board, (121.69, 103.79), (122.50, 102.52), "/GND", width=0.25, layer=pcbnew.F_Cu)
    add_track(board, (122.50, 102.52), (125.5, 102.52), "/GND", width=0.25, layer=pcbnew.F_Cu)
    add_via(board, (125.5, 102.52), "/GND")


def add_track(board: pcbnew.BOARD, start: tuple[float, float], end: tuple[float, float],
              net_name: str, width: float = 0.25, layer: int = pcbnew.F_Cu) -> None:
    track = pcbnew.PCB_TRACK(board)
    track.SetStart(v(*start))
    track.SetEnd(v(*end))
    track.SetWidth(mm(width))
    track.SetLayer(layer)
    track.SetNet(net(board, net_name))
    board.Add(track)


def add_via(board: pcbnew.BOARD, at: tuple[float, float], net_name: str,
            diameter: float = 0.6, drill: float = 0.3) -> None:
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(v(*at))
    via.SetWidth(mm(diameter))
    via.SetDrill(mm(drill))
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    via.SetNet(net(board, net_name))
    board.Add(via)


def add_logo(board: pcbnew.BOARD, center: tuple[float, float],
             layer: int = pcbnew.B_SilkS, scale: float = 1.0) -> None:
    """Place the Code Myriad emblem as filled silkscreen polygons centered at `center`.

    Geometry is baked in tools/codemyriad-logo.json (converted from the official
    codemyriad.io/logo.svg by tools/svg_logo_to_silk.py) -- polygons in mm, centered
    on their own origin. The emblem is left/right and top/bottom symmetric, so it
    needs no back-layer mirroring; the ring's hole is preserved by a bridge already
    present in the source path.
    """
    data = json.loads(LOGO_JSON.read_text())
    cx, cy = center
    for poly in data["polys"]:
        sps = pcbnew.SHAPE_POLY_SET()
        sps.NewOutline()
        for x, y in poly:
            sps.Append(mm(cx + x * scale), mm(cy + y * scale))
        shape = pcbnew.PCB_SHAPE(board)
        shape.SetShape(pcbnew.SHAPE_T_POLY)
        shape.SetPolyShape(sps)
        shape.SetLayer(layer)
        shape.SetFilled(True)
        shape.SetWidth(mm(0.12))
        board.Add(shape)


BRAND_X = 107.0  # connector-wing center: toward the edge connector (x~98),
                 # clear of the through-hole proto field (which starts at x~110.85)


LOGO_SCALE = 0.82  # ~8.2 mm wide: fits the connector wing with margin on both sides


def add_branding(board: pcbnew.BOARD, layer: int, protogon: bool) -> None:
    """Code Myriad branding (emblem + codemyriad.io, optional PROTOGON) in the
    connector wing -- toward the edge connector and clear of the proto field.
    Placed on both faces (call once per side)."""
    if protogon:
        add_text(board, "PROTOGON", (BRAND_X, 93.0), size=0.8, layer=layer, bold=True)
    add_logo(board, (BRAND_X, 100.0), layer=layer, scale=LOGO_SCALE)
    add_text(board, "codemyriad.io", (BRAND_X, 107.0), size=0.85, layer=layer, bold=True)


def add_silkscreen(board: pcbnew.BOARD) -> None:
    add_text(board, "3V3", (119.3, 83.47), size=0.8, bold=True, align="right")
    add_text(board, "GND", (119.3, 116.49), size=0.8, bold=True, align="right")

    # Breakout labels aligned with the official J2 pin map.
    labels = [
        ("GND", "GND", 88.55),
        ("LS_E", "HS_F", 91.09),
        ("LS_D", "HS_G", 93.63),
        ("LS_C", "GND", 96.17),
        ("DET/G", "3V3", 98.71),
        ("SCL", "3V3", 101.25),
        ("SDA", "GND", 103.79),
        ("LS_B", "HS_H", 106.33),
        ("LS_A", "HS_I", 108.87),
        ("GND", "GND", 111.41),
    ]
    for _left, right, y in labels:
        add_text(board, right, (118.9, y), size=0.8, align="right")

    # Small orientation marks. The edge connector footprint already carries top
    # and bottom text; these make the fab side clearer on the finished PCB.
    add_text(board, "+", (106.1, 94.0), size=0.9, bold=True)

    # Branding on BOTH faces, in the connector wing (toward the edge connector,
    # clear of the through-hole proto field). Back keeps the PROTOGON name.
    add_branding(board, pcbnew.B_SilkS, protogon=True)
    add_branding(board, pcbnew.F_SilkS, protogon=False)


def add_fab_notes(board: pcbnew.BOARD) -> None:
    add_text(board, "FAB: 1.0mm FR4, black soldermask, ENIG finish, no bevel on edge connector tab",
             (137.0, 79.2), size=0.8, layer=pcbnew.Cmts_User, align="left")
    add_text(board, "TEST: verify 3V3 rail after insertion in a 2024 Tildagon",
             (137.0, 120.8), size=0.8, layer=pcbnew.Cmts_User, align="left")


def copy_project_files() -> None:
    OUT.mkdir(exist_ok=True)
    shutil.copy2(UPSTREAM / "LICENSE.txt", OUT / "CERN-OHL-P-2.0.txt")
    shutil.copy2(UPSTREAM / "hexpansion_paper_template.svg", OUT / "official-hexpansion-paper-template.svg")
    # Use the upstream project/schematic as a harmless KiCad project shell; the
    # generated PCB is the source of truth for this bare protoboard.
    pro = (UPSTREAM / "hexpansion.kicad_pro").read_text()
    pro = pro.replace("hexpansion", "codemyriad-protogon")
    (OUT / "codemyriad-protogon.kicad_pro").write_text(pro)
    sch = (UPSTREAM / "hexpansion.kicad_sch").read_text()
    sch = sch.replace("hexpansion.kicad_sch", "codemyriad-protogon.kicad_sch")
    sch = sch.replace("Nodule Breakout", "Code Myriad Protogon")
    (OUT / "codemyriad-protogon.kicad_sch").write_text(sch)
    (OUT / "fp-lib-table").write_text(
        '(fp_lib_table\n'
        '  (version 7)\n'
        '  (lib (name "tildagon")(type "KiCad")(uri "${KIPRJMOD}/tildagon.pretty")(options "")(descr ""))\n'
        '  (lib (name "MountingHole")(type "KiCad")(uri "${KIPRJMOD}/MountingHole.pretty")(options "")(descr ""))\n'
        '  (lib (name "Connector_PinHeader_2.54mm")(type "KiCad")(uri "${KIPRJMOD}/Connector_PinHeader_2.54mm.pretty")(options "")(descr ""))\n'
        ')\n'
    )
    (OUT / "sym-lib-table").write_text("(sym_lib_table\n)\n")


def write_local_footprint_library(board: pcbnew.BOARD) -> None:
    libs = {
        "J1": OUT / "tildagon.pretty",
        "J2": OUT / "Connector_PinHeader_2.54mm.pretty",
        "H1": OUT / "MountingHole.pretty",
    }
    for lib in libs.values():
        shutil.rmtree(lib, ignore_errors=True)
        lib.mkdir(exist_ok=True)
    io = pcbnew.PCB_IO_KICAD_SEXPR()
    for fp in board.GetFootprints():
        lib = libs.get(fp.GetReference())
        if lib is not None:
            io.FootprintSave(str(lib), fp)


def normalize_board_file() -> None:
    text = BOARD_OUT.read_text()
    text = text.replace(
        '(comment 3 "Order as 1.0 mm FR4, ENIG, purple soldermask, white silkscreen")',
        '(comment 3 "Order as 1.0 mm FR4, ENIG, black soldermask, white silkscreen")',
    )
    text = text.replace(
        '(layer "F.SilkS"\n\t\t\t\t(type "Top Silk Screen")\n\t\t\t)',
        '(layer "F.SilkS"\n\t\t\t\t(type "Top Silk Screen")\n\t\t\t\t(color "White")\n\t\t\t)',
    )
    text = text.replace(
        '(layer "F.Mask"\n\t\t\t\t(type "Top Solder Mask")\n\t\t\t\t(thickness 0.01)\n\t\t\t)',
        '(layer "F.Mask"\n\t\t\t\t(type "Top Solder Mask")\n\t\t\t\t(color "Black")\n\t\t\t\t(thickness 0.01)\n\t\t\t)',
    )
    text = text.replace(
        '(layer "B.Mask"\n\t\t\t\t(type "Bottom Solder Mask")\n\t\t\t\t(thickness 0.01)\n\t\t\t)',
        '(layer "B.Mask"\n\t\t\t\t(type "Bottom Solder Mask")\n\t\t\t\t(color "Black")\n\t\t\t\t(thickness 0.01)\n\t\t\t)',
    )
    text = text.replace(
        '(layer "B.SilkS"\n\t\t\t\t(type "Bottom Silk Screen")\n\t\t\t)',
        '(layer "B.SilkS"\n\t\t\t\t(type "Bottom Silk Screen")\n\t\t\t\t(color "White")\n\t\t\t)',
    )
    text = text.replace('(copper_finish "None")', '(copper_finish "ENIG")')
    BOARD_OUT.write_text(text)


def main() -> None:
    copy_project_files()
    board = pcbnew.LoadBoard(str(BOARD_IN))
    write_local_footprint_library(board)
    set_board_settings(board)
    set_detect_to_ground(board)
    clear_generated_items(board)
    add_expanded_outline(board)
    add_proto_grid(board)
    add_silkscreen(board)
    add_fab_notes(board)
    pcbnew.SaveBoard(str(BOARD_OUT), board)
    normalize_board_file()
    # KiCad 9's Ubuntu Python binding occasionally segfaults during interpreter
    # teardown after successful SaveBoard. Exit directly once the file is written.
    os._exit(0)


if __name__ == "__main__":
    main()
