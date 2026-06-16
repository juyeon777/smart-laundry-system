"""
OLED 연결 테스트 (SSD1306 128x64, I2C)

사용법:
  python3 src/oled_test.py [버스번호] [주소(16진)]

예:
  python3 src/oled_test.py          # 기본: 버스 13, 0x3c
  python3 src/oled_test.py 1        # 버스 1에서 시도
  python3 src/oled_test.py 13 0x3c  # 버스 13, 주소 0x3c

라즈베리파이 5는 GPIO 2/3 I2C 버스 번호가 환경에 따라 다릅니다.
`i2cdetect -l`로 OLED가 보이는 버스 번호를 확인한 뒤 인자로 넘기세요.
"""

import sys

port = int(sys.argv[1]) if len(sys.argv) > 1 else 13
addr = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x3c

print(f"[OLED TEST] i2c-{port} @ {hex(addr)} 시도 중...")

try:
    from luma.core.interface.serial import i2c
    from luma.oled.device import ssd1306
    from luma.core.render import canvas
except ImportError as e:
    print(f"[설치 필요] luma.oled 가 없습니다: {e}")
    print("  pip3 install luma.oled  (필요시 --break-system-packages)")
    sys.exit(1)

try:
    serial = i2c(port=port, address=addr)
    device = ssd1306(serial, width=128, height=64)
except Exception as e:
    print(f"[실패] {type(e).__name__}: {e}")
    print("  → 다른 버스 번호로 시도해 보세요. 예: python3 src/oled_test.py 1")
    sys.exit(1)

with canvas(device) as draw:
    draw.rectangle(device.bounding_box, outline="white")
    draw.text((12, 16), "OLED OK!", fill="white")
    draw.text((12, 34), f"i2c-{port} {hex(addr)}", fill="white")

print("[성공] 화면에 'OLED OK!' 가 보이면 정상입니다.")
