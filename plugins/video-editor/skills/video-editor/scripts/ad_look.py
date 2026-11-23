"""The designed look of a 3D ad shot (imported by blender_product_ad.py, runs inside Blender): camera moves, animated
backgrounds, decoration in depth layers, the motion style. Choices come from ad_design.py.

move(name, n, seed)      re-shoots the shot with a camera move, starting from the shot's own framing (the anchor:
                         camera and target at frame 1), so a move fits any product and any shot
background(kind, c1, c2, n)  gradient_bokeh | haze_glints | neon_grid | window_light | plain
decor(kind, n, seed)     droplets | gold_dust | light_specks | soft_dust | none - near the lens (out of focus) and behind
light_rig(family)        each mood family's light: fresh high-key, luxury gold rims + a long streak, tech neon rims,
                         clean a big soft top light
ease(style, whip=False)  bouncy (overshoot) | smooth (sine) | snappy (expo) | auto on objects with few keys; the camera
                         always eases in and out (a whip snaps)
"""
import math, random
import bpy
from mathutils import Vector, Matrix

import ad_can as AC


def _cam():
    return bpy.data.objects["Cam"], bpy.data.objects["CamTarget"]


def _key(o, fr, **kw):
    for k, v in kw.items(): setattr(o, k, v); o.keyframe_insert(k, frame=fr)


def anchor():
    sc = bpy.context.scene; sc.frame_set(1); cam, tgt = _cam()
    return cam.location.copy(), tgt.location.copy(), cam.data.lens


def move(name, n, seed=1):
    """Camera moves relative to the anchor. Returns True when the camera was changed."""
    if not name or name == "native": return False
    cam, tgt = _cam(); C, T, L = anchor(); d = C - T; dist = d.length
    h = Vector((d.x, d.y, 0)); h = h.normalized() if h.length > 1e-6 else Vector((0, -1, 0))
    p = Vector((-h.y, h.x, 0)); sgn = 1 if random.Random(seed).random() < 0.5 else -1
    cam.animation_data_clear(); tgt.animation_data_clear()
    if cam.data.animation_data: cam.data.animation_data_clear()
    cam.data.dof.focus_object = tgt
    def at(fr, c, t, lens=None):
        _key(cam, fr, location=c); _key(tgt, fr, location=t)
        if lens: cam.data.lens = lens; cam.data.keyframe_insert("lens", frame=fr)
    def rz(v, a): return Matrix.Rotation(a, 3, "Z") @ v
    if name == "dolly_in": at(1, T + d * 1.2, T); at(n, T + d * 0.85, T)
    elif name == "dolly_out": at(1, T + d * 0.85, T); at(n, T + d * 1.3, T)
    elif name in ("orbit", "spiral"):
        a0, a1 = math.radians(-38 * sgn), math.radians(34 * sgn)
        for k in range(5):
            t = k / 4; a = a0 + (a1 - a0) * t
            dd = rz(d, a) * ((1.1 - 0.2 * t) if name == "spiral" else 1.0) + Vector((0, 0, (0.28 * dist * 0.4 * t) if name == "spiral" else 0))
            at(1 + round((n - 1) * t), T + dd, T)
    elif name == "crane_down": at(1, T + h * dist * 0.8 + Vector((0, 0, dist * 0.6)), T - Vector((0, 0, 0.1))); at(n, C, T)
    elif name == "crane_up": at(1, C - Vector((0, 0, 0.12 * dist)), T - Vector((0, 0, 0.08))); at(n, C + Vector((0, 0, 0.16 * dist)), T + Vector((0, 0, 0.1)))
    elif name == "truck": at(1, C + p * 0.32 * dist * sgn, T + p * 0.08 * dist * sgn); at(n, C - p * 0.32 * dist * sgn, T - p * 0.08 * dist * sgn)
    elif name == "low_hero":
        up = Vector((0, 0, 0.12))
        at(1, Vector((*(T + h * dist * 1.1).xy, 0.2)), T + up); at(n, Vector((*(T + h * dist * 0.92).xy, 0.24)), T + up)
    elif name == "top_down":
        at(1, T + Vector((0, -0.04, dist * 0.85)) + p * 0.12, T); at(n, T + Vector((0, -0.04, dist * 0.72)) - p * 0.12, T)
    elif name == "macro_slide":
        at(1, T + d * 0.55 + p * 0.14 * dist * sgn, T, L + 10); at(n, T + d * 0.5 - p * 0.14 * dist * sgn, T, L + 10)
    elif name == "rack_focus":
        at(1, T + d * 1.05, T); at(n, T + d * 0.95, T)
        cam.data.dof.focus_object = None; cam.data.dof.aperture_fstop = min(cam.data.dof.aperture_fstop, 2.2)
        for fr, fd in ((1, dist * 0.3), (max(2, int(n * 0.15)), dist * 0.3), (max(3, int(n * 0.45)), dist), (n, dist * 0.95)):
            cam.data.dof.focus_distance = fd; cam.data.dof.keyframe_insert("focus_distance", frame=fr)
        foreground(C, T, L, 5, seed)                                       # something to pull focus from
    elif name == "dolly_zoom": at(1, T + d * 1.7, T, L * 1.7); at(n, T + d * 0.85, T, L * 0.85)
    elif name == "whip_in":
        at(1, C, T + p * dist * 1.1 * sgn); at(7, C + (T - C) * 0.04, T); at(n, C + (T - C) * 0.1, T)
    elif name == "push_tilt": at(1, C, T); at(n, T + h * dist * 0.7 + Vector((0, 0, dist * 0.45)), T - Vector((0, 0, 0.05)))
    else: return False
    return True


def foreground(C, T, L, k, seed):
    """Soft shapes close to the lens, for a rack focus to start on."""
    rnd = random.Random(seed + 7); fwd = (T - C).normalized(); right = fwd.cross(Vector((0, 0, 1))).normalized(); up = right.cross(fwd)
    fl = bpy.data.materials.get("floor"); col = tuple(fl.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value[:3]) if fl else (0.5, 0.5, 0.5)
    m = AC.principled("fg_soft", tuple(c * 0.8 for c in col), 0.0, 0.3)   # set-coloured shapes, not white orbs
    for i in range(min(k, 3)):                                             # at the frame edges: the product stays clear
        z = (T - C).length * rnd.uniform(0.2, 0.3); hh = z * 18 / L
        xo = math.copysign(rnd.uniform(0.6, 0.95), rnd.uniform(-1, 1))
        pos = C + fwd * z + right * xo * hh * 9 / 16 + up * rnd.uniform(-0.9, 0.9) * hh
        bpy.ops.mesh.primitive_uv_sphere_add(radius=z * rnd.uniform(0.008, 0.018), location=pos); o = bpy.context.object
        o.data.materials.append(m); o.visible_shadow = False


# ---------------------------------------------------------------- backgrounds
def _emit(name, color, strength):
    m = bpy.data.materials.get(name)
    if m: return m
    m = AC.principled(name, color, 0.0, 0.5, **{"Emission Color": (*color, 1), "Emission Strength": strength}); return m


def _light(c, w=0.55): return tuple(x + (1 - x) * w for x in c)


def background(kind, c1, c2, n, seed=3):
    """Something alive behind the product: the eye reads a still wall as a render, a moving one as a set."""
    rnd = random.Random(seed); sc = bpy.context.scene
    if kind in (None, "plain"): return
    if kind == "gradient_bokeh":
        wall = bpy.data.materials.get("wall")
        if wall:                                                           # two soft pools of light drift across the wall
            nt = wall.node_tree; N = nt.nodes; Lk = nt.links; b = N["Principled BSDF"]; tc = N.new("ShaderNodeTexCoord"); pools = []
            for k, (x0, z0, dx) in enumerate(((-2.5, 3.0, 1.6), (2.8, 6.0, -1.3))):
                mp = N.new("ShaderNodeMapping"); mp.inputs["Scale"].default_value = (0.3, 0.3, 0.3)
                gr = N.new("ShaderNodeTexGradient"); gr.gradient_type = "SPHERICAL"; pw = N.new("ShaderNodeMath"); pw.operation = "POWER"; pw.inputs[1].default_value = 1.6
                Lk.new(tc.outputs["Object"], mp.inputs["Vector"]); Lk.new(mp.outputs["Vector"], gr.inputs["Vector"]); Lk.new(gr.outputs["Fac"], pw.inputs[0])
                loc = mp.inputs["Location"]                               # the pool centre, in the wall's own coordinates
                loc.default_value = (-x0 * 0.3, -z0 * 0.3, 0); loc.keyframe_insert("default_value", frame=1)
                loc.default_value = (-(x0 + dx) * 0.3, -(z0 + 0.4) * 0.3, 0); loc.keyframe_insert("default_value", frame=n)
                pools.append(pw)
            mx = N.new("ShaderNodeMath"); mx.operation = "MAXIMUM"; Lk.new(pools[0].outputs[0], mx.inputs[0]); Lk.new(pools[1].outputs[0], mx.inputs[1])
            mix = N.new("ShaderNodeMix"); mix.data_type = "RGBA"; mix.inputs["A"].default_value = (*c2, 1); mix.inputs["B"].default_value = (*_light(c1, 0.45), 1)
            Lk.new(mx.outputs[0], mix.inputs["Factor"]); Lk.new(mix.outputs["Result"], b.inputs["Base Color"])
            Lk.new(mix.outputs["Result"], b.inputs["Emission Color"]); b.inputs["Emission Strength"].default_value = 0.25
        for i in range(28):                                                # bokeh discs behind the product
            bpy.ops.mesh.primitive_uv_sphere_add(radius=rnd.uniform(0.03, 0.08), segments=12, ring_count=8,
                                                 location=(rnd.uniform(-2.6, 2.6), rnd.uniform(2.5, 6.5), rnd.uniform(0.2, 3.2)))
            o = bpy.context.object; o.data.materials.append(_emit(f"bokeh{i % 3}", _light(c1 if i % 3 else (1, 1, 1), 0.5), 4.0)); o.visible_shadow = False
            p0 = o.location.copy(); _key(o, 1, location=p0); _key(o, n, location=p0 + Vector((rnd.uniform(-0.3, 0.3), 0, rnd.uniform(0.15, 0.5))))
    elif kind == "haze_glints":
        fl = bpy.data.materials.get("floor")
        if fl:
            b = fl.node_tree.nodes["Principled BSDF"]; b.inputs["Roughness"].default_value = 0.1; b.inputs["Base Color"].default_value = (*(x * 0.35 for x in c2), 1)
        bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 3.5, 2)); hz = bpy.context.object; hz.scale = (12, 7, 4.5)
        m = bpy.data.materials.new("haze"); m.use_nodes = True; N = m.node_tree.nodes; Lk = m.node_tree.links
        N.remove(N["Principled BSDF"]); vol = N.new("ShaderNodeVolumePrincipled"); vol.inputs["Color"].default_value = (*_light(c1, 0.5), 1)
        tc = N.new("ShaderNodeTexCoord"); mp = N.new("ShaderNodeMapping"); nz = N.new("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 1.6
        mr = N.new("ShaderNodeMapRange"); mr.inputs["To Min"].default_value = 0.0; mr.inputs["To Max"].default_value = 0.018   # a hint of haze, not fog
        for x, y in ((tc.outputs["Object"], mp.inputs["Vector"]), (mp.outputs["Vector"], nz.inputs["Vector"]), (nz.outputs["Fac"], mr.inputs["Value"]),
                     (mr.outputs["Result"], vol.inputs["Density"]), (vol.outputs["Volume"], N["Material Output"].inputs["Volume"])): Lk.new(x, y)
        loc = mp.inputs["Location"]; loc.default_value = (0, 0, 0); loc.keyframe_insert("default_value", frame=1)
        loc.default_value = (0.25, 0.05, 0.12); loc.keyframe_insert("default_value", frame=n)                   # the haze drifts
        hz.data.materials.append(m); hz.visible_shadow = False
        gold = (1.0, 0.72, 0.3)
        for i in range(40):                                                # glints that twinkle
            bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=rnd.uniform(0.006, 0.016), location=(rnd.uniform(-2.2, 2.2), rnd.uniform(-0.5, 4), rnd.uniform(0.3, 2.8)))
            o = bpy.context.object; gm = AC.principled(f"glint{i}", gold, 1.0, 0.2, **{"Emission Color": (*gold, 1), "Emission Strength": 0.0})
            o.data.materials.append(gm); o.visible_shadow = False; es = gm.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"]
            ph = rnd.uniform(0, 6.28); per = rnd.uniform(18, 40)
            for fr in range(1, n + 1, 4): es.default_value = 12 * max(0, math.sin(fr / per * 6.28 + ph)) ** 6; es.keyframe_insert("default_value", frame=fr)
            p0 = o.location.copy(); _key(o, 1, location=p0); _key(o, n, location=p0 + Vector((0.1, 0, 0.12)))
    elif kind == "neon_grid":
        cyan, mag = (0.1, 0.9, 1.0), (1.0, 0.15, 0.8); gm = _emit("grid", cyan, 3.0)
        root = bpy.data.objects.new("grid", None); sc.collection.objects.link(root)
        for i in range(-10, 11):
            for along in (0, 1):
                bpy.ops.mesh.primitive_cube_add(size=1, location=(i * 0.6, 3, 0.003) if along else (0, i * 0.6 + 3, 0.003)); o = bpy.context.object
                o.scale = (0.008, 14, 0.004) if along else (14, 0.008, 0.004); o.data.materials.append(gm); o.parent = root; o.visible_shadow = False
        _key(root, 1, location=(0, 0, 0)); _key(root, n, location=(0, -0.6, 0))                                 # the floor scrolls
        for k in range(5):                                                 # neon strips across the wall
            bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 8.6, 0.6 + k * 0.7)); o = bpy.context.object
            o.scale = (rnd.uniform(1.5, 4), 0.02, 0.02); o.data.materials.append(_emit(f"neon{k}", mag if k % 2 else cyan, 6.0)); o.visible_shadow = False
            x0 = rnd.uniform(-6, -2) * (1 if k % 2 else -1); _key(o, 1, location=(x0, 8.6, o.location.z)); _key(o, n, location=(-x0, 8.6, o.location.z))
    elif kind == "window_light":
        bpy.ops.object.light_add(type="SPOT", location=(3.5, -2.5, 5.5)); sp = bpy.context.object; sp.data.energy = 2500; sp.data.spot_size = math.radians(70)
        sp.data.shadow_soft_size = 0.05; sp.data.color = (1.0, 0.96, 0.9)
        d = Vector((0, 6, 1.5)) - sp.location; sp.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
        fr_root = bpy.data.objects.new("window", None); sc.collection.objects.link(fr_root); fr_root.location = sp.location + d.normalized() * 1.2
        fr_root.rotation_euler = sp.rotation_euler
        for x in (-0.36, 0.0, 0.36):                                       # the window frame: bars that cast the shadow
            bpy.ops.mesh.primitive_cube_add(size=1, location=(x, 0, 0)); o = bpy.context.object; o.scale = (0.03, 1.2, 0.03); o.parent = fr_root; o.visible_camera = False
        for y in (-0.4, 0.0, 0.4):
            bpy.ops.mesh.primitive_cube_add(size=1, location=(0, y, 0)); o = bpy.context.object; o.scale = (1.2, 0.03, 0.03); o.parent = fr_root; o.visible_camera = False
        p0 = fr_root.location.copy(); _key(fr_root, 1, location=p0); _key(fr_root, n, location=p0 + Vector((0.35, 0, -0.1)))   # the light moves slowly


# ---------------------------------------------------------------- decoration in depth
def decor(kind, n, seed=5):
    if kind in (None, "none"): return
    C, T, L = anchor(); rnd = random.Random(seed); fwd = (T - C).normalized(); dist = (T - C).length
    right = fwd.cross(Vector((0, 0, 1))).normalized(); up = right.cross(fwd)
    spec = {"droplets": (18, (0.012, 0.035), None), "gold_dust": (45, (0.002, 0.005), ((1.0, 0.75, 0.35), 1.8)),
            "light_specks": (30, (0.003, 0.007), ((0.2, 0.9, 1.0), 4.0)), "soft_dust": (40, (0.002, 0.004), ((1, 1, 1), 0.35))}[kind]
    cnt, (r0, r1), em = spec
    cnt = max(8, int(cnt * min(1.0, dist / 2.5)))                          # close shots: fewer, or they pile up as bokeh
    mat = AC.clear_liquid("water", (0.97, 0.99, 1.0), 0.02, 1.333, 0.55) if kind == "droplets" else AC.principled(f"decor_{kind}", em[0], 0.0, 0.4, **{"Emission Color": (*em[0], 1), "Emission Strength": em[1]})
    for i in range(cnt):
        near = kind == "droplets" and i % 3 == 0                           # only clear drops near the lens: glowing specks there
        z = dist * (rnd.uniform(0.3, 0.5) if near else rnd.uniform(0.75, 1.8)); hh = z * 18 / L   # turn into orbs over the product
        xo, yo = rnd.uniform(-1, 1), rnd.uniform(-1, 1)
        if (near or z < dist * 1.15) and abs(xo) < 0.55 and abs(yo) < 0.5: xo = math.copysign(rnd.uniform(0.55, 1.0), xo)   # the product stays clear
        pos = C + fwd * z + right * xo * hh * 9 / 16 + up * yo * hh
        r = rnd.uniform(r0, r1) * (2.2 if near else 1.0) * (z / dist) ** 0.5
        if kind == "light_specks": bpy.ops.mesh.primitive_cube_add(size=r * 2, location=pos)
        else: bpy.ops.mesh.primitive_uv_sphere_add(radius=r, segments=16, ring_count=10, location=pos)
        o = bpy.context.object; o.data.materials.append(mat); o.visible_shadow = False
        if kind == "droplets": bpy.ops.object.shade_smooth()
        drift = Vector((rnd.uniform(-0.05, 0.05), rnd.uniform(-0.05, 0.05), rnd.uniform(0.04, 0.16))) * dist * 0.4
        _key(o, 1, location=pos); _key(o, n, location=pos + drift)


# ---------------------------------------------------------------- motion style
def _fcurves(ad):
    if not ad or not ad.action: return []
    fcs = getattr(ad.action, "fcurves", None)
    if fcs is not None: return list(fcs)
    try: return [fc for layer in ad.action.layers for strip in layer.strips for cb in strip.channelbags for fc in cb.fcurves]
    except Exception: return []


def ease(style="auto", whip=False):
    """Interpolation by motion style on objects with few keys (dense per-frame keys - simulations - are left alone)."""
    style_map = {"bouncy": ("BACK", "EASE_OUT"), "smooth": ("SINE", "EASE_IN_OUT"), "snappy": ("EXPO", "EASE_OUT"), "auto": ("BEZIER", "AUTO")}
    obj_i, obj_e = style_map.get(style, style_map["auto"])
    for ob in bpy.data.objects:
        is_cam = ob.name in ("Cam", "CamTarget")
        for fc in _fcurves(ob.animation_data):
            kps = fc.keyframe_points
            if len(kps) > 8 and not is_cam: continue
            for kp in kps:
                if is_cam: kp.interpolation, kp.easing = ("EXPO", "EASE_OUT") if whip else ("SINE", "EASE_IN_OUT")
                else:
                    kp.interpolation = obj_i
                    if obj_i != "BEZIER": kp.easing = obj_e
                    else: kp.easing = "AUTO"
                    if obj_i == "BACK":
                        try: kp.back = 1.2
                        except Exception: pass


# ---------------------------------------------------------------- light per mood family
RIGS = {   # key: energy, size, colour; rims: energy, size, colour (left, right); world: strength factor; extras
    # tuned against the approved v5 look: brighter rigs washed the colours out to pink under the neutral view
    "fresh":  {"key": (430, 3.5, (1.0, 0.98, 0.94)), "rims": (450, 0.8, (1.0, 0.94, 0.84), (1.0, 0.9, 0.8)), "world": 1.0, "fill": 110},
    "luxury": {"key": (230, 1.2, (1.0, 0.9, 0.8)), "rims": (1000, 0.35, (1.0, 0.72, 0.38), (1.0, 0.78, 0.45)), "world": 0.3, "streak": 160},
    "tech":   {"key": (180, 1.5, (0.75, 0.85, 1.0)), "rims": (1600, 0.3, (1.0, 0.2, 0.8), (0.1, 0.9, 1.0)), "world": 0.3},
    "clean":  {"key": (260, 6.0, (1.0, 1.0, 1.0)), "rims": (200, 1.5, (1.0, 1.0, 1.0), (1.0, 1.0, 1.0)), "world": 1.0, "fill": 90, "top": True},
}


def light_rig(family):
    """Re-light the studio for the mood family (the studio's key/rimL/rimR lights and the world)."""
    R = RIGS.get(family); objs = bpy.data.objects
    if not R: return
    e, sz, col = R["key"]; k = objs.get("key")
    if k:
        k.data.energy, k.data.size, k.data.color = e, sz, col
        if R.get("top"):                                                   # clean: one big soft light from above the front
            k.location = (0.0, -1.6, 4.6); d = Vector((0, 0, 0.6)) - k.location; k.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    e, sz, cl, cr = R["rims"]
    for nm, cc, push in (("rimL", cl, 1), ("rimR", cr, 1)):
        o = objs.get(nm)
        if o:
            o.data.energy, o.data.size, o.data.color = e, sz, cc
            if family in ("luxury", "tech"):                               # rims further behind: a thin bright edge
                o.location.y += 1.2; d = Vector((0, 0, 0.6)) - o.location; o.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    w = bpy.context.scene.world
    if w and w.node_tree:
        for nd in w.node_tree.nodes:
            if nd.type == "BACKGROUND": nd.inputs["Strength"].default_value *= R["world"]
    if R.get("fill"):
        bpy.ops.object.light_add(type="AREA", location=(0, -4.5, 1.2)); f = bpy.context.object; f.name = "fill"
        f.data.energy, f.data.size = R["fill"], 4.0; d = Vector((0, 0, 0.7)) - f.location; f.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    if R.get("streak"):                                                    # luxury: a long thin light = a clean streak on the product
        bpy.ops.object.light_add(type="AREA", location=(-2.2, 0.6, 1.4)); st = bpy.context.object; st.name = "streak"   # beside and behind: an edge streak
        st.data.shape = "RECTANGLE"; st.data.size, st.data.size_y = 0.12, 3.0; st.data.energy = R["streak"]; st.data.color = (1.0, 0.92, 0.8)
        d = Vector((0, 0, 0.7)) - st.location; st.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
