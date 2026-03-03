from dataclasses import dataclass
import math
from typing import overload

from maptrix.morton import MortonCode
from maptrix.pos import Position
from maptrix.tileid import PackedTileId


@dataclass
class Coord2PointXY:
    """
    Convert WGS84 to Point_X_Y Coordinates or NDS to Point_X_Y Coordinates
    """

    long: float | int
    lat: float | int

    @property
    def to_nds_coordinate(self) -> "Coord2PointXY":
        return CoordinateMath.WGS2NDS(self)

    @property
    def to_wgs84_coordinate(self) -> "Coord2PointXY":
        return CoordinateMath.NDS2WGS(self)

    @property
    def to_Coord2PointXYZ(self) -> "Coord2PointXYZ":
        return Coord2PointXYZ(long=self.long, lat=self.lat, height=0)

    @overload
    def get_tile_id(self) -> int: ...

    @overload
    def get_tile_id(self, level: int) -> int: ...

    def get_tile_id(self, level: int | None = None) -> int:
        nds_coord = self.to_nds_coordinate
        mcode = MortonCode(
            MortonCode.from_nds_coordinates(nds_coord.long, nds_coord.lat)
        )
        if level is None:
            tile = PackedTileId.from_morton_and_level(mcode, 13).value
            return tile
        else:
            tile = PackedTileId.from_morton_and_level(mcode, level).value
            return tile


@dataclass
class Coord2PointXYZ(Coord2PointXY):
    """
    Convert WGS84 to Point_X_Y_Z Coordinates or NDS to Point_X_Y_Z Coordinates
    """

    height: float | int


class Maths:
    def __init__(self):
        pass

    @staticmethod
    def subtract(a: Coord2PointXY, b: Coord2PointXY):
        return Coord2PointXY(a.long - b.long, a.lat - b.lat)

    @staticmethod
    def divide(a: Coord2PointXY, b: float):
        if b == 0:
            raise ValueError("Division by zero is not allowed.")
        return Coord2PointXY(a.long / b, a.lat / b)

    @staticmethod
    def multiply(a: Coord2PointXY, b: float):
        return Coord2PointXY(a.long * b, a.lat * b)

    @staticmethod
    def add(a: Coord2PointXY, b: Coord2PointXY):
        return Coord2PointXY(a.long + b.long, a.lat + b.lat)

    @classmethod
    def offset_bits(cls, d):
        if d > 0:
            d += 1
        return math.ceil(math.log2(abs(d)))

    @classmethod
    def max_bits(cls, obj: Coord2PointXY):
        a, b = obj.long, obj.lat
        if a == 0:
            a = 1
        else:
            a = a.bit_length()
        if b == 0:
            b = 1
        else:
            b = b.bit_length()
        return max(a, b)

    @classmethod
    def widen(cls, v, mask):
        """Widen a 32-bit value to 64 bits by interleaving zeros"""
        v &= mask
        v = (v | (v << 16)) & 0x0000FFFF0000FFFF
        v = (v | (v << 8)) & 0x00FF00FF00FF00FF
        v = (v | (v << 4)) & 0x0F0F0F0F0F0F0F0F
        v = (v | (v << 2)) & 0x3333333333333333
        v = (v | (v << 1)) & 0x5555555555555555
        return v


class CoordinateMath:
    def __init__(self, coordinate_shift: int = 3):
        self.coordinate_shift = coordinate_shift

    @classmethod
    def WGS2NDS(cls, position: Coord2PointXY):
        """Description : Convert WGS84 to NDS Coordinates and return the NDS Coordinates
        Args:
            position (Coord2PointXY): WGS84 Coordinates
        Returns:
            Coord2PointXY: NDS Coordinates with keys 'x' and 'y'
        """
        _ = Position(position.long, position.lat).to_nds()
        return Coord2PointXY(long=_.x, lat=_.y)

    @classmethod
    def NDS2WGS(cls, position: Coord2PointXY):
        _ = Position.from_nds_coordinates(position.long, position.lat)
        return Coord2PointXY(long=_.x, lat=_.y)

    def snap(
        self,
        point: Coord2PointXY,
        ref_point: Coord2PointXY,
        coordinate_shift: int = None,
    ):
        """Description : Snapping here means referencing and judging the coordinate offset from the reference point.
        This ensures that the difference encoding between point and ref_point is non-Zero
        to ensure the point is not redundant.

        If a point is redundant, the offset values will be exactly 0,0 and in the case where the offset becomes 0,
        we'll exclude that point from the encoding.

        Snapping works in a way that the first node of a given segment is referenced
        from the tile center of the respective tile on which it lies. Then the next nodes are
        referenced from the previous node, resulting in smaller offset values.

        In the process there is a coordinate shift that is applied to ensure that the offset values are
        within a certain range. This also causes the point resolution to be reduced, and a little coefficient
        difference variation from actual is occurred.

        Args:
            point (Coord2PointXY): WGS84 Coordinates
            ref_point (Coord2PointXY): Reference WGS84 Coordinates
            coordinate_shift (int, optional): Coordinate shift. Defaults to 3.
        """
        pos = self.WGS2NDS(point)
        pos1 = Maths.subtract(pos, ref_point)
        if coordinate_shift is None:
            divided = Maths.divide(pos1, float(0x01 << self.coordinate_shift))
        else:
            divided = Maths.divide(pos1, float(0x01 << coordinate_shift))
        return Coord2PointXY(math.floor(divided.long), math.floor(divided.lat))

    def unsnap(
        self,
        point: Coord2PointXY,
        ref_point: Coord2PointXY,
        coordinate_shift: int = None,
    ):
        """Description : To overcome the snapping effect, the offset values are multiplied by a coefficient
         and added to the reference point. This provides the actual position post-shift is applied to the coordinate offset.
         This has to be applied on all nodes that are being referenced from the previous one.

        Args:
            point (Coord2PointXY): WGS84 Coordinates
            ref_point (Coord2PointXY): Reference WGS84 Coordinates
            coordinate_shift (int, optional): Coordinate shift. Defaults to 3.
        """
        if coordinate_shift is None:
            return self.NDS2WGS(
                Maths.add(Maths.multiply(point, 1 << self.coordinate_shift), ref_point)
            )
        else:
            return self.NDS2WGS(
                Maths.add(Maths.multiply(point, 1 << coordinate_shift), ref_point)
            )

    @staticmethod
    def get_tile_center(tileId: int):
        """Description : Returns two values, the x and y coordinates of the tile center
        Args:
            tileId (int): Tile ID
        Returns:
            Coord2PointXY: Center coordinates with keys 'x' and 'y'
        """
        _ = PackedTileId(tileId).center()
        return Coord2PointXY(long=_[0], lat=_[1])

    @classmethod
    def latitude_isvalid(cls, lat):
        """Check if the latitude is valid (-90 to 90 degrees)"""
        return -90.0 <= lat <= 90.0

    @classmethod
    def longitude_isvalid(cls, lng):
        """Check if longitude is valid (-180 to 180 degrees)"""
        return -180.0 <= lng <= 180.0


class TileMath:
    @classmethod
    def get_tile_content_index(
        cls, south_west_tile: int, num_rows: int, num_cols: int, tiles: list[int]
    ):
        """Description : This evaluates the tile content index for a grid of tiles starting from the south-west tile.
        It returns a list indicating the presence (1) or absence (0) of tiles in the specified area.

        Args:
            south_west_tile (int): The tile ID of the south-west corner of the area.
            num_rows (int): The number of rows in the area.
            num_cols (int): The number of columns in the area.
            tiles (list[int]): A list of tile IDs representing the tiles to be included in the index.

        Returns:
            Tile content index (list): A list of 1s and 0s indicating the presence (1) or absence (0) of tiles.
        """
        south_west_tile = PackedTileId(south_west_tile)
        tile_content_index = []
        current_tile = south_west_tile
        row_start_tile = south_west_tile
        tile_content_index.append(current_tile.value)

        for row in range(num_rows):
            for col in range(num_cols - 1):
                current_tile = current_tile.right_neighbour()
                tile_content_index.append(current_tile.value)
            row_start_tile = row_start_tile.top_neighbour()
            current_tile = row_start_tile
            tile_content_index.append(current_tile.value)

        tile_content_index.remove(current_tile.value)
        tile_content_index_value = []
        for tile in tile_content_index:
            if tile in tiles:
                tile_content_index_value.append(1)
            else:
                tile_content_index_value.append(0)
        return tile_content_index_value, tile_content_index


class AdasV2:
    @classmethod
    def get_encoded_curvature(cls, curvature: float) -> int:
        """Description : Encode the curvature value as per NDS specification and return the encoded value.

        Args: curvature (float): Curvature value.

        Returns: int: Encoded curvature value.
        """
        value = 0

        if curvature < 0:
            SING = -1
        else:
            SING = 1

        if abs(curvature) < 0.00064:
            value = 511 + round(curvature * 100000)
        elif 0.00064 <= abs(curvature) < 0.00192:
            value = 511 + SING * 32 + round((curvature * 100000) / 2)
        elif 0.00192 <= abs(curvature) < 0.00448:
            value = 511 + SING * 80 + round((curvature * 100000) / 4)
        elif 0.00448 <= abs(curvature) < 0.00960:
            value = 511 + SING * 136 + round((curvature * 100000) / 8)
        elif 0.00960 <= abs(curvature) < 0.01984:
            value = 511 + SING * 196 + round((curvature * 100000) / 16)
        elif 0.01984 <= abs(curvature) < 0.04032:
            value = 511 + SING * 258 + round((curvature * 100000) / 32)
        elif 0.04032 <= abs(curvature) < 0.08128:
            value = 511 + SING * 321 + round((curvature * 100000) / 64)
        elif 0.08128 <= abs(curvature) < 0.16192:
            value = 511 + SING * 384 + round((curvature * 100000) / 128)
        elif 0.16192 <= abs(curvature):
            value = 511 + SING * 511
        return value
