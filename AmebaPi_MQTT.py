import serial
import paho.mqtt.client as mqtt
import time

# --- 설정 ---
SERIAL_PORT = '/dev/ttyUSB0' 
BAUD_RATE = 115200

MQTT_BROKER_HOST = "100.112.74.119" # ⚠️ 중앙 서버(노트북) Tailscale IP
MQTT_TOPIC = "AjouHospital/patient/1"

# --- [추가] MQTT 연결 성공 확인 콜백 ---
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("✅ [Pi -> 중앙서버] MQTT 브로커 연결 성공!")
    else:
        print(f"❌ [Pi -> 중앙서버] MQTT 연결 실패. (Return code: {rc})")

# --- MQTT 클라이언트 설정 (중앙 서버 접속) ---
# [수정] 콜백 API 버전을 명시하여 경고 제거
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1) 
client.on_connect = on_connect  # [추가] 콜백 함수 등록

client.username_pw_set("mqttuser", "asdf")

try:
    print("중앙 서버 MQTT 브로커에 연결 시도...")
    client.connect(MQTT_BROKER_HOST, 1883, 60)
    client.loop_start()

    # --- 시리얼 수신 ---
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    print(f"{SERIAL_PORT} 포트에서 테스트 신호 수신 대기 중...")

    while True:
        line = ser.readline()
        if line:
            signal = line.decode('utf-8').strip()

            if signal == "Fall":
                print("✅ [Ameba -> Pi] 테스트 신호 수신 성공!")
                
                # [수정] 발행 전 연결 상태 확인 (더 안정적)
                if client.is_connected():
                    (rc, mid) = client.publish(MQTT_TOPIC, signal, qos=1)
                    if rc == mqtt.MQTT_ERR_SUCCESS:
                        print("✅ [Pi -> 중앙서버] MQTT 전송 성공!")
                    else:
                        print(f"❌ [Pi -> 중앙서버] MQTT 전송 실패 (코드: {rc})")
                else:
                    print("❌ [Pi -> 중앙서버] MQTT 연결 끊김. 전송 실패.")
        
        time.sleep(0.01)

except serial.SerialException as e:
    print(f"시리얼 포트 오류: {e}")
except Exception as e:
    print(f"오류: {e}")
finally:
    if 'ser' in locals() and ser.is_open:
        ser.close()
    client.loop_stop()