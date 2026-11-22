"""Real-looking ingredients for 3D product ads (imported by blender_product_ad.py, runs inside Blender).

The rule from the user's review of v1: an object that exists in real life must be built like the real thing - a citrus
is a round, slightly lumpy body with a pored, waxy peel; cut open it shows white pith, a rind ring and juicy segments
split by membranes; juice is a liquid that sprays, stretches into strands and breaks into drops - never a flat picture.

fruit_mesh(kind, R, keep)   whole fruit, or a cut piece: keep="top"/"bottom" (halves) or ("wheel", t) (a slice)
peel_material / flesh_material   procedural peel (pores, colour drift, wax coat) and a painted cross-section
splash(...)                 juice as metaball strands on ballistic paths, keyed per frame, with an optional speed ramp
FRUITS                      presets: yuzu, orange, lemon, lime, grapefruit
"""
import math, random
import bpy, bmesh
import numpy as np
from mathutils import Vector, noise

CYCLES = False   # set by blender_product_ad.py: Cycles' real SSS/transmission whitens flesh and juice -> lighter settings


FRUITS = {   # sRGB colours; lump = peel lumpiness; squash = height/width; segs = segments in the cross-section
    "yuzu":       dict(peel=("#F5D21C", "#D9B814"), flesh="#FFD84E", pith="#FBF1CF", segs=10, lump=0.045, squash=0.86, pores=95, juice="#FFC21C"),
    "orange":     dict(peel=("#FF8C10", "#F06A05"), flesh="#FF9A1A", pith="#FFF0D6", segs=11, lump=0.012, squash=0.96, pores=120, juice="#FF8A10"),
    "lemon":      dict(peel=("#FBE33A", "#EFCB1C"), flesh="#FBEA7A", pith="#FFF9E2", segs=9,  lump=0.018, squash=1.22, pores=110, juice="#F7E05A"),
    "lime":       dict(peel=("#6DA82A", "#4E8A1C"), flesh="#C7DE6A", pith="#F2F6D8", segs=10, lump=0.010, squash=1.02, pores=130, juice="#B9D85A"),
    "grapefruit": dict(peel=("#FFB347", "#F59A3A"), flesh="#F25A4A", pith="#FFF1E4", segs=12, lump=0.010, squash=0.94, pores=110, juice="#F4604E"),
}


def lin(c):
    if isinstance(c, str): c = c.lstrip("#"); c = tuple(int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return tuple(((x + 0.055) / 1.055) ** 2.4 if x > 0.04045 else x / 12.92 for x in c)


# ---------- shape ----------
def fruit_mesh(kind="yuzu", R=1.0, keep=None, seed=7, name=None):
    """A citrus body: sphere pushed out by smooth noise (lumps), squashed or stretched along the stem (Z) axis, a stem
    dimple on top. keep cuts it across the equator: "top"/"bottom" halves, or ("wheel", t) a slice t thick (in R)."""
    f = FRUITS[kind]; bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=160, v_segments=110, radius=1.0)
    off = Vector((seed * 3.1, seed * 1.7, seed * 2.3))
    for v in bm.verts:
        n = v.co.normalized()
        lump = noise.noise(n * 1.8 + off) * f["lump"] + noise.noise(n * 6.0 + off) * f["lump"] * 0.25
        p = n * (1.0 + lump)
        p.z *= f["squash"]
        if kind == "lemon": p.z *= 1 + 0.16 * max(0.0, abs(n.z) - 0.9) / 0.1            # the pointed ends
        p.z -= 0.06 * math.exp(-(1 - n.z) * 35) if n.z > 0 else 0                        # stem dimple
        v.co = p * R
    cap = []
    if keep:
        cuts = [(0.0, keep == "top")] if keep in ("top", "bottom") else [(-keep[1] * R / 2, True), (keep[1] * R / 2, False)]
        for z0, keep_above in cuts:
            geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
            bmesh.ops.bisect_plane(bm, geom=geom, dist=1e-6, plane_co=(0, 0, z0), plane_no=(0, 0, 1),
                                   clear_inner=keep_above, clear_outer=not keep_above)
            edges = [e for e in bm.edges if e.is_boundary]
            for e in edges: e.smooth = False                                             # a crisp cut edge
            new = bmesh.ops.holes_fill(bm, edges=edges, sides=0)["faces"]
            cap += bmesh.ops.poke(bm, faces=new)["faces"]
    me = bpy.data.meshes.new(name or kind); bm.to_mesh(me); bm.free()
    cap_ids = set()
    for p in me.polygons:
        p.use_smooth = True
        if abs(p.normal.z) > 0.999 and all(abs(me.vertices[i].co.z - me.vertices[p.vertices[0]].co.z) < 1e-4 for i in p.vertices):
            p.use_smooth = False; p.material_index = 1; cap_ids.add(p.index)
    uv = me.uv_layers.new(name="UV")
    rr = max((Vector((me.vertices[i].co.x, me.vertices[i].co.y)).length for pi in cap_ids for i in me.polygons[pi].vertices), default=R)
    for p in me.polygons:
        for li in p.loop_indices:
            c = me.vertices[me.loops[li].vertex_index].co
            uv.data[li].uv = (c.x / rr * 0.5 + 0.5, c.y / rr * 0.5 + 0.5) if p.index in cap_ids else (math.atan2(c.y, c.x) / 6.283 % 1, c.z / R * 0.5 + 0.5)
    return me


def stem(kind, R, parent, z_top):
    """Short woody stem and a star calyx on the top pole."""
    m = bpy.data.materials.get("stem") or _principled("stem", lin("#5E6B2A"), 0.55)
    bpy.ops.mesh.primitive_cone_add(vertices=6, radius1=0.09 * R, radius2=0.02 * R, depth=0.035 * R, location=(0, 0, z_top - 0.01 * R))
    cx = bpy.context.object; cx.data.materials.append(m); cx.parent = parent
    bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=0.02 * R, depth=0.08 * R, location=(0, 0, z_top + 0.03 * R))
    st = bpy.context.object; st.data.materials.append(m); st.parent = parent; st.rotation_euler.x = 0.25
    return cx, st


# ---------- materials ----------
def _principled(name, color, rough=0.4):
    m = bpy.data.materials.new(name); m.use_nodes = True; b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1); b.inputs["Roughness"].default_value = rough
    return m


def _set(node, name, val):
    if name in node.inputs: node.inputs[name].default_value = val


def peel_material(kind):
    """Pores (Voronoi dimples), slow colour drift (noise), waxy coat, a little light through the skin."""
    f = FRUITS[kind]; m = bpy.data.materials.get("peel_" + kind)
    if m: return m
    m = _principled("peel_" + kind, lin(f["peel"][0]), 0.35); nt = m.node_tree; N = nt.nodes; L = nt.links; b = N["Principled BSDF"]
    tc = N.new("ShaderNodeTexCoord")
    vor = N.new("ShaderNodeTexVoronoi"); vor.inputs["Scale"].default_value = f["pores"]; L.new(tc.outputs["Object"], vor.inputs["Vector"])
    fine = N.new("ShaderNodeTexNoise"); fine.inputs["Scale"].default_value = 40; L.new(tc.outputs["Object"], fine.inputs["Vector"])
    add = N.new("ShaderNodeMath"); add.operation = "MULTIPLY_ADD"; add.inputs[1].default_value = 0.25
    L.new(fine.outputs["Fac"], add.inputs[0]); L.new(vor.outputs["Distance"], add.inputs[2])
    bump = N.new("ShaderNodeBump"); bump.inputs["Strength"].default_value = 0.45; _set(bump, "Distance", 0.006)
    L.new(add.outputs[0], bump.inputs["Height"]); L.new(bump.outputs["Normal"], b.inputs["Normal"])
    col = N.new("ShaderNodeTexNoise"); col.inputs["Scale"].default_value = 3.5; col.inputs["Detail"].default_value = 6; L.new(tc.outputs["Object"], col.inputs["Vector"])
    ramp = N.new("ShaderNodeValToRGB"); ramp.color_ramp.elements[0].color = (*lin(f["peel"][1]), 1); ramp.color_ramp.elements[1].color = (*lin(f["peel"][0]), 1)
    ramp.color_ramp.elements[0].position = 0.35; ramp.color_ramp.elements[1].position = 0.65
    L.new(col.outputs["Fac"], ramp.inputs["Fac"]); L.new(ramp.outputs["Color"], b.inputs["Base Color"])
    rmap = N.new("ShaderNodeMapRange"); rmap.inputs["To Min"].default_value = 0.28; rmap.inputs["To Max"].default_value = 0.48
    L.new(fine.outputs["Fac"], rmap.inputs["Value"]); L.new(rmap.outputs["Result"], b.inputs["Roughness"])
    _set(b, "Coat Weight", 0.3); _set(b, "Coat Roughness", 0.18)
    _set(b, "Subsurface Weight", 0.12); _set(b, "Subsurface Scale", 0.03)
    return m


def _vnoise(x, y, seed=0.0):
    """Smooth value noise on float arrays (numpy only, Blender has no PIL/scipy)."""
    xi, yi = np.floor(x), np.floor(y); fx, fy = x - xi, y - yi
    h = lambda i, j: np.modf(np.abs(np.sin(i * 127.1 + j * 311.7 + seed * 74.7)) * 43758.5453)[0]
    sx, sy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
    a, b, c, d = h(xi, yi), h(xi + 1, yi), h(xi, yi + 1), h(xi + 1, yi + 1)
    return a + (b - a) * sx + (c - a) * sy + (a - b - c + d) * sx * sy


def _fbm(x, y, oct=4, seed=0.0):
    s, amp, tot = 0.0, 1.0, 0.0
    for o in range(oct): s = s + amp * _vnoise(x * 2 ** o, y * 2 ** o, seed + o); tot += amp; amp *= 0.5
    return s / tot


def _sstep(e0, e1, x): t = np.clip((x - e0) / (e1 - e0), 0, 1); return t * t * (3 - 2 * t)


def flesh_maps(kind, S=1024, seed=1.0):
    """Paint the cut face: rind ring, white pith, segments with radially stretched juice vesicles, white membranes and a
    pithy core. Returns colour, roughness and height images (UV = cut plane, radius 1 = the edge)."""
    f = FRUITS[kind]; n = f["segs"]
    v, u = np.mgrid[-1:1:S * 1j, -1:1:S * 1j]
    r = np.hypot(u, v); th = np.arctan2(v, u)
    thw = th + 0.05 * (_fbm(r * 3, th * 1.5, 3, seed) - 0.5)                            # segments are never perfectly even
    sp = thw * n / (2 * np.pi); d = np.abs(sp - np.round(sp)) * (2 * np.pi / n) * r      # arc distance to the nearest membrane
    memb = 1 - _sstep(0.002 + 0.003 * r, 0.006 + 0.005 * r, d)
    seg = np.round(sp); arc = (sp - seg) * (2 * np.pi / n) * r                          # position across the segment
    ves = _fbm(r * 9 + seg * 7.3, arc * 60, 3, seed + 3); ridge = 1 - 2 * np.abs(ves - 0.5)   # vesicles: long along the radius
    spark = _sstep(0.8, 0.95, _vnoise(r * 22 + seg * 3.1, arc * 120, seed + 9))
    sd = np.zeros_like(r)                                                                # seeds near the core in some segments
    for k in range(n):
        if (k * 7 + int(seed)) % 3: continue
        ac = (k + 0.5) * 2 * np.pi / n; rc = 0.2 + 0.04 * ((k * 5) % 3)
        du, dv = u - rc * np.cos(ac), v - rc * np.sin(ac)
        along = du * np.cos(ac) + dv * np.sin(ac); across = -du * np.sin(ac) + dv * np.cos(ac)
        sd = np.maximum(sd, 1 - _sstep(0.8, 1.0, np.hypot(along / 0.075, across / 0.035)))
    edge = 0.955 + 0.012 * (_fbm(th * 3, 0, 2, seed + 5) - 0.5); pith_in = 0.86 + 0.02 * (_fbm(th * 4, 1, 2, seed + 6) - 0.5)
    core = 0.085 + 0.03 * np.cos(thw * n) * 0.5
    fl, pi, pe = np.array(lin(f["flesh"])), np.array(lin(f["pith"])), np.array(lin(f["peel"][0]))
    pulp = fl[None, None] * (0.62 + 0.5 * ridge[..., None]) * (0.85 + 0.2 * _sstep(0.1, 0.8, r)[..., None]) + 0.25 * spark[..., None]
    col = pulp
    col = col * (1 - memb[..., None]) + pi * 0.95 * memb[..., None]
    w_pith = _sstep(pith_in - 0.015, pith_in + 0.01, r); col = col * (1 - w_pith[..., None]) + pi * (0.9 + 0.1 * _vnoise(u * 60, v * 60, seed)[..., None]) * w_pith[..., None]
    w_rind = _sstep(edge - 0.008, edge + 0.004, r); col = col * (1 - w_rind[..., None]) + pe * w_rind[..., None]
    col = col * (1 - sd[..., None]) + np.array(lin("#F3E6B8")) * sd[..., None]
    w_core = 1 - _sstep(core - 0.02, core + 0.01, r); col = col * (1 - w_core[..., None]) + pi * w_core[..., None]
    rough = 0.05 + 0.25 * memb + 0.5 * w_pith + 0.1 * w_core + 0.2 * sd
    height = 0.35 + 0.35 * ridge * (1 - memb) + 0.25 * memb + 0.45 * w_pith + 0.2 * w_core - 0.1 * spark + 0.25 * sd
    out = []
    for nm, arr, data in (("col", np.clip(col, 0, 1), False), ("rough", rough, True), ("height", height, True)):
        rgba = np.ones((S, S, 4), np.float32)
        if arr.ndim == 2: rgba[..., 0] = rgba[..., 1] = rgba[..., 2] = arr
        else: rgba[..., :3] = arr
        im = bpy.data.images.new(f"{kind}_flesh_{nm}", S, S, alpha=False, float_buffer=True)
        im.colorspace_settings.name = "Non-Color" if data else "Linear Rec.709"     # before the pixels: changing it regenerates (blanks) the image
        im.pixels.foreach_set(rgba.ravel()); im.pack(); out.append(im)
    return out


def flesh_material(kind):
    m = bpy.data.materials.get("flesh_" + kind)
    if m: return m
    col, rough, height = flesh_maps(kind)
    m = _principled("flesh_" + kind, (1, 1, 1), 0.1); nt = m.node_tree; N = nt.nodes; L = nt.links; b = N["Principled BSDF"]
    tc = N.new("ShaderNodeTexCoord")
    for im, inp in ((col, "Base Color"), (rough, "Roughness")):
        tx = N.new("ShaderNodeTexImage"); tx.image = im; tx.extension = "EXTEND"; L.new(tc.outputs["UV"], tx.inputs["Vector"]); L.new(tx.outputs["Color"], b.inputs[inp])
    th = N.new("ShaderNodeTexImage"); th.image = height; th.extension = "EXTEND"; L.new(tc.outputs["UV"], th.inputs["Vector"])
    bump = N.new("ShaderNodeBump"); bump.inputs["Strength"].default_value = 0.7; _set(bump, "Distance", 0.01)
    L.new(th.outputs["Color"], bump.inputs["Height"]); L.new(bump.outputs["Normal"], b.inputs["Normal"])
    _set(b, "Subsurface Weight", 0.1 if CYCLES else 0.35); _set(b, "Subsurface Scale", 0.05); _set(b, "Coat Weight", 0.3 if CYCLES else 0.6); _set(b, "Coat Roughness", 0.04)
    _set(b, "Specular IOR Level", 0.65)
    return m


def juice_material(kind):
    f = FRUITS[kind]; m = bpy.data.materials.get("juice_" + kind)
    if m: return m
    c = lin(f["juice"]); m = _principled("juice_" + kind, c, 0.02); b = m.node_tree.nodes["Principled BSDF"]
    _set(b, "Transmission Weight", 0.35 if CYCLES else 0.75); _set(b, "IOR", 1.34); _set(b, "Subsurface Weight", 0.5 if CYCLES else 0.25)
    _set(b, "Emission Color", (*c, 1)); _set(b, "Emission Strength", 0.25)                 # backlit juice glows
    for attr, val in (("use_raytrace_refraction", True), ("surface_render_method", "DITHERED")):
        try: setattr(m, attr, val)
        except Exception: pass
    return m


def fruit(kind="yuzu", R=0.4, keep=None, loc=(0, 0, 0), name=None, seed=7, with_stem=True):
    """Place a fruit object (whole, half, or wheel) with peel + flesh materials."""
    me = fruit_mesh(kind, R, keep, seed, name)
    ob = bpy.data.objects.new(name or kind, me); bpy.context.scene.collection.objects.link(ob); ob.location = loc
    me.materials.append(peel_material(kind)); me.materials.append(flesh_material(kind))
    if with_stem and keep in (None, "top"):
        stem(kind, R, ob, max(v.co.z for v in me.vertices))
    return ob


# ---------- liquid ----------
def splash(kind, center, f0, frames, warp, n=48, seed=5, axis="x", speed=1.0, g=7.0, size=1.0, life=1.4, disc=0.6):
    """Juice spraying from a cut face. Each strand = a lead drop and 6 trailing ones on the same ballistic path a little
    behind in time, so neighbours merge (metaball) into stretched strands that thin and break into drops.
    warp(frame) -> simulated seconds since f0 (lets the caller slow time down: speed ramp). axis: the cut-face normal
    ("x" = sprays left and right). Drops vanish under the floor or after life seconds."""
    rnd = random.Random(seed); mb = bpy.data.metaballs.new("juice"); mb.resolution = 0.03; mb.render_resolution = 0.012 * min(1.0, size * 1.5); mb.threshold = 0.6   # tiny drops need a finer grid
    ob = bpy.data.objects.new("juice", mb); bpy.context.scene.collection.objects.link(ob); mb.materials.append(juice_material(kind))
    strands = []
    for k in range(n):
        a = rnd.uniform(0, 2 * math.pi); rr = disc * math.sqrt(rnd.random())
        side = rnd.choice((-1, 1)); out = rnd.uniform(0.6, 2.6) * speed
        p0 = Vector(center) + (Vector((0, rr * math.cos(a), rr * math.sin(a))) if axis == "x" else Vector((rr * math.cos(a), rr * math.sin(a), 0)))
        radial = Vector((0, math.cos(a), math.sin(a))) if axis == "x" else Vector((math.cos(a), math.sin(a), 0))
        v0 = (Vector((side * out, 0, 0)) if axis == "x" else Vector((0, 0, out))) + radial * rnd.uniform(0.6, 2.2) * speed
        v0 += Vector((0, rnd.uniform(-1.6, 0.4), rnd.uniform(0.6, 2.4))) * speed                # up and toward the lens
        rad = rnd.uniform(0.035, 0.075) * size * (0.6 if rnd.random() < 0.4 else 1.0)
        delay = rnd.uniform(0, 0.05)
        strands.append((p0, v0, rad, delay))
    els = []
    for p0, v0, rad, delay in strands:
        for j in range(7):                                                             # close together: a strand, not beads
            e = mb.elements.new(); e.type = "BALL"; e.radius = 0.0; els.append((e, p0, v0, rad * (1 - 0.11 * j), delay + j * 0.006))
    for fr in range(1, frames + 1):
        s = warp(fr)
        for i, (e, p0, v0, rad, lag) in enumerate(els):
            t = s - lag
            if t <= 0 or t > life: e.co = p0; e.radius = 0.0
            else:
                p = p0 + v0 * t + Vector((0, 0, -0.5 * g * t * t))
                e.co = p; e.radius = 0.0 if p.z < 0.02 else rad * (1 - 0.35 * t / life)
            mb.keyframe_insert(f"elements[{i}].co", frame=fr); mb.keyframe_insert(f"elements[{i}].radius", frame=fr)
    return ob


def ramp(f0, fast=6, slow=0.28, fps=30, back=None):
    """Speed ramp: real speed for `fast` frames after f0, then slow motion (slow x); optional return to 1x at `back`."""
    def w(fr):
        if fr <= f0: return 0.0
        d = fr - f0; s = min(d, fast) / fps
        if d > fast:
            e = d - fast
            if back and fr > back: s += (back - f0 - fast) * slow / fps + (fr - back) / fps
            else: s += e * slow / fps
        return s
    return w
