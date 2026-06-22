#!/usr/bin/env python3
"""Render a constant-velocity loop of the Protogon GLB in Blender."""

from __future__ import annotations

import argparse
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import bpy
from mathutils import Vector


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--outdir", required=True)
    parser.add_argument("--frames", type=int, default=192,
                        help="frames for a full 360 turn; 192 @ 24fps = 8.0s/rev (slow, "
                             "calm turntable). Keep it even so the GIF's stride-2 "
                             "decimation stays exact.")
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--samples", type=int, default=None,
                        help="render samples; default 8 for eevee/workbench, 128 for cycles")
    parser.add_argument("--engine", choices=["eevee", "workbench", "cycles"], default="eevee",
                        help="cycles = GPU-accelerated path tracing (accurate, photoreal); "
                             "eevee = fast rasterizer (default); workbench = flat preview")
    parser.add_argument("--gpu-backend", choices=["OPTIX", "CUDA", "HIP", "ONEAPI", "auto"],
                        default="auto", help="Cycles GPU backend; auto prefers OptiX then CUDA")
    parser.add_argument("--denoiser", choices=["openimagedenoise", "optix", "none"],
                        default="openimagedenoise",
                        help="Cycles denoiser; OIDN is the reliable default (the OptiX "
                             "denoiser fails to initialize on some GPU/driver combos, e.g. "
                             "Blackwell + Blender 4.5). Path tracing still runs on the GPU.")
    parser.add_argument("--poster-only", action="store_true",
                        help="render only the still poster (fast preview), skip the loop/MP4/GIF")
    parser.add_argument("--xray", action="store_true",
                        help="make the soldermask translucent so the copper routing/traces "
                             "show through -- a design-inspection view, not a product shot")
    parser.add_argument("--hdri", default="renders/hdri/studio_small_03_1k.hdr",
                        help="studio HDRI (relative to cwd) for soft lighting/reflections; "
                             "falls back to a flat neutral world if missing")
    parser.add_argument("--standard-view", action="store_true",
                        help="use the Standard view transform (literal colours) for a "
                             "colour-accuracy check instead of the AgX beauty transform")
    parser.add_argument("--background", default="renders/bg/EMF-photo.jpg",
                        help="backdrop photo composited behind the board (relative to cwd); "
                             "pass '' or a missing path for the plain studio backdrop")
    parser.add_argument("--top-texture")
    parser.add_argument("--bottom-texture")
    # GIF/contact-sheet deliverables are derived from the rendered MP4 (needs ffmpeg).
    # 12.5 fps => exactly 8 centiseconds per GIF frame, so every frame has an identical
    # delay (GIF stores delays in whole centiseconds; 12 fps cannot be expressed evenly).
    parser.add_argument("--gif-fps", type=float, default=12.5)
    parser.add_argument("--gif-width", type=int, default=900)
    parser.add_argument("--contact-tiles", default="4x2")
    parser.add_argument("--skip-gif", action="store_true")
    parser.add_argument("--skip-contact", action="store_true")
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    return parser.parse_args(argv)


def look_at(obj: bpy.types.Object, target: Vector) -> None:
    direction = target - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def scene_bounds(objects: list[bpy.types.Object]) -> tuple[Vector, Vector]:
    points: list[Vector] = []
    for obj in objects:
        if obj.type not in {"MESH", "CURVE", "FONT"}:
            continue
        for corner in obj.bound_box:
            points.append(obj.matrix_world @ Vector(corner))
    if not points:
        raise SystemExit("No renderable geometry (MESH/CURVE/FONT) found in the imported model.")
    lo = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
    hi = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
    return lo, hi


def material(name: str, color: tuple[float, float, float, float],
             metallic: float = 0.0, roughness: float = 0.45, alpha: float = 1.0,
             coat: float = 0.0, coat_roughness: float = 0.1,
             spec_tint: tuple[float, float, float, float] | None = None,
             transmission: float = 0.0) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = color
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        ins = bsdf.inputs
        ins["Base Color"].default_value = color
        ins["Metallic"].default_value = metallic
        ins["Roughness"].default_value = roughness
        if "Alpha" in ins:
            ins["Alpha"].default_value = alpha
        # Blender 4.x Principled inputs: "Coat Weight"/"Coat Roughness" (was
        # Clearcoat), "Specular Tint" (now a color = F82 metal edge tint),
        # "Transmission Weight". Guarded so other Blender versions don't break.
        if coat and "Coat Weight" in ins:
            ins["Coat Weight"].default_value = coat
            if "Coat Roughness" in ins:
                ins["Coat Roughness"].default_value = coat_roughness
        if spec_tint is not None and "Specular Tint" in ins:
            ins["Specular Tint"].default_value = spec_tint
        if transmission and "Transmission Weight" in ins:
            ins["Transmission Weight"].default_value = transmission
    return mat


def apply_board_materials(objects: list[bpy.types.Object], xray: bool = False) -> None:
    # On a real black-soldermask board the copper traces are buried under the mask and
    # are not visible -- only the exposed gold pads and white silk show. `xray` makes the
    # soldermask translucent so the copper routing (the J1->J2 breakout traces) is visible:
    # a design-inspection view, NOT a truthful product shot.
    mats = {
        # Black soldermask: a raised-black base (NOT pure black, which reads as a flat
        # void) plus a Coat lacquer layer for the semi-gloss wet sheen real mask has.
        "mask": material("black soldermask", (0.013, 0.013, 0.016, 1.0),
                         roughness=0.42, coat=0.30, coat_roughness=0.10,
                         alpha=(0.15 if xray else 1.0)),
        # FR4 edge: desaturated tan, slightly translucent at the visible 1mm edge.
        "fr4": material("FR4 edge", (0.055, 0.045, 0.028, 1.0), roughness=0.8,
                        transmission=0.25),
        # ENIG: real gold metal (Metallic 1.0), paler than jewellery gold, satin (not a
        # mirror), with a warm Specular Tint (F82 edge tint) so it reads as ENIG, not chrome.
        "gold": material("ENIG gold", (0.85, 0.66, 0.30, 1.0), metallic=1.0,
                         roughness=0.35, spec_tint=(1.0, 0.82, 0.52, 1.0)),
        # White silkscreen: matte printed ink, NO emission (emission would glow and
        # destroy assessability).
        "silk": material("white silkscreen", (0.92, 0.92, 0.90, 1.0), roughness=0.9),
    }
    for obj in objects:
        if obj.type != "MESH":
            continue
        name = obj.name.lower()
        slot_names = {slot.material.name for slot in obj.material_slots if slot.material is not None}
        if slot_names & {"mat_0", "mat_1"} or any(token in name for token in ("copper", "pad", "via")):
            mat = mats["gold"]
        elif slot_names & {"mat_2", "mat_3"} or "silkscreen" in name:
            mat = mats["silk"]
        elif slot_names & {"mat_4", "mat_5"} or "soldermask" in name:
            mat = mats["mask"]
        else:
            mat = mats["fr4"]
        obj.data.materials.clear()
        obj.data.materials.append(mat)


def material_slots(obj: bpy.types.Object) -> set[str]:
    return {slot.material.name for slot in obj.material_slots if slot.material is not None}


def image_material(name: str, image_path: str) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    # Hard alpha cutout for the art PNGs. The Mix(Transparent, Emission, Fac=Alpha)
    # node graph below does the actual cutout; these material flags are version-dependent
    # hints (Blender 4.3+/5.0 dropped blend_method/alpha_threshold in favour of
    # surface_render_method), so set whichever the running Blender exposes.
    if hasattr(mat, "surface_render_method"):
        mat.surface_render_method = "DITHERED"
    if hasattr(mat, "blend_method"):
        mat.blend_method = "CLIP"
    if hasattr(mat, "alpha_threshold"):
        mat.alpha_threshold = 0.35
    if hasattr(mat, "use_screen_refraction"):
        mat.use_screen_refraction = False
    nodes = mat.node_tree.nodes
    for node in list(nodes):
        nodes.remove(node)
    output = nodes.new("ShaderNodeOutputMaterial")
    image = nodes.new("ShaderNodeTexImage")
    image.image = bpy.data.images.load(image_path)
    image.extension = "CLIP"
    emission = nodes.new("ShaderNodeEmission")
    transparent = nodes.new("ShaderNodeBsdfTransparent")
    mix = nodes.new("ShaderNodeMixShader")
    mat.node_tree.links.new(image.outputs["Color"], emission.inputs["Color"])
    mat.node_tree.links.new(image.outputs["Alpha"], mix.inputs["Fac"])
    mat.node_tree.links.new(transparent.outputs["BSDF"], mix.inputs[1])
    mat.node_tree.links.new(emission.outputs["Emission"], mix.inputs[2])
    mat.node_tree.links.new(mix.outputs["Shader"], output.inputs["Surface"])
    return mat


def add_surface_plane(name: str, image_path: str, width: float, height: float,
                      z: float, bottom: bool) -> bpy.types.Object:
    hw = width / 2
    hh = height / 2
    # The board flips 180deg around Y during the loop, so the back face would appear
    # mirrored. bottom=True reverses the vertex winding to un-mirror the back-face art.
    # The bottom-surface texture is authored to match this winding -- if you regenerate
    # the textures, sanity-check a mid-loop frame so the back-face text reads upright.
    if bottom:
        verts = [(-hw, -hh, z), (-hw, hh, z), (hw, hh, z), (hw, -hh, z)]
    else:
        verts = [(-hw, -hh, z), (hw, -hh, z), (hw, hh, z), (-hw, hh, z)]
    mesh = bpy.data.meshes.new(name + "_mesh")
    mesh.from_pydata(verts, [], [(0, 1, 2, 3)])
    mesh.update()
    uv_layer = mesh.uv_layers.new(name="UVMap")
    for loop, uv in zip(uv_layer.data, [(0, 0), (1, 0), (1, 1), (0, 1)]):
        loop.uv = uv
    obj = bpy.data.objects.new(name, mesh)
    obj.data.materials.append(image_material(name + "_material", image_path))
    bpy.context.collection.objects.link(obj)
    return obj


def keep_body_only(objects: list[bpy.types.Object]) -> list[bpy.types.Object]:
    kept = []
    for obj in list(objects):
        if obj.type == "MESH" and "mat_6" in material_slots(obj):
            kept.append(obj)
        else:
            bpy.data.objects.remove(obj, do_unlink=True)
    return kept


def iter_action_fcurves(action: bpy.types.Action):
    """Yield every fcurve of an action across Blender versions.

    Blender <= 4.3 exposes a flat ``action.fcurves`` collection. Blender 4.4+/5.0
    switched to slotted actions where fcurves live under
    ``action.layers[].strips[].channelbags[].fcurves`` and ``action.fcurves`` is gone.
    """
    legacy = getattr(action, "fcurves", None)
    if legacy is not None:
        yield from legacy
        return
    for layer in getattr(action, "layers", []):
        for strip in layer.strips:
            for channelbag in getattr(strip, "channelbags", []):
                yield from channelbag.fcurves


def linearize_animation(action: bpy.types.Action | None) -> None:
    if action is None:
        return
    for fcurve in iter_action_fcurves(action):
        for keyframe in fcurve.keyframe_points:
            keyframe.interpolation = "LINEAR"


def _ffmpeg(*ffargs: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *ffargs], check=True)


def encode_mp4(frame_glob: str, mp4: Path, fps: int) -> None:
    """Encode a rendered PNG frame sequence to an H.264 MP4.

    Blender 5.0 removed the in-app FFmpeg muxer (FFMPEG is no longer a valid
    image_settings.file_format), so video is produced from PNG frames with
    external ffmpeg. yuv420p keeps the file broadly playable.
    """
    _ffmpeg("-framerate", str(fps), "-i", frame_glob,
            "-c:v", "libx264", "-crf", "18", "-preset", "slow",
            "-pix_fmt", "yuv420p", str(mp4))


def integer_decimation(frames: int, src_fps: float, gif_fps: float) -> int:
    """Pick a whole-number frame stride k that divides `frames`.

    Decimating by an integer that divides the loop length keeps the GIF's angular
    step uniform (every kept frame is exactly k*tau/frames apart, including the
    wrap), which is what makes the loop judder-free. A non-integer rate (e.g. the
    old 24->18 fps = 4:3) drops frames unevenly and produces a periodic stutter.
    """
    k = max(1, round(src_fps / gif_fps))
    while k > 1 and frames % k != 0:
        k -= 1
    return k


def generate_gif(mp4: Path, gif: Path, src_fps: float, gif_fps: float,
                 frames: int, width: int) -> None:
    if shutil.which("ffmpeg") is None:
        print("WARNING: ffmpeg not found; skipping GIF generation.", file=sys.stderr)
        return
    k = integer_decimation(frames, src_fps, gif_fps)
    with tempfile.TemporaryDirectory() as tmp:
        frame_glob = str(Path(tmp) / "f_%04d.png")
        palette = str(Path(tmp) / "palette.png")
        # 1) Extract every k-th source frame -> uniform angular steps, no duplicates.
        _ffmpeg("-i", str(mp4),
                "-vf", f"select='not(mod(n,{k}))',scale={width}:-1:flags=lanczos",
                "-fps_mode", "passthrough", frame_glob)
        # 2) Re-time the kept frames at gif_fps (uniform per-frame delay) and palettize.
        _ffmpeg("-framerate", str(gif_fps), "-i", frame_glob,
                "-vf", "palettegen=stats_mode=diff", palette)
        _ffmpeg("-framerate", str(gif_fps), "-i", frame_glob, "-i", palette,
                "-lavfi", "paletteuse=dither=bayer:bayer_scale=3", "-loop", "0", str(gif))
    print(f"Wrote {gif} (stride {k}, {gif_fps} fps).")


def generate_contact(mp4: Path, jpg: Path, frames: int, tiles: str) -> None:
    if shutil.which("ffmpeg") is None:
        print("WARNING: ffmpeg not found; skipping contact sheet.", file=sys.stderr)
        return
    try:
        cols, rows = (int(n) for n in tiles.lower().split("x"))
    except ValueError:
        raise SystemExit(f"--contact-tiles must look like 4x2, got {tiles!r}")
    step = max(1, frames // (cols * rows))
    _ffmpeg("-i", str(mp4),
            "-vf", f"select='not(mod(n,{step}))',scale=320:-1,tile={tiles}",
            "-frames:v", "1", "-q:v", "3", str(jpg))
    print(f"Wrote {jpg} ({tiles}, every {step}th frame).")


def configure_gpu(scene: bpy.types.Scene, samples: int, prefer: str = "auto",
                  denoiser: str = "openimagedenoise") -> str | None:
    """Set up Cycles to render on the GPU.

    Prefers OptiX (RTX RT cores) then CUDA, falling back to CPU with a warning if
    no GPU backend is usable. Disables the CPU device once a GPU is found so the
    render does not stall on slow hybrid tiles. Enables a denoiser so even modest
    sample counts come out clean -- fast AND accurate. OpenImageDenoise is the
    default because the OptiX denoiser fails to initialise on some GPU/driver
    combos (observed on RTX 5060 Blackwell + Blender 4.5); path tracing still runs
    on the GPU regardless of which denoiser is chosen. Prints the chosen device(s)
    so the render log records what ran. Returns the backend used, or None for CPU.
    """
    scene.render.engine = "CYCLES"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    order = ["OPTIX", "CUDA", "HIP", "ONEAPI"] if prefer == "auto" else [prefer]
    chosen = None
    for backend in order:
        try:
            prefs.compute_device_type = backend
        except TypeError:
            continue  # this Blender build/platform does not offer that backend
        prefs.refresh_devices()
        if any(d.type == backend for d in prefs.devices):
            chosen = backend
            break
    if chosen is None:
        print("WARNING: no GPU backend available; Cycles will render on CPU (slow).",
              file=sys.stderr)
        scene.cycles.device = "CPU"
    else:
        for device in prefs.devices:
            device.use = (device.type == chosen)  # GPU(s) only; CPU off
        scene.cycles.device = "GPU"
        enabled = [d.name for d in prefs.devices if d.use]
        print(f"Cycles GPU backend: {chosen}; devices: {enabled}", flush=True)
    scene.cycles.samples = samples
    # Adaptive sampling spends samples only where needed (cheaper, clean turntable frames).
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = 0.01
    # Gold metal + small bright sources spark fireflies; clamp indirect and soften noisy
    # sharp gold reflections, and disable caustics (a big noise source, irrelevant here).
    scene.cycles.sample_clamp_indirect = 10.0
    scene.cycles.blur_glossy = 1.0
    scene.cycles.caustics_reflective = False
    scene.cycles.caustics_refractive = False
    if denoiser == "none":
        scene.cycles.use_denoising = False
    else:
        scene.cycles.use_denoising = True
        try:
            scene.cycles.denoiser = "OPTIX" if denoiser == "optix" else "OPENIMAGEDENOISE"
        except TypeError:
            pass
        # OIDN best-practice for fine silk text + gold micro-detail: Albedo+Normal guiding
        # passes with Accurate prefilter preserve edges that the 'None' prefilter blurs.
        for attr, val in (("denoising_input_passes", "RGB_ALBEDO_NORMAL"),
                          ("denoising_prefilter", "ACCURATE")):
            if hasattr(scene.cycles, attr):
                try:
                    setattr(scene.cycles, attr, val)
                except TypeError:
                    pass
    return chosen


def setup_world(scene: bpy.types.Scene, hdri_path: str | None,
                bg_color: tuple[float, float, float], strength: float = 1.0) -> None:
    """Light the scene with a studio HDRI (soft reflections that make gold/coat read as
    metal/lacquer) while showing a clean solid backdrop to the camera, via a Light Path
    'Is Camera Ray' mix. Falls back to a flat neutral world if the HDRI file is missing."""
    world = scene.world or bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    solid = nt.nodes.new("ShaderNodeBackground")
    solid.inputs["Color"].default_value = (*bg_color, 1.0)
    if hdri_path and Path(hdri_path).exists():
        env = nt.nodes.new("ShaderNodeTexEnvironment")
        env.image = bpy.data.images.load(hdri_path)
        envbg = nt.nodes.new("ShaderNodeBackground")
        envbg.inputs["Strength"].default_value = strength
        lp = nt.nodes.new("ShaderNodeLightPath")
        mix = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(env.outputs["Color"], envbg.inputs["Color"])
        nt.links.new(lp.outputs["Is Camera Ray"], mix.inputs["Fac"])
        nt.links.new(envbg.outputs["Background"], mix.inputs[1])  # non-camera -> HDRI light/reflections
        nt.links.new(solid.outputs["Background"], mix.inputs[2])  # camera -> clean solid backdrop
        nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])
    else:
        print(f"WARNING: HDRI '{hdri_path}' not found; using a flat neutral world.",
              file=sys.stderr)
        nt.links.new(solid.outputs["Background"], out.inputs["Surface"])


def setup_background_composite(scene: bpy.types.Scene, image_path: str) -> None:
    """Composite the rendered board (transparent film) over a backdrop photo, so the board
    appears in front of it. Lighting and reflections still come from the studio HDRI, so
    the materials read true; only the camera-visible background becomes the photo."""
    scene.render.film_transparent = True
    scene.use_nodes = True
    nt = scene.node_tree
    nt.nodes.clear()
    rl = nt.nodes.new("CompositorNodeRLayers")
    img = nt.nodes.new("CompositorNodeImage")
    img.image = bpy.data.images.load(image_path)
    scale = nt.nodes.new("CompositorNodeScale")
    scale.space = "RENDER_SIZE"
    if hasattr(scale, "frame_method"):
        scale.frame_method = "CROP"  # fill the frame, crop any overflow
    over = nt.nodes.new("CompositorNodeAlphaOver")
    comp = nt.nodes.new("CompositorNodeComposite")
    nt.links.new(img.outputs["Image"], scale.inputs["Image"])
    nt.links.new(scale.outputs["Image"], over.inputs[1])  # backdrop photo (behind)
    nt.links.new(rl.outputs["Image"], over.inputs[2])      # board render, on top (its alpha)
    nt.links.new(over.outputs["Image"], comp.inputs["Image"])


def main() -> None:
    args = parse_args()
    if args.samples is None:
        args.samples = 128 if args.engine == "cycles" else 8
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()

    bpy.ops.import_scene.gltf(filepath=args.model)
    imported = list(bpy.context.scene.objects)
    apply_board_materials(imported, xray=args.xray)
    lo, hi = scene_bounds(imported)
    center = (lo + hi) * 0.5
    size = hi - lo
    max_dim = max(size.x, size.y)
    if bool(args.top_texture) != bool(args.bottom_texture):
        print("WARNING: --top-texture and --bottom-texture must BOTH be given to use "
              "surface art; falling back to full board materials.", file=sys.stderr)
    use_surface_textures = bool(args.top_texture and args.bottom_texture)
    if use_surface_textures:
        imported = keep_body_only(imported)

    root = bpy.data.objects.new("protogon_root", None)
    bpy.context.collection.objects.link(root)
    for obj in imported:
        obj.location -= center
        obj.parent = root
    if use_surface_textures:
        z_pad = max(size.z * 0.08, 0.00006)
        top = add_surface_plane("top_art", args.top_texture, size.x, size.y, size.z / 2 + z_pad, bottom=False)
        bottom = add_surface_plane("bottom_art", args.bottom_texture, size.x, size.y, -size.z / 2 - z_pad, bottom=True)
        top.parent = root
        bottom.parent = root

    bpy.context.scene.frame_start = 1
    bpy.context.scene.frame_end = args.frames
    # Standing turntable: stand the board upright (constant +90deg about X) and spin it
    # about the vertical Z axis. A flat board flipped about an in-plane axis collapses to
    # an invisible sliver whenever it passes edge-on to the camera (the board literally
    # disappears twice per turn); spinning it upright about the vertical axis instead keeps
    # its full-height edge visible (a thin blade) at the edge-on moments while still
    # revealing both faces over the loop.
    #
    # Seamless loop: the full-turn keyframe sits one frame PAST the last rendered frame
    # (args.frames + 1). Only frames 1..args.frames are rendered, so the last frame stops
    # exactly one angular step short of a full revolution; looping back to frame 1 then
    # advances by that same step -- no duplicate/stutter frame at the seam.
    # Do NOT change this to args.frames: that reintroduces a doubled seam frame.
    stand = math.pi / 2
    root.rotation_euler = (stand, 0, 0)
    root.keyframe_insert(data_path="rotation_euler", frame=1)
    root.rotation_euler = (stand, 0, math.tau)
    root.keyframe_insert(data_path="rotation_euler", frame=args.frames + 1)
    linearize_animation(root.animation_data.action if root.animation_data else None)

    camera = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
    bpy.context.collection.objects.link(camera)
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = max_dim * 1.62
    # Clip planes scaled to the model. The camera sits ~2.4*max_dim from the origin and
    # the board spans ~max_dim about it, so as a corner swings toward the camera it can
    # fall inside Blender's default 0.1 near-clip and get sliced flat (it looked like the
    # board was clipped to a bounding cube). Generous, scale-relative planes prevent that.
    camera.data.clip_start = max_dim * 0.1
    camera.data.clip_end = max_dim * 10.0
    # 3/4 view from the front, slightly to the side and above. The board stands on the
    # Z axis, so a front-ish camera sees a thin lit edge (not nothing) at the edge-on turn.
    camera.location = Vector((max_dim * 0.55, -max_dim * 2.3, max_dim * 0.6))
    look_at(camera, Vector((0, 0, 0)))
    bpy.context.scene.camera = camera

    # Lighting: a neutral studio HDRI gives soft, believable environment reflections --
    # what makes the ENIG gold and the soldermask coat actually read as those materials --
    # while a clean solid colour is shown to the camera (Light Path "Is Camera Ray") so the
    # backdrop stays calm and assess-able. Two soft area lights sweep highlights across the
    # board to reveal the silk and the mask sheen. Area energy is scaled by max_dim^2 so
    # brightness stays independent of the model's import scale.
    setup_world(bpy.context.scene, args.hdri, bg_color=(0.05, 0.05, 0.06), strength=0.55)

    def add_area(name: str, location: Vector, energy: float, size: float) -> bpy.types.Object:
        light = bpy.data.objects.new(name, bpy.data.lights.new(name, "AREA"))
        bpy.context.collection.objects.link(light)
        light.location = location
        look_at(light, Vector((0, 0, 0)))
        light.data.energy = energy
        light.data.size = size
        return light

    e = max_dim * max_dim
    add_area("Key", Vector((-max_dim * 1.1, -max_dim * 1.4, max_dim * 1.5)), e * 30.0, max_dim * 1.3)
    add_area("Rim", Vector(( max_dim * 0.6,  max_dim * 1.5, max_dim * 1.1)), e * 13.0, max_dim * 1.1)

    scene = bpy.context.scene
    if args.engine == "workbench":
        scene.render.engine = "BLENDER_WORKBENCH"
        scene.display.shading.light = "STUDIO"
        scene.display.shading.color_type = "MATERIAL"
        scene.display.shading.show_shadows = True
        scene.display.shading.show_cavity = True
    elif args.engine == "cycles":
        configure_gpu(scene, args.samples, prefer=args.gpu_backend, denoiser=args.denoiser)
    else:
        # Blender 4.2-4.4 named the engine BLENDER_EEVEE_NEXT; 5.0 renamed it back to
        # BLENDER_EEVEE. Pick whichever the running Blender actually exposes.
        engine_ids = {e.identifier for e in
                      scene.render.bl_rna.properties["engine"].enum_items}
        scene.render.engine = ("BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in engine_ids
                               else "BLENDER_EEVEE")
        if hasattr(scene, "eevee") and hasattr(scene.eevee, "taa_render_samples"):
            scene.eevee.taa_render_samples = args.samples
    scene.render.resolution_x = args.width
    scene.render.resolution_y = args.height
    scene.render.fps = args.fps
    scene.render.film_transparent = False
    # AgX for the beauty render (rolls bright gold highlights off gracefully like film);
    # Standard for a colour-accuracy snapshot (literal material values, to compare against
    # the kicad-cli stackup render and physical swatches).
    if args.standard_view:
        scene.view_settings.view_transform = "Standard"
    else:
        try:
            scene.view_settings.view_transform = "AgX"
        except TypeError:
            scene.view_settings.view_transform = "Filmic"
        for look in ("AgX - Medium High Contrast", "Medium High Contrast", "None"):
            try:
                scene.view_settings.look = look
                break
            except TypeError:
                continue
    scene.view_settings.exposure = 0
    scene.view_settings.gamma = 1

    # Optional photo backdrop (e.g. the EMF sign): board on transparent film composited
    # over the image. Lighting/reflections still come from the studio HDRI.
    if args.background and Path(args.background).exists():
        setup_background_composite(scene, args.background)
    elif args.background:
        print(f"WARNING: backdrop '{args.background}' not found; plain backdrop kept.",
              file=sys.stderr)

    scene.frame_set(1)
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(outdir / "protogon-loop-poster.png")
    bpy.ops.render.render(write_still=True)

    if args.poster_only:
        print(f"poster-only: wrote {outdir / 'protogon-loop-poster.png'}; "
              "skipping loop/MP4/GIF/contact.")
        return

    if shutil.which("ffmpeg") is None:
        print("WARNING: ffmpeg not found; rendered the poster only, skipping "
              "MP4/GIF/contact.", file=sys.stderr)
        return

    # Render the loop as PNG frames, then encode the MP4 (and derive the GIF +
    # contact sheet) with external ffmpeg. The GIF/contact were previously produced
    # by an ad-hoc step that introduced judder via non-integer 24->18 fps downsampling;
    # wiring them here keeps the documented deliverables reproducible.
    mp4_path = outdir / "protogon-loop.mp4"
    with tempfile.TemporaryDirectory() as frame_dir:
        scene.render.image_settings.file_format = "PNG"
        scene.render.filepath = str(Path(frame_dir) / "f####")
        bpy.ops.render.render(animation=True)
        encode_mp4(str(Path(frame_dir) / "f%04d.png"), mp4_path, args.fps)

    if not args.skip_gif:
        generate_gif(mp4_path, outdir / "protogon-loop.gif",
                     args.fps, args.gif_fps, args.frames, args.gif_width)
    if not args.skip_contact:
        generate_contact(mp4_path, outdir / "protogon-loop-contact.jpg",
                         args.frames, args.contact_tiles)


if __name__ == "__main__":
    main()
