"""
스마트 빨래 날씨 감지 시스템 - 메인 코드

Raspberry Pi 5에서 빗물 센서로 비를 감지하고,
서보모터(지붕/해 모형) · LED · 부저를 제어하여 빨래를 보호합니다.
+ 폰/맥북 브라우저로 접속하는 웹 대시보드(스마트홈 앱 스타일)로 상태 확인 및 원격 제어.

- lgpio: GPIO 입출력 (RPi.GPIO는 라즈베리파이 5 미지원)
- gpiozero.Servo: 서보모터 PWM 제어
- Flask: 웹 대시보드 (같은 와이파이에서 http://<Pi-IP>:5000 접속)

핀 배정 (BCM):
  RAIN_SENSOR_PIN = 17  빗물 감지 센서 DO (LOW=비 감지)
  BUZZER_PIN      = 27  부저 (수동형, PWM 멜로디)
  LED_RED_PIN     = 22  맑음 표시 (빨간 LED)
  LED_BLUE_PIN    = 23  비 표시 (파란 LED)
  BTN_OPEN_PIN    = 24  수동 맑음 버튼 (내부 풀업)
  BTN_CLOSE_PIN   = 25  수동 비 버튼 (내부 풀업)
  SERVO_ROOF_PIN  = 18  지붕(차양) 서보모터
  SERVO_SUN_PIN   = 19  해 모형 서보모터

제어 방법: ① 빗물센서 자동  ② 물리 버튼  ③ 웹 대시보드 버튼
(수동(버튼/웹)으로 맑음 상태라도, 실제 비가 감지되면 자동으로 비 모드로 오버라이드)
"""

import lgpio
import time
import threading
from gpiozero import Servo
from datetime import datetime

try:
    from flask import Flask, jsonify
except ImportError:
    print("[설치 필요] Flask 가 없습니다.")
    print("  sudo apt install -y python3-flask   (또는 pip3 install flask --break-system-packages)")
    raise SystemExit(1)

RAIN_SENSOR_PIN = 17
BUZZER_PIN      = 27
LED_RED_PIN     = 22
LED_BLUE_PIN    = 23
BTN_OPEN_PIN    = 24
BTN_CLOSE_PIN   = 25
SERVO_ROOF_PIN  = 18
SERVO_SUN_PIN   = 19

WEB_PORT = 5000

h = lgpio.gpiochip_open(0)
lgpio.gpio_claim_input(h, RAIN_SENSOR_PIN)
lgpio.gpio_claim_input(h, BTN_OPEN_PIN, lgpio.SET_PULL_UP)
lgpio.gpio_claim_input(h, BTN_CLOSE_PIN, lgpio.SET_PULL_UP)
lgpio.gpio_claim_output(h, BUZZER_PIN, 0)  # 수동형: 시작 시 무음(고정 레벨)
lgpio.gpio_claim_output(h, LED_RED_PIN, 0)
lgpio.gpio_claim_output(h, LED_BLUE_PIN, 0)

servo_roof = Servo(SERVO_ROOF_PIN)
servo_sun  = Servo(SERVO_SUN_PIN)

current_mode   = None
buzzer_running = False
buzzer_thread  = None
manual_mode    = False
last_trigger   = "-"
last_rain      = False
state_lock     = threading.Lock()

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

def set_sunny():
    servo_roof.max()
    time.sleep(0.5)
    servo_sun.max()

def set_rainy():
    servo_sun.min()
    time.sleep(0.5)
    servo_roof.min()

# 음계 주파수 (Hz)
NOTE = {'G3': 196, 'A3': 220, 'B3': 247,
        'C4': 262, 'D4': 294, 'E4': 330, 'F4': 349,
        'G4': 392, 'A4': 440, 'B4': 494, 'C5': 523}

def buzzer_silent():
    # 수동형: 듀티 0%면 펄스가 없어 무음 (주파수 0은 'bad PWM micros' 에러)
    lgpio.tx_pwm(h, BUZZER_PIN, 1000, 0)

def play_tone(freq, dur):
    lgpio.tx_pwm(h, BUZZER_PIN, freq, 50)  # 주파수 freq, 듀티 50%
    time.sleep(dur)

def stop_buzzer():
    global buzzer_running
    buzzer_running = False
    buzzer_silent()

def buzzer_sunny():
    # 수동형: 도-미-솔-도 상행 멜로디 (1회)
    for note in ('C4', 'E4', 'G4', 'C5'):
        if not buzzer_running:
            break
        play_tone(NOTE[note], 0.15)
    buzzer_silent()

def buzzer_rainy():
    # 수동형: 낮게 하행하는 불길한 경고음, 마지막 음 길게 (1회)
    seq = (('G4', 0.18), ('E4', 0.18), ('C4', 0.18), ('A3', 0.45))
    for note, dur in seq:
        if not buzzer_running:
            break
        play_tone(NOTE[note], dur)
    buzzer_silent()

def start_buzzer(mode):
    global buzzer_thread, buzzer_running
    stop_buzzer()
    time.sleep(0.1)
    buzzer_running = True
    target = buzzer_sunny if mode == 'sunny' else buzzer_rainy
    buzzer_thread = threading.Thread(target=target, daemon=True)
    buzzer_thread.start()

def activate_sunny(trigger="AUTO"):
    global current_mode, last_trigger
    with state_lock:
        if current_mode == 'sunny':
            return
        current_mode = 'sunny'
        last_trigger = trigger
        lgpio.gpio_write(h, LED_RED_PIN,  1)
        lgpio.gpio_write(h, LED_BLUE_PIN, 0)
        set_sunny()
        start_buzzer('sunny')
        print_status('sunny', trigger)

def activate_rainy(trigger="AUTO"):
    global current_mode, last_trigger
    with state_lock:
        if current_mode == 'rainy':
            return
        current_mode = 'rainy'
        last_trigger = trigger
        lgpio.gpio_write(h, LED_BLUE_PIN, 1)
        lgpio.gpio_write(h, LED_RED_PIN,  0)
        set_rainy()
        start_buzzer('rainy')
        print_status('rainy', trigger)

# ----------------------------------------------------------------------------
# 웹 대시보드 (스마트홈 앱 스타일) — 폰/맥북 브라우저에서 http://<Pi-IP>:5000
# ----------------------------------------------------------------------------
app = Flask(__name__)

PAGE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="스마트 빨래">
<meta name="theme-color" content="#f5a623">
<title>스마트 빨래 시스템</title>
<style>
  *{box-sizing:border-box;-webkit-tap-highlight-color:transparent;}
  body{margin:0;font-family:-apple-system,"Apple SD Gothic Neo",sans-serif;background:#1c1c22;
       color:#fff;min-height:100vh;display:flex;flex-direction:column;align-items:center;
       transition:background .4s;padding:28px 16px;}
  body.sunny{background:linear-gradient(160deg,#ffb347,#ff8c00);}
  body.rainy{background:linear-gradient(160deg,#4a6fa5,#2c3e60);}
  h1{font-size:19px;font-weight:700;margin:6px 0 22px;opacity:.95;}
  .card{background:rgba(255,255,255,.13);backdrop-filter:blur(8px);border-radius:24px;
        padding:30px 24px;width:100%;max-width:380px;text-align:center;
        box-shadow:0 10px 34px rgba(0,0,0,.28);}
  .emoji{font-size:88px;line-height:1;margin:2px 0 10px;}
  .mode{font-size:34px;font-weight:800;margin:0 0 8px;}
  .sub{font-size:14px;opacity:.88;margin:3px 0;}
  .badge{display:inline-block;padding:5px 14px;border-radius:999px;font-size:12px;
         font-weight:700;margin-top:12px;background:rgba(0,0,0,.28);}
  .btns{width:100%;max-width:380px;margin-top:26px;display:flex;flex-direction:column;gap:12px;}
  button{border:none;border-radius:18px;padding:18px;font-size:18px;font-weight:700;
         color:#fff;cursor:pointer;transition:transform .1s;}
  button:active{transform:scale(.96);}
  .b-sun{background:#f5a623;} .b-rain{background:#3b6fb0;} .b-auto{background:rgba(255,255,255,.22);}
</style>
</head>
<body>
  <h1>🧺 스마트 빨래 날씨 시스템</h1>
  <div class="card">
    <div class="emoji" id="emoji">⏳</div>
    <div class="mode" id="mode">연결 중...</div>
    <div class="sub" id="trigger">—</div>
    <div class="sub" id="time">—</div>
    <span class="badge" id="badge">—</span>
  </div>
  <div class="btns">
    <button class="b-sun" onclick="send('sunny')">☀️ 맑음 (지붕 닫기)</button>
    <button class="b-rain" onclick="send('rainy')">🌧️ 비 (지붕 펴기)</button>
    <button class="b-auto" onclick="send('auto')">🔄 자동 모드로</button>
  </div>
<script>
async function send(a){ try{ await fetch('/'+a,{method:'POST'}); }catch(e){} refresh(); }
async function refresh(){
  try{
    const s = await (await fetch('/status')).json();
    const sunny = s.mode==='sunny', rainy = s.mode==='rainy';
    document.body.className = s.mode||'';
    document.getElementById('emoji').textContent = sunny?'☀️':(rainy?'🌧️':'⏳');
    document.getElementById('mode').textContent  = sunny?'맑음':(rainy?'비':'...');
    document.getElementById('trigger').textContent = '트리거: ' + s.trigger;
    document.getElementById('time').textContent    = '시간: ' + s.time;
    document.getElementById('badge').textContent =
        (s.manual?'수동 모드':'자동 모드') + (s.rain?' · 비 감지중':'');
  }catch(e){}
}
setInterval(refresh,1000); refresh();
</script>
</body>
</html>"""

@app.route('/')
def index():
    return PAGE

@app.route('/status')
def status():
    return jsonify(mode=current_mode, trigger=last_trigger,
                   time=timestamp(), manual=manual_mode, rain=last_rain)

@app.route('/sunny', methods=['POST'])
def web_sunny():
    global manual_mode
    manual_mode = True
    activate_sunny(trigger="WEB (Manual)")
    return ('', 204)

@app.route('/rainy', methods=['POST'])
def web_rainy():
    global manual_mode
    manual_mode = True
    activate_rainy(trigger="WEB (Manual)")
    return ('', 204)

@app.route('/auto', methods=['POST'])
def web_auto():
    global manual_mode
    manual_mode = False
    return ('', 204)

def run_web():
    import logging
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    app.run(host='0.0.0.0', port=WEB_PORT, threaded=True, use_reloader=False)

def main():
    global manual_mode, last_rain
    threading.Thread(target=run_web, daemon=True).start()
    print("\n" + "="*45)
    print("  Smart Laundry Weather Detection System")
    print("  Raspberry Pi 5")
    print(f"  Started at {timestamp()}")
    print("="*45)
    print("  [BTN1] Manual Sunny  | [BTN2] Manual Rainy")
    print("  [AUTO] Rain Sensor Detection")
    print(f"  [WEB ] http://<Pi-IP>:{WEB_PORT}  (같은 와이파이)")
    print("="*45 + "\n")
    activate_sunny(trigger="SYSTEM START")

    # 빗물센서 디바운스: 같은 값이 RAIN_STABLE_N회 연속일 때만 인정 (떨림/노이즈 방지)
    RAIN_STABLE_N  = 5          # 0.1s * 5 = 0.5초 동안 같은 값이어야 모드 전환
    rain_candidate = False
    rain_count     = 0
    stable_rain    = False
    try:
        while True:
            rain_raw  = lgpio.gpio_read(h, RAIN_SENSOR_PIN) == 0
            btn_open  = lgpio.gpio_read(h, BTN_OPEN_PIN)   == 0
            btn_close = lgpio.gpio_read(h, BTN_CLOSE_PIN)  == 0

            # 디바운스: 0.5초 연속 같은 값일 때만 stable_rain 갱신
            if rain_raw == rain_candidate:
                rain_count += 1
            else:
                rain_candidate = rain_raw
                rain_count = 1
            if rain_count >= RAIN_STABLE_N:
                stable_rain = rain_candidate
            rain = stable_rain
            last_rain = stable_rain

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
