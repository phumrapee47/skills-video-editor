"""A styled glass drink for 3D product ads (references/ad-craft.md "food styling" and "glass drinks"): a glass mug,
cup or tall glass; the drink in layers that blend softly; piped whipped cream (a star-tip swirl); chocolate or caramel
sauce over the rim running down in thick tongues and drizzled on the cream; a striped straw; sprinkles; condensation
beads only where the cold drink is behind the glass.

product.json: {"shape": "drink", "glass": "mug" | "cup" | "tall",
               "layers": [{"color": "#6B3A23", "to": 0.18}, {"color": "#F6B8C6", "to": 1.0}],   ("to": fraction of the fill)
               "fill": 0.88, "cream": "#FFF6EC" | null, "drip": "chocolate" | "caramel" | "#hex" | null, "drizzle": true,
               "straw": ["#FFFFFF", "#EC6A9A"] | null, "sprinkles": true, "cold": true}
Built in the can's envelope (bottom at local z -0.58, about 1.16 tall with the cream; the front faces -x), so every
shot frames it like the can. Called through ad_shapes.build.
"""
import math, random
import bpy, bmesh
from mathutils import Vector

import ad_can as AC

GLASS = {"mug": dict(rb=0.30, rt=0.36, h=0.80, handle=True), "cup": dict(rb=0.27, rt=0.38, h=0.78, handle=False),
         "tall": dict(rb=0.24, rt=0.29, h=0.92, handle=False)}
SAUCE = {"chocolate": (0.065, 0.026, 0.011), "caramel": (0.52, 0.24, 0.05)}
ZB = -0.58


def _lin(h):
    h = h.lstrip("#"); c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(((x + 0.055) / 1.055) ** 2.4 if x > 0.04045 else x / 12.92 for x in c)


def _link(name, data, parent):
    o = bpy.data.objects.new(name, data); bpy.context.scene.collection.objects.link(o); o.parent = parent; return o


def lathe(name, prof, segs=96):
    """A closed surface of revolution from a (radius, z) path that starts and ends on the axis."""
    bm = bmesh.new(); rings = []
    ang = [2 * math.pi * i / segs for i in range(segs)]
    for r, z in prof:
        rings.append([bm.verts.new((0, 0, z))] if r < 1e-6 else [bm.verts.new((r * math.cos(a), r * math.sin(a), z)) for a in ang])
    for A, B in zip(rings, rings[1:]):
        if len(A) == 1 and len(B) == 1: continue
        for i in range(segs):
            j = (i + 1) % segs
            if len(A) == 1: bm.faces.new((A[0], B[j], B[i]))
            elif len(B) == 1: bm.faces.new((A[i], A[j], B[0]))
            else: bm.faces.new((A[i], A[j], B[j], B[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    for p in me.polygons: p.use_smooth = True
    return me


def _ramp_material(name, layers, z0, z1, clear=False):
    """The drink: colour by height (object z), each layer a band, neighbours blending over ~3 % of the fill."""
    m = AC.principled(name, (1, 1, 1), 0.0, 0.28 if not clear else 0.05, **({"Subsurface Weight": 0.35} if not clear else {"Transmission Weight": 0.6 if AC.CYCLES else 0.0}))
    N = m.node_tree.nodes; L = m.node_tree.links; b = N["Principled BSDF"]
    tc = N.new("ShaderNodeTexCoord"); sx = N.new("ShaderNodeSeparateXYZ"); mr = N.new("ShaderNodeMapRange")
    mr.inputs["From Min"].default_value = z0; mr.inputs["From Max"].default_value = z1
    cr = N.new("ShaderNodeValToRGB"); el = cr.color_ramp.elements; lo = 0.0
    stops = []
    for k, ly in enumerate(layers):
        hi = float(ly.get("to", 1.0)); c = (*_lin(ly["color"]), 1)
        stops += [(min(hi, lo + 0.015) if k else 0.0, c), (max(lo, hi - 0.015) if k < len(layers) - 1 else 1.0, c)]; lo = hi
    el[0].position, el[0].color = stops[0]; el[1].position, el[1].color = stops[-1]
    for pos, c in stops[1:-1]: e = el.new(pos); e.color = c
    for x_, y_ in ((tc.outputs["Object"], sx.inputs[0]), (sx.outputs["Z"], mr.inputs["Value"]), (mr.outputs["Result"], cr.inputs["Fac"]), (cr.outputs["Color"], b.inputs["Base Color"])):
        L.new(x_, y_)
    if "Subsurface Radius" in b.inputs: b.inputs["Subsurface Radius"].default_value = (0.08, 0.05, 0.04)
    return m


def swirl(name, r0, z0, height, turns=3.0, tube=0.085, n=260, m=32, parent=None):
    """Piped whipped cream: a star-tip cross-section (ridges) swept up a narrowing spiral to a soft peak."""
    bm = bmesh.new(); rings = []; path = []
    for i in range(n + 1):
        u = i / n; a = 2 * math.pi * turns * u
        R = (r0 - 0.012) * (1 - u) ** 0.85 + 0.012; z = z0 + height * (u ** 1.05) * 0.92
        path.append((Vector((R * math.cos(a), R * math.sin(a), z)), tube * (1 - u) ** 0.55 + 0.012 * (1 - u)))
    for i, (P, tr) in enumerate(path):
        Q = path[min(n, i + 1)][0] - path[max(0, i - 1)][0]; T = Q.normalized()
        Nn = T.cross(Vector((0, 0, 1))); Nn = Nn.normalized() if Nn.length > 1e-6 else Vector((1, 0, 0)); B = T.cross(Nn).normalized()
        ring = []
        for k in range(m):
            th = 2 * math.pi * k / m; rho = 1 + 0.22 * math.cos(8 * th)               # eight ridges of a star tip
            off = (Nn * math.cos(th) + B * math.sin(th)) * tr * rho
            off.z *= 0.86                                                        # it slumps a little under its weight
            ring.append(bm.verts.new(P + off))
        rings.append(ring)
    for A, Bv in zip(rings, rings[1:]):
        for k in range(m): bm.faces.new((A[k], A[(k + 1) % m], Bv[(k + 1) % m], Bv[k]))
    c0 = bm.verts.new(path[0][0]); bm.faces.new([c0] + rings[0][::-1]) if False else None
    for k in range(m): bm.faces.new((rings[0][(k + 1) % m], rings[0][k], c0))
    tip = bm.verts.new(path[-1][0] + Vector((0, 0, 0.035)))
    for k in range(m): bm.faces.new((rings[-1][k], rings[-1][(k + 1) % m], tip))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    for p in me.polygons: p.use_smooth = True
    o = _link(name, me, parent); sub = o.modifiers.new("smooth", "SUBSURF"); sub.levels = 1; sub.render_levels = 1
    return o, path


def build(spec, name):
    rnd = random.Random(spec.get("seed", 7))
    G = GLASS.get(spec.get("glass", "mug"), GLASS["mug"]); rb, rt, h = G["rb"], G["rt"], G["h"]; t, tb = 0.032, 0.07
    ztop = ZB + h; rout = lambda z: rb + (rt - rb) * (z - ZB) / h; rin = lambda z: rout(z) - t
    root = bpy.data.objects.new(name, None); bpy.context.scene.collection.objects.link(root)
    # ---- the glass: outer wall up, a rounded rim, inner wall down, a thick base
    zs = [ZB + h * f for f in (0.08, 0.3, 0.55, 0.8, 0.97)]
    prof = [(0, ZB), (rb - 0.03, ZB), (rb - 0.004, ZB + 0.01), (rb, ZB + 0.03)] + [(rout(z), z) for z in zs]
    prof += [(rt - 0.004, ztop), (rt - t / 2, ztop + 0.006), (rt - t + 0.004, ztop), ]
    prof += [(rin(z), z) for z in reversed(zs[1:])] + [(rin(ZB + tb + 0.03), ZB + tb + 0.03), (rin(ZB + tb) - 0.02, ZB + tb), (0, ZB + tb)]
    gme = lathe("glass", prof); glass = _link(name + "_glass", gme, root)
    gm = AC.clear_liquid("glass", (0.97, 0.985, 1.0), 0.015, 1.5, 0.45); cold = gm.copy(); cold.name = "glass_cold"
    gme.materials.append(gm); gme.materials.append(cold)
    fill = float(spec.get("fill", 0.88)); zf = ZB + tb + (h - tb) * fill
    for p in gme.polygons:                                                 # the outer wall below the drink: cold, beads form there
        c = p.center; r = math.hypot(c.x, c.y)
        if c.z < zf - 0.02 and c.z > ZB + 0.03 and r > rin(c.z) + t * 0.5: p.material_index = 1
    if G["handle"]:
        bm = bmesh.new(); bmesh.ops.create_cone(bm, cap_ends=False, segments=8, radius1=1, radius2=1, depth=1) if False else None
        bpy.ops.mesh.primitive_torus_add(major_radius=0.17, minor_radius=0.034, major_segments=48, minor_segments=16,
                                         location=(0, rt + 0.06, ZB + h * 0.5), rotation=(0, math.radians(90), 0))
        hd = bpy.context.object; hd.name = name + "_handle"
        bm = bmesh.new(); bm.from_mesh(hd.data); M = hd.matrix_world
        kill = [v for v in bm.verts if (M @ v.co).y < rout((M @ v.co).z) - 0.012]
        bmesh.ops.delete(bm, geom=kill, context="VERTS"); bm.to_mesh(hd.data); bm.free()
        hd.data.materials.append(gm); hd.parent = root
        for p in hd.data.polygons: p.use_smooth = True
    # ---- the drink, slightly into the inner wall (no gap line), a flat top
    lp = [(0, ZB + tb + 0.002), (rin(ZB + tb) - 0.018, ZB + tb + 0.002), (rin(ZB + tb + 0.03) + 0.003, ZB + tb + 0.03)]
    lp += [(rin(z) + 0.003, z) for z in [ZB + tb + (zf - ZB - tb) * f for f in (0.3, 0.6, 0.9)]] + [(rin(zf) + 0.003, zf), (rin(zf) * 0.96, zf + 0.004), (0, zf + 0.004)]
    dme = lathe("drink", lp); drink = _link(name + "_drink", dme, root)
    layers = spec.get("layers") or [{"color": "#F6B8C6", "to": 1.0}]
    dme.materials.append(_ramp_material("drink", layers, ZB + tb, zf, spec.get("clear", False)))
    # ---- cream: a dome to sit on, then the piped swirl
    cream_top = 0.72 if spec.get("glass", "mug") != "tall" else 0.62; cr_path = None   # a proud swirl, as styled
    if spec.get("cream"):
        cm = AC.principled("cream", _lin(spec["cream"]), 0.0, 0.5, **{"Subsurface Weight": 0.5, "Coat Weight": 0.1})
        b = cm.node_tree.nodes["Principled BSDF"]
        if "Subsurface Radius" in b.inputs: b.inputs["Subsurface Radius"].default_value = (0.06, 0.05, 0.04)
        bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=1, location=(0, 0, ztop - 0.005)); dome = bpy.context.object
        dome.name = name + "_cream_base"; dome.scale = (rin(ztop) + 0.008, rin(ztop) + 0.008, 0.07); dome.data.materials.append(cm); dome.parent = root
        bpy.ops.object.shade_smooth()
        sw, cr_path = swirl(name + "_cream", rin(ztop) - 0.05, ztop + 0.03, cream_top - ztop - 0.03, turns=3.0, tube=0.09 if spec.get("glass") != "tall" else 0.07, parent=root)
        sw.data.materials.append(cm)
    # ---- sauce over the rim, running down; drizzled along the top of the swirl
    if spec.get("drip"):
        col = SAUCE.get(spec["drip"]) or _lin(spec["drip"])
        sm = AC.principled("sauce", col, 0.0, 0.12, **{"Coat Weight": 0.7, "Coat Roughness": 0.05, "Specular IOR Level": 0.7})
        mb = bpy.data.metaballs.new("sauce_drip"); mb.resolution = 0.02; mb.render_resolution = 0.008; mb.threshold = 0.6
        def ball(p, r):
            e = mb.elements.new(); e.co = p; e.radius = r; e.stiffness = 2.0
        for k in range(72):                                                # the band over the rim
            a = 2 * math.pi * k / 72; ball(Vector((math.cos(a) * (rt - 0.006), math.sin(a) * (rt - 0.006), ztop + 0.01)), 0.05)
        front_clear = math.pi                                              # local -x faces the lens: keep one tongue there, short
        for k in range(10):
            a = 2 * math.pi * k / 10 + rnd.uniform(-0.2, 0.2); Lk = rnd.uniform(0.1, 0.42) * (0.6 if abs(((a - front_clear + math.pi) % (2 * math.pi)) - math.pi) < 0.4 else 1.0)
            s = 0.0; wob = rnd.uniform(-0.04, 0.04)
            while s < Lk:
                z = ztop - s; rr = 0.036 - 0.012 * s / Lk; aa = a + wob * s
                ball(Vector((math.cos(aa) * (rout(z) + 0.012), math.sin(aa) * (rout(z) + 0.012), z)), rr); s += 0.022
            z = ztop - Lk; ball(Vector((math.cos(a + wob * Lk) * (rout(z) + 0.016), math.sin(a + wob * Lk) * (rout(z) + 0.016), z)), 0.042)   # the drop at the end
        if spec.get("drizzle", True) and cr_path:
            for i in range(14, len(cr_path) - 12, 4):
                P, tr = cr_path[i]; ball(P + Vector((0, 0, tr * 0.82)), 0.024)
        mo = _link(name + "_sauce_mb", mb, root); mb.materials.append(sm)
        # bake to a mesh: a metaball re-meshes at every motion-blur step with a different topology and EEVEE's blur
        # turns that into blocky garbage (it only moves with the glass, so a fixed mesh blurs correctly)
        mb.resolution = 0.008; bpy.context.view_layer.update(); dg = bpy.context.evaluated_depsgraph_get()
        sme = bpy.data.meshes.new_from_object(mo.evaluated_get(dg)); sme.materials.clear(); sme.materials.append(sm)
        for p in sme.polygons: p.use_smooth = True
        bpy.data.objects.remove(mo); _link(name + "_sauce", sme, root)
    # ---- straw
    if spec.get("straw"):
        c1, c2 = (_lin(spec["straw"][0]), _lin(spec["straw"][1])) if isinstance(spec["straw"], list) else ((1, 1, 1), _lin(spec["straw"]))
        bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.026, depth=1.15, location=(0.1, -0.1, 0.34)); st = bpy.context.object
        st.name = name + "_straw"; st.rotation_euler = (math.radians(-14), math.radians(8), 0); st.parent = root; bpy.ops.object.shade_smooth()
        stm = AC.principled("straw", c1, 0.0, 0.3); N = stm.node_tree.nodes; L = stm.node_tree.links
        tc = N.new("ShaderNodeTexCoord"); wv = N.new("ShaderNodeTexWave"); wv.wave_type = "BANDS"; wv.bands_direction = "DIAGONAL"; wv.inputs["Scale"].default_value = 6.0
        rp = N.new("ShaderNodeValToRGB"); rp.color_ramp.interpolation = "CONSTANT"; rp.color_ramp.elements[0].color = (*c1, 1); rp.color_ramp.elements[1].position = 0.5
        rp.color_ramp.elements[1].color = (*c2, 1)
        for x_, y_ in ((tc.outputs["Object"], wv.inputs["Vector"]), (wv.outputs["Fac"], rp.inputs["Fac"]), (rp.outputs["Color"], N["Principled BSDF"].inputs["Base Color"])):
            L.new(x_, y_)
        st.data.materials.append(stm)
    # ---- sprinkles on the cream
    if spec.get("sprinkles") and cr_path:
        bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=10, v_segments=6, radius=1)
        for v in bm.verts: v.co.x *= 2.6; v.co.y *= 0.75; v.co.z *= 0.75
        spm = bpy.data.meshes.new("sprinkle"); bm.to_mesh(spm); bm.free(); spm.materials.append(None)
        for p in spm.polygons: p.use_smooth = True
        cols = [(1.0, 0.22, 0.42), (0.25, 0.55, 1.0), (1.0, 0.85, 0.2), (0.95, 0.95, 0.95), (0.45, 0.85, 0.5)]
        mats = [AC.principled(f"sprinkle{i}", c, 0.0, 0.3) for i, c in enumerate(cols)]
        for i in range(70):
            P, tr = cr_path[rnd.randrange(8, len(cr_path) - 8)]; th = rnd.uniform(-1.2, 1.2)
            pos = P + Vector((math.cos(th) * 0.3, math.sin(th) * 0.3, 0.9)).normalized() * tr * 1.02
            o = _link(f"sprinkle{i}", spm, root); o.location = pos; o.scale = (0.012,) * 3
            o.rotation_euler = (rnd.uniform(0, 3.14), rnd.uniform(0, 3.14), rnd.uniform(0, 3.14))
            o.material_slots[0].link = "OBJECT"; o.material_slots[0].material = mats[i % len(mats)]
    if spec.get("cold", True):
        AC.condensation(glass, cold, density=4500)
    return root
