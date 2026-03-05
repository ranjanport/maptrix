"""Geofile operation helpers built on top of GDAL/OGR bindings."""

from maptrix.geofileops.gdb import GeoFileDatabase, set_geofileops_threads as set_gdb_threads
from maptrix.geofileops.shp import ShapefileDatabase, set_geofileops_threads as set_shp_threads
from maptrix.geofileops.tab import TabFileDatabase, set_geofileops_threads as set_tab_threads

__all__ = [
    "GeoFileDatabase",
    "ShapefileDatabase",
    "TabFileDatabase",
    "set_gdb_threads",
    "set_shp_threads",
    "set_tab_threads",
]
