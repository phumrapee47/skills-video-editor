"""Liquids that behave like the real thing (references/ad-craft.md section 5), built with Geometry Nodes so they move
by themselves with the scene clock:

stream(curve_obj, mat, r0)   a pour: the path stays the keyed curve (a ballistic arc from the opening); the body is
                             swept along it - wide and flat at the lip (a sheet), thinning as it speeds up (continuity:
                             area ~ 1/velocity), an elliptical section that twists, ripples running down it that grow
                             with the fall (Rayleigh-Plateau), and the last part broken into a line of drops. A "Grow"
                             input trims it while it first reaches down.
surface(name, r, mat, ...)   the top of a drink being poured into: a disc on the level with a dip where the stream
                             lands, rings spreading from it, choppy turbulence, a slow slosh across the glass, and an
                             aerated white patch at the impact (attribute "aer" for the material). A "Pour" input sets
                             how hard it churns; it calms when the pour stops.
"""
import math
import bpy

TAU = 2 * math.pi


def key_input(mod, ident, value, frame):
    """Set and keyframe a Geometry Nodes modifier input: Blender 5 (mod.properties.inputs.<id>.value) or older
    (mod["<id>"])."""
    props = getattr(mod, "properties", None)
    if props is not None and hasattr(getattr(props, "inputs", None), ident):
        x = getattr(props.inputs, ident); x.value = value; x.keyframe_insert("value", frame=frame)
    else:
        mod[ident] = value; mod.keyframe_insert(f'["{ident}"]', frame=frame)


class _G:
    """A small helper to build node groups readably."""
    def __init__(self, name):
        self.ng = bpy.data.node_groups.new(name, "GeometryNodeTree"); self.N = self.ng.nodes; self.L = self.ng.links
        self.ng.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
        self.ng.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
        self.gi = self.N.new("NodeGroupInput"); self.go = self.N.new("NodeGroupOutput")

    def input(self, name, default, lo=0.0, hi=1.0):
        s = self.ng.interface.new_socket(name=name, in_out="INPUT", socket_type="NodeSocketFloat"); s.default_value = default
        s.min_value, s.max_value = lo, hi; return self.gi.outputs[name], s.identifier

    def node(self, kind, **props):
        n = self.N.new(kind)
        for k, v in props.items(): setattr(n, k, v)
        return n

    def link(self, a, b): self.L.new(a, b)

    def math(self, op, a, b=None, c=None):
        n = self.node("ShaderNodeMath", operation=op)
        for i, x in enumerate((a, b, c)):
            if x is None: continue
            if isinstance(x, (int, float)): n.inputs[i].default_value = x
            else: self.link(x, n.inputs[i])
        return n.outputs[0]

    def vmath(self, op, a, b=None, scale=None):
        n = self.node("ShaderNodeVectorMath", operation=op)
        for i, x in enumerate((a, b)):
            if x is None: continue
            if isinstance(x, (tuple, list)): n.inputs[i].default_value = x
            else: self.link(x, n.inputs[i])
        if scale is not None:
            if isinstance(scale, (int, float)): n.inputs["Scale"].default_value = scale
            else: self.link(scale, n.inputs["Scale"])
        return n.outputs["Value"] if op in ("LENGTH", "DOT_PRODUCT", "DISTANCE") else n.outputs["Vector"]

    def combine(self, x, y, z):
        n = self.node("ShaderNodeCombineXYZ")
        for i, v in enumerate((x, y, z)):
            if isinstance(v, (int, float)): n.inputs[i].default_value = v
            else: self.link(v, n.inputs[i])
        return n.outputs[0]


def stream(cu_obj, mat, r0=0.03, drops_from=0.84, seed=3):
    """Geometry Nodes on the stream curve object (its own bevel switched off). Returns (modifier, grow input id)."""
    cu_obj.data.bevel_depth = 0.0
    g = _G("stream_fx"); grow, grow_id = g.input("Grow", 1.0)
    rs = g.node("GeometryNodeResampleCurve"); rs.inputs["Count"].default_value = 90; g.link(g.gi.outputs["Geometry"], rs.inputs["Curve"])
    tr = g.node("GeometryNodeTrimCurve"); tr.mode = "FACTOR"; g.link(rs.outputs[0], tr.inputs["Curve"]); g.link(grow, tr.inputs["End"])
    sp = g.node("GeometryNodeSplineParameter").outputs["Factor"]; t = g.node("GeometryNodeInputSceneTime").outputs["Seconds"]
    # radius: sheet at the lip, thinning with speed, travelling ripples that grow downstream
    thin = g.math("POWER", g.math("MULTIPLY_ADD", sp, 3.0, 1.0), -0.5)
    sheet = g.math("MULTIPLY_ADD", g.math("POWER", g.math("SUBTRACT", 1.0, sp), 6.0), 1.4, 1.0)
    amp = g.math("MULTIPLY_ADD", g.math("POWER", sp, 1.5), 0.32, 0.07)
    wave = g.math("SINE", g.math("MULTIPLY", g.math("SUBTRACT", g.math("MULTIPLY", sp, 7.0), g.math("MULTIPLY", t, 3.4)), TAU))
    wave2 = g.math("SINE", g.math("MULTIPLY", g.math("SUBTRACT", g.math("MULTIPLY", sp, 17.0), g.math("MULTIPLY", t, 6.1)), TAU))
    rip = g.math("MULTIPLY_ADD", g.math("MULTIPLY_ADD", wave2, 0.35, wave), amp, 1.0)
    radius = g.math("MULTIPLY", g.math("MULTIPLY", g.math("MULTIPLY", thin, sheet), rip), r0)
    tilt = g.node("GeometryNodeSetCurveTilt"); g.link(tr.outputs[0], tilt.inputs["Curve"])
    g.link(g.math("MULTIPLY_ADD", sp, 7.5, g.math("MULTIPLY", t, 2.2)), tilt.inputs["Tilt"])   # the section twists along the fall
    # body (up to drops_from) and the broken end (drops)
    sel = g.math("GREATER_THAN", sp, drops_from)
    sep = g.node("GeometryNodeSeparateGeometry"); sep.domain = "POINT"; g.link(tilt.outputs[0], sep.inputs["Geometry"]); g.link(sel, sep.inputs["Selection"])
    prof = g.node("GeometryNodeCurvePrimitiveCircle"); prof.inputs["Resolution"].default_value = 14; prof.inputs["Radius"].default_value = 1.0
    ell = g.node("GeometryNodeTransform"); ell.inputs["Scale"].default_value = (1.0, 0.62, 1.0); g.link(prof.outputs["Curve"], ell.inputs["Geometry"])
    c2m = g.node("GeometryNodeCurveToMesh"); c2m.inputs["Fill Caps"].default_value = True
    g.link(sep.outputs["Inverted"], c2m.inputs["Curve"]); g.link(ell.outputs[0], c2m.inputs["Profile Curve"]); g.link(radius, c2m.inputs["Scale"])
    c2p = g.node("GeometryNodeCurveToPoints"); c2p.mode = "COUNT"; c2p.inputs["Count"].default_value = 9; g.link(sep.outputs["Selection"], c2p.inputs["Curve"])
    rnd = g.node("FunctionNodeRandomValue"); rnd.data_type = "FLOAT"; rnd.inputs["Seed"].default_value = seed
    for nm, v in (("Min", 0.45), ("Max", 1.05)):                           # the float Min/Max (Blender 5: look up by name and type)
        next(i for i in rnd.inputs if i.name == nm and i.type == "VALUE").default_value = v
    jit = g.node("ShaderNodeTexNoise"); jit.inputs["Scale"].default_value = 30.0
    pos = g.node("GeometryNodeInputPosition").outputs[0]
    g.link(g.vmath("ADD", pos, g.combine(0, 0, g.math("MULTIPLY", t, 1.5))), jit.inputs["Vector"])
    off = g.vmath("SCALE", g.vmath("SUBTRACT", jit.outputs["Color"], (0.5, 0.5, 0.5)), scale=r0 * 0.8)
    sp_d = g.node("GeometryNodeSetPosition"); g.link(c2p.outputs["Points"], sp_d.inputs["Geometry"]); g.link(off, sp_d.inputs["Offset"])
    ico = g.node("GeometryNodeMeshIcoSphere"); ico.inputs["Radius"].default_value = r0 * 0.75; ico.inputs["Subdivisions"].default_value = 2
    iop = g.node("GeometryNodeInstanceOnPoints"); g.link(sp_d.outputs[0], iop.inputs["Points"]); g.link(ico.outputs["Mesh"], iop.inputs["Instance"])
    g.link([o for o in rnd.outputs if o.enabled and o.type == "VALUE"][0], iop.inputs["Scale"])
    real = g.node("GeometryNodeRealizeInstances"); g.link(iop.outputs[0], real.inputs[0])
    sm = g.node("GeometryNodeSetShadeSmooth"); g.link(c2m.outputs[0], sm.inputs["Geometry"])
    join = g.node("GeometryNodeJoinGeometry"); g.link(real.outputs[0], join.inputs[0]); g.link(sm.outputs[0], join.inputs[0])
    smat = g.node("GeometryNodeSetMaterial"); smat.inputs["Material"].default_value = mat; g.link(join.outputs[0], smat.inputs["Geometry"])
    g.link(smat.outputs[0], g.go.inputs["Geometry"])
    mod = cu_obj.modifiers.new("stream_fx", "NODES"); mod.node_group = g.ng
    return mod, grow_id


def surface(name, r, mat, impact=(0.0, 0.0), parent=None, res=72):
    """A churning liquid top of radius r (local, z = 0 at the level). Returns (object, modifier, pour input id)."""
    me = bpy.data.meshes.new(name); ob = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(ob)
    if parent: ob.parent = parent
    me.materials.append(mat)
    g = _G(name + "_fx"); pour, pour_id = g.input("Pour", 1.0)
    grid = g.node("GeometryNodeMeshGrid"); grid.inputs["Size X"].default_value = 2 * r; grid.inputs["Size Y"].default_value = 2 * r
    grid.inputs["Vertices X"].default_value = res; grid.inputs["Vertices Y"].default_value = res
    pos = g.node("GeometryNodeInputPosition").outputs[0]
    dc = g.vmath("LENGTH", g.vmath("MULTIPLY", pos, (1, 1, 0)))
    dele = g.node("GeometryNodeDeleteGeometry"); dele.domain = "POINT"; g.link(grid.outputs["Mesh"], dele.inputs["Geometry"])
    g.link(g.math("GREATER_THAN", dc, r * 1.001), dele.inputs["Selection"])
    t = g.node("GeometryNodeInputSceneTime").outputs["Seconds"]
    d = g.vmath("LENGTH", g.vmath("SUBTRACT", g.vmath("MULTIPLY", pos, (1, 1, 0)), (impact[0], impact[1], 0)))
    crater = g.math("MULTIPLY", g.math("EXPONENT", g.math("MULTIPLY", g.math("POWER", g.math("DIVIDE", d, r * 0.25), 2.0), -1.0)), -r * 0.28)
    ring = g.math("MULTIPLY", g.math("SINE", g.math("SUBTRACT", g.math("MULTIPLY", d, 80.0 / r * 0.25), g.math("MULTIPLY", t, 14.0))),
                  g.math("MULTIPLY", g.math("EXPONENT", g.math("MULTIPLY", d, -2.6 / r)), r * 0.075))
    nz = g.node("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 3.0 / r * 0.4; nz.inputs["Detail"].default_value = 4
    g.link(g.vmath("ADD", pos, g.combine(0, 0, g.math("MULTIPLY", t, 1.8))), nz.inputs["Vector"])
    chop = g.math("MULTIPLY", g.math("SUBTRACT", nz.outputs["Fac"], 0.5), r * 0.18)
    sep = g.node("ShaderNodeSeparateXYZ"); g.link(pos, sep.inputs[0])
    slosh = g.math("MULTIPLY", g.math("ADD", g.math("MULTIPLY", sep.outputs["X"], g.math("COSINE", g.math("MULTIPLY", t, 4.2))),
                                       g.math("MULTIPLY", sep.outputs["Y"], g.math("SINE", g.math("MULTIPLY", t, 3.1)))), 0.07)
    edge = g.math("SUBTRACT", 1.0, g.math("POWER", g.math("DIVIDE", dc, r), 4.0))                     # pinned at the glass
    churn = g.math("MULTIPLY", g.math("ADD", g.math("ADD", crater, ring), chop), pour)
    z = g.math("MULTIPLY", g.math("ADD", churn, g.math("MULTIPLY", slosh, g.math("MULTIPLY_ADD", pour, 0.7, 0.3))), edge)
    setp = g.node("GeometryNodeSetPosition"); g.link(dele.outputs[0], setp.inputs["Geometry"]); g.link(g.combine(0, 0, z), setp.inputs["Offset"])
    aer = g.math("MULTIPLY", g.math("EXPONENT", g.math("MULTIPLY", g.math("POWER", g.math("DIVIDE", d, r * 0.38), 2.0), -1.0)), pour)
    st = g.node("GeometryNodeStoreNamedAttribute"); st.data_type = "FLOAT"; st.domain = "POINT"; st.inputs["Name"].default_value = "aer"
    g.link(setp.outputs[0], st.inputs["Geometry"]); g.link(aer, st.inputs["Value"])
    sm = g.node("GeometryNodeSetShadeSmooth"); g.link(st.outputs[0], sm.inputs["Geometry"])
    smat = g.node("GeometryNodeSetMaterial"); smat.inputs["Material"].default_value = mat; g.link(sm.outputs[0], smat.inputs["Geometry"])
    g.link(smat.outputs[0], g.go.inputs["Geometry"])
    mod = ob.modifiers.new(name + "_fx", "NODES"); mod.node_group = g.ng
    return ob, mod, pour_id


def aerated(mat, white=(0.95, 0.94, 0.9)):
    """A churned liquid top: fine moving ripples everywhere (bump), and where the surface is aerated (attribute "aer")
    a froth of small bubbles - whiter, rougher - rather than a flat white tint."""
    N = mat.node_tree.nodes; L = mat.node_tree.links; b = next(n for n in N if n.type == "BSDF_PRINCIPLED")
    at = N.new("ShaderNodeAttribute"); at.attribute_name = "aer"
    tc = N.new("ShaderNodeTexCoord"); vo = N.new("ShaderNodeTexVoronoi"); vo.inputs["Scale"].default_value = 140.0
    vo.feature = "F1"; L.new(tc.outputs["Object"], vo.inputs["Vector"])
    cells = N.new("ShaderNodeMapRange"); cells.inputs["From Min"].default_value = 0.08; cells.inputs["From Max"].default_value = 0.4
    cells.inputs["To Min"].default_value = 1.0; cells.inputs["To Max"].default_value = 0.35; L.new(vo.outputs["Distance"], cells.inputs["Value"])
    froth = N.new("ShaderNodeMath"); froth.operation = "MULTIPLY"; L.new(at.outputs["Fac"], froth.inputs[0]); L.new(cells.outputs["Result"], froth.inputs[1])
    base = b.inputs["Base Color"]; src = base.links[0].from_socket if base.is_linked else None
    mix = N.new("ShaderNodeMix"); mix.data_type = "RGBA"; mix.inputs["B"].default_value = (*white, 1)
    if src: L.new(src, mix.inputs["A"])
    else: mix.inputs["A"].default_value = base.default_value
    L.new(froth.outputs[0], mix.inputs["Factor"]); L.new(mix.outputs["Result"], base)
    rr = N.new("ShaderNodeMapRange"); rr.inputs["To Min"].default_value = b.inputs["Roughness"].default_value; rr.inputs["To Max"].default_value = 0.55
    L.new(froth.outputs[0], rr.inputs["Value"]); L.new(rr.outputs["Result"], b.inputs["Roughness"])
    nz = N.new("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 60.0; nz.inputs["Detail"].default_value = 3
    L.new(tc.outputs["Object"], nz.inputs["Vector"])
    bump = N.new("ShaderNodeBump"); bump.inputs["Strength"].default_value = 0.25; bump.inputs["Distance"].default_value = 0.004
    L.new(nz.outputs["Fac"], bump.inputs["Height"]); L.new(bump.outputs["Normal"], b.inputs["Normal"])
    if "Coat Normal" in b.inputs: L.new(bump.outputs["Normal"], b.inputs["Coat Normal"])
    return mat


def flip_pour(glass, mouth_at, target, F, n, mat, res=110, cache_dir=None, radius=0.05, g=9.81, fill_speed=0.25):
    """A real (simulated) pour for final renders: a Mantaflow FLIP domain round the opening and the glass, a liquid
    inflow that follows the opening every 2 frames with a velocity that carries it into the glass, the glass as a
    collision effector; baked here (headless), the domain's liquid mesh rendered with the drink material. The stream
    breaks, splashes, fills and sloshes by itself. mouth_at(frame) -> (point, direction)."""
    import os, tempfile
    from mathutils import Vector
    sc = bpy.context.scene; sc.frame_set(F); P0, _ = mouth_at(F)
    kids = [o for o in [glass] + list(glass.children_recursive) if o.type == "MESH" and o.name.endswith(("_glass", "_handle"))]   # the vessel, not its drink
    pts = [o.matrix_world @ Vector(c) for o in kids for c in o.bound_box]
    for fr in range(F, n + 1, 6): sc.frame_set(fr); pts.append(mouth_at(fr)[0])
    sc.frame_set(F)
    lo = Vector((min(p.x for p in pts) - 0.12, min(p.y for p in pts) - 0.12, max(0.0, min(p.z for p in pts) - 0.02)))
    hi = Vector((max(p.x for p in pts) + 0.12, max(p.y for p in pts) + 0.12, max(p.z for p in pts) + 0.12))
    bpy.ops.mesh.primitive_cube_add(size=1, location=(lo + hi) / 2); dom = bpy.context.object; dom.name = "flip_domain"; dom.scale = hi - lo
    m = dom.modifiers.new("fluid", "FLUID"); m.fluid_type = "DOMAIN"; ds = m.domain_settings
    ds.domain_type = "LIQUID"; ds.resolution_max = res; ds.use_mesh = True; ds.mesh_scale = 2; ds.use_flip_particles = False
    ds.cache_type = "ALL"; ds.cache_frame_start = max(1, F - 2); ds.cache_frame_end = n
    ds.cache_directory = cache_dir or os.path.join(tempfile.gettempdir(), "ve_flip"); ds.time_scale = 0.8
    try: ds.mesh_smoothen_pos = 2; ds.mesh_smoothen_neg = 1
    except Exception: pass
    dom.data.materials.append(mat)
    for o in kids:                                                         # the glass: the liquid stays inside it
        e = o.modifiers.new("fluid", "FLUID"); e.fluid_type = "EFFECTOR"; e.effector_settings.effector_type = "COLLISION"
        try: e.effector_settings.surface_distance = max(0.012, 1.2 * max(hi - lo) / res)   # a glass wall is thinner than a cell: thicken it
        except Exception: pass
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, segments=16, ring_count=8, location=P0); fl = bpy.context.object; fl.name = "flip_inflow"
    fm = fl.modifiers.new("fluid", "FLUID"); fm.fluid_type = "FLOW"; fs = fm.flow_settings
    fs.flow_type = "LIQUID"; fs.flow_behavior = "INFLOW"; fs.flow_source = "MESH"; fs.use_initial_velocity = True; fl.hide_render = True
    # aim: the stream must clear the near rim, so it crosses rim height a little inside it (the real arc from an opening
    # beside the glass); the target given is only a fallback when the opening is already over the glass
    G0 = kids[0].matrix_world.translation; Rg = max(max(abs(v.co.x), abs(v.co.y)) for v in kids[0].data.vertices) * kids[0].matrix_world.to_scale().x
    rim = max((kids[0].matrix_world @ v.co).z for v in kids[0].data.vertices)
    for fr in list(range(max(1, F - 2), n + 1, 2)) + [n]:
        sc.frame_set(fr); P, _ = mouth_at(fr); off = P.xy - G0.xy
        if off.length > Rg * 0.5: aim = G0.xy + off.normalized() * Rg * 0.2; target = Vector((aim.x, aim.y, rim + 0.04))
        dz = max(0.05, P.z - target.z); T = math.sqrt(2 * dz / g)
        fl.location = P; fl.keyframe_insert("location", frame=fr)
        fs.velocity_coord = ((target.x - P.x) / T, (target.y - P.y) / T, 0.0); fs.keyframe_insert("velocity_coord", frame=fr)
        fs.use_inflow = fr >= F; fs.keyframe_insert("use_inflow", frame=fr)
    # the level has to rise in the shot's time, a stream of the true thickness would take far longer: a hidden, slow inflow
    # on the glass floor tops it up (the usual liquid-shot trick) while the stream keeps the surface churning
    base = min((kids[0].matrix_world @ v.co).z for v in kids[0].data.vertices if (v.co.xy).length < Rg * 0.3)
    floor_z = max((kids[0].matrix_world @ v.co).z for v in kids[0].data.vertices if (v.co.xy).length < Rg * 0.3 and (kids[0].matrix_world @ v.co).z < base + 0.2)
    bpy.ops.mesh.primitive_cylinder_add(radius=Rg * 0.55, depth=0.03, vertices=24, location=(G0.x, G0.y, floor_z + 0.1)); bo = bpy.context.object; bo.name = "flip_fill"
    bm_ = bo.modifiers.new("fluid", "FLUID"); bm_.fluid_type = "FLOW"; bf = bm_.flow_settings; bo.hide_render = True
    bf.flow_type = "LIQUID"; bf.flow_behavior = "INFLOW"; bf.flow_source = "MESH"; bf.use_initial_velocity = True; bf.velocity_coord = (0, 0, fill_speed)
    for fr, on in ((1, False), (F + 8, True), (int(F + (n - F) * 0.85), False)): bf.use_inflow = on; bf.keyframe_insert("use_inflow", frame=fr)
    sc.frame_end = max(sc.frame_end, n)
    with bpy.context.temp_override(active_object=dom, object=dom, selected_objects=[dom]):
        bpy.ops.fluid.bake_all()
    g0, rg = G0, Rg
    for fr in (F + (n - F) // 2, n):                                       # QA: how much of the liquid is inside the glass
        sc.frame_set(fr); me = dom.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh()
        V = [dom.matrix_world @ v.co for v in me.vertices]; ins = sorted(v.z for v in V if (v.xy - g0.xy).length < rg and v.z < rim)
        lv = (ins[int(len(ins) * 0.8)] - floor_z) / max(1e-6, rim - floor_z) if ins else 0.0
        print(f"FLIP frame {fr}: {len(V)} verts, {100 * len(ins) / max(1, len(V)):.0f}% in the glass, level {100 * lv:.0f}% of the glass")
        dom.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh_clear()
    return dom
