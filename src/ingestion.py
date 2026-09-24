import os
import subprocess
import pandas as pd
from utils_climate import obtener_clima_historico

def descargar_si_falta(ruta_archivo, url):
    """
    Descarga el archivo desde el portal oficial si no existe localmente.
    """
    if not os.path.exists(ruta_archivo) or os.path.getsize(ruta_archivo) == 0:
        print(f"Descargando fuente: {os.path.basename(ruta_archivo)}...")
        # Usamos curl silencioso y siguiendo redirecciones de forma segura
        cmd = f'curl.exe -L -k -s -o "{ruta_archivo}" "{url}"'
        subprocess.run(cmd, shell=True, check=True)

def cargar_y_limpiar_sitios(ruta):
    """
    Lee y procesa el dataset de visitantes a sitios turísticos del MINCETUR.
    """
    df = pd.read_csv(ruta, sep=";", encoding="latin1")
    # Limpiamos caracteres invisibles en los nombres de columnas
    df.columns = [col.replace('\ufeff', '').strip() for col in df.columns]
    
    # Filtramos la categoría 'TOTAL' para evitar duplicar nacionales y extranjeros
    df_total = df[df['TIPO_VISITANTE'] == 'TOTAL'].copy()
    
    # Agrupamos por año y mes para obtener el total de visitas a sitios por mes
    df_mensual = df_total.groupby(['ANIO', 'ID_MES'])['NUMERO_VISITANTES'].sum().reset_index()
    df_mensual.rename(columns={'NUMERO_VISITANTES': 'visitantes_sitios_total'}, inplace=True)
    return df_mensual

def cargar_y_limpiar_emisivo(ruta):
    """
    Lee y procesa el dataset de turismo emisivo (peruanos viajando al exterior).
    """
    df = pd.read_csv(ruta, sep=";", encoding="latin1")
    df.columns = [col.replace('\ufeff', '').strip() for col in df.columns]
    
    # Sumamos los turistas emisivos agrupando por año y mes
    df_mensual = df.groupby(['ANIO', 'ID_MES'])['NUMERO_TURISTAS'].sum().reset_index()
    df_mensual.rename(columns={'NUMERO_TURISTAS': 'turistas_emisivo_total'}, inplace=True)
    return df_mensual

def cargar_y_limpiar_receptivo(ruta):
    """
    Lee y procesa el dataset de turismo receptivo (extranjeros ingresando a Perú).
    """
    df = pd.read_excel(ruta, sheet_name=0, engine="openpyxl")
    df.columns = [col.replace('\ufeff', '').strip() for col in df.columns]
    
    # Sumamos las llegadas internacionales agrupando por año y mes
    df_mensual = df.groupby(['ANIO', 'ID_MES'])['NUMERO_VISITANTES'].sum().reset_index()
    df_mensual.rename(columns={'NUMERO_VISITANTES': 'turistas_receptivo_total'}, inplace=True)
    return df_mensual

def ejecutar_pipeline_ingestion():
    print("=== INICIANDO FASE 1: INGESTION Y LIMPIEZA DE DATOS ===")
    
    # Definimos las rutas del proyecto
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    raw_dir = os.path.join(base_dir, "data", "raw")
    processed_dir = os.path.join(base_dir, "data", "processed")
    
    os.makedirs(raw_dir, exist_ok=True)
    os.makedirs(processed_dir, exist_ok=True)
    
    # URLs de descarga directa de los datos abiertos del MINCETUR
    urls = {
        "sitios_turisticos.csv": "https://datosabiertos.mincetur.gob.pe/DGIETA/Visitantes_sitios_turisticos_2019_2025.csv",
        "turismo_emisivo.csv": "https://www.datosabiertos.gob.pe/sites/default/files/Salida_turistas_peruanos_residentes.csv",
        "turismo_receptivo.xlsx": "https://datosabiertos.mincetur.gob.pe/DGIETA/Llegada_turistas_internacionales.xlsx"
    }
    
    # Paso 1: Aseguramos que los archivos brutos estén descargados
    for nombre, url in urls.items():
        descargar_si_falta(os.path.join(raw_dir, nombre), url)
        
    print("Procesando datasets del MINCETUR...")
    df_sitios = cargar_y_limpiar_sitios(os.path.join(raw_dir, "sitios_turisticos.csv"))
    df_emisivo = cargar_y_limpiar_emisivo(os.path.join(raw_dir, "turismo_emisivo.csv"))
    df_receptivo = cargar_y_limpiar_receptivo(os.path.join(raw_dir, "turismo_receptivo.xlsx"))
    
    # Paso 2: Unimos las tres fuentes de turismo por Año y Mes
    df_turismo = pd.merge(df_sitios, df_emisivo, on=['ANIO', 'ID_MES'], how='outer')
    df_turismo = pd.merge(df_turismo, df_receptivo, on=['ANIO', 'ID_MES'], how='outer')
    
    # Paso 3: Traemos los datos de clima histórico desde la API de Open-Meteo
    print("Consultando clima histórico desde API Open-Meteo...")
    df_clima = obtener_clima_historico(latitud=-13.5319, longitud=-71.9675, fecha_inicio="2019-01-01", fecha_fin="2025-12-31")
    
    # Paso 4: Consolidamos turismo + clima en un solo DataFrame
    df_consolidado = pd.merge(df_turismo, df_clima, on=['ANIO', 'ID_MES'], how='left')
    
    # Filtramos estrictamente el periodo histórico 2019 - 2025 (84 meses completos)
    df_consolidado = df_consolidado[(df_consolidado['ANIO'] >= 2019) & (df_consolidado['ANIO'] <= 2025)].copy()
    
    # Creamos la columna fecha estandarizada (YYYY-MM-01)
    df_consolidado['fecha'] = pd.to_datetime(
        df_consolidado['ANIO'].astype(str) + '-' + df_consolidado['ID_MES'].astype(str).str.zfill(2) + '-01'
    )
    
    # Calculamos la demanda consolidada (Sitios Turísticos + Turismo Receptivo)
    df_consolidado['demanda_total'] = df_consolidado['visitantes_sitios_total'].fillna(0) + df_consolidado['turistas_receptivo_total'].fillna(0)
    
    # Ordenamos cronológicamente y organizamos las columnas
    columnas_orden = [
        'fecha', 'ANIO', 'ID_MES', 'demanda_total', 
        'visitantes_sitios_total', 'turistas_receptivo_total', 'turistas_emisivo_total',
        'temp_mean', 'temp_max', 'temp_min', 'precipitacion'
    ]
    df_final = df_consolidado[columnas_orden].sort_values('fecha').reset_index(drop=True)
    
    # Paso 5: Guardamos el archivo final limpio
    ruta_salida = os.path.join(processed_dir, "datos_consolidados_limpios.csv")
    df_final.to_csv(ruta_salida, index=False, encoding="utf-8")
    
    print(f"\n¡Éxito! Dataset consolidado generado correctamente en:")
    print(f" -> {ruta_salida}")
    print(f" -> Filas totales: {len(df_final)} (84 meses de Enero 2019 a Diciembre 2025)")
    return df_final

if __name__ == "__main__":
    ejecutar_pipeline_ingestion()
