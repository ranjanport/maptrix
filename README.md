# MapTrix

MapTrix is a Python implementation of geo utilities for map data processing and computation, including geospatial calculations, map data manipulation, and spatial analysis tools.

## Features

- WGS84 to NDS coordinate conversion utilities.
- Morton (Z-order) encoding/decoding for 2D coordinates.
- NDS.Live packed tile ID helpers, neighbors, and tile metrics.
- Bounding box utilities for NDS coordinate space.
- Snapping/unsnapping helpers for point encoding.

## Requirements

- Python 3.9+

## Installation

From source:

```bash
pip install -e .
```

## Quickstart

```python
from maptrix.pos import Position
from maptrix.morton import MortonCode
from maptrix.tileid import PackedTileId
from maptrix.bounding_box import NdsBoundingBox

# WGS84 to NDS
wgs = Position(lon=77.5946, lat=12.9716)
nds_x, nds_y = wgs.to_nds_coordinates()

# Morton encoding
morton = MortonCode().from_nds(nds_x, nds_y)

# Tile ID at level 13
tile = PackedTileId.from_morton_and_level(MortonCode(morton), level=13)
print(tile.value, tile.level())

# Tile bounds as NDS bounding box
bbox = NdsBoundingBox.from_tile(tile)
print(bbox)
```

Snapping example:

```python
from maptrix.libmath import Coord2PointXY, CoordinateMath

maths = CoordinateMath(coordinate_shift=3)
point = Coord2PointXY(long=77.5946, lat=12.9716)
ref = Coord2PointXY(long=77.5900, lat=12.9700)

snap = maths.snap(point, ref)
unsnap = maths.unsnap(snap, ref)
```

## API Overview

- `maptrix.pos.Position`: WGS84 position utilities, normalization, distance, and bearings.
- `maptrix.morton.MortonCode`: Morton encoding/decoding for NDS coordinates.
- `maptrix.tileid.PackedTileId`: NDS.Classic / NDS.Live packed tile ID helpers and neighbors.
- `maptrix.bounding_box.NdsBoundingBox`: Bounding box creation and intersection checks.
- `maptrix.libmath`: Convenience helpers for snapping and coordinate conversion.

## Project Structure

```
src/maptrix/
  __init__.py
  bounding_box.py
  libmath.py
  morton.py
  pos.py
  tileid.py
```

## Testing

If you add tests, you can run them with:

```bash
python -m unittest 
```

## License

See `pyproject.toml`.

