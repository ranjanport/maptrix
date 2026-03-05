from osgeo import ogr, gdal

path = "./resources/test.gdb"

print("GDAL version:", gdal.VersionInfo())
print("OpenFileGDB driver:", ogr.GetDriverByName("OpenFileGDB"))

ds = ogr.Open(path, gdal.OF_VECTOR)

print("Dataset:", ds)

if ds:
    print("Layers:")
    for i in range(ds.GetLayerCount()):
        print(ds.GetLayerByIndex(i).GetName())