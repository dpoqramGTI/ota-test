import network
import machine
import time
import ntptime  # Módulo para obtener tiempo NTP
from umqtt.simple import MQTTClient
import ubinascii
from ota import OTAUpdater

# Configuración Wi-Fi
SSID = "Red de poquet"
PASSWORD = "poquet123"
#SSID = "Casa xiaomi"
#PASSWORD = "Dreamsfamily"

# Configuración GitHub OTA
firmware_url = "https://github.com/dpoqramGTI/ota-test/"

# Configuración MQTT
MQTT_BROKER = "192.168.99.236"
MQTT_PORT = 1883
MQTT_TOPIC = b"maquinas/estado"
CLIENT_ID = ubinascii.hexlify(network.WLAN().config('mac')).decode()

# Configuración del pin de la máquina con resistencia pull-up
PIN_MAQUINA = machine.Pin(5, machine.Pin.IN, pull=machine.Pin.PULL_UP)

# Configuración de los pines para los LEDs
LED_ENCENDIDO = machine.Pin(4, machine.Pin.OUT)
LED_APAGADO = machine.Pin(0, machine.Pin.OUT)

# Variables globales
estado_anterior = None
timestamp_correcto = None

# envia un mensaje avisando de que ha actualizado el firmware
def enviar_mensaje_actualizacion(cliente_mqtt):
    mensaje = f"{CLIENT_ID}:actualizado"
    try:
        cliente_mqtt.publish('maquina/firmware/update', mensaje, retain=True)
        print(f"Mensaje de actualización enviado: {mensaje}")
    except Exception as e:
        print("Error enviando el mensaje de actualización por MQTT:", e)
    

def check_firmware_update():
    ota_updater = OTAUpdater(SSID, PASSWORD, firmware_url, "main.py")
    ota_updater.download_and_install_update_if_available()

def suscribirse_a_reset_mqtt(cliente_mqtt):
    def callback(topic, msg):
        global estado_anterior
        print("Mensaje ota reset - recibido:", msg)
        if msg == b"reset":
            print("Reiniciando máquina...")
            machine.reset()
            estado_anterior = None

    cliente_mqtt.set_callback(callback)
    cliente_mqtt.subscribe("maquina/force_reset_ota")

def conectar_wifi_en_bucle():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    while not wlan.isconnected():
        print("Conectando a la red Wi-Fi...")
        wlan.connect(SSID, PASSWORD)
        timeout = 10
        while not wlan.isconnected() and timeout > 0:
            time.sleep(1)
            timeout -= 1
            print("Esperando conexión a Wi-Fi...", timeout)
        if wlan.isconnected():
            print("Conectado a Wi-Fi. IP:", wlan.ifconfig()[0])
        else:
            print("Error: No se pudo conectar a la red Wi-Fi. Reintentando en 5 segundos...")
            time.sleep(5)


def conectar_mqtt_en_bucle(cliente_mqtt):
    while True:
        try:
            print("Intentando conectar al broker MQTT...")
            cliente_mqtt.connect()
            print("Conectado al broker MQTT.")
            return  # Salir del bucle si la conexión es exitosa
        except Exception as e:
            print(f"Error al conectar al broker MQTT: {e}")
            print("Reintentando en 5 segundos...")
            time.sleep(5)


def sincronizar_ntp():
    global timestamp_correcto
    try:
        ntptime.settime()
        print("Hora sincronizada con NTP.")
    except Exception as e:
        print("Error al sincronizar con NTP:", e)


def enviar_estado(cliente_mqtt):
    global estado_anterior, timestamp_correcto
    estado_actual = "encendido" if PIN_MAQUINA.value() == 0 else "apagado"
    print("PIN_MAQUINA.value():", PIN_MAQUINA.value())
    # Actualizar los LEDs según el estado de la máquina
    if estado_actual == "encendido":
        LED_ENCENDIDO.value(1)
        LED_APAGADO.value(0)
    else:
        LED_ENCENDIDO.value(0)
        LED_APAGADO.value(1)

    # Si el estado cambió, enviar el mensaje al broker MQTT
    if estado_actual != estado_anterior:
        timestamp_correcto = time.mktime(time.localtime()) + 946684800  # Ajuste del tiempo
        mensaje = f"{CLIENT_ID}:{estado_actual}:{timestamp_correcto}"
        try:
            cliente_mqtt.publish(MQTT_TOPIC, mensaje, retain=True)
            print(f"Estado enviado: {mensaje}")
            estado_anterior = estado_actual
        except Exception as e:
            print("Error enviando el estado por MQTT:", e)

def main():
    # Conectar al Wi-Fi en un bucle hasta que sea exitoso
    conectar_wifi_en_bucle()

    # Verificar actualizaciones de firmware al inicio solo si hay Wi-Fi
    if network.WLAN(network.STA_IF).isconnected():
        check_firmware_update()
    else:
        print("Error: No se puede verificar actualizaciones de firmware porque no hay conexión Wi-Fi.")
    # Sincronizar la hora NTP (opcional)
    sincronizar_ntp()

    # Crear cliente MQTT
    cliente_mqtt = MQTTClient(CLIENT_ID, MQTT_BROKER, port=MQTT_PORT, keepalive=60)

    # Intentar conectar al broker MQTT en bucle hasta que sea exitoso
    conectar_mqtt_en_bucle(cliente_mqtt)
    
    # Suscribirse al topic para manejar el reset OTA solo si la conexión MQTT está activa
    try:
        cliente_mqtt.ping()  # Envía un ping al broker para verificar la conexión
        cliente_mqtt.wait_msg()  # Procesa los mensajes entrantes del broker
        suscribirse_a_reset_mqtt(cliente_mqtt)
        print("Suscripción al topic de reset OTA completada.")
    except Exception as e:
        print("Error al suscribirse al topic de reset OTA:", e)
    try:
        while True:
            # Verificar y reconectar Wi-Fi si es necesario
            if not network.WLAN(network.STA_IF).isconnected():
                print("Wi-Fi desconectado. Intentando reconectar...")
                conectar_wifi_en_bucle()

            # Verificar y reconectar MQTT si es necesario
            try:
                cliente_mqtt.ping()  # Envía un ping al broker para verificar la conexión
                cliente_mqtt.wait_msg()  # Procesa los mensajes entrantes del broker
                #print("Ping exitoso: conexión MQTT sigue activa.")
            except Exception as e:
                print("Conexión MQTT perdida. Intentando reconectar...")
                conectar_mqtt_en_bucle(cliente_mqtt)

            # Enviar estado de la máquina
            enviar_estado(cliente_mqtt)

            # Esperar antes del siguiente ciclo
            time.sleep(1)
    except Exception as e:
        print("Error en el bucle principal:", e)
    finally:
        cliente_mqtt.disconnect()  # Desconectar el cliente MQTT si ocurre un error


# Ejecutar la función principal
main()

