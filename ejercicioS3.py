import numpy as np # Not strictly used in this streamlined version, but kept if you plan future numerical enhancements
import math as m
import requests # Necesitas instalar esta librería: pip install requests

# --- Constantes y Tarifas de Cotización (puedes ajustarlas aquí) ---
PRECIO_LITRO_BENCINA = 1000 # CLP por litro (valor fijo, puedes actualizarlo manualmente)
CONSUMO_BARREDORA_LT_HR = 8 # Litros por hora
COSTO_TRASLADO_KM = 2300 # CLP por kilómetro (Aplicable a barredora y residuos no peligrosos fuera GC)

TARIFA_RESIDUOS_NO_PELIGROSOS_KG = 120 # CLP por kilogramo
COSTO_TRASLADO_GRAN_CONCEPCION_NO_PEL = 50000 # CLP (Costo fijo dentro del Gran Concepción)
# Centro de disposición para no peligrosos: Copiulemu (Asumido como destino para cálculo fuera GC)

ARRIENDO_TOLVA_PELIGROSOS = 100000 # CLP
TRANSPORTE_PELIGROSOS_FIJO = 250000 # CLP
# Centro de disposición para peligrosos: Hidronor (Costos fijos, no requiere cálculo de ruta)

# Coordenadas aproximadas de los centros de disposición
# ¡IMPORTANTE! Ajusta estas coordenadas a las ubicaciones EXACTAS de tus centros.
COORD_COPIULEMU_LAT = -36.9038
COORD_COPIULEMU_LON = -72.8239 

COORD_HIDRONOR_LAT = -36.6806 
COORD_HIDRONOR_LON = -73.0805 


# --- Función para convertir Grados, Minutos, Segundos a Decimal ---
def dms_to_decimal(dms_str):
    """
    Convierte una cadena de texto con formato Grados°Minutos′Segundos″ Dirección
    (ej: "35°25′37″ Sur") a un valor decimal de latitud/longitud.
    Maneja direcciones "Sur" y "Oeste" asignando un valor negativo.
    """
    dms_str = dms_str.replace('°', ' ').replace('′', ' ').replace('″', ' ').strip()
    
    parts = dms_str.split()
    
    if len(parts) < 3:
        raise ValueError("Formato de entrada incorrecto. Se esperan al menos grados, minutos, segundos.")

    degrees = float(parts[0])
    minutes = float(parts[1])
    seconds = float(parts[2])

    decimal_value = degrees + (minutes / 60) + (seconds / 3600)

    dms_str_lower = dms_str.lower()
    if 'sur' in dms_str_lower or parts[-1].lower() == 's' or \
       'oeste' in dms_str_lower or parts[-1].lower() == 'o':
        decimal_value *= -1
    
    return decimal_value

# --- Función para obtener coordenadas de una dirección usando la API de Nominatim (OSM) ---
def get_coordinates_from_address(address):
    base_url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": address,
        "format": "json",
        "limit": 1
    }
    headers = {
        "User-Agent": "MiAplicacionPythonDeCotizacion/1.0 (tu_email@example.com)"
    }

    print(f"Buscando coordenadas para: '{address}' con Nominatim...")
    try:
        response = requests.get(base_url, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()

        if data:
            latitude = float(data[0]['lat'])
            longitude = float(data[0]['lon'])
            print(f"✅ Encontrado: Lat={latitude}, Lon={longitude}")
            return latitude, longitude
        else:
            print(f"❌ No se encontraron coordenadas para la dirección: '{address}'")
            return None, None
    except requests.exceptions.RequestException as e:
        print(f"❌ Error de conexión con la API de Nominatim: {e}")
        print("Asegúrate de tener conexión a internet.")
        return None, None
    except Exception as e:
        print(f"⚠️ Ocurrió un error inesperado al procesar la dirección desde Nominatim: {e}")
        return None, None

# --- Función: Obtener distancia en ruta usando la API de OSRM ---
def get_route_distance(lat1, lon1, lat2, lon2):
    """
    Calcula la distancia de la ruta en coche entre dos puntos geográficos
    utilizando la API pública de OSRM (Open Source Routing Machine).
    Devuelve la distancia en kilómetros.
    """
    # Formato de URL para OSRM: /route/v1/{profile}/{lon1},{lat1};{lon2},{lat2}
    # Usamos 'driving' como perfil para distancia en coche.
    base_url_osrm = f"http://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}"
    params = {
        "overview": "false", # Solo necesitamos la distancia, no la geometría de la ruta
        "steps": "false",
        "alternatives": "false"
    }
    headers = {
        "User-Agent": "MiAplicacionPythonDeCotizacion/1.0 (tu_email@example.com)"
    }

    print(f"Calculando distancia en ruta entre ({lat1:.4f}, {lon1:.4f}) y ({lat2:.4f}, {lon2:.4f}) con OSRM...")
    try:
        response = requests.get(base_url_osrm, params=params, headers=headers)
        response.raise_for_status() # Lanza un error para códigos de estado HTTP erróneos
        route_data = response.json()

        if route_data and route_data['code'] == 'Ok' and route_data['routes']:
            # La distancia en OSRM está en metros
            distance_meters = route_data['routes'][0]['distance']
            distance_km = distance_meters / 1000
            print(f"✅ Distancia en ruta encontrada: {distance_km:.2f} km")
            return distance_km
        else:
            print(f"❌ No se pudo calcular la ruta con OSRM. Código de respuesta: {route_data.get('code', 'N/A')}")
            if route_data.get('code') == 'NoRoute':
                print("Esto puede deberse a que no hay una ruta de carretera entre los puntos, o los puntos están demasiado cerca/lejos.")
            return None
    except requests.exceptions.RequestException as e:
        print(f"❌ Error de conexión con la API de OSRM: {e}")
        print("Asegúrate de tener conexión a internet y que el servicio de OSRM esté disponible.")
        return None
    except Exception as e:
        print(f"⚠️ Ocurrió un error inesperado al procesar la ruta desde OSRM: {e}")
        return None

# ---------------------------------------
# LÓGICA DE COTIZACIÓN DE SERVICIOS
# ---------------------------------------

# --- Función auxiliar para procesar un solo punto de entrada ---
def process_point_input(input_str, point_number):
    lat, lon = None, None
    
    # Priorizamos detección de DMS por sus símbolos únicos
    if '°' in input_str or '′' in input_str or '″' in input_str:
        print(f"Punto {point_number}: Formato DMS detectado.")
        try:
            if ',' in input_str:
                lat_str, lon_str = [s.strip() for s in input_str.split(',')]
                lat = dms_to_decimal(lat_str)
                lon = dms_to_decimal(lon_str)
            else:
                print(f"❌ Error: El formato DMS para el Punto {point_number} parece incompleto (falta ',' entre latitud y longitud).")
        except (ValueError, IndexError) as e:
            print(f"❌ Error al procesar DMS para el Punto {point_number}: {e}. Asegúrate del formato D°M′S″ Dirección,D°M′S″ Dirección.")
        
        # Si a pesar del intento DMS no se obtuvieron coordenadas válidas
        if lat is None or lon is None:
            print(f"Intentando obtener coordenadas para Punto {point_number} como dirección...")
            lat, lon = get_coordinates_from_address(input_str) # Intentar como dirección
    else:
        # Si no hay símbolos DMS, asumimos que es una dirección
        print(f"Punto {point_number}: Formato de Dirección detectado.")
        lat, lon = get_coordinates_from_address(input_str)
        
    return lat, lon

# --- Función para cotizar barredora ---
def cotizar_barredora():
    print("\n🧹 Cotización de Servicio de Barredora")
    
    lat_origen, lon_origen = None, None
    while lat_origen is None or lon_origen is None:
        origen_input = input("Ingrese dirección o coordenadas del lugar de inicio del servicio: ")
        lat_origen, lon_origen = process_point_input(origen_input, 1)
        if lat_origen is None or lon_origen is None:
            print("No se pudieron obtener las coordenadas de origen. Por favor, intente de nuevo.")
            
    lat_destino, lon_destino = None, None
    while lat_destino is None or lon_destino is None:
        destino_input = input("Ingrese dirección o coordenadas del lugar de finalización del servicio: ")
        lat_destino, lon_destino = process_point_input(destino_input, 2)
        if lat_destino is None or lon_destino is None:
            print("No se pudieron obtener las coordenadas de destino. Por favor, intente de nuevo.")

    distancia_km = get_route_distance(lat_origen, lon_origen, lat_destino, lon_destino)

    if distancia_km is None:
        print("No se pudo calcular la distancia en ruta para la cotización de barredora. No se puede generar la cotización.")
        return

    try:
        horas_servicio_str = input("Ingrese la duración estimada del servicio en horas (ej: 2.5): ")
        horas_servicio = float(horas_servicio_str)
        if horas_servicio <= 0:
            print("Las horas de servicio deben ser un valor positivo.")
            return

        costo_combustible = CONSUMO_BARREDORA_LT_HR * horas_servicio * PRECIO_LITRO_BENCINA
        # Se asume que el traslado se cobra por la distancia de ida y vuelta
        costo_traslado = (distancia_km * 2) * COSTO_TRASLADO_KM 
        costo_total = costo_combustible + costo_traslado

        print(f"\n--- Resumen de Cotización Barredora ---")
        print(f"Distancia de traslado (ida y vuelta): {distancia_km * 2:.2f} km")
        print(f"Costo de Combustible ({horas_servicio:.1f} horas): ${costo_combustible:,.0f} CLP")
        print(f"Costo de Traslado ({distancia_km * 2:.2f} km): ${costo_traslado:,.0f} CLP")
        print(f"Costo Total Estimado del Servicio: ${costo_total:,.0f} CLP")
        print("---------------------------------------")

    except ValueError:
        print("Entrada inválida para las horas de servicio. Por favor, ingrese un número.")
    except Exception as e:
        print(f"Ocurrió un error inesperado durante la cotización: {e}")

# --- Función para cotizar transporte de residuos no peligrosos ---
def cotizar_residuos_no_peligrosos():
    print("\n♻️ Cotización de Transporte de Residuos No Peligrosos")

    lat_origen, lon_origen = None, None
    while lat_origen is None or lon_origen is None:
        origen_input = input("Ingrese dirección o coordenadas del punto de recolección: ")
        lat_origen, lon_origen = process_point_input(origen_input, 1)
        if lat_origen is None or lon_origen is None:
            print("No se pudieron obtener las coordenadas de origen. Por favor, intente de nuevo.")
            
    try:
        peso_kg_str = input("Ingrese el peso de los residuos en kilogramos (kg): ")
        peso_kg = float(peso_kg_str)
        if peso_kg <= 0:
            print("El peso debe ser un valor positivo.")
            return

        costo_residuos = peso_kg * TARIFA_RESIDUOS_NO_PELIGROSOS_KG

        # Preguntar si está dentro del Gran Concepción
        ubicacion_gc = input("¿El punto de recolección está dentro del Gran Concepción? (si/no): ").lower().strip()
        
        costo_traslado = 0
        distancia_total_info = "N/A"

        if ubicacion_gc == 'si':
            costo_traslado = COSTO_TRASLADO_GRAN_CONCEPCION_NO_PEL
            distancia_total_info = "Dentro Gran Concepción (costo fijo)"
            print("Aplicando tarifa de traslado fijo para Gran Concepción.")
        else:
            # Si no está en Gran Concepción, calcular distancia a Copiulemu
            print("Calculando costo de traslado fuera del Gran Concepción hacia Copiulemu...")
            distancia_a_copiulemu = get_route_distance(lat_origen, lon_origen, COORD_COPIULEMU_LAT, COORD_COPIULEMU_LON)
            if distancia_a_copiulemu is None:
                print("No se pudo calcular la distancia a Copiulemu. No se puede cotizar el traslado.")
                return
            # Considerar viaje de ida y vuelta para el cálculo del traslado
            costo_traslado = (distancia_a_copiulemu * 2) * COSTO_TRASLADO_KM 
            distancia_total_info = f"{distancia_a_copiulemu * 2:.2f} km (ida y vuelta a Copiulemu)"


        costo_total = costo_residuos + costo_traslado

        print(f"\n--- Resumen de Cotización Residuos No Peligrosos ---")
        print(f"Peso de Residuos: {peso_kg:.2f} kg")
        print(f"Costo por Residuos: ${costo_residuos:,.0f} CLP")
        print(f"Distancia de Traslado: {distancia_total_info}")
        print(f"Costo de Traslado: ${costo_traslado:,.0f} CLP")
        print(f"Costo Total Estimado del Servicio: ${costo_total:,.0f} CLP")
        print("---------------------------------------")

    except ValueError:
        print("Entrada inválida para el peso. Por favor, ingrese un número.")
    except Exception as e:
        print(f"Ocurrió un error inesperado durante la cotización: {e}")

# --- Función para cotizar transporte de residuos peligrosos ---
def cotizar_residuos_peligrosos():
    print("\n☣️ Cotización de Transporte de Residuos Peligrosos")
    
    print(f"El centro de disposición para residuos peligrosos es Hidronor. Los costos son fijos:")
    print(f"  - Arriendo de tolva: ${ARRIENDO_TOLVA_PELIGROSOS:,.0f} CLP")
    print(f"  - Transporte fijo: ${TRANSPORTE_PELIGROSOS_FIJO:,.0f} CLP")

    costo_total = ARRIENDO_TOLVA_PELIGROSOS + TRANSPORTE_PELIGROSOS_FIJO

    print(f"\n--- Resumen de Cotización Residuos Peligrosos ---")
    print(f"Costo Total Estimado del Servicio: ${costo_total:,.0f} CLP")
    print("---------------------------------------")


# ---------------------------------------
# MENÚ PRINCIPAL SIMPLIFICADO
# ---------------------------------------
def menu():
    while True:
        print("\n===== MENÚ DE COTIZACIONES DE SERVICIOS =====")
        print("1. Cotización de Servicio de Barredora")
        print("2. Cotización de Transporte de Residuos No Peligrosos")
        print("3. Cotización de Transporte de Residuos Peligrosos")
        print("4. Salir")

        opcion = input("Seleccione una opción (1-4): ")

        if opcion == "1":
            cotizar_barredora()
        elif opcion == "2":
            cotizar_residuos_no_peligrosos()
        elif opcion == "3":
            cotizar_residuos_peligrosos()
        elif opcion == "4":
            print("¡Hasta pronto! Gracias por usar el sistema de cotizaciones 👋")
            break
        else:
            print("⚠️ Opción no válida. Intente de nuevo.")

# Ejecutar el menú principal
if __name__ == "__main__":
    menu()