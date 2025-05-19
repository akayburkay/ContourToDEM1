import os
import numpy as np
from osgeo import gdal, ogr, osr
import sys

def contours_to_dem(input_shp_path, output_tif_path, resolution=10, z_field="YUKS_NUM"):
    try:
        gdal.UseExceptions()   #GDAL/OGR libraries are based on C++ and generally use silent error handling methods when errors occur.
        ogr.UseExceptions()
        
        try:
            print(f"{input_shp_path} opening file...")
            contour_ds = ogr.Open(input_shp_path)
            if contour_ds is None:
                raise Exception(f"Open file not found: {input_shp_path}")
            
            contour_layer = contour_ds.GetLayer()
            feature_count = contour_layer.GetFeatureCount()
            print(f"{feature_count} curves found.")
            
            # Elevation field control
            layer_defn = contour_layer.GetLayerDefn()
            field_names = [layer_defn.GetFieldDefn(i).GetName() for i in range(layer_defn.GetFieldCount())]
            
            if z_field not in field_names:
                raise Exception(f"'{z_field}' alanı shapefileda bulunamadı. Mevcut alanlar: {', '.join(field_names)}")
            
            srs = contour_layer.GetSpatialRef()
            if srs is None:
                raise Exception("coğrafi referans bulunamadı")
            
            x_min, x_max, y_min, y_max = contour_layer.GetExtent()    #bbox
            print(f"Veri kapsamı: X({x_min:.2f}, {x_max:.2f}), Y({y_min:.2f}, {y_max:.2f})")
            
            elev_values = []
            contour_layer.ResetReading()   
            for feature in contour_layer:
                elev = feature.GetField(z_field)
                if elev is not None:
                    elev_values.append(float(elev))
            
            if not elev_values:
                raise Exception(f"'{z_field}' geçerli yükseklik değeri bulunamadı")
            
            print(f"Yükseklik değer aralığı: Min={min(elev_values):.2f}, Max={max(elev_values):.2f}")
            
            # DEM boyutlarını hesapla
            x_size = int((x_max - x_min) / resolution) #The goal is to calculate how many pixels will be horizontal and vertical
            y_size = int((y_max - y_min) / resolution)
            print(f"DEM boyutları: {x_size}x{y_size} piksel")
            

            output_dir = os.path.dirname(output_tif_path)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir)
                print(f"Çıkış klasörü oluşturuldu: {output_dir}")
            

            driver = gdal.GetDriverByName("GTiff")
            print("DEM dosyası oluşturuluyor...")
            dem_ds = driver.Create(
                output_tif_path,
                x_size,
                y_size,
                1, #bant 
                gdal.GDT_Float32 
            )
            
            if dem_ds is None:
                raise Exception("DEM dosyası oluşturulamadı")
            
            # Coğrafi referans ve dönüşüm bilgilerini ayarla
            geotransform = (
                x_min,  # Üst X
                resolution,  # Piksel genişliği
                0,  # Dönüş
                y_max,  # Üst Y
                0,  # Dönüş
                -resolution  # Piksel yüksekliği (negatif)
            )
            dem_ds.SetProjection(srs.ExportToWkt())
            dem_ds.SetGeoTransform(geotransform)
            

            band = dem_ds.GetRasterBand(1)
            nodata_value = -9999
            band.SetNoDataValue(nodata_value)
            band.Fill(nodata_value)
            
            print("Eğriler rasterlaştırılıyor...")
            options = [
                f"ATTRIBUTE={z_field}",
                "ALL_TOUCHED=TRUE"
            ]
            
            gdal.RasterizeLayer(
                dem_ds,  #raster
                [1],  # band 1
                contour_layer,  # vektör katman
                None, None,  # Maske ve transform (otomatik)
                [0],  # Başlangıç değeri
                options
            )
            #control
            data = band.ReadAsArray()
            valid_pixels = np.sum(data != nodata_value)
            print(f"Rasterleştirme tamamlandı. {valid_pixels} adet geçerli piksel oluşturuldu.")
            
            if valid_pixels == 0:
                raise Exception("Rasterleştirme başarısız")
            
            #(siyah çıktı sorununu önlemek için)
            min_val = np.min(data[data != nodata_value])
            max_val = np.max(data[data != nodata_value])
            print(f"Raster veri aralığı: Min={min_val:.2f}, Max={max_val:.2f}")
            
            # boşluk doldurma için interp. işlemi fill_nodata adındaki fonksiyon sayesinde 
            try:
                print("NoData alanları dolduruluyor...")
                filled_dem = fill_nodata(data, geotransform, nodata_value)
                band.WriteArray(filled_dem)
                band.FlushCache()  #bellekten diske yazar bu
            except Exception as e:
                print(f"Uyarı: DEM doldurma işlemi başarısız oldu, ham DEM kaydediliyor. Hata: {str(e)}")
            
            #doğrulama
            band.ComputeStatistics(False)
            print(f"DEM başarıyla oluşturuldu: {output_tif_path}")
            print(f"Son DEM istatistikleri: Min={band.GetMinimum():.2f}, Max={band.GetMaximum():.2f}")
            
            return True
            
        except Exception as e:
            print(f"Hata oluştu: {str(e)}", file=sys.stderr)
            return False
        
        finally:
            # Veri setlerini kapat
            if 'dem_ds' in locals():
                dem_ds = None
            if 'contour_ds' in locals():
                contour_ds = None
    
    except Exception as e:
        print(f"Beklenmeyen bir hata oluştu: {str(e)}", file=sys.stderr)
        return False

def fill_nodata(data, geotransform, nodata_value, max_search_dist=100, smooth_iterations=0):
    """
    DEM'deki NoData değerlerini doldurur

    data -- DEM verisi
    geotransform -- Coğrafi dönüşüm
    nodata_value -- NoData değeri
    max_search_dist -- Pikseli doldurma için maksimum arama mesafesi için
    smooth_iterations -- Yumuşatma
    """
    try:
        mask = (data == nodata_value)

        from scipy.ndimage import distance_transform_edt
        
        valid_cells = np.argwhere(~mask)
        
        if len(valid_cells) == 0:
            return data  # Doldurulacak veri yok
        
        # Her NoData hücresi için en yakın valid hücrenin indeksini bul
        x_res = geotransform[1]
        y_res = abs(geotransform[5])
        
        distances, indices = distance_transform_edt(
            mask,
            return_indices=True,
            sampling=[x_res, y_res]
        )
        

        fill_mask = mask & (distances <= max_search_dist)

        filled_data = data.copy()
        filled_data[fill_mask] = data[tuple(indices[:, fill_mask])]
        
        #yumuşatma
        for _ in range(smooth_iterations):
            filled_data = smooth_dem(filled_data, mask)
        
        return filled_data
    
    except Exception as e:
        print(f"Doldurma işlemi sırasında hata: {str(e)}", file=sys.stderr)
        raise

def smooth_dem(data, mask):
    """
    DEM verisini yumuşatır (NoData alanları etkilemez)
    """
    try:
        from scipy.ndimage import uniform_filter
        
        smoothed = uniform_filter(data, size=3)
        
        # Sadece orijinal verinin NoData olmadığı yerleri koru
        result = data.copy()
        result[~mask] = smoothed[~mask]
        
        return result
    
    except Exception as e:
        print(f"Yumuşatma işlemi sırasında hata: {str(e)}", file=sys.stderr)
        raise

if __name__ == "__main__":
    shp1 = r"C:\Users\Msi\Desktop\prjshp\a1.shp"
    output_tif = r"C:\Users\Msi\Desktop\dem_raster\dem_1.tif"
    
    success = contours_to_dem(shp1, output_tif, resolution=10, z_field="YUKS_NUM")
    
    if success:
        print("İşlem başarıyla tamamlandı.")
        sys.exit(0)
    else:
        print("İşlem başarısız,beceremedim :d", file=sys.stderr)
        sys.exit(1)