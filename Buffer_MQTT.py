import cv2
import collections
import time
import serial
import datetime
import os
import json
import paho.mqtt.client as mqtt
import requests # ⭐️ [수정] 빠진 영상 업로드 라이브러리 추가
# [추가] DeprecationWarning (경고) 메시지 해결용
from paho.mqtt.client import CallbackAPIVersion 

# ==========================================
# [설정 영역]
# ==========================================

# 1. RTSP (카메라) 설정
AMEBA_RTSP_URL = "rtsp://192.168.196.79:554"
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp" 

# [수정 1] 실제 프레임(약 12~15)에 맞춰 15로 수정 (안 그러면 2배속 재생됨)
FPS = 15
BUFFER_SECONDS = 5          
BUFFER_SIZE = FPS * BUFFER_SECONDS # 15 * 5 = 75 프레임

# 2. Serial (아메바 보드 통신) 설정
SERIAL_PORT = '/dev/ttyUSB0' 
BAUD_RATE = 115200
# [수정 2] 아메바 보드와 약속한 "낙상" 신호
FALL_SIGNAL_STRING = "Fall" 

# 3. MQTT (서버 통신) 설정
MQTT_BROKER_HOST = "100.112.74.119" 
MQTT_TOPIC = "AjouHospital/patient/1"
MQTT_PORT = 1883
# [추가 3] MQTT 로그인 정보 (필수)
MQTT_USER = "mqttuser"
MQTT_PASS = "asdf"

# 4. 중앙 서버 업로드 주소 (Pi 5의 Flask 대시보드 주소)
UPLOAD_SERVER_URL = "http://100.112.74.119:5000/upload" 

# ==========================================

# [수정 4] 경고 메시지 제거를 위해 API 버전 명시
client = mqtt.Client(callback_api_version=CallbackAPIVersion.VERSION1)

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("📡 MQTT 브로커 연결 성공!")
    else:
        print(f"❌ MQTT 연결 실패 (코드: {rc})")

def upload_video(filename):
    """지정된 파일을 중앙 서버로 HTTP POST 업로드합니다."""
    try:
        with open(filename, 'rb') as f:
            files = {'video': (filename, f, 'video/mp4')}
            response = requests.post(UPLOAD_SERVER_URL, files=files, timeout=10)
            
            if response.status_code == 200:
                print(f"🚀 (2/3) 영상 업로드 성공: {filename}")
                return True
            else:
                print(f"❌ (2/3) 영상 업로드 실패 (서버 응답: {response.status_code})")
                return False
    except requests.exceptions.ConnectionError:
        print("❌ (2/3) 영상 업로드 실패: 서버에 연결할 수 없습니다. (Pi 5 서버 켜있나요?)")
        return False
    except Exception as e:
        print(f"❌ (2/3) 영상 업로드 중 알 수 없는 오류: {e}")
        return False

def send_mqtt_alert(filename):
    """MQTT로 낙상 알림과 파일명을 전송"""
    payload = {
        "event": "FALL_DETECTED",
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "video_file": filename, 
    }
    payload_json = json.dumps(payload)
    
    try:
        if client.is_connected():
            client.publish(MQTT_TOPIC, payload_json)
            print(f"📡 (3/3) MQTT 알림 전송 완료: {MQTT_TOPIC}")
        else:
            print("❌ (3/3) MQTT 연결이 끊겨 알림 전송에 실패했습니다.")
    except Exception as e:
        print(f"❌ (3/3) MQTT 알림 전송 실패: {e}")

def save_video(buffer_data, width, height):
    """버퍼에 있는 영상을 파일로 저장"""
    if not buffer_data:
        return None
    now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"Fall_Event_{now}.mp4"
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(filename, fourcc, FPS, (width, height))
    print(f"💾 (1/3) 로컬 영상 저장 시작 ({len(buffer_data)} 프레임)...")
    for frame in buffer_data:
        out.write(frame)
    out.release()
    print(f"✅ (1/3) 로컬 영상 저장 완료: {filename}")
    return filename

# ==========================================
# 메인 실행 로직
# ==========================================

# 1. MQTT 연결
client.on_connect = on_connect
try:
    # [수정 5] connect() 호출 *전에* 로그인 정보를 설정해야 합니다. (순서 중요!)
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.connect(MQTT_BROKER_HOST, MQTT_PORT, 60)
    client.loop_start() 
except Exception as e:
    print(f"❌ MQTT 초기화 실패: {e}")

# 2. Serial 연결
try:
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.1) 
    print(f"🔌 시리얼 포트 연결 성공 ({SERIAL_PORT})")
except Exception as e:
    print(f"❌ 시리얼 포트 열기 실패: {e}")
    exit()

# 3. RTSP 연결
cap = cv2.VideoCapture(AMEBA_RTSP_URL)

cap.set(cv2.CAP_PROP_BUFFERSIZE, 0)
if not cap.isOpened():
    print("❌ RTSP 카메라 연결 실패. (Ameba 보드 IP 확인, 720p 설정 확인)")
    exit()

width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
print(f"🎥 시스템 가동 시작 (해상도: {width}x{height})")
frame_buffer = collections.deque(maxlen=BUFFER_SIZE)
# [추가 1] 테스트용 타이머 변수 설정
start_time = time.time()
test_signal_sent = False

try:
    while cap.isOpened():
        # --- [A] 영상 읽기 & 버퍼링 ---
        ret, frame = cap.read()
        if not ret:
            print("⚠️ 영상 끊김. (Ameba 보드 720p + Serial 정리 코드 확인)")
            cap.release()
            while not cap.isOpened():
                print("RTSP 재연결 중...")
                cap = cv2.VideoCapture(AMEBA_RTSP_URL)
                time.sleep(3)
            continue
        
        frame_buffer.append(frame)

        # ⭐️ [추가 2] 10초 뒤에 자동으로 아메바에게 'f' 전송 (테스트용)
        if not test_signal_sent and (time.time() - start_time > 10):
            print("\n⏰ [TEST] 10초 경과! 아메바에게 'f' 신호 전송 중...")
            ser.write(b'f')  # 아메바에게 'f'를 보냄
            test_signal_sent = True # 한 번만 보내도록 설정

        # --- [B] 시리얼 신호 감지 ---
        if ser.in_waiting > 0:
            try:
                data = ser.readline().decode('utf-8', errors='ignore').strip()
                
                # [수정 6] 정확히 약속된 "Fall" 신호일 때만 반응
                if data == FALL_SIGNAL_STRING: 
                    print(f"\n🚨 [이벤트 감지] 시리얼 신호 수신: {data}")
                    
                    # 1. 로컬에 .mp4 파일로 저장
                    saved_filename = save_video(list(frame_buffer), width, height)
                    
                    if saved_filename:
                        # 2. 중앙 서버로 파일 업로드
                        upload_success = upload_video(saved_filename)
                        
                        # 3. MQTT 알림 전송
                        send_mqtt_alert(saved_filename)
                        
                        # (선택) 업로드 성공 시 로컬 파일 삭제
                        if upload_success:
                            # os.remove(saved_filename) # (주석 해제 시 삭제)
                            # print(f"🧹 로컬 파일 삭제 완료: {saved_filename}")
                            pass

                    print("🔄 시스템 모니터링 재개...\n")
                    ser.reset_input_buffer()
                
                elif data: 
                    # "SCRFD tick[0]" 같은 다른 모든 메시지는 무시
                    # print(f" (디버그 메시지 무시: {data})") # (주석 해제 시 확인 가능)
                    pass 
                    
            except Exception as e:
                print(f"시리얼 읽기 오류: {e}")

except KeyboardInterrupt:
    print("\n프로그램을 종료합니다.")

finally:
    if 'cap' in locals():
        cap.release()
    if 'ser' in locals():
        ser.close()
    client.loop_stop()
    print("시스템 종료.")