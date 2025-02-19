/*
  cal                     // Iniciar calibración
  [1-7]                  // Seleccionar sensor de referencia
  [8]                    // Usar DHT como referencia
  [9]                    // Usar valor manual
  [temperatura]          // Si se eligió valor manual
  [1-3]                 // Minutos de calibración
  'cancel'              // Cancelar calibración en cualquier momento
*/

// Primero todos los includes
#include <Wire.h>
#include <RTClib.h>
#include <DHT.h>
#include <LiquidCrystal.h>
#include <SPI.h>
#include <SdFat.h>
#include <EEPROM.h>
#include "Adafruit_MAX31855.h"
#include "max6675.h"

// Luego las definiciones de pines y constantes
#define SD_CS_PIN 53
// Modificar definición de pines DHT
#define DHT22_PIN 40
#define DHT11_PIN 45
#define DHTTYPE_22 DHT22
#define DHTTYPE_11 DHT11
// Buffer 
#define DATA_BUFFER_SIZE 15
#define BUFFER_THRESHOLD (DATA_BUFFER_SIZE - 1)
#define EEPROM_CALIBRATION_START 0
#define CALIBRATION_BYTES_PER_SENSOR 8
#define ERROR_MESSAGE_DURATION 5000
#define DISPLAY_UPDATE_INTERVAL 1000
// Definiciones para tablas de calibración
#define MAX_CALIBRATION_TABLES 15
#define TABLE_NAME_LENGTH 16
#define TABLE_DATA_SIZE (7 * sizeof(SensorCalibration))
#define TABLE_HEADER_SIZE (TABLE_NAME_LENGTH + 1) // +1 para el flag de activo
#define TOTAL_TABLE_SIZE (TABLE_HEADER_SIZE + TABLE_DATA_SIZE)
#define TABLES_START_ADDRESS 0
#define ACTIVE_TABLE_ADDRESS (MAX_CALIBRATION_TABLES * TOTAL_TABLE_SIZE)
// Agregar al inicio con las otras definiciones
#define MAIN_MENU 0
#define CALIBRATION_MENU 1
#define RESET_MENU 2
#define OFFSET_MENU 3
#define TABLE_MENU 4
#define SD_MENU 5
// Definir nuevas constantes
#define TABLES_FILENAME "tablas.dat"
#define DATA_FILENAME "datos.txt"
#define TABLES_BACKUP_FILENAME "tablas.bak"
#define MAX_PATH_LEN 64  // Para nombres de archivo
#define TABLES_FILENAME "tablas.dat"
#define TABLES_BACKUP_FILENAME "tablas.bak"
// Constantes para validación
const float MIN_VALID_TEMP = -50.0;
const float MAX_VALID_TEMP = 300.0;
const unsigned long CALIBRATION_TIMEOUT = 300000; // 5 minutos

// Estructuras de pines como PROGMEM
const PROGMEM uint8_t MAX31855_PINS[][3] = {
    {2, 3, 4},     // S1
    {5, 6, 7},     // S2
    {8, 9, 10},    // S3
    {11, 12, 13},  // S4
    {A4, 38, A5}   // S5
};

const PROGMEM uint8_t MAX6675_PINS[][3] = {
    {A1, 34, A0},  // S6
    {A3, 36, A2}   // S7
};

// Enumeración para tipo de referencia
enum RefType {
    REF_NONE = 0,
    REF_SENSOR = 1,
    REF_DHT = 2,
    REF_MANUAL = 3
};

// Estructuras de datos
struct SensorCalibration {
    float offset;
    float slope;
};

// Estructura para el encabezado de tabla
struct CalibrationTableHeader {
    char name[TABLE_NAME_LENGTH];
    bool active;
} __attribute__((packed));

// Estructura para tabla completa
struct CalibrationTable {
    CalibrationTableHeader header;
    SensorCalibration calibrations[7];
} __attribute__((packed));

struct CalibrationConfig {
    RefType refType;
    int refSensor;
    float refValue;
    unsigned long duration;
    DateTime startTime;
};

struct SensorState {
    bool isConnected: 1;
    float lastValue;
    float sumValue;
    int readCount;
    unsigned long lastErrorTime;
};

struct {
    SensorState sensors[7];
    bool dht22_ok: 1;
    bool dht11_ok: 1;
    unsigned long dht22LastErrorTime;
    unsigned long dht11LastErrorTime;
} sensorStates;

// Primero definimos SensorData (debe ir después de las definiciones de constantes y antes de otras estructuras)
struct SensorData {
    DateTime timestamp;
    float values[7];
    float tempDHT22;
    float humDHT22;
    float tempDHT11;
    float humDHT11;
    bool sensorOk[7];
    bool dht22Ok;
    bool dht11Ok;
} __attribute__((packed));

// Estructura del buffer circular (debe ir después de SensorData)
struct CircularBuffer {
    SensorData data[DATA_BUFFER_SIZE];
    int head;
    int tail;
    int count;
};

// Variables globales
SensorCalibration sensorCalibrations[7];
CalibrationConfig calConfig;
CircularBuffer dataBuffer;  // Reemplaza a la anterior declaración de SensorData* dataBuffer
bool calibrationMode = false;
bool calibrationSetupComplete = false;
bool sdAvailable = false;
bool displayingError = false;
unsigned long lastDisplayUpdate = 0;
unsigned long lastCalibrationActivity = 0;
bool isCalibrated = false;
int activeTableIndex = -1;
// Variable global para control de menú
uint8_t currentMenu = MAIN_MENU;

// Objetos
LiquidCrystal lcd(32, 30, 28, 26, 24, 22);
RTC_DS3231 rtc;
DHT dht22(DHT22_PIN, DHTTYPE_22);
DHT dht11(DHT11_PIN, DHTTYPE_11);
SdFat SD;
Adafruit_MAX31855* max31855Sensors[5];
MAX6675* max6675Sensors[2];

// PROTOTIPOS DE FUNCIONES
void showTemporaryMessage(const char* line1, const char* line2 = NULL, 
                         const char* line3 = NULL, const char* line4 = NULL, 
                         int duration = 2000);
void updateMainDisplay(DateTime now);
void printSensorValue(int index);
bool isValidTemperature(float temp);
void processCalibrationInput(String input);
void backupCurrentCalibration();
void restoreFromBackup();
float applySensorCalibration(int sensorIndex, float rawValue);
void handleSensorError(int index);
void displayError(const char* message);
void createFilesIfNotExist();
void checkSensors();
void logData(DateTime now);
void checkSD();
void saveCalibrationToEEPROM();
void loadCalibrationFromEEPROM();
void startCalibration();
void handleCalibration();
void finishCalibration();
void updateCalibrationDisplay();
float getRefTemperature();
void processCalibrationSetup();
void processSerialCommand();

bool loadCalibrationTable(const char* name);
void listCalibrationTables();
void showCurrentOffsets();

// PROTOTIPOS DE FUNCIONES (agregar estas líneas)
void showMainMenu();
void showResetMenu();
void showOffsetMenu();
void showTableManagementMenu();
void showSDMenu();
void resetToDefault(bool affectEEPROM);
void formatDataFile();
void initBuffer();  // Faltaba este prototipo
void deleteCalibrationTables();

// Implementación de funciones
bool isValidTemperature(float temp) {
    return !isnan(temp) && temp >= MIN_VALID_TEMP && temp <= MAX_VALID_TEMP;
}

// Función para inicializar el buffer circular (debe ir antes de setup)
void initBuffer() {
    dataBuffer.head = 0;
    dataBuffer.tail = 0;
    dataBuffer.count = 0;
}

void setup() {
    // Iniciar comunicación serial
    Serial.begin(9600);
    while (!Serial && millis() < 3000) {
        ; // Esperar al puerto serial pero no más de 3 segundos
    }
    Serial.println(F("\n=== SISTEMA INICIANDO ==="));
    
    /*/ Configurar contraste LCD
    if (LCD_CONTRAST_PIN != 255) {  // Si se usa pin de contraste
        pinMode(LCD_CONTRAST_PIN, OUTPUT);
        analogWrite(LCD_CONTRAST_PIN, 80);  // Ajusta este valor (0-255) para el contraste
    }
    */
    
    // Inicializar LCD con configuración mejorada
    lcd.begin(20, 4);
    lcd.clear();
    lcd.home();
    delay(100);  // Pequeña pausa para estabilizar
    
    showTemporaryMessage(
        "Iniciando sistema",
        "Por favor espere",
        "Verificando",
        "componentes..."
    );
    
    // Inicializar RTC
    Serial.println(F("Iniciando RTC..."));
    if (!rtc.begin()) {
        showTemporaryMessage(
            "Error Critico:",
            "RTC no detectado",
            "Sistema detenido",
            "Revisar conexion",
            -1  // No timeout, requiere reset
        );
        Serial.println(F("ERROR: RTC no encontrado"));
        while (1);
    }

    if (rtc.lostPower()) {
        showTemporaryMessage(
            "Aviso: RTC",
            "perdio energia",
            "Ajustando fecha",
            "y hora...",
            2000
        );
        Serial.println(F("RTC perdió energía, ajustando fecha y hora..."));
        rtc.adjust(DateTime(F(__DATE__), F(__TIME__)));
    }
    
    // Cargar calibración
    Serial.println(F("Cargando calibración..."));
    showTemporaryMessage(
        "Cargando",
        "calibracion",
        "desde EEPROM",
        "espere...",
        1000
    );
    loadCalibrationFromEEPROM();
    
    // Asignar buffer para datos
    Serial.println(F("Inicializando buffer de datos..."));
    initBuffer();
    
    showTemporaryMessage(
        "Buffer de datos",
        "inicializado",
        "correctamente",
        NULL,
        1000
    );
    
    // Inicializar sensores MAX31855
    Serial.println(F("Iniciando sensores MAX31855..."));
    showTemporaryMessage(
        "Iniciando",
        "sensores MAX31855",
        "espere...",
        NULL,
        1000
    );
    
    for (int i = 0; i < 5; i++) {
        uint8_t clk = pgm_read_byte(&MAX31855_PINS[i][2]);
        uint8_t cs = pgm_read_byte(&MAX31855_PINS[i][1]);
        uint8_t do_pin = pgm_read_byte(&MAX31855_PINS[i][0]);
        max31855Sensors[i] = new Adafruit_MAX31855(clk, cs, do_pin);
        
        // Verificar sensor
        float testRead = max31855Sensors[i]->readCelsius();
        sensorStates.sensors[i].isConnected = isValidTemperature(testRead);
        sensorStates.sensors[i].lastValue = 0.0;
        sensorStates.sensors[i].sumValue = 0;
        sensorStates.sensors[i].readCount = 0;
        sensorStates.sensors[i].lastErrorTime = 0;
    }
    
    // Inicializar sensores MAX6675
    Serial.println(F("Iniciando sensores MAX6675..."));
    showTemporaryMessage(
        "Iniciando",
        "sensores MAX6675",
        "espere...",
        NULL,
        1000
    );
    
    for (int i = 0; i < 2; i++) {
        uint8_t clk = pgm_read_byte(&MAX6675_PINS[i][2]);
        uint8_t cs = pgm_read_byte(&MAX6675_PINS[i][1]);
        uint8_t do_pin = pgm_read_byte(&MAX6675_PINS[i][0]);
        max6675Sensors[i] = new MAX6675(clk, cs, do_pin);
        
        // Verificar sensor
        float testRead = max6675Sensors[i]->readCelsius();
        sensorStates.sensors[i + 5].isConnected = isValidTemperature(testRead);
        sensorStates.sensors[i + 5].lastValue = 0.0;
        sensorStates.sensors[i + 5].sumValue = 0;
        sensorStates.sensors[i + 5].readCount = 0;
        sensorStates.sensors[i + 5].lastErrorTime = 0;
    }
    
    // Inicializar DHT22
    Serial.println(F("Iniciando DHT22..."));
    dht22.begin();
    float testTemp22 = dht22.readTemperature();
    float testHum22 = dht22.readHumidity();
    sensorStates.dht22_ok = !isnan(testTemp22) && !isnan(testHum22);
    sensorStates.dht22LastErrorTime = 0;
    
    // Inicializar DHT11
    Serial.println(F("Iniciando DHT11..."));
    dht11.begin();
    float testTemp11 = dht11.readTemperature();
    float testHum11 = dht11.readHumidity();
    sensorStates.dht11_ok = !isnan(testTemp11) && !isnan(testHum11);
    sensorStates.dht11LastErrorTime = 0;
    
    // Inicializar SD
    Serial.println(F("Iniciando SD..."));
    showTemporaryMessage(
        "Iniciando",
        "tarjeta SD",
        "espere...",
        NULL,
        1000
    );

    // Inicializar buffer circular
    initBuffer();
    
    sdAvailable = SD.begin(SD_CS_PIN);
    if (sdAvailable) {
        Serial.println(F("SD detectada, creando archivos..."));
        createFilesIfNotExist();
    } else {
        Serial.println(F("ADVERTENCIA: SD no detectada"));
        showTemporaryMessage(
            "Advertencia:",
            "SD no detectada",
            "Usando buffer",
            "temporal",
            2000
        );
    }
    
    // Resumen del estado del sistema
    String sensorStatus = "";
    int sensoresOk = 0;
    for (int i = 0; i < 7; i++) {
        if (sensorStates.sensors[i].isConnected) sensoresOk++;
    }
    
    char statusLine[21];
    char dhtStatus[21];
    sprintf(statusLine, "Sensores OK: %d/7", sensoresOk);
    sprintf(dhtStatus, "DHT22:%s DHT11:%s",
            sensorStates.dht22_ok ? "OK" : "ERR",
            sensorStates.dht11_ok ? "OK" : "ERR");
    
    showTemporaryMessage(
        "Sistema Listo",
        statusLine,
        sdAvailable ? "SD: OK" : "SD: No detectada",
        dhtStatus,
        3000
    );
    
    // Mostrar menú principal
    Serial.println(F("\n=== SISTEMA LISTO ==="));
    Serial.print(F("Sensores activos: "));
    Serial.println(sensoresOk);
    Serial.print(F("SD Card: "));
    Serial.println(sdAvailable ? F("OK") : F("No disponible"));
    Serial.print(F("DHT22: "));
    Serial.println(sensorStates.dht22_ok ? F("OK") : F("Error"));
    Serial.print(F("DHT11: "));
    Serial.println(sensorStates.dht11_ok ? F("OK") : F("Error"));
    
    // Mostrar comandos disponibles
    Serial.println(F("\nComandos disponibles:"));
    Serial.println(F("cal    : Iniciar calibración"));
    Serial.println(F("reset  : Restablecer valores por defecto"));
    Serial.println(F("offset : Ajustar offset manual"));
    Serial.println(F("show   : Mostrar offsets actuales"));
    Serial.println(F("save   : Guardar tabla actual"));
    Serial.println(F("load   : Cargar tabla guardada"));
    Serial.println(F("list   : Listar tablas guardadas"));
    Serial.println(F("help   : Mostrar esta ayuda"));
    Serial.println(F("back   : Volver al menú anterior"));
    Serial.println(F("menu   : Mostrar menú actual"));
    Serial.println(F("========================\n"));
    
    currentMenu = MAIN_MENU;  // Establecer menú inicial
    lastDisplayUpdate = 0;  // Forzar primera actualización de pantalla
}

// Funciones de visualización
void updateMainDisplay(DateTime now) {
    //lcd.clear();
    if (!displayingError) {
        // Primera línea: Estado del sistema, S1-S3 y contador de buffer
        lcd.setCursor(0, 0);
        lcd.print(sdAvailable ? F("SD1") : F("SD"));
        
        // Mostrar contador de buffer si la SD no está disponible
        if (!sdAvailable) {
            lcd.print(F("B"));
            lcd.print(dataBuffer.count);  // Muestra el número directamente: B1, B2, B10, B100, etc.
            
            // Agregar espacios para mantener alineación
            if (dataBuffer.count < 10) lcd.print(F("  "));       // B1__
            else if (dataBuffer.count < 100) lcd.print(F(" "));  // B10_
            // No necesita espacios para B100
        } else {
            lcd.print(F("   "));  // Espacios para alinear cuando no hay contador
        }

        // Mostrar sensores S1-S3
        for (int i = 0; i <=2; i++) {
            printSensorValue(i);
            if (i < 2) lcd.print(F(" "));  // Espacio entre sensores, excepto al final
        }
                
        // Segunda línea: S3-S7 (20 caracteres)
        lcd.setCursor(0, 1);
        // Imprimir cada sensor con espaciado controlado
        for (int i = 3; i <= 6; i++) {
            printSensorValue(i);
            if (i < 6) lcd.print(F(" "));  // Espacio entre sensores, excepto al final
        }
        
        // Tercera línea: Información de ambos DHT (20 caracteres)
        lcd.setCursor(0, 2);  // Línea 3
        // Si fallan ambos sensores
        if (!sensorStates.dht11_ok && !sensorStates.dht22_ok) {
            lcd.print(F("Error DTH11 y DTH22 "));
        } 
        // Si falla el DHT11, mostrar solo DHT22
        else if (!sensorStates.dht11_ok) {
            float temp22 = dht22.readTemperature();
            float hum22 = dht22.readHumidity();
            
            lcd.print(F("DHTextERR "));
            if (isValidTemperature(temp22)) {
                if (temp22 < 10) lcd.print(F(" "));
                lcd.print(temp22, 1);
            } else {
                lcd.print(F("ERR"));
            }
            lcd.print(F("int"));
            if (!isnan(hum22)) {
                if (hum22 < 10) lcd.print(F(" "));
                lcd.print(hum22, 0);
            } else {
                lcd.print(F("ERR"));
            }
        }
        // Si falla el DHT22, mostrar solo DHT11
        else if (!sensorStates.dht22_ok) {
            float temp11 = dht11.readTemperature();
            float hum11 = dht11.readHumidity();
            
            lcd.print(F("DHTintERR "));
            if (isValidTemperature(temp11)) {
                if (temp11 < 10) lcd.print(F(" "));
                lcd.print(temp11, 1);
            } else {
                lcd.print(F("ERR"));
            }
            lcd.print(F("ext"));
            if (!isnan(hum11)) {
                if (hum11 < 10) lcd.print(F(" "));
                lcd.print(hum11, 0);
            } else {
                lcd.print(F("ERR"));
            }
            lcd.print(F("   ")); // Relleno con espacios
        }
        // Si ambos funcionan, mostrar los dos
        else {
            float temp11 = dht11.readTemperature();
            float hum11 = dht11.readHumidity();
            float temp22 = dht22.readTemperature();
            float hum22 = dht22.readHumidity();
            
            // DHT11
            if (isValidTemperature(temp11)) {
                if (temp11 < 10) lcd.print(F(" "));
                lcd.print(temp11, 1);
            } else {
                lcd.print(F("ERR"));
            }
            lcd.print(F("ext"));
            if (!isnan(hum11)) {
                if (hum11 < 10) lcd.print(F(" "));
                lcd.print(hum11, 0);
            } else {
                lcd.print(F("ERR"));
            }
            
            // Separador
            lcd.print(F(" "));
            
            // DHT22
            if (isValidTemperature(temp22)) {
                if (temp22 < 10) lcd.print(F(" "));
                lcd.print(temp22, 1);
            } else {
                lcd.print(F("ERR"));
            }
            lcd.print(F("int"));
            if (!isnan(hum22)) {
                if (hum22 < 10) lcd.print(F(" "));
                lcd.print(hum22, 0);
            } else {
                lcd.print(F("ERR"));
            }
        }
        // Cuarta línea: Fecha/Hora (20 caracteres)
        lcd.setCursor(0, 3);  // Línea 4
        lcd.print(isCalibrated ? F("C1") : F("C-"));
        lcd.print(" ");
        char datetime[20];
        sprintf(datetime, "%02d/%02d/%02d %02d:%02d:%02d",
                now.day(), now.month(), now.year() % 100,
                now.hour(), now.minute(), now.second());
                               
        lcd.print(datetime);
    }
}

// Modificar la función printSensorValue para mejor formato
void printSensorValue(int index) {
    if (sensorStates.sensors[index].isConnected) {
        float value = sensorStates.sensors[index].lastValue;
        if (isValidTemperature(value)) {
            char tempStr[6];  // Buffer para el string formateado
            
            if (value < 100) {
                // Formato: XX.X (ej: 25.4) o X.X (ej: 5.4)
                dtostrf(value, 4, 1, tempStr);
                // Asegurar que ocupamos exactamente 4 caracteres
                if (value < 10) {
                    lcd.print(' ');  // Espacio extra para alinear
                }
                lcd.print(tempStr);
            } else {
                lcd.print(F("OVF"));
            }
        } else {
            lcd.print(F("ERR"));
        }
    } else {
        lcd.print(F("---"));
    }
}

// Función auxiliar para mostrar mensajes temporales sin interrumpir la operación
void showTemporaryMessage(const char* line1, const char* line2, 
                         const char* line3, const char* line4, 
                         int duration) {
    lcd.clear();
    lcd.print(line1);
    
    if (line2) {
        lcd.setCursor(0, 1);
        lcd.print(line2);
    }
    
    if (line3) {
        lcd.setCursor(0, 2);
        lcd.print(line3);
    }
    
    if (line4) {
        lcd.setCursor(0, 3);
        lcd.print(line4);
    }
    
    if (duration > 0) {
        delay(duration);
        lastDisplayUpdate = 0; // Forzar actualización inmediata
    }
} 


// Función para mostrar el menú principal
void showMainMenu() {
    Serial.println(F("\n=== MENÚ PRINCIPAL ==="));
    Serial.println(F("cal              : Iniciar calibración"));
    Serial.println(F("reset            : Opciones de reset"));
    Serial.println(F("offset           : Ajustar offset manual"));
    Serial.println(F("table            : Gestión de tablas"));
    Serial.println(F("sd               : Opciones de SD"));
    Serial.println(F("show             : Mostrar configuración actual"));
    Serial.println(F("help             : Mostrar este menú"));
    Serial.println(F("========================"));
}

// Actualizar el menú de calibración para mostrar la nueva opción
void showCalibrationMenu() {
    Serial.println(F("\n=== MODO CALIBRACIÓN ==="));
    Serial.println(F("1-7: Usar sensor S1-S7 como referencia"));
    Serial.println(F("8: Usar sensor DHT11 como referencia"));
    Serial.println(F("9: Usar sensor DHT22 como referencia"));
    Serial.println(F("10: Ingresar valor manual de referencia"));
    Serial.println(F("back o b: Volver al menú principal"));
    Serial.println(F("cancel: Cancelar calibración"));
    Serial.println(F("========================"));
}

void showOffsetMenu() {
    Serial.println(F("\n=== AJUSTE DE OFFSET ==="));
    Serial.println(F("Formato: offset <sensor> <valor>"));
    Serial.println(F("Ejemplo: offset 1 -2.5"));
    Serial.println(F("Sensor: 1-7"));
    Serial.println(F("Valor: -50.0 a 50.0"));
    Serial.println(F("back o b: Volver al menú principal"));
    Serial.println(F("show: Ver valores actuales"));
    Serial.println(F("========================"));
}

void showTableMenu() {
    Serial.println(F("\n=== MANEJO DE TABLAS ==="));
    Serial.println(F("save [nombre]: Guardar configuración actual"));
    Serial.println(F("load [nombre]: Cargar configuración guardada"));
    Serial.println(F("list        : Listar tablas disponibles"));
    Serial.println(F("back o b    : Volver al menú principal"));
    Serial.println(F("========================"));
}

void showResetMenu() {
    Serial.println(F("\n=== OPCIONES DE RESET ==="));
    Serial.println(F("1: Reset temporal (solo RAM)"));
    Serial.println(F("2: Reset permanente (EEPROM)"));
    Serial.println(F("3: Reset tabla actual"));
    Serial.println(F("4: Reset todo (RAM + EEPROM)"));
    Serial.println(F("back: Volver al menú anterior"));
    Serial.println(F("========================"));
}

// Modificar ShowTableMenu para incluir nuevas opciones
void showTableManagementMenu() {
    Serial.println(F("\n=== GESTIÓN DE TABLAS ==="));
    Serial.println(F("save [nombre]     : Guardar nueva tabla"));
    Serial.println(F("load [nombre]     : Cargar tabla"));
    Serial.println(F("setdefault [nom]  : Establecer tabla como default"));
    Serial.println(F("makedefault       : Hacer valores actuales default"));
    Serial.println(F("rename [old] [new]: Renombrar tabla"));
    Serial.println(F("delete [nombre]   : Eliminar tabla"));
    Serial.println(F("list             : Listar tablas"));
    Serial.println(F("menu             : Ir a menú principal"));
    Serial.println(F("back             : Volver"));
    Serial.println(F("========================"));
}

// Modificar showSDMenu para incluir más opciones
void showSDMenu() {
    Serial.println(F("\n=== OPCIONES SD ==="));
    Serial.println(F("1: Borrar archivo de datos"));
    Serial.println(F("2: Borrar tablas de calibración"));
    Serial.println(F("3: Formatear SD completa"));
    Serial.println(F("4: Ver estado SD"));
    Serial.println(F("back: Volver al menú anterior"));
    Serial.println(F("========================"));
}

void displayError(const char* message) {
    displayingError = true;
    lcd.setCursor(0, 2);
    lcd.print(F("                    ")); // Limpiar línea
    lcd.setCursor(0, 2);
    lcd.print(message);
    
    static unsigned long errorEndTime = 0;
    errorEndTime = millis() + ERROR_MESSAGE_DURATION;
    
    if (millis() >= errorEndTime) {
        displayingError = false;
    }
}

// Agregar función para formatear SD completa
// Modificar la función formatSD
void formatSD() {
    Serial.println(F("¡ADVERTENCIA! Se borrarán TODOS los datos de la SD"));
    Serial.println(F("Escriba 'FORMATEAR' para confirmar:"));
    
    while (!Serial.available()) {
        delay(100);
    }
    
    String confirmation = Serial.readStringUntil('\n');
    confirmation.trim();
    
    if (confirmation == "FORMATEAR") {
        // Desmontar SD
        SD.end();
        delay(100);
        
        // Reiniciar SD
        if (SD.begin(SD_CS_PIN)) {
            // Borrar todos los archivos
            FsFile root = SD.open("/");
            if (root) {
                deleteAllFiles(root);
                root.close();
            }
            
            // Recrear estructura básica
            createFilesIfNotExist();
            
            Serial.println(F("SD formateada correctamente"));
            showTemporaryMessage(
                "SD Formateada",
                "Correctamente",
                "Archivos recreados",
                NULL,
                2000
            );
        } else {
            Serial.println(F("Error al formatear SD"));
        }
    } else {
        Serial.println(F("Operación cancelada"));
    }
}

// Función auxiliar para borrar todos los archivos
void deleteAllFiles(FsFile& dir) {
    char name[MAX_PATH_LEN];
    while (true) {
        FsFile entry = dir.openNextFile();
        if (!entry) {
            break;
        }
        
        entry.getName(name, sizeof(name));
        if (!entry.isDirectory()) {
            entry.close();
            SD.remove(name);
        }
        entry.close();
    }
}

// Función auxiliar para mostrar directorio
// Modificar la función printDirectory para manejar correctamente los tamaños de archivo
void printDirectory(FsFile& dir, int numTabs) {
    char name[MAX_PATH_LEN];
    while (true) {
        FsFile entry = dir.openNextFile();
        if (!entry) {
            break;
        }
        
        for (uint8_t i = 0; i < numTabs; i++) {
            Serial.print('\t');
        }
        
        entry.getName(name, sizeof(name));
        Serial.print(name);
        
        if (entry.isDirectory()) {
            Serial.println("/");
            printDirectory(entry, numTabs + 1);
        } else {
            Serial.print("\t\t");
            // Convertir el tamaño a un tipo que Arduino pueda manejar
            uint32_t fileSize = entry.size() & 0xFFFFFFFF; // Tomar solo los 32 bits menos significativos
            if(fileSize < 1024) {
                Serial.print(fileSize);
                Serial.println(F(" B"));
            } else if(fileSize < 1048576) {
                Serial.print(fileSize / 1024);
                Serial.println(F(" KB"));
            } else {
                Serial.print(fileSize / 1048576);
                Serial.println(F(" MB"));
            }
        }
        entry.close();
    }
}

void processCalibrationSetup() {
    while (Serial.available()) {
        String input = Serial.readStringUntil('\n');
        input.trim();

        // Debug - Mostrar lo que se recibió
        Serial.print(F("Entrada recibida: "));
        Serial.println(input);
        
        // Verificar si la entrada es válida
        if (input.length() > 0) {
            processCalibrationInput(input);
            lastCalibrationActivity = millis();
        }
    }
}

// Modificar la función processCalibrationInput para incluir DHT22
void processCalibrationInput(String input) {
    input.trim();
    
    if (input.equalsIgnoreCase("cancel")) {
        calibrationMode = false;
        lcd.clear();
        lcd.print(F("Calibracion"));
        lcd.setCursor(0, 1);
        lcd.print(F("Cancelada"));
        delay(2000);
        return;
    }

    if (calConfig.refType == REF_NONE) {
        int selection = input.toInt();
        
        if (selection >= 1 && selection <= 7) {
            if (!sensorStates.sensors[selection - 1].isConnected) {
                Serial.print(F("Error: Sensor S"));
                Serial.print(selection);
                Serial.println(F(" no responde"));
                return;
            }
            calConfig.refType = REF_SENSOR;
            calConfig.refSensor = selection - 1;
            
            for (int i = 0; i < 7; i++) {
                if (i != calConfig.refSensor) {
                    sensorCalibrations[i].offset = 0.0;
                    sensorCalibrations[i].slope = 1.0;
                }
            }
            
            Serial.println(F("Ingrese duración (1-3 minutos):"));
        } 
        else if (selection == 8) {
            if (!sensorStates.dht11_ok) {
                Serial.println(F("Error: DHT11 no responde"));
                return;
            }
            calConfig.refType = REF_DHT;
            calConfig.refSensor = 0; // DHT11
            
            for (int i = 0; i < 7; i++) {
                sensorCalibrations[i].offset = 0.0;
                sensorCalibrations[i].slope = 1.0;
            }
            
            Serial.println(F("Ingrese duración (1-3 minutos):"));
        }
        else if (selection == 9) { // Nueva opción para DHT22
            if (!sensorStates.dht22_ok) {
                Serial.println(F("Error: DHT22 no responde"));
                return;
            }
            calConfig.refType = REF_DHT;
            calConfig.refSensor = 1; // DHT22
            
            for (int i = 0; i < 7; i++) {
                sensorCalibrations[i].offset = 0.0;
                sensorCalibrations[i].slope = 1.0;
            }
            
            Serial.println(F("Ingrese duración (1-3 minutos):"));
        }
        else if (selection == 10) {
            calConfig.refType = REF_MANUAL;
            Serial.println(F("Ingrese temperatura (-50 a 300°C):"));
        }
        else {
            Serial.println(F("Selección inválida (1-10)"));
            return;
        }
    }
    else if (calConfig.refType == REF_MANUAL && calConfig.refValue == 0.0) {
        float temp = input.toFloat();
        if (isValidTemperature(temp)) {
            calConfig.refValue = temp;
            
            for (int i = 0; i < 7; i++) {
                sensorCalibrations[i].offset = 0.0;
                sensorCalibrations[i].slope = 1.0;
            }
            
            Serial.println(F("Ingrese duración (1-3 minutos):"));
        } else {
            Serial.println(F("Temperatura inválida (-50 a 300°C)"));
            return;
        }
    }
    else {
        int minutes = input.toInt();
        if (minutes >= 1 && minutes <= 3) {
            calConfig.duration = minutes * 60000UL;
            startCalibration();
            calibrationSetupComplete = true;
        } else {
            Serial.println(F("Duración inválida. Use 1-3 minutos."));
            return;
        }
    }
    
    lastCalibrationActivity = millis();
}

void startCalibration() {
    calConfig.startTime = rtc.now();
    
    for (int i = 0; i < 7; i++) {
        sensorStates.sensors[i].sumValue = 0;
        sensorStates.sensors[i].readCount = 0;
        
        float initialReading = readSensor(i);
        if (!isValidTemperature(initialReading)) {
            Serial.print(F("Advertencia: S"));
            Serial.print(i + 1);
            Serial.println(F(" no responde"));
        }
    }
    
    if (calConfig.refType == REF_DHT) {
        float dhtTemp = dht22.readTemperature(); // Cambio aquí
        if (!isValidTemperature(dhtTemp)) {
            Serial.println(F("Error: DHT22 no responde")); // Cambio aquí
            calibrationMode = false;
            return;
        }
    }
    
    lcd.clear();
    lcd.print(F("Calibrando..."));
    Serial.println(F("=== INICIANDO CALIBRACIÓN ==="));
}

void handleCalibration() {
    DateTime now = rtc.now();
    TimeSpan elapsed = now - calConfig.startTime;
    unsigned long elapsedMillis = elapsed.totalseconds() * 1000UL;
    
    // Mostrar progreso cada 5 segundos
    static unsigned long lastProgressUpdate = 0;
    if (millis() - lastProgressUpdate > 5000) {
        lastProgressUpdate = millis();
        Serial.print(F("Progreso calibración: "));
        Serial.print((elapsedMillis * 100) / calConfig.duration);
        Serial.println(F("%"));
    }
    
    if (elapsedMillis >= calConfig.duration) {
        finishCalibration();
        return;
    }
    
    float refTemp = getRefTemperature();
    if (!isValidTemperature(refTemp)) {
        displayError("Error en referencia");
        return;
    }
    
    // Acumular lecturas
    for (int i = 0; i < 7; i++) {
        if (i == calConfig.refSensor && calConfig.refType == REF_SENSOR) continue;
        
        float currentTemp = readSensor(i);
        if (isValidTemperature(currentTemp)) {
            sensorStates.sensors[i].sumValue += (refTemp - currentTemp);
            sensorStates.sensors[i].readCount++;
        }
    }
    
    updateCalibrationDisplay();
}

// Única definición de finishCalibration
void finishCalibration() {
    Serial.println(F("\n=== CALIBRACION COMPLETADA ==="));
    
    // Calcular offsets finales
    for (int i = 0; i < 7; i++) {
        if (i == calConfig.refSensor && calConfig.refType == REF_SENSOR) {
            continue;
        }
        
        if (sensorStates.sensors[i].readCount > 0) {
            // Calcular offset promedio
            sensorCalibrations[i].offset = sensorStates.sensors[i].sumValue / sensorStates.sensors[i].readCount;
            Serial.print(F("S"));
            Serial.print(i + 1);
            Serial.print(F(" Offset: "));
            Serial.println(sensorCalibrations[i].offset);
        }
    }
    
    saveCalibrationToEEPROM();
    
    calibrationMode = false;
    calibrationSetupComplete = false;
    isCalibrated = true;
    
    showTemporaryMessage(
        "Calibracion",
        "Completada!",
        "Valores guardados",
        "en EEPROM",
        3000
    );
}

void restoreFromBackup() {
    const int BACKUP_START = EEPROM_CALIBRATION_START + (7 * CALIBRATION_BYTES_PER_SENSOR);
    for (int i = 0; i < 7; i++) {
        EEPROM.get(BACKUP_START + (i * CALIBRATION_BYTES_PER_SENSOR), sensorCalibrations[i]);
    }
}

void saveCalibrationToEEPROM() {
    SensorCalibration tempCal[7];
    
    // Escribir nueva calibración
    for (int i = 0; i < 7; i++) {
        EEPROM.put(EEPROM_CALIBRATION_START + (i * CALIBRATION_BYTES_PER_SENSOR), sensorCalibrations[i]);
    }
    
    // Verificar escritura
    bool verificationOk = true;
    for (int i = 0; i < 7; i++) {
        EEPROM.get(EEPROM_CALIBRATION_START + (i * CALIBRATION_BYTES_PER_SENSOR), tempCal[i]);
        if (tempCal[i].offset != sensorCalibrations[i].offset || 
            tempCal[i].slope != sensorCalibrations[i].slope) {
            verificationOk = false;
            break;
        }
    }
    
    if (!verificationOk) {
        Serial.println(F("Error al guardar calibración"));
        restoreFromBackup();
        displayError("Error guardando cal");
    }
}

void loadCalibrationFromEEPROM() {
    Serial.println(F("Cargando calibracion de EEPROM..."));
    isCalibrated = false;
    bool hasValidCalibration = false;
    
    for (int i = 0; i < 7; i++) {
        EEPROM.get(EEPROM_CALIBRATION_START + (i * CALIBRATION_BYTES_PER_SENSOR), sensorCalibrations[i]);
        
        if (!isnan(sensorCalibrations[i].offset) && 
            !isnan(sensorCalibrations[i].slope) && 
            sensorCalibrations[i].slope != 0) {
            hasValidCalibration = true;
        } else {
            sensorCalibrations[i].offset = 0.0;
            sensorCalibrations[i].slope = 1.0;
        }
    }
    
    if (hasValidCalibration) {
        showTemporaryMessage(
            "Calibracion",
            "cargada de EEPROM",
            "correctamente",
            NULL,
            2000
        );
        isCalibrated = true;
    } else {
        showTemporaryMessage(
            "Sin calibracion",
            "en EEPROM",
            "Usando valores",
            "por defecto",
            2000
        );
    }
}

// Actualizar getRefTemperature() - Modificar la lectura de DHT
// Modificar getRefTemperature para manejar ambos DHT
float getRefTemperature() {
    switch (calConfig.refType) {
        case REF_SENSOR:
            return readSensor(calConfig.refSensor);
        case REF_DHT:
            if (calConfig.refSensor == 0) { // DHT11
                return dht11.readTemperature();
            } else { // DHT22
                return dht22.readTemperature();
            }
        case REF_MANUAL:
            return calConfig.refValue;
        default:
            return NAN;
    }
}

void updateCalibrationDisplay() {
    lcd.clear();
    lcd.print(F("=== CALIBRANDO ==="));
    
    TimeSpan elapsed = rtc.now() - calConfig.startTime;
    int progress = (elapsed.totalseconds() * 1000UL * 100) / calConfig.duration;
    progress = constrain(progress, 0, 100);
    
    // Barra de progreso visual
    lcd.setCursor(0, 1);
    lcd.print(F("["));
    int barLength = map(progress, 0, 100, 0, 16);
    for(int i = 0; i < 16; i++) {
        lcd.print(i < barLength ? '=' : ' ');
    }
    lcd.print(F("]"));
    
    // Porcentaje numérico
    lcd.setCursor(0, 2);
    lcd.print(F("Progreso: "));
    if(progress < 10) lcd.print(" ");
    if(progress < 100) lcd.print(" ");
    lcd.print(progress);
    lcd.print(F("%"));
    
    lcd.setCursor(0, 3);
    lcd.print(F("Ref: "));
    float refTemp = getRefTemperature();
    if (isValidTemperature(refTemp)) {
        lcd.print(refTemp, 1);
        lcd.print(F("C"));
    } else {
        lcd.print(F("ERROR"));
    }
}


float readSensor(int index) {
    float temp;
    if (index < 5) {
        temp = max31855Sensors[index]->readCelsius();
    } else {
        temp = max6675Sensors[index-5]->readCelsius();
    }
    
    if (!isValidTemperature(temp)) {
        if (sensorStates.sensors[index].isConnected) {
            handleSensorError(index);
        }
        return NAN;
    }
    
    return applySensorCalibration(index, temp);
}

float applySensorCalibration(int sensorIndex, float rawValue) {
    if (!isValidTemperature(rawValue)) return rawValue;
    return (rawValue * sensorCalibrations[sensorIndex].slope) + sensorCalibrations[sensorIndex].offset;
}

void handleSensorError(int index) {
    unsigned long now = millis();
    if (now - sensorStates.sensors[index].lastErrorTime >= ERROR_MESSAGE_DURATION) {
        sensorStates.sensors[index].lastErrorTime = now;
        sensorStates.sensors[index].isConnected = false;
        
        char errorTitle[21];
        char errorDetail[21];
        sprintf(errorTitle, "Error en Sensor %d", index + 1);
        sprintf(errorDetail, "Verificar conexion");
        
        showTemporaryMessage(
            errorTitle,
            errorDetail,
            NULL,
            NULL,
            2000
        );
    }
}

void checkSensors() {
    for (int i = 0; i < 7; i++) {
        float temp = readSensor(i);
        if (isValidTemperature(temp)) {
            sensorStates.sensors[i].lastValue = temp;
            sensorStates.sensors[i].isConnected = true;
        }
    }
    
    // Check DHT22
    if (sensorStates.dht22_ok) {
        float temp22 = dht22.readTemperature();
        float hum22 = dht22.readHumidity();
        if (!isValidTemperature(temp22) || isnan(hum22)) {
            if (millis() - sensorStates.dht22LastErrorTime >= ERROR_MESSAGE_DURATION) {
                sensorStates.dht22LastErrorTime = millis();
                sensorStates.dht22_ok = false;
                displayError("Error en DHT22");
            }
        }
    }
    
    // Check DHT11
    if (sensorStates.dht11_ok) {
        float temp11 = dht11.readTemperature();
        float hum11 = dht11.readHumidity();
        if (!isValidTemperature(temp11) || isnan(hum11)) {
            if (millis() - sensorStates.dht11LastErrorTime >= ERROR_MESSAGE_DURATION) {
                sensorStates.dht11LastErrorTime = millis();
                sensorStates.dht11_ok = false;
                // No mostrar error en pantalla para DHT11
            }
        }
    }
}

// Cargar datos a la SD
void logData(DateTime now) {
    // Crear estructura de datos
    SensorData newData;
    newData.timestamp = now;
    
    // Capturar datos de sensores
    for (int i = 0; i < 7; i++) {
        newData.values[i] = sensorStates.sensors[i].lastValue;
        newData.sensorOk[i] = sensorStates.sensors[i].isConnected;
    }
    
    // DHT22
    if (sensorStates.dht22_ok) {
        newData.tempDHT22 = dht22.readTemperature();
        newData.humDHT22 = dht22.readHumidity();
        newData.dht22Ok = true;
    } else {
        newData.dht22Ok = false;
    }
    
    // DHT11
    if (sensorStates.dht11_ok) {
        newData.tempDHT11 = dht11.readTemperature();
        newData.humDHT11 = dht11.readHumidity();
        newData.dht11Ok = true;
    } else {
        newData.dht11Ok = false;
    }
    
    // Si no hay SD disponible, guardar en buffer y mostrar mensaje
    if (!sdAvailable) {
        addToBuffer(newData);
        static unsigned long lastErrorShow = 0;
        if (millis() - lastErrorShow >= 5000) {  // Mostrar mensaje cada 5 segundos
            lastErrorShow = millis();
            showTemporaryMessage(
                "Error SD",
                "Usando buffer",
                String("Registros: " + String(dataBuffer.count)).c_str(),
                NULL,
                2000
            );
        }
        return;
    }
    
    // Si hay SD, intentar guardar
    File dataFile = SD.open("datos.txt", FILE_WRITE);
    if (!dataFile) {
        sdAvailable = false;
        addToBuffer(newData);  // Guardar en buffer si falla la SD
        showTemporaryMessage(
            "Error SD",
            "Usando buffer",
            String("Registros: " + String(dataBuffer.count)).c_str(),
            NULL,
            2000
        );
        return;
    }
    
    // Escribir datos en SD
    writeDataToFile(dataFile, newData);
    dataFile.close();
}

// Nueva función para escribir datos en archivo
void writeDataToFile(File &file, SensorData &data) {
    char buffer[32];
    DateTime now = data.timestamp;
    
    sprintf(buffer, "%02d/%02d/%04d\t%02d:%02d:%02d",
            now.day(), now.month(), now.year(),
            now.hour(), now.minute(), now.second());
    file.print(buffer);
    
    // Sensores de temperatura
    for (int i = 0; i < 7; i++) {
        file.print('\t');
        if (data.sensorOk[i]) {
            file.print(data.values[i], 1);
        } else {
            file.print("nan");
        }
    }
    
    // DHT22
    file.print('\t');
    if (data.dht22Ok) {
        file.print(data.tempDHT22, 1);
        file.print('\t');
        file.print(data.humDHT22, 0);
    } else {
        file.print("nan\tnan");
    }
    
    // DHT11
    file.print('\t');
    if (data.dht11Ok) {
        file.print(data.tempDHT11, 1);
        file.print('\t');
        file.print(data.humDHT11, 0);
    } else {
        file.print("nan\tnan");
    }
    
    file.println();
}

void createFilesIfNotExist() {
    if (!SD.exists("datos.txt")) {
        File dataFile = SD.open("datos.txt", FILE_WRITE);
        if (dataFile) {
            dataFile.println(F("Fecha\tHora\tS1(C)\tS2(C)\tS3(C)\tS4(C)\tS5(C)\tS6(C)\tS7(C)\tDHT22_Temp(C)\tDHT22_Hum(%)\tDHT11_Temp(C)\tDHT11_Hum(%)"));
            dataFile.close();
        }
    }
}

// Modificar checkSD para mejor manejo de errores
void checkSD() {
    static unsigned long lastSDCheck = 0;
    if (millis() - lastSDCheck > 5000) {
        lastSDCheck = millis();
        
        bool prevSDState = sdAvailable;
        sdAvailable = SD.begin(SD_CS_PIN);
        
        // Si la SD se desconecta
        if (!sdAvailable && prevSDState) {
            showTemporaryMessage(
                "SD Desconectada",
                "Usando buffer",
                String("Registros: " + String(dataBuffer.count)).c_str(),
                NULL,
                2000
            );
        }
        // Si la SD se reconecta y hay datos en el buffer
        else if (sdAvailable && !prevSDState && dataBuffer.count > 0) {
            showTemporaryMessage(
                "SD Detectada",
                "Guardando buffer...",
                String("Registros: " + String(dataBuffer.count)).c_str(),
                NULL,
                2000
            );
            
            File dataFile = SD.open("datos.txt", FILE_WRITE);
            if (dataFile) {
                int savedCount = 0;
                while (dataBuffer.count > 0) {
                    writeDataToFile(dataFile, dataBuffer.data[dataBuffer.tail]);
                    dataBuffer.tail = (dataBuffer.tail + 1) % DATA_BUFFER_SIZE;
                    dataBuffer.count--;
                    savedCount++;
                }
                dataFile.close();
                
                showTemporaryMessage(
                    "Datos Guardados",
                    String("Total: " + String(savedCount)).c_str(),
                    "registros en SD",
                    NULL,
                    2000
                );
            }
        }
        
        // Forzar actualización de la pantalla
        lastDisplayUpdate = 0;
    }
}

// Función para agregar datos al buffer circular
void addToBuffer(const SensorData& newData) {
    if (dataBuffer.count == DATA_BUFFER_SIZE) {
        // Si el buffer está lleno, avanzar tail para sobrescribir el dato más antiguo
        dataBuffer.tail = (dataBuffer.tail + 1) % DATA_BUFFER_SIZE;
        dataBuffer.count--;
    }
    
    // Agregar nuevo dato
    dataBuffer.data[dataBuffer.head] = newData;
    dataBuffer.head = (dataBuffer.head + 1) % DATA_BUFFER_SIZE;
    dataBuffer.count++;
}

// Modificar loadCalibrationTable para usar SD
bool loadCalibrationTable(const char* name) {
    if (!sdAvailable) {
        Serial.println(F("Error: SD no disponible"));
        return false;
    }

    File tableFile = SD.open(TABLES_FILENAME, FILE_READ);
    if (!tableFile) {
        Serial.println(F("Error: No se pudo abrir archivo de tablas"));
        return false;
    }

    CalibrationTable table;
    bool found = false;

    while (tableFile.available() >= sizeof(CalibrationTable)) {
        tableFile.read((uint8_t*)&table, sizeof(CalibrationTable));
        
        if (table.header.active && 
            strncmp(table.header.name, name, TABLE_NAME_LENGTH) == 0) {
            memcpy(sensorCalibrations, table.calibrations, sizeof(sensorCalibrations));
            found = true;
            break;
        }
    }

    tableFile.close();

    if (found) {
        Serial.println(F("Tabla cargada correctamente desde SD"));
        return true;
    } else {
        Serial.println(F("Error: Tabla no encontrada"));
        return false;
    }
}

// Modificar listCalibrationTables para usar SD
void listCalibrationTables() {
    if (!sdAvailable) {
        Serial.println(F("Error: SD no disponible"));
        return;
    }

    File tableFile = SD.open(TABLES_FILENAME, FILE_READ);
    if (!tableFile) {
        Serial.println(F("No hay tablas guardadas"));
        return;
    }

    Serial.println(F("\n=== TABLAS DE CALIBRACIÓN EN SD ==="));
    bool found = false;
    CalibrationTable table;

    while (tableFile.available() >= sizeof(CalibrationTable)) {
        tableFile.read((uint8_t*)&table, sizeof(CalibrationTable));
        
        if (table.header.active) {
            found = true;
            Serial.print(F("- "));
            Serial.println(table.header.name);
        }
    }

    tableFile.close();

    if (!found) {
        Serial.println(F("No hay tablas guardadas"));
    }
    Serial.println(F("========================"));
}

// Mostrar valores actuales
void showCurrentOffsets() {
    Serial.println(F("\n=== OFFSETS ACTUALES ==="));
    for (int i = 0; i < 7; i++) {
        Serial.print(F("Sensor "));
        Serial.print(i + 1);
        Serial.print(F(": Offset = "));
        Serial.print(sensorCalibrations[i].offset);
        Serial.print(F(", Slope = "));
        Serial.println(sensorCalibrations[i].slope);
    }
    Serial.println(F("========================"));
}

// AQUÍ TERMNAN LAS NUEVAS FUNCIONES


void resetToDefault(bool affectEEPROM) {
    // Reset valores en RAM
    for (int i = 0; i < 7; i++) {
        sensorCalibrations[i].offset = 0.0;
        sensorCalibrations[i].slope = 1.0;
    }
    isCalibrated = false;
    
    if (affectEEPROM) {
        // Crear tabla default con valores por defecto
        CalibrationTable defaultTable;
        strncpy(defaultTable.header.name, "default", TABLE_NAME_LENGTH);
        defaultTable.header.active = true;
        for (int i = 0; i < 7; i++) {
            defaultTable.calibrations[i].offset = 0.0;
            defaultTable.calibrations[i].slope = 1.0;
        }
        
        // Guardar en EEPROM
        EEPROM.put(TABLES_START_ADDRESS, defaultTable);
        activeTableIndex = 0;
    }
    
    Serial.println(F("Reset completado"));
    showTemporaryMessage(
        "Reset completado",
        affectEEPROM ? "Valores guardados" : "Reset temporal",
        affectEEPROM ? "en EEPROM" : "en RAM",
        NULL,
        2000
    );
}

void formatDataFile() {
    if (!sdAvailable) {
        Serial.println(F("Error: SD no disponible"));
        return;
    }
    
    Serial.println(F("¿Seguro que desea formatear el archivo de datos?"));
    Serial.println(F("Escriba 'confirmar' para proceder"));
    
    while (!Serial.available()) {
        delay(100);
    }
    
    String confirmation = Serial.readStringUntil('\n');
    confirmation.trim();
    
    if (confirmation == "confirmar") {
        if (SD.remove("datos.txt")) {
            createFilesIfNotExist();
            Serial.println(F("Archivo formateado correctamente"));
            showTemporaryMessage(
                "Archivo de datos",
                "formateado",
                "correctamente",
                NULL,
                2000
            );
        } else {
            Serial.println(F("Error al formatear archivo"));
        }
    } else {
        Serial.println(F("Operación cancelada"));
    }
}

// Función para establecer una tabla como default
bool setTableAsDefault(const char* name) {
    if (!sdAvailable) {
        Serial.println(F("Error: SD no disponible"));
        return false;
    }

    // Primero verificar si la tabla existe y cargarla
    File tableFile = SD.open(TABLES_FILENAME, FILE_READ);
    if (!tableFile) {
        Serial.println(F("Error: No se pudo abrir archivo de tablas"));
        return false;
    }

    CalibrationTable table;
    bool found = false;

    while (tableFile.available() >= sizeof(CalibrationTable)) {
        tableFile.read((uint8_t*)&table, sizeof(CalibrationTable));
        
        if (table.header.active && 
            strncmp(table.header.name, name, TABLE_NAME_LENGTH) == 0) {
            found = true;
            break;
        }
    }
    
    tableFile.close();

    if (!found) {
        Serial.println(F("Error: Tabla no encontrada"));
        return false;
    }

    // Guardar en EEPROM
    for (int i = 0; i < 7; i++) {
        EEPROM.put(EEPROM_CALIBRATION_START + (i * CALIBRATION_BYTES_PER_SENSOR), 
                   table.calibrations[i]);
    }
    
    // Cargar los valores en memoria
    memcpy(sensorCalibrations, table.calibrations, sizeof(sensorCalibrations));
    isCalibrated = true;

    Serial.println(F("Tabla establecida como default correctamente"));
    showTemporaryMessage(
        "Tabla establecida",
        "como configuracion",
        "por defecto",
        NULL,
        2000
    );
    return true;
}

// Función para hacer los valores actuales default
void makeCurrentValuesDefault() {
    // Guardar valores actuales en EEPROM
    for (int i = 0; i < 7; i++) {
        EEPROM.put(EEPROM_CALIBRATION_START + (i * CALIBRATION_BYTES_PER_SENSOR), 
                   sensorCalibrations[i]);
    }
    
    isCalibrated = true;
    Serial.println(F("Valores actuales establecidos como default"));
    showTemporaryMessage(
        "Valores actuales",
        "guardados como",
        "configuracion",
        "por defecto",
        2000
    );
}

// Función para guardar tabla en SD
bool saveCalibrationTable(const char* name) {
    if (!sdAvailable) {
        Serial.println(F("Error: SD no disponible"));
        return false;
    }

    if (strlen(name) == 0 || strlen(name) >= TABLE_NAME_LENGTH) {
        Serial.println(F("Error: Nombre de tabla inválido"));
        return false;
    }

    // Crear estructura para la nueva tabla
    CalibrationTable newTable;
    memset(&newTable, 0, sizeof(CalibrationTable));
    strncpy(newTable.header.name, name, TABLE_NAME_LENGTH - 1);
    newTable.header.active = true;
    memcpy(newTable.calibrations, sensorCalibrations, sizeof(sensorCalibrations));

    // Si el archivo no existe, crearlo
    if (!SD.exists(TABLES_FILENAME)) {
        File tableFile = SD.open(TABLES_FILENAME, FILE_WRITE);
        if (!tableFile) {
            Serial.println(F("Error: No se pudo crear archivo de tablas"));
            return false;
        }
        tableFile.close();
    }

    // Crear archivo temporal
    if (SD.exists(TABLES_BACKUP_FILENAME)) {
        SD.remove(TABLES_BACKUP_FILENAME);
    }
    
    File tableFile = SD.open(TABLES_FILENAME, FILE_READ);
    File tempFile = SD.open(TABLES_BACKUP_FILENAME, FILE_WRITE);
    
    if (!tableFile || !tempFile) {
        if (tableFile) tableFile.close();
        if (tempFile) tempFile.close();
        Serial.println(F("Error al abrir archivos"));
        return false;
    }

    // Copiar tablas existentes o reemplazar si encuentra el mismo nombre
    CalibrationTable existingTable;
    bool replaced = false;
    
    while (tableFile.available() >= sizeof(CalibrationTable)) {
        tableFile.read((uint8_t*)&existingTable, sizeof(CalibrationTable));
        
        if (existingTable.header.active && 
            strncmp(existingTable.header.name, name, TABLE_NAME_LENGTH) == 0) {
            tempFile.write((uint8_t*)&newTable, sizeof(CalibrationTable));
            replaced = true;
        } else if (existingTable.header.active) {
            tempFile.write((uint8_t*)&existingTable, sizeof(CalibrationTable));
        }
    }

    // Si no se reemplazó, agregar al final
    if (!replaced) {
        tempFile.write((uint8_t*)&newTable, sizeof(CalibrationTable));
    }

    tableFile.close();
    tempFile.close();

    // Reemplazar archivo original con el temporal
    SD.remove(TABLES_FILENAME);
    SD.rename(TABLES_BACKUP_FILENAME, TABLES_FILENAME);

    Serial.println(F("Tabla guardada correctamente en SD"));
    return true;
}

// Función para renombrar tabla
bool renameCalibrationTable(const char* oldName, const char* newName) {
    if (!sdAvailable) {
        Serial.println(F("Error: SD no disponible"));
        return false;
    }

    if (strlen(newName) == 0 || strlen(newName) >= TABLE_NAME_LENGTH) {
        Serial.println(F("Error: Nombre nuevo inválido"));
        return false;
    }

    File tableFile = SD.open(TABLES_FILENAME, FILE_READ);
    File tempFile = SD.open(TABLES_BACKUP_FILENAME, FILE_WRITE);

    if (!tableFile || !tempFile) {
        if (tableFile) tableFile.close();
        if (tempFile) tempFile.close();
        Serial.println(F("Error al abrir archivos"));
        return false;
    }

    CalibrationTable table;
    bool found = false;

    while (tableFile.available() >= sizeof(CalibrationTable)) {
        tableFile.read((uint8_t*)&table, sizeof(CalibrationTable));
        
        if (table.header.active && 
            strncmp(table.header.name, oldName, TABLE_NAME_LENGTH) == 0) {
            strncpy(table.header.name, newName, TABLE_NAME_LENGTH - 1);
            found = true;
        }
        tempFile.write((uint8_t*)&table, sizeof(CalibrationTable));
    }

    tableFile.close();
    tempFile.close();

    if (!found) {
        SD.remove(TABLES_BACKUP_FILENAME);
        return false;
    }

    SD.remove(TABLES_FILENAME);
    SD.rename(TABLES_BACKUP_FILENAME, TABLES_FILENAME);
    return true;
}

// Función para eliminar tabla
bool deleteCalibrationTable(const char* name) {
    if (!sdAvailable) {
        Serial.println(F("Error: SD no disponible"));
        return false;
    }

    File tableFile = SD.open(TABLES_FILENAME, FILE_READ);
    File tempFile = SD.open(TABLES_BACKUP_FILENAME, FILE_WRITE);

    if (!tableFile || !tempFile) {
        if (tableFile) tableFile.close();
        if (tempFile) tempFile.close();
        return false;
    }

    CalibrationTable table;
    bool found = false;

    while (tableFile.available() >= sizeof(CalibrationTable)) {
        tableFile.read((uint8_t*)&table, sizeof(CalibrationTable));
        
        if (table.header.active && 
            strncmp(table.header.name, name, TABLE_NAME_LENGTH) == 0) {
            found = true;
            continue; // Skip writing this table
        }
        tempFile.write((uint8_t*)&table, sizeof(CalibrationTable));
    }

    tableFile.close();
    tempFile.close();

    if (!found) {
        SD.remove(TABLES_BACKUP_FILENAME);
        return false;
    }

    SD.remove(TABLES_FILENAME);
    SD.rename(TABLES_BACKUP_FILENAME, TABLES_FILENAME);
    return true;
}

// Función para borrar todas las tablas de calibración
void deleteCalibrationTables() {
    if (!sdAvailable) {
        Serial.println(F("Error: SD no disponible"));
        return;
    }

    Serial.println(F("¿Seguro que desea borrar todas las tablas?"));
    Serial.println(F("Escriba 'BORRAR' para confirmar:"));
    
    while (!Serial.available()) {
        delay(100);
    }
    
    String confirmation = Serial.readStringUntil('\n');
    confirmation.trim();
    
    if (confirmation == "BORRAR") {
        if (SD.exists(TABLES_FILENAME)) {
            if (SD.remove(TABLES_FILENAME)) {
                Serial.println(F("Tablas de calibración borradas"));
                showTemporaryMessage(
                    "Tablas borradas",
                    "correctamente",
                    NULL,
                    NULL,
                    2000
                );
            } else {
                Serial.println(F("Error al borrar tablas"));
                showTemporaryMessage(
                    "Error al borrar",
                    "tablas",
                    NULL,
                    NULL,
                    2000
                );
            }
        } else {
            Serial.println(F("No hay tablas que borrar"));
            showTemporaryMessage(
                "No hay tablas",
                "que borrar",
                NULL,
                NULL,
                2000
            );
        }
    } else {
        Serial.println(F("Operación cancelada"));
    }
}

// ProcessSerialCommand
void processSerialCommand() {
    while (Serial.available()) {
        String command = Serial.readStringUntil('\n');
        command.trim();
        
        Serial.print(F("Comando recibido: "));
        Serial.println(command);

        // Comandos globales
        if (command == "menu" || command == "m") {
            currentMenu = MAIN_MENU;
            showMainMenu();
            return;
        }
        else if (command == "help") {
            showMainMenu();
            return;
        }
        else if (command == "back" || command == "b") {
            if (currentMenu != MAIN_MENU) {
                currentMenu = MAIN_MENU;
                showMainMenu();
            }
            return;
        }

        switch (currentMenu) {
            case MAIN_MENU:
                if (command == "cal") {
                    Serial.println(F("\n=== MODO CALIBRACIÓN ==="));
                    Serial.println(F("Seleccione la referencia:"));
                    Serial.println(F("1-7: Usar sensor S1-S7 como referencia"));
                    Serial.println(F("8: Usar sensor DHT11 como referencia"));
                    Serial.println(F("9: Usar sensor DHT22 como referencia"));
                    Serial.println(F("10: Ingresar valor manual de referencia"));
                    Serial.println(F("'cancel' para cancelar en cualquier momento"));
                    Serial.println(F("========================"));
                    
                    lcd.clear();
                    lcd.print(F("Modo Calibracion"));
                    lcd.setCursor(0, 1);
                    lcd.print(F("Seleccione ref:"));
                    lcd.setCursor(0, 2);
                    lcd.print(F("1-7:S 8-9:DHT11-DHT22 "));
                    lcd.setCursor(0, 3);
                    lcd.print(F("10:M"));
                    
                    calibrationMode = true;
                    calibrationSetupComplete = false;
                    calConfig.refType = REF_NONE;
                    calConfig.refSensor = -1;
                    calConfig.refValue = 0.0;
                    calConfig.duration = 60000;
                    lastCalibrationActivity = millis();
                    
                    currentMenu = CALIBRATION_MENU;
                }
                else if (command == "reset") {
                    showResetMenu();
                    currentMenu = RESET_MENU;
                }
                else if (command == "offset") {
                    showOffsetMenu();
                    currentMenu = OFFSET_MENU;
                }
                else if (command == "table") {
                    showTableManagementMenu();
                    currentMenu = TABLE_MENU;
                }
                else if (command == "sd") {
                    showSDMenu();
                    currentMenu = SD_MENU;
                }
                else if (command == "show") {
                    showCurrentOffsets();
                }
                break;

            case CALIBRATION_MENU:
                if (command == "cancel") {
                    calibrationMode = false;
                    currentMenu = MAIN_MENU;
                    showMainMenu();
                    
                    lcd.clear();
                    lcd.print(F("Calibracion"));
                    lcd.setCursor(0, 1);
                    lcd.print(F("Cancelada"));
                    delay(2000);
                }
                else {
                    processCalibrationInput(command);
                }
                break;

            case RESET_MENU:
                if (command == "1") {
                    resetToDefault(false);  // Solo RAM
                    currentMenu = MAIN_MENU;
                    showMainMenu();
                }
                else if (command == "2") {
                    resetToDefault(true);   // RAM + EEPROM
                    currentMenu = MAIN_MENU;
                    showMainMenu();
                }
                else if (command == "3") {
                    // Reset tabla actual
                    if (activeTableIndex >= 0) {
                        CalibrationTable table;
                        EEPROM.get(TABLES_START_ADDRESS + (activeTableIndex * TOTAL_TABLE_SIZE), table);
                        for (int i = 0; i < 7; i++) {
                            table.calibrations[i].offset = 0.0;
                            table.calibrations[i].slope = 1.0;
                        }
                        EEPROM.put(TABLES_START_ADDRESS + (activeTableIndex * TOTAL_TABLE_SIZE), table);
                        memcpy(sensorCalibrations, table.calibrations, sizeof(sensorCalibrations));
                        Serial.println(F("Tabla actual reseteada"));
                    } else {
                        Serial.println(F("No hay tabla activa"));
                    }
                    currentMenu = MAIN_MENU;
                    showMainMenu();
                }
                else if (command == "4") {
                    // Reset completo
                    for (int i = 0; i < MAX_CALIBRATION_TABLES; i++) {
                        CalibrationTable emptyTable;
                        emptyTable.header.active = false;
                        EEPROM.put(TABLES_START_ADDRESS + (i * TOTAL_TABLE_SIZE), emptyTable);
                    }
                    resetToDefault(true);
                    Serial.println(F("Reset completo realizado"));
                    currentMenu = MAIN_MENU;
                    showMainMenu();
                }
                break;

            case OFFSET_MENU:
                if (command.startsWith("offset ")) {
                    String parts[3];
                    int partIndex = 0;
                    int lastSpace = 0;
                    
                    for (int i = 0; i < command.length(); i++) {
                        if (command.charAt(i) == ' ' || i == command.length() - 1) {
                            parts[partIndex] = command.substring(lastSpace, i == command.length() - 1 ? i + 1 : i);
                            parts[partIndex].trim();
                            lastSpace = i + 1;
                            partIndex++;
                            if (partIndex >= 3) break;
                        }
                    }
                    
                    if (partIndex == 3) {
                        int sensor = parts[1].toInt() - 1;
                        float offsetValue = parts[2].toFloat();
                        
                        if (sensor >= 0 && sensor < 7 && offsetValue >= -50.0 && offsetValue <= 50.0) {
                            sensorCalibrations[sensor].offset = offsetValue;
                            
                            char lcdMessage[21];
                            sprintf(lcdMessage, "S%d: %+.1f", sensor + 1, offsetValue);
                            
                            showTemporaryMessage(
                                "Offset ajustado",
                                lcdMessage,
                                "Correctamente",
                                NULL,
                                2000
                            );
                            
                            Serial.print(F("Offset del sensor "));
                            Serial.print(sensor + 1);
                            Serial.print(F(" ajustado a "));
                            Serial.println(offsetValue);
                        } else {
                            Serial.println(F("Error: Valor fuera de rango"));
                            Serial.println(F("Sensor: 1-7"));
                            Serial.println(F("Offset: -50.0 a 50.0"));
                            
                            showTemporaryMessage(
                                "Error:",
                                "Valor fuera",
                                "de rango",
                                NULL,
                                2000
                            );
                        }
                    }
                }
                else if (command == "show") {
                    showCurrentOffsets();
                }
                break;

            case TABLE_MENU:
                if (command.startsWith("save ")) {
                    String tableName = command.substring(5);
                    tableName.trim();
                    
                    if (saveCalibrationTable(tableName.c_str())) {
                        Serial.println(F("Tabla guardada correctamente"));
                        showTemporaryMessage(
                            "Tabla guardada",
                            tableName.c_str(),
                            "correctamente",
                            NULL,
                            2000
                        );
                    } else {
                        Serial.println(F("Error al guardar tabla"));
                    }
                }
                else if (command.startsWith("load ")) {
                    String tableName = command.substring(5);
                    tableName.trim();
                    
                    if (loadCalibrationTable(tableName.c_str())) {
                        Serial.println(F("Tabla cargada correctamente"));
                        showTemporaryMessage(
                            "Tabla cargada",
                            tableName.c_str(),
                            "correctamente",
                            NULL,
                            2000
                        );
                    } else {
                        Serial.println(F("Error: Tabla no encontrada"));
                    }
                }
                else if (command.startsWith("setdefault ")) {
                    String tableName = command.substring(11);
                    tableName.trim();
                    setTableAsDefault(tableName.c_str());
                }
                else if (command == "makedefault") {
                    makeCurrentValuesDefault();
                }
                else if (command.startsWith("rename ")) {
                    String params = command.substring(7);
                    int spacePos = params.indexOf(' ');
                    if (spacePos > 0) {
                        String oldName = params.substring(0, spacePos);
                        String newName = params.substring(spacePos + 1);
                        oldName.trim();
                        newName.trim();
                        
                        if (renameCalibrationTable(oldName.c_str(), newName.c_str())) {
                            Serial.println(F("Tabla renombrada correctamente"));
                        } else {
                            Serial.println(F("Error al renombrar tabla"));
                        }
                    }
                }
                else if (command.startsWith("delete ")) {
                    String tableName = command.substring(7);
                    tableName.trim();
                    
                    if (deleteCalibrationTable(tableName.c_str())) {
                        Serial.println(F("Tabla eliminada correctamente"));
                    } else {
                        Serial.println(F("Error: Tabla no encontrada"));
                    }
                }
                else if (command == "list") {
                    listCalibrationTables();
                }
                break;

            case SD_MENU:
                if (command == "1") {
                    formatDataFile();
                    currentMenu = MAIN_MENU;
                    showMainMenu();
                }
                else if (command == "2") {
                    deleteCalibrationTables();
                    currentMenu = MAIN_MENU;
                    showMainMenu();
                }
                else if (command == "3") {
                    formatSD();
                    currentMenu = MAIN_MENU;
                    showMainMenu();
                }
                else if (command == "4") {
                    if (sdAvailable) {
                        Serial.println(F("SD Card: Conectada y funcionando"));
                        FsFile root = SD.open("/");
                        if (root) {
                            Serial.println(F("\nArchivos en SD:"));
                            printDirectory(root, 0);
                            root.close();
                        }
                    } else {
                        Serial.println(F("SD Card: No disponible"));
                    }
                    currentMenu = MAIN_MENU;
                    showMainMenu();
                }
                break;
        }
    }
}

// loop()
void loop() {
    DateTime now = rtc.now();
    
    if (calibrationMode) {
        if (Serial.available() > 0) {
            String input = Serial.readStringUntil('\n');
            input.trim();
            Serial.print(F("Entrada recibida: "));
            Serial.println(input);
            processCalibrationInput(input);
        }
        
        // Verificar timeout
        if (millis() - lastCalibrationActivity > CALIBRATION_TIMEOUT) {
            Serial.println(F("Timeout de calibración"));
            calibrationMode = false;
            return;
        }

        if (calibrationSetupComplete) {
            handleCalibration();
        }
    } else {
        if (Serial.available() > 0) {
            processSerialCommand();
        }
        
        if (millis() - lastDisplayUpdate >= DISPLAY_UPDATE_INTERVAL) {
            lastDisplayUpdate = millis();
            checkSensors();
            updateMainDisplay(now);
            logData(now);
            checkSD();
        }
    }
}
