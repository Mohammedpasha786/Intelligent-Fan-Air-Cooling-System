/*
 * Intelligent Fan Air Cooling System — Arduino Prototype
 * 
 * Hardware:
 *   - Arduino Uno / Mega
 *   - DHT22 sensor (inside temperature + humidity)  → Pin 2
 *   - DS18B20 sensor (outside temperature)          → Pin 3
 *   - L298N motor driver or relay module            → Pins 9, 10
 *   - 12V DC fan (PWM-controlled via MOSFET)        → Pin 9 (PWM)
 *   - Fan direction relay                            → Pin 10
 *   - OLED display (SSD1306, I2C)                   → SDA/SCL
 *   - Optional: ESP8266 WiFi for weather forecast
 * 
 * Libraries required:
 *   - DHT sensor library (Adafruit)
 *   - OneWire + DallasTemperature
 *   - Adafruit SSD1306 + GFX
 */

#include <DHT.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <Wire.h>
#include <Adafruit_SSD1306.h>

// ─── Pin Definitions ────────────────────────────────────────────────────────
#define DHT_PIN        2
#define DHT_TYPE       DHT22
#define DS18B20_PIN    3
#define FAN_PWM_PIN    9
#define FAN_DIR_PIN   10
#define BUTTON_PIN    12     // Manual override button

// ─── Display ────────────────────────────────────────────────────────────────
#define SCREEN_WIDTH  128
#define SCREEN_HEIGHT  64
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);

// ─── Sensors ────────────────────────────────────────────────────────────────
DHT dht(DHT_PIN, DHT_TYPE);
OneWire oneWire(DS18B20_PIN);
DallasTemperature ds18b20(&oneWire);

// ─── Control Parameters ─────────────────────────────────────────────────────
const float T_MIN        = 20.0;   // °C comfort minimum
const float T_MAX        = 25.0;   // °C comfort maximum
const float T_TARGET     = 22.0;   // °C desired temperature
const float HYSTERESIS   = 0.5;    // °C dead band
const int   READ_INTERVAL = 30000; // ms between sensor reads

// ─── State ──────────────────────────────────────────────────────────────────
float T_inside   = 22.0;
float T_outside  = 18.0;
float humidity   = 50.0;
int   fanSpeed   = 0;        // 0–255 PWM
bool  fanRunning = false;
bool  manualMode = false;
unsigned long lastRead = 0;
float energyWh   = 0.0;
unsigned long lastEnergyTime = 0;

// ─── Setup ──────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(9600);
  dht.begin();
  ds18b20.begin();

  pinMode(FAN_PWM_PIN, OUTPUT);
  pinMode(FAN_DIR_PIN, OUTPUT);
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  analogWrite(FAN_PWM_PIN, 0);

  if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println(F("SSD1306 allocation failed"));
  }
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  display.println(F("Fan Cooling System"));
  display.println(F("Initializing..."));
  display.display();
  delay(2000);

  lastEnergyTime = millis();
  Serial.println(F("time_s,T_in,T_out,RH,fan_speed,energy_wh"));
}

// ─── Main Loop ──────────────────────────────────────────────────────────────
void loop() {
  unsigned long now = millis();

  // Check manual override button
  if (digitalRead(BUTTON_PIN) == LOW) {
    manualMode = !manualMode;
    delay(300);  // debounce
  }

  // Read sensors every READ_INTERVAL ms
  if (now - lastRead >= READ_INTERVAL) {
    lastRead = now;
    readSensors();
    if (!manualMode) {
      runController();
    }
    applyFanCommand();
    accumulateEnergy(now);
    updateDisplay();
    logSerial(now / 1000UL);
  }
}

// ─── Sensor Reading ─────────────────────────────────────────────────────────
void readSensors() {
  float h = dht.readHumidity();
  float t = dht.readTemperature();
  if (!isnan(h) && !isnan(t)) {
    humidity  = h;
    T_inside  = t;
  }

  ds18b20.requestTemperatures();
  float t_out = ds18b20.getTempCByIndex(0);
  if (t_out != DEVICE_DISCONNECTED_C) {
    T_outside = t_out;
  }
}

// ─── Rule-Based Controller ───────────────────────────────────────────────────
void runController() {
  bool outsideCooler = T_outside < (T_inside - HYSTERESIS);
  bool tooHot        = T_inside > T_MAX;
  bool comfortable   = T_inside <= T_MIN + HYSTERESIS;

  if (tooHot && outsideCooler) {
    fanRunning = true;
    float excess = T_inside - T_MAX;
    float speedFraction = constrain(0.3f + 0.15f * excess, 0.0f, 1.0f);
    fanSpeed = (int)(speedFraction * 255);
  } else if (comfortable || !outsideCooler) {
    fanRunning = false;
    fanSpeed = 0;
  }
  // Hysteresis: keep current state if between thresholds
}

// ─── Fan Output ──────────────────────────────────────────────────────────────
void applyFanCommand() {
  analogWrite(FAN_PWM_PIN, fanRunning ? fanSpeed : 0);
  // Direction: always inject cool outside air
  digitalWrite(FAN_DIR_PIN, HIGH);
}

// ─── Energy Accounting ───────────────────────────────────────────────────────
void accumulateEnergy(unsigned long now) {
  float dt_h = (now - lastEnergyTime) / 3600000.0f;
  lastEnergyTime = now;
  // Estimated power: 150W max, cubic relationship with speed
  float speedFrac = fanSpeed / 255.0f;
  float powerW = 150.0f * speedFrac * speedFrac * speedFrac;
  energyWh += powerW * dt_h;
}

// ─── OLED Display ────────────────────────────────────────────────────────────
void updateDisplay() {
  display.clearDisplay();
  display.setCursor(0, 0);

  display.setTextSize(1);
  display.print(F("IN: "));
  display.print(T_inside, 1);
  display.print(F("C  RH:"));
  display.print(humidity, 0);
  display.println(F("%"));

  display.print(F("OUT:"));
  display.print(T_outside, 1);
  display.println(F("C"));

  display.print(F("Fan: "));
  if (fanRunning) {
    display.print((fanSpeed * 100) / 255);
    display.println(F("% ON"));
  } else {
    display.println(F("OFF"));
  }

  display.print(F("Energy: "));
  display.print(energyWh, 1);
  display.println(F("Wh"));

  if (manualMode) display.println(F("[MANUAL MODE]"));

  display.display();
}

// ─── Serial Logging ──────────────────────────────────────────────────────────
void logSerial(unsigned long time_s) {
  Serial.print(time_s);        Serial.print(F(","));
  Serial.print(T_inside, 2);   Serial.print(F(","));
  Serial.print(T_outside, 2);  Serial.print(F(","));
  Serial.print(humidity, 1);   Serial.print(F(","));
  Serial.print(fanSpeed);      Serial.print(F(","));
  Serial.println(energyWh, 3);
}
