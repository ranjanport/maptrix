"""Description : MapInfo TAB operations using GDAL/OGR Python bindings.

This module provides high-level helpers to move vector data between:
- MapInfo TAB datasets (`.tab`)
- PostgreSQL/PostGIS
- ESRI Shapefiles (`.shp`)

Implementation Notes:
- Uses ``osgeo.ogr``/``osgeo.gdal`` directly (no subprocess calls).
- Supports parallel layer-level processing via a thread pool.
- Raises GDAL/OGR exceptions directly because ``gdal.UseExceptions()`` is enabled.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import threading
from typing import Any, Dict, Iterable, List, Optional, Union

from osgeo import gdal, ogr

PathLike = Union[str, Path]

gdal.UseExceptions()

# Global thread controller (module-wide)
GEOFILEOPS_THREADS: int = max(1, (threading.active_count() or 4))


def set_geofileops_threads(n: int) -> None:
    """Description : Configure global thread count for TAB operations.

    Args:
        n (int): Desired number of worker threads.

    Returns:
        None

    Note:
        Values lower than ``1`` are clamped to ``1``.
    """
    global GEOFILEOPS_THREADS
    GEOFILEOPS_THREADS = max(1, int(n))


class TabFileDatabase:
    """Description : MapInfo TAB interface using GDAL/OGR bindings.

    This class supports bulk conversion workflows from a single `.tab` file
    or a directory that contains multiple `.tab` files.

    Args:
        tab_path (PathLike): Path to a `.tab` file or directory of TAB files.
        mode (str, optional): Open mode.
            - ``"open"`` validates that ``tab_path`` exists.
            - ``"create"`` defers file creation until export methods run.
            Defaults to ``"open"``.

    Raises:
        FileNotFoundError: If ``mode="open"`` and ``tab_path`` does not exist.
        RuntimeError: If required GDAL drivers are unavailable.
    """

    def __init__(self, tab_path: PathLike, mode: str = "open") -> None:
        """Description : Initialize a TabFileDatabase instance.

        Args:
            tab_path (PathLike): Path to TAB input/output root.
            mode (str, optional): ``"open"`` or ``"create"``.

        Returns:
            None

        Raises:
            FileNotFoundError: If open mode is requested but path is missing.
            RuntimeError: If GDAL drivers are unavailable.
        """
        self.tab_path = Path(tab_path)

        if mode == "open" and not self.tab_path.exists():
            raise FileNotFoundError(self.tab_path)

        if ogr.GetDriverByName("MapInfo File") is None:
            raise RuntimeError("GDAL MapInfo File driver not available")
        if ogr.GetDriverByName("ESRI Shapefile") is None:
            raise RuntimeError("GDAL ESRI Shapefile driver not available")

    @staticmethod
    def _pg_connection_string(
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
        """
        if isinstance(connection, str):
            return connection

        return (
            f"PG:host={connection['host']} "
            f"port={connection.get('port', 5432)} "
            f"dbname={connection['dbname']} "
            f"user={connection['user']} "
            f"password={connection['password']} "
            f"schemas={schema}"
        )

    @staticmethod
    def _list_layers(ds, tables: Optional[Iterable[str]] = None) -> List[str]:
        """Description : List layer names in a GDAL dataset.

        Args:
            ds: Open GDAL dataset.
            tables (Optional[Iterable[str]], optional): Optional allow-list of
                layer names. If provided, only matching names are returned.

        Returns:
            List[str]: Layer names in dataset order.
        """
        layers = [ds.GetLayerByIndex(i).GetName() for i in range(ds.GetLayerCount())]
        if tables:
            allowed = set(tables)
            layers = [layer for layer in layers if layer in allowed]
        return layers

    @staticmethod
    def _run_parallel(items: Iterable[Any], func) -> None:
        """Description : Execute item-wise work in a shared thread pool.

        Args:
            items (Iterable[Any]): Work items to process.
            func (Callable[[Any], Any]): Worker function called once per item.

        Returns:
            None
        """
        with ThreadPoolExecutor(max_workers=GEOFILEOPS_THREADS) as exe:
            futures = [exe.submit(func, item) for item in items]
            for future in as_completed(futures):
                future.result()

    @staticmethod
    def _cleanup_sidecar(path: Path) -> None:
        """Description : Remove existing dataset files with the same stem.

        Args:
            path (Path): Primary path (`.tab` or `.shp`) whose sidecar files
                should be deleted.

        Returns:
            None
        """
        for candidate in path.parent.glob(f"{path.stem}.*"):
            if candidate.is_file():
                candidate.unlink()

    def _iter_tabfiles(self, tables: Optional[Iterable[str]] = None) -> List[Path]:
        """Description : Resolve source TAB files for processing.

        Args:
            tables (Optional[Iterable[str]], optional): Optional list of file stems
                (layer names) to include.

        Returns:
            List[Path]: Ordered list of `.tab` files to process.
        """
        if self.tab_path.is_file():
            files = [self.tab_path]
        else:
            files = sorted(self.tab_path.glob("*.tab"))

        if tables:
            allowed = set(tables)
            files = [path for path in files if path.stem in allowed]
        return files

    def tab2pg(
        self,
        connection: Union[str, Dict[str, Any]],
        *,
        schema: str = "public",
        overwrite: bool = False,
        tables: Optional[Iterable[str]] = None,
    ) -> None:
        """Description : Import TAB datasets into PostgreSQL/PostGIS.

        Args:
            connection (Union[str, Dict[str, Any]]): PostgreSQL connection
                information in string or mapping form.
            schema (str, optional): Target schema for created layers.
                Defaults to ``"public"``.
            overwrite (bool, optional): If ``True``, allow replacing existing
                target layers. Defaults to ``False``.
            tables (Optional[Iterable[str]], optional): Optional subset of
                TAB stems to import.

        Returns:
            None
        """
        pg_conn = self._pg_connection_string(connection, schema=schema)
        files = self._iter_tabfiles(tables)

        def worker(tab_file: Path) -> None:
            src_ds = ogr.Open(str(tab_file))
            if src_ds is None:
                raise RuntimeError(f"Failed to open TAB file: {tab_file}")
            layer_name = src_ds.GetLayerByIndex(0).GetName()

            options = gdal.VectorTranslateOptions(
                format="PostgreSQL",
                layers=[layer_name],
                geometryType="PROMOTE_TO_MULTI",
                layerCreationOptions=[
                    f"SCHEMA={schema}",
                    "OVERWRITE=YES" if overwrite else "OVERWRITE=NO",
                ],
            )
            gdal.VectorTranslate(pg_conn, src_ds, options=options)

        self._run_parallel(files, worker)

    def pg2tab(
        self,
        connection: Union[str, Dict[str, Any]],
        *,
        schema: str = "public",
        tables: Optional[Iterable[str]] = None,
        overwrite: bool = True,
    ) -> None:
        """Description : Export PostgreSQL/PostGIS layers to TAB datasets.

        Args:
            connection (Union[str, Dict[str, Any]]): PostgreSQL connection
                information in string or mapping form.
            schema (str, optional): Source schema filter. Defaults to ``"public"``.
            tables (Optional[Iterable[str]], optional): Optional subset of
                layer names to export.
            overwrite (bool, optional): If ``True``, existing output files for
                a layer are removed before writing.

        Returns:
            None
        """
        pg_conn = self._pg_connection_string(connection, schema=schema)
        src_ds = ogr.Open(pg_conn)
        if src_ds is None:
            raise RuntimeError("Failed to open PostgreSQL source")

        output_dir = self.tab_path if self.tab_path.is_dir() else self.tab_path.parent
        output_dir.mkdir(parents=True, exist_ok=True)

        layers = self._list_layers(src_ds, tables)

        def worker(layer_name: str) -> None:
            src = ogr.Open(pg_conn)
            if src is None:
                raise RuntimeError("Worker failed to open PostgreSQL source")
            tab_path = output_dir / f"{layer_name}.tab"
            if overwrite:
                self._cleanup_sidecar(tab_path)
            options = gdal.VectorTranslateOptions(
                format="MapInfo File",
                layers=[layer_name],
            )
            gdal.VectorTranslate(str(tab_path), src, options=options)

        self._run_parallel(layers, worker)

    def tab2shp(
        self,
        output_dir: PathLike,
        *,
        tables: Optional[Iterable[str]] = None,
        overwrite: bool = True,
    ) -> None:
        """Description : Convert TAB datasets to ESRI Shapefile format.

        Args:
            output_dir (PathLike): Destination directory for generated `.shp`
                and sidecar files.
            tables (Optional[Iterable[str]], optional): Optional subset of TAB
                stems to export.
            overwrite (bool, optional): If ``True``, existing output files for
                a layer are removed before writing.

        Returns:
            None
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        files = self._iter_tabfiles(tables)

        def worker(tab_file: Path) -> None:
            src_ds = ogr.Open(str(tab_file))
            if src_ds is None:
                raise RuntimeError(f"Failed to open TAB file: {tab_file}")
            layer_name = src_ds.GetLayerByIndex(0).GetName()
            shp_path = output_dir / f"{layer_name}.shp"
            if overwrite:
                self._cleanup_sidecar(shp_path)

            options = gdal.VectorTranslateOptions(
                format="ESRI Shapefile",
                layers=[layer_name],
            )
            gdal.VectorTranslate(str(shp_path), src_ds, options=options)

        self._run_parallel(files, worker)
