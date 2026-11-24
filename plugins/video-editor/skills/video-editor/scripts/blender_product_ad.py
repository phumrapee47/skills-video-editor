"""3D product ad shots in Blender, headless: a can (or bottle) wrapped in the product's label image, a studio set in
the product's colour, floating flavour pieces, and the shot types of the 3D-ad study (references/ad-3d.md).

Run:  blender -b -P blender_product_ad.py -- --label label.png [--alt a.png b.png] [--slice slice.png]
        --set "#FFB81C" "#FF7A1E" --out shots_dir [--size 1080x1920] [--fps 30] [--shots reveal hero macro burst trio]
        [--still [--frame N]] [--samples 24] [--shape can|bottle] [--fruit yuzu|orange|lemon|lime|grapefruit]
Writes <out>/<shot>/####.png per shot (or one still per shot with --still to check the look first).
--fruit builds the flavour as real 3D fruit (ad_fruit.py: pored peel, cut faces, juice) instead of --slice pictures.
Shots: split (the fruit is slashed, halves fly apart in a speed ramp, juice sprays, the can rises out of the middle),
reveal (falls in spinning, pieces fly past the lens), hero (slow turn, light sweep), macro (slide along the
label, shallow focus), burst (pieces explode outward), trio (three flavours slide in, slow orbit).
Use only the user's own product and label art.
"""
import math, sys, os, argparse, random, json
import bpy
from mathutils import Vector, Matrix
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ad_fruit as AF
import ad_can as AC
import ad_shapes as AS
import ad_look as LK
import ad_cut as CUT

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--label", help="the can label (2:1 image); other products come from --product"); ap.add_argument("--alt", nargs="*", default=[]); ap.add_argument("--slice")
ap.add_argument("--set", nargs=2, default=["#FFB81C", "#FF7A1E"]); ap.add_argument("--out", required=True)
ap.add_argument("--size", default="1080x1920"); ap.add_argument("--fps", type=int, default=30)
ap.add_argument("--shots", nargs="*", default=None); ap.add_argument("--still", action="store_true")
ap.add_argument("--samples", type=int, default=24); ap.add_argument("--shape", default="can")
ap.add_argument("--fruit", help="real 3D ingredient instead of flat slice pictures: yuzu|orange|lemon|lime|grapefruit")
ap.add_argument("--frame", type=int, nargs="*", help="with --still: which frame(s) to check; several frames -> <shot>_still_<frame>.png each")
ap.add_argument("--label-front", type=float, default=0.5, help="where the logo is across the label image (0-1); a label with the logo twice: 0.25")
ap.add_argument("--product", help="product.json (product_from_photo.py or by hand): bottle/lathe, box, pouch, bar; default: the can")
ap.add_argument("--spec", help="shot list JSON (ad_pipeline.py): per shot id, type, frames, event frame, key frame, camera path, cold; "
                                "renders <out>/<id>/####.png, resumes (frames already on disk are skipped)")
ap.add_argument("--label-metal", help="where the can shows bare metal through the print: 'auto' (grey/silver pixels of the label) or a mask image (white = metal)")
ap.add_argument("--liquid", help="hex colour of the drink for the crown pool (milk, coffee...); default: the fruit juice, else the set colour")
ap.add_argument("--cold", action="store_true", help="condensation beads on the can (Geometry Nodes)")
ap.add_argument("--engine", default="eevee", choices=["eevee", "cycles"], help="cycles: GPU path tracing + denoise for the final render")
ap.add_argument("--cycles-exposure", type=float, default=-0.8, help="stops; Cycles measured 0.3-0.6 stops brighter than EEVEE on the same scene, the set more")
ap.add_argument("--device", default="auto", choices=["auto", "cuda", "optix", "cpu"], help="cycles device (auto = CUDA/HIP/Metal, OptiX last)")
ap.add_argument("--view", default="neutral", choices=["neutral", "agx"], help="neutral = Khronos PBR Neutral (true label colours); agx = AgX Medium High Contrast")
a = ap.parse_args(argv)
if a.shots is None and not a.spec: a.shots = ["reveal", "hero", "macro", "burst", "trio"]
a.label = os.path.abspath(a.label) if a.label else None; a.alt = [os.path.abspath(x) for x in a.alt]; a.out = os.path.abspath(a.out)
if a.slice: a.slice = os.path.abspath(a.slice)
AC.CYCLES = AF.CYCLES = a.engine == "cycles"
PRODUCT = None
if a.product:                                                              # texture paths are relative to the product.json
    PRODUCT = json.load(open(a.product, encoding="utf-8")); _pd = os.path.dirname(os.path.abspath(a.product))
    for _k in ("texture", "front_tex", "back_tex"):
        if PRODUCT.get(_k): PRODUCT[_k] = os.path.join(_pd, PRODUCT[_k])
LEN = {"crown": 84, "twist": 84, "tear": 84, "snap": 96, "open": 75, "toppop": 75, "drops": 72, "zerog": 96, "hero_low": 90, "split": 120, "reveal": 75, "hero": 105, "macro": 75, "burst": 75, "trio": 96}


def hexrgb(h): h = h.lstrip("#"); return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def lin(c): return tuple(((x + 0.055) / 1.055) ** 2.4 if x > 0.04045 else x / 12.92 for x in c)


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene; W, H = map(int, a.size.split("x"))
    for eng in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"):
        try: sc.render.engine = eng; break
        except TypeError: continue
    sc.render.resolution_x, sc.render.resolution_y = W, H; sc.render.fps = a.fps
    sc.render.image_settings.file_format = "PNG"; sc.render.film_transparent = False
    ee = sc.eevee
    for attr, val in (("taa_render_samples", a.samples), ("use_raytracing", True), ("use_shadows", True), ("use_gtao", True),
                      ("light_threshold", 0.0002)):                       # default 0.01 cuts each light off at a distance: a hard dark
                                                                           # band across the far backdrop
        try: setattr(ee, attr, val)
        except Exception: pass
    try: sc.render.use_motion_blur = True; sc.render.motion_blur_shutter = 0.35
    except Exception: pass
    if a.view == "agx":                                                    # the guide's look; can wash out a flat label
        sc.view_settings.view_transform = "AgX"
        for lk in ("AgX - Medium High Contrast", "Medium High Contrast"):
            try: sc.view_settings.look = lk; break
            except Exception: continue
    else:
        for vt in ("Khronos PBR Neutral", "Standard"):                   # keeps the product's own colours (AgX washed them out)
            try: sc.view_settings.view_transform = vt; break
            except Exception: continue
    if a.engine == "cycles":                                               # final quality: GPU path tracing + denoise
        sc.render.engine = "CYCLES"; cy = sc.cycles
        try:
            pr = bpy.context.preferences.addons["cycles"].preferences
            order = {"auto": ("CUDA", "HIP", "METAL", "ONEAPI", "OPTIX"), "optix": ("OPTIX",), "cuda": ("CUDA",), "cpu": ()}[a.device]
            for dev in order:                                              # CUDA first: OptiX kernels fail on some drivers
                try: pr.compute_device_type = dev; pr.get_devices(); break
                except Exception: continue
            gpus = [d for d in pr.devices if d.type != "CPU"] if order else []
            for d in pr.devices: d.use = (d.type != "CPU") if gpus else True
            cy.device = "GPU" if gpus else "CPU"
        except Exception: cy.device = "CPU"
        cy.samples = a.samples; cy.use_denoising = True
        try: cy.denoiser = "OPENIMAGEDENOISE"
        except Exception: pass
        cy.max_bounces = 12; cy.transmission_bounces = 12; cy.volume_bounces = 2; cy.caustics_reflective = False
        sc.view_settings.exposure = a.cycles_exposure                      # Cycles gathers more bounce light than EEVEE: match the approved preview
        print("CYCLES device", cy.device)
    return sc


def mat(name, color=(1, 1, 1), metal=0.0, rough=0.4, image=None, alpha=False, emit=0.0):
    m = bpy.data.materials.new(name); m.use_nodes = True; nt = m.node_tree; b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1); b.inputs["Metallic"].default_value = metal; b.inputs["Roughness"].default_value = rough
    if image:
        tx = nt.nodes.new("ShaderNodeTexImage"); tx.image = bpy.data.images.load(image); nt.links.new(tx.outputs["Color"], b.inputs["Base Color"])
        if alpha:
            nt.links.new(tx.outputs["Alpha"], b.inputs["Alpha"])
            try: m.surface_render_method = "BLENDED"
            except Exception: m.blend_method = "BLEND"
    if emit:
        try: b.inputs["Emission Strength"].default_value = emit; b.inputs["Emission Color"].default_value = (*color, 1)
        except Exception: pass
    return m


def can(label, x=0.0, name="can"):
    """The can of ad_can.py (blueprint profile, real lid and tab), label wrapped on the printed area, wet with --cold."""
    me = AC.body_mesh(name, front=a.label_front); body = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(body)
    body.location = (x, 0, 0.6)
    m_label = mat(name + "_label", image=label, metal=0.35, rough=0.26)
    try: m_label.node_tree.nodes["Principled BSDF"].inputs["Coat Weight"].default_value = 0.35        # varnish over the print
    except Exception: pass
    if a.label_metal: metal_ink(m_label, label, a.label_metal)
    m_metal = AC.aluminium(name + "_metal"); me.materials.append(m_label); me.materials.append(m_metal)
    AC.lid_parts(body, m_metal, name)
    if a.cold: AC.condensation(body, m_label, seed=len(bpy.data.objects))
    bpy.context.view_layer.objects.active = body
    return body


def metal_ink(m, label, how):
    """Printed cans leave the aluminium bare in places (silver panels, unprinted lines): there the label is metal."""
    import numpy as np
    img = bpy.data.images.load(label) if isinstance(label, str) else label
    if how == "auto":                                                      # grey/silver pixels: low saturation, mid-high value
        W, H = img.size; px = np.empty(W * H * 4, np.float32); img.pixels.foreach_get(px); px = px.reshape(-1, 4)
        mx, mn = px[:, :3].max(1), px[:, :3].min(1); sat = (mx - mn) / (mx + 1e-6)
        mask = ((sat < 0.1) & (mx > 0.45) & (mx < 0.93)).astype(np.float32)
        rgba = np.ones((W * H, 4), np.float32); rgba[:, 0] = rgba[:, 1] = rgba[:, 2] = mask
        mi = bpy.data.images.new("metal_mask", W, H, float_buffer=True); mi.colorspace_settings.name = "Non-Color"; mi.pixels.foreach_set(rgba.ravel()); mi.pack()
    else:
        mi = bpy.data.images.load(how); mi.colorspace_settings.name = "Non-Color"
    nt = m.node_tree; N = nt.nodes; L = nt.links; b = N["Principled BSDF"]
    tx = N.new("ShaderNodeTexImage"); tx.image = mi
    uvsrc = next((n for n in N if n.type == "TEX_IMAGE" and n.image and n.image != mi), None)
    if uvsrc and uvsrc.inputs["Vector"].is_linked: L.new(uvsrc.inputs["Vector"].links[0].from_socket, tx.inputs["Vector"])
    mr = N.new("ShaderNodeMapRange"); mr.inputs["To Min"].default_value = b.inputs["Metallic"].default_value; mr.inputs["To Max"].default_value = 1.0
    L.new(tx.outputs["Color"], mr.inputs["Value"]); L.new(mr.outputs["Result"], b.inputs["Metallic"])
    rr = N.new("ShaderNodeMapRange"); rr.inputs["To Min"].default_value = b.inputs["Roughness"].default_value; rr.inputs["To Max"].default_value = 0.16
    L.new(tx.outputs["Color"], rr.inputs["Value"]); L.new(rr.outputs["Result"], b.inputs["Roughness"])


def co2_puff(loc, f0, n_end, rise=0.35):
    """The CO2 mist that escapes when a can or bottle opens: a volume blob with wispy noise density that bursts, rises,
    spreads and fades."""
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=1, location=loc); v = bpy.context.object; v.name = "co2"
    m = bpy.data.materials.new("co2"); m.use_nodes = True; nt = m.node_tree; N = nt.nodes; L = nt.links
    for nd in list(N):
        if nd.type == "BSDF_PRINCIPLED": N.remove(nd)
    out = N["Material Output"]; vol = N.new("ShaderNodeVolumePrincipled"); vol.inputs["Color"].default_value = (1, 1, 1, 1); vol.inputs["Anisotropy"].default_value = 0.4   # glows when backlit
    tc = N.new("ShaderNodeTexCoord"); mp = N.new("ShaderNodeMapping"); mp.inputs["Scale"].default_value = (1.0, 1.0, 0.35)   # stretched upward: wisps
    tex = N.new("ShaderNodeTexNoise"); tex.inputs["Scale"].default_value = 3.2; tex.inputs["Detail"].default_value = 10
    _ = (L.new(tc.outputs["Object"], mp.inputs["Vector"]), L.new(mp.outputs["Vector"], tex.inputs["Vector"]))
    edge = N.new("ShaderNodeTexGradient"); edge.gradient_type = "SPHERICAL"; L.new(tc.outputs["Object"], edge.inputs["Vector"])
    ramp = N.new("ShaderNodeMapRange"); ramp.inputs["From Min"].default_value = 0.5; ramp.inputs["From Max"].default_value = 0.78
    mul = N.new("ShaderNodeMath"); mul.operation = "MULTIPLY"
    soft = N.new("ShaderNodeMath"); soft.operation = "MULTIPLY"                       # fade to nothing at the edge: no ball outline
    L.new(tex.outputs["Fac"], ramp.inputs["Value"]); L.new(ramp.outputs["Result"], soft.inputs[0]); L.new(edge.outputs["Fac"], soft.inputs[1])
    L.new(soft.outputs[0], mul.inputs[0]); L.new(mul.outputs[0], vol.inputs["Density"])
    L.new(vol.outputs["Volume"], out.inputs["Volume"]); v.data.materials.append(m)
    dens = mul.inputs[1]
    for fr, d in ((1, 0), (f0, 0), (f0 + 3, 40), (f0 + 14, 16), (min(f0 + 34, n_end), 0)):
        dens.default_value = d; dens.keyframe_insert("default_value", frame=fr)
    x, y, z = loc
    key(v, 1, scale=(0.01,) * 3, location=loc); key(v, f0, scale=(0.02,) * 3, location=loc)
    key(v, f0 + 6, scale=(0.05, 0.05, 0.08), location=(x, y, z + rise * 0.25)); key(v, n_end, scale=(0.11, 0.11, 0.17), location=(x, y, z + rise))
    return v


def studio(c1, c2):
    sc = bpy.context.scene; w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True
    bg = w.node_tree.nodes["Background"]; bg.inputs["Color"].default_value = (*lin(c2), 1); bg.inputs["Strength"].default_value = 0.35
    hdri = os.path.join(bpy.utils.system_resource("DATAFILES"), "studiolights", "world", "studio.exr")   # ships with Blender (CC0)
    if os.path.exists(hdri):                                               # metal and water reflect a studio, not the set colour
        env = w.node_tree.nodes.new("ShaderNodeTexEnvironment"); env.image = bpy.data.images.load(hdri)
        b2 = w.node_tree.nodes.new("ShaderNodeBackground"); b2.inputs["Color"].default_value = (*lin(c2), 1); b2.inputs["Strength"].default_value = 0.28
        w.node_tree.links.new(env.outputs["Color"], bg.inputs["Color"]); bg.inputs["Strength"].default_value = 0.4
        add = w.node_tree.nodes.new("ShaderNodeAddShader"); w.node_tree.links.new(bg.outputs[0], add.inputs[0]); w.node_tree.links.new(b2.outputs[0], add.inputs[1])
        w.node_tree.links.new(add.outputs[0], w.node_tree.nodes["World Output"].inputs["Surface"])        # neutral reflections + the set's warm fill
    try: w.use_sun_shadow = False                                          # EEVEE turns the HDRI's hot spot into a sun; its shadow drew
    except Exception: pass                                                 # a hard band across the curved sweep (the key light shadows the product)
    LK.cyclorama(mat("floor", lin(c1), 0.0, 0.22), lin(c1), lin(c2))      # one seamless sweep: no floor-wall corner line
    def area(name, loc, energy, size, color=(1, 1, 1)):
        bpy.ops.object.light_add(type="AREA", location=loc); L = bpy.context.object; L.name = name; L.data.energy = energy; L.data.size = size; L.data.color = color
        d = Vector((0, 0, 0.6)) - L.location; L.rotation_euler = d.to_track_quat("-Z", "Y").to_euler(); return L
    area("key", (2.6, -3.2, 3.2), 380, 3.0)
    area("rimL", (-2.8, 1.6, 2.2), 700, 0.6, (1.0, 0.95, 0.85)); area("rimR", (2.8, 1.8, 2.0), 520, 0.6, (1.0, 0.9, 0.8))
    sweep = area("sweep", (-3.0, -2.0, 1.2), 0, 0.25)                     # animated light sweep across the label
    return sweep


def slices(n, img, seed=3, spread=1.6):
    import random; random.seed(seed); out = []
    m = mat("slice", image=img, alpha=True, rough=0.35)
    for k in range(n):
        bpy.ops.mesh.primitive_plane_add(size=0.42, location=(random.uniform(-spread, spread), random.uniform(-2.2, 0.8), random.uniform(0.1, 1.6)))
        s = bpy.context.object; s.data.materials.append(m)
        s.rotation_euler = (random.uniform(0, 3), random.uniform(0, 3), random.uniform(0, 3)); out.append(s)
    return out


def pieces3d(n, kind, seed=3, spread=1.6, R=0.2):
    """Real 3D flavour pieces: wheels, halves and whole fruit (shared meshes), scattered like slices() does."""
    import random; random.seed(seed); out = []
    kinds = [("wheel", ("wheel", 0.16)), ("half", "top"), ("whole", None)]
    meshes = {}
    for nm, keep in kinds:
        ob = AF.fruit(kind, R if nm != "whole" else R * 0.8, keep, name="piece_" + nm, with_stem=False)
        meshes[nm] = ob.data; bpy.data.objects.remove(ob)
    for k in range(n):
        nm = ("wheel", "wheel", "half", "whole")[k % 4]
        ob = bpy.data.objects.new(f"piece{k}", meshes[nm]); bpy.context.scene.collection.objects.link(ob)
        ob.location = (random.uniform(-spread, spread), random.uniform(-2.2, 0.8), random.uniform(0.1, 1.6))
        ob.rotation_euler = (random.uniform(0, 3), random.uniform(0, 3), random.uniform(0, 3)); out.append(ob)
    return out


def light_blade(f0, z0=2.3, z1=-0.2, x=0.0, y=-1.1):
    """A thin glowing line that slashes down through the fruit just before it splits (the 'cut')."""
    bpy.ops.mesh.primitive_cube_add(size=1, location=(x, y, z0)); b = bpy.context.object; b.name = "blade"
    b.data.materials.append(mat("blade", (1, 0.98, 0.9), emit=40.0))
    key(b, f0 - 5, location=(x, y, z0), scale=(0.0, 0.0, 0.0)); key(b, f0 - 2, location=(x, y, (z0 + z1) / 2), scale=(0.012, 0.012, z0 - z1))
    key(b, f0 + 1, location=(x, y, z1), scale=(0.0, 0.0, 0.0))
    return b


def open_shot(n, F=22, view="45"):
    """What the product DOES: the can opens. The tab tenses, snaps up, its nose pushes the flap in, CO2 mist bursts out
    of the hole and a fine spray jumps; the camera keeps moving. view "45" = macro over the lid at 45 deg; "top" = the
    guide's Top Pop, straight down on the lid. Sound: fizz at frame F."""
    body = can(a.label); body.rotation_euler.z = math.radians(90)          # opening and label front toward the lens
    nm = body.name; tp, fp = bpy.data.objects[nm + "_tabpivot"], bpy.data.objects[nm + "_flappivot"]
    for fr, ang in ((1, 0), (F - 8, -10), (F, -78), (F + 6, -62), (n, -58)): key(tp, fr, rotation_euler=(0, math.radians(ang), 0))
    for fr, ang in ((1, 0), (F - 2, 0), (F + 2, -58), (n, -60)): key(fp, fr, rotation_euler=(0, math.radians(ang), 0))
    if view == "top": key(body, 1, rotation_euler=(0, 0, math.radians(60))); key(body, n, rotation_euler=(0, 0, math.radians(100)))
    else: key(body, 1, rotation_euler=(0, 0, math.radians(80))); key(body, n, rotation_euler=(0, 0, math.radians(97)))
    lz = 0.6 + AC.LIDZ; hole = (0.0, AC.OPEN_X, lz + 0.01)                 # where the hole is when it opens (rotation ~90 deg)
    co2_puff(hole, F, n)
    AF.splash(a.fruit or "yuzu", hole, F, n, AF.ramp(F, fast=4, slow=0.4), n=26, seed=8, axis="z", speed=0.45, g=5.0, size=0.16, disc=0.03)
    bpy.ops.object.light_add(type="AREA", location=(0, -0.6, 3.2)); sb = bpy.context.object; sb.data.size = 3.5; sb.data.energy = 420
    sb.rotation_euler = (math.radians(-12), 0, 0)                          # white softbox: aluminium reads silver, not set-coloured
    if view == "top":
        sb.location = (1.6, -0.2, lz + 1.2); sb.data.energy = 110; sb.rotation_euler = (0, math.radians(55), 0)   # low side softbox: a gradient, not a white lid
        bpy.ops.mesh.primitive_plane_add(size=8, location=(0, 0, lz + 2.6)); fl = bpy.context.object      # black flag overhead: a flat lid
        fl.data.materials.append(mat("flag", (0.02, 0.02, 0.02), 0.0, 0.9))                              # mirrors whatever is above it (Cycles)
        for nd in bpy.context.scene.world.node_tree.nodes:                 # a flat lid seen from above mirrors the world overhead:
            if nd.type == "BACKGROUND" and not nd.inputs["Color"].is_linked: nd.inputs["Strength"].default_value = 0.04   # the warm fill turns a flat lid brown
        cam = camera((0, -0.06, lz + 1.5), (0, -0.05, lz), 50, fstop=4.0)
        key(cam, 1, location=(0, -0.06, lz + 1.6)); key(cam, n, location=(0, -0.05, lz + 1.25))
    else:
        cam = camera((0, -1.3, lz + 0.55), (0, -0.04, lz - 0.01), 55, fstop=3.2)
        key(cam, 1, location=(0.12, -1.35, lz + 0.57)); key(cam, n, location=(-0.05, -1.05, lz + 0.41))
    try: bpy.context.scene.eevee.volumetric_tile_size = "4"                 # finer mist
    except Exception: pass


def drops_shot(n, F=18):
    """Guide shot 1 (Macro): 85 mm, shallow focus, the camera rises slowly along the cold, wet label; the beads catch the
    studio lights and one bead lets go and runs down."""
    cold = a.cold; a.cold = True
    body = can(a.label); body.rotation_euler.z = math.radians(90); a.cold = cold
    AC.run_drop(body, F, n - 5, 0.32, -0.22, math.pi)
    key(body, 1, rotation_euler=(0, 0, math.radians(84))); key(body, n, rotation_euler=(0, 0, math.radians(96)))
    cam = camera((0.0, -1.55, 0.45), (0, -0.33, 0.55), 85, focus=1.22, fstop=1.6)
    key(cam, 1, location=(0.06, -1.55, 0.38)); key(cam, n, location=(-0.04, -1.5, 0.86))
    tgt = bpy.data.objects["CamTarget"]; key(tgt, 1, location=(0, -0.33, 0.42)); key(tgt, n, location=(0, -0.33, 0.9))


def zerog_shot(n):
    """Guide shot 3 (Zero-G): the can floats turning slowly, ice cubes and the flavour drift around it without gravity,
    70 mm dolly in."""
    import random; rnd = random.Random(5); zc = 1.05
    body = hero_obj(a.label); body.location = (0, 0, zc)
    key(body, 1, rotation_euler=(math.radians(8), math.radians(-6), math.radians(40)), location=(0, 0, zc - 0.04))
    key(body, n, rotation_euler=(math.radians(-6), math.radians(5), math.radians(110)), location=(0, 0, zc + 0.05))
    for k in range(10):
        ang = rnd.uniform(0, 2 * math.pi); rr = rnd.uniform(0.62, 1.15); h = rnd.uniform(-0.75, 0.8)
        p0 = Vector((math.cos(ang) * rr, math.sin(ang) * rr * 0.8, zc + h))
        if k < 7 or not a.fruit: ob = AC.ice_cube(f"ice{k}", rnd.uniform(0.14, 0.24), k)
        else: ob = AF.fruit(a.fruit, 0.15, ("wheel", 0.16) if k % 2 else "top", name=f"fl{k}", with_stem=False)
        drift = Vector((rnd.uniform(-0.08, 0.08), rnd.uniform(-0.08, 0.08), rnd.uniform(0.04, 0.14)))
        r0 = Vector((rnd.uniform(0, 3), rnd.uniform(0, 3), rnd.uniform(0, 3)))
        key(ob, 1, location=p0, rotation_euler=r0); key(ob, n, location=p0 + drift, rotation_euler=r0 + Vector((0.6, 0.4, 0.5)))
    cam = camera((0, -6.6, zc + 0.05), (0, 0, zc), 70, focus=6.4, fstop=3.5)
    key(cam, 1, location=(0.15, -6.8, zc + 0.12)); key(cam, n, location=(-0.05, -5.4, zc))


def hero_low_shot(n):
    """Guide shot 4 (Hero): 85 mm from slightly below, the can settles still in the centre with the logo to the lens and
    empty space above for the line."""
    body = hero_obj(a.label)
    flat = bool(PRODUCT) and PRODUCT.get("shape") in ("pouch", "box", "bar")   # a flat product never shows its thin edge
    key(body, 1, location=(0, 0, 0.95), rotation_euler=(0, 0, math.radians(62 if flat else 20)))
    key(body, int(n * 0.55), location=(0, 0, 0.6), rotation_euler=(0, 0, math.radians(86)))
    key(body, n, location=(0, 0, 0.6), rotation_euler=(0, 0, math.radians(90)))
    cam = camera((0, -6.2, 0.32), (0, 0, 0.95), 85, focus=6.2, fstop=4.0)
    key(cam, 1, location=(0.1, -6.5, 0.3)); key(cam, n, location=(0, -5.9, 0.34))


def hero_obj(label, x=0.0, name="can"):
    """The product of --product (bottle, box, pouch, bar, any round product from a photo), else the can."""
    if PRODUCT and PRODUCT.get("shape", "can") != "can":
        o = AS.build(PRODUCT, name, label, a.label_front)
        if PRODUCT["shape"] == "bar":                                      # a bar's front is its long side: turn it so that
            w = bpy.data.objects.new(name + "_front", None); bpy.context.scene.collection.objects.link(w)   # 'rotation 90' shows it
            o.parent = w; o.rotation_euler = (math.radians(-24), 0, math.radians(-90)); w.scale = (1.35,) * 3; o = w   # tilted: the top shows
        o.location = (x, 0, 0.6); return o
    return can(label, x, name)


def chip(name, r, seed):
    """A crisp: a thin wavy saddle disc, golden with darker blisters and salt."""
    rnd = random.Random(seed); bpy.ops.mesh.primitive_circle_add(vertices=40, radius=r, fill_type="TRIFAN"); o = bpy.context.object; o.name = name
    bpy.ops.object.mode_set(mode="EDIT"); bpy.ops.mesh.subdivide(number_cuts=3); bpy.ops.object.mode_set(mode="OBJECT")
    c = rnd.uniform(1.2, 2.2) / r
    for v in o.data.vertices:
        x, y = v.co.x, v.co.y; v.co.z = c * 0.25 * (x * x - y * y) + r * 0.04 * math.sin(x / r * 9 + seed) * math.cos(y / r * 7)
        s = 1 + 0.08 * math.sin(math.atan2(y, x) * 5 + seed); v.co.x *= s; v.co.y *= s
    sol = o.modifiers.new("t", "SOLIDIFY"); sol.thickness = r * 0.05
    bpy.ops.object.shade_smooth()
    m = bpy.data.materials.get("chip")
    if not m:
        m = AC.principled("chip", lin(hexrgb("#F2CF6B")), 0.0, 0.45, **{"Subsurface Weight": 0.2}); nt = m.node_tree
        nz = nt.nodes.new("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 14; rp = nt.nodes.new("ShaderNodeValToRGB")
        rp.color_ramp.elements[0].color = (*lin(hexrgb("#D9A441")), 1); rp.color_ramp.elements[1].color = (*lin(hexrgb("#F7DC86")), 1)   # golden, a few browner blisters
        rp.color_ramp.elements[0].position = 0.35; rp.color_ramp.elements[1].position = 0.6
        nt.links.new(nz.outputs["Fac"], rp.inputs["Fac"]); nt.links.new(rp.outputs["Color"], nt.nodes["Principled BSDF"].inputs["Base Color"])
        vo = nt.nodes.new("ShaderNodeTexVoronoi"); vo.inputs["Scale"].default_value = 60; bp = nt.nodes.new("ShaderNodeBump"); bp.inputs["Strength"].default_value = 0.3
        nt.links.new(vo.outputs["Distance"], bp.inputs["Height"]); nt.links.new(bp.outputs["Normal"], nt.nodes["Principled BSDF"].inputs["Normal"])
    o.data.materials.append(m); return o


def ballistic(obj, p0, v0, f0, n, w, g=6.0, spin=(0, 0, 0), r0=(0, 0, 0), every=2):
    """Key an object on a ballistic path through simulated time w(frame) (speed ramp aware)."""
    for fr in list(range(1, n + 1, every)) + [n]:
        t = w(fr); p = Vector(p0) + Vector(v0) * t + Vector((0, 0, -0.5 * g * t * t))
        key(obj, fr, location=p, rotation_euler=Vector(r0) + Vector(spin) * t)


def twist_shot(n, F=24):
    """The bottle opens: the cap turns (counter-clockwise, the thread lifts it a little), lets go on the event, pops up
    spinning in slow motion, a puff of CO2 escapes the neck. Macro on the neck."""
    body = hero_obj(a.label); body.rotation_euler.z = math.radians(90)
    piv = bpy.data.objects.get(body.name + "_cappivot")
    if not piv: raise SystemExit("twist needs a product with a cap (bottle: cap_from_mm)")
    bpy.context.view_layer.update(); nz = (body.matrix_world @ piv.location).z if False else 0.6 + piv.location.z
    w = AF.ramp(F, fast=4, slow=0.35)
    for fr in range(1, n + 1):
        if fr <= F:
            t = fr / F; key(piv, fr, rotation_euler=(0, 0, math.radians(260) * t ** 1.4), location=(0, 0, piv.location.z if fr > 1 else piv.location.z))
        else:
            s = w(fr); key(piv, fr, rotation_euler=(math.radians(25) * min(1, s * 3), 0, math.radians(260) + math.radians(900) * s),
                           location=(0, 0, piv.location.z + 0.55 * s - 0.5 * s * s))
    co2_puff((0.0, 0.0, nz + 0.01), F, n, rise=0.3)
    bpy.ops.object.light_add(type="AREA", location=(0, -0.6, 3.2)); sb = bpy.context.object; sb.data.size = 3.0; sb.data.energy = 300
    cam = camera((0, -1.9, nz + 0.2), (0, 0, nz + 0.12), 55, fstop=3.5)                   # neck low in frame, room above for the cap
    key(cam, 1, location=(0.15, -1.95, nz + 0.18)); key(cam, n, location=(-0.05, -1.7, nz + 0.26))
    tg = bpy.data.objects["CamTarget"]; key(tg, 1, location=(0, 0, nz + 0.08)); key(tg, n, location=(0, 0, nz + 0.25))


def tear_shot(n, F=22):
    """The pouch opens: the top strip tears off from the notch along a jagged line and flies away, crisps burst out
    of the opening in slow motion. The bag faces the lens."""
    PRODUCT_T = dict(PRODUCT or {"shape": "pouch"}); body = AS.pouch(PRODUCT_T, "bag", tear_at=0.86); body.location = (0, 0, 0.6)
    body.rotation_euler.z = math.radians(90); key(body, 1, rotation_euler=(0, 0, math.radians(84))); key(body, n, rotation_euler=(0, 0, math.radians(96)))
    sp = bpy.data.objects["bag_strippivot"]; w = AF.ramp(F, fast=5, slow=0.3)
    for fr in range(1, n + 1):
        if fr < F - 6: key(sp, fr, rotation_euler=(0, 0, 0), location=sp.location.copy())
        elif fr <= F: t = (fr - F + 6) / 6; key(sp, fr, rotation_euler=(math.radians(-28) * t, 0, 0))
        else:
            s = w(fr); key(sp, fr, rotation_euler=(math.radians(-28) - math.radians(160) * s, math.radians(40) * s, 0))
    top = 0.6 + (0.86 - 0.5) * 1.157                                       # the tear line, world height
    random.seed(7)
    for i in range(20):
        c = chip(f"chip{i}", random.uniform(0.08, 0.13), i)
        x0 = random.uniform(-0.45, 0.45)                                   # across the bag (world x: the bag faces the lens)
        ballistic(c, (x0, random.uniform(-0.05, 0.05), top - 0.05), (x0 * 1.2 + random.uniform(-0.35, 0.35), random.uniform(-0.5, 0.1), random.uniform(1.6, 2.8)),
                  F, n, lambda fr, F=F + 2 + i % 4: w(fr) - w(F) if fr > F else 0.0, g=5.0,
                  spin=(random.uniform(-6, 6), random.uniform(-6, 6), random.uniform(-4, 4)), r0=(random.uniform(0, 3), random.uniform(0, 3), 0))
        key(c, 1, scale=(0.001,) * 3); key(c, F + 1 + i % 4, scale=(0.001,) * 3); key(c, F + 3 + i % 4, scale=(1, 1, 1))
    cam = camera((0, -4.0, 1.05), (0, 0, 0.95), 50, fstop=4.0)
    key(cam, 1, location=(0.1, -4.2, 1.0)); key(cam, n, location=(-0.05, -3.6, 1.12))


def CAN_H_HALF(): return 1.157 / 2


def snap_shot(n, F=24):
    """A filled bar snaps: the ends go down, the break opens from the top, crumbs fly, the filling (caramel) pulls into
    strands that stretch, thin, sag and finally break into two drooping tails. Slow motion after the snap."""
    bar = AS.build(PRODUCT or {"shape": "bar"}, "bar"); bar.location = (0, 0, 0.75); bar.rotation_euler.z = math.radians(-14)   # side on: the gap and the strands face the lens
    L_, W_, H_ = bar["size"]; hL, hR = bpy.data.objects["bar_halfL"], bpy.data.objects["bar_halfR"]
    w = AF.ramp(F, fast=4, slow=0.3)
    ang = lambda fr: 0.0 if fr <= F else math.radians(16) * (1 - math.exp(-w(fr) * 7))
    sep = lambda fr: 0.0 if fr <= F else 0.11 * (1 - math.exp(-w(fr) * 2.4))          # halves part slowly: the filling has time to stretch
    for fr in range(1, n + 1):
        th, d = ang(fr), sep(fr)
        key(hL, fr, rotation_euler=(0, -th, 0), location=(-d, 0, -H_ / 2)); key(hR, fr, rotation_euler=(0, th, 0), location=(d, 0, -H_ / 2))
    bpy.context.view_layer.update()
    fil = AC.principled("filling", lin(hexrgb((PRODUCT or {}).get("filling", "#C8741E"))), 0.0, 0.12,
                        **{"Coat Weight": 0.7, "Coat Roughness": 0.05, "Subsurface Weight": 0.15 if AC.CYCLES else 0.4})
    mb = bpy.data.metaballs.new("goo"); mb.resolution = 0.02; mb.render_resolution = 0.006; mb.threshold = 0.6
    goo = bpy.data.objects.new("goo", mb); bpy.context.scene.collection.objects.link(goo); goo.parent = bar; mb.materials.append(fil)
    rnd = random.Random(4); strands = []
    for k in range(7):
        y = rnd.uniform(-0.38, 0.38) * W_; z = H_ * rnd.uniform(0.45, 0.8); brk = rnd.uniform(0.13, 0.27); r = rnd.uniform(0.014, 0.024)
        strands.append((y, z, brk, r, [mb.elements.new() for _ in range(22)]))     # close elements: a strand, not beads
    def face_pt(side, fr, y, z):                                           # a point on a broken face, in bar space
        th, d = ang(fr), sep(fr); s = -1 if side == "L" else 1; t = th * s
        p = Vector((0, y, z)); p = Vector((p.x * math.cos(t) + p.z * math.sin(t), p.y, -p.x * math.sin(t) + p.z * math.cos(t)))
        return p + Vector((s * d, 0, -H_ / 2))
    for fr in range(1, n + 1):
        for si, (y, z, brk, r, els) in enumerate(strands):
            A, B = face_pt("L", fr, y, z), face_pt("R", fr, y, z); gap = (B - A).length
            for j, e in enumerate(els):
                t = j / (len(els) - 1)
                if fr <= F + 1: e.co = A.lerp(B, t); e.radius = 0.0
                elif gap < brk:                                            # stretching: thins in the middle, sags
                    thin = max(0.25, 1 - 0.65 * (1 - abs(2 * t - 1)) * gap / brk)
                    sag = 2.2 * gap * gap * (1 - (2 * t - 1) ** 2)
                    e.co = A.lerp(B, t) - Vector((0, 0, sag)); e.radius = r * thin * (1.4 if j in (0, len(els) - 1) else 1)
                else:                                                      # broken: two tails droop from the faces
                    side_p = A if t < 0.5 else B; tt = (t if t < 0.5 else 1 - t) * 2
                    droop = min(1.0, (gap - brk) * 6)
                    e.co = side_p + Vector(((B - A).normalized().x * 0.04 * tt * (1 if t < 0.5 else -1), 0, -0.09 * tt * (0.4 + droop)))
                    e.radius = r * max(0.3, 1 - 0.6 * tt)
                ix = si * len(els) + j
                mb.keyframe_insert(f"elements[{ix}].co", frame=fr); mb.keyframe_insert(f"elements[{ix}].radius", frame=fr)
    choc = bpy.data.materials.get("bar_choc")
    for i in range(26):                                                    # crumbs off the top of the break
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=rnd.uniform(0.004, 0.012)); c = bpy.context.object; c.name = f"crumb{i}"
        for v in c.data.vertices: v.co *= rnd.uniform(0.6, 1.3)
        c.data.materials.append(choc); c.parent = bar
        p0 = (rnd.uniform(-0.01, 0.01), rnd.uniform(-0.4, 0.4) * W_, H_ / 2)
        ballistic(c, p0, (rnd.uniform(-0.5, 0.5), rnd.uniform(-0.4, 0.4), rnd.uniform(0.5, 1.4)), F, n, lambda fr: max(0.0, w(fr)), g=5.0,
                  spin=(rnd.uniform(-9, 9), rnd.uniform(-9, 9), 0))
        key(c, 1, scale=(0.001,) * 3); key(c, F, scale=(0.001,) * 3); key(c, F + 1, scale=(1, 1, 1))
    cam = camera((0.05, -1.8, 0.98), (0, 0, 0.76), 55, fstop=3.2)            # tight on the break: the ends may leave the frame
    key(cam, 1, location=(0.12, -1.9, 1.0)); key(cam, n, location=(-0.02, -1.45, 0.93))


def split_shot(n, F=30):
    """The hero concept: a real fruit turns in the light; a steel blade sweeps through it while a seam of light runs
    down its skin and juice beads along the cut; the halves fly apart in a speed ramp, juice films stretch between the
    faces and tear, mist and pulp fly, and the can rises spinning out of the middle (references/ad-craft.md)."""
    kind = a.fruit or "yuzu"; R = 0.95; zc = 1.0; ang = math.radians(30)            # the cut plane turned toward the lens
    rig = bpy.data.objects.new("FruitRig", None); bpy.context.scene.collection.objects.link(rig); rig.location = (0, 0, zc)
    halves = []
    for keep in ("top", "bottom"):
        h = AF.fruit(kind, R, keep, name="half_" + keep); h.parent = rig; h.rotation_euler = (0, math.radians(90), 0); halves.append(h)
    bpy.context.view_layer.update(); pts = CUT.ring_points(halves[0], R)
    key(rig, 1, rotation_euler=(0.15, 0, ang - math.radians(65)), location=(0, 0, zc - 0.05)); key(rig, F, rotation_euler=(0, 0, ang), location=(0, 0, zc + 0.04))
    w = AF.ramp(F, fast=5, slow=0.3); gap = lambda fr: 0.0 if fr <= F else 2 * 1.05 * (1 - math.exp(-w(fr) * 5))
    body = hero_obj(a.label); body.location = (0, 0, zc)
    for fr in range(F - 1, n + 1, 1):
        s_ = w(fr); o = 1 - math.exp(-s_ * 5); wob = math.sin(s_ * 26) * math.exp(-s_ * 5) * math.radians(7)   # the halves tip and wobble
        for h, sg in zip(halves, (1, -1)):
            key(h, fr, location=(sg * (0.0005 + 1.05 * o), 0.25 * o, -0.12 * o), rotation_euler=(sg * wob, math.radians(90), sg * math.radians(70) * (1 - math.exp(-s_ * 4))))
        g = 0.001 if fr < F else 0.15 + 0.85 * (1 - math.exp(-s_ * 4.5))
        key(body, fr, scale=(g, g, g), rotation_euler=(0, 0, math.radians(90) - math.radians(600) * math.exp(-s_ * 3.2)))
    key(body, 1, scale=(0.001,) * 3)
    jc = AF.lin(AF.FRUITS[kind]["juice"]); jm = AF.juice_material(kind)
    CUT.blade(rig, R, F); CUT.seam(rig, pts, F); CUT.beads(rig, pts, F, jm)
    CUT.sheets(rig, halves, R, F, n, gap, jc)
    basis = Matrix.Rotation(ang, 3, "Z"); c0 = (0, 0, zc)
    CUT.flyers(c0, F, n, lambda fr: w(fr) - 0.01, CUT.sphere_mesh("mist"), AC.principled("mist", tuple(x * 0.6 + 0.4 for x in jc), 0.0, 0.2,
               **{"Emission Color": (*jc, 1), "Emission Strength": 0.4}), 110, (1.8, 3.4), (0.003, 0.008), 21, g=4.0, life=0.8, basis=basis)
    CUT.flyers(c0, F, n, w, CUT.vesicle_mesh("pulp"), AC.principled("pulp", jc, 0.0, 0.15, **{"Subsurface Weight": 0.4, "Coat Weight": 0.5}),
               16, (0.9, 1.8), (0.012, 0.022), 22, g=5.0, life=1.4, basis=basis)
    AF.splash(kind, (0, 0, zc), F, n, w, n=34, seed=11, axis="x", speed=1.25, size=1.2, disc=R * 0.8)
    cam = camera((0, -4.6, 1.05), (0, 0, zc), 40, focus=4.4, fstop=4.0)
    key(cam, 1, location=(0.2, -4.4, 1.1)); key(cam, F, location=(0, -4.0, 1.05)); key(cam, F + 12, location=(0, -4.6, 1.0)); key(cam, n, location=(0, -3.7, 0.95))


def crown_shot(n, F=24):
    """The product drops into a pool of its own liquid: a crown splash rises round it in slow motion, drops fly off the
    crown's fingers, ripple rings spread across the pool."""
    kind = a.fruit
    col = lin(hexrgb(a.liquid)) if a.liquid else AF.lin(AF.FRUITS[kind]["juice"]) if kind else lin(hexrgb((PRODUCT or {}).get("liquid", a.set[0])))
    w = AF.ramp(F, fast=4, slow=0.3); zp = 0.05
    CUT.pool((0, 0, zp), 30.0, F, n, col)                                   # the whole floor is the liquid
    body = hero_obj(a.label); r0 = 0.36
    for fr, z, rx in ((1, 2.4, 0.18), (F - 6, 1.1, 0.06), (F, 0.6 + zp - 0.07, 0.0), (F + 4, 0.6 + zp - 0.02, 0.0), (n, 0.6 + zp - 0.045, 0.0)):   # settles a little into the liquid
        key(body, fr, location=(0, 0, z), rotation_euler=(rx, 0, math.radians(90 - 25 * rx)))
    CUT.crown((0, 0, zp), r0, F, n, w, col)
    cam = camera((0, -3.6, 0.55), (0, 0, 0.62), 50, fstop=3.5)
    key(cam, 1, location=(0.1, -3.9, 0.6)); key(cam, n, location=(-0.05, -3.2, 0.5))


def camera(loc, look, lens=50, focus=None, fstop=2.0):
    cam = bpy.data.objects.get("Cam")
    if not cam:
        bpy.ops.object.camera_add(); cam = bpy.context.object; cam.name = "Cam"; bpy.context.scene.camera = cam
    cam.location = loc; cam.data.lens = lens
    d = Vector(look) - Vector(loc)
    tgt = bpy.data.objects.get("CamTarget")
    if not tgt:
        tgt = bpy.data.objects.new("CamTarget", None); bpy.context.scene.collection.objects.link(tgt)
        con = cam.constraints.new("TRACK_TO"); con.target = tgt; con.track_axis = "TRACK_NEGATIVE_Z"; con.up_axis = "UP_Y"   # stays aimed while it moves
    tgt.location = look
    cam.data.dof.use_dof = True; cam.data.dof.aperture_fstop = fstop; cam.data.dof.focus_distance = focus or d.length
    return cam


def key(obj, frame, **kw):
    for k, v in kw.items(): setattr(obj, k, v); obj.keyframe_insert(k, frame=frame)


def ease_all():
    for ob in bpy.data.objects:
        ad = ob.animation_data
        if not ad or not ad.action: continue
        fcs = getattr(ad.action, "fcurves", None)
        if fcs is None:                                                    # Blender 5 layered actions
            try: fcs = [fc for layer in ad.action.layers for strip in layer.strips for cb in strip.channelbags for fc in cb.fcurves]
            except Exception: fcs = []
        for fc in fcs:
            for kp in fc.keyframe_points: kp.interpolation = "BEZIER"; kp.easing = "AUTO"


def anchors(sc, sid, spec, n):
    """Where the product is on screen (0-1, top-left origin) at a few frames: its label front, top, left and right
    edges. ad_pipeline points callouts at these, so a label line lands on the product, not on the set."""
    from bpy_extras.object_utils import world_to_camera_view
    root = next((bpy.data.objects[k] for k in ("bar_front", "can_front", "can", "bag", "bar") if k in bpy.data.objects), None)   # a wrapper first: it holds the front
    if not root or not sc.camera: return
    meshes = [o for o in [root] + list(root.children_recursive) if o.type == "MESH" and o.visible_get()]
    out = {}
    base = int(spec.get("base") or n)
    for fr in sorted({1, int(spec.get("key") or base * 0.6), max(1, int(base * 0.75)), base}):
        sc.frame_set(fr); dg = bpy.context.evaluated_depsgraph_get(); pts = []
        for o in meshes:
            oe = o.evaluated_get(dg); pts += [oe.matrix_world @ Vector(c) for c in oe.bound_box]
        if not pts: continue
        lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts))); hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
        c = (lo + hi) / 2
        def scr(p): v = world_to_camera_view(sc, sc.camera, p); return [round(v.x, 4), round(1 - v.y, 4), round(v.z, 3)]
        out[str(fr)] = {"label": scr(Vector((c.x, lo.y, c.z))), "top": scr(Vector((c.x, c.y, hi.z))), "left": scr(Vector((lo.x, lo.y, c.z))),
                        "right": scr(Vector((hi.x, lo.y, c.z))), "low": scr(Vector((c.x, lo.y, lo.z + (hi.z - lo.z) * 0.3)))}
    out["tracks"] = feature_tracks(sc, root, meshes, n)                    # callouts point at these, frame by frame
    json.dump(out, open(os.path.join(a.out, f"{sid}_anchors.json"), "w"), indent=1)


FEATURES = {"logo": (0.55, None), "detail": (0.27, None), "top": (0.95, None), "base": (0.06, None)}   # height on the product


def feature_tracks(sc, root, meshes, n, every=2):
    """Named points ON the product (its front faces -x of the root at rotation 90, the lens): the logo, the lower
    label (detail), the top rim or cap, the base. Found by casting rays at the settled product's own surface (in its
    local space), then projected every `every` frames: [x, y from the top, facing], facing = how squarely the surface
    there turns to the camera (callouts skip points turned away)."""
    from bpy_extras.object_utils import world_to_camera_view
    from mathutils.bvhtree import BVHTree
    sc.frame_set(n); dg = bpy.context.evaluated_depsgraph_get(); inv = root.matrix_world.inverted(); V, F = [], []
    for o in meshes:
        oe = o.evaluated_get(dg)
        try: me = oe.to_mesh()
        except RuntimeError: continue
        m = inv @ oe.matrix_world; off = len(V)
        V += [m @ v.co for v in me.vertices]; F += [[off + k for k in pl.vertices] for pl in me.polygons]; oe.to_mesh_clear()
    if len(V) < 8 or not F: return {}
    bvh = BVHTree.FromPolygons(V, F)
    x0, z0, z1 = min(v.x for v in V), min(v.z for v in V), max(v.z for v in V); y0, y1 = min(v.y for v in V), max(v.y for v in V)
    yc, hgt = (y0 + y1) / 2, z1 - z0
    logo_v = (PRODUCT or {}).get("logo_v", FEATURES["logo"][0])
    pts = {}
    for name, (zf, _) in FEATURES.items():
        z = z0 + (logo_v if name == "logo" else zf) * hgt
        loc, nrm, _i, _d = bvh.ray_cast(Vector((x0 - 1.0, yc, z)), Vector((1, 0, 0)))
        if loc is None: continue
        if nrm.x > 0: nrm = -nrm                                           # the side facing the ray
        pts[name] = (loc, nrm.normalized())
    tracks = {"frames": []}; tracks.update({k: [] for k in pts})
    frames = list(range(1, n + 1, every)) + ([n] if (n - 1) % every else [])
    for fr in frames:
        sc.frame_set(fr); M = root.matrix_world; R = M.to_3x3(); cam = sc.camera.matrix_world.translation
        tracks["frames"].append(fr)
        for k, (p_, nrm) in pts.items():
            w = M @ p_; nw = (R @ nrm).normalized(); v = world_to_camera_view(sc, sc.camera, w)
            tracks[k].append([round(v.x, 4), round(1 - v.y, 4), round(nw.dot((cam - w).normalized()), 2)])
    return tracks


EVENT = {"crown": 24, "twist": 24, "tear": 22, "snap": 24, "split": 30, "open": 22, "toppop": 22, "drops": 18, "burst": 2}   # default frame of each shot's physical event


def camera_path(cs, n):
    """Replace the shot's own camera move with the spec's: from/to positions, look/look_to targets, lens, fstop."""
    cam, tgt = bpy.data.objects["Cam"], bpy.data.objects["CamTarget"]
    cam.animation_data_clear(); tgt.animation_data_clear()
    p0 = Vector(cs.get("from", cam.location)); p1 = Vector(cs.get("to", p0)); l0 = Vector(cs.get("look", tgt.location)); l1 = Vector(cs.get("look_to", l0))
    key(cam, 1, location=p0); key(cam, n, location=p1); key(tgt, 1, location=l0); key(tgt, n, location=l1)
    if "lens" in cs: cam.data.lens = cs["lens"]
    if "fstop" in cs: cam.data.dof.aperture_fstop = cs["fstop"]
    cam.data.dof.focus_object = tgt                                        # focus follows the target on any path


def build(spec):
    """spec: {"type": shot type, "id": folder name, "frames": n, "event": frame of the physical event, "key": frame for
    the storyboard still, "camera": {...}, "cold": bool}. A plain shot name works too."""
    if isinstance(spec, str): spec = {"type": spec}
    shot = spec["type"]; sid = spec.get("id", shot); n = int(spec.get("frames") or LEN[shot]); F = int(spec.get("event") or EVENT.get(shot, 0))
    cold0 = a.cold; a.cold = spec.get("cold", a.cold)
    sc = reset(); c1, c2 = hexrgb(a.set[0]), hexrgb(a.set[1]); sweep = studio(c1, c2)
    sc.frame_start, sc.frame_end = 1, n
    if shot == "split":
        split_shot(n, F)
    elif shot == "open":
        open_shot(n, F)
    elif shot == "twist":
        twist_shot(n, F)
    elif shot == "crown":
        crown_shot(n, F)
    elif shot == "tear":
        tear_shot(n, F)
    elif shot == "snap":
        snap_shot(n, F)
    elif shot == "toppop":
        open_shot(n, F, view="top")
    elif shot == "drops":
        drops_shot(n, F)
    elif shot == "zerog":
        zerog_shot(n)
    elif shot == "hero_low":
        hero_low_shot(n)
    elif shot == "trio":
        labels = [a.label] + (a.alt + [a.label, a.label])[:2]
        cans = [can(labels[1], -0.5, "left"), can(labels[0], 0.0, "mid"), can(labels[2], 0.5, "right")]
        spots = [(-0.5, 0.55), (0.0, -0.05), (0.5, 0.55)]                   # a V: fits a vertical frame, the hero flavour in front
        for i, c in enumerate(cans):
            x, y = spots[i]
            key(c, 1, location=(x + (-3 if i == 0 else 3 if i == 2 else 0), y, 0.6 + (2.5 if i == 1 else 0)))
            key(c, 30 + i * 6, location=(x, y, 0.6))
            c.rotation_euler.z = math.radians(-30 + i * 30); key(c, n, rotation_euler=(0, 0, math.radians(-20 + i * 30)))
        cam = camera((0, -4.4, 1.1), (0, 0.2, 0.62), 40, fstop=5)
        key(cam, 1, location=(-0.4, -4.6, 1.2)); key(cam, n, location=(0.4, -4.2, 1.05))
    else:
        body = hero_obj(a.label)
        cnt = 10 if shot in ("reveal", "burst") else 6
        pieces = pieces3d(cnt, a.fruit) if a.fruit else slices(cnt, a.slice) if a.slice else []
        if shot == "reveal":
            key(body, 1, location=(0, 0, 3.2), rotation_euler=(0.5, 0.3, math.radians(-110)))
            key(body, 40, location=(0, 0, 0.6), rotation_euler=(0, 0, math.radians(105)))
            key(body, n, location=(0, 0, 0.6), rotation_euler=(0, 0, math.radians(118)))
            for i, p in enumerate(pieces):                                 # pieces fly past the lens
                y0 = p.location.y; key(p, 1, location=(p.location.x, -4.5, p.location.z)); key(p, n, location=(p.location.x * 1.2, y0 + 1.2, p.location.z))
            cam = camera((0, -3.3, 0.9), (0, 0, 0.66), 40, focus=3.3, fstop=1.8)
        elif shot == "hero":
            key(body, 1, rotation_euler=(0, 0, math.radians(50))); key(body, n, rotation_euler=(0, 0, math.radians(130)))
            key(sweep.data, 1, energy=0); key(sweep.data, 30, energy=650); key(sweep.data, n, energy=0)
            key(sweep, 1, location=(-3.0, -2.0, 1.2)); key(sweep, n, location=(3.0, -2.0, 1.2))
            cam = camera((0, -2.9, 0.8), (0, 0, 0.64), 45, focus=2.9, fstop=2.8)
            key(cam, 1, location=(0.25, -3.1, 0.85)); key(cam, n, location=(-0.1, -2.6, 0.78))
            for p in pieces: p.location.y += 1.8
        elif shot == "macro":
            key(body, 1, rotation_euler=(0, 0, math.radians(70))); key(body, n, rotation_euler=(0, 0, math.radians(110)))
            cam = camera((0.25, -1.25, 0.72), (0, -0.33, 0.66), 60, focus=0.95, fstop=2.0)   # glide across the front of the label
            key(cam, 1, location=(0.35, -1.25, 0.78)); key(cam, n, location=(-0.3, -1.2, 0.6))
            for p in pieces: p.location = (p.location.x * 0.3, -1.6, p.location.z)
        elif shot == "burst":
            for i, p in enumerate(pieces):
                ang = i / len(pieces) * 2 * math.pi
                key(p, 1, location=(0, 0, 0.7), scale=(0.2, 0.2, 0.2))
                key(p, 40, location=(math.cos(ang) * 1.3, math.sin(ang) * 0.9 - 0.3, 0.6 + math.sin(ang * 2) * 0.6), scale=(1, 1, 1))
                key(p, n, location=(math.cos(ang) * 1.5, math.sin(ang) * 1.0 - 0.3, 0.7 + math.sin(ang * 2) * 0.7), rotation_euler=(p.rotation_euler.x + 2, p.rotation_euler.y, p.rotation_euler.z + 1))
            key(body, 1, rotation_euler=(0, 0, math.radians(60))); key(body, n, rotation_euler=(0, 0, math.radians(150)))
            if a.fruit:                                                    # juice bursts out with the pieces, then slow motion
                AF.splash(a.fruit, (0, 0.35, 0.75), F, n, AF.ramp(F, fast=6, slow=0.35), n=44, seed=4, axis="z", speed=1.1, size=0.8, disc=0.35)
            cam = camera((0, -3.4, 0.95), (0, 0, 0.7), 36, focus=3.4, fstop=3.0)
            key(cam, 1, location=(0, -3.0, 0.9)); key(cam, n, location=(0, -3.7, 1.0))
    if spec.get("camera"): camera_path(spec["camera"], n)                 # an explicit path wins over the designed move
    elif spec.get("move"): LK.move(spec["move"], n, seed=sum(map(ord, sid)))
    LK.light_rig(spec.get("family"))                                      # the mood family's light
    LK.background(spec.get("bg"), lin(c1), lin(c2), n)                     # the design pass (ad_design.py)
    LK.decor(spec.get("decor"), n, seed=sum(map(ord, sid)) + 1)
    if shot in ("split", "snap", "tear", "twist", "crown", "open", "toppop") and F: LK.shake(F, n)     # the camera feels the hit
    LK.contact_shadow(n)                                                   # a soft shadow under a hovering product
    if spec.get("motion"): LK.ease(spec["motion"], whip=spec.get("move") == "whip_in")
    else: ease_all()
    a.cold = cold0
    os.makedirs(os.path.join(a.out, sid), exist_ok=True)
    anchors(sc, sid, spec, n)
    if a.still:
        import time as _t
        frs = a.frame or [int(spec.get("key") or n * 0.6)]
        for fr in frs:
            sc.frame_set(int(fr)); sc.render.filepath = os.path.join(a.out, sid + ("_still.png" if len(frs) == 1 else f"_still_{fr:03d}.png"))
            t0 = _t.time(); bpy.ops.render.render(write_still=True); print(f"RENDER_S {sid} {_t.time() - t0:.2f}", flush=True)   # render only, not the scene build
    else:
        sc.render.use_overwrite = False; sc.render.use_placeholder = True    # resume: frames already on disk are skipped
        sc.render.filepath = os.path.join(a.out, sid, ""); bpy.ops.render.render(animation=True)


if a.spec:
    import json
    SP = json.load(open(a.spec, encoding="utf-8"))
    for sp in SP["shots"]:
        if a.shots and sp["id"] not in a.shots and sp["type"] not in a.shots: continue
        build(sp)
    print("DONE", [sp["id"] for sp in SP["shots"]])
else:
    for s in a.shots: build(s)
    print("DONE", a.shots)
