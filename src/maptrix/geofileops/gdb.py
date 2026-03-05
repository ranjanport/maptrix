"""Description : GeoFileDatabase operations using GDAL Python bindings.

This module provides high-level helpers to move vector data between:
- File Geodatabases (`.gdb`)
- PostgreSQL/PostGIS
- ESRI Shapefile directories

Implementation Notes:
- Uses ``osgeo.ogr``/``osgeo.gdal`` directly (no subprocess or ``ogr2ogr`` binary calls).
- Supports parallel layer-level processing via a thread pool.
- Raises GDAL/OGR exceptions directly because ``gdal.UseExceptions()`` is enabled.
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
    """Description : Configure global thread count for geofile operations.

    This setting is applied by :meth:`GeoFileDatabase._run_parallel` and is
    process-wide for this module.

    Args:
        n (int): Desired number of worker threads.

    Returns:
        None

    Note:
        Values lower than ``1`` are clamped to ``1``.
    """
    global GEOFILEOPS_THREADS
    GEOFILEOPS_THREADS = max(1, int(n))


# ----------------------------------------------------------------------
# GeoFileDatabase
# ----------------------------------------------------------------------

class GeoFileDatabase:
    """Description : GeoFileDatabase interface using GDAL/OGR bindings.

    This class wraps common import/export workflows for File Geodatabases,
    PostgreSQL/PostGIS, and Shapefiles while hiding low-level GDAL option setup.
    For parallel workloads, each worker opens its own source dataset handle to
    reduce shared-handle contention.

    Args:
        gdb_path (PathLike): Path to the File Geodatabase directory (``.gdb``).
        mode (str, optional): Open mode.
            - ``"open"`` validates that ``gdb_path`` exists.
            - ``"create"`` defers dataset creation until export methods run.
            Defaults to ``"open"``.

    Raises:
        FileNotFoundError: If ``mode="open"`` and ``gdb_path`` does not exist.
        RuntimeError: If the GDAL ``OpenFileGDB`` driver is unavailable.
    """

    def __init__(self, gdb_path: PathLike, mode: str='open') -> None:
        """Description : Initialize a GeoFileDatabase instance.

        Args:
            gdb_path (PathLike): Path to a `.gdb` directory.
            mode (str, optional): ``"open"`` or ``"create"``.

        Returns:
            None

        Raises:
            FileNotFoundError: If open mode is requested but the path is missing.
            RuntimeError: If required GDAL OpenFileGDB support is not available.
        """
        self.gdb_path = Path(gdb_path)

        if mode == 'open' and not self.gdb_path.exists():
            raise FileNotFoundError(self.gdb_path)

        self._driver = ogr.GetDriverByName("OpenFileGDB")
        if self._driver is None:
            raise RuntimeError("GDAL OpenFileGDB driver not available")

    def _open_gdb(self, update: bool = False):
        """Description : Open the configured geodatabase path.

        Args:
            update (bool, optional): Open with update/write intent when ``True``.
                Defaults to ``False``.

        Returns:
            GDAL/OGR dataset handle for the geodatabase.

        Raises:
            RuntimeError: If the geodatabase cannot be opened.
        """
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
        """Description : Normalize PostgreSQL connection input to GDAL format.

        Args:
            connection (Union[str, Dict[str, Any]]):
                - Prebuilt GDAL string (for example ``"PG:host=... dbname=..."``), or
                - Mapping with keys ``host``, ``dbname``, ``user``, ``password`` and
                  optional ``port``.
            schema (str, optional): Schema restriction used when a mapping is
                provided. Defaults to ``"public"``.

        Returns:
            str: GDAL-compatible PostgreSQL connection string.

        Raises:
            KeyError: If a required mapping key is missing.
        """
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
        """Description : List layer names in a GDAL dataset.

        Args:
            ds: Open GDAL dataset.
            tables (Optional[Iterable[str]], optional): Optional allow-list of
                layer names. If provided, only matching names are returned.

        Returns:
            List[str]: Layer names in dataset order.
        """
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
        """Description : Import layers from FileGDB into PostgreSQL/PostGIS.

        Each selected layer is translated independently using GDAL
        ``VectorTranslate`` and can be processed in parallel.

        Args:
            connection (Union[str, Dict[str, Any]]): PostgreSQL connection
                information in string or mapping form.
            schema (str, optional): Target schema for created layers.
                Defaults to ``"public"``.
            overwrite (bool, optional): If ``True``, allow replacing existing
                target layers. Defaults to ``False``.
            tables (Optional[Iterable[str]], optional): Subset of source layer
                names to export. Exports all layers when ``None``.

        Returns:
            None

        Raises:
            RuntimeError: If source GDB, PostgreSQL connection, or worker
                translation fails.
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
        """Description : Export PostgreSQL/PostGIS layers into a FileGDB.

        Selected layers are translated from PostgreSQL into the geodatabase path
        represented by this instance.

        Args:
            connection (Union[str, Dict[str, Any]]): PostgreSQL connection
                information in string or mapping form.
            schema (str, optional): Source schema to read from. Defaults to
                ``"public"``.
            tables (Optional[Iterable[str]], optional): Subset of source table
                names to export. Exports all discovered layers when ``None``.
            mode (Optional[Literal["update", "append", "overwrite"]], optional):
                GDAL access mode for destination writes. If ``None`` and target
                path exists, existing GDB is deleted and recreated.

        Returns:
            None

        Raises:
            RuntimeError: If PostgreSQL source cannot be opened or translation
                fails.
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
        """Description : Export PostgreSQL tables into FileGDB feature datasets.

        This is similar to :meth:`pg2gdb`, but tables are grouped into named
        feature datasets using GDAL creation options.

        Args:
            connection (Union[str, Dict[str, Any]]): PostgreSQL connection
                information in string or mapping form.
            feature_mapping (Dict[str, Iterable[str]]): Mapping of
                ``feature_dataset_name -> iterable_of_table_names``.
            schema (str, optional): Source schema to read from. Defaults to
                ``"public"``.
            mode (Optional[Literal["update", "append", "overwrite"]], optional):
                GDAL access mode for destination writes. If ``None`` and target
                path exists, existing GDB is deleted and recreated.

        Returns:
            None

        Raises:
            RuntimeError: If PostgreSQL source cannot be opened or any worker
                translation fails.
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
    ) -> None:
        """Description : Export FileGDB layers to ESRI Shapefile format.

        One Shapefile is generated per selected layer in ``output_dir``.

        Args:
            output_dir (PathLike): Destination directory for generated
                ``.shp/.dbf/.shx/...`` files.
            tables (Optional[Iterable[str]], optional): Subset of source layers
                to export. Exports all layers when ``None``.

        Returns:
            None

        Raises:
            RuntimeError: If source geodatabase or worker translation fails.
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
        """Description : Execute item-wise work in a shared thread pool.

        Args:
            items (Iterable[Any]): Work items to process.
            func (Callable[[Any], Any]): Worker function called once per item.

        Returns:
            None

        Raises:
            Exception: Re-raises the first worker exception surfaced by
                ``future.result()``.
        """

        with ThreadPoolExecutor(max_workers=GEOFILEOPS_THREADS) as exe:
            futures = [exe.submit(func, item) for item in items]

            for f in as_completed(futures):
                f.result()

    def get_layers_from_db(self, connection: Union[str, Dict[str, Any]], schema:str='public'):
        """Description : List layer names from a PostgreSQL/PostGIS source.

        Args:
            connection (Union[str, Dict[str, Any]]): PostgreSQL connection
                information in string or mapping form.
            schema (str, optional): Source schema filter. Defaults to ``"public"``.

        Returns:
            List[str]: Layer names available in the specified database/schema.
        """
        pg_conn = self._pg_connection_string(connection, schema=schema)
        src_ds = ogr.Open(pg_conn)
        layers = self._list_layers(src_ds)
        return layers
