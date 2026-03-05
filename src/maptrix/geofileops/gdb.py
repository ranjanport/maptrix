"""
GeoFileDatabase operations using GDAL Python bindings.

Implementation Notes
--------------------
- Uses osgeo.ogr directly (NO subprocess / ogr2ogr binary).
- Parallel layer processing supported.
- Designed for SDK packaging and compiled wheel distribution.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Dict, Iterable, Literal, Optional, Union, Any, List
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

from osgeo import ogr, gdal

PathLike = Union[str, Path]


# ----------------------------------------------------------------------
# Global GDAL Configuration
# ----------------------------------------------------------------------

gdal.UseExceptions()

# Global thread controller (SDK-wide)
GEOFILEOPS_THREADS: int = max(1, (threading.active_count() or 4))


def set_geofileops_threads(n: int) -> None:
    """
    Configure global parallel execution threads.

    Parameters
    ----------
    n : int
        Number of worker threads.
    """
    global GEOFILEOPS_THREADS
    GEOFILEOPS_THREADS = max(1, int(n))


# ----------------------------------------------------------------------
# GeoFileDatabase
# ----------------------------------------------------------------------

class GeoFileDatabase:
    """Description: GeoFileDatabase interface using GDAL/OGR bindings.

    Args:
        gdb_path: path to the File Geodatabase directory (.gdb).
        mode: 'open' or 'create'.

    """

    def __init__(self, gdb_path: PathLike, mode: str='open') -> None:
        self.gdb_path = Path(gdb_path)

        if mode == 'open' and not self.gdb_path.exists():
            raise FileNotFoundError(self.gdb_path)

        self._driver = ogr.GetDriverByName("OpenFileGDB")
        if self._driver is None:
            raise RuntimeError("GDAL OpenFileGDB driver not available")

    def _open_gdb(self, update: bool = False):
        ds = ogr.OpenShared(str(self.gdb_path), update)
        if ds is None:
            raise RuntimeError("Failed to open GDB")
        return ds

    @classmethod
    def _pg_connection_string(
        cls,
        connection: Union[str, Dict[str, Any]],
        schema: str = "public",
    ) -> str:
        if isinstance(connection, str):
            return connection

        return (
            f"PG:host={connection['host']} "
            f"port={connection.get('port',5432)} "
            f"dbname={connection['dbname']} "
            f"user={connection['user']} "
            f"password={connection['password']} "
            f"schemas={schema}"
        )

    @classmethod
    def _list_layers(cls, ds, tables=None) -> List[str]:
        layers = [ds.GetLayerByIndex(i).GetName()
                  for i in range(ds.GetLayerCount())]

        if tables:
            layers = [l for l in layers if l in tables]

        return layers


    def gdb2pg(
        self,
        connection: Union[str, Dict[str, Any]],
        *,
        schema: str = "public",
        overwrite: bool = False,
        tables: Optional[Iterable[str]] = None,
    ) -> None:
        """
        Import GDB layers into PostgreSQL/PostGIS.
        """

        src_ds = self._open_gdb()
        pg_conn = self._pg_connection_string(connection)

        pg_driver = ogr.GetDriverByName("PostgreSQL")
        dst_ds = pg_driver.Open(pg_conn, update=1)

        layers = self._list_layers(src_ds, tables)

        def worker(layer_name: str):
            src_ds = ogr.Open(str(self.gdb_path))
            if src_ds is None:
                raise RuntimeError("Worker failed to open GDB")

            options = gdal.VectorTranslateOptions(
                format="PostgreSQL",
                layers=[layer_name],
                geometryType="PROMOTE_TO_MULTI",
                layerCreationOptions=[
                    f"SCHEMA={schema}",
                    "OVERWRITE=YES" if overwrite else "OVERWRITE=NO",
                ],
            )

            gdal.VectorTranslate(
                pg_conn,
                src_ds,
                options=options,
            )
        self._run_parallel(layers, worker)


    def pg2gdb(
        self,
        connection: Union[str, Dict[str, Any]],
        *,
        schema: str = "public",
        tables: Optional[Iterable[str]] = None,
        mode: Union[None, Literal['update', 'append', 'overwrite']] = None,
    ) -> None:
        """
        Export PostGIS tables into GDB.
        """

        pg_conn = self._pg_connection_string(connection, schema=schema)
        src_ds = ogr.Open(pg_conn)

        gdb_driver = ogr.GetDriverByName("OpenFileGDB")

        if mode is None and self.gdb_path.exists():
            shutil.rmtree(self.gdb_path)

        dst_ds = gdb_driver.CreateDataSource(str(self.gdb_path))

        layers = self._list_layers(src_ds, tables)

        def worker(layer_name: str):

            src_ds = ogr.Open(pg_conn)
            if src_ds is None:
                raise RuntimeError("Worker failed to open PG source")

            options = gdal.VectorTranslateOptions(
                format="OpenFileGDB",
                layers=[layer_name],
                accessMode=mode
            )

            gdal.VectorTranslate(
                str(self.gdb_path),
                src_ds,
                options=options,

            )
        self._run_parallel(layers, worker)

    def pg2gdbf(
        self,
        connection: Union[str, Dict[str, Any]],
        feature_mapping: Dict[str, Iterable[str]],
        *,
        schema: str = "public",
        mode: Union[None, Literal['update', 'append', 'overwrite']] = None,
    ) -> None:
        """
        Export tables grouped into feature datasets.
        """

        pg_conn = self._pg_connection_string(connection, schema=schema)
        src_ds = ogr.Open(pg_conn)

        gdb_driver = ogr.GetDriverByName("OpenFileGDB")

        if mode is None and self.gdb_path.exists():
            shutil.rmtree(self.gdb_path)

        dst_ds = gdb_driver.CreateDataSource(str(self.gdb_path))

        tasks = []

        for dataset, tables in feature_mapping.items():
            for table in tables:
                tasks.append((dataset, table))

        def worker(task):
            dataset, table = task

            src_ds = ogr.Open(pg_conn)
            if src_ds is None:
                raise RuntimeError("Worker PG open failed")

            options = gdal.VectorTranslateOptions(
                format="OpenFileGDB",
                layers=[table],
                datasetCreationOptions=[
                    f"FEATURE_DATASET={dataset}"
                ],
                layerCreationOptions=[
                    f"FEATURE_DATASET={dataset}"
                ],
                accessMode=mode
            )

            gdal.VectorTranslate(
                str(self.gdb_path),
                src_ds,
                options=options,
            )

        self._run_parallel(tasks, worker)


    def gdb2shape(
        self,
        output_dir: PathLike,
        *,
        tables: Optional[Iterable[str]] = None,
        overwrite: bool = True,
    ) -> None:
        """
        Convert GDB layers to Shapefiles.
        """

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        src_ds = self._open_gdb()
        shp_driver = ogr.GetDriverByName("ESRI Shapefile")

        layers = self._list_layers(src_ds, tables)

        def worker(layer_name: str):
            # Each thread opens its own dataset
            src_ds = ogr.Open(str(self.gdb_path))
            if src_ds is None:
                raise RuntimeError("Failed to open GDB in worker")

            shp_path = output_dir / f"{layer_name}.shp"

            options = gdal.VectorTranslateOptions(
                format="ESRI Shapefile",
                layers=[layer_name],
            )

            gdal.VectorTranslate(
                str(shp_path),  # destination path
                src_ds,  # DATASET (not layer)
                options=options,
            )

        self._run_parallel(layers, worker)

    @staticmethod
    def _run_parallel(items, func):
        """
        Execute operations using a global thread pool.
        """

        with ThreadPoolExecutor(max_workers=GEOFILEOPS_THREADS) as exe:
            futures = [exe.submit(func, item) for item in items]

            for f in as_completed(futures):
                f.result()

    def get_layers_from_db(self, connection: Union[str, Dict[str, Any]], schema:str='public'):
        pg_conn = self._pg_connection_string(connection, schema=schema)
        src_ds = ogr.Open(pg_conn)
        layers = self._list_layers(src_ds)
        return layers