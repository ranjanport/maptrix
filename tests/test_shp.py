import os
from pathlib import Path

import pytest
from dotenv import load_dotenv
from osgeo import ogr

from maptrix.geofileops.gdb import GeoFileDatabase
from maptrix.geofileops.shp import ShapefileDatabase

load_dotenv()


TEST_DIR = Path(__file__).parent
RESOURCE_DIR = TEST_DIR / "resources"
TEST_GDB = RESOURCE_DIR / "boundary.gdb"
PG_CONN = os.getenv("MAPTRIX_TEST_PG")
OUTPUT_DIR = TEST_DIR / "output"


def _require_driver(name: str) -> None:
    if ogr.GetDriverByName(name) is None:
        pytest.skip(f"{name} driver not available")


def _require_pg_connection(connection: str) -> None:
    if not connection:
        pytest.skip("Postgres connection not provided")
    _require_driver("PostgreSQL")
    try:
        ds = ogr.Open(connection)
    except RuntimeError:
        pytest.skip("Postgres connection unavailable")
    if ds is None:
        pytest.skip("Postgres connection unavailable")


@pytest.fixture(scope="session")
def shp_dir() -> Path:
    _require_driver("OpenFileGDB")
    _require_driver("ESRI Shapefile")
    if not TEST_GDB.exists():
        pytest.skip("Test GDB not found")

    out_dir = OUTPUT_DIR = TEST_DIR / "output" / "shp"
    GeoFileDatabase(TEST_GDB).gdb2shape(out_dir)
    return out_dir


def test_shp_initialization(shp_dir: Path) -> None:
    shp = ShapefileDatabase(shp_dir)
    assert shp.shp_path.exists()


def test_shp_invalid_path() -> None:
    with pytest.raises(FileNotFoundError):
        ShapefileDatabase("invalid_shp_path")


def test_shp2tab(shp_dir: Path, tmp_path: Path) -> None:
    _require_driver("MapInfo File")
    out_dir = OUTPUT_DIR / "tab_from_shp"

    ShapefileDatabase(shp_dir).shp2tab(out_dir)

    assert any(out_dir.glob("*.tab"))


def test_shp2pg(shp_dir: Path) -> None:
    _require_pg_connection(PG_CONN)

    shp = ShapefileDatabase(shp_dir)
    first_layer = next(shp_dir.glob("*.shp")).stem
    shp.shp2pg(PG_CONN, schema="shp2pg", overwrite=True, tables=[first_layer])


def test_pg2shp() -> None:
    _require_pg_connection(PG_CONN)

    ds = ogr.Open(PG_CONN)
    layer_count = ds.GetLayerCount()
    if layer_count == 0:
        pytest.skip("No layers available in PostgreSQL source")
    first_layer = ds.GetLayerByIndex(0).GetName()

    out_dir = OUTPUT_DIR / "shp_from_pg"
    ShapefileDatabase(out_dir, mode="create").pg2shp(
        PG_CONN,
        schema="shp2pg",
        tables=[first_layer],
    )

    assert any(out_dir.glob("*.shp"))
