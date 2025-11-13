import cv2
import collections
import time
import serial
import datetime
import os
import json
import paho.mqtt.client as mqtt

# ==========================================
# [설정 영역] 사용자 환경에 맞게 수정하세요
# ==========================================

# 1. RTSP (카메라) 설정
AMEBA_RTSP_URL = "rtsp://192.168.196.79:554"
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp" # TCP 강제 설정 (필수)
FPS = 30                    # 아메바 보드 설정값 (30 추천)
BUFFER_SECONDS = 5          # 사고 전 몇 초를 저장할지
BUFFER_SIZE = FPS * BUFFER_SECONDS

# 2. Serial (아메바 보드 통신) 설정
SERIAL_PORT = '/dev/ttyUSB0' 
BAUD_RATE = 115200

# 3. MQTT (서버 통신) 설정
MQTT_BROKER_HOST = "100.112.74.119" # ⚠️ 중앙 서버(노트북) Tailscale IP
MQTT_TOPIC = "AjouHospital/patient/1"


# ==========================================

# 전역 변수: MQTT 클라이언트
client = mqtt.Client()

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("📡 MQTT 브로커 연결 성공!")
    else:
        print(f"❌ MQTT 연결 실패 (코드: {rc})")

def send_mqtt_alert(filename):
    """MQTT로 낙상 알림과 파일명을 전송"""
    payload = {
        "event": "FALL_DETECTED",
        "location": "Room 101",
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "video_file": filename,
        "message": "Patient fall detected! Video saved."
    }
    payload_json = json.dumps(payload)
    
    try:
        client.publish(MQTT_TOPIC, payload_json)
        print(f"📡 MQTT 전송 완료: {MQTT_TOPIC} -> {payload_json}")
    except Exception as e:
        print(f"❌ MQTT 전송 실패: {e}")

def save_video(buffer_data, width, height):
    """버퍼에 있는 영상을 파일로 저장"""
    if not buffer_data:
        return None

    now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"Fall_Event_{now}.mp4"
    
    # 코덱 설정
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(filename, fourcc, FPS, (width, height))
    
    print(f"💾 사고 영상 저장 시작 ({len(buffer_data)} 프레임)...")
    for frame in buffer_data:
        out.write(frame)
    out.release()
    
    print(f"✅ 영상 저장 완료: {filename}")
    return filename

# ==========================================
# 메인 실행 로직
# ==========================================

# 1. MQTT 연결
client.on_connect = on_connect
try:
    # ⭐️ [수정됨] 변수명을 MQTT_BROKER -> MQTT_BROKER_HOST 로 수정
    client.connect(MQTT_BROKER_HOST, 1883, 60)
    client.loop_start() # 백그라운드에서 MQTT 통신 처리
    
except Exception as e:
    print(f"❌ MQTT 초기화 실패: {e}")
    # MQTT 연결 실패해도 시리얼/영상 저장은 계속되도록 exit() 제거

# 2. Serial 연결
try:
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.1) # timeout을 짧게 줘서 영상 끊김 방지
    print(f"🔌 시리얼 포트 연결 성공 ({SERIAL_PORT})")
except Exception as e:
    print(f"❌ 시리얼 포트 열기 실패: {e}")
    print("   1. 아메바 보드가 USB에 연결되었는지 확인하세요.")
    print("   2. 'ls /dev/tty*' 명령어로 포트가 '/dev/ttyUSB0'이 맞는지 확인하세요.")
    exit()

# 3. 영상 버퍼 초기화
frame_buffer = collections.deque(maxlen=BUFFER_SIZE)

# 4. RTSP 연결
cap = cv2.VideoCapture(AMEBA_RTSP_URL)
if not cap.isOpened():
    print("❌ RTSP 카메라 연결 실패. 주소나 네트워크를 확인하세요.")
    exit()

width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
print(f"🎥 시스템 가동 시작 (해상도: {width}x{height})")
print("   - 평소에는 영상을 버퍼링하다가")
print("   - 시리얼 신호가 오면 저장 후 MQTT를 보냅니다.")

try:
    while cap.isOpened():
        # --- [A] 영상 읽기 & 버퍼링 ---
        ret, frame = cap.read()
        if not ret:
            print("⚠️ 영상 끊김. 재연결 시도...")
            # 스트림이 끊기면 다시 연결 시도
            cap.release()
            while not cap.isOpened():
                print("RTSP 재연결 중...")
                cap = cv2.VideoCapture(AMEBA_RTSP_URL)
                time.sleep(3)
            continue
        
        frame_buffer.append(frame)

        # (로그: 100프레임마다 한 번씩만 출력)
        if len(frame_buffer) % 100 == 0:
            print(f"모니터링 중... [버퍼: {len(frame_buffer)}/{BUFFER_SIZE}]")

        # --- [B] 시리얼 신호 감지 ---
        if ser.in_waiting > 0:
            try:
                # 데이터 읽기 (줄바꿈 제거, 디코딩)
                data = ser.readline().decode('utf-8', errors='ignore').strip()
                
                if data: # 데이터가 있다면 (예: "FALL", "1" 등)
                    print(f"\n🚨 [이벤트 감지] 시리얼 신호 수신: {data}")
                    
                    # 1. 버퍼 영상 저장 (현재 버퍼 상태 복사해서 전달)
                    saved_filename = save_video(list(frame_buffer), width, height)
                    
                    # 2. MQTT 알림 전송
                    if saved_filename:
                        send_mqtt_alert(saved_filename)
                    
                    print("🔄 시스템 모니터링 재개...\n")
                    
                    # (선택) 중복 저장 방지를 위해 시리얼 버퍼 비우기
                    ser.reset_input_buffer()
                    
            except Exception as e:
                print(f"시리얼 읽기 오류: {e}")

except KeyboardInterrupt:
    print("\n프로그램을 종료합니다.")

finally:
    cap.release()
    ser.close()
    client.loop_stop()
    print("시스템 종료.")