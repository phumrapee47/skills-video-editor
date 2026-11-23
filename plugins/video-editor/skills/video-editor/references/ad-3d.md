# Product ads from product photos: 2.5D and 3D (study of 24 reference ads, 2026-11-22)

Direction set by the user: ads are not cut from footage any more; the user sends product photos and the skill builds a
2.5D or 3D ad (footage-cut ads were judged too plain: simple callouts, music that missed the mood). References: 24
CGI / motion-design product ads by independent 3D artists (Creative Commons BY, YouTube, local study only), measured
with `scripts/study_refs.py` plus a 12-frame strip each.

## The four mood families (decide this FIRST: it drives light, motion, type AND music)
| Family | Picture | Motion | Type | Music (what to ask the library for) | Refs |
|---|---|---|---|---|---|
| **Luxury / premium** | black or deep-colour set, product rim-lit or gold-lit, reflective floor or water, slow particles, smoke | slow orbit (shots 4-20 s), macro glides over the label, slow reveal from darkness, splash in slow motion | thin serif or wide-spaced capitals, gold or white, small, fades; script lines ("Unveil the Essence of Luxury") | slow, deep, cinematic: low pulses, ambient pads, sparse piano, 70-100 BPM; Calming/Mysterious/Epic, never bouncy | perfume x2, tequila, microphone, loafers, massage gun, Nothing phone |
| **Fresh / fun** | saturated flat colour filling the frame (yellow, coral, orange), the flavour around the product (fruit, splashes, ice), many cans | fast: product flies and spins in, cuts on the beat 0.3-1 s, pattern grids of the product, liquid swirls | huge bold or brush-script words, repeated/echoed ("Refreshing Refreshing"), flavour names | upbeat pop/funk/latin, bright, 110-130 BPM, cuts on the beat; Bright/Bouncy/Uplifting | Lipton, OLIPOP, Coca-Cola, soda mock-up, fresh juice |
| **Tech / power** | dark set with neon (green, pink, cyan) rim light, glow lines on the floor, grids | fast cuts, exploded views, light sweeps across edges, glitch transitions | wide techno capitals with glow, feature words with icons ("NEON LEDS", "5 PROGRAMMABLE BUTTONS", "SPEED + PRECISION") | electronic: driving synth, bass hits on the cuts, 120-170 BPM; Driving/Intense/Action | Razer headset, gaming mouse, Nike Air, PC case |
| **Clean / minimal** | white, light grey or pastel, soft shadow, product alone, lots of space | smooth slow turns, parts separating and returning (lid lifts, buds float), colourways lined up | small clean sans, one line ("PURE SOUND", "One bottle. Endless possibilities."), price badges in beauty | light: soft piano, airy electronic, gentle pluck, 80-110 BPM; Calming/Relaxed/Bright | AirPods, smartwatch, thermal bottle, skincare jars, headphones on orange |

Measured pace: two groups. Orbit/hero ads hold shots 4-20 s (smartwatch 14 s, massage gun 20 s, sneaker 14 s);
energetic ads cut every 0.3-1 s (Razer 0.44 s, tequila 0.42 s, mouse 0.44 s, microphone 0.33 s). Loudness -4 to -21
LUFS, most -9 to -15. Beat sync above chance in the fast drink ads (Coca-Cola 0.47 vs 0.39, microphone 0.58 vs 0.42).

## Shape of a product ad (15-45 s)
1. **Reveal** (0-3 s): the product appears out of darkness / flies in / a light sweep finds it; or a teaser of a detail.
2. **Hero turn**: the full product turning slowly, reflected on the floor; the name comes in (often the product name
   or a short claim, rarely more than 3 words at once).
3. **Details**: macro passes over the label, the material, the cap, the buttons; 2-4 feature words, each on its own
   shot, placed in empty space beside the product (not pointing lines: the type sits in the composition).
4. **Flavour / use / world**: the fruit and splashes, the colourways in a row, the product in a scene.
5. **Pack shot + logo**: product centred, name, short line, sometimes price or "available now"; logo end card.

## Craft details the simple version missed (user: "too simple")
- Light does the storytelling: a light sweep (specular band) crossing the product, rim light, a glow that breathes.
- A ground: reflection or soft contact shadow under the product; floating products cast a soft shadow below.
- Depth: foreground elements passing out of focus (fruit, ice, particles, leaves), background bokeh.
- Motion is eased (slow in, slow out) and never stops dead; the camera keeps drifting even on holds.
- Type is part of the picture: sized and placed in negative space, revealed with masks, tracking or blur, not boxes.
- Colour of the set matches the product (yellow set for a yellow can, black/gold for gold perfume).

## Concept first, then realism (v2 lesson, user review of LUMA v1, 2026-11-22)
v1 passed as a first round, but the user set the production bar: "the skill must think up the design itself". A yuzu
drawn as a flat picture is not acceptable when a real yuzu exists; production level means a round fruit with a real peel,
and an idea such as: the fruit is cut through the middle, the can rises out of it, and the juice sprays realistically.

### 1. Find the concept (write it down before building anything)
1. **The product's truth**: what is it made of or what does it do? (yuzu soda -> yuzu fruit and juice; coffee -> beans,
   crema; perfume -> its flower or wood; sneakers -> foam and air; headphones -> sound; skincare -> its drop of serum).
2. **One physical event that turns the truth into the product** - the hook of the ad (first 1-4 s):
   | Concept | Event | Fits |
   |---|---|---|
   | Born from the ingredient | the fruit/bean/flower is cut, cracks or opens; the product rises out of it | drinks, food, beauty |
   | Splash / pour | the liquid hits, crowns, wraps the product in slow motion | drinks, skincare, perfume |
   | Explode and assemble | parts fly apart showing the inside, snap back together | tech, shoes, tools |
   | Freeze moment | time stops mid-burst, the camera travels through the frozen pieces | fresh, sport |
   | Material macro | the camera glides over the real surface (peel pores, leather grain, brushed metal) | luxury, clean |
   | Orbit of ingredients | real ingredients circle the product, each landing on a beat | fresh, food |
3. **Beat board** (5-7 beats): for each beat write the physical event, the camera move and the sound. LUMA v2: whole
   yuzu turns in the light -> light blade slashes (slash) -> halves fly apart, juice sprays, speed ramp to slow motion
   (splash) -> can rises spinning from the middle -> macro on the label -> burst of real wheels and halves with juice
   (splash) -> hero turn (fizz) -> three flavours -> end card.

### 2. Realism checklist for anything that exists in real life
- **Shape**: a real volume, never a card: citrus = slightly lumpy, squashed or stretched sphere with a stem dimple and
  calyx (`ad_fruit.fruit_mesh`); scale may be cheated (a giant fruit around a can) but proportions stay believable.
- **Surface**: micro detail at macro distance: peel pores (Voronoi bump), slow colour drift, waxy coat, light through
  the skin (subsurface).
- **Inside when cut**: what a real cut shows: rind ring, white pith, segments with white membranes, juice vesicles
  stretched along the radius, seeds, wet gloss (`ad_fruit.flesh_maps`, painted with numpy into the cut face).
- **Physics**: liquids spray in strands that thin and break into drops, fall under gravity and vanish at the floor
  (`ad_fruit.splash`, metaball strands keyed per frame); pieces keep drifting after the event (follow-through).
- **Time**: anticipation (slow turn before the cut), the event at real speed for ~5 frames, then a speed ramp into
  slow motion (`ad_fruit.ramp`), the camera never stops.
- **Sound**: every physical event has its sound on the frame it happens (slash, splash, fizz, impact).
- **Check stills** of the key frames before rendering the shot (`--still --frame N`): before, the event, after.

### Pitfalls found building v2
- A generated Blender image blanks its pixels when its colour space is changed afterwards: set the colour space first.
- Vesicle noise in polar coordinates must use the arc inside the segment, not angle x radius (that drew circles).
- Metaball strands need their elements close (lag ~6 ms): at 18 ms they read as a string of beads.
- The two halves must touch exactly before the cut; a gap shows the cut faces as a dark seam on the whole fruit.

## What the product can DO (affordances, v3 - user, 2026-11-22)
The user's second rule: the skill must know what the product itself can do and use it - a can opens, a bag tears open,
a filled bar snapped in half lets its filling stretch out. The product's own action is usually the payoff beat (or the
hook when the ingredient has nothing strong). The catalogue is `assets/ad_concepts.json` (16 product types, 10
ingredient groups; each action with its physics, sound, camera, beat and the shot that builds it, or how to build it);
`scripts/ad_concept.py --product "<what it is>"` turns it into a beat board and marks TO BUILD beats.
- Add a product type or action to the JSON when a brief brings one that is missing; the tests check that every shot
  named there exists in `blender_product_ad.py`.
- A TO BUILD beat is still the concept: build it (the `build` hint says how) or tell the user which beat is missing;
  never silently swap it for a generic turn.
- Built so far: `split` (citrus: slash, halves, juice, the product rises), `burst` (real wheels/halves + juice),
  `open` (can: tab tenses and snaps up, its nose pushes the scored flap in, CO2 mist with wispy noise density rises
  from the hole, a fine spray jumps; sound: fizz on the snap), `reveal` (toss), plus macro/hero/trio.
- Pitfalls: aluminium in a coloured set reflects the set and reads brown - add a white softbox above for metal
  close-ups; a hole disc needs zero specular or it reads grey; a volume needs density fading to its edge (spherical
  gradient) and noise stretched upward, or it renders as a ball.

## v4: the can built to a blueprint, condensation, the guide's shot list, Cycles (user's production guide, 2026-11-23)
The user sent a can blueprint (front/back/top/bottom/3-quarter views) and a production guide (Blender: units, AgX,
HDRI, Eevee for previews and Cycles for the final render, lathe-like can with neck and domed base, lid and pull tab
with its origin on the rivet, Geometry Nodes condensation, a 4-shot list, render to PNG sequence, edit). What the skill
now does with it (`scripts/ad_can.py`):
- **Can = lathe of the real profile** (330 ml: 66 x 115.7 mm, scene unit 100 mm): domed base + stand ring, chime,
  straight wall, necked shoulder, double-seam rim, countersink, flat lid panel. The label covers the printed area
  (6-106 mm, ~207 x 100 mm, i.e. a 2:1 image). `--label-front` = where the logo sits across the label image (a label
  with the logo twice: 0.25); the opening is always above the logo.
- **Lid**: rivet, the stay-on tab (rounded plate with finger hole and rivet hole, scanfill holes, bevel) on a pivot at
  the rivet, the scored opening with its flap on a hinge pivot, the dark hole under it.
- **Condensation** (`--cold`): Geometry Nodes - Poisson disk points on the label faces only (Material Selection),
  a bead per point aligned to the normal (Distribute's Rotation), radius skewed small (rand^3), flattened 0.55 against
  the metal, joined to the can; `run_drop` lets one bead run down.
- **Ice** (`ice_cube`): bevelled, subdivided, lumped by a Clouds displace; clear with white frosted patches.
- **Guide shot list** -> shots: `drops` (Macro, 85 mm rising along the wet label), `toppop` (Top Pop, straight down,
  tab opens), `zerog` (Zero-G, can floats with ice and fruit, 70 mm dolly), `hero_low` (Hero, 85 mm low angle,
  settles with space for the line).
- **Engines**: EEVEE for previews and the normal delivery; `--engine cycles` (GPU, `--device auto` tries CUDA first:
  OptiX kernels fail to load on some drivers; OpenImageDenoise) for the final: ~20 s/frame at 1080x1920,
  128 samples on a laptop RTX 4050, so a 15 s ad is ~2.5 h - offer it as the final pass after the EEVEE cut is approved.
- **Look**: default view stays Khronos PBR Neutral (true label colours); `--view agx` gives the guide's AgX Medium
  High Contrast. Lighting: Blender's bundled `studio.exr` (CC0, no download) for neutral reflections + the set colour
  as warm fill.
- **Edit**: the guide finishes in Blender's VSE; the skill keeps `edit_plan.py` (titles, music, sound design, QA,
  safe zones) - same result, automatic and checked.

Pitfalls found:
- EEVEE refraction of tiny beads/ice picks up the far wall: they render dark or bronze. In EEVEE use the stand-in
  (`clear_liquid`: transparent centre, darker rim by layer weight, Fresnel glossy; white diffuse frost for ice,
  translucent frost took the set colour = dirty ice); Cycles gets real transmission.
- A flat lid seen from straight above mirrors whatever is overhead: a strong softbox burns it white, the warm world
  fill turns it brown. Top view: low side softbox, warm fill off, neutral HDRI.
- Blender 5's Random Value node exposes only the sockets of its type: find sockets by name, not index.
- A shot that forces `--cold` must restore the flag, or every later shot in the same run gets wet.

## 1.10: one shot list, approval gates, music-locked timing (`scripts/ad_pipeline.py`)
Why: a final Cycles render costs hours; the concept, the copy, the timing and the look must be approved before it, in
that order, each on the cheapest thing that shows it.
1. `init <dir> --product ... --label ... [--fruit] [--brief] [--track] [--fps 24]`: the concept (`ad_concept.py`) becomes
   `shots.json`; the music is chosen (mood brief or a track) and its beat grid measured; every shot gets a length in
   whole beats and its physical event (slash, tab snap, burst) an `event_beat`; the music starts on a beat. Claude
   then writes the copy (`title`, one or a list per shot) and adjusts shots, beats, `camera` paths, `cold`.
2. `run` -> **storyboard**: one still per shot at its key frame (432x768, ~15 s for 5 shots) on a sheet with the shot,
   its length in beats, the event, the title and the sounds. Gate: the user approves the concept and copy.
3. `run --approve` -> **animatic**: all shots at 360x640, 4 samples (~2 min for 15 s), cut to the music with titles,
   sound design and each shot's physical sounds, QA. Gate: timing and moves.
4. **preview**: full size EEVEE + QA + safe zones. Gate: the look.
5. **final_test**: one Cycles frame -> time estimate for the whole ad. Gate: the cost. Then **final**: Cycles,
   resumable (frames on disk are skipped: rerun the same command after a stop).
- Never pass `--approve` for the user: each gate is the user's yes (development runs say so when they do).
- Change anything in `shots.json` and rerun `run` (without `--approve`) to redo the current stage; finished frames are
  reused only for shots that did not change (a fingerprint of each shot's spec, size, samples and engine sits in its frame folder).
- Tempo: the library's BPM tag and the measured one agree on half/double-time tracks (Happy Alley: 73.8 BPM, a beat
  0.81 s) - the beat grid is the music's, cuts of 3-5 beats then run 2.4-4 s.
- The final-cost gate renders one Cycles frame per shot at half size (render time measured inside Blender, x4 for
  full size) and puts them on a sheet: the user sees the final look before paying hours for it. It caught that Cycles
  is 0.3-0.6 stops brighter than EEVEE and that its real SSS/transmission turns flesh, juice and beaded labels pale
  and pink. Cycles profile now: `--cycles-exposure -0.8`, flesh SSS 0.1 / coat 0.3, juice transmission 0.35 with
  SSS 0.5, condensation density x0.5. LUMA v5: ~3.3 h for 369 frames on a laptop RTX 4050.

## 1.11: the user's product from photos, more shapes and what they do, the brief
- **Photo -> product** (`scripts/product_from_photo.py front.jpg [--back b.jpg] [--shape]`): cut-out (alpha; plain
  background by colour; busy background with rembg and a model already on disk, never a download) -> shape guess
  (bar / box / bottle / round) -> round products: the radius profile from the silhouette rows, the cap above the neck,
  every row's visible arc unwrapped by asin into one texture with the photo's shading divided out, the back from
  `--back` or each row's own colour -> boxes and pouches: the front picture on the faces -> the studio `set` colours
  from the product's own palette. Check `check.jpg` (outline per row, cap line, texture). Round trip on a rendered
  500 ml bottle: diameter 66.5 vs 66 mm, cap 193.3 vs 193 mm. Shoot straight on, from far, plain background.
- **Shapes** (`scripts/ad_shapes.py`, all scaled to the can's envelope so every camera works): bottle (preset: clear
  PET, liquid to a fill level, label band, knurled cap; or the photo texture), any lathe product, box (front/back
  prints), pillow pouch (swelling sheets, crimped seals), filled bar (two halves with a painted broken face:
  shell, biscuit, caramel; ridges). `hero_obj()` puts the product in every generic shot; a bar is turned so its long
  side faces the lens, tilted and scaled up.
- **What they do** (new shots): `twist` (bottle: the cap turns, lets go, pops up spinning in slow motion, CO2 at the
  neck), `tear` (pouch: the top strip tears from the notch along a jagged line, crisps burst out), `snap` (bar: the
  ends bend down, crumbs fly, the caramel stretches into strands that thin, sag and break into drooping tails).
  Sounds: `twist`, `rip`, `snap`. A shot built for another shape is never offered (`shot_needs` in the catalogue).
- **Brief** (`ad_pipeline.py init <dir> --brief-file brief.json`): product, photo/back or shape, family, length,
  fps, audience, USP, platforms and the approved copy (hook, details, payoff, name, price, cta) -> titles placed by
  beat role in the family's style, shots scaled in whole beats to the length. The storyboard shows every line.
- Pitfalls: old shots assumed the logo faced the lens at 0 deg - every product now shows its front at 90 deg; a bar
  is long - side on, tight on the break, or its ends leave a 9:16 frame and the strands hide behind a half; strands
  need halves that part slowly (11 cm-equivalent) or the filling breaks into beads at once; glossy chocolate mirrors
  a bright floor - keep it satin.

## 1.12: design before building (`scripts/ad_design.py`, `scripts/ad_look.py`)
The user asked whether the skill designs the camera work, transitions, a living background, decoration and motion
before it builds - so that ads are not all filmed the same way. Now a design pass runs before the storyboard and the
storyboard IS the design board (one frame per shot with its move drawn as an icon, transition, background, decor,
motion and the signature move in the header):
- **Camera language** (14 moves: dolly in/out, orbit, spiral, crane down/up, truck, low hero, top-down, macro slide,
  rack focus, dolly zoom, whip-in, push-tilt, or the shot's own staging). Each shot type lists the moves that keep its
  action readable (a snap stays side-on, a top pop stays above). Moves are computed from the shot's own framing (its
  camera and target at frame 1), so they fit every product.
- **Variety rules**: neighbours never share a move or a shot size, a move used before costs more, at least one
  signature move (orbit, spiral, crane down, dolly zoom, whip-in) per ad, the mood family weights the choice;
  `ad_design.py <dir> --variant N` reshuffles inside the rules, `--lock s3_zerog=orbit` keeps a choice.
- **Transitions** by family (fresh: whip blur, white flash, zoom, slide; luxury: dissolve, dip to black, light sweep;
  tech: glitch, whip, slice; clean: dissolve, slide), never over a shot whose event comes in its first 0.4 s; the
  outgoing shot is rendered longer by the overlap, so every shot still starts on its beat; whips and slides get a swish.
- **Living backgrounds**: fresh `gradient_bokeh` (soft light pools drifting across the wall + bokeh discs), luxury
  `haze_glints` (dark glossy floor, a hint of haze, twinkling gold glints), tech `neon_grid` (scrolling grid floor,
  neon strips crossing the wall), clean `window_light` (window-frame shadows sliding across the wall).
- **Decoration in depth**: droplets / gold dust / light specks / soft dust, behind and around the product; only clear
  droplets may come near the lens; nothing glowing in front of the product; fewer when the camera is close.
- **Motion style**: bouncy (overshoot), smooth (sine), snappy (expo) on objects with few keys; the camera eases in and
  out (a whip snaps).
Pitfalls found: glowing specks near the lens become white orbs over the product; huge emissive spheres read as pasted
clouds (light pools painted into the wall material read as light); Blender exits 0 when the script raises - the
pipeline now runs it with `--python-exit-code 1`, or failed renders silently reuse old frames; product paths are
stored absolute (Blender may run from another folder).

## 1.13: light per mood, finishing, materials, loudness
- **Light rigs** (`ad_look.light_rig`): fresh high-key (big soft key + front fill), luxury dark with gold rims set
  behind and a long thin streak light beside the product, tech neon rims (magenta / cyan) on a dark world, clean one
  big soft light from above the front. Tuned against the approved v5 look: brighter rigs washed every colour to pink
  under the neutral view transform.
- **Finishing** (`ad_pipeline.finish_filter`, ffmpeg, the same for EEVEE and Cycles, also applied to the storyboard
  stills): highlight glow, a little lens fringing, vignette, temporal grain, the family's grade. The glow's screen
  blend must run in planar RGB (`format=gbrp`): in YUV it also blends the colour planes and turns orange pink/red
  (a test guards it).
- **Materials**: brushed aluminium (fine stretched-noise bump; anisotropy in Cycles); `--label-metal auto|mask.png`
  makes grey/silver areas of the label bare metal (metallic, smoother); the bar gets V grooves between blocks and an
  embossed brand name per block (made from the product name).
- **Loudness**: music-led plans set `"master": {"glue": true, "limit": 0.56}` - the mix bus is compressed and
  limited before the two-pass loudnorm, then the true-peak limiter catches the rest. A dense track went from
  -16.8 to -15.3 LUFS (true peak -2.9 dBTP); VOLT and MOLTO land at -13.9 / -14.0. Short music-led ads have a low
  LRA (~1 LU) because the music is constant, not because of the glue.
- Tested on all four families: LUMA (fresh), MOLTO (luxury), KAZE (clean), VOLT (tech, new: dark can, silver panels,
  neon grid). Still weak: the bar macro (a blurred dark side), droplets near the lens read as rings in EEVEE.

## 1.14: ads that sell (structure, voice, brand, ABCD, hook variants)
Research (platform guides and production practice, see the 1.14 notes in the session): beautiful CGI is not enough -
YouTube's ABCD (Attract, Brand, Connect, Direct; Google/Kantar, 11,000 ads), TikTok's guide (the proposition in the
first 3 s, the hook within 6 s, captions, short text) and direct-response practice (hook -> benefit -> demo -> proof
-> offer -> call to action; test several openings of one ad).
- **Structure** (`brief.structure`): `brand` (hook, details, payoff, name + price) or `performance` (hook, benefit,
  proof, demo on the product's own action, then name + offer + a call to action already on the hero shot, which gets
  two extra beats; the card repeats the call to action). Copy keys: hook, benefit, details, proof, demo, name, offer
  / price, cta, cta_mid, callouts, hooks.
- **Voiceover** (`brief.vo`: lines per role + voice, or true for lines from the copy): edge-tts (free, online; Thai
  `th-TH-PremwadeeNeural`, English `en-US-AndrewNeural`), placed on its role's shot, the brand name said in the first
  line, the music ducks 9 dB under it; broken TTS files are retried. Paths are absolute (a relative path silenced the
  whole mix: no voice found -> reference level 0).
- **Sonic logo** (`make_sfx.sonic_logo`): three notes + a held chord from the brand name, timbre by mood family, on
  the end card instead of the chime. **Brand kit** (`brief.brand`): fonts, accent, corner logo, the logo large on the
  card.
- **Callouts on the product** (`copy.callouts`): Blender writes where the product is on screen per shot
  (`<shot>_anchors.json`: label, top, left, right); the callouts go to the shot with the most room beside the settled
  product, on the roomier side, stopping at the apps' button column - none rather than squeezed ones (a 9:16 hero
  often fills the width).
- **ABCD check** (printed at the storyboard and preview gates, kept in shots.json): product on screen by 3 s, hook by
  3 s, brand seen by 5 s, brand said by 5 s, calls to action (card + before it for performance), benefit and proof on
  screen, readable text (<= 8 words, <= 4 words/s), works muted, length, voiceover fits.
- **Hook variants** (`ad_pipeline.py variants <dir> --n 3 [--source animatic]`): the opening shot re-shot with
  another camera move and `copy.hooks` lines; the rest of the ad is shared (only the first shot renders again).
