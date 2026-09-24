// Touch a wire on GPIO4 (T0) to toggle the LED on GPIO2 (built-in LED on most devkits).
// Classic ESP32: touchRead() gets SMALLER when you touch (your body adds capacitance).

const int TOUCH_PIN = T0;   // GPIO4
const int LED_PIN   = 2;
const float SENS    = 0.7;  // calibration knob: touched if reading < baseline*SENS. Raise if it misses touches, lower if it false-triggers.

int threshold;
bool ledOn = false, wasTouched = false;

void setup() {
  Serial.begin(115200);
  pinMode(LED_PIN, OUTPUT);
  delay(500);
  long sum = 0;  // don't touch the wire during boot: this measures "untouched"
  for (int i = 0; i < 50; i++) { sum += touchRead(TOUCH_PIN); delay(10); }
  threshold = (sum / 50) * SENS;
  Serial.printf("baseline=%ld threshold=%d\n", sum / 50, threshold);
}

void loop() {
  int v = touchRead(TOUCH_PIN);
  bool touched = v < threshold;
  if (touched && !wasTouched) {           // toggle only on the moment of touch, not while holding
    ledOn = !ledOn;
    digitalWrite(LED_PIN, ledOn);
  }
  wasTouched = touched;
  Serial.printf("value=%d threshold=%d led=%d\n", v, threshold, ledOn);
  delay(50);
}
