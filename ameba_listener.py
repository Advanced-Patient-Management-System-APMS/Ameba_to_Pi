import serial
import time

# USB 포트에 연결된 AMB82-MINI와 통신을 시작합니다.
# 포트 이름('/dev/ttyACM0')은 연결 상태에 따라 다를 수 있습니다.
# 'ls /dev/tty*' 명령어로 확인 가능
try:
    ser = serial.Serial('/dev/ttyUSB0', 115200, timeout=1)
    ser.flush()
    print("AMB82-MINI와의 통신을 시작합니다. 신호를 기다립니다...")
except serial.SerialException as e:
    print(f"연결에 실패했습니다: {e}")
    print("'/dev/ttyACM0' 포트가 맞는지, 보드가 연결되었는지 확인해주세요.")
    exit() # 연결 실패 시 프로그램 종료

# 계속해서 AMB82-MINI로부터 메시지가 오는지 귀 기울여 듣습니다.
try:
    while True:
        # 시리얼 포트에 데이터가 들어왔는지 확인
        if ser.in_waiting > 0:
            # 데이터가 있으면 한 줄을 읽어옵니다.
            line = ser.readline().decode('utf-8').rstrip()

            # 읽어온 메시지를 화면에 출력합니다.
            print(f"수신된 신호: {line}")

            # 만약 메시지가 "FALL_SUSPECTED" 라면, 다음 행동을 실행
            if line == "FALL":
                print("✅ 낙상 의심 신호 감지! 중앙 서버에 보고하는 절차를 시작합니다.")
                # (나중에 여기에 MQTT 메시지를 보내는 코드를 추가할 부분)

        time.sleep(0.1) # CPU 부하를 줄이기 위해 잠시 대기

except KeyboardInterrupt:
    print("\n프로그램을 종료합니다.")
    ser.close()