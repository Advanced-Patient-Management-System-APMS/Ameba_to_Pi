/*
 * [최종 Ameba 코드]
 * 1. 720p (VIDEO_HD)로 과부하 문제 해결
 * 2. FDPostProcess의 Serial.print/printf를 모두 제거하여 병목 현상 해결
 * 3. loop()에 'f' 키로 "Fall" 신호를 보내는 테스트 로직 추가
 */

#include "WiFi.h"
#include "StreamIO.h"
#include "VideoStream.h"
#include "RTSP.h"
#include "NNFaceDetection.h"
#include "VideoStreamOverlay.h"

#define CHANNEL   0
#define CHANNELNN 3

#define NNWIDTH  576
#define NNHEIGHT 320

// 1. 720p (VIDEO_HD)로 설정
VideoSetting config(VIDEO_HD, 30, VIDEO_H264, 0); 
VideoSetting configNN(NNWIDTH, NNHEIGHT, 10, VIDEO_RGB, 0);
NNFaceDetection facedet;
RTSP rtsp;
StreamIO videoStreamer(1, 1);
StreamIO videoStreamerNN(1, 1);

char ssid[] = "kwc7162";    
char pass[] = "kwangyeon404"; 
int status = WL_IDLE_STATUS;
IPAddress ip;
int rtsp_portnum;

void setup()
{
    Serial.begin(115200);

    // WiFi 연결 (불필요한 Serial.print 제거)
    while (status != WL_CONNECTED) {
        status = WiFi.begin(ssid, pass);
        delay(2000);
    }
    ip = WiFi.localIP();
    
    // 비트레이트 1Mbps 설정
    config.setBitrate(1 * 1024 * 1024);    
    Camera.configVideoChannel(CHANNEL, config);
    Camera.configVideoChannel(CHANNELNN, configNN);
    Camera.videoInit();

    rtsp.configVideo(config);
    rtsp.begin();
    rtsp_portnum = rtsp.getPort();

    facedet.configVideo(configNN);
    facedet.setResultCallback(FDPostProcess); // 2. "깨끗한" FDPostProcess 호출
    facedet.modelSelect(FACE_DETECTION, NA_MODEL, DEFAULT_SCRFD, NA_MODEL);
    facedet.begin();

    videoStreamer.registerInput(Camera.getStream(CHANNEL));
    videoStreamer.registerOutput(rtsp);
    if (videoStreamer.begin() != 0) { }
    Camera.channelBegin(CHANNEL);

    videoStreamerNN.registerInput(Camera.getStream(CHANNELNN));
    videoStreamerNN.setStackSize();
    videoStreamerNN.setTaskPriority();
    videoStreamerNN.registerOutput(facedet);
    if (videoStreamerNN.begin() != 0) { }
    Camera.channelBegin(CHANNELNN);

    OSD.configVideo(CHANNEL, config);
    OSD.begin();

    // [추가] 시작 시 RTSP 주소와 테스트 방법 안내
    Serial.println("Ameba Setup Done.");
    Serial.print("RTSP URL: rtsp://");
    Serial.print(ip);
    Serial.print(":");
    Serial.println(rtsp_portnum);
    Serial.println("Type 'f' in Serial Monitor to simulate a fall.");
}

void loop()
{
    // [수정 3] "Fall" 신호 전송 로직
    // 아두이노 IDE의 시리얼 모니터에서 'f' 키를 누르면
    // Pi 4로 "Fall" 문자열을 전송합니다.
    if (Serial.available() > 0) {
        char c = Serial.read();
        if (c == 'f' || c == 'F') {
            Serial.println("Fall"); // ⭐️ 파이썬이 기다리는 정확한 신호
        }
    }
}

// User callback function for post processing of face detection results
void FDPostProcess(std::vector<FaceDetectionResult> results)
{
    // [수정 4] 모든 Serial.print/printf가 제거된 "깨끗한" 상태
    // (병목 현상 해결)
    
    int count = 0;
    uint16_t im_h = config.height();
    uint16_t im_w = config.width();

    OSD.createBitmap(CHANNEL);

    if (facedet.getResultCount() > 0) {
        for (int i = 0; i < facedet.getResultCount(); i++) {
            FaceDetectionResult item = results[i];
            int xmin = (int)(item.xMin() * im_w);
            int xmax = (int)(item.xMax() * im_w);
            int ymin = (int)(item.yMin() * im_h);
            int ymax = (int)(item.yMax() * im_h);

            // OSD(화면)에는 그리지만, Serial(USB)로는 아무것도 보내지 않음
            OSD.drawRect(CHANNEL, xmin, ymin, xmax, ymax, 3, OSD_COLOR_WHITE);
            char text_str[40];
            snprintf(text_str, sizeof(text_str), "%s %d", item.name(), item.score());
            OSD.drawText(CHANNEL, xmin, ymin - OSD.getTextHeight(CHANNEL), text_str, OSD_COLOR_CYAN);

            for (int j = 0; j < 5; j++) {
                int x = (int)(item.xFeature(j) * im_w);
                int y = (int)(item.yFeature(j) * im_h);
                OSD.drawPoint(CHANNEL, x, y, 8, OSD_COLOR_RED);
                count++;
                if (count == MAX_FACE_DET) {
                    goto OSDUpdate;
                }
            }
        }
    }

OSDUpdate:
    OSD.update(CHANNEL);
}