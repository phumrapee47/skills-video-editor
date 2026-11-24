# Ad craft: what makes a 3D product ad look expensive (study, 2026-11-23)

Why this file: the user judged two parts of the skill "too easy" - the fruit cut (a flat glowing bar through the
fruit) and the callouts (tiny spaced caps, a dot and a straight line). They sent reference work from Thai 3D product
studios (Fastwork listings: frappe mugs with whipped cream, chocolate drip, floating hearts, a coffee crown splash
round a jar; a perfume packshot tilted on a rippled water surface). Below: what those references do, what the craft
literature says, and what the skill must do. Statuses: DONE / PARTIAL / TODO.

## 1. Breakdown of the references
**Frappe mugs (playful / fresh family)**
- Set: a seamless pastel gradient (no floor line, no wall corner), the palette taken from the product (pink straw,
  pink hearts, lilac backdrop). Soft top-left key, big soft shadow under the mug, rim highlights on the glass edge.
- Food styling does the selling: piped whipped cream with ridges, a glossy chocolate drip running over the rim in thick
  tongues, sprinkles on the cream, a bent striped straw. Every element has its own material (cream: soft SSS, matte;
  chocolate: dark glossy, thick; glass: double wall, condensation beads only where the cold drink touches).
- Props tell the mood: floating hearts in two sizes, some in front out of focus, some behind; nothing random.
- Callout: a hand-drawn curved arrow and handwritten text ("put your logo here") - friendly, part of the art.
- Splash variants: coffee or chocolate erupting in a crown round a jar, ice cubes and pearls flying, the splash
  framing the product rather than hiding it; thick, glossy liquid with sheets and droplets, not beads.

**Perfume on water (luxury / clean family)**
- One idea, nothing else: a heavy glass bottle tilted on a still water surface; ripple rings spread from the contact
  point; a mirror reflection broken by the ripples; a horizon that fades into soft haze.
- Low camera near the water level, cool lilac-blue palette, very soft high-key light, negative space above.
- The glass is thick: refraction bends the background through the walls; highlights are long and soft (strip lights).

## 2. What the craft sources agree on
- **Imperfection**: perfect surfaces read as CGI - fingerprints and smudges on gloss, edge wear, dust in crevices,
  roughness variation, micro bevels on every "sharp" edge ([Will Gibbons](https://www.willgibbons.com/realistic-rendering/),
  [why CGI ads look fake](https://dev.to/maverickframe/why-cgi-ads-look-fake-a-practical-quality-checklist-for-brands-3iol),
  [soona](https://support.soona.co/why-does-the-image-look-fake-3d-rendered)).
- **One photograph**: product, light direction, shadows, perspective and scale must belong to one camera and one light
  setup; a missing contact shadow makes a product float; wrong scale (a bottle as tall as a sink) breaks it
  ([Photoroom](https://www.photoroom.com/blog/how-to-make-ai-product-images-look-real-for-e-commerce)).
- **Light**: few lights, each with one job; a directed rim + dark background + controlled catch-lights for premium;
  long strip lights for long soft highlights on glass and metal; real light sources are not perfectly flat
  ([XO3D lighting guide](https://xo3d.co.uk/resources/3d-rendering/product-rendering/lighting-guide/),
  [Lightmap](https://lightmap.co.uk/learning/5-tips-for-better-studio-lighting)).
- **Glass and drinks**: refraction through every condensation bead; beads only where the cold liquid touches the
  glass; liquid geometry slightly overlapping the inner wall; caustics in Cycles (reflective + refractive caustics on,
  Filter Glossy 0) or faked with a projected caustic texture
  ([KeyShot condensation](https://www.keyshot.com/blog/how-to-create-water-droplets-and-condensation-in-keyshot/),
  [Onshape liquid in glass](https://www.onshape.com/en/resource-center/tech-tips/rendering-liquid-glass-render-studio),
  [perfume caustics thread](https://blenderartists.org/t/perfume-bokeh-caustics/1493699)).
- **Splashes**: studios simulate (Houdini FLIP crown splash: lowered gravity for slow motion, surface tension on for
  the crown, whitewater for spray) or build them procedurally (Geometry Nodes splash generators: size, shape, droplet
  count controllable); still photographers composite splash and product
  ([SideFX crown splash](https://www.sidefx.com/docs/houdini/shelf/crownsplash.html),
  [GN splash setup](https://80.lv/articles/a-customizable-water-splash-setup-made-with-geometry-nodes),
  [MIOPS](https://www.miops.com/blogs/news/high-speed-product-photography-how-to-capture-splashes-pours-and-liquid-that-sells)).
- **Trends**: clean pastel or gradient backdrops (mesh gradients over flat ones), exaggerated props (floating fruit,
  crushed cans), water droplets for minimal looks; the purple-pink neon gradient is overused
  ([Omi beauty trends](https://omi.so/resources/blog/visual-style-trends-in-beauty-cosmetics-visuals),
  [Kittl](https://www.kittl.com/get-started/trends2027), [Adobe](https://www.adobe.com/express/learn/blog/microtrend-digital-real)).
- **Callouts**: motion graphics must not overpower the product; elements are revealed one by one with care; good
  callout packs are clean lines with restrained type, pointing at a real feature
  ([PremiumBeat](https://www.premiumbeat.com/blog/animate-commercial-graphics-after-effects/)).

## 3. Why the skill's cut and callouts look cheap - and the fix
**The cut** (now: an emissive white bar sweeps down, the halves pop apart)
- Real cuts show the cutter or its trace: a thin metal blade with a moving reflection, or a seam of light that runs
  ON the fruit surface along the cut path (a curve that follows the curvature), and motion blur / a smear on the frame
  of the cut. DONE 1.15: steel blade (motion-blurred) + a seam curve on the real rim.
- The fruit reacts: beads of juice appear along the seam a few frames before it opens, the halves tip and wobble,
  juice stretches in thin sheets between the faces before tearing into droplets, a fine mist and pulp bits fly.
  DONE 1.15: beads on the seam, hooked juice films that tear, mist, pulp, wobble; droplets (metaball strands).
- The camera feels the hit: a 2-4 frame shake and a speed ramp into slow motion. DONE 1.15 (speed ramp + `ad_look.shake`).

**The callouts** (now: spaced caps, dot, straight line, stuck at an edge)
- They point at a real feature (the logo, the fruit pieces, the cap, the "zero sugar" line), not at the bounding box
  edge. DONE 1.16: feature tracks (logo, detail, top, base) ray-cast on the product, projected every 2nd frame.
- They are designed per mood: fresh/playful = hand-drawn curved arrow drawn on + handwritten text; luxury = hairline
  elbow leader, small serif caps, a ring marker, a slow wipe reveal; tech = elbow leader with corner brackets and a
  glow, a scan line; clean = a dot and a short line, gentle fade. TODO: callout style kit; needs a handwriting font
  with Thai (OFL, e.g. Mali or Itim from Google Fonts - ask before downloading). DONE 1.16: `callouts.py` looks dot,
  hairline, tech, hand; Mali SemiBold bundled (the user approved the download).
- They animate in order: marker, line draws, text reveals; they leave before the next beat. DONE 1.16.

## 4. Other gaps the references expose
| Craft point | Skill now | To do |
|---|---|---|
| Seamless backdrop | DONE 1.15: cyclorama, floor-to-wall gradient | mesh gradients (several colour points) |
| Contact shadow | DONE 1.15: `contact_shadow` follows the product's height | - |
| Imperfection | DONE 1.17: `imperfect` - uneven roughness + smudges on gloss | edge wear, micro bevels |
| Textured light | PARTIAL 1.17: strip lights (fresh, clean), luxury streak | gradient textures on softboxes |
| Prop kits | DONE 1.17: hearts, beans, leaves, pearls, sprinkles in depth layers, palette-matched | flowers |
| Food styling | DONE 1.17: piped cream swirl, sauce over the rim + drizzle, sprinkles (`ad_drink.py`) | - |
| Glass drinks | DONE 1.17: mug/cup/tall, layered drink, beads only below the drink line, straw | caustics (Cycles) |
| Crown splash | DONE 1.15: `crown` shot (procedural crown, pool with ripples, drops) | Mantaflow/FLIP for finals |
| Water set | DONE 1.17: `water` background - still dark mirror, ripple rings, haze horizon | - |
| Reference match | DONE 1.17: `ref_style.py` - palette, set, accent, light side, mood family | props from the picture |
