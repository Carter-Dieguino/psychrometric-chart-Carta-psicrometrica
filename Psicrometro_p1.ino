#include <Wire.h>
#include <RTClib.h>
#include <DHT.h>
#include <LiquidCrystal.h>
#include <SPI.h>
#include <SdFat.h>  // Usar SdFat en lugar de SD
#include "Adafruit_MAX31855.h"
#include <math.h>

#define SD_CS_PIN 10
#define DHTPIN 8
#define DHTTYPE DHT11

#define MAXDO_1   2
#define MAXCS_1   3
#define MAXCLK_1  4

#define MAXDO_2   5
#define MAXCS_2   6
#define MAXCLK_2  7

const unsigned long INTERVALO_ESCRITURA_MS = 1000;       // 1 segundo
const unsigned long INTERVALO_PROMEDIOS_MS = 60000;      // 1 minuto
const unsigned long INTERVALO_VERIFICACION_SD = 1000;    // 1 segundo

const double ALTURA_CHAPINGO = 2250.0;

LiquidCrystal lcd(32, 30, 28, 26, 24, 22);
RTC_DS3231 rtc;
DHT dht(DHTPIN, DHTTYPE);

Adafruit_MAX31855 termoparTbh(MAXCLK_1, MAXCS_1, MAXDO_1);  // Bulbo húmedo
Adafruit_MAX31855 termoparTbs(MAXCLK_2, MAXCS_2, MAXDO_2);  // Bulbo seco

double sumaTbs = 0.0, sumaTbh = 0.0, sumaDHT = 0.0, sumaHR = 0.0;
unsigned int contadorMuestras = 0;

unsigned long ultimaEscritura = 0;
unsigned long ultimoCalculo = 0;
unsigned long ultimaVerificacionSD = 0;

bool sdDisponible = false;

SdFat SD;

struct ValoresPreviosLCD {
  String tbs = "";
  String tbh = "";
  String tempDHT = "";
  String humDHT = "";
  DateTime fechaHora;
} prevLCD;

class CalculadoraPropiedades {
  public:
    const double Ra = 287.055;

    double gradosKelvin(double temp) {
      return temp + 273.15;
    }

    double calcularPresion(double altura) {
      return 101325.0 * pow((1 - 2.25577e-5 * altura), 5.2559); // en Pa
    }

    double calcularPvs(double T) {
      double T_K = gradosKelvin(T);
      double ln_pws;

      if (T <= 0) {
        // Fórmula para temperaturas <= 0°C
        ln_pws = (-5.6745359e3 / T_K) + 6.3925247 + (-9.6778430e-3 * T_K)
                 + (6.2215701e-7 * pow(T_K, 2)) + (2.0747825e-9 * pow(T_K, 3))
                 + (-9.4840240e-13 * pow(T_K, 4)) + 4.1635019 * log(T_K);
      } else {
        // Fórmula para temperaturas > 0°C
        ln_pws = (-5.8002206e3 / T_K) + 1.3914993 + (-4.8640239e-2 * T_K)
                 + (4.1764768e-5 * pow(T_K, 2)) + (-1.4452093e-8 * pow(T_K, 3))
                 + 6.5459673 * log(T_K);
      }
      return exp(ln_pws);
    }

    double calcularPv(double Hr, double pvs) {
      return (Hr / 100.0) * pvs;
    }

    double razonHumedad(double Pv, double presionAt) {
      return 0.622 * (Pv / (presionAt - Pv));
    }

    double razonHumedadSaturada(double pvs, double presionAt) {
      return 0.622 * (pvs / (presionAt - pvs));
    }

    double gradoSaturacion(double W, double Ws) {
      return (W / Ws) * 100.0;
    }

    double volumenEspecifico(double Tbs, double presionAt, double W) {
      double Tbs_K = gradosKelvin(Tbs);
      return ((Ra * Tbs_K) / presionAt) * ((1 + 1.6078 * W) / (1 + W));
    }

    double temperaturaPuntoRocio(double Pv) {
      double lnPv = log(Pv);
      return (116.9 + 237.3 * lnPv) / (16.78 - lnPv);
    }

    double entalpia(double Tbs, double W) {
      return 1.006 * Tbs + W * (2501 + 1.805 * Tbs);
    }

    double calcularHumedadRelativa(double Tbs, double Tbh, double presionAt) {
      double pvsTbh = calcularPvs(Tbh);
      double pvsTbs = calcularPvs(Tbs);
      double Pv = pvsTbh - presionAt * 0.000662 * (Tbs - Tbh);

      if (Tbs >= Tbh) {
        return (Pv / pvsTbs) * 100.0;
      } else {
        return NAN;
      }
    }
};

struct PropiedadesPsicrometricas {
  double Hr;
  double pvs;
  double Pv;
  double W;
  double Ws;
  double Gsaturacion;
  double Veh;
  double Tpr;
  double h;
};

struct DatosIndividuales {
  uint32_t timestamp;  // Tiempo en segundos desde una fecha base
  float tbs;
  float tbh;
  float tempDHT;
  float humDHT;
};

struct DatosPromedio {
  uint32_t timestamp;  // Tiempo en segundos desde una fecha base
  float promTbs;
  float promTbh;
  float Hr;
  float pvs;
  float Pv;
  float Ws;
  float W;
  float Gsaturacion;
  float Veh;
  float h;
  float Tpr;
  float promTempDHT;
  float promHumDHT;
};

#define TAMANO_BUFFER_INDIVIDUAL 60  // Almacenar hasta 60 registros individuales (1 minuto)
DatosIndividuales bufferDatosIndividuales[TAMANO_BUFFER_INDIVIDUAL];
int indiceBufferIndividuales = 0;

#define TAMANO_BUFFER_PROMEDIO 10  // Almacenar hasta 10 promedios (10 minutos)
DatosPromedio bufferDatosPromedios[TAMANO_BUFFER_PROMEDIO];
int indiceBufferPromedios = 0;

void mostrarEnLCD(String tbsStr, String tbhStr, String tempDHTStr, String humDHTStr, DateTime fecha);
void registrarDatos(double tbs, double tbh, double tempDHT, double humDHT, DateTime ahora);
void calcularPromedios(DateTime ahora);
void verificarSD();
void crearArchivosSiNoExisten();
void escribirDatosPendientes();

void setup() {
  Serial.begin(9600);
  lcd.begin(20, 4);

  if (!rtc.begin()) {
    Serial.println("Error: No se encontró el RTC");
    while (1);
  }

  if (rtc.lostPower()) {
    Serial.println("RTC perdió energía, ajustando fecha y hora...");
    rtc.adjust(DateTime(F(__DATE__), F(__TIME__)));
  }

  dht.begin();
  lcd.clear();

  lcd.setCursor(0, 0);
  lcd.print("Tbs  Tbh  DHT11 HR");
  lcd.setCursor(0, 2);
  lcd.print("Fecha:");
  lcd.setCursor(0, 3);
  lcd.print("Hora: ");

  if (SD.begin(SD_CS_PIN)) {
    sdDisponible = true;
    crearArchivosSiNoExisten();
  } else {
    sdDisponible = false;
    Serial.println("No se pudo inicializar la tarjeta SD.");
  }

  prevLCD.fechaHora = DateTime((uint32_t)0);
}

void loop() {
  DateTime ahora = rtc.now();
  unsigned long tiempoActual = millis();

  double tbs = termoparTbs.readCelsius();
  double tbh = termoparTbh.readCelsius();
  float tempDHT = dht.readTemperature();
  float humDHT = dht.readHumidity();

  if (isnan(tbs) || isnan(tbh) || isnan(tempDHT) || isnan(humDHT)) {
    Serial.println("Error en lectura de sensores");
    return;
  }

  String tbsStr = String(tbs, 1);
  String tbhStr = String(tbh, 1);
  String tempDHTStr = String(tempDHT, 1);
  String humDHTStr = String(humDHT, 1);

  mostrarEnLCD(tbsStr, tbhStr, tempDHTStr, humDHTStr, ahora);

  sumaTbs += tbs;
  sumaTbh += tbh;
  sumaDHT += tempDHT;
  sumaHR += humDHT;
  contadorMuestras++;

  if (tiempoActual - ultimaEscritura >= INTERVALO_ESCRITURA_MS) {
    registrarDatos(tbs, tbh, tempDHT, humDHT, ahora);
    ultimaEscritura = tiempoActual;
  }

  if (tiempoActual - ultimoCalculo >= INTERVALO_PROMEDIOS_MS) {
    calcularPromedios(ahora);
    ultimoCalculo = tiempoActual;
  }

  if (tiempoActual - ultimaVerificacionSD >= INTERVALO_VERIFICACION_SD) {
    verificarSD();
    ultimaVerificacionSD = tiempoActual;
  }
}

void verificarSD() {
  SD.end();
  delay(10);

  if (SD.begin(SD_CS_PIN)) {
    if (!sdDisponible) {
      Serial.println("Tarjeta SD detectada.");
      crearArchivosSiNoExisten();
      escribirDatosPendientes();
    }
    sdDisponible = true;
  } else {
    if (sdDisponible) {
      Serial.println("Tarjeta SD no detectada.");
    }
    sdDisponible = false;
  }
}

void mostrarEnLCD(String tbsStr, String tbhStr, String tempDHTStr, String humDHTStr, DateTime fecha) {
  if (tbsStr != prevLCD.tbs) {
    lcd.setCursor(0, 1);
    lcd.print("    ");
    lcd.setCursor(0, 1);
    lcd.print(tbsStr);
    prevLCD.tbs = tbsStr;
  }

  if (tbhStr != prevLCD.tbh) {
    lcd.setCursor(5, 1);
    lcd.print("    ");
    lcd.setCursor(5, 1);
    lcd.print(tbhStr);
    prevLCD.tbh = tbhStr;
  }

  if (tempDHTStr != prevLCD.tempDHT) {
    lcd.setCursor(10, 1);
    lcd.print("    ");
    lcd.setCursor(10, 1);
    lcd.print(tempDHTStr);
    prevLCD.tempDHT = tempDHTStr;
  }

  if (humDHTStr != prevLCD.humDHT) {
    lcd.setCursor(15, 1);
    lcd.print("    ");
    lcd.setCursor(15, 1);
    lcd.print(humDHTStr);
    prevLCD.humDHT = humDHTStr;
  }

  if (fecha.second() != prevLCD.fechaHora.second() ||
      fecha.minute() != prevLCD.fechaHora.minute() ||
      fecha.hour() != prevLCD.fechaHora.hour() ||
      fecha.day() != prevLCD.fechaHora.day() ||
      fecha.month() != prevLCD.fechaHora.month() ||
      fecha.year() != prevLCD.fechaHora.year()) {

    lcd.setCursor(7, 2);
    lcd.print("          ");
    lcd.setCursor(7, 2);
    lcd.print(fecha.day());
    lcd.print("/");
    lcd.print(fecha.month());
    lcd.print("/");
    lcd.print(fecha.year());

    lcd.setCursor(6, 3);
    lcd.print("        ");
    lcd.setCursor(6, 3);
    if (fecha.hour() < 10) lcd.print('0');
    lcd.print(fecha.hour());
    lcd.print(":");
    if (fecha.minute() < 10) lcd.print('0');
    lcd.print(fecha.minute());
    lcd.print(":");
    if (fecha.second() < 10) lcd.print('0');
    lcd.print(fecha.second());

    prevLCD.fechaHora = fecha;
  }
}

void registrarDatos(double tbs, double tbh, double tempDHT, double humDHT, DateTime ahora) {
  char buffer[128];

  if (sdDisponible) {
    File archivo = SD.open("datos.txt", FILE_WRITE);
    if (archivo) {
      char tbsStr[10], tbhStr[10], tempDHTStr[10], humDHTStr[10];
      dtostrf(tbs, 6, 2, tbsStr);
      dtostrf(tbh, 6, 2, tbhStr);
      dtostrf(tempDHT, 6, 2, tempDHTStr);
      dtostrf(humDHT, 6, 2, humDHTStr);

      sprintf(buffer, "%02d/%02d/%04d\t%02d:%02d:%02d\t%s\t%s\t%s\t%s",
              ahora.day(), ahora.month(), ahora.year(),
              ahora.hour(), ahora.minute(), ahora.second(),
              tbsStr, tbhStr, tempDHTStr, humDHTStr);

      archivo.println(buffer);
      archivo.close();
    } else {
      Serial.println("Error al abrir datos.txt para escritura.");
    }
  } else {
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
      Serial.println("Buffer de datos individuales lleno. Datos antiguos serán sobrescritos.");
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

void calcularPromedios(DateTime ahora) {
  if (contadorMuestras == 0) return;

  double promTbs = sumaTbs / contadorMuestras;
  double promTbh = sumaTbh / contadorMuestras;
  double promTempDHT = sumaDHT / contadorMuestras;
  double promHumDHT = sumaHR / contadorMuestras;

  CalculadoraPropiedades calc;
  PropiedadesPsicrometricas props;
  double presionAt = calc.calcularPresion(ALTURA_CHAPINGO);
  props.Hr = calc.calcularHumedadRelativa(promTbs, promTbh, presionAt);
  if (isnan(props.Hr)) props.Hr = 0.0;
  props.pvs = calc.calcularPvs(promTbs);
  props.Pv = calc.calcularPv(props.Hr, props.pvs);
  props.W = calc.razonHumedad(props.Pv, presionAt);
  props.Ws = calc.razonHumedadSaturada(props.pvs, presionAt);
  props.Gsaturacion = calc.gradoSaturacion(props.W, props.Ws);
  props.Veh = calc.volumenEspecifico(promTbs, presionAt, props.W);
  props.Tpr = calc.temperaturaPuntoRocio(props.Pv);
  props.h = calc.entalpia(promTbs, props.W);

  char buffer[256];

  if (sdDisponible) {
    File archivo = SD.open("promed.txt", FILE_WRITE);
    if (archivo) {
      char promTbsStr[10], promTbhStr[10], HrStr[10], pvsStr[10], PvStr[10], WsStr[10], WStr[10], GsaturacionStr[10], VehStr[10], hStr[10], TprStr[10], promTempDHTStr[10], promHumDHTStr[10];

      dtostrf(promTbs, 6, 2, promTbsStr);
      dtostrf(promTbh, 6, 2, promTbhStr);
      dtostrf(props.Hr, 6, 2, HrStr);
      dtostrf(props.pvs, 8, 2, pvsStr);
      dtostrf(props.Pv, 8, 2, PvStr);
      dtostrf(props.Ws, 8, 5, WsStr);
      dtostrf(props.W, 8, 5, WStr);
      dtostrf(props.Gsaturacion, 6, 2, GsaturacionStr);
      dtostrf(props.Veh, 8, 2, VehStr);
      dtostrf(props.h, 8, 2, hStr);
      dtostrf(props.Tpr, 6, 2, TprStr);
      dtostrf(promTempDHT, 6, 2, promTempDHTStr);
      dtostrf(promHumDHT, 6, 2, promHumDHTStr);

      sprintf(buffer, "%02d/%02d/%04d\t%02d:%02d:%02d\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s",
              ahora.day(), ahora.month(), ahora.year(),
              ahora.hour(), ahora.minute(), ahora.second(),
              promTbsStr, promTbhStr, HrStr, pvsStr, PvStr, WsStr, WStr, GsaturacionStr, VehStr, hStr, TprStr, promTempDHTStr, promHumDHTStr);

      archivo.println(buffer);
      archivo.close();
    } else {
      Serial.println("Error al abrir promed.txt para escritura.");
    }
  } else {
    if (indiceBufferPromedios < TAMANO_BUFFER_PROMEDIO) {
      DatosPromedio datosProm;
      datosProm.timestamp = ahora.unixtime();
      datosProm.promTbs = promTbs;
      datosProm.promTbh = promTbh;
      datosProm.Hr = props.Hr;
      datosProm.pvs = props.pvs;
      datosProm.Pv = props.Pv;
      datosProm.Ws = props.Ws;
      datosProm.W = props.W;
      datosProm.Gsaturacion = props.Gsaturacion;
      datosProm.Veh = props.Veh;
      datosProm.h = props.h;
      datosProm.Tpr = props.Tpr;
      datosProm.promTempDHT = promTempDHT;
      datosProm.promHumDHT = promHumDHT;

      bufferDatosPromedios[indiceBufferPromedios] = datosProm;
      indiceBufferPromedios++;
    } else {
      Serial.println("Buffer de datos promediados lleno. Datos antiguos serán sobrescritos.");
      for (int i = 1; i < TAMANO_BUFFER_PROMEDIO; i++) {
        bufferDatosPromedios[i - 1] = bufferDatosPromedios[i];
      }
      DatosPromedio datosProm;
      datosProm.timestamp = ahora.unixtime();
      datosProm.promTbs = promTbs;
      datosProm.promTbh = promTbh;
      datosProm.Hr = props.Hr;
      datosProm.pvs = props.pvs;
      datosProm.Pv = props.Pv;
      datosProm.Ws = props.Ws;
      datosProm.W = props.W;
      datosProm.Gsaturacion = props.Gsaturacion;
      datosProm.Veh = props.Veh;
      datosProm.h = props.h;
      datosProm.Tpr = props.Tpr;
      datosProm.promTempDHT = promTempDHT;
      datosProm.promHumDHT = promHumDHT;
      bufferDatosPromedios[TAMANO_BUFFER_PROMEDIO - 1] = datosProm;
    }
  }

  sumaTbs = sumaTbh = sumaDHT = sumaHR = 0.0;
  contadorMuestras = 0;
}

void crearArchivosSiNoExisten() {
  if (!SD.exists("datos.txt")) {
    File archivo = SD.open("datos.txt", FILE_WRITE);
    if (archivo) {
      archivo.println("Fecha\tHora\t\tTbs\t\tTbh\t\tDHT11\t\tHR");
      archivo.close();
    } else {
      Serial.println("Error al crear datos.txt");
    }
  }

  if (!SD.exists("promed.txt")) {
    File archivo = SD.open("promed.txt", FILE_WRITE);
    if (archivo) {
      archivo.println("Fecha\tHora\t\tProm_Tbs\tProm_Tbh\tHR\t\tPvs\t\tPv\t\tWs\t\tW\t\tG_sat\t\tVesp\t\th\t\tTpr\t\tProm_DHT11\tProm_HR");
      archivo.close();
    } else {
      Serial.println("Error al crear promed.txt");
    }
  }
}

void escribirDatosPendientes() {
  char buffer[256];

  if (indiceBufferIndividuales > 0) {
    Serial.println("Escribiendo datos individuales pendientes en la SD...");
    File archivo = SD.open("datos.txt", FILE_WRITE);
    if (archivo) {
      for (int i = 0; i < indiceBufferIndividuales; i++) {
        DateTime fechaHora(bufferDatosIndividuales[i].timestamp);

        char tbsStr[10], tbhStr[10], tempDHTStr[10], humDHTStr[10];
        dtostrf(bufferDatosIndividuales[i].tbs, 6, 2, tbsStr);
        dtostrf(bufferDatosIndividuales[i].tbh, 6, 2, tbhStr);
        dtostrf(bufferDatosIndividuales[i].tempDHT, 6, 2, tempDHTStr);
        dtostrf(bufferDatosIndividuales[i].humDHT, 6, 2, humDHTStr);

        sprintf(buffer, "%02d/%02d/%04d\t%02d:%02d:%02d\t%s\t%s\t%s\t%s",
                fechaHora.day(), fechaHora.month(), fechaHora.year(),
                fechaHora.hour(), fechaHora.minute(), fechaHora.second(),
                tbsStr, tbhStr, tempDHTStr, humDHTStr);

        archivo.println(buffer);
      }
      archivo.close();
      indiceBufferIndividuales = 0;
    } else {
      Serial.println("Error al abrir datos.txt para escritura.");
    }
  }

  if (indiceBufferPromedios > 0) {
    Serial.println("Escribiendo datos promediados pendientes en la SD...");
    File archivo = SD.open("promed.txt", FILE_WRITE);
    if (archivo) {
      for (int i = 0; i < indiceBufferPromedios; i++) {
        DateTime fechaHora(bufferDatosPromedios[i].timestamp);

        char promTbsStr[10], promTbhStr[10], HrStr[10], pvsStr[10], PvStr[10], WsStr[10], WStr[10], GsaturacionStr[10], VehStr[10], hStr[10], TprStr[10], promTempDHTStr[10], promHumDHTStr[10];

        dtostrf(bufferDatosPromedios[i].promTbs, 6, 2, promTbsStr);
        dtostrf(bufferDatosPromedios[i].promTbh, 6, 2, promTbhStr);
        dtostrf(bufferDatosPromedios[i].Hr, 6, 2, HrStr);
        dtostrf(bufferDatosPromedios[i].pvs, 8, 2, pvsStr);
        dtostrf(bufferDatosPromedios[i].Pv, 8, 2, PvStr);
        dtostrf(bufferDatosPromedios[i].Ws, 8, 5, WsStr);
        dtostrf(bufferDatosPromedios[i].W, 8, 5, WStr);
        dtostrf(bufferDatosPromedios[i].Gsaturacion, 6, 2, GsaturacionStr);
        dtostrf(bufferDatosPromedios[i].Veh, 8, 2, VehStr);
        dtostrf(bufferDatosPromedios[i].h, 8, 2, hStr);
        dtostrf(bufferDatosPromedios[i].Tpr, 6, 2, TprStr);
        dtostrf(bufferDatosPromedios[i].promTempDHT, 6, 2, promTempDHTStr);
        dtostrf(bufferDatosPromedios[i].promHumDHT, 6, 2, promHumDHTStr);

        sprintf(buffer, "%02d/%02d/%04d\t%02d:%02d:%02d\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s",
                fechaHora.day(), fechaHora.month(), fechaHora.year(),
                fechaHora.hour(), fechaHora.minute(), fechaHora.second(),
                promTbsStr, promTbhStr, HrStr, pvsStr, PvStr, WsStr, WStr, GsaturacionStr, VehStr, hStr, TprStr, promTempDHTStr, promHumDHTStr);

        archivo.println(buffer);
      }
      archivo.close();
      indiceBufferPromedios = 0;
    } else {
      Serial.println("Error al abrir promed.txt para escritura.");
    }
  }
}
