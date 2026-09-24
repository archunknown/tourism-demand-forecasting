import openmeteo_requests
import requests_cache
from retry_requests import retry
import pandas as pd

def obtener_clima_historico(latitud=-13.5319, longitud=-71.9675, fecha_inicio="2019-01-01", fecha_fin="2025-12-31"):
    """
    Consulta la API gratuita de Open-Meteo para obtener datos climáticos históricos
    y agruparlos de forma mensual (temperaturas y lluvias).
    """
    # Guardamos en caché las respuestas para no saturar la API con llamadas repetidas
    cache_session = requests_cache.CachedSession('.cache', expire_after=-1)
    retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
    openmeteo = openmeteo_requests.Client(session=retry_session)

    # Endpoint oficial de la API de clima histórico
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": latitud,
        "longitude": longitud,
        "start_date": fecha_inicio,
        "end_date": fecha_fin,
        "daily": ["temperature_2m_mean", "temperature_2m_max", "temperature_2m_min", "precipitation_sum"],
        "timezone": "America/Lima"
    }

    # Hacemos la consulta a la API
    responses = openmeteo.weather_api(url, params=params)
    daily = responses[0].Daily()

    # Construimos el rango de fechas diarias
    fechas_diarias = pd.date_range(
        start=pd.to_datetime(daily.Time(), unit="s", utc=True).tz_convert("America/Lima").tz_localize(None),
        end=pd.to_datetime(daily.TimeEnd(), unit="s", utc=True).tz_convert("America/Lima").tz_localize(None),
        freq=pd.Timedelta(seconds=daily.Interval()),
        inclusive="left"
    )

    # Extraemos los valores numéricos que nos devuelve la API
    df_diario = pd.DataFrame({
        "fecha": fechas_diarias,
        "temp_mean": daily.Variables(0).ValuesAsNumpy(),
        "temp_max": daily.Variables(1).ValuesAsNumpy(),
        "temp_min": daily.Variables(2).ValuesAsNumpy(),
        "precipitacion": daily.Variables(3).ValuesAsNumpy()
    })

    # Extraemos año y mes para poder agrupar mensualmente
    df_diario["ANIO"] = df_diario["fecha"].dt.year
    df_diario["ID_MES"] = df_diario["fecha"].dt.month

    # Agrupamos por mes: sacamos promedios de temperatura y suma de lluvias
    df_mensual = df_diario.groupby(["ANIO", "ID_MES"]).agg({
        "temp_mean": "mean",
        "temp_max": "max",
        "temp_min": "min",
        "precipitacion": "sum"
    }).reset_index()

    # Redondeamos los decimales para dejar los datos limpios
    df_mensual["temp_mean"] = df_mensual["temp_mean"].round(2)
    df_mensual["temp_max"] = df_mensual["temp_max"].round(2)
    df_mensual["temp_min"] = df_mensual["temp_min"].round(2)
    df_mensual["precipitacion"] = df_mensual["precipitacion"].round(2)

    return df_mensual
