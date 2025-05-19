from osgeo import ogr, gdal

shapefile_path = r"C:\Users\Msi\Desktop\prjshp\a1.shp"

def open_datasource(shapefile_path):
    driver = ogr.GetDriverByName("ESRI Shapefile")
    datasource=driver.Open(shapefile_path,1)  ##write mode
    if datasource is None:
        print(f"File not opened: {shapefile_path}")
    return datasource

def convert_field_to_numeric(shapefile_path, old_field="YUKSEKLIK", new_field="ELEV"):
    datasource = open_datasource(shapefile_path)
    if datasource is None:
        print("File not opened")
        return

    layer = datasource.GetLayer()
    layer_defn = layer.GetLayerDefn()

    if layer_defn.GetFieldIndex(new_field) == -1:   #control
        field_defn = ogr.FieldDefn(new_field, ogr.OFTReal)
        layer.CreateField(field_defn)

    for feature in layer:
        value = feature.GetField(old_field)
        try:
            num = float(value)
        except (ValueError, TypeError):        
            num = None
        feature.SetField(new_field, num)
        layer.SetFeature(feature)

    print(f"'{old_field}' → '{new_field}' completed conversion.")
    datasource = None

def projection_info(shapefile_path):
    datasource = open_datasource(shapefile_path)
    if datasource is None:
        print(f"File not opened: {shapefile_path}")
        return

    layer = datasource.GetLayer()
    spatial_ref = layer.GetSpatialRef()

    if spatial_ref is None:
        print(f"projection information not found: {shapefile_path}")
        return

    spatial_ref.AutoIdentifyEPSG()
    authority_code = spatial_ref.GetAuthorityCode(None)
    if authority_code:
        print(f"🌍 EPSG code: EPSG:{authority_code}")
    else:
        print("EPSG Code not found")
    print("-" * 25)

def check_field_type(shapefile_path, field_name="ELEV"):
    datasource = open_datasource(shapefile_path)
    if datasource is None:
        print(f"File not opened: {shapefile_path}")
        return

    layer = datasource.GetLayer()
    layer_defn = layer.GetLayerDefn()

    field_index = layer_defn.GetFieldIndex(field_name)
    if field_index == -1:
        print(f"❗ '{field_name}' field not found: {shapefile_path}")
        return

    field_defn = layer_defn.GetFieldDefn(field_index)
    field_type = field_defn.GetType()
    field_type_name = field_defn.GetFieldTypeName(field_type)

    print(f"✅ {shapefile_path}  '{field_name}' field type: {field_type_name}")
    print("-" * 60)

def detect_geometry_type(shapefile_path):
    datasource = open_datasource(shapefile_path)
    if datasource is None:
        print("File not opened.")
        return

    layer = datasource.GetLayer()
    geom_type = layer.GetGeomType()
    geom_type_name = ogr.GeometryTypeToName(geom_type)

    print(f"✅ {shapefile_path} geometrisi: {geom_type_name}")
    print("-" * 30)

projection_info(shapefile_path)
convert_field_to_numeric(shapefile_path)
check_field_type(shapefile_path)
detect_geometry_type(shapefile_path)

print("🛠️ GDAL version:", gdal.__version__)
