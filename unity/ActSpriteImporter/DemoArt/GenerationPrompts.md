# Generated dungeon art prompts

Both images were made with the built-in image generator. `KnightSheet.png` was supplied only as a visual style reference. It was not edited or included as a subject.

## DungeonWall.png

```text
Use case: stylized-concept
Asset type: seamless repeating 2D side-scroller game background tile
Primary request: Create a horizontally seamless dungeon wall backdrop tile that can repeat indefinitely left-to-right behind a small knight character in a 2D platformer.
Input images: Image 1 is a style reference only: a transparent pixel-art knight sprite sheet. Match its coarse pixel clusters and muted medieval palette, especially pale blue-gray steel, charcoal outlines, muted cobalt cloth, brown leather, and small restrained crimson accents; do not include the knight.
Scene/backdrop: An old underground stone dungeon wall, cool blue-gray slate masonry, occasional shallow arch stones and restrained iron details, a few dim warm torch niches at mid-height, subtle depth without foreground props. Keep a broad calm middle area behind the playable knight.
Style/medium: crisp hand-authored pixel art, chunky readable clusters, limited palette and hard pixel edges, no antialiasing, consistent with a classic 16-bit side-scroller sprite.
Composition/framing: Flat side-on orthographic wall layer, full-bleed tile with the left and right edges exactly matching for seamless horizontal repetition; evenly distribute small masonry variation so no single landmark draws the eye at a seam; keep top and bottom edges visually continuous too. No perspective.
Lighting/mood: dim, cool and readable, with soft restrained amber torch glow.
Materials/textures: chipped stone blocks, dark mortar, subtle pixel clusters and sparse wear.
Constraints: no characters, no floor, no foreground silhouette, no text, no UI, no frame, no border, no watermark. The image must be a single usable game background tile, with continuous horizontal edges suitable for texture repeat.
```

## DungeonGround.png

```text
Use case: stylized-concept
Asset type: seamless repeating side-view ground tile for a 2D pixel-art dungeon platformer
Primary request: Create one horizontally seamless dungeon floor texture tile that forms a flat walkable path for the referenced small knight.
Input images: Image 1 is a style reference only: transparent pixel-art knight sprite sheet. Match its coarse readable pixel clusters and muted steel-blue gray palette, with dark charcoal outlines, subtle blue highlights and sparse brown accents; do not include the knight.
Scene/backdrop: A side-on cutaway view of a level stone floor: the very top edge is a continuous, perfectly straight and level walking surface made of broad slate flagstones, with a shallow visible front edge and a darker blocky stone underside beneath it. The top surface must be perfectly flat from left edge to right edge so a 2D BoxCollider can align with it.
Style/medium: crisp hand-authored 16-bit pixel art, limited palette, chunky pixel clusters and hard pixel edges, no antialiasing, no perspective, designed to sit beneath a small pixel-art knight without looking higher resolution or painterly.
Composition/framing: Single full-bleed rectangular tile viewed exactly from the side. Left and right edges must match exactly for seamless horizontal repeat. The level top walk surface touches the top border across the entire width, and the stone depth fills the rest of the image down to the bottom border. Avoid unique landmarks; distribute block variation evenly. No gaps, holes, steps, slope, or protrusions on top.
Lighting/mood: cool dim dungeon light with restrained pale blue-gray highlights, readable against a darker background.
Materials/textures: worn flat slate floor slabs, dark mortar seams, chunky stone blocks on the cutaway face; very sparse tiny brown dirt pixels only on the vertical face.
Constraints: no characters, no wall, no objects on the floor, no perspective, no text, no UI, no frame, no border, no watermark. The texture must be a single usable game tile with a straight flat collision-ready top edge and seamless horizontal side edges.
```
