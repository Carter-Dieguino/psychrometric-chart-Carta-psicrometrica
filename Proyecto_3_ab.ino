#include <Wire.h>
#include <RTClib.h>
#include <DHT.h>
#include <LiquidCrystal.h>
#include <SPI.h>
#include <SdFat.h>  
#include "Adafruit_MAX31855.h"
#include <math.h>

#define SD_CS_PIN 10
#define DHTPIN 8
#define DHTTYPE DHT11

// Pines para los sensores MAX31855 existentes
// Bulbo húmedo
#define MAXDO_1   2
#define MAXCS_1   3
#define MAXCLK_1  4
// Bulbo seco
#define MAXDO_2   5
#define MAXCS_2   6
#define MAXCLK_2  7

const double ALTURA_CHAPINGO = 2250.0;  // Altitud en metros

// Compensación para los sensores
const double COMPENSACION_TBS = 0.0;     // Ajustable en el futuro
const double COMPENSACION_TBH = 0.0;     // Ajustable en el futuro

LiquidCrystal lcd(32, 30, 28, 26, 24, 22);  // Inicializar LCD
RTC_DS3231 rtc;  // Inicializar RTC
DHT dht(DHTPIN, DHTTYPE);  // Inicializar sensor DHT11

// Inicializar sensores termopar MAX31855
Adafruit_MAX31855 termoparTbh(MAXCLK_1, MAXCS_1, MAXDO_1);  // Bulbo húmedo
Adafruit_MAX31855 termoparTbs(MAXCLK_2, MAXCS_2, MAXDO_2);  // Bulbo seco

bool sdDisponible = false;  // Bandera de disponibilidad de la SD

SdFat SD;  // Usar biblioteca SdFat para operaciones con la tarjeta SD

// Estructura para almacenar datos individuales con variables enteras
struct DatosIndividuales {
  uint32_t timestamp;  // 4 bytes
  int16_t tbs;        // 2 bytes (temperatura * 10)
  int16_t tbh;        // 2 bytes (temperatura * 10)
  int16_t tempDHT;    // 2 bytes (temperatura * 10)
  int16_t humDHT;     // 2 bytes (humedad * 10)
};
// Total por entrada: 4 + (2 * 4) = 12 bytes

#define TAMANO_BUFFER_INDIVIDUAL 260  // Ajustado a 260 entradas
DatosIndividuales bufferDatosIndividuales[TAMANO_BUFFER_INDIVIDUAL];
int indiceBufferIndividuales = 0;

int segundoAnterior = -1;  // Variable para detectar cambio de segundo

// Estructura para almacenar valores previos de la LCD y actualizar solo cuando cambien
struct ValoresPreviosLCD {
  String tbs = "";
  String tbh = "";
  String tempDHT = "";
  String humDHT = "";
  DateTime fechaHora;
} prevLCD;

// Prototipos de funciones
void mostrarEnLCD(String tbsStr, String tbhStr, String tempDHTStr, String humDHTStr, DateTime fecha);
void registrarDatos(int16_t tbs, int16_t tbh, int16_t tempDHT, int16_t humDHT, DateTime ahora);
void verificarSD();
void crearArchivosSiNoExisten();
void escribirDatosPendientes();

void setup() {
  Serial.begin(9600);
  lcd.begin(20, 4);  // Inicializar LCD con 20 columnas y 4 filas

  if (!rtc.begin()) {
    Serial.println(F("Error: No se encontró el RTC"));  // RTC no encontrado
    while (1);
  }

  if (rtc.lostPower()) {
    Serial.println(F("RTC perdió energía, ajustando fecha y hora..."));
    rtc.adjust(DateTime(F(__DATE__), F(__TIME__)));  // Ajustar RTC a la hora de compilación
  }

  dht.begin();
  lcd.clear();

  lcd.setCursor(0, 0);
  lcd.print(F("Iniciando..."));
  
  sdDisponible = SD.begin(SD_CS_PIN);
  if (sdDisponible) {
    crearArchivosSiNoExisten();
    escribirDatosPendientes();  // Intentar escribir datos pendientes al inicio
  } else {
    Serial.println(F("No se pudo inicializar la tarjeta SD."));
  }

  prevLCD.fechaHora = DateTime((uint32_t)0);  // Inicializar fecha/hora previa de la LCD
}

void loop() {
  DateTime ahora = rtc.now();

  // Verificar si ha cambiado el segundo
  if (ahora.second() != segundoAnterior) {
    segundoAnterior = ahora.second();

    // Leer sensores
    double tbs = termoparTbs.readCelsius();
    double tbh = termoparTbh.readCelsius();
    float tempDHT = dht.readTemperature();
    float humDHT = dht.readHumidity();

    if (isnan(tbs) || isnan(tbh) || isnan(tempDHT) || isnan(humDHT)) {
      Serial.println(F("Error en lectura de sensores"));
      return;
    }

    // Aplicar compensaciones
    tbs += COMPENSACION_TBS;
    tbh += COMPENSACION_TBH;

    // Convertir valores a enteros escalados (temperatura * 10, humedad * 10)
    int16_t tbsInt = (int16_t)(tbs * 10);
    int16_t tbhInt = (int16_t)(tbh * 10);
    int16_t tempDHTInt = (int16_t)(tempDHT * 10);
    int16_t humDHTInt = (int16_t)(humDHT * 10);

    // Convertir valores a String para mostrar en LCD
    String tbsStr = String(tbs, 1);
    String tbhStr = String(tbh, 1);
    String tempDHTStr = String(tempDHT, 1);
    String humDHTStr = String(humDHT, 0);  // Mostrar como entero

    mostrarEnLCD(tbsStr, tbhStr, tempDHTStr, humDHTStr, ahora);
    registrarDatos(tbsInt, tbhInt, tempDHTInt, humDHTInt, ahora);

    verificarSD();
  }
}

void verificarSD() {
  static unsigned long ultimaVerificacionSD = 0;
  DateTime ahora = rtc.now();

  // Verificar tarjeta SD cada minuto
  if (ahora.minute() != ultimaVerificacionSD) {
    ultimaVerificacionSD = ahora.minute();

    SD.end();
    delay(10);

    if (SD.begin(SD_CS_PIN)) {
      if (!sdDisponible) {
        Serial.println(F("Tarjeta SD detectada."));
        crearArchivosSiNoExisten();
        escribirDatosPendientes();
      }
      sdDisponible = true;
    } else {
      if (sdDisponible) {
        Serial.println(F("Tarjeta SD no detectada."));
      }
      sdDisponible = false;
    }
  }
}

void mostrarEnLCD(String tbsStr, String tbhStr, String tempDHTStr, String humDHTStr, DateTime fecha) {
  // Línea 0: Tbs y Tbh
  if (tbsStr != prevLCD.tbs || tbhStr != prevLCD.tbh) {
    lcd.setCursor(0, 0);
    lcd.print(F("Tbs:"));
    lcd.print(tbsStr);
    lcd.print(F(" Tbh:"));
    lcd.print(tbhStr);
    lcd.print(F("   ")); // Limpiar el resto de la línea
    prevLCD.tbs = tbsStr;
    prevLCD.tbh = tbhStr;
  }

  // Línea 1: Temp y Humedad DHT11
  if (tempDHTStr != prevLCD.tempDHT || humDHTStr != prevLCD.humDHT) {
    lcd.setCursor(0, 1);
    lcd.print(F("T:"));
    lcd.print(tempDHTStr);
    lcd.print(F(" Hr:"));
    lcd.print(humDHTStr);
    lcd.print(F("%"));
    lcd.print(F("   ")); // Limpiar el resto de la línea
    prevLCD.tempDHT = tempDHTStr;
    prevLCD.humDHT = humDHTStr;
  }

  // Línea 3: Fecha y Hora (dejamos línea 2 vacía)
  if (fecha.second() != prevLCD.fechaHora.second()) {
    lcd.setCursor(0, 3);
    if (fecha.day() < 10) lcd.print('0');
    lcd.print(fecha.day());
    lcd.print('/');
    if (fecha.month() < 10) lcd.print('0');
    lcd.print(fecha.month());
    lcd.print('/');
    lcd.print(fecha.year() % 100); // Últimos dos dígitos del año
    lcd.print(' ');
    if (fecha.hour() < 10) lcd.print('0');
    lcd.print(fecha.hour());
    lcd.print(':');
    if (fecha.minute() < 10) lcd.print('0');
    lcd.print(fecha.minute());
    lcd.print(':');
    if (fecha.second() < 10) lcd.print('0');
    lcd.print(fecha.second());
    lcd.print(F("   ")); // Limpiar el resto de la línea

    prevLCD.fechaHora = fecha;
  }
}

void registrarDatos(int16_t tbs, int16_t tbh, int16_t tempDHT, int16_t humDHT, DateTime ahora) {
  char buffer[256];

  if (sdDisponible) {
    File archivo = SD.open("datos.txt", FILE_WRITE);
    if (archivo) {
      // Convertir valores a cadenas para escribir en la SD
      char tbsStr[10], tbhStr[10], tempDHTStr[10], humDHTStr[10];

      dtostrf(tbs / 10.0, 6, 1, tbsStr);
      dtostrf(tbh / 10.0, 6, 1, tbhStr);
      dtostrf(tempDHT / 10.0, 6, 1, tempDHTStr);
      dtostrf(humDHT / 10.0, 6, 1, humDHTStr);

      sprintf(buffer, "%02d/%02d/%04d\t%02d:%02d:%02d\t%s\t%s\t%s\t%s",
              ahora.day(), ahora.month(), ahora.year(),
              ahora.hour(), ahora.minute(), ahora.second(),
              tbsStr, tbhStr, tempDHTStr, humDHTStr);

      archivo.println(buffer);
      archivo.close();
    } else {
      Serial.println(F("Error al abrir datos.txt para escritura."));
      sdDisponible = false;  // Marcar SD como no disponible
    }
  } else {
    // Almacenar datos en el buffer si la SD no está disponible
    if (indiceBufferIndividuales < TAMANO_BUFFER_INDIVIDUAL) {
      DatosIndividuales datosInd;
      datosInd.timestamp = ahora.unixtime();
      datosInd.tbs = tbs;
      datosInd.tbh = tbh;
      datosInd.tempDHT = tempDHT;
      datosInd.humDHT = humDHT;

      bufferDatosIndividuales[indiceBufferIndividuales] = datosInd;
      indiceBufferIndividuales++;
    } else {
      // Si el buffer está lleno, sobrescribir los datos más antiguos
      Serial.println(F("Buffer de datos individuales lleno. Datos antiguos serán sobrescritos."));
      for (int i = 1; i < TAMANO_BUFFER_INDIVIDUAL; i++) {
        bufferDatosIndividuales[i - 1] = bufferDatosIndividuales[i];
      }
      DatosIndividuales datosInd;
      datosInd.timestamp = ahora.unixtime();
      datosInd.tbs = tbs;
      datosInd.tbh = tbh;
      datosInd.tempDHT = tempDHT;
      datosInd.humDHT = humDHT;
      bufferDatosIndividuales[TAMANO_BUFFER_INDIVIDUAL - 1] = datosInd;
    }
  }
}

void crearArchivosSiNoExisten() {
  if (!SD.exists("datos.txt")) {
    File archivo = SD.open("datos.txt", FILE_WRITE);
    if (archivo) {
      archivo.println(F("Fecha\t\tHora\t\tTbs\tTbh\tDHT11T\tDHT11HR"));
      archivo.close();
    } else {
      Serial.println(F("Error al crear datos.txt"));
    }
  }
}

void escribirDatosPendientes() {
  if (indiceBufferIndividuales > 0 && sdDisponible) {
    Serial.println(F("Escribiendo datos individuales pendientes en la SD..."));
    File archivo = SD.open("datos.txt", FILE_WRITE);
    if (archivo) {
      char buffer[256];
      for (int i = 0; i < indiceBufferIndividuales; i++) {
        DateTime fechaHora(bufferDatosIndividuales[i].timestamp);

        char tbsStr[10], tbhStr[10], tempDHTStr[10], humDHTStr[10];

        dtostrf(bufferDatosIndividuales[i].tbs / 10.0, 6, 1, tbsStr);
        dtostrf(bufferDatosIndividuales[i].tbh / 10.0, 6, 1, tbhStr);
        dtostrf(bufferDatosIndividuales[i].tempDHT / 10.0, 6, 1, tempDHTStr);
        dtostrf(bufferDatosIndividuales[i].humDHT / 10.0, 6, 1, humDHTStr);

        sprintf(buffer, "%02d/%02d/%04d\t%02d:%02d:%02d\t%s\t%s\t%s\t%s",
                fechaHora.day(), fechaHora.month(), fechaHora.year(),
                fechaHora.hour(), fechaHora.minute(), fechaHora.second(),
                tbsStr, tbhStr, tempDHTStr, humDHTStr);

        archivo.println(buffer);
      }
      archivo.close();
      indiceBufferIndividuales = 0;
    } else {
      Serial.println(F("Error al abrir datos.txt para escritura."));
    }
  }
}
