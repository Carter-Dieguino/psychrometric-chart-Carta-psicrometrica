import math
import tkinter as tk
from tkinter import filedialog, messagebox
import pandas as pd
from tkinter import ttk
import numpy as np
import matplotlib.pyplot as plt
from scipy.interpolate import griddata
import openpyxl
import tkinter.simpledialog as simpledialog  # Para cuadros de diálogo
from datetime import datetime

import math
import numpy as np

class CalculadoraPropiedades:
    def __init__(self):
        self.Ra = 287.055
        
    def Grados_Kelvin(self, temp):
        return temp + 273.15
    
    def calcular_presion(self, altura):
        p_atm = 101.325 * (math.pow((1 - 2.25577e-5 * altura), 5.2559))
        return p_atm * 1000  
    
    def calcular_pvs(self, Tbs):
        if Tbs < -100:
            Tbs = -100
        elif Tbs > 200:
            Tbs = 200

        Tbs_K = self.Grados_Kelvin(Tbs)

        if Tbs <= 0:  
            C1 = -5.6745359e3
            C2 = 6.3925247e0
            C3 = -9.6778430e-3
            C4 = 6.2215701e-7
            C5 = 2.0747825e-9
            C6 = -9.4840240e-13
            C7 = 4.1635019e0
            ln_pws = (C1 / Tbs_K) + C2 + C3 * Tbs_K + C4 * Tbs_K ** 2 + C5 * Tbs_K ** 3 + C6 * Tbs_K ** 4 + C7 * math.log(Tbs_K)

        elif 0 < Tbs <= 200:
            C8 = -5.8002206e3
            C9 = 1.3914993e0
            C10 = -4.8640239e-2
            C11 = 4.1764768e-5
            C12 = -1.4452093e-8
            C13 = 6.5459673e0
            ln_pws = (C8 / Tbs_K) + C9 + C10 * Tbs_K + C11 * Tbs_K ** 2 + C12 * Tbs_K ** 3 + C13 * math.log(Tbs_K)

        return math.exp(ln_pws)

    def calcular_pv(self, Hr, pvs2):
        return Hr * pvs2

    def razon_humedad(self, Pv, presionAt):
        return 0.622 * (Pv / (presionAt - Pv))

    def razon_humedad_saturada(self, pvs2, presionAt):
        return 0.622 * (pvs2 / (presionAt - pvs2))

    def grado_saturacion(self, W, Ws):
        return (W / Ws) * 100

    def volumen_especifico(self, Tbs, presionAt, W):
        Tbs_K = self.Grados_Kelvin(Tbs)
        return ((self.Ra * Tbs_K) / presionAt) * (1 + 1.6078 * W) / (1 + W)

    def temperatura_punto_rocio(self, Tbs, Pv):
        if Pv <= 0:
            Pv = 0.00001  
        if -60 < Tbs < 0:
            return -60.450 + 7.0322 * math.log(Pv) + 0.3700 * (math.log(Pv)) ** 2
        elif 0 < Tbs < 70:
            return -35.957 - 1.8726 * math.log(Pv) + 1.1689 * (math.log(Pv)) ** 2
        return None

    def entalpia(self, Tbs, W):
        return 1.006 * Tbs + W * (2501 + 1.805 * Tbs)

    def bulbo_humedo(self, presionAt, Tbs, W, iter=20):
        Tpr = Tbs - 1
        x0 = np.array(Tpr)
        tolerancia = 0.00001

        for i in range(iter):
            X = x0 + 273.15
            pvs2 = self.calcular_pvs(X - 273.15)

            if pvs2 <= 0:
                pvs2 = 0.00001  
            
            Ws_2 = 0.62198 * (pvs2 / (presionAt - pvs2))
            fx_tbh = (((2501 - 2.381 * x0) * Ws_2 - 1.006 * (Tbs - x0)) / (2501 + 1.805 * Tbs - 4.186 * x0)) - W

            fx_tbh_d = (((2501 - 2.381 * x0) * Ws_2 + Ws_2 * (-2.381) + 1.006) / (2501 + 1.805 * Tbs - 4.186 * x0))

            Tbh = x0 - (fx_tbh / fx_tbh_d)

            if x0 == 0:
                x0 = 1e-14
                
            error = (Tbh - x0) / x0

            x0 = Tbh

            if np.all(np.abs(error) < tolerancia):
                break
        return Tbh

    def calcular_humedad_relativa_desde_bulbo_humedo(self, Tbs, Tbh, presionAt):
        pWBT = self.calcular_pvs(Tbh)
        pSeca = self.calcular_pvs(Tbs)
        pHR = pWBT - presionAt * 0.000662 * (Tbs - Tbh)
        if Tbs >= Tbh and pHR <= pSeca and pHR > 0:
            Hr = pHR / pSeca
            return Hr
        else:
            raise ValueError("Error en los valores ingresados. Verifica que Tbs >= Tbh y que las temperaturas estén en rangos razonables.")

class ManejoDatos:
    def cargar_archivo(self, ruta_archivo):
        try:
            extension = ruta_archivo.split('.')[-1].lower()

            if extension in ['xlsx', 'xls']:
                try:
                    df_cleaned = pd.read_excel(ruta_archivo, sheet_name=None)
                except Exception as e:
                    raise ValueError(f"Error al leer archivo Excel: {e}. Intentando cargar como CSV...")

            elif extension == 'csv':
                df_cleaned = pd.read_csv(ruta_archivo)
            elif extension == 'txt':
                df_cleaned = pd.read_csv(ruta_archivo, delimiter='\t')
            else:
                raise ValueError(f"Formato no soportado: {extension}")

            return df_cleaned

        except Exception as e:
            raise ValueError(f"Ocurrió un error al procesar el archivo: {e}")

    def procesar_datos(self, df_cleaned):
        try:
            if isinstance(df_cleaned, dict):
                if 'Hoja1' in df_cleaned:
                    df_cleaned = df_cleaned['Hoja1']
                elif 'Sheet1' in df_cleaned:
                    df_cleaned = df_cleaned['Sheet1']
                else:
                    raise ValueError("No se encontró 'Hoja1' ni 'Sheet1'. Intentando con la primera hoja disponible.")
                    df_cleaned = next(iter(df_cleaned.values()))

            df_cleaned.columns = [
                'Fecha Local', 'Fecha UTC', 'Dirección del Viento', 'Dirección de ráfaga (grados)',
                'Rapidez de viento (km/h)', 'Rapidez de ráfaga (km/h)', 'Temperatura', 'Humedad',
                'Presión Atmosférica (hpa)', 'Precipitación (mm)', 'Radiación Solar (W/m²)'
            ]
            
            df_cleaned.drop(columns=['Fecha Local'], inplace=True)

            return df_cleaned

        except Exception as e:
            raise ValueError(f"Error al procesar los datos: {e}")

    def cargar_excel(self, ruta_excel):
        try:
            excel_file = pd.ExcelFile(ruta_excel)
            sheet_name = None

            if 'Hoja1' in excel_file.sheet_names:
                sheet_name = 'Hoja1'
            elif 'Sheet1' in excel_file.sheet_names:
                sheet_name = 'Sheet1'
            else:
                sheet_name = excel_file.sheet_names[0]

            df_cleaned = pd.read_excel(ruta_excel, sheet_name=sheet_name, header=8, usecols="B:L")

            df_cleaned.columns = [
                'Fecha Local', 'Fecha UTC', 'Dirección del Viento', 'Dirección de ráfaga (grados)',
                'Rapidez de viento (km/h)', 'Rapidez de ráfaga (km/h)', 'Temperatura', 'Humedad',
                'Presión Atmosférica (hpa)', 'Precipitación (mm)', 'Radiación Solar (W/m²)'
            ]
            
            df_cleaned.drop(columns=['Fecha Local'], inplace=True)

            # Leer la altura desde la columna 11 (columna "L"), fila 6 (índice 5)
            df_initial = pd.read_excel(ruta_excel, sheet_name=sheet_name, header=None, usecols=[11])
            altura = df_initial.iloc[6, 0]  # Fila 6 (índice 5)

            if pd.isna(altura):
                altura = simpledialog.askfloat("Entrada", "Introduce la altura en metros:", parent=None)
                if altura is None:
                    raise ValueError("Se requiere la altura para continuar.")
            df_cleaned['Altura'] = altura

            df_cleaned['Fecha UTC'] = pd.to_datetime(df_cleaned['Fecha UTC'], format='%Y-%m-%d %H:%M:%S', errors='coerce')
            df_cleaned.set_index('Fecha UTC', inplace=True)

            # Convertir columnas a numéricas y manejar errores
            numeric_columns = ['Temperatura', 'Humedad', 'Altura', 'Dirección del Viento', 'Dirección de ráfaga (grados)',
                               'Rapidez de viento (km/h)', 'Rapidez de ráfaga (km/h)', 'Presión Atmosférica (hpa)',
                               'Precipitación (mm)', 'Radiación Solar (W/m²)']
            df_cleaned[numeric_columns] = df_cleaned[numeric_columns].apply(pd.to_numeric, errors='coerce')

            df_cleaned['Humedad'] = df_cleaned['Humedad'] / 100

            # Eliminar filas con valores NaN en 'Temperatura', 'Humedad' y 'Altura'
            df_cleaned.dropna(subset=['Temperatura', 'Humedad', 'Altura'], inplace=True)

            # Resampleo diario para el climograma
            df_daily_avg = df_cleaned.resample('D').mean()

            df_hourly_avg = df_cleaned.resample('h').mean()
            df_interpolated = df_hourly_avg.interpolate(method='linear')
            df_interpolated_reset = df_interpolated.reset_index()

            column_order = [
                'Fecha UTC', 'Altura', 'Temperatura', 'Humedad',
                'Dirección del Viento', 'Dirección de ráfaga (grados)', 'Rapidez de viento (km/h)',
                'Rapidez de ráfaga (km/h)', 'Presión Atmosférica (hpa)', 'Precipitación (mm)', 'Radiación Solar (W/m²)'
            ]
            df_interpolated_reset = df_interpolated_reset[column_order]

            # Calcula las propiedades psicrométricas para cada fila
            resultados = df_interpolated_reset.apply(self.calcular_propiedades_fila, axis=1)
            df_final = pd.concat([df_interpolated_reset.reset_index(drop=True), resultados], axis=1)

            # Guardar df_daily_avg para el climograma
            self.df_daily_avg = df_daily_avg.reset_index()

            return df_final

        except Exception as e:
            raise ValueError(f"Ocurrió un error al leer el archivo: {e}")

    def calcular_propiedades_fila(self, row):
        calculadora = CalculadoraPropiedades()
        try:
            Tbs = row['Temperatura']
            Hr = row['Humedad']
            altura = row['Altura']

            if pd.isnull(Tbs) or pd.isnull(Hr) or pd.isnull(altura):
                return pd.Series({
                    'Tbh (°C)': None,
                    'φ (%)': None,
                    'Tpr (°C)': None,
                    'Pvs (kPa)': None,
                    'Pv (kPa)': None,
                    'Ws (kg_vp/kg_AS)': None,
                    'W (kg_vp/kg_AS)': None,
                    'μ [G_sat]': None,
                    'Veh (m³/kg_AS)': None,
                    'h (kJ/kg_AS)': None
                })

            if Hr <= 0:
                Hr = 0.00001
            if altura < 0:
                raise ValueError(f"Error: La altura {altura} no es válida. Solo se permiten valores positivos.")

            presionAt = calculadora.calcular_presion(altura)
            pvs2 = calculadora.calcular_pvs(Tbs)
            Pv = calculadora.calcular_pv(Hr, pvs2)
            W = calculadora.razon_humedad(Pv, presionAt)
            Ws = calculadora.razon_humedad_saturada(pvs2, presionAt)
            Gsaturacion = calculadora.grado_saturacion(W, Ws)
            Veh = calculadora.volumen_especifico(Tbs, presionAt, W)
            Tpr = calculadora.temperatura_punto_rocio(Tbs, Pv)
            h = calculadora.entalpia(Tbs, W)
            Tbh = calculadora.bulbo_humedo(presionAt, Tbs, W)
            return pd.Series({
                'Tbh (°C)': Tbh,
                'φ (%)': Hr * 100,
                'Tpr (°C)': Tpr,
                'Pvs (kPa)': pvs2 / 1000,
                'Pv (kPa)': Pv / 1000,
                'Ws (kg_vp/kg_AS)': Ws,
                'W (kg_vp/kg_AS)': W,
                'μ [G_sat]': Gsaturacion,
                'Veh (m³/kg_AS)': Veh,
                'h (kJ/kg_AS)': h
            })
        except Exception as e:
            return pd.Series({
                'Tbh (°C)': None,
                'φ (%)': None,
                'Tpr (°C)': None,
                'Pvs (kPa)': None,
                'Pv (kPa)': None,
                'Ws (kg_vp/kg_AS)': None,
                'W (kg_vp/kg_AS)': None,
                'μ [G_sat]': None,
                'Veh (m³/kg_AS)': None,
                'h (kJ/kg_AS)': None
            })

    def guardar_excel(self, tabla, ruta_guardado):
        datos_guardar = []
        for item in tabla.get_children():
            datos_fila = tabla.item(item)['values']
            datos_guardar.append(datos_fila)

        columnas = ["#", "Fecha", "Hora", "Altura (m)", "Tbs (°C)", "Tbh (°C)", "φ (%)", "Tpr (°C)", 
                    "Pvs (kPa)", "Pv (kPa)", "Ws (kg_vp/kg_AS)", "W (kg_vp/kg_AS)", 
                    "μ [G_sat]", "Veh (m³/kg_AS)", "h (kJ/kg_AS)"]
        df = pd.DataFrame(datos_guardar, columns=columnas)
        df.to_excel(ruta_guardado, index=False)

class InterfazGrafica:
    def __init__(self, calculadora, manejo_datos):
        self.calculadora = calculadora
        self.manejo_datos = manejo_datos
        self.ruta_excel = ''
        self.datos_excel = None
        self.datos_promedio = None
        self.root = None
        self.df_daily_avg = None  # Para el climograma

    def iniciar_interfaz(self):
        self.root = tk.Tk()
        self.root.title("Calculadora de Propiedades")
        self.root.geometry("1400x700")

        # Estilos
        style = ttk.Style(self.root)
        style.theme_use('clam')
        style.configure('TButton', font=('Arial', 10))
        style.configure('Treeview.Heading', font=('Arial', 10, 'bold'))

        self.crear_botones()
        self.crear_tabla()
        self.root.mainloop()

    def crear_botones(self):
        frame_botones = ttk.Frame(self.root)
        frame_botones.pack(fill='x', padx=10, pady=10)

        boton_cargar = ttk.Button(frame_botones, text="Cargar Excel", command=self.cargar_excel)
        boton_cargar.pack(side='left', padx=5)

        boton_datos_registrados = ttk.Button(frame_botones, text="Datos Registrados", command=self.cargar_datos_registrados)
        boton_datos_registrados.pack(side='left', padx=5)

        boton_guardar = ttk.Button(frame_botones, text="Guardar Excel", command=self.guardar_excel)
        boton_guardar.pack(side='left', padx=5)

        boton_psicrometrica = ttk.Button(frame_botones, text="Graficar Psicrométrica", command=self.graficar_psicrometrica)
        boton_psicrometrica.pack(side='left', padx=5)

        boton_climograma = ttk.Button(frame_botones, text="Graficar Climograma", command=self.graficar_climograma)
        boton_climograma.pack(side='left', padx=5)

        boton_calcular_bulbo_humedo = ttk.Button(frame_botones, text="Calcular desde Bulbo Húmedo", command=self.calcular_desde_bulbo_humedo)
        boton_calcular_bulbo_humedo.pack(side='left', padx=5)

        boton_calcular_humedad_relativa = ttk.Button(frame_botones, text="Calcular desde Humedad Relativa", command=self.calcular_desde_humedad_relativa)
        boton_calcular_humedad_relativa.pack(side='left', padx=5)

    def crear_tabla(self):
        columnas = ("#", "Fecha", "Hora", "Altura (m)", "Tbs (°C)", "Tbh (°C)", "φ (%)", "Tpr (°C)", 
                    "Pvs (kPa)", "Pv (kPa)", "Ws (kg_vp/kg_AS)", "W (kg_vp/kg_AS)", "μ [G_sat]", "Veh (m³/kg_AS)", "h (kJ/kg_AS)")
        self.tabla = ttk.Treeview(self.root, columns=columnas, show='headings')
        for col in columnas:
            self.tabla.heading(col, text=col)
            self.tabla.column(col, anchor='center')

        # Añadir barras de desplazamiento
        frame_tabla = ttk.Frame(self.root)
        frame_tabla.pack(fill='both', expand=True)

        scrollbar_vertical = ttk.Scrollbar(frame_tabla, orient="vertical", command=self.tabla.yview)
        scrollbar_vertical.pack(side='right', fill='y')

        scrollbar_horizontal = ttk.Scrollbar(frame_tabla, orient="horizontal", command=self.tabla.xview)
        scrollbar_horizontal.pack(side='bottom', fill='x')

        self.tabla.configure(yscrollcommand=scrollbar_vertical.set, xscrollcommand=scrollbar_horizontal.set)
        self.tabla.pack(fill='both', expand=True)

    def cargar_excel(self):
        try:
            self.datos_excel = None  # Resetear variables
            self.datos_promedio = None
            self.df_daily_avg = None
            self.ruta_excel = filedialog.askopenfilename(title="Seleccionar archivo Excel", filetypes=[("Archivos Excel", "*.xlsx *.xls")], parent=self.root)
            if self.ruta_excel:
                self.datos_excel = self.manejo_datos.cargar_excel(self.ruta_excel)
                if self.datos_excel is not None and not self.datos_excel.empty:
                    # Limpiar la tabla antes de cargar nuevos datos
                    for row in self.tabla.get_children():
                        self.tabla.delete(row)

                    # Agregar los datos a la tabla
                    for idx, row in self.datos_excel.iterrows():
                        idx_tabla = len(self.tabla.get_children()) + 1
                        fecha = row['Fecha UTC'].strftime('%Y-%m-%d')
                        hora = row['Fecha UTC'].strftime('%H:%M:%S')
                        valores = [idx_tabla, fecha, hora, row['Altura'], row['Temperatura'], row['Tbh (°C)'], row['φ (%)'], row['Tpr (°C)'],
                                   row['Pvs (kPa)'], row['Pv (kPa)'], row['Ws (kg_vp/kg_AS)'], row['W (kg_vp/kg_AS)'],
                                   row['μ [G_sat]'], row['Veh (m³/kg_AS)'], row['h (kJ/kg_AS)']]
                        self.tabla.insert("", "end", values=valores)

                    # Guardar df_daily_avg para el climograma
                    self.df_daily_avg = self.manejo_datos.df_daily_avg
                else:
                    messagebox.showwarning("Advertencia", "El archivo no pudo ser cargado o está vacío.")
            else:
                messagebox.showwarning("Advertencia", "No se seleccionó ningún archivo.")
        except Exception as e:
            messagebox.showerror("Error", f"Ocurrió un error al leer el archivo: {e}")

    def cargar_datos_registrados(self):
        try:
            self.datos_excel = None  # Resetear variables
            self.datos_promedio = None
            self.df_daily_avg = None
            ruta_archivo = filedialog.askopenfilename(title="Seleccionar archivo Excel", filetypes=[("Archivos Excel", "*.xlsx *.xls")], parent=self.root)
            if ruta_archivo:
                self.datos_promedio = self.calcular_promedio_intervalo_10_minutos(ruta_archivo)
                if self.datos_promedio is not None and not self.datos_promedio.empty:
                    # Calcular las propiedades psicrométricas
                    resultados = self.datos_promedio.apply(lambda row: self.calcular_resultados_fila_desde_Tbs_Tbh(row), axis=1)

                    for row in self.tabla.get_children():
                        self.tabla.delete(row)

                    for idx, resultado in enumerate(resultados.values, start=1):
                        self.tabla.insert("", "end", values=[idx] + list(resultado))

                    # Resampleo diario para el climograma
                    self.df_daily_avg = self.datos_promedio.copy()
                    self.df_daily_avg['Fecha'] = pd.to_datetime(self.df_daily_avg['Fecha'])
                    self.df_daily_avg.set_index('Fecha', inplace=True)
                    self.df_daily_avg = self.df_daily_avg.resample('D').mean().reset_index()
                else:
                    messagebox.showwarning("Advertencia", "El archivo no pudo ser cargado o está vacío.")
            else:
                messagebox.showwarning("Advertencia", "No se seleccionó ningún archivo.")
        except Exception as e:
            messagebox.showerror("Error", f"Ocurrió un error al procesar los datos registrados: {e}")

    def calcular_promedio_intervalo_10_minutos(self, ruta_archivo):
        try:
            # Cargar el archivo y seleccionar la hoja
            df = pd.read_excel(ruta_archivo, sheet_name="Hoja1")

            # Crear una columna de fecha y hora combinada para usar como índice
            df['Fecha_Hora'] = pd.to_datetime(df['Fecha'].astype(str) + ' ' + df['Hora'].astype(str))

            # Establecer 'Fecha_Hora' como índice
            df.set_index('Fecha_Hora', inplace=True)

            # Intentar obtener la altura desde la columna 6 (columna "G"), fila 1 (índice 0)
            try:
                altura_df = pd.read_excel(ruta_archivo, sheet_name="Hoja1", header=None, usecols=[6])
                altura = altura_df.iloc[1, 0]
                if pd.isna(altura):
                    raise ValueError
            except:
                altura = simpledialog.askfloat("Entrada", "Introduce la altura en metros:", parent=self.root)
                if altura is None:
                    raise ValueError("Se requiere la altura para continuar.")
            df['Altura (m)'] = altura

            # Convertir columnas a numéricas
            df['Tbs'] = pd.to_numeric(df['Tbs'], errors='coerce')
            df['Tbh'] = pd.to_numeric(df['Tbh'], errors='coerce')

            # Eliminar filas con valores NaN en 'Tbs' y 'Tbh'
            df.dropna(subset=['Tbs', 'Tbh'], inplace=True)

            if df.empty:
                raise ValueError("Los datos de temperatura están vacíos o no son válidos.")

            # Generar una lista para almacenar los resultados
            promedios = []

            # Crear el primer intervalo desde el primer registro redondeado al múltiplo de 10 minutos más cercano hacia abajo
            inicio = (df.index.min().replace(second=0, microsecond=0) - pd.Timedelta(minutes=df.index.min().minute % 10)).replace(second=0)
            fin = df.index.max()

            while inicio < fin:
                # Definir el final del intervalo como exactamente 10 minutos después
                fin_intervalo = inicio + pd.Timedelta(minutes=9, seconds=59)

                # Filtrar datos dentro de este intervalo
                datos_intervalo = df.loc[inicio:fin_intervalo]

                if not datos_intervalo.empty:
                    # Calcular el promedio de Tbs y Tbh para el intervalo actual
                    promedio_Tbs = datos_intervalo['Tbs'].mean()
                    promedio_Tbh = datos_intervalo['Tbh'].mean()
                    altura = datos_intervalo['Altura (m)'].mean()

                    # Guardar la fecha y hora inicial
                    fecha = inicio.date()
                    hora = inicio.time()

                    # Añadir el resultado al DataFrame
                    promedios.append({'Fecha': fecha, 'Hora': hora, 'Altura (m)': altura, 'Tbs (°C)': promedio_Tbs, 'Tbh (°C)': promedio_Tbh})

                # Avanzar al siguiente intervalo de 10 minutos
                inicio = inicio + pd.Timedelta(minutes=10)

            # Convertir los resultados en un DataFrame
            df_promedio = pd.DataFrame(promedios)

            if df_promedio.empty:
                raise ValueError("No se pudieron calcular promedios en los intervalos.")

            # Convertir columnas a numéricas
            df_promedio['Tbs (°C)'] = pd.to_numeric(df_promedio['Tbs (°C)'], errors='coerce')
            df_promedio['Tbh (°C)'] = pd.to_numeric(df_promedio['Tbh (°C)'], errors='coerce')
            df_promedio['Altura (m)'] = pd.to_numeric(df_promedio['Altura (m)'], errors='coerce')

            # Eliminar filas con valores NaN después de la conversión
            df_promedio.dropna(subset=['Tbs (°C)', 'Tbh (°C)', 'Altura (m)'], inplace=True)

            return df_promedio

        except Exception as e:
            raise ValueError(f"Ocurrió un error al calcular los promedios: {e}")

    def calcular_resultados_fila_desde_Tbs_Tbh(self, row):
        try:
            Tbs = row['Tbs (°C)']
            Tbh = row['Tbh (°C)']
            altura = row['Altura (m)']

            if pd.isnull(Tbs) or pd.isnull(Tbh) or pd.isnull(altura):
                return [row['Fecha'], row['Hora'], altura, Tbs, Tbh] + [None]*9

            if altura < 0:
                raise ValueError("La altura no puede ser negativa.")
            if Tbs < Tbh:
                raise ValueError("La temperatura de bulbo seco debe ser mayor o igual a la de bulbo húmedo.")

            presionAt = self.calculadora.calcular_presion(altura)

            # Calcular la humedad relativa desde el bulbo húmedo
            Hr = self.calculadora.calcular_humedad_relativa_desde_bulbo_humedo(Tbs, Tbh, presionAt)
            
            # Verificar límites
            if Hr <= 0 or Hr > 1:
                raise ValueError("La humedad relativa calculada está fuera de los límites (0 < Hr ≤ 1).")

            pvs2 = self.calculadora.calcular_pvs(Tbs)
            Pv = self.calculadora.calcular_pv(Hr, pvs2)
            W = self.calculadora.razon_humedad(Pv, presionAt)
            Ws = self.calculadora.razon_humedad_saturada(pvs2, presionAt)
            Gsaturacion = self.calculadora.grado_saturacion(W, Ws)
            Veh = self.calculadora.volumen_especifico(Tbs, presionAt, W)
            Tpr = self.calculadora.temperatura_punto_rocio(Tbs, Pv)
            h = self.calculadora.entalpia(Tbs, W)

            return [row['Fecha'], row['Hora'], altura, Tbs, Tbh, Hr * 100, Tpr, pvs2/1000, Pv/1000, Ws, W, Gsaturacion, Veh, h]
        except Exception as e:
            return [row['Fecha'], row['Hora'], altura, Tbs, Tbh] + [None]*9

    def guardar_excel(self):
        try:
            ruta_guardado = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel Files", "*.xlsx")], parent=self.root)
            if ruta_guardado:
                self.manejo_datos.guardar_excel(self.tabla, ruta_guardado)
                messagebox.showinfo("Éxito", f"Los datos se han guardado correctamente en '{ruta_guardado}'.")
            else:
                messagebox.showwarning("Advertencia", "No se ha seleccionado una ubicación para guardar el archivo.")
        except Exception as e:
            messagebox.showerror("Error", f"Ocurrió un error al guardar el archivo: {e}")

    def graficar_psicrometrica(self):
        try:
            Tbs = np.linspace(0, 60, 100)
            Hr = np.linspace(0.1, 1.0, 10)
            altura = 0

            Tbs_grid, Hr_grid = np.meshgrid(Tbs, Hr)
            presionAt = self.calculadora.calcular_presion(altura)
            pvs2_grid = np.vectorize(self.calculadora.calcular_pvs)(Tbs_grid)
            Pv_grid = Hr_grid * pvs2_grid
            W_grid = 0.622 * (Pv_grid / (presionAt - Pv_grid))

            plt.figure(figsize=(10, 8))

            for i in range(len(Hr)):
                plt.plot(Tbs, W_grid[i, :], label=f'Hr {Hr[i]*100:.0f}%')

            # Agregar datos cargados
            if self.datos_excel is not None:
                df = self.datos_excel.dropna(subset=['Temperatura', 'W (kg_vp/kg_AS)', 'φ (%)'])
                Tbs_list = df['Temperatura'].astype(float).values
                W_list = df['W (kg_vp/kg_AS)'].astype(float).values
                phi_list = df['φ (%)'].astype(float).values

                if len(Tbs_list) == 0 or len(W_list) == 0:
                    messagebox.showwarning("Advertencia", "No hay datos válidos para graficar.")
                    return

                plt.scatter(Tbs_list, W_list, marker='o', color='blue', label='Datos Cargados')

                # Crear grid para contour
                if len(Tbs_list) > 3 and len(W_list) > 3:
                    grid_x, grid_y = np.mgrid[min(Tbs_list):max(Tbs_list):100j, min(W_list):max(W_list):100j]
                    points = np.column_stack((Tbs_list, W_list))
                    values = phi_list
                    grid_z = griddata(points, values, (grid_x, grid_y), method='linear')

                    plt.contourf(grid_x, grid_y, grid_z, levels=15, cmap='viridis', alpha=0.5)

            elif self.datos_promedio is not None:
                Tbs_list = []
                W_list = []
                Hr_list = []
                for item in self.tabla.get_children():
                    valores = self.tabla.item(item)['values']
                    try:
                        Tbs_val = float(valores[4])
                        W_val = float(valores[11])
                        Hr_val = float(valores[6])
                        Tbs_list.append(Tbs_val)
                        W_list.append(W_val)
                        Hr_list.append(Hr_val)
                    except:
                        continue

                if len(Tbs_list) == 0 or len(W_list) == 0:
                    messagebox.showwarning("Advertencia", "No hay datos válidos para graficar.")
                    return

                plt.scatter(Tbs_list, W_list, marker='o', color='red', label='Datos Registrados')

                # Crear grid para contour
                if len(Tbs_list) > 3 and len(W_list) > 3:
                    grid_x, grid_y = np.mgrid[min(Tbs_list):max(Tbs_list):100j, min(W_list):max(W_list):100j]
                    points = np.column_stack((Tbs_list, W_list))
                    values = Hr_list
                    grid_z = griddata(points, values, (grid_x, grid_y), method='linear')

                    plt.contourf(grid_x, grid_y, grid_z, levels=15, cmap='viridis', alpha=0.5)

            else:
                messagebox.showwarning("Advertencia", "No hay datos cargados para graficar.")
                return

            plt.xlabel('Tbs (°C)')
            plt.ylabel('W (kg_vp/kg_AS)')
            plt.title('Gráfico Psicrométrico: Tbs vs W')
            plt.legend()
            plt.grid(True)

            plt.show()
        except Exception as e:
            messagebox.showerror("Error", f"Error al generar el gráfico psicrométrico: {e}")

    def graficar_climograma(self):
        try:
            if self.df_daily_avg is not None and not self.df_daily_avg.empty:
                datos = self.df_daily_avg
                dias = np.arange(len(datos))

                # Determinar si usar 'Temperatura' o 'Tbs (°C)'
                if 'Temperatura' in datos.columns:
                    temperatura = datos['Temperatura'].values
                elif 'Tbs (°C)' in datos.columns:
                    temperatura = datos['Tbs (°C)'].values
                else:
                    temperatura = [0]*len(datos)

                # Verificar si hay datos de 'Radiación Solar (W/m²)'
                if 'Radiación Solar (W/m²)' in datos.columns and not datos['Radiación Solar (W/m²)'].isnull().all():
                    radiacion = datos['Radiación Solar (W/m²)'].values
                    tiene_radiacion = True
                else:
                    radiacion = [0]*len(datos)
                    tiene_radiacion = False

                fig, ax1 = plt.subplots()

                ax1.set_xlabel('Día')
                if tiene_radiacion:
                    ax1.set_ylabel('Radiación Global Promedio (W/m²)', color='tab:blue')
                    ax1.bar(dias, radiacion, color='blue', label='Radiación (W/m²)', alpha=0.7)
                    ax1.tick_params(axis='y', labelcolor='tab:blue')
                else:
                    ax1.set_ylabel('')

                ax2 = ax1.twinx()
                ax2.set_ylabel('Temperatura Promedio (°C)', color='tab:red')
                ax2.plot(dias, temperatura, color='red', marker='o', linestyle='-', label='Temperatura (°C)', linewidth=2, markersize=6)
                ax2.tick_params(axis='y', labelcolor='tab:red')

                ax1.set_xticks(np.arange(0, len(dias), max(1, len(dias)//10)))

                fig.tight_layout()
                plt.title("Climograma: Temperatura vs Radiación")
                plt.show()

            else:
                raise ValueError("No se han cargado datos para graficar.")

        except Exception as e:
            messagebox.showerror("Error", f"Error al generar el climograma: {e}")

    def tabla_data(self):
        for item in self.tabla.get_children():
            valores = self.tabla.item(item)['values']
            yield dict(zip(self.tabla["columns"], valores))

    def calcular_desde_bulbo_humedo(self):
        try:
            # Pedir entrada de temperatura de bulbo seco, bulbo húmedo y altura
            Tbs = float(simpledialog.askstring("Entrada", "Introduce la temperatura de bulbo seco en °C:", parent=self.root))
            Tbh = float(simpledialog.askstring("Entrada", "Introduce la temperatura de bulbo húmedo en °C:", parent=self.root))
            altura = float(simpledialog.askstring("Entrada", "Introduce la altura en metros:", parent=self.root))
            
            if altura < 0:
                raise ValueError("La altura no puede ser negativa.")
            if Tbs < Tbh:
                raise ValueError("La temperatura de bulbo seco debe ser mayor o igual a la de bulbo húmedo.")
    
            # Calcular la presión atmosférica
            presionAt = self.calculadora.calcular_presion(altura)
    
            # Calcular la humedad relativa desde el bulbo húmedo
            Hr = self.calculadora.calcular_humedad_relativa_desde_bulbo_humedo(Tbs, Tbh, presionAt)
            
            # Verificar límites
            if Hr <= 0 or Hr > 1:
                raise ValueError("La humedad relativa calculada está fuera de los límites (0 < Hr ≤ 1).")
    
            # Continuar con los cálculos
            pvs2 = self.calculadora.calcular_pvs(Tbs)
            Pv = self.calculadora.calcular_pv(Hr, pvs2)
            W = self.calculadora.razon_humedad(Pv, presionAt)
            Ws = self.calculadora.razon_humedad_saturada(pvs2, presionAt)
            Gsaturacion = self.calculadora.grado_saturacion(W, Ws)
            Veh = self.calculadora.volumen_especifico(Tbs, presionAt, W)
            Tpr = self.calculadora.temperatura_punto_rocio(Tbs, Pv)
            h = self.calculadora.entalpia(Tbs, W)
    
            idx = len(self.tabla.get_children()) + 1
            fecha_actual = datetime.now().strftime('%Y-%m-%d')
            hora_actual = datetime.now().strftime('%H:%M:%S')
            self.tabla.insert("", "end", values=[idx, fecha_actual, hora_actual, altura, Tbs, Tbh, Hr * 100, Tpr, pvs2/1000, Pv/1000, Ws, W, Gsaturacion, Veh, h])
    
        except Exception as e:
            messagebox.showerror("Error", f"Ocurrió un error al calcular: {e}")

    def calcular_desde_humedad_relativa(self):
        try:
            # Pedir entrada de temperatura de bulbo seco, humedad relativa y altura
            Tbs = float(simpledialog.askstring("Entrada", "Introduce la temperatura de bulbo seco en °C:", parent=self.root))
            Hr = float(simpledialog.askstring("Entrada", "Introduce la humedad relativa en %:", parent=self.root)) / 100
            altura = float(simpledialog.askstring("Entrada", "Introduce la altura en metros:", parent=self.root))
            
            if altura < 0:
                raise ValueError("La altura no puede ser negativa.")
            if Hr <= 0 or Hr > 1:
                raise ValueError("La humedad relativa debe estar entre 0 y 100%.")
    
            # Calcular la presión atmosférica
            presionAt = self.calculadora.calcular_presion(altura)
    
            # Continuar con los cálculos
            pvs2 = self.calculadora.calcular_pvs(Tbs)
            Pv = self.calculadora.calcular_pv(Hr, pvs2)
            W = self.calculadora.razon_humedad(Pv, presionAt)
            Ws = self.calculadora.razon_humedad_saturada(pvs2, presionAt)
            Gsaturacion = self.calculadora.grado_saturacion(W, Ws)
            Veh = self.calculadora.volumen_especifico(Tbs, presionAt, W)
            Tpr = self.calculadora.temperatura_punto_rocio(Tbs, Pv)
            h = self.calculadora.entalpia(Tbs, W)
            Tbh = self.calculadora.bulbo_humedo(presionAt, Tbs, W)
    
            idx = len(self.tabla.get_children()) + 1
            fecha_actual = datetime.now().strftime('%Y-%m-%d')
            hora_actual = datetime.now().strftime('%H:%M:%S')
            self.tabla.insert("", "end", values=[idx, fecha_actual, hora_actual, altura, Tbs, Tbh, Hr * 100, Tpr, pvs2/1000, Pv/1000, Ws, W, Gsaturacion, Veh, h])
    
        except Exception as e:
            messagebox.showerror("Error", f"Ocurrió un error al calcular: {e}")

if __name__ == "__main__":
    calculadora = CalculadoraPropiedades()
    manejo_datos = ManejoDatos()
    interfaz = InterfazGrafica(calculadora, manejo_datos)
    interfaz.iniciar_interfaz()
