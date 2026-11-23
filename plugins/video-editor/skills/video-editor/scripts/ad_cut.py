"""A cut that reads as real, and liquid that behaves like liquid (imported by blender_product_ad.py, inside Blender).

The user's verdict on the old cut: a flat glowing bar through the fruit looks cheap. A real cut shows what cuts and
how the fruit answers (references/ad-craft.md):
  blade(...)        a thin steel blade sweeping through the cut plane in a few frames (motion blur makes the streak);
                    the cut plane is turned toward the lens so its face catches the light
  seam(...)         a line of light drawn ON the fruit's surface along the cut, top to bottom, as the blade passes
  beads(...)        juice beading along the seam just before the halves open
  sheets(...)       juice films hooked to both cut faces: they stretch, sag and tear open as the halves part
  mist(...), pulp(...)  fine spray and juice vesicles flying from the cut, in the shot's speed ramp
  pool(...), crown(...) a liquid pool with spreading ripple rings, and a crown splash round a product dropped into it
"""
import math, random
import bpy, bmesh
from mathutils import Vector, Matrix

import ad_can as AC


def _key(o, fr, **kw):
    for k, v in kw.items(): setattr(o, k, v); o.keyframe_insert(k, frame=fr)


def _mat(name, color, rough=0.1, metal=0.0, **kw):
    return bpy.data.materials.get(name) or AC.principled(name, color, metal, rough, **kw)


def ring_points(half, R):
    """The cut edge of a half in rig space (the rim of its flat face), sorted round, from the fruit's own mesh."""
    me = half.data; pts = []
    for v in me.vertices:
        if abs(v.co.z) < 1e-4 and Vector((v.co.x, v.co.y)).length > 0.85 * R:
            pts.append(half.matrix_local @ v.co)
    pts.sort(key=lambda p: math.atan2(p.y, p.z)); return pts


def seam(rig, pts, F, front_sign=-1, width=0.006):
    """A bright line drawn along the front half of the cut edge, from the top down, while the blade passes."""
    arc = [p * 1.006 for p in pts if p.y * front_sign > -0.02]
    arc.sort(key=lambda p: -p.z)                                           # top -> bottom
    cu = bpy.data.curves.new("seam", "CURVE"); cu.dimensions = "3D"; cu.bevel_depth = width; cu.bevel_resolution = 2
    sp = cu.splines.new("POLY"); sp.points.add(len(arc) - 1)
    for i, p in enumerate(arc): sp.points[i].co = (p.x, p.y, p.z, 1)
    ob = bpy.data.objects.new("seam", cu); bpy.context.scene.collection.objects.link(ob); ob.parent = rig
    m = AC.principled("seam", (1.0, 0.97, 0.9), 0.0, 0.2, **{"Emission Color": (1.0, 0.95, 0.85, 1), "Emission Strength": 0.0})
    cu.materials.append(m); es = m.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"]
    for fr, e, end, st in ((F - 5, 0, 0.0, 0.0), (F - 4, 30, 0.0, 0.0), (F - 1, 30, 1.0, 0.0), (F, 20, 1.0, 0.0), (F + 2, 6, 1.0, 1.0)):
        cu.bevel_factor_end = end; cu.keyframe_insert("bevel_factor_end", frame=fr)
        cu.bevel_factor_start = st; cu.keyframe_insert("bevel_factor_start", frame=fr)   # the line runs off the bottom as the halves part
        es.default_value = e; es.keyframe_insert("default_value", frame=fr)
    for fr, h in ((F - 6, True), (F - 5, False), (F + 2, True)):
        ob.hide_render = h; ob.keyframe_insert("hide_render", frame=fr); ob.hide_viewport = h; ob.keyframe_insert("hide_viewport", frame=fr)
    return ob


def blade(rig, R, F, frames=7):
    """A thin steel blade: long along the cut, edge down, sweeping from above the fruit to below it in a few frames."""
    bpy.ops.mesh.primitive_cube_add(size=1); b = bpy.context.object; b.name = "blade"
    bm = bmesh.new(); bm.from_mesh(b.data)
    for v in bm.verts:                                                     # a wedge: thin spine on top, sharp edge below
        v.co.x *= 0.012 if v.co.z > 0 else 0.0008; v.co.y *= 3.2 * R; v.co.z *= 0.42 * R
    bm.to_mesh(b.data); bm.free()
    bv = b.modifiers.new("bev", "BEVEL"); bv.width = 0.003; bv.segments = 2
    b.data.materials.append(_mat("steel", (0.95, 0.95, 0.97), 0.16, 1.0)); b.parent = rig
    t = math.radians(-12)
    for fr, z, y in ((F - frames - 1, 2.2 * R, -0.4 * R), (F - frames, 1.4 * R, -0.3 * R), (F, -1.5 * R, 0.25 * R), (F + 1, -2.4 * R, 0.4 * R)):
        _key(b, fr, location=(0, y, z), rotation_euler=(t, 0, 0))
    for fr, s in ((F - frames - 2, 0.0), (F - frames - 1, 1.0), (F + 1, 1.0), (F + 2, 0.0)): _key(b, fr, scale=(s, s, s))
    return b


def beads(rig, pts, F, kind_mat, n=40, seed=3, front_sign=-1):
    """Juice wells up along the cut a moment before the halves open."""
    rnd = random.Random(seed); arc = [p for p in pts if p.y * front_sign > 0.0]
    if not arc: return
    me = bpy.data.meshes.new("bead"); bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=12, v_segments=8, radius=1.0); bm.to_mesh(me); bm.free()
    for poly in me.polygons: poly.use_smooth = True
    me.materials.append(kind_mat)
    for i in range(n):
        p = arc[rnd.randrange(len(arc))] * 1.008; o = bpy.data.objects.new(f"bead{i}", me); bpy.context.scene.collection.objects.link(o); o.parent = rig
        o.location = p; r = rnd.uniform(0.012, 0.03); t0 = F - 4 + rnd.randint(0, 3)
        for fr, s in ((t0 - 1, 0.0), (t0 + 1, r), (F + 1, r * 1.2), (F + 3, 0.0)): _key(o, fr, scale=(s, s, s * 0.8))


def sheets(rig, halves, R, F, n, gap_of, kind_mat_color, count=4, seed=5):
    """Juice films between the two cut faces. Each film is a strip whose two ends are hooked to points on the faces
    (empties parented to the halves), so it stretches as they part; a third hook sags its middle; holes open in it
    (noise threshold rising) until it tears away."""
    rnd = random.Random(seed); sc = bpy.context.scene; sc.frame_set(F); bpy.context.view_layer.update()
    hA, hB = halves; out = []
    m = bpy.data.materials.new("juice_film"); m.use_nodes = True; N = m.node_tree.nodes; L = m.node_tree.links; b = N["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*kind_mat_color, 1); b.inputs["Roughness"].default_value = 0.04
    for k_, v_ in (("Coat Weight", 0.6), ("Emission Color", (*kind_mat_color, 1)), ("Emission Strength", 0.15), ("Transmission Weight", 0.3 if AC.CYCLES else 0.0)):
        if k_ in b.inputs: b.inputs[k_].default_value = v_
    tc = N.new("ShaderNodeTexCoord"); nz = N.new("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 9.0; nz.inputs["Detail"].default_value = 3
    cmp = N.new("ShaderNodeMath"); cmp.operation = "GREATER_THAN"
    lw = N.new("ShaderNodeLayerWeight"); lw.inputs["Blend"].default_value = 0.35; ar = N.new("ShaderNodeMapRange")
    ar.inputs["To Min"].default_value = 0.3; ar.inputs["To Max"].default_value = 0.95                 # thin film: see-through face on, denser at the edges
    am = N.new("ShaderNodeMath"); am.operation = "MULTIPLY"
    for x_, y_ in ((tc.outputs["Object"], nz.inputs["Vector"]), (nz.outputs["Fac"], cmp.inputs[0]), (lw.outputs["Facing"], ar.inputs["Value"]),
                   (cmp.outputs[0], am.inputs[0]), (ar.outputs["Result"], am.inputs[1]), (am.outputs[0], b.inputs["Alpha"])):
        L.new(x_, y_)
    for k_, v_ in (("Coat Roughness", 0.02), ("Specular IOR Level", 0.8)):
        if k_ in b.inputs: b.inputs[k_].default_value = v_
    try: m.surface_render_method = "DITHERED"
    except Exception: pass
    thr = cmp.inputs[1]
    for k in range(count):
        zf = rnd.uniform(-0.5, 0.45) * R; yf = rnd.uniform(-0.35, 0.15) * R; hgt = rnd.uniform(0.05, 0.16) * R   # strands and narrow films
        ends = []
        for h in (hA, hB):                                                 # a point on each face, in world space at the cut
            e = bpy.data.objects.new(f"film{k}_{h.name}", None); sc.collection.objects.link(e)
            pw = rig.matrix_world @ Vector((0, yf, zf)); e.parent = h; e.matrix_world = Matrix.Translation(pw); ends.append(e)
        bpy.context.view_layer.update()
        nx, ny = 22, 4; me = bpy.data.meshes.new(f"film{k}"); verts, faces = [], []
        pa, pb = ends[0].matrix_world.translation.copy(), ends[1].matrix_world.translation.copy(); up = rig.matrix_world.to_3x3() @ Vector((0, 0, 1))
        for j in range(ny + 1):
            for i in range(nx + 1): verts.append(pa.lerp(pb, i / nx) + up * (j / ny - 0.5) * hgt)
        for j in range(ny):
            for i in range(nx): a_ = j * (nx + 1) + i; faces.append((a_, a_ + 1, a_ + nx + 2, a_ + nx + 1))
        mk = m.copy(); mk.name = f"juice_film{k}"; me.from_pydata(verts, [], faces); me.materials.append(mk)
        ob = bpy.data.objects.new(f"film{k}", me); sc.collection.objects.link(ob)
        vgA, vgB, vgM = ob.vertex_groups.new(name="A"), ob.vertex_groups.new(name="B"), ob.vertex_groups.new(name="M")
        for j in range(ny + 1):
            for i in range(nx + 1):
                vi = j * (nx + 1) + i; u = i / nx
                vgA.add([vi], 1 - u, "REPLACE"); vgB.add([vi], u, "REPLACE"); vgM.add([vi], math.sin(math.pi * u), "REPLACE")
        mid = bpy.data.objects.new(f"film{k}_mid", None); sc.collection.objects.link(mid); mid.location = (pa + pb) / 2
        mid.matrix_world = Matrix.Translation((pa + pb) / 2); bpy.context.view_layer.update()   # bind the hook at its real place
        for vg, tgt in (("A", ends[0]), ("B", ends[1]), ("M", mid)):
            hk = ob.modifiers.new("hook" + vg, "HOOK"); hk.object = tgt; hk.vertex_group = vg; hk.matrix_inverse = tgt.matrix_world.inverted()
        sol = ob.modifiers.new("thick", "SOLIDIFY"); sol.thickness = 0.003
        sub = ob.modifiers.new("smooth", "SUBSURF"); sub.levels = 1; sub.render_levels = 1
        for poly in me.polygons: poly.use_smooth = True
        brk = F + rnd.randint(8, 16)                                       # tear frame: films stretch through the slow motion
        for fr in range(F, n + 1, 2):                                      # sag grows with the gap
            g = gap_of(fr); _key(mid, fr, location=(pa + pb) / 2 - up * min(0.4 * R, 0.9 * g * g))
        out.append((ob, brk))
    for ob, brk in out:
        t_ = [n_ for n_ in ob.data.materials[0].node_tree.nodes if n_.type == "MATH"][0].inputs[1]
        for fr, t in ((1, 1.1), (F, 1.1), (F + 1, -0.1), (brk - 4, -0.1), (brk, 0.3), (brk + 5, 1.1)):   # whole, holes open, torn away
            t_.default_value = t; t_.keyframe_insert("default_value", frame=fr)
    return out


def flyers(center, F, n, warp, mesh, mat, count, speed, size, seed, g=6.0, life=1.0, spread=1.0, axis_x=True, basis=None):
    """Small bodies (mist drops, pulp) launched from around a centre in the shot's speed ramp; shrinking with age."""
    rnd = random.Random(seed); me = mesh; me.materials.append(mat); out = []
    for i in range(count):
        a = rnd.uniform(0, 2 * math.pi); d = Vector((rnd.choice((-1, 1)) * rnd.uniform(0.6, 1.0) if axis_x else math.cos(a) * spread,
                                                     rnd.uniform(-0.9, 0.3), rnd.uniform(0.2, 1.0) + (math.sin(a) * 0.4 if axis_x else 0.3)))
        v0 = (basis @ d if basis else d).normalized() * rnd.uniform(*speed); p0 = Vector(center) + Vector((0, rnd.uniform(-0.3, 0.3), rnd.uniform(-0.4, 0.4))) * 0.5
        o = bpy.data.objects.new(f"fly{seed}_{i}", me); bpy.context.scene.collection.objects.link(o); o.visible_shadow = False
        r = rnd.uniform(*size); rot = Vector((rnd.uniform(0, 3), rnd.uniform(0, 3), rnd.uniform(0, 3)))
        for fr in [1, F] + list(range(F + 1, n + 1, 2)):
            t = max(0.0, warp(fr)); p = p0 + v0 * t + Vector((0, 0, -0.5 * g * t * t)); s = 0.0 if fr <= F or t > life or p.z < 0.02 else r * (1 - 0.6 * t / life)
            o.location = p; o.scale = (s, s, s * (1.6 if not axis_x else 1.0)); o.rotation_euler = rot + v0 * t
            for k in ("location", "scale", "rotation_euler"): o.keyframe_insert(k, frame=fr)
        out.append(o)
    return out


def sphere_mesh(name, seg=10):
    me = bpy.data.meshes.new(name); bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=max(6, seg // 2), radius=1.0); bm.to_mesh(me); bm.free()
    for p in me.polygons: p.use_smooth = True
    return me


def vesicle_mesh(name):
    """A juice vesicle: a teardrop."""
    me = sphere_mesh(name, 12)
    for v in me.vertices: v.co.z *= 2.2 if v.co.z > 0 else 1.0; v.co.x *= 0.8
    return me


# ---------------------------------------------------------------- pool and crown splash
def _liquid(name, color, edge=(0.55, 0.97)):
    """Glossy liquid for thin sheets: see-through face on, dense at grazing angles; real transmission in Cycles."""
    m = AC.principled(name, color, 0.0, 0.03, **{"Coat Weight": 0.7, "Coat Roughness": 0.02, "Specular IOR Level": 0.8,
                                                 "Emission Color": (*color, 1), "Emission Strength": 0.12, "Transmission Weight": 0.35 if AC.CYCLES else 0.0})
    N = m.node_tree.nodes; L = m.node_tree.links; lw = N.new("ShaderNodeLayerWeight"); lw.inputs["Blend"].default_value = 0.3
    ar = N.new("ShaderNodeMapRange"); ar.inputs["To Min"].default_value, ar.inputs["To Max"].default_value = edge
    L.new(lw.outputs["Facing"], ar.inputs["Value"]); L.new(ar.outputs["Result"], N["Principled BSDF"].inputs["Alpha"])
    try: m.surface_render_method = "DITHERED"
    except Exception: pass
    return m


def pool(center, radius, F, n, color, rings_speed=1.6):
    """The set floor becomes a liquid surface; when something lands (frame F) ripple rings spread out from the centre
    behind a moving front and fade (the perfume-on-water look, references/ad-craft.md)."""
    bpy.ops.mesh.primitive_circle_add(vertices=128, radius=radius, fill_type="TRIFAN", location=center); o = bpy.context.object; o.name = "pool"
    m = AC.principled("pool", color, 0.0, 0.05, **{"Coat Weight": 0.8, "Coat Roughness": 0.02, "Specular IOR Level": 0.7}); N = m.node_tree.nodes; L = m.node_tree.links
    tc = N.new("ShaderNodeTexCoord"); ln = N.new("ShaderNodeVectorMath"); ln.operation = "LENGTH"; L.new(tc.outputs["Object"], ln.inputs[0])
    ph = N.new("ShaderNodeMath"); ph.operation = "MULTIPLY_ADD"; ph.inputs[1].default_value = 22.0        # r*k + phase
    L.new(ln.outputs["Value"], ph.inputs[0]); phase = ph.inputs[2]
    sn = N.new("ShaderNodeMath"); sn.operation = "SINE"; L.new(ph.outputs[0], sn.inputs[0])
    fr_ = N.new("ShaderNodeMapRange"); L.new(ln.outputs["Value"], fr_.inputs["Value"]); front = fr_.inputs["From Min"]   # 1 inside the front, 0 beyond
    fr_.inputs["To Min"].default_value = 1.0; fr_.inputs["To Max"].default_value = 0.0
    fall = N.new("ShaderNodeMath"); fall.operation = "EXPONENT"; neg = N.new("ShaderNodeMath"); neg.operation = "MULTIPLY"; neg.inputs[1].default_value = -0.9
    L.new(ln.outputs["Value"], neg.inputs[0]); L.new(neg.outputs[0], fall.inputs[0])                       # weaker far out
    e1 = N.new("ShaderNodeMath"); e1.operation = "MULTIPLY"; L.new(sn.outputs[0], e1.inputs[0]); L.new(fr_.outputs["Result"], e1.inputs[1])
    e2 = N.new("ShaderNodeMath"); e2.operation = "MULTIPLY"; L.new(e1.outputs[0], e2.inputs[0]); L.new(fall.outputs[0], e2.inputs[1])
    env = N.new("ShaderNodeMath"); env.operation = "MULTIPLY"; L.new(e2.outputs[0], env.inputs[0]); amp = env.inputs[1]
    bump = N.new("ShaderNodeBump"); bump.inputs["Strength"].default_value = 0.5; bump.inputs["Distance"].default_value = 0.02; L.new(env.outputs[0], bump.inputs["Height"])
    b = N["Principled BSDF"]; L.new(bump.outputs["Normal"], b.inputs["Normal"])
    if "Coat Normal" in b.inputs: L.new(bump.outputs["Normal"], b.inputs["Coat Normal"])                  # the coat carries the reflection
    o.data.materials.append(m)
    for fr, p_, a_, f_ in ((1, 0, 0.0, 0.0), (F, 0, 0.0, 0.0), (F + 2, -4, 1.0, 0.5), (n, -4 - (n - F) * rings_speed, 0.25, 0.5 + (n - F) / 30 * 1.6)):
        phase.default_value = p_; phase.keyframe_insert("default_value", frame=fr); amp.default_value = a_; amp.keyframe_insert("default_value", frame=fr)
        front.default_value = f_; front.keyframe_insert("default_value", frame=fr)
        fr_.inputs["From Max"].default_value = f_ + 0.35; fr_.inputs["From Max"].keyframe_insert("default_value", frame=fr)
    return o


def crown(center, r0, F, n, warp, color, fingers=13, seed=7, height=0.8):
    """A crown splash: a thin liquid wall thrown up round the product, flaring out, its rim breaking into fingers that
    shed drops; it rises fast, hangs in the slow motion, then falls back into the pool."""
    rnd = random.Random(seed); bm = bmesh.new(); seg, rows = 128, 16; ph = rnd.uniform(0, 6.28)
    tips = [rnd.uniform(0.6, 1.0) for _ in range(fingers)]
    grid = []
    for j in range(rows + 1):
        t = j / rows; row = []
        for i in range(seg):
            a = i / seg * 2 * math.pi; k = int((a * fingers / (2 * math.pi)) % fingers)
            lobe = max(0.0, math.cos(a * fingers + ph)) ** 6 * tips[k]                     # narrow fingers on the rim
            rise = max(0.0, (t - 0.55) / 0.45)                                              # they grow out of the top of the wall
            back = 0.42 + 0.58 * (math.sin(a) + 1) / 2                                     # low in front (-y, the lens side), tall behind: it frames the label
            r = 1.0 + 0.9 * t * t + 0.25 * lobe * rise; z = back * (t * (0.8 + 0.2 * math.sin(a * 3 + ph)) - 0.12 * (1 - lobe) * rise + 0.55 * lobe * rise * rise)
            row.append(bm.verts.new((math.cos(a) * r, math.sin(a) * r, z)))
        grid.append(row)
    for j in range(rows):
        for i in range(seg): bm.faces.new((grid[j][i], grid[j][(i + 1) % seg], grid[j + 1][(i + 1) % seg], grid[j + 1][i]))
    me = bpy.data.meshes.new("crown"); bm.to_mesh(me); bm.free()
    for p in me.polygons: p.use_smooth = True
    o = bpy.data.objects.new("crown", me); bpy.context.scene.collection.objects.link(o); o.location = center
    sol = o.modifiers.new("t", "SOLIDIFY"); sol.thickness = 0.012; sub = o.modifiers.new("s", "SUBSURF"); sub.levels = 1; sub.render_levels = 2
    m = _liquid("crown_liq", color); me.materials.append(m)
    for fr in [1, F] + list(range(F + 1, n + 1, 2)):
        t = max(0.0, warp(fr)); up = 0.0 if fr <= F else min(1.0, t / 0.2) * math.exp(-max(0, t - 0.3) * 3.5)   # up fast, hangs, falls back
        rr = r0 * (1.0 + 1.1 * min(1.0, t / 0.4)); o.scale = (rr, rr, max(1e-3, height * up)); o.keyframe_insert("scale", frame=fr)
    drops = flyers(Vector(center) + Vector((0, 0, height * 0.9)), F, n, lambda fr: max(0.0, warp(fr) - 0.1), sphere_mesh("crown_drop"), m, 46,
                   (1.2, 2.4), (0.01, 0.028), seed + 1, g=5.0, life=1.3, spread=1.0, axis_x=False)
    return o, drops
