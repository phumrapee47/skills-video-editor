"""Product shapes beyond the can for 3D ads (imported by blender_product_ad.py, runs inside Blender).

Every product is built at its real proportions and scaled to the can's envelope (1.157 units tall, origin at the
middle, bottom at local z -0.58) so every shot's camera works for every product. A product is a dict (product.json,
written by product_from_photo.py or by hand):
  {"shape": "bottle"|"lathe"|"box"|"pouch"|"bar", "height_mm": 212, "profile": [[r_mm, z_mm], ...] (lathe/bottle),
   "cap_from_mm": 192 (bottle: the cap is its own object above this), "texture": "body.png" (lathe: the whole visible
   surface unwrapped, v = height), "front": 0.5, "size_mm": [w, h, d] (box/pouch/bar), "front_tex", "back_tex",
   "material": "plastic"|"glass"|"paper"|"foil"|"metal", "liquid": "#hex" (clear bottle), "fill": 0.85,
   "coating": "#hex", "filling": "#hex" (bar)}
Builders return the root object; moving parts hang on named pivots: <name>_cappivot (bottle cap: rotate Z, rise),
<name>_strip (pouch tear strip), <name>_halfL / <name>_halfR (bar halves, hinge at the bottom).
"""
import math, random
import bpy, bmesh
import numpy as np
from mathutils import Vector

import ad_can as AC

CAN_H = 1.157


def _mat(name, color=(1, 1, 1), metal=0.0, rough=0.4, image=None, **kw):
    m = AC.principled(name, color, metal, rough, **kw)
    if image:
        nt = m.node_tree; tx = nt.nodes.new("ShaderNodeTexImage"); tx.image = bpy.data.images.load(image) if isinstance(image, str) else image
        tx.extension = "EXTEND"; nt.links.new(tx.outputs["Color"], nt.nodes["Principled BSDF"].inputs["Base Color"])
    return m


def hexlin(h):
    h = h.lstrip("#"); c = tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return tuple(((x + 0.055) / 1.055) ** 2.4 if x > 0.04045 else x / 12.92 for x in c)


def _link(name, me, parent=None):
    o = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(o)
    if parent: o.parent = parent
    return o


# ---------------------------------------------------------------- lathe (can, bottle, jar, anything round)
def lathe_mesh(name, profile, k, segs=128, front=0.5, v_range=None, mat_split=None, zmid=None):
    """profile: [(r_mm, z_mm)] from the bottom centre up to the top centre; k: scene units per mm; z is shifted so zmid
    (default: the profile's middle) sits at local 0 - pass the whole product's middle so its parts line up.
    UV: u around (the front of the texture faces local -x), v = height in mm over v_range."""
    zs = [z for _, z in profile]; H = max(zs) - min(zs); zmid = (min(zs) + H / 2) if zmid is None else zmid
    v0, v1 = v_range or (min(zs), max(zs))
    bm = bmesh.new()
    vs = [bm.verts.new((max(r, 0) * k, 0, (z - zmid) * k)) for r, z in profile]
    es = [bm.edges.new((vs[i], vs[i + 1])) for i in range(len(vs) - 1)]
    bmesh.ops.spin(bm, geom=vs + es, cent=(0, 0, 0), axis=(0, 0, 1), angle=2 * math.pi, steps=segs, use_merge=True)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-7)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    uv = me.uv_layers.new(name="UV")
    for p in me.polygons:
        p.use_smooth = True
        if mat_split: p.material_index = mat_split(p.center.z / k + zmid, Vector((p.center.x, p.center.y)).length / k)
        for li in p.loop_indices:
            v = me.vertices[me.loops[li].vertex_index].co
            uv.data[li].uv = ((math.atan2(v.y, v.x) / (2 * math.pi) - 0.5 + front) % 1.0, (v.z / k + zmid - v0) / (v1 - v0))
        us = [uv.data[li].uv[0] for li in p.loop_indices]
        if max(us) - min(us) > 0.5:
            for li in p.loop_indices:
                if uv.data[li].uv[0] < 0.5: uv.data[li].uv[0] += 1.0
    try: me.set_sharp_from_angle(angle=math.radians(50))
    except Exception: pass
    return me, zmid


BOTTLE_500 = [(0, 2), (12, 1.6), (22, 0.8), (28, 0.6), (31, 2.2), (32.6, 6), (33, 12), (33, 70), (33, 128), (32.4, 140), (30.5, 150),
              (27.5, 160), (23.5, 168), (19.5, 175), (16.0, 181), (13.8, 185), (13.6, 187), (15.4, 187.6), (15.4, 189.0), (13.4, 189.6),
              (13.2, 193.0), (14.9, 193.0), (15.3, 193.8), (15.3, 210.6), (14.6, 211.6), (0, 211.8)]


def bottle(spec, name, label=None, front=0.5):
    """PET/glass bottle or any round product. From a photo: the whole body textured as photographed (opaque print).
    Preset: clear plastic, the liquid inside to a fill level, a printed label band, a knurled cap. The cap is its own
    object on <name>_cappivot (its bottom), so it can twist off."""
    prof = spec.get("profile") or BOTTLE_500; capz = spec.get("cap_from_mm", None if spec.get("profile") else 193.0)
    zlo, zhi = min(z for _, z in prof), max(z for _, z in prof); H = zhi - zlo; k = CAN_H / H; zmid = zlo + H / 2
    root = _link(name, None)
    body_p = [p for p in prof if capz is None or p[1] <= capz]; cap_p = [p for p in prof if capz is not None and p[1] >= capz]
    if body_p[-1][0] > 0: body_p = body_p + [(0, body_p[-1][1])]
    if cap_p and cap_p[0][0] > 0: cap_p = [(0, cap_p[0][1])] + cap_p
    tex = spec.get("texture"); fr = spec.get("front", front)
    if tex:                                                               # photo: one texture over the full height
        mt = _mat(name + "_print", image=tex, rough=0.22, **{"Coat Weight": 0.6, "Coat Roughness": 0.05})
        me, _ = lathe_mesh(name + "_body", body_p, k, front=fr, v_range=(zlo, zhi), zmid=zmid)
        _link(name + "_body", me, root); me.materials.append(mt)
    else:
        clear = AC.clear_liquid(name + "_pet", (0.96, 0.98, 1.0), 0.03, 1.45, 0.75)
        me, _ = lathe_mesh(name + "_body", body_p, k, front=fr, zmid=zmid); _link(name + "_body", me, root); me.materials.append(clear)
        fill = spec.get("fill", 0.86); ztop = zlo + fill * (capz - zlo)
        liq = [(r * 0.965, z) for r, z in body_p if z <= ztop] + [(0, ztop)]
        liq_m = AC.principled(name + "_liquid", hexlin(spec.get("liquid", "#9BC53D")), 0.0, 0.05,
                              **{"Transmission Weight": 0.6 if AC.CYCLES else 0.0, "Subsurface Weight": 0.3, "Coat Weight": 0.5})
        lm, _ = lathe_mesh(name + "_liquid", liq, k, zmid=zmid); _link(name + "_liquid", lm, root).data.materials.append(liq_m)
        if label:                                                         # the printed label band round the straight wall
            lz0, lz1 = spec.get("label_mm", (45, 125))
            bm_, _ = lathe_mesh(name + "_label", [(0, lz0), (33.3, lz0), (33.3, lz1), (0, lz1)], k, front=fr, v_range=(lz0, lz1), zmid=zmid)
            _link(name + "_label", bm_, root); bm_.materials.append(_mat(name + "_label", image=label, rough=0.3, **{"Coat Weight": 0.4}))
    if cap_p:
        piv = bpy.data.objects.new(name + "_cappivot", None); bpy.context.scene.collection.objects.link(piv); piv.parent = root
        piv.location = (0, 0, (cap_p[0][1] - zmid) * k)
        cm, _ = lathe_mesh(name + "_cap", cap_p, k, front=fr, v_range=(zlo, zhi), zmid=cap_p[0][1])    # cap bottom on the pivot
        _link(name + "_cap", cm, piv)
        if tex: cm.materials.append(bpy.data.materials[name + "_print"])
        else:
            capm = AC.principled(name + "_capm", hexlin(spec.get("cap", "#2E7D32")), 0.0, 0.35)
            nt = capm.node_tree; N = nt.nodes; L = nt.links; tc = N.new("ShaderNodeTexCoord"); sp = N.new("ShaderNodeSeparateXYZ")
            ang = N.new("ShaderNodeMath"); ang.operation = "ARCTAN2"; ri = N.new("ShaderNodeMath"); ri.operation = "SINE"
            mul = N.new("ShaderNodeMath"); mul.operation = "MULTIPLY"; mul.inputs[1].default_value = 60
            bump = N.new("ShaderNodeBump"); bump.inputs["Strength"].default_value = 0.6
            L.new(tc.outputs["Object"], sp.inputs[0]); L.new(sp.outputs[1], ang.inputs[0]); L.new(sp.outputs[0], ang.inputs[1])
            L.new(ang.outputs[0], mul.inputs[0]); L.new(mul.outputs[0], ri.inputs[0]); L.new(ri.outputs[0], bump.inputs["Height"])
            L.new(bump.outputs["Normal"], N["Principled BSDF"].inputs["Normal"]); cm.materials.append(capm)       # knurled grip
    return root


# ---------------------------------------------------------------- box
def box(spec, name):
    """A carton: bevelled box at the photo's proportions, the front print on the front face (local -x), the back print
    (or the front again) on the back, sides in the sampled side colour."""
    w, h, d = spec.get("size_mm", [70, 180, 40]); k = CAN_H / h
    bpy.ops.mesh.primitive_cube_add(size=1); o = bpy.context.object; o.name = name
    o.scale = (d * k, w * k, h * k); bpy.ops.object.transform_apply(scale=True)
    me = o.data; uv = me.uv_layers.active or me.uv_layers.new()
    side = AC.principled(name + "_side", hexlin(spec.get("side", "#F2F2F2")), 0.0, 0.45)
    fm = _mat(name + "_front", image=spec.get("front_tex"), rough=0.35, **{"Coat Weight": 0.3})
    bm_ = _mat(name + "_back", image=spec.get("back_tex") or spec.get("front_tex"), rough=0.35)
    me.materials.append(side); me.materials.append(fm); me.materials.append(bm_)
    for p in me.polygons:
        n = p.normal
        if n.x < -0.9 or n.x > 0.9:
            p.material_index = 1 if n.x < 0 else 2
            for li in p.loop_indices:
                v = me.vertices[me.loops[li].vertex_index].co
                uu = (0.5 - v.y / (w * k)) if n.x < 0 else (v.y / (w * k) + 0.5)                   # reads right way round from outside
                uv.data[li].uv = (uu, v.z / (h * k) + 0.5)
    b = o.modifiers.new("bevel", "BEVEL"); b.width = 0.012; b.segments = 3
    return o


# ---------------------------------------------------------------- pouch
def _pouch_mesh(name, w, h, T, crimp, y_from, y_to, jag_top=None, jag_bot=None, nx=48, ny=72):
    """Front (local -x) and back sheets of a pillow pouch between heights y_from..y_to (0 = bottom, 1 = top). The
    thickness swells to T in the middle; top and bottom seals are flat with crimp ridges. jag_top/jag_bot(u) move the
    top/bottom row onto a torn line."""
    verts, faces, uvs, mats = [], [], [], []
    for side, sign in ((0, -1), (1, 1)):
        base = len(verts)
        for j in range(ny + 1):
            for i in range(nx + 1):
                u = i / nx; t = y_from + (y_to - y_from) * j / ny
                if j == ny and jag_top: t = jag_top(u)
                if j == 0 and jag_bot: t = jag_bot(u)
                inner = (t - crimp) / (1 - 2 * crimp)
                puff = T * (1 - abs(2 * u - 1) ** 3.0) ** 0.6 * (1 - abs(2 * inner - 1) ** 2.4) ** 0.5 if 0 <= inner <= 1 else 0.0008 * (math.sin(u * 140) > 0)
                verts.append((sign * puff, (u - 0.5) * w, (t - 0.5) * h)); uvs.append((u if side else (1 - u), t))   # reads right way round from outside
        for j in range(ny):
            for i in range(nx):
                a = base + j * (nx + 1) + i; q = [a, a + 1, a + nx + 2, a + nx + 1]
                faces.append(q if sign > 0 else q[::-1]); mats.append(side)
    me = bpy.data.meshes.new(name); me.from_pydata(verts, [], faces); me.update()
    uv = me.uv_layers.new(name="UV")
    for p, m_ in zip(me.polygons, mats):
        p.material_index = m_; p.use_smooth = True
        for li in p.loop_indices: uv.data[li].uv = uvs[me.loops[li].vertex_index]
    return me


def pouch(spec, name, tear_at=None):
    """Pillow pouch (chips, snacks, coffee): front and back sheets swelling to the middle, crimped seals. tear_at
    (0-1 of the height): split there along a jagged tear line into the bag and a separate top strip <name>_strip."""
    w, h, d = spec.get("size_mm", [180, 250, 60]); k = CAN_H / h; W, Hh, T = w * k, h * k, d * k / 2
    fm = _mat(name + "_front", image=spec.get("front_tex"), rough=0.28, **{"Coat Weight": 0.5, "Coat Roughness": 0.1,
                                                                          "Metallic": 0.15 if spec.get("material", "foil") == "foil" else 0.0})
    bmat = _mat(name + "_back", image=spec.get("back_tex") or spec.get("front_tex"), rough=0.3, **{"Coat Weight": 0.5})
    crimp = 0.06
    if tear_at is None:
        me = _pouch_mesh(name, W, Hh, T, crimp, 0, 1); o = _link(name, me); me.materials.append(fm); me.materials.append(bmat); return o
    rnd = random.Random(3); pts = [rnd.uniform(-0.012, 0.012) for _ in range(40)]
    jag = lambda u: tear_at + pts[min(39, int(u * 39))] + 0.004 * math.sin(u * 90)
    me = _pouch_mesh(name, W, Hh, T, crimp, 0, tear_at, jag_top=jag); o = _link(name, me); me.materials.append(fm); me.materials.append(bmat)
    piv = bpy.data.objects.new(name + "_strippivot", None); bpy.context.scene.collection.objects.link(piv); piv.parent = o
    piv.location = (0, -W / 2, (tear_at - 0.5) * Hh)                       # tears from the notch on one side
    sm = _pouch_mesh(name + "_strip", W, Hh, T, crimp, tear_at, 1, jag_bot=jag)
    s = _link(name + "_strip", sm, piv); s.location = (0, W / 2, -(tear_at - 0.5) * Hh); sm.materials.append(fm); sm.materials.append(bmat)
    for oo in (o, s):
        sol = oo.modifiers.new("thick", "SOLIDIFY"); sol.thickness = 0.002; sol.offset = 0
    return o


# ---------------------------------------------------------------- filled bar
def bar_section(coating, filling, S=512, layers=None):
    """The broken face of a filled bar: chocolate shell, then layers (caramel, wafer/biscuit, nougat), painted."""
    v, u = np.mgrid[0:1:S * 1j, 0:1:S * 1j]
    rng = np.random.default_rng(2); noise = rng.random((S, S)) * 0.06
    shell = 0.09; col = np.zeros((S, S, 3))
    c = np.array(hexlin(coating)); f = np.array(hexlin(filling)); bis = np.array(hexlin("#C8924A"))
    inside = (u > shell) & (u < 1 - shell) & (v > shell * 1.4) & (v < 1 - shell)
    col[:] = c * (0.85 + noise[..., None])
    lay = layers or [(0.0, 0.42, bis), (0.42, 1.0, f)]
    yy = (v - shell * 1.4) / (1 - shell * 2.4)
    for a, b_, cc in lay:
        m = inside & (yy >= a) & (yy < b_)
        tex = 0.8 + 0.4 * rng.random((S, S)) if cc is bis else 0.95 + 0.1 * np.sin(u * 40 + v * 7)
        col[m] = (np.array(cc) * tex[..., None])[m]
    rgba = np.ones((S, S, 4), np.float32); rgba[..., :3] = np.clip(col, 0, 1)
    im = bpy.data.images.new("bar_section", S, S, float_buffer=True); im.colorspace_settings.name = "Linear Rec.709"
    im.pixels.foreach_set(rgba.ravel()); im.pack(); return im


def bar(spec, name):
    """A filled chocolate bar as two halves meeting at local x=0 (the snap), each with a painted broken face; ridges
    on top. Pivots <name>_halfL/_halfR hinge on the bottom edge of the break."""
    L_, W_, H_ = spec.get("size_mm", [120, 32, 18]); k = 0.95 / L_ * 1.0          # a bar lies across the frame
    coat = AC.principled(name + "_choc", hexlin(spec.get("coating", "#4A2615")), 0.0, 0.38, **{"Coat Weight": 0.1, "Specular IOR Level": 0.45})   # satin, not a mirror of the floor
    nt = coat.node_tree; nz = nt.nodes.new("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 60
    bmp = nt.nodes.new("ShaderNodeBump"); bmp.inputs["Strength"].default_value = 0.08
    nt.links.new(nz.outputs["Fac"], bmp.inputs["Height"]); nt.links.new(bmp.outputs["Normal"], nt.nodes["Principled BSDF"].inputs["Normal"])
    sec = _mat(name + "_section", image=bar_section(spec.get("coating", "#4A2615"), spec.get("filling", "#C8741E")), rough=0.45)
    root = _link(name, None); halves = []
    for side in (-1, 1):
        piv = bpy.data.objects.new(name + ("_halfL" if side < 0 else "_halfR"), None); bpy.context.scene.collection.objects.link(piv)
        piv.parent = root; piv.location = (0, 0, -H_ * k / 2)
        bm = bmesh.new(); hl = L_ * k / 2
        bmesh.ops.create_cube(bm, size=1.0)
        for vv in bm.verts:
            vv.co.x = (vv.co.x + 0.5) * hl * side; vv.co.y *= W_ * k; vv.co.z = (vv.co.z + 0.5) * H_ * k
        bmesh.ops.subdivide_edges(bm, edges=[e for e in bm.edges if abs(e.verts[0].co.x - e.verts[1].co.x) > 1e-6], cuts=24, use_grid_fill=True)
        for vv in bm.verts:                                                    # ridges across the top (the bar's segments)
            if vv.co.z > H_ * k * 0.99 and abs(vv.co.x) > 0.004:
                vv.co.z += 0.004 * (0.5 + 0.5 * math.cos(abs(vv.co.x) / (hl / 4) * 2 * math.pi))
        me = bpy.data.meshes.new(f"{name}_half{side}"); bm.to_mesh(me); bm.free()
        uv = me.uv_layers.new(name="UV"); me.materials.append(coat); me.materials.append(sec)
        for p in me.polygons:
            br = abs(p.center.x) < 1e-5 and abs(p.normal.x) > 0.9
            p.material_index = 1 if br else 0
            for li in p.loop_indices:
                co = me.vertices[me.loops[li].vertex_index].co
                uv.data[li].uv = (co.y / (W_ * k) + 0.5, co.z / (H_ * k)) if br else (co.x, co.y)
        h = _link(f"{name}_half{'L' if side < 0 else 'R'}_mesh", me, piv)
        bv = h.modifiers.new("bevel", "BEVEL"); bv.width = 0.006; bv.segments = 3; bv.limit_method = "ANGLE"
        halves.append(piv)
    root["k"] = k; root["size"] = [L_ * k, W_ * k, H_ * k]
    return root


def build(spec, name, label=None, front=0.5, **kw):
    s = spec.get("shape", "can")
    if s in ("bottle", "lathe", "jar"): return bottle(spec, name, label, front)
    if s == "box": return box(spec, name)
    if s == "pouch": return pouch(spec, name, kw.get("tear_at"))
    if s == "bar": return bar(spec, name)
    raise ValueError(f"unknown shape {s}")
