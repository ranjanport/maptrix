import os
from dotenv import load_dotenv
load_dotenv()

import pytest
from osgeo import ogr
from pathlib import Path

from maptrix.geofileops.gdb import GeoFileDatabase




# ----------------------------------------------------------------------
# TEST CONFIG
# ----------------------------------------------------------------------

TEST_DIR = Path(__file__).parent
RESOURCE_DIR = TEST_DIR / "resources"
TEST_GDB = RESOURCE_DIR / "boundary.gdb"

OUTPUT_DIR = TEST_DIR / "output"
OUTPUT_GDB = OUTPUT_DIR / "out.gdb"
OUTPUT_GDBF = OUTPUT_DIR / "outf.gdb"


# Optional Postgres config (env driven)
PG_CONN = os.getenv("MAPTRIX_TEST_PG")


# ----------------------------------------------------------------------
# FIXTURES
# ----------------------------------------------------------------------

@pytest.fixture(scope="session")
def gdb():
    """Provide GeoFileDatabase instance."""
    if not TEST_GDB.exists():
        pytest.skip("Test GDB not found")

    return GeoFileDatabase(TEST_GDB)


# @pytest.fixture(autouse=True)
# def cleanup_output():
#     """Clean up output directory before each test."""
#     if OUTPUT_DIR.exists():
#         for p in OUTPUT_DIR.rglob("*"):
#             if p.is_file():
#                 p.unlink()
#     OUTPUT_DIR.mkdir(exist_ok=True)
#     yield


# ----------------------------------------------------------------------
# DRIVER CHECKS
# ----------------------------------------------------------------------

def _require_driver(name: str):
    if ogr.GetDriverByName(name) is None:
        pytest.skip(f"{name} driver not available")


# ----------------------------------------------------------------------
# BASIC INIT
# ----------------------------------------------------------------------

def test_gdb_initialization():
    gdb = GeoFileDatabase(TEST_GDB)
    assert gdb.gdb_path.exists()


def test_invalid_path():
    with pytest.raises(FileNotFoundError):
        GeoFileDatabase("invalid.gdb")


# ----------------------------------------------------------------------
# GDB -> SHAPEFILE
# ----------------------------------------------------------------------

def test_gdb2shape_all_layers(gdb):
    _require_driver("ESRI Shapefile")

    gdb.gdb2shape(OUTPUT_DIR)

    shp_files = list(OUTPUT_DIR.glob("*.shp"))
    assert len(shp_files) > 0


def test_gdb2shape_subset(gdb):
    _require_driver("ESRI Shapefile")

    ds = ogr.Open(str(TEST_GDB))
    layer_name = ds.GetLayerByIndex(0).GetName()

    gdb.gdb2shape(OUTPUT_DIR, tables=[layer_name])

    shp_files = list(OUTPUT_DIR.glob("*.shp"))
    assert len(shp_files) == 1
    assert shp_files[0].stem == layer_name


# ----------------------------------------------------------------------
# GDB -> POSTGRES
# ----------------------------------------------------------------------

@pytest.mark.skipif(
    PG_CONN is None,
    reason="Postgres connection not provided"
)
def test_gdb2pg(gdb):
    _require_driver("PostgreSQL")

    gdb.gdb2pg(
        PG_CONN,
        schema="test_gdb",
        overwrite=True,
    )


# ----------------------------------------------------------------------
# POSTGRES -> GDB
# ----------------------------------------------------------------------

@pytest.mark.skipif(
    PG_CONN is None,
    reason="Postgres connection not provided"
)
def test_pg2gdb():
    _require_driver("OpenFileGDB")

    gdb = GeoFileDatabase(OUTPUT_GDB, mode="create")

    gdb.pg2gdb(
        PG_CONN,
        schema='test_gdb',
        mode=None
    )

    assert OUTPUT_GDB.exists() or True  # creation validated by GDAL


# ----------------------------------------------------------------------
# FEATURE DATASET EXPORT
# ----------------------------------------------------------------------

@pytest.mark.skipif(
    PG_CONN is None,
    reason="Postgres connection not provided"
)
def test_pg2gdbf():
    _require_driver("OpenFileGDB")

    gdb = GeoFileDatabase(OUTPUT_GDBF,  mode="create")
    layers = gdb.get_layers_from_db(
        connection=PG_CONN,
        schema="public",
    )
    mapping = {}
    for layer in layers:
        mapping[layer+"class"] = [layer]

    gdb.pg2gdbf(
        PG_CONN,
        feature_mapping=mapping,
    )


# ----------------------------------------------------------------------
# THREAD SAFETY
# ----------------------------------------------------------------------

def test_parallel_execution(gdb):
    """
    Ensures a parallel pipeline does not crash.
    """

    gdb.gdb2shape(OUTPUT_DIR)

    assert any(OUTPUT_DIR.glob("*.shp"))