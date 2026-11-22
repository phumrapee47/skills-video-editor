"""A real drink can for 3D ads, built from a can blueprint (imported by blender_product_ad.py, runs inside Blender).

Standard 330 ml can: diameter 66 mm, height 115.7 mm. Scene unit = 100 mm (radius 0.33), the bottom sits at local
z = -0.58 so the old placement (location z 0.6) still stands it on the floor.
  body_mesh()     lathe of the real profile: domed base and stand ring, chime, straight wall, necked shoulder, double
                  seam rim, countersink and a flat lid panel; the printed label covers z 6-106 mm (cylinder UV)
  tab_mesh()      the stay-on pull tab: rounded plate with the finger hole and the small rivet hole (scanfill holes)
  lid_parts()     rivet, tab on a pivot, the scored opening, its flap on a hinge pivot, the dark hole under it
  condensation()  Geometry Nodes: Poisson-disk water beads (many small, few big) aligned to the surface, on the label only
  ice_cube()      bevelled, slightly melted cube with clear/frosted ice, crackle bump and a cloudy core
"""
import math, random
import bpy, bmesh
from mathutils import Vector

MM = 0.01; Z0 = -0.58
PROFILE = [  # (radius mm, height mm) from the centre of the base dome, round the outside, over the seam, to the lid centre
    (0, 9.5), (8, 9.2), (15, 8.2), (20, 6.6), (23, 4.6), (24.5, 2.6), (25.0, 1.2), (25.6, 0.0), (26.6, 0.3),
    (28.5, 1.6), (30.5, 3.6), (32.0, 6.0), (32.8, 8.5), (33.0, 11.0), (33.0, 40.0), (33.0, 70.0), (33.0, 98.0),
    (32.9, 100.0), (32.3, 102.5), (31.0, 105.2), (29.4, 107.6), (28.2, 109.6), (27.7, 111.0),
    (27.7, 112.2), (28.1, 113.3), (28.3, 114.4), (28.1, 115.3), (27.6, 115.7), (27.0, 115.4),
    (26.7, 114.6), (26.4, 112.5), (26.2, 110.4), (25.8, 109.8), (25.3, 110.0), (25.0, 110.6), (24.4, 111.3),
    (18.0, 111.3), (9.0, 111.3), (0, 111.3)]
LABEL_MM = (6.0, 106.0)
LIDZ = 111.3 * MM + Z0                 # local z of the lid panel
OPEN_X, OPEN_R = -0.135, (0.092, 0.072)   # scored opening: centre on local -x (the label front), radii


def principled(name, color=(1, 1, 1), metal=0.0, rough=0.4, **kw):
    m = bpy.data.materials.new(name); m.use_nodes = True; b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1); b.inputs["Metallic"].default_value = metal; b.inputs["Roughness"].default_value = rough
    for k, v in kw.items():
        if k in b.inputs: b.inputs[k].default_value = v
    return m


def _glass(m):
    for attr, val in (("use_raytrace_refraction", True), ("surface_render_method", "DITHERED")):
        try: setattr(m, attr, val)
        except Exception: pass
    return m


CYCLES = False                         # set by blender_product_ad.py: true refraction in Cycles, a predictable stand-in in EEVEE


def clear_liquid(name, tint=(1, 1, 1), rough=0.02, ior=1.333, edge=0.6, frost=None):
    """Water / ice. Cycles: real transmission. EEVEE: screen-space refraction of tiny beads picks up the far wall and
    renders them dark, so use what the eye reads on real beads instead: see-through centre, darker refracting rim
    (layer-weight facing), sharp glossy highlights on a Fresnel mix. frost: (noise scale, amount) adds white frosted
    patches (ice)."""
    if CYCLES:
        m = _glass(principled(name, tint, 0.0, rough, **{"Transmission Weight": 1.0, "IOR": ior})); return m
    m = bpy.data.materials.new(name); m.use_nodes = True; nt = m.node_tree; N = nt.nodes; L = nt.links
    N.remove(N["Principled BSDF"]); out = N["Material Output"]
    lw = N.new("ShaderNodeLayerWeight"); lw.inputs["Blend"].default_value = 0.35
    rim = N.new("ShaderNodeMix"); rim.data_type = "RGBA"
    rim.inputs["A"].default_value = (*tint, 1); rim.inputs["B"].default_value = (tint[0] * edge, tint[1] * edge, tint[2] * edge, 1)
    L.new(lw.outputs["Facing"], rim.inputs["Factor"])
    tr = N.new("ShaderNodeBsdfTransparent"); L.new(rim.outputs["Result"], tr.inputs["Color"])
    gl = N.new("ShaderNodeBsdfGlossy"); gl.inputs["Roughness"].default_value = rough
    fr = N.new("ShaderNodeFresnel"); fr.inputs["IOR"].default_value = ior
    mx = N.new("ShaderNodeMixShader"); L.new(fr.outputs[0], mx.inputs[0]); L.new(tr.outputs[0], mx.inputs[1]); L.new(gl.outputs[0], mx.inputs[2])
    last = mx
    if frost:
        nz = N.new("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = frost[0]; nz.inputs["Detail"].default_value = 8
        mr = N.new("ShaderNodeMapRange"); mr.inputs["From Min"].default_value = 0.42; mr.inputs["From Max"].default_value = 0.72
        mr.inputs["To Max"].default_value = frost[1]
        tl = N.new("ShaderNodeBsdfDiffuse"); tl.inputs["Color"].default_value = (0.9, 0.94, 0.98, 1)   # white frost (translucent took the set colour: dirty ice)
        m2 = N.new("ShaderNodeMixShader"); L.new(nz.outputs["Fac"], mr.inputs["Value"]); L.new(mr.outputs["Result"], m2.inputs[0])
        L.new(mx.outputs[0], m2.inputs[1]); L.new(tl.outputs[0], m2.inputs[2]); last = m2
    L.new(last.outputs[0], out.inputs["Surface"])
    for attr, val in (("surface_render_method", "DITHERED"), ("use_transparent_shadow", True)):
        try: setattr(m, attr, val)
        except Exception: pass
    return m


def aluminium(name):
    """Brushed can metal: fully metallic, roughness drifting with fine noise (never a perfect mirror)."""
    m = principled(name, (0.91, 0.92, 0.93), 1.0, 0.2); nt = m.node_tree; N = nt.nodes; L = nt.links; b = N["Principled BSDF"]
    nz = N.new("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 180; mr = N.new("ShaderNodeMapRange")
    mr.inputs["To Min"].default_value = 0.14; mr.inputs["To Max"].default_value = 0.28
    L.new(nz.outputs["Fac"], mr.inputs["Value"]); L.new(mr.outputs["Result"], b.inputs["Roughness"])
    return m


def body_mesh(name, segs=128, front=0.5):
    """front: u of the label image that faces local -x (the side above which the opening sits = the logo)."""
    bm = bmesh.new()
    vs = [bm.verts.new((r * MM, 0, z * MM + Z0)) for r, z in PROFILE]
    es = [bm.edges.new((vs[i], vs[i + 1])) for i in range(len(vs) - 1)]
    bmesh.ops.spin(bm, geom=vs + es, cent=(0, 0, 0), axis=(0, 0, 1), angle=2 * math.pi, steps=segs, use_merge=True)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    uv = me.uv_layers.new(name="UV")
    for p in me.polygons:
        c = p.center; zmm = (c.z - Z0) / MM; rmm = Vector((c.x, c.y)).length / MM
        p.material_index = 0 if (LABEL_MM[0] <= zmm <= LABEL_MM[1] and rmm > 29.5) else 1
        p.use_smooth = True
        for li in p.loop_indices:
            v = me.vertices[me.loops[li].vertex_index].co
            uv.data[li].uv = ((math.atan2(v.y, v.x) / (2 * math.pi) - 0.5 + front) % 1.0, ((v.z - Z0) / MM - LABEL_MM[0]) / (LABEL_MM[1] - LABEL_MM[0]))
        us = [uv.data[li].uv[0] for li in p.loop_indices]
        if max(us) - min(us) > 0.5:                                        # seam: faces spanning 1 -> 0
            for li in p.loop_indices:
                if uv.data[li].uv[0] < 0.5: uv.data[li].uv[0] += 1.0
    try: me.set_sharp_from_angle(angle=math.radians(50))                  # crisp seam rim, smooth wall
    except Exception: pass
    return me


def _superellipse(cx, cy, a, b, n=3.0, k=56, rev=False):
    pts = []
    for i in range(k):
        t = 2 * math.pi * i / k; c, s = math.cos(t), math.sin(t)
        pts.append((cx + a * math.copysign(abs(c) ** (2 / n), c), cy + b * math.copysign(abs(s) ** (2 / n), s)))
    return pts[::-1] if rev else pts


def tab_mesh(name="tab", thick=0.007):
    """Pull tab in tab space: rivet at the origin, the nose toward -x (over the opening), the finger hole toward +x."""
    bm = bmesh.new(); loops = [_superellipse(0.055, 0, 0.118, 0.062, 3.4, 72),
                               _superellipse(0.112, 0, 0.046, 0.034, 2.6, 40), _superellipse(0.035, 0, 0.012, 0.012, 2.0, 16)]
    edges = []
    for pts in loops:
        vs = [bm.verts.new((x, y, 0)) for x, y in pts]
        edges += [bm.edges.new((vs[i], vs[(i + 1) % len(vs)])) for i in range(len(vs))]
    bmesh.ops.triangle_fill(bm, use_beauty=True, use_dissolve=False, edges=edges, normal=(0, 0, 1))
    faces = [f for f in bm.faces]
    ext = bmesh.ops.extrude_face_region(bm, geom=faces)
    bmesh.ops.translate(bm, vec=(0, 0, thick), verts=[e for e in ext["geom"] if isinstance(e, bmesh.types.BMVert)])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    return me


def lid_parts(body, m_metal, name):
    """Rivet, tab, scored opening, flap and the dark hole. Pivots: <name>_tabpivot (rotate Y negative: the finger end
    rises, the nose presses the flap) and <name>_flappivot (rotate Y negative: the flap pops in)."""
    dark = principled(name + "_hole", (0.004, 0.003, 0.002), 0.0, 1.0); dark.node_tree.nodes["Principled BSDF"].inputs["Specular IOR Level"].default_value = 0.0
    score = principled(name + "_score", (0.5, 0.5, 0.52), 1.0, 0.45)
    def add(me_or_op, parent, loc, scale=(1, 1, 1), m=m_metal, nm="part", **kw):
        if isinstance(me_or_op, bpy.types.Mesh): o = bpy.data.objects.new(nm, me_or_op); bpy.context.scene.collection.objects.link(o)
        else: me_or_op(location=(0, 0, 0), **kw); o = bpy.context.object; o.name = nm
        o.location = loc; o.scale = scale; o.data.materials.append(m); o.parent = parent
        for p in o.data.polygons: p.use_smooth = True
        return o
    def pivot(nm, loc):
        e = bpy.data.objects.new(nm, None); bpy.context.scene.collection.objects.link(e); e.parent = body; e.location = loc; return e
    z = LIDZ
    add(bpy.ops.mesh.primitive_cylinder_add, body, (OPEN_X, 0, z + 0.0004), (OPEN_R[0], OPEN_R[1], 0.0008), dark, name + "_hole", vertices=64, radius=1, depth=1)
    add(bpy.ops.mesh.primitive_torus_add, body, (OPEN_X, 0, z + 0.0006), (1.0, OPEN_R[1] / OPEN_R[0], 0.35), score, name + "_score",
        major_radius=OPEN_R[0] + 0.004, minor_radius=0.0035, major_segments=96, minor_segments=8)
    fp = pivot(name + "_flappivot", (OPEN_X + OPEN_R[0], 0, z + 0.0012))
    add(bpy.ops.mesh.primitive_cylinder_add, fp, (-OPEN_R[0], 0, 0), (OPEN_R[0] - 0.002, OPEN_R[1] - 0.002, 0.0016), m_metal, name + "_flap", vertices=64, radius=1, depth=1)
    rv = add(bpy.ops.mesh.primitive_uv_sphere_add, body, (0, 0, z + 0.004), (0.022, 0.022, 0.009), m_metal, name + "_rivet", segments=24, ring_count=12)
    tp = pivot(name + "_tabpivot", (0.0, 0, z + 0.0035))
    tab = add(tab_mesh(name + "_tab"), tp, (0, 0, 0), (1, 1, 1), m_metal, name + "_tab")
    b = tab.modifiers.new("bevel", "BEVEL"); b.width = 0.0022; b.segments = 2; b.limit_method = "ANGLE"
    return tp, fp


def condensation(body, label_mat, density=7000, seed=1, rmin=0.0022, rmax=0.012):
    """Water beads on a cold can: Geometry Nodes - Poisson-disk points on the label faces, a water-bead instance per
    point aligned to the surface normal, radius skewed small (r = rmin + (rmax-rmin) * rand^3), flattened against the
    metal, joined back to the can."""
    drop = bpy.data.objects.get("drop_src")
    if not drop:
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=1, location=(0, 0, -50)); drop = bpy.context.object; drop.name = "drop_src"
        bpy.ops.object.shade_smooth(); drop.hide_render = True; drop.hide_viewport = True
    water = bpy.data.materials.get("water") or clear_liquid("water", (0.97, 0.99, 1.0), 0.02, 1.333, 0.55)
    ng = bpy.data.node_groups.new("condensation", "GeometryNodeTree")
    ng.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    N, L = ng.nodes, ng.links
    gi, go = N.new("NodeGroupInput"), N.new("NodeGroupOutput")
    sel = N.new("GeometryNodeMaterialSelection"); sel.inputs["Material"].default_value = label_mat
    dist = N.new("GeometryNodeDistributePointsOnFaces"); dist.distribute_method = "POISSON"
    if CYCLES: density *= 0.5                                              # real refraction makes each bead read stronger
    dist.inputs["Distance Min"].default_value = rmin * 2.2; dist.inputs["Density Max"].default_value = density; dist.inputs["Seed"].default_value = seed
    L.new(gi.outputs[0], dist.inputs["Mesh"]); L.new(sel.outputs["Selection"], dist.inputs["Selection"])
    oi = N.new("GeometryNodeObjectInfo"); oi.inputs["Object"].default_value = drop
    rnd = N.new("FunctionNodeRandomValue"); rnd.data_type = "FLOAT"; rnd.inputs["Seed"].default_value = seed   # sockets by name: Blender 5 shows only the float ones
    pw = N.new("ShaderNodeMath"); pw.operation = "POWER"; pw.inputs[1].default_value = 3.0
    ma = N.new("ShaderNodeMath"); ma.operation = "MULTIPLY_ADD"; ma.inputs[1].default_value = rmax - rmin; ma.inputs[2].default_value = rmin
    flat = N.new("ShaderNodeMath"); flat.operation = "MULTIPLY"; flat.inputs[1].default_value = 0.55
    comb = N.new("ShaderNodeCombineXYZ")
    L.new([o for o in rnd.outputs if o.enabled and o.type == "VALUE"][0], pw.inputs[0]); L.new(pw.outputs[0], ma.inputs[0])
    L.new(ma.outputs[0], comb.inputs[0]); L.new(ma.outputs[0], comb.inputs[1]); L.new(ma.outputs[0], flat.inputs[0]); L.new(flat.outputs[0], comb.inputs[2])
    inst = N.new("GeometryNodeInstanceOnPoints")
    L.new(dist.outputs["Points"], inst.inputs["Points"]); L.new(oi.outputs["Geometry"], inst.inputs["Instance"])
    L.new(dist.outputs["Rotation"], inst.inputs["Rotation"]); L.new(comb.outputs[0], inst.inputs["Scale"])
    sm = N.new("GeometryNodeSetMaterial"); sm.inputs["Material"].default_value = water; L.new(inst.outputs[0], sm.inputs["Geometry"])
    j = N.new("GeometryNodeJoinGeometry"); L.new(gi.outputs[0], j.inputs[0]); L.new(sm.outputs[0], j.inputs[0]); L.new(j.outputs[0], go.inputs[0])
    mod = body.modifiers.new("condensation", "NODES"); mod.node_group = ng
    return mod


def run_drop(body, f0, f1, z_from=0.45, z_to=-0.25, angle=math.pi):
    """One bead that lets go and runs down the front of the label (local angle pi = the label front)."""
    water = bpy.data.materials.get("water")
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=16, radius=1); d = bpy.context.object; d.name = "run_drop"
    bpy.ops.object.shade_smooth(); d.data.materials.append(water); d.parent = body
    r = 0.33 + 0.004; x, y = r * math.cos(angle), r * math.sin(angle)
    d.rotation_euler = (0, 0, angle)
    for fr, z, sz in ((1, z_from, (0.012, 0.024, 0.016)), (f0, z_from, (0.013, 0.025, 0.017)), (f1, z_to, (0.009, 0.019, 0.03))):
        d.location = (x, y, z); d.scale = sz; d.keyframe_insert("location", frame=fr); d.keyframe_insert("scale", frame=fr)
    return d


def ice_cube(name="ice", size=0.2, seed=0):
    """Ice: a bevelled cube, lumped a little (melted), clear surface with frosted patches, crackle bump and a cloudy core."""
    bpy.ops.mesh.primitive_cube_add(size=size); o = bpy.context.object; o.name = name
    b = o.modifiers.new("bevel", "BEVEL"); b.width = size * 0.16; b.segments = 4
    s = o.modifiers.new("subd", "SUBSURF"); s.levels = 1; s.render_levels = 2
    tx = bpy.data.textures.get("ice_lumps") or bpy.data.textures.new("ice_lumps", "CLOUDS"); tx.noise_scale = 0.08
    d = o.modifiers.new("melt", "DISPLACE"); d.texture = tx; d.strength = size * 0.05; d.texture_coords = "OBJECT"
    bpy.ops.object.shade_smooth()
    m = bpy.data.materials.get("ice")
    if not m and not CYCLES:
        m = clear_liquid("ice", (0.93, 0.97, 1.0), 0.06, 1.31, 0.78, frost=(2.2, 0.35))
    if not m:
        m = _glass(principled("ice", (0.9, 0.96, 1.0), 0.0, 0.05, **{"Transmission Weight": 1.0, "IOR": 1.31}))
        nt = m.node_tree; N = nt.nodes; L = nt.links; bs = N["Principled BSDF"]
        nz = N.new("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 3.0; nz.inputs["Detail"].default_value = 6
        mr = N.new("ShaderNodeMapRange"); mr.inputs["From Min"].default_value = 0.45; mr.inputs["From Max"].default_value = 0.7
        mr.inputs["To Min"].default_value = 0.02; mr.inputs["To Max"].default_value = 0.35            # clear vs frosted patches
        L.new(nz.outputs["Fac"], mr.inputs["Value"]); L.new(mr.outputs["Result"], bs.inputs["Roughness"])
        vo = N.new("ShaderNodeTexVoronoi"); vo.feature = "DISTANCE_TO_EDGE"; vo.inputs["Scale"].default_value = 9
        bump = N.new("ShaderNodeBump"); bump.inputs["Strength"].default_value = 0.18; bump.invert = True
        L.new(vo.outputs["Distance"], bump.inputs["Height"]); L.new(bump.outputs["Normal"], bs.inputs["Normal"])
        vol = N.new("ShaderNodeVolumePrincipled"); vol.inputs["Color"].default_value = (0.95, 0.98, 1, 1)
        tc = N.new("ShaderNodeTexCoord"); mp = N.new("ShaderNodeMapping"); mp.inputs["Scale"].default_value = (2 / size,) * 3
        gr = N.new("ShaderNodeTexGradient"); gr.gradient_type = "SPHERICAL"
        cn = N.new("ShaderNodeMath"); cn.operation = "POWER"; cn.inputs[1].default_value = 2.0
        dn = N.new("ShaderNodeMath"); dn.operation = "MULTIPLY"; dn.inputs[1].default_value = 6.0
        for x, y in ((tc.outputs["Object"], mp.inputs["Vector"]), (mp.outputs["Vector"], gr.inputs["Vector"]), (gr.outputs["Fac"], cn.inputs[0]),
                     (cn.outputs[0], dn.inputs[0]), (dn.outputs[0], vol.inputs["Density"]), (vol.outputs["Volume"], N["Material Output"].inputs["Volume"])):
            L.new(x, y)                                                                              # cloudy core, clear edges
    o.data.materials.append(m)
    return o
