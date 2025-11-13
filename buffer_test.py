import cv2
import collections
import time

# --- 1. 설정 (필수 수정) ---
# ⚠️ 1단계에서 확인한 Ameba의 RTSP 주소를 여기에 정확히 입력하세요!
AMEBA_RTSP_URL = "rtsp://192.168.196.79:554" 

VIDEO_BUFFER_SECONDS = 5  # 5초 버퍼
VIDEO_FPS_ESTIMATE = 10   # Ameba 스트림의 예상 FPS (성능에 따라 조절)
BUFFER_SIZE = VIDEO_BUFFER_SECONDS * VIDEO_FPS_ESTIMATE # 총 50프레임 저장

# 'deque'는 버퍼 크기가 꽉 차면 가장 오래된 프레임을 자동으로 버리는 링 버퍼입니다.
frame_buffer = collections.deque(maxlen=BUFFER_SIZE)

print("영상 버퍼링 스크립트 시작...")

# --- 2. 메인 루프: RTSP 접속 및 버퍼링 ---
while True:
    try:
        print(f"RTSP 스트림에 연결 시도 중: {AMEBA_RTSP_URL}")
        cap = cv2.VideoCapture(AMEBA_RTSP_URL)
        
        # 캡처 객체가 열리지 않으면 5초 후 재시도
        if not cap.isOpened():
            print("오류: RTSP 스트림에 연결할 수 없습니다. 5초 후 재시도...")
            cap.release()
            time.sleep(5)
            continue

        print("✅ RTSP 스트림 연결 성공! 5초 버퍼링 시작...")
        
        # 스트림이 열려있는 동안 계속 프레임 읽기
        while cap.isOpened():
            ret, frame = cap.read()
            
            # ret이 False이면 스트림이 끊긴 것
            if not ret:
                print("RTSP 스트림 연결 끊김. 재연결 시도...")
                break # 내부 루프를 빠져나가 재연결 로직 실행

            # ------------------------------------------------
            # [핵심] 링 버퍼에 최신 프레임 추가
            # ------------------------------------------------
            frame_buffer.append(frame)
            
            # (디버깅용) 현재 버퍼 상태 출력
            if len(frame_buffer) % VIDEO_FPS_ESTIMATE == 0:
                 print(f"버퍼링 중... [{len(frame_buffer)} / {BUFFER_SIZE}] 프레임")

            # CPU 과부하 방지 (FPS에 맞춰 조절)
            time.sleep(1 / VIDEO_FPS_ESTIMATE)

    except cv2.error as e:
        print(f"OpenCV 오류 발생: {e}")
    except Exception as e:
        print(f"알 수 없는 오류 발생: {e}")
    finally:
        # 오류 발생 시 자원 해제 후 5초 뒤 재시작
        if 'cap' in locals():
            cap.release()
        print("5초 후 재시작합니다...")
        time.sleep(5)