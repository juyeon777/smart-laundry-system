"""
스마트 빨래 날씨 감지 시스템 - 메인 코드

Raspberry Pi 5에서 빗물 센서로 비를 감지하고,
서보모터(지붕/해 모형) · LED · 부저를 제어하여 빨래를 보호합니다.

- lgpio: GPIO 입출력 (RPi.GPIO는 라즈베리파이 5 미지원)
- gpiozero.Servo: 서보모터 PWM 제어

핀 배정 (BCM):
  RAIN_SENSOR_PIN = 17  빗물 감지 센서 DO (LOW=비 감지)
  BUZZER_PIN      = 27  부저 (능동형, ON/OFF)
  LED_RED_PIN     = 22  맑음 표시 (빨간 LED)
  LED_BLUE_PIN    = 23  비 표시 (파란 LED)
  BTN_OPEN_PIN    = 24  수동 맑음 버튼 (내부 풀업)
  BTN_CLOSE_PIN   = 25  수동 비 버튼 (내부 풀업)
  SERVO_ROOF_PIN  = 18  지붕(차양) 서보모터
  SERVO_SUN_PIN   = 19  해 모형 서보모터

[재진행 예정] OLED 128x64 (I2C)
  현재 OLED가 특정 I2C 버스에서 감지되나 luma/smbus2 통신이 불안정하여
  코드에서 제외된 상태입니다. 통신 이슈 해결 후 아래 표시(print_status) 시점에
  화면 출력 로직을 추가할 예정입니다. (자리표시 주석: "OLED 예정" 참고)
"""

import lgpio
import time
import threading
from gpiozero import Servo
from datetime import datetime

RAIN_SENSOR_PIN = 17
BUZZER_PIN      = 27
LED_RED_PIN     = 22
LED_BLUE_PIN    = 23
BTN_OPEN_PIN    = 24
BTN_CLOSE_PIN   = 25
SERVO_ROOF_PIN  = 18
SERVO_SUN_PIN   = 19

# [OLED 예정] I2C 핀(SDA=GPIO2, SCL=GPIO3) 고정. 통신 이슈 해결 후 활성화.
# OLED_I2C_ADDR = 0x3C

h = lgpio.gpiochip_open(0)
lgpio.gpio_claim_input(h, RAIN_SENSOR_PIN)
lgpio.gpio_claim_input(h, BTN_OPEN_PIN, lgpio.SET_PULL_UP)
lgpio.gpio_claim_input(h, BTN_CLOSE_PIN, lgpio.SET_PULL_UP)
lgpio.gpio_claim_output(h, BUZZER_PIN, 1)
lgpio.gpio_claim_output(h, LED_RED_PIN, 0)
lgpio.gpio_claim_output(h, LED_BLUE_PIN, 0)

servo_roof = Servo(SERVO_ROOF_PIN)
servo_sun  = Servo(SERVO_SUN_PIN)

# [OLED 예정] 통신 이슈 해결 후 초기화 코드 추가
# from luma.core.interface.serial import i2c
# from luma.oled.device import ssd1306
# oled = ssd1306(i2c(port=1, address=OLED_I2C_ADDR))

current_mode   = None
buzzer_running = False
buzzer_thread  = None
manual_mode    = False

def timestamp():
    return datetime.now().strftime("%H:%M:%S")

def print_status(mode, trigger):
    print("\n" + "="*45)
    print(f"  Smart Laundry Weather Detection System")
    print("="*45)
    if mode == 'sunny':
        print(f"  Status   : SUNNY")
        print(f"  LED      : RED ON")
        print(f"  Roof     : CLOSED")
        print(f"  Sun      : UP")
    elif mode == 'rainy':
        print(f"  Status   : RAINY")
        print(f"  LED      : BLUE ON")
        print(f"  Roof     : OPEN")
        print(f"  Sun      : DOWN")
    print(f"  Trigger  : {trigger}")
    print(f"  Time     : {timestamp()}")
    print("="*45)
    # [OLED 예정] 동일한 상태(mode, trigger)를 OLED 화면에도 출력 예정
    # update_oled(mode, trigger)

def set_sunny():
    servo_roof.max()
    time.sleep(0.5)
    servo_sun.max()

def set_rainy():
    servo_sun.min()
    time.sleep(0.5)
    servo_roof.min()

def stop_buzzer():
    global buzzer_running
    buzzer_running = False
    lgpio.gpio_write(h, BUZZER_PIN, 1)

def buzzer_sunny():
    # 능동형: 짧게 3번 삐
    for _ in range(3):
        if not buzzer_running:
            break
        lgpio.gpio_write(h, BUZZER_PIN, 0)
        time.sleep(0.15)
        lgpio.gpio_write(h, BUZZER_PIN, 1)
        time.sleep(0.15)

def buzzer_rainy():
    # 능동형: 길게 반복
    while buzzer_running:
        lgpio.gpio_write(h, BUZZER_PIN, 0)
        time.sleep(0.5)
        lgpio.gpio_write(h, BUZZER_PIN, 1)
        time.sleep(0.5)

def start_buzzer(mode):
    global buzzer_thread, buzzer_running
    stop_buzzer()
    time.sleep(0.1)
    buzzer_running = True
    target = buzzer_sunny if mode == 'sunny' else buzzer_rainy
    buzzer_thread = threading.Thread(target=target, daemon=True)
    buzzer_thread.start()

def activate_sunny(trigger="AUTO"):
    global current_mode
    if current_mode == 'sunny':
        return
    current_mode = 'sunny'
    lgpio.gpio_write(h, LED_RED_PIN,  1)
    lgpio.gpio_write(h, LED_BLUE_PIN, 0)
    set_sunny()
    start_buzzer('sunny')
    print_status('sunny', trigger)

def activate_rainy(trigger="AUTO"):
    global current_mode
    if current_mode == 'rainy':
        return
    current_mode = 'rainy'
    lgpio.gpio_write(h, LED_BLUE_PIN, 1)
    lgpio.gpio_write(h, LED_RED_PIN,  0)
    set_rainy()
    start_buzzer('rainy')
    print_status('rainy', trigger)

def main():
    global manual_mode
    print("\n" + "="*45)
    print("  Smart Laundry Weather Detection System")
    print("  Raspberry Pi 5")
    print(f"  Started at {timestamp()}")
    print("="*45)
    print("  [BTN1] Manual Sunny  | [BTN2] Manual Rainy")
    print("  [AUTO] Rain Sensor Detection")
    print("="*45 + "\n")
    activate_sunny(trigger="SYSTEM START")
    try:
        while True:
            rain      = lgpio.gpio_read(h, RAIN_SENSOR_PIN) == 0
            btn_open  = lgpio.gpio_read(h, BTN_OPEN_PIN)   == 0
            btn_close = lgpio.gpio_read(h, BTN_CLOSE_PIN)  == 0

            if btn_open:
                manual_mode = True
                activate_sunny(trigger="BUTTON 1 (Manual)")
                time.sleep(0.3)
            elif btn_close:
                manual_mode = True
                activate_rainy(trigger="BUTTON 2 (Manual)")
                time.sleep(0.3)
            elif not manual_mode:
                if rain:
                    activate_rainy(trigger="RAIN SENSOR (Auto)")
                else:
                    activate_sunny(trigger="RAIN CLEARED (Auto)")
            elif manual_mode and rain:
                manual_mode = False
                activate_rainy(trigger="RAIN SENSOR (Auto Override)")

            time.sleep(0.1)

    except KeyboardInterrupt:
        print(f"\n[{timestamp()}] Shutting down...")
    finally:
        stop_buzzer()
        lgpio.gpio_write(h, LED_RED_PIN,  0)
        lgpio.gpio_write(h, LED_BLUE_PIN, 0)
        lgpio.gpiochip_close(h)
        print("System stopped.\n")

if __name__ == "__main__":
    main()
