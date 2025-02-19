'''
Software por Diego Ramos AB24_77
Versión 3.2.4
'''

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from scipy import stats
from scipy.interpolate import griddata
import matplotlib.dates as mdates
from matplotlib.colors import LinearSegmentedColormap
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import math
import openpyxl
import xlrd
import os

##############

class ManejadorDatos:
    @staticmethod
    def cargar_archivo(ruta):
        """
        Carga datos desde diferentes formatos de archivo y procesa las columnas.
        
        Args:
            ruta (str): Ruta del archivo a cargar
            
        Returns:
            pd.DataFrame: DataFrame con los datos procesados
        """
        extension = ruta.split('.')[-1].lower()
        
        try:
            if extension == 'csv':
                datos = pd.read_csv(ruta)
            elif extension in ['xlsx', 'xls']:
                xl = pd.ExcelFile(ruta)
                if len(xl.sheet_names) > 1:
                    hoja = ManejadorDatos.seleccionar_hoja(xl.sheet_names)
                    if not hoja:
                        return None
                    datos = pd.read_excel(ruta, sheet_name=hoja)
                else:
                    datos = pd.read_excel(ruta)
            else:
                raise ValueError(f"Formato de archivo no soportado: {extension}")

            # Procesar y renombrar columnas
            datos = ManejadorDatos.procesar_columnas(datos)
            return datos
            
        except Exception as e:
            raise Exception(f"Error al cargar el archivo: {str(e)}")

    @staticmethod
    def procesar_columnas(datos):
        """
        Procesa las columnas, filtra outliers y calcula promedios cada 10 minutos.
        
        Args:
            datos (pd.DataFrame): DataFrame original
            
        Returns:
            pd.DataFrame: DataFrame procesado con promedios cada 10 minutos
        """
        # Mapeo de nombres de columnas exactamente como están en el Excel
        mapeo_columnas = {
            'Fecha': 'Fecha',
            'Hora': 'Hora',
            'S1_temp_sustrato': 'S1_temp_sustrato',
            'S2_temp_tallo': 'S2_temp_tallo',
            'S3_temp_hoja': 'S3_temp_hoja',
            'S4_temp_fruto': 'S4_temp_fruto',
            'S5_temp_1m_altura': 'S5_temp_1m_altura',
            'S6_temp_2m_altura': 'S6_temp_2m_altura',
            'S7_temp_3_altura': 'S7_temp_3_altura',
            'Temp_interna_invernadero': 'Temp_interna_invernadero',
            'Hum_interna_invernadero': 'Hum_interna_invernadero',
            'Temp_externa_invernadero': 'Temp_externa_invernadero',
            'Hum_externa_invernadero': 'Hum_externa_invernadero'
        }
        
        # Renombrar columnas
        datos = datos.rename(columns=mapeo_columnas)
        
        def detectar_cambios_bruscos(serie):
            """Detecta cambios bruscos en una serie de temperaturas."""
            diff_prev = abs(serie - serie.shift(1))
            diff_next = abs(serie - serie.shift(-1))
            umbral_cambio = 1.5
            return (diff_prev > umbral_cambio) & (diff_next > umbral_cambio)
        
        # Columnas de temperatura que requieren tratamiento de outliers
        columnas_temperatura = [
            'S1_temp_sustrato', 'S2_temp_tallo', 'S3_temp_hoja', 'S4_temp_fruto',
            'S5_temp_1m_altura', 'S6_temp_2m_altura', 'S7_temp_3_altura',
            'Temp_interna_invernadero', 'Temp_externa_invernadero'
        ]
        
        # Columnas de humedad (solo para promedios)
        columnas_humedad = [
            'Hum_interna_invernadero', 'Hum_externa_invernadero'
        ]
        
        # Procesar outliers solo en columnas de temperatura
        for columna in columnas_temperatura:
            if columna in datos.columns:
                datos[columna] = pd.to_numeric(datos[columna], errors='coerce')
                valores_originales = datos[columna].copy()
                
                # 1. Filtro inicial de valores físicamente imposibles
                mask_fisico = (datos[columna] >= -10) & (datos[columna] <= 75)
                datos.loc[~mask_fisico, columna] = np.nan
                
                # 2. Detectar cambios bruscos
                mask_cambios = detectar_cambios_bruscos(datos[columna])
                datos.loc[mask_cambios, columna] = np.nan
                
                # 3. Filtro basado en la mediana local
                ventana = datos[columna].rolling(window=5, center=True)
                mediana_local = ventana.median()
                std_local = ventana.std()
                
                desviacion = abs(datos[columna] - mediana_local)
                mask_desviacion = desviacion > (1.5 * std_local)
                datos.loc[mask_desviacion, columna] = np.nan
                
                # 4. Interpolación de valores faltantes
                datos[columna] = datos[columna].interpolate(method='linear', limit=2)
                
                # Para huecos más grandes, usar la mediana local
                mask_nan = datos[columna].isna()
                if mask_nan.any():
                    for idx in datos.index[mask_nan]:
                        inicio = max(0, idx - 2)
                        fin = min(len(datos), idx + 3)
                        valores_cercanos = datos.loc[inicio:fin, columna].dropna()
                        if len(valores_cercanos) > 0:
                            datos.loc[idx, columna] = valores_cercanos.median()
                
                # 5. Redondear solo los valores que fueron interpolados
                mascara_valores_modificados = (datos[columna] != valores_originales) | mask_nan
                datos.loc[mascara_valores_modificados, columna] = datos.loc[mascara_valores_modificados, columna].round(1)
        
        # Convertir columnas de humedad a numérico
        for columna in columnas_humedad:
            if columna in datos.columns:
                datos[columna] = pd.to_numeric(datos[columna], errors='coerce')
        
        # Combinar fecha y hora
        if 'Fecha' in datos.columns and 'Hora' in datos.columns:
            datos['Fecha_Hora'] = pd.to_datetime(
                datos['Fecha'].astype(str) + ' ' + datos['Hora'].astype(str)
            )
            datos = datos.drop(['Fecha', 'Hora'], axis=1)
        
        # Establecer Fecha_Hora como índice para el resample
        datos.set_index('Fecha_Hora', inplace=True)
        
        # Calcular promedios cada 10 minutos para todas las columnas numéricas
        columnas_para_promedio = columnas_temperatura + columnas_humedad
        datos_promedio = datos[columnas_para_promedio].resample('10min').mean()
        
        # Interpolar valores NaN en los promedios
        for columna in datos_promedio.columns:
            datos_promedio[columna] = datos_promedio[columna].interpolate(
                method='linear',
                limit=7  # límite de 7 períodos de 10 minutos
            )
        
        # Redondear todos los valores a un decimal
        datos_promedio = datos_promedio.round(1)
        
        # Resetear el índice para tener Fecha_Hora como columna
        datos_promedio.reset_index(inplace=True)
        
        return datos_promedio

    @staticmethod
    def seleccionar_hoja(hojas):
        """
        Muestra un diálogo para seleccionar una hoja del Excel.
        
        Args:
            hojas (list): Lista de nombres de hojas disponibles
            
        Returns:
            str: Nombre de la hoja seleccionada o None si se cancela
        """
        dialog = tk.Toplevel()
        dialog.title("Seleccionar Hoja")
        dialog.geometry("300x200")
        dialog.transient(dialog.master)
        dialog.grab_set()
        
        # Variable para almacenar la selección
        seleccion = tk.StringVar(value=hojas[0])
        
        ttk.Label(dialog, 
                 text="Seleccione la hoja a cargar:").pack(pady=10)
        
        # Listbox para mostrar las hojas
        listbox = tk.Listbox(dialog, height=5)
        listbox.pack(pady=5, fill='x', padx=20)
        for hoja in hojas:
            listbox.insert(tk.END, hoja)
        
        # Variable para almacenar el resultado
        resultado = {'hoja': None}
        
        def confirmar():
            if listbox.curselection():
                resultado['hoja'] = listbox.get(listbox.curselection())
            dialog.destroy()
        
        def cancelar():
            dialog.destroy()
        
        # Botones
        frame_botones = ttk.Frame(dialog)
        frame_botones.pack(pady=10)
        ttk.Button(frame_botones, 
                  text="Aceptar",
                  command=confirmar).pack(side='left', padx=5)
        ttk.Button(frame_botones,
                  text="Cancelar",
                  command=cancelar).pack(side='left', padx=5)
        
        dialog.wait_window()
        return resultado['hoja']

    @staticmethod
    def guardar_archivo(datos, ruta):
        """
        Guarda los datos en diferentes formatos.
        
        Args:
            datos (pd.DataFrame): DataFrame a guardar
            ruta (str): Ruta donde guardar el archivo
        """
        extension = ruta.split('.')[-1].lower()
        
        try:
            if extension == 'csv':
                datos.to_csv(ruta, index=False)
            elif extension in ['xlsx', 'xls']:
                datos.to_excel(ruta, index=False)
            else:
                raise ValueError(f"Formato de archivo no soportado: {extension}")
        except Exception as e:
            raise Exception(f"Error al guardar el archivo: {str(e)}")

class CalculadoraPropiedades:
    def __init__(self):
        self.Ra = 287.055  # J/(kg·K)
        self.P0 = 101325   # Pa

    def Grados_Kelvin(self, temp):
        return temp + 273.15

    def calcular_presion(self, altura):
        p_atm_Pa = self.P0 * (1 - 2.25577e-5 * altura) ** 5.2559
        return p_atm_Pa / 1000  # Convertir Pa a kPa

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
            ln_pws = (C1 / Tbs_K) + C2 + C3 * Tbs_K + C4 * Tbs_K ** 2 + \
                     C5 * Tbs_K ** 3 + C6 * Tbs_K ** 4 + C7 * math.log(Tbs_K)
        else:
            C8 = -5.8002206e3
            C9 = 1.3914993e0
            C10 = -4.8640239e-2
            C11 = 4.1764768e-5
            C12 = -1.4452093e-8
            C13 = 6.5459673e0
            ln_pws = (C8 / Tbs_K) + C9 + C10 * Tbs_K + C11 * Tbs_K ** 2 + \
                     C12 * Tbs_K ** 3 + C13 * math.log(Tbs_K)

        return math.exp(ln_pws) / 1000  # Convertir Pa a kPa

    def calcular_pv(self, Hr, pvs2):
        return (Hr / 100) * pvs2

    def razon_humedad(self, Pv_Pa, presionAt_Pa):
        return 0.622 * (Pv_Pa / (presionAt_Pa - Pv_Pa))

    def razon_humedad_saturada(self, pvs2_Pa, presionAt_Pa):
        return 0.622 * (pvs2_Pa / (presionAt_Pa - pvs2_Pa))

    def grado_saturacion(self, W, Ws):
        return (W / Ws) * 100

    def volumen_especifico(self, Tbs, presionAt_Pa, W):
        Tbs_K = self.Grados_Kelvin(Tbs)
        return ((self.Ra * Tbs_K) / presionAt_Pa) * (1 + 1.6078 * W) / (1 + W)

    def temperatura_punto_rocio(self, Pv_Pa):
        Pv_hPa = Pv_Pa / 100  # Convertir Pa a hPa
        if Pv_hPa <= 0:
            Pv_hPa = 0.01
        gamma = math.log(Pv_hPa / 6.112)
        Tpr = (243.5 * gamma) / (17.67 - gamma)
        return Tpr

    def entalpia(self, Tbs, W):
        return 1.006 * Tbs + W * (2501 + 1.805 * Tbs)

    def calcular_propiedades_desde_Tbs_Hr(self, Tbs, Hr, presionAt):
        if Hr <= 0 or Hr > 100:
            raise ValueError("La humedad relativa debe estar entre 0 y 100%.")
        
        pvs = self.calcular_pvs(Tbs)
        Pv = self.calcular_pv(Hr, pvs)
        W = self.razon_humedad(Pv * 1000, presionAt * 1000)
        Ws = self.razon_humedad_saturada(pvs * 1000, presionAt * 1000)
        Gsaturacion = self.grado_saturacion(W, Ws)
        Veh = self.volumen_especifico(Tbs, presionAt * 1000, W)
        Tpr = self.temperatura_punto_rocio(Pv * 1000)
        h = self.entalpia(Tbs, W)

        return {
            "Tbs (°C)": Tbs,
            "φ (%)": Hr,
            "Tpr (°C)": Tpr,
            "Pvs (kPa)": pvs,
            "Pv (kPa)": Pv,
            "Ws (kg_vp/kg_AS)": Ws,
            "W (kg_vp/kg_AS)": W,
            "μ [G_sat]": Gsaturacion,
            "Veh (m³/kg_AS)": Veh,
            "h (kJ/kg_AS)": h
        }

class InterfazGraficaMejorada:
    def __init__(self, calculadora):
        self.calculadora = calculadora
        self.datos = None
        self.root = None
        self.selected_row = None
        self.analizador = None
        self.current_panel = None
        self.nav_buttons = {}

    def iniciar_interfaz(self):
        """Inicializa y configura la interfaz principal."""
        self.root = tk.Tk()
        self.root.title("Sistema de Análisis de Invernadero Software AB24_77 V3.27")
        self.root.geometry("1400x800")
        
        # Configurar tema y estilo
        self.setup_styles()
        
        # Frame principal
        self.main_container = ttk.Frame(self.root)
        self.main_container.pack(fill='both', expand=True)
        
        # Crear navbar
        self.crear_navbar()
        
        # Crear área de trabajo principal
        self.workspace = ttk.Frame(self.main_container, padding="10")
        self.workspace.pack(fill='both', expand=True)
        
        # Crear paneles
        self.crear_panel_datos()
        self.crear_panel_analisis()
        self.crear_panel_visualizacion()
        
        # Mostrar panel inicial
        self.mostrar_panel('datos')
        
        # Configurar eventos
        self.configurar_eventos()
        
        self.root.mainloop()

    def setup_styles(self):
        """Configura los estilos de la interfaz."""
        style = ttk.Style(self.root)
        style.theme_use('clam')
        
        # Colores
        primary_color = '#2c3e50'
        secondary_color = '#34495e'
        accent_color = '#3498db'
        
        # Configuración general
        style.configure('.',
                       background='#f5f6fa',
                       foreground='#333333',
                       font=('Arial', 10))
        
        # Navbar
        style.configure('Navbar.TFrame',
                       background=primary_color)
        style.configure('Navbar.TButton',
                       background=primary_color,
                       foreground='white',
                       padding=10)
        
        # Botones
        style.configure('Action.TButton',
                       background=accent_color,
                       foreground='white',
                       padding=(10, 5))
        
        # Headers
        style.configure('Header.TLabel',
                       font=('Arial', 14, 'bold'),
                       foreground=primary_color)

    def crear_navbar(self):
        """Crea la barra de navegación."""
        navbar = ttk.Frame(self.main_container, style='Navbar.TFrame')
        navbar.pack(fill='x', side='top')
        
        # Botones de navegación
        for text, panel_id in [
            ("Datos", "datos"),
            ("Análisis", "analisis"),
            ("Visualización", "visualizacion")
        ]:
            btn = ttk.Button(navbar,
                           text=text,
                           command=lambda p=panel_id: self.mostrar_panel(p),
                           style='Navbar.TButton')
            btn.pack(side='left', padx=2)
            self.nav_buttons[panel_id] = btn

    def validar_altura(self, value):
        """Valida que la entrada de altura sea un número no negativo."""
        if value == "":
            return True
        try:
            num = float(value)
            return num >= 0
        except ValueError:
            return False
        
    def resaltar_error_altura(self):
        """Resalta el campo de altura en rojo temporalmente."""
        self.altura_entry.configure(style="Error.TEntry")
        self.root.after(1000, lambda: self.altura_entry.configure(style="TEntry"))

    def obtener_altura(self):
        """Obtiene la altura ingresada o usa el valor por defecto."""
        try:
            return float(self.altura_entry.get() or 0)
        except ValueError:
            return 0

    def mostrar_menu_borrado(self):
        """Muestra el menú de opciones de borrado."""
        if not hasattr(self, 'datos') or self.datos is None:
            messagebox.showwarning("Advertencia", "No hay datos para borrar")
            return
            
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="Borrar Todo", command=self.borrar_todo)
        menu.add_command(label="Borrar por Rango de Fechas", command=self.borrar_por_fechas)
        
        try:
            menu.tk_popup(
                self.root.winfo_pointerx(),
                self.root.winfo_pointery()
            )
        finally:
            menu.grab_release()

    def borrar_todo(self):
        """Borra todos los datos de la tabla."""
        if messagebox.askyesno("Confirmar", "¿Está seguro de borrar todos los datos?"):
            self.datos = None
            self.analizador = None
            
            # Limpiar tabla
            for item in self.tabla.get_children():
                self.tabla.delete(item)
            
            # Actualizar estado
            self.archivo_label.config(text="No hay archivo cargado")
            self.registros_label.config(text="0 registros")
            
            # Deshabilitar botones de análisis y visualización
            self.deshabilitar_botones_analisis()

    def borrar_por_fechas(self):
        """Abre una ventana para seleccionar el rango de fechas a borrar."""
        if 'Fecha_Hora' not in self.datos.columns:
            messagebox.showerror("Error", "Los datos no contienen información de fechas")
            return
            
        ventana = tk.Toplevel(self.root)
        ventana.title("Borrar por Rango de Fechas")
        ventana.geometry("400x250") # "XxY"
        
        # Crear frame principal
        frame = ttk.Frame(ventana, padding="10")
        frame.pack(fill='both', expand=True)
        
        # Fechas mínima y máxima disponibles
        fecha_min = self.datos['Fecha_Hora'].min()
        fecha_max = self.datos['Fecha_Hora'].max()
        
        # Variables para las fechas
        fecha_inicio = tk.StringVar(value=fecha_min.strftime('%Y-%m-%d %H:%M:%S'))
        fecha_fin = tk.StringVar(value=fecha_max.strftime('%Y-%m-%d %H:%M:%S'))
        
        # Widgets para fecha inicial
        ttk.Label(frame, text="Fecha Inicial:").pack(pady=5)
        entry_inicio = ttk.Entry(frame, textvariable=fecha_inicio)
        entry_inicio.pack(pady=5)
        
        # Widgets para fecha final
        ttk.Label(frame, text="Fecha Final:").pack(pady=5)
        entry_fin = ttk.Entry(frame, textvariable=fecha_fin)
        entry_fin.pack(pady=5)
        
        def aplicar_borrado():
            try:
                inicio = pd.to_datetime(fecha_inicio.get())
                fin = pd.to_datetime(fecha_fin.get())
                
                if inicio > fin:
                    messagebox.showerror("Error", "La fecha inicial debe ser anterior a la fecha final")
                    return
                    
                # Filtrar datos fuera del rango seleccionado
                mascara = ~self.datos['Fecha_Hora'].between(inicio, fin)
                self.datos = self.datos[mascara].reset_index(drop=True)
                
                # Actualizar tabla
                self.actualizar_tabla()
                
                # Actualizar contador de registros
                self.registros_label.config(text=f"{len(self.datos)} registros")
                
                # Cerrar ventana
                ventana.destroy()
                
            except ValueError:
                messagebox.showerror("Error", "Formato de fecha inválido.\nUse: YYYY-MM-DD HH:MM:SS")
        
        # Botones
        frame_botones = ttk.Frame(frame)
        frame_botones.pack(pady=20)
        
        ttk.Button(frame_botones, text="Aplicar", command=aplicar_borrado).pack(side='left', padx=5)
        ttk.Button(frame_botones, text="Cancelar", command=ventana.destroy).pack(side='left', padx=5)

    def deshabilitar_botones_analisis(self):
        """
        Deshabilita los botones de análisis y visualización cuando no hay datos.
        Solo se deshabilitan si el DataFrame está vacío o es None.
        """
        should_disable = not hasattr(self, 'datos') or self.datos is None or len(self.datos) == 0
        
        if hasattr(self, 'analisis_buttons'):
            for btn in self.analisis_buttons.values():
                if should_disable:
                    btn.state(['disabled'])
                else:
                    btn.state(['!disabled'])
                
        if hasattr(self, 'visualizacion_buttons'):
            for btn in self.visualizacion_buttons.values():
                if should_disable:
                    btn.state(['disabled'])
                else:
                    btn.state(['!disabled'])

    def crear_panel_datos(self):
        """Crea el panel principal de datos con funcionalidades extendidas."""
        self.panel_datos = ttk.Frame(self.workspace)
        
        # Crear subframe para la barra de herramientas
        self.toolbar = ttk.Frame(self.panel_datos)
        self.toolbar.pack(fill='x', pady=5, padx=5)
        
        # Frame para botones principales
        btn_frame = ttk.Frame(self.toolbar)
        btn_frame.pack(side='left', fill='x')
        
        # Botones principales con iconos
        self.crear_boton_con_tooltip(
            btn_frame, "Cargar Datos", self.cargar_datos,
            "Cargar datos desde archivo CSV o Excel"
        ).pack(side='left', padx=2)
        
        self.crear_boton_con_tooltip(
            btn_frame, "Guardar Datos", self.guardar_datos,
            "Guardar datos en archivo CSV o Excel"
        ).pack(side='left', padx=2)
        
        self.crear_boton_con_tooltip(
            btn_frame, "Abrir Archivo", self.mostrar_menu_archivos,
            "Abrir diferentes tipos de archivos"
        ).pack(side='left', padx=2)
        
        self.crear_boton_con_tooltip(
            btn_frame, "Borrar", self.mostrar_menu_borrado,
            "Borrar datos de la tabla"
        ).pack(side='left', padx=2)
        
        # Frame para la entrada de altura
        altura_frame = ttk.Frame(btn_frame)
        altura_frame.pack(side='left', padx=10)
        
        ttk.Label(altura_frame, text="Altura (msnm):").pack(side='left', padx=2)
        
        vcmd = (self.root.register(self.validar_altura), '%P')
        self.altura_entry = ttk.Entry(altura_frame, width=10, validate='key', 
                                    validatecommand=vcmd)
        self.altura_entry.pack(side='left', padx=2)
        self.altura_entry.insert(0, "0")
        
        # Variable para controlar el número de intentos de carga sin altura
        self.intentos_carga = 0
        
        # Estilo para el entry normal y con error
        style = ttk.Style()
        style.configure("Error.TEntry", fieldbackground="pink")
        
        # Separador
        ttk.Separator(self.toolbar, orient='vertical').pack(side='left', padx=5, fill='y')
        
        # Frame para información y estado
        info_frame = ttk.Frame(self.toolbar)
        info_frame.pack(side='right', fill='x')
        
        self.estado_label = ttk.Label(info_frame, text="Listo")
        self.estado_label.pack(side='right', padx=5)
        
        # Crear tabla
        self.crear_tabla(self.panel_datos)
        
        # Barra de estado inferior
        self.crear_barra_estado()
        
        # Hacer que el panel ocupe todo el espacio disponible
        self.panel_datos.pack(fill='both', expand=True)
    
    def crear_boton_con_tooltip(self, parent, texto, comando, tooltip):
        """Crea un botón con tooltip."""
        btn = ttk.Button(parent, text=texto, command=comando, style='Action.TButton')
        
        def mostrar_tooltip(event):
            if hasattr(self, 'tooltip') and self.tooltip:
                self.tooltip.destroy()
            
            x = btn.winfo_rootx() + 25
            y = btn.winfo_rooty() + 20
            
            self.tooltip = tk.Toplevel(btn)
            self.tooltip.wm_overrideredirect(True)
            self.tooltip.wm_geometry(f"+{x}+{y}")
            
            label = ttk.Label(self.tooltip, text=tooltip, 
                            justify='left',
                            background="#ffffe0", 
                            relief='solid', 
                            borderwidth=1)
            label.pack()
        
        def ocultar_tooltip(event):
            if hasattr(self, 'tooltip') and self.tooltip:
                self.tooltip.destroy()
                self.tooltip = None
        
        btn.bind('<Enter>', mostrar_tooltip)
        btn.bind('<Leave>', ocultar_tooltip)
        
        return btn

    def crear_barra_estado(self):
        """Crea una barra de estado en la parte inferior."""
        status_frame = ttk.Frame(self.panel_datos)
        status_frame.pack(fill='x', side='bottom', pady=2)
        
        # Información del archivo
        self.archivo_label = ttk.Label(status_frame, text="No hay archivo cargado")
        self.archivo_label.pack(side='left', padx=5)
        
        # Separador
        ttk.Separator(status_frame, orient='vertical').pack(side='left', padx=5, fill='y')
        
        # Información de registros
        self.registros_label = ttk.Label(status_frame, text="0 registros")
        self.registros_label.pack(side='left', padx=5)

    def mostrar_menu_archivos(self):
        """Muestra un menú desplegable para diferentes tipos de archivos."""
        menu = tk.Menu(self.root, tearoff=0)
        
        # Submenú para Excel
        excel_menu = tk.Menu(menu, tearoff=0)
        excel_menu.add_command(label="Nuevo", command=lambda: self.abrir_archivo('excel', 'nuevo'))
        excel_menu.add_command(label="Existente", command=lambda: self.abrir_archivo('excel', 'existente'))
        menu.add_cascade(label="Excel", menu=excel_menu)
        
        # Submenú para Word
        word_menu = tk.Menu(menu, tearoff=0)
        word_menu.add_command(label="Nuevo", command=lambda: self.abrir_archivo('word', 'nuevo'))
        word_menu.add_command(label="Existente", command=lambda: self.abrir_archivo('word', 'existente'))
        menu.add_cascade(label="Word", menu=word_menu)
        
        # Submenú para PowerPoint
        ppt_menu = tk.Menu(menu, tearoff=0)
        ppt_menu.add_command(label="Nuevo", command=lambda: self.abrir_archivo('powerpoint', 'nuevo'))
        ppt_menu.add_command(label="Existente", command=lambda: self.abrir_archivo('powerpoint', 'existente'))
        menu.add_cascade(label="PowerPoint", menu=ppt_menu)
        
        # Mostrar el menú
        try:
            menu.tk_popup(
                self.root.winfo_pointerx(),
                self.root.winfo_pointery()
            )
        finally:
            menu.grab_release()

    def abrir_archivo(self, tipo, modo):
        """
        Abre archivos de Office usando las aplicaciones predeterminadas.
        
        Args:
            tipo (str): 'excel', 'word', o 'powerpoint'
            modo (str): 'nuevo' o 'existente'
        """
        try:
            # Definir las extensiones y tipos de archivo por tipo
            tipos_archivo = {
                'excel': {
                    'extensiones': ['xlsx', 'xls'],
                    'filetypes': [('Excel Files', '*.xlsx;*.xls')],
                    'default_ext': '.xlsx'
                },
                'word': {
                    'extensiones': ['docx', 'doc'],
                    'filetypes': [('Word Files', '*.docx;*.doc')],
                    'default_ext': '.docx'
                },
                'powerpoint': {
                    'extensiones': ['pptx', 'ppt'],
                    'filetypes': [('PowerPoint Files', '*.pptx;*.ppt')],
                    'default_ext': '.pptx'
                }
            }
            
            if modo == 'existente':
                # Configurar el diálogo de archivo para el tipo específico
                config_tipo = tipos_archivo.get(tipo, {})
                filename = filedialog.askopenfilename(
                    title=f'Abrir archivo de {tipo.capitalize()}',
                    filetypes=[
                        config_tipo['filetypes'][0],
                        ('Todos los archivos', '*.*')
                    ],
                    defaultextension=config_tipo['default_ext']
                )
                
                if filename:
                    import platform
                    import subprocess
                    import os
                    from pathlib import Path
                    
                    system = platform.system().lower()
                    extension = Path(filename).suffix.lower()[1:]  # Obtener extensión sin el punto
                    
                    try:
                        if system == 'windows':
                            # En Windows, asegurarse de usar la asociación de tipo de archivo
                            from win32com import client
                            if extension in ['xlsx', 'xls']:
                                excel = client.Dispatch('Excel.Application')
                                excel.Visible = True
                                excel.Workbooks.Open(filename)
                            elif extension in ['docx', 'doc']:
                                word = client.Dispatch('Word.Application')
                                word.Visible = True
                                word.Documents.Open(filename)
                            elif extension in ['pptx', 'ppt']:
                                powerpoint = client.Dispatch('PowerPoint.Application')
                                powerpoint.Visible = True
                                powerpoint.Presentations.Open(filename)
                            else:
                                os.startfile(filename)
                        
                        elif system == 'darwin':  # macOS
                            if extension in ['xlsx', 'xls']:
                                subprocess.run(['open', '-a', 'Microsoft Excel', filename], check=True)
                            elif extension in ['docx', 'doc']:
                                subprocess.run(['open', '-a', 'Microsoft Word', filename], check=True)
                            elif extension in ['pptx', 'ppt']:
                                subprocess.run(['open', '-a', 'Microsoft PowerPoint', filename], check=True)
                            else:
                                subprocess.run(['open', filename], check=True)
                        
                        else:  # Linux
                            # En Linux, intentar usar xdg-mime para obtener la aplicación predeterminada
                            mime_type = subprocess.run(['xdg-mime', 'query', 'filetype', filename],
                                                     capture_output=True, text=True).stdout.strip()
                            default_app = subprocess.run(['xdg-mime', 'query', 'default', mime_type],
                                                       capture_output=True, text=True).stdout.strip()
                            
                            if default_app:
                                subprocess.run(['xdg-open', filename], check=True)
                            else:
                                # Intentar con aplicaciones específicas si no hay predeterminada
                                if extension in ['xlsx', 'xls']:
                                    subprocess.run(['libreoffice', '--calc', filename], check=True)
                                elif extension in ['docx', 'doc']:
                                    subprocess.run(['libreoffice', '--writer', filename], check=True)
                                elif extension in ['pptx', 'ppt']:
                                    subprocess.run(['libreoffice', '--impress', filename], check=True)
                                else:
                                    subprocess.run(['xdg-open', filename], check=True)
                        
                        self.actualizar_estado(f"Archivo de {tipo} abierto correctamente")
                        
                    except Exception as e:
                        messagebox.showerror("Error", f"No se pudo abrir el archivo: {str(e)}")
                        
            else:  # modo == 'nuevo'
                config_tipo = tipos_archivo.get(tipo, {})
                nuevo_archivo = filedialog.asksaveasfilename(
                    defaultextension=config_tipo['default_ext'],
                    filetypes=[config_tipo['filetypes'][0]]
                )
                
                if nuevo_archivo:
                    try:
                        # Crear archivo vacío según el tipo
                        if tipo == 'excel':
                            import pandas as pd
                            df = pd.DataFrame()
                            df.to_excel(nuevo_archivo, index=False)
                        else:
                            # Para Word y PowerPoint, crear archivo vacío
                            with open(nuevo_archivo, 'w') as f:
                                pass
                        
                        # Abrir el archivo recién creado
                        self.abrir_archivo(tipo, 'existente')
                        
                    except Exception as e:
                        messagebox.showerror("Error", f"No se pudo crear el archivo: {str(e)}")
                        
        except Exception as e:
            messagebox.showerror("Error", f"Error al procesar {tipo}: {str(e)}")
            self.actualizar_estado("Error al procesar archivo")
        
    def encontrar_aplicacion_office(self, tipo):
        """
        Busca la aplicación de Office en las ubicaciones típicas de Windows.
        
        Args:
            tipo (str): 'excel', 'word', o 'powerpoint'
            
        Returns:
            str: Ruta a la aplicación o None si no se encuentra
        """
        import os
        
        # Posibles ubicaciones de Office
        office_paths = [
            os.path.expandvars(r'%ProgramFiles%\Microsoft Office\root\Office16'),
            os.path.expandvars(r'%ProgramFiles(x86)%\Microsoft Office\root\Office16'),
            os.path.expandvars(r'%ProgramFiles%\Microsoft Office\Office16'),
            os.path.expandvars(r'%ProgramFiles(x86)%\Microsoft Office\Office16'),
        ]
        
        # Nombres de ejecutables
        exe_names = {
            'excel': 'EXCEL.EXE',
            'word': 'WINWORD.EXE',
            'powerpoint': 'POWERPNT.EXE'
        }
        
        # Buscar en cada ubicación
        for path in office_paths:
            exe_path = os.path.join(path, exe_names[tipo])
            if os.path.exists(exe_path):
                return exe_path
        
        return None

    def mostrar_tooltip(event):
            x, y, _, _ = btn.bbox("insert")
            x += btn.winfo_rootx() + 25
            y += btn.winfo_rooty() + 20
            
            # Destruir tooltip existente
            self.ocultar_tooltip()
            
            self.tooltip = tk.Toplevel(btn)
            self.tooltip.wm_overrideredirect(True)
            self.tooltip.wm_geometry(f"+{x}+{y}")
            
            label = ttk.Label(self.tooltip, text=tooltip, 
                            justify='left',
                            background="#ffffe0", 
                            relief='solid', 
                            borderwidth=1)
            label.pack()
        
    def ocultar_tooltip(event=None):
        if hasattr(self, 'tooltip'):
            self.tooltip.destroy()
            self.tooltip = None
        
        self.ocultar_tooltip = ocultar_tooltip
        btn.bind('<Enter>', mostrar_tooltip)
        btn.bind('<Leave>', ocultar_tooltip)
        
        return btn

    def crear_tabla(self, parent):
        """Crea la tabla principal con las columnas actualizadas y estilo mejorado."""
        table_frame = ttk.Frame(parent)
        table_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Columnas actualizadas
        columnas = (
            "Fecha_Hora",
            "S1_temp_sustrato", "S2_temp_tallo", "S3_temp_hoja", "S4_temp_fruto",
            "S5_temp_1m_altura", "S6_temp_2m_altura", "S7_temp_3_altura",
            "Temp_interna_invernadero", "Hum_interna_invernadero",
            "Temp_externa_invernadero", "Hum_externa_invernadero",
            "Pvs (kPa)", "Pv (kPa)", 
            "W (kg_vp/kg_AS)", "h (kJ/kg_AS)", "Tpr (°C)"
        )
        
        style = ttk.Style()
        
        # Configurar estilos para filas alternadas
        style.configure("Treeview", 
                       background="white",
                       fieldbackground="white",
                       rowheight=25)
        
        # Estilo para filas alternadas
        style.map("Treeview",
                  background=[("selected", "#0078D7")],
                  foreground=[("selected", "white")])
        
        self.tabla = ttk.Treeview(
            table_frame,
            columns=columnas,
            show='headings',
            style="Treeview"
        )
        
        # Configurar columnas
        for col in columnas:
            self.tabla.heading(col, text=col)
            if col == "Fecha_Hora":
                self.tabla.column(col, width=150)
            else:
                self.tabla.column(col, width=100)
        
        # Scrollbars
        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tabla.yview)
        hsb = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tabla.xview)
        self.tabla.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        # Layout
        vsb.pack(side='right', fill='y')
        hsb.pack(side='bottom', fill='x')
        self.tabla.pack(fill='both', expand=True)
        
        # Bind para colorear filas después de insertar/actualizar datos
        def actualizar_colores_filas(event=None):
            items = self.tabla.get_children("")
            for i, item in enumerate(items):
                # Color alternado para filas
                if i % 2 == 0:
                    self.tabla.tag_configure(f'row_{i}', background='white')
                    self.tabla.item(item, tags=(f'row_{i}',))
                else:
                    self.tabla.tag_configure(f'row_{i}', background='#F5F5F5')
                    self.tabla.item(item, tags=(f'row_{i}',))
                
                # Separación cada 10 filas
                if (i + 1) % 10 == 0 and i < len(items) - 1:
                    self.tabla.tag_configure(f'separator_{i}', background='#E0E0E0')
                    self.tabla.item(items[i+1], tags=(f'separator_{i}',))
        
        self.tabla.bind('<<TreeviewOpen>>', actualizar_colores_filas)
        self.tabla.bind('<<TreeviewClose>>', actualizar_colores_filas)
        
        # Guardar la función para usarla después de cargar datos
        self.actualizar_colores_filas = actualizar_colores_filas
    
    def crear_panel_analisis(self):
        """Crea el panel de análisis."""
        self.panel_analisis = ttk.Frame(self.workspace)
        
        # Header
        ttk.Label(self.panel_analisis,
                 text="Análisis de Datos",
                 style='Header.TLabel').pack(pady=10)
        
        # Frame para botones
        button_frame = ttk.Frame(self.panel_analisis)
        button_frame.pack(pady=5)
        
        # Crear y almacenar referencias a los botones
        self.analisis_buttons = {}
        for texto, comando in [
            ("Perfil Vertical de Temperatura", self.analizar_perfil_vertical),
            ("Temperaturas de la Planta", self.analizar_temperaturas_planta),
            ("Condiciones Internas vs Externas", self.analizar_condiciones_interno_externo),
            ("Análisis de Estrés Térmico", self.analizar_estres_termico),
            ("Análisis de Correlaciones", self.analizar_correlaciones),
            ("Análisis de Series Temporales", self.analizar_series_temporales)
        ]:
            btn = ttk.Button(button_frame,
                           text=texto,
                           command=comando,
                           style='Action.TButton')
            btn.pack(pady=5)
            self.analisis_buttons[texto] = btn
            btn.state(['disabled'])

    def crear_panel_visualizacion(self):
        """Crea el panel de visualización."""
        self.panel_visualizacion = ttk.Frame(self.workspace)
        
        # Header
        ttk.Label(self.panel_visualizacion,
                 text="Visualización de Datos",
                 style='Header.TLabel').pack(pady=10)
        
        # Frame para botones
        button_frame = ttk.Frame(self.panel_visualizacion)
        button_frame.pack(pady=5)
        
        # Crear y almacenar referencias a los botones
        self.visualizacion_buttons = {}
        for texto, comando in [
            ("Mapa de Calor 3D", self.visualizar_mapa_calor_3d),
            ("Análisis Diurno vs Nocturno", self.visualizar_comparacion_diurna_nocturna),
            ("Análisis Psicrométrico", self.visualizar_analisis_psicrometrico),
            ("Carta Psicrométrica", self.visualizar_carta_psicrometrica),
            ("Distribución Espacial de Temperaturas", self.visualizar_distribucion_espacial),
            ("Tendencias y Pronósticos", self.visualizar_tendencias_pronosticos)
        ]:
            btn = ttk.Button(button_frame,
                           text=texto,
                           command=comando,
                           style='Action.TButton')
            btn.pack(pady=5)
            self.visualizacion_buttons[texto] = btn
            btn.state(['disabled'])

    def mostrar_panel(self, panel):
        """Muestra el panel seleccionado y oculta los demás."""
        # Ocultar todos los paneles
        for p in [self.panel_datos, self.panel_analisis, self.panel_visualizacion]:
            p.pack_forget()
        
        # Mostrar el panel seleccionado
        if panel == 'datos':
            self.panel_datos.pack(fill='both', expand=True)
        elif panel == 'analisis':
            self.panel_analisis.pack(fill='both', expand=True)
        elif panel == 'visualizacion':
            self.panel_visualizacion.pack(fill='both', expand=True)
        
        self.current_panel = panel

    def cargar_datos(self):
        """Carga datos desde un archivo CSV o Excel."""
        altura = self.obtener_altura()
        
        if altura == 0:
            self.intentos_carga += 1
            if self.intentos_carga == 1:
                messagebox.showwarning(
                    "Advertencia",
                    "Por favor, ingrese la altura en metros sobre el nivel del mar (msnm)"
                )
                self.resaltar_error_altura()
                return
        else:
            self.intentos_carga = 0
        
        filename = filedialog.askopenfilename(
            filetypes=[
                ("Todos los formatos", "*.csv;*.xlsx;*.xls"),
                ("Archivos CSV", "*.csv"),
                ("Archivos Excel", "*.xlsx;*.xls"),
                ("Todos los archivos", "*.*")
            ]
        )
        
        if filename:
            try:
                # Cargar datos usando el manejador
                self.datos = ManejadorDatos.cargar_archivo(filename)
                
                if self.datos is not None:
                    # Convertir columna de fecha si existe
                    if 'Fecha_Hora' in self.datos.columns:
                        self.datos['Fecha_Hora'] = pd.to_datetime(self.datos['Fecha_Hora'])
                    
                    # Calcular propiedades psicrométricas usando la altura ingresada
                    self.calcular_propiedades_psicrometricas(altura)
                    
                    # Actualizar tabla
                    self.actualizar_tabla()
                    
                    # Crear instancia del analizador
                    self.analizador = AnalisisInvernadero(self.datos, self.calculadora)
                    
                    # Habilitar botones
                    self.habilitar_botones_analisis()
                    
                    # Actualizar estado
                    self.archivo_label.config(text=f"Archivo: {os.path.basename(filename)}")
                    self.registros_label.config(text=f"{len(self.datos)} registros")
                    
                    messagebox.showinfo("Éxito", "Datos cargados correctamente")
            
            except Exception as e:
                messagebox.showerror("Error", f"Error al cargar datos: {str(e)}")
            
    def habilitar_botones_analisis(self):
        """Habilita los botones de análisis y visualización una vez que hay datos cargados."""
        if hasattr(self, 'analisis_buttons'):
            for btn in self.analisis_buttons.values():
                btn.state(['!disabled'])
                
        if hasattr(self, 'visualizacion_buttons'):
            for btn in self.visualizacion_buttons.values():
                btn.state(['!disabled'])

    def calcular_propiedades_psicrometricas(self, altura):
        """
        Calcula las propiedades psicrométricas usando temperatura y humedad internas.
        
        Args:
            altura (float): Altura en metros sobre el nivel del mar
        """
        presion_atm = self.calculadora.calcular_presion(altura)
        
        # Iterar sobre cada fila
        for idx, row in self.datos.iterrows():
            try:
                Tbs = row['Temp_interna_invernadero']
                Hr = row['Hum_interna_invernadero']
                
                # Calcular propiedades
                props = self.calculadora.calcular_propiedades_desde_Tbs_Hr(Tbs, Hr, presion_atm)
                
                # Actualizar DataFrame
                for key, value in props.items():
                    if key in ['Tbs (°C)', 'φ (%)']: continue
                    self.datos.at[idx, key] = value
                    
            except Exception as e:
                print(f"Error en fila {idx}: {str(e)}")

    def actualizar_tabla(self):
        """Actualiza la tabla con los datos procesados."""
        # Limpiar tabla
        for row in self.tabla.get_children():
            self.tabla.delete(row)
            
        # Insertar nuevos datos
        for idx, row in self.datos.iterrows():
            valores = [
                row['Fecha_Hora'].strftime('%Y-%m-%d %H:%M:%S'),
                row['S1_temp_sustrato'], row['S2_temp_tallo'],
                row['S3_temp_hoja'], row['S4_temp_fruto'],
                row['S5_temp_1m_altura'], row['S6_temp_2m_altura'],
                row['S7_temp_3_altura'],
                row['Temp_interna_invernadero'], row['Hum_interna_invernadero'],
                row['Temp_externa_invernadero'], row['Hum_externa_invernadero'],
                row.get('Pvs (kPa)', ''), row.get('Pv (kPa)', ''),
                row.get('W (kg_vp/kg_AS)', ''), row.get('h (kJ/kg_AS)', ''),
                row.get('Tpr (°C)', '')
            ]
            self.tabla.insert("", "end", values=valores)
        
        # Actualizar colores después de insertar datos
        if hasattr(self, 'actualizar_colores_filas'):
            self.actualizar_colores_filas()
        
    def guardar_datos(self):
        """Guarda los datos en formato CSV o Excel."""
        if self.datos is not None:
            filename = filedialog.asksaveasfilename(
                defaultextension=".xlsx",
                filetypes=[
                    ("Excel (*.xlsx)", "*.xlsx"),
                    ("CSV (*.csv)", "*.csv"),
                    ("Excel 97-2003 (*.xls)", "*.xls")
                ]
            )
            
            if filename:
                try:
                    ManejadorDatos.guardar_archivo(self.datos, filename)
                    messagebox.showinfo("Éxito", "Datos guardados correctamente")
                except Exception as e:
                    messagebox.showerror("Error", f"Error al guardar datos: {str(e)}")
        else:
            messagebox.showwarning("Advertencia", "No hay datos para guardar")

    def configurar_eventos(self):
        """Configura los eventos de la interfaz."""
        self.tabla.bind('<Button-3>', self.mostrar_menu_contextual)
        self.tabla.bind('<<TreeviewSelect>>', self.on_select)

    def mostrar_menu_contextual(self, event):
        """Muestra el menú contextual."""
        item = self.tabla.identify_row(event.y)
        if item:
            self.tabla.selection_set(item)
            menu = tk.Menu(self.root, tearoff=0)
            menu.add_command(label="Copiar", command=self.copiar_seleccion)
            menu.post(event.x_root, event.y_root)

    def on_select(self, event):
        """Maneja la selección de elementos en la tabla."""
        selected_items = self.tabla.selection()
        if selected_items:
            self.selected_row = selected_items[0]

    def copiar_seleccion(self):
        """Copia la selección al portapapeles."""
        if self.selected_row:
            valores = self.tabla.item(self.selected_row)['values']
            self.root.clipboard_clear()
            self.root.clipboard_append('\t'.join(map(str, valores)))

    # Métodos de análisis
    def analizar_perfil_vertical(self):
        if self.analizador:
            self.analizador.analizar_perfil_vertical()
            plt.show()
        else:
            messagebox.showwarning("Advertencia", "Cargue datos primero")

    def analizar_temperaturas_planta(self):
        if self.analizador:
            self.analizador.analizar_temperaturas_planta()
            plt.show()
        else:
            messagebox.showwarning("Advertencia", "Cargue datos primero")

    def analizar_condiciones_interno_externo(self):
        if self.analizador:
            self.analizador.analizar_condiciones_interno_externo()
            plt.show()
        else:
            messagebox.showwarning("Advertencia", "Cargue datos primero")

    def analizar_estres_termico(self):
        if self.analizador:
            self.analizador.analizar_estres_termico()
            plt.show()
        else:
            messagebox.showwarning("Advertencia", "Cargue datos primero")

    def analizar_correlaciones(self):
        if self.analizador:
            self.analizador.graficar_correlaciones()
            plt.show()
        else:
            messagebox.showwarning("Advertencia", "Cargue datos primero")

    def analizar_series_temporales(self):
        if self.analizador:
            self.analizador.graficar_series_temporales()
            plt.show()
        else:
            messagebox.showwarning("Advertencia", "Cargue datos primero")

    # Métodos de visualización
    def visualizar_mapa_calor_3d(self):
        if self.analizador:
            self.analizador.graficar_mapa_calor_3d()
            plt.show()
        else:
            messagebox.showwarning("Advertencia", "Cargue datos primero")

    def visualizar_comparacion_diurna_nocturna(self):
        if not self.analizador:
            messagebox.showwarning("Advertencia", "Cargue datos primero")
            return

        fig = plt.figure(figsize=(15, 10))
        gs = plt.GridSpec(2, 2)

        # Temperatura promedio por hora
        ax1 = fig.add_subplot(gs[0, :])
        datos_hora = self.analizador.datos.groupby('Hora')['Temp_interna_invernadero'].agg(['mean', 'std'])
        ax1.plot(datos_hora.index, datos_hora['mean'], 'b-')
        ax1.fill_between(datos_hora.index, 
                        datos_hora['mean'] - datos_hora['std'],
                        datos_hora['mean'] + datos_hora['std'],
                        alpha=0.3)
        ax1.set_title('Perfil de Temperatura Diaria')
        ax1.set_xlabel('Hora del día')
        ax1.set_ylabel('Temperatura (°C)')

        # Boxplot comparativo día/noche
        ax2 = fig.add_subplot(gs[1, 0])
        sns.boxplot(data=self.analizador.datos, x='Periodo', y='Temp_interna_invernadero', ax=ax2)
        ax2.set_title('Distribución de Temperaturas Día vs Noche')
        ax2.set_ylabel('Temperatura (°C)')

        # Humedad relativa día vs noche
        ax3 = fig.add_subplot(gs[1, 1])
        sns.boxplot(data=self.analizador.datos, x='Periodo', y='Hum_interna_invernadero', ax=ax3)
        ax3.set_title('Distribución de Humedad Día vs Noche')
        ax3.set_ylabel('Humedad Relativa (%)')

        plt.tight_layout()
        plt.show()

    def visualizar_analisis_psicrometrico(self):
        if not self.analizador:
            messagebox.showwarning("Advertencia", "Cargue datos primero")
            return

        fig = plt.figure(figsize=(15, 10))
        gs = plt.GridSpec(2, 2)

        # Diagrama de dispersión Temperatura vs Humedad
        ax1 = fig.add_subplot(gs[0, :])
        scatter = ax1.scatter(self.analizador.datos['Temp_interna_invernadero'],
                            self.analizador.datos['Hum_interna_invernadero'],
                            c=self.analizador.datos['h (kJ/kg_AS)'],
                            cmap='viridis')
        plt.colorbar(scatter, ax=ax1, label='Entalpía (kJ/kg_AS)')
        ax1.set_xlabel('Temperatura (°C)')
        ax1.set_ylabel('Humedad Relativa (%)')
        ax1.set_title('Diagrama Psicrométrico')

        # Histograma 2D
        ax2 = fig.add_subplot(gs[1, 0])
        plt.hist2d(self.analizador.datos['Temp_interna_invernadero'],
                  self.analizador.datos['Hum_interna_invernadero'],
                  bins=30, cmap='viridis')
        ax2.set_xlabel('Temperatura (°C)')
        ax2.set_ylabel('Humedad Relativa (%)')
        ax2.set_title('Distribución de Condiciones')

        # Serie temporal de punto de rocío
        ax3 = fig.add_subplot(gs[1, 1])
        ax3.plot(self.analizador.datos['Fecha_Hora'],
                self.analizador.datos['Tpr (°C)'],
                'b-', label='Punto de Rocío')
        ax3.plot(self.analizador.datos['Fecha_Hora'],
                self.analizador.datos['Temp_interna_invernadero'],
                'r-', label='Temperatura')
        ax3.set_xlabel('Fecha/Hora')
        ax3.set_ylabel('Temperatura (°C)')
        ax3.set_title('Temperatura vs Punto de Rocío')
        ax3.legend()

        plt.tight_layout()
        plt.show()

    def visualizar_tendencias_pronosticos(self):
        """Genera y muestra las tendencias y pronósticos en una ventana separada."""
        if not self.analizador:
            messagebox.showwarning("Advertencia", "Cargue datos primero")
            return
            
        try:
            # Crear una nueva ventana
            ventana = tk.Toplevel(self.root)
            ventana.title("Tendencias y Pronósticos")
            ventana.geometry("800x600")
            
            # Calcular tendencias usando medias móviles
            ventana_media = 24  # 24 puntos para media móvil
            datos = self.analizador.datos.copy()
            datos['MM_Temp'] = datos['Temp_interna_invernadero'].rolling(window=ventana_media).mean()
            datos['MM_Hum'] = datos['Hum_interna_invernadero'].rolling(window=ventana_media).mean()

            # Crear figura
            fig = plt.figure(figsize=(15, 10))
            gs = plt.GridSpec(2, 1)

            # Temperatura y tendencia
            ax1 = fig.add_subplot(gs[0])
            ax1.plot(datos['Fecha_Hora'], datos['Temp_interna_invernadero'],
                    'b-', alpha=0.5, label='Temperatura Real')
            ax1.plot(datos['Fecha_Hora'], datos['MM_Temp'],
                    'r-', label='Tendencia (Media Móvil)')
            ax1.set_title('Tendencia de Temperatura')
            ax1.set_xlabel('Fecha/Hora')
            ax1.set_ylabel('Temperatura (°C)')
            ax1.legend()

            # Humedad y tendencia
            ax2 = fig.add_subplot(gs[1])
            ax2.plot(datos['Fecha_Hora'], datos['Hum_interna_invernadero'],
                    'g-', alpha=0.5, label='Humedad Real')
            ax2.plot(datos['Fecha_Hora'], datos['MM_Hum'],
                    'r-', label='Tendencia (Media Móvil)')
            ax2.set_title('Tendencia de Humedad')
            ax2.set_xlabel('Fecha/Hora')
            ax2.set_ylabel('Humedad Relativa (%)')
            ax2.legend()

            plt.tight_layout()
            
            # Embeber el gráfico en la ventana
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            canvas = FigureCanvasTkAgg(fig, master=ventana)
            canvas.draw()
            canvas.get_tk_widget().pack(fill='both', expand=True)
            
            # Agregar barra de herramientas de navegación
            from matplotlib.backends.backend_tkagg import NavigationToolbar2Tk
            toolbar = NavigationToolbar2Tk(canvas, ventana)
            toolbar.update()
            
            self.actualizar_estado("Tendencias y pronósticos generados")
            
        except Exception as e:
            messagebox.showerror("Error", f"Error al generar tendencias y pronósticos: {str(e)}")
            self.actualizar_estado("Error al generar tendencias y pronósticos")
        
    def actualizar_estado(self, mensaje):
        """Actualiza el mensaje de estado en la interfaz."""
        self.estado_label.config(text=mensaje)

    def visualizar_carta_psicrometrica(self):
        """Genera y muestra la carta psicrométrica en una ventana separada."""
        if not self.analizador:
            messagebox.showwarning("Advertencia", "Cargue datos primero")
            return
            
        try:
            # Crear una nueva ventana
            ventana = tk.Toplevel(self.root)
            ventana.title("Carta Psicrométrica")
            ventana.geometry("800x600")
            
            # Crear el gráfico
            fig = self.analizador.visualizar_carta_psicrometrica()
            
            # Embeber el gráfico en la ventana
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            canvas = FigureCanvasTkAgg(fig, master=ventana)
            canvas.draw()
            canvas.get_tk_widget().pack(fill='both', expand=True)
            
            # Agregar barra de herramientas de navegación
            from matplotlib.backends.backend_tkagg import NavigationToolbar2Tk
            toolbar = NavigationToolbar2Tk(canvas, ventana)
            toolbar.update()
            
            self.actualizar_estado("Carta psicrométrica generada")
            
        except Exception as e:
            messagebox.showerror("Error", f"Error al generar la carta psicrométrica: {str(e)}")
            self.actualizar_estado("Error al generar carta psicrométrica")

    def visualizar_distribucion_espacial(self):
        """Genera y muestra la distribución espacial en una ventana separada."""
        if not self.analizador:
            messagebox.showwarning("Advertencia", "Cargue datos primero")
            return
            
        try:
            # Crear una nueva ventana
            ventana = tk.Toplevel(self.root)
            ventana.title("Distribución Espacial de Temperaturas")
            ventana.geometry("800x600")
            
            # Crear el gráfico
            fig = self.analizador.visualizar_distribucion_espacial()
            
            # Embeber el gráfico en la ventana
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            canvas = FigureCanvasTkAgg(fig, master=ventana)
            canvas.draw()
            canvas.get_tk_widget().pack(fill='both', expand=True)
            
            # Agregar barra de herramientas de navegación
            from matplotlib.backends.backend_tkagg import NavigationToolbar2Tk
            toolbar = NavigationToolbar2Tk(canvas, ventana)
            toolbar.update()
            
            self.actualizar_estado("Distribución espacial generada")
            
        except Exception as e:
            messagebox.showerror("Error", f"Error al generar la distribución espacial: {str(e)}")
            self.actualizar_estado("Error al generar distribución espacial")

class AnalisisInvernadero:
    def __init__(self, datos, calculadora=None):
        self.datos = datos.copy()
        self.calculadora = calculadora
        self.setup_data()
        self.setup_plotting_style()

    def visualizar_carta_psicrometrica(self):
        """Genera una carta psicrométrica."""
        fig = plt.figure(figsize=(15, 10))
        
        # Crear malla de temperaturas y humedades relativas
        T = np.linspace(0, 50, 100)
        HR = np.array([10, 20, 30, 40, 50, 60, 70, 80, 90, 100])
        
        # Calcular la presión atmosférica a 2240 msnm
        p_atm = self.calculadora.calcular_presion(2240)
        
        # Líneas de humedad relativa constante
        for hr in HR:
            w = []
            for t in T:
                try:
                    props = self.calculadora.calcular_propiedades_desde_Tbs_Hr(t, hr, p_atm)
                    w.append(props['W (kg_vp/kg_AS)'] * 1000)  # Convertir a g/kg
                except ValueError:
                    w.append(np.nan)
            plt.plot(T, w, 'k--', alpha=0.3, label=f'HR {hr}%' if hr % 20 == 0 else "")
        
        # Datos del invernadero
        scatter = plt.scatter(self.datos['Temp_interna_invernadero'],
                             self.datos['W (kg_vp/kg_AS)'] * 1000,  # Convertir a g/kg
                             c=mdates.date2num(self.datos['Fecha_Hora']),
                             cmap='viridis',
                             alpha=0.6)
        
        # Configuración del gráfico
        plt.colorbar(scatter, label='Tiempo')
        plt.xlabel('Temperatura de Bulbo Seco (°C)')
        plt.ylabel('Humedad Absoluta (g/kg)')
        plt.title('Carta Psicrométrica con Datos del Invernadero')
        plt.grid(True, alpha=0.3)
        plt.legend()
        
        return fig

    def visualizar_distribucion_espacial(self):
        """Genera una visualización 3D de la distribución espacial de temperaturas."""
        fig = plt.figure(figsize=(12, 8))
        ax = fig.add_subplot(111, projection='3d')
        
        # Definir puntos de medición
        puntos = {
            'S1_temp_sustrato': (0, 0, 0.1),     # Base
            'S2_temp_tallo': (0, 0, 0.5),        # Tallo
            'S3_temp_hoja': (0.3, 0, 1.0),       # Hoja
            'S4_temp_fruto': (0.2, 0.2, 0.8),    # Fruto
            'S5_temp_1m_altura': (0.5, 0.5, 1.0), # 1m
            'S6_temp_2m_altura': (0.5, 0.5, 2.0), # 2m
            'S7_temp_3_altura': (0.5, 0.5, 3.0)   # 3m
        }
        
        # Obtener temperaturas promedio
        temps_promedio = {sensor: self.datos[sensor].mean() for sensor in puntos.keys()}
        
        # Crear arrays para la visualización
        x = [coord[0] for coord in puntos.values()]
        y = [coord[1] for coord in puntos.values()]
        z = [coord[2] for coord in puntos.values()]
        temps = [temps_promedio[sensor] for sensor in puntos.keys()]
        
        # Graficar puntos
        scatter = ax.scatter(x, y, z, c=temps, 
                            cmap='coolwarm', 
                            s=100, 
                            alpha=0.6)
        
        # Agregar etiquetas
        for sensor, (x, y, z) in puntos.items():
            temp = temps_promedio[sensor]
            label = f'{sensor}\n{temp:.1f}°C'
            ax.text(x, y, z, label, fontsize=8)
        
        # Configuración del gráfico
        plt.colorbar(scatter, label='Temperatura (°C)')
        ax.set_xlabel('X (m)')
        ax.set_ylabel('Y (m)')
        ax.set_zlabel('Altura (m)')
        ax.set_title('Distribución Espacial de Temperaturas')
        
        # Ajustar los límites y la vista
        ax.set_xlim([-0.5, 1.5])
        ax.set_ylim([-0.5, 1.5])
        ax.set_zlim([0, 3.5])
        
        return fig

    def setup_data(self):
        """Prepara los datos para el análisis."""
        if not pd.api.types.is_datetime64_any_dtype(self.datos['Fecha_Hora']):
            self.datos['Fecha_Hora'] = pd.to_datetime(self.datos['Fecha_Hora'])
        
        # Agregar columnas de tiempo
        self.datos['Hora'] = self.datos['Fecha_Hora'].dt.hour
        self.datos['Es_Dia'] = self.datos['Hora'].between(6, 18)
        self.datos['Periodo'] = self.datos['Es_Dia'].map({True: 'Día', False: 'Noche'})
        
        # Calcular índices de estrés térmico
        self.calcular_indices_estres()

    def setup_plotting_style(self):
        """Configura el estilo global de las visualizaciones."""
        plt.style.use('default')
        colors = ['#2ecc71', '#e74c3c', '#3498db', '#f1c40f', '#9b59b6']
        plt.rcParams['axes.prop_cycle'] = plt.cycler(color=colors)
        plt.rcParams['figure.figsize'] = [12, 8]
        plt.rcParams['font.size'] = 10
        plt.rcParams['axes.labelsize'] = 12
        plt.rcParams['axes.titlesize'] = 14

    def calcular_indices_estres(self):
        """Calcula índices de estrés térmico para las plantas."""
        # Temperatura óptima para tomates
        temp_optima = 25
        
        # Índice de estrés por calor
        self.datos['Estres_Calor'] = np.where(
            self.datos['Temp_interna_invernadero'] > temp_optima,
            self.datos['Temp_interna_invernadero'] - temp_optima,
            0
        )
        
        # Índice de estrés por frío
        self.datos['Estres_Frio'] = np.where(
            self.datos['Temp_interna_invernadero'] < temp_optima,
            temp_optima - self.datos['Temp_interna_invernadero'],
            0
        )

    def analizar_perfil_vertical(self):
        """Análisis detallado del perfil vertical de temperatura."""
        fig = plt.figure(figsize=(15, 10))
        gs = plt.GridSpec(2, 2)
        
        # Perfil promedio
        ax1 = fig.add_subplot(gs[0, 0])
        alturas = [1, 2, 3]
        temps_dia = [
            self.datos[self.datos['Es_Dia']]['S5_temp_1m_altura'].mean(),
            self.datos[self.datos['Es_Dia']]['S6_temp_2m_altura'].mean(),
            self.datos[self.datos['Es_Dia']]['S7_temp_3_altura'].mean()
        ]
        temps_noche = [
            self.datos[~self.datos['Es_Dia']]['S5_temp_1m_altura'].mean(),
            self.datos[~self.datos['Es_Dia']]['S6_temp_2m_altura'].mean(),
            self.datos[~self.datos['Es_Dia']]['S7_temp_3_altura'].mean()
        ]
        
        ax1.plot(temps_dia, alturas, 'o-', label='Día')
        ax1.plot(temps_noche, alturas, 'o-', label='Noche')
        ax1.set_xlabel('Temperatura (°C)')
        ax1.set_ylabel('Altura (m)')
        ax1.set_title('Perfil Vertical Promedio')
        ax1.grid(True)
        ax1.legend()
        
        # Variación temporal
        ax2 = fig.add_subplot(gs[0, 1])
        for altura, sensor in zip(['1m', '2m', '3m'], 
                                ['S5_temp_1m_altura', 'S6_temp_2m_altura', 'S7_temp_3_altura']):
            ax2.plot(self.datos['Fecha_Hora'], self.datos[sensor], 
                    label=f'Altura {altura}')
        ax2.set_title('Variación Temporal por Altura')
        ax2.set_xlabel('Fecha/Hora')
        ax2.set_ylabel('Temperatura (°C)')
        ax2.legend()
        
        # Boxplot por altura y período
        ax3 = fig.add_subplot(gs[1, :])
        data_to_plot = []
        labels = []
        sensores = ['S5_temp_1m_altura', 'S6_temp_2m_altura', 'S7_temp_3_altura']
        nombres = ['1m', '2m', '3m']  # Nombres corregidos para las etiquetas
        
        for sensor, nombre in zip(sensores, nombres):
            for periodo in ['Día', 'Noche']:
                data = self.datos[self.datos['Periodo'] == periodo][sensor]
                data_to_plot.append(data)
                labels.append(f'{nombre} - {periodo}')
        
        ax3.boxplot(data_to_plot, labels=labels)
        ax3.set_title('Distribución de Temperaturas por Altura y Período')
        ax3.set_ylabel('Temperatura (°C)')
        plt.xticks(rotation=45)
        
        plt.tight_layout()
        return fig

    def analizar_temperaturas_planta(self):
        """Análisis de temperaturas en diferentes partes de la planta."""
        fig = plt.figure(figsize=(15, 10))
        gs = plt.GridSpec(2, 2)
        
        # Series temporales
        ax1 = fig.add_subplot(gs[0, :])
        partes_planta = {
            'S1_temp_sustrato': 'Sustrato',
            'S2_temp_tallo': 'Tallo',
            'S3_temp_hoja': 'Hoja',
            'S4_temp_fruto': 'Fruto'
        }
        
        for sensor, nombre in partes_planta.items():
            ax1.plot(self.datos['Fecha_Hora'], self.datos[sensor], 
                    label=nombre)
        ax1.set_title('Temperaturas por Parte de la Planta')
        ax1.set_xlabel('Fecha/Hora')
        ax1.set_ylabel('Temperatura (°C)')
        ax1.legend()
        
        # Boxplot comparativo
        ax2 = fig.add_subplot(gs[1, 0])
        sns.boxplot(data=self.datos[list(partes_planta.keys())], ax=ax2)
        ax2.set_xticklabels([partes_planta[col] for col in partes_planta.keys()],
                           rotation=45)
        ax2.set_title('Distribución de Temperaturas')
        ax2.set_ylabel('Temperatura (°C)')
        
        # Análisis de correlación entre partes
        ax3 = fig.add_subplot(gs[1, 1])
        corr = self.datos[list(partes_planta.keys())].corr()
        sns.heatmap(corr, annot=True, cmap='coolwarm', ax=ax3,
                   xticklabels=[partes_planta[col] for col in partes_planta.keys()],
                   yticklabels=[partes_planta[col] for col in partes_planta.keys()])
        ax3.set_title('Correlación entre Temperaturas')
        
        plt.tight_layout()
        return fig

    def analizar_condiciones_interno_externo(self):
        """Análisis de correlación entre condiciones internas y externas."""
        fig = plt.figure(figsize=(15, 10))
        gs = plt.GridSpec(2, 2)
        
        # Scatter temperatura
        ax1 = fig.add_subplot(gs[0, 0])
        ax1.scatter(self.datos['Temp_externa_invernadero'],
                   self.datos['Temp_interna_invernadero'])
        ax1.set_xlabel('Temperatura Externa (°C)')
        ax1.set_ylabel('Temperatura Interna (°C)')
        ax1.set_title('Correlación de Temperaturas')
        
        # Ajuste lineal para temperatura
        z = np.polyfit(self.datos['Temp_externa_invernadero'],
                      self.datos['Temp_interna_invernadero'], 1)
        p = np.poly1d(z)
        ax1.plot(self.datos['Temp_externa_invernadero'],
                p(self.datos['Temp_externa_invernadero']), "r--",
                alpha=0.8, label=f'R² = {np.corrcoef(self.datos["Temp_externa_invernadero"], self.datos["Temp_interna_invernadero"])[0,1]**2:.3f}')
        ax1.legend()
        
        # Scatter humedad
        ax2 = fig.add_subplot(gs[0, 1])
        ax2.scatter(self.datos['Hum_externa_invernadero'],
                   self.datos['Hum_interna_invernadero'])
        ax2.set_xlabel('Humedad Externa (%)')
        ax2.set_ylabel('Humedad Interna (%)')
        ax2.set_title('Correlación de Humedad')
        
        # Ajuste lineal para humedad
        z_hum = np.polyfit(self.datos['Hum_externa_invernadero'],
                          self.datos['Hum_interna_invernadero'], 1)
        p_hum = np.poly1d(z_hum)
        ax2.plot(self.datos['Hum_externa_invernadero'],
                p_hum(self.datos['Hum_externa_invernadero']), "r--",
                alpha=0.8, label=f'R² = {np.corrcoef(self.datos["Hum_externa_invernadero"], self.datos["Hum_interna_invernadero"])[0,1]**2:.3f}')
        ax2.legend()
        
        # Series temporales
        ax3 = fig.add_subplot(gs[1, :])
        ax3.plot(self.datos['Fecha_Hora'], self.datos['Temp_interna_invernadero'],
                label='Temp. Interna')
        ax3.plot(self.datos['Fecha_Hora'], self.datos['Temp_externa_invernadero'],
                label='Temp. Externa')
        ax3_twin = ax3.twinx()
        ax3_twin.plot(self.datos['Fecha_Hora'], self.datos['Hum_interna_invernadero'],
                     'g-', label='Hum. Interna')
        ax3_twin.plot(self.datos['Fecha_Hora'], self.datos['Hum_externa_invernadero'],
                     'y-', label='Hum. Externa')
        
        ax3.set_xlabel('Fecha/Hora')
        ax3.set_ylabel('Temperatura (°C)')
        ax3_twin.set_ylabel('Humedad (%)')
        ax3.legend(loc='upper left')
        ax3_twin.legend(loc='upper right')
        ax3.set_title('Series Temporales de Condiciones Internas y Externas')
        
        plt.tight_layout()
        return fig

    def analizar_estres_termico(self):
        """Análisis del estrés térmico en las plantas."""
        fig = plt.figure(figsize=(15, 10))
        gs = plt.GridSpec(2, 2)
        
        # Índices de estrés a lo largo del tiempo
        ax1 = fig.add_subplot(gs[0, :])
        ax1.plot(self.datos['Fecha_Hora'], self.datos['Estres_Calor'],
                'r-', label='Estrés por Calor')
        ax1.plot(self.datos['Fecha_Hora'], self.datos['Estres_Frio'],
                'b-', label='Estrés por Frío')
        ax1.set_title('Índices de Estrés Térmico')
        ax1.set_xlabel('Fecha/Hora')
        ax1.set_ylabel('Índice de Estrés (°C)')
        ax1.legend()
        
        # Histograma de temperaturas
        ax2 = fig.add_subplot(gs[1, 0])
        ax2.hist(self.datos['Temp_interna_invernadero'], bins=30)
        ax2.axvline(25, color='r', linestyle='--', label='Temp. Óptima')
        ax2.set_title('Distribución de Temperaturas')
        ax2.set_xlabel('Temperatura (°C)')
        ax2.set_ylabel('Frecuencia')
        ax2.legend()
        
        # Boxplot por período
        ax3 = fig.add_subplot(gs[1, 1])
        sns.boxplot(data=self.datos, x='Periodo', y='Temp_interna_invernadero', ax=ax3)
        ax3.axhline(25, color='r', linestyle='--', label='Temp. Óptima')
        ax3.set_title('Temperaturas por Período')
        ax3.set_ylabel('Temperatura (°C)')
        ax3.legend()
        
        plt.tight_layout()
        return fig

    def graficar_mapa_calor_3d(self):
        """Genera una visualización térmica 3D altamente visual del invernadero."""
        fig = plt.figure(figsize=(15, 10))
        ax = fig.add_subplot(111, projection='3d')
        
        # Crear una malla densa para el invernadero
        x = np.linspace(-1, 1, 50)
        y = np.linspace(-1, 1, 50)
        z = np.linspace(0, 3.5, 50)
        X, Y, Z = np.meshgrid(x, y, z)
        
        # Definir posiciones de sensores
        puntos = {
            'S1_temp_sustrato': (0, 0, 0.1),    # Sustrato
            'S2_temp_tallo': (0, 0, 0.5),       # Tallo
            'S3_temp_hoja': (0.2, 0, 1.0),      # Hoja
            'S4_temp_fruto': (0.1, 0.1, 0.8),   # Fruto
            'S5_temp_1m_altura': (0, 0, 1.0),   # 1m
            'S6_temp_2m_altura': (0, 0, 2.0),   # 2m
            'S7_temp_3_altura': (0, 0, 3.0)     # 3m
        }
        
        coords = np.array(list(puntos.values()))
        temps = np.array([self.datos[sensor].mean() for sensor in puntos.keys()])
        
        # Crear el volumen de temperatura interpolado
        points = coords
        grid_temps = griddata(points, temps, (X, Y, Z), method='linear')
        
        # Crear planos de corte en diferentes posiciones
        x_plane = 0
        y_plane = 0
        z_planes = [0.5, 1.5, 2.5]
        
        # Configurar colormaps
        cmap = plt.cm.RdYlBu_r  # Red-Yellow-Blue reversed (rojo=caliente, azul=frío)
        norm = plt.Normalize(temps.min()-1, temps.max()+1)
        
        # Dibujar planos de corte
        for z_plane in z_planes:
            z_idx = np.argmin(np.abs(z - z_plane))
            plane = grid_temps[:, :, z_idx]
            X_plane, Y_plane = np.meshgrid(x, y)
            Z_plane = np.full_like(X_plane, z_plane)
            surf = ax.plot_surface(X_plane, Y_plane, Z_plane,
                                 facecolors=cmap(norm(plane)),
                                 alpha=0.3)
        
        # Dibujar planos verticales
        y_idx = np.argmin(np.abs(y - y_plane))
        plane = grid_temps[:, y_idx, :]
        X_plane, Z_plane = np.meshgrid(x, z)
        Y_plane = np.full_like(X_plane, y_plane)
        surf = ax.plot_surface(X_plane, Y_plane, Z_plane,
                              facecolors=cmap(norm(plane)),
                              alpha=0.3)
        
        # Graficar puntos de sensores con esferas
        scatter = ax.scatter(coords[:, 0], coords[:, 1], coords[:, 2],
                            c=temps, cmap=cmap, norm=norm,
                            s=200, edgecolor='black', linewidth=1)
        
        # Añadir etiquetas con fondo semitransparente
        for (x, y, z), temp, name in zip(coords, temps, puntos.keys()):
            label = f'{name}\n{temp:.1f}°C'
            ax.text(x, y, z+0.1, label,
                    bbox=dict(facecolor='white', alpha=0.7, edgecolor='none'),
                    horizontalalignment='center', fontsize=8)
        
        # Agregar una barra de color clara
        cbar = plt.colorbar(scatter, ax=ax, pad=0.1)
        cbar.set_label('Temperatura (°C)', fontsize=12)
        
        # Configuración del gráfico
        ax.set_title('Distribución Térmica 3D del Invernadero', fontsize=14, pad=20)
        ax.set_xlabel('X (m)', fontsize=10, labelpad=10)
        ax.set_ylabel('Y (m)', fontsize=10, labelpad=10)
        ax.set_zlabel('Altura (m)', fontsize=10, labelpad=10)
        
        # Ajustar límites y vista
        ax.set_xlim([-1, 1])
        ax.set_ylim([-1, 1])
        ax.set_zlim([0, 3.5])
        ax.view_init(elev=25, azim=45)  # Vista isométrica
        
        # Agregar una cuadrícula más visible
        ax.grid(True, alpha=0.3)
        
        # Ajustar el espaciado
        plt.tight_layout()
        
        return fig

    def graficar_series_temporales(self):
        """Genera gráficos de series temporales."""
        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 15))
        
        # Temperaturas
        cols_temp = [col for col in self.datos.columns if 'temp' in col.lower()]
        for col in cols_temp:
            ax1.plot(self.datos['Fecha_Hora'], self.datos[col], label=col)
        ax1.set_title('Temperaturas')
        ax1.set_xlabel('Fecha/Hora')
        ax1.set_ylabel('Temperatura (°C)')
        ax1.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
        
        # Humedad
        ax2.plot(self.datos['Fecha_Hora'], self.datos['Hum_interna_invernadero'],
                label='Humedad Interna')
        ax2.plot(self.datos['Fecha_Hora'], self.datos['Hum_externa_invernadero'],
                label='Humedad Externa')
        ax2.set_title('Humedad Relativa')
        ax2.set_xlabel('Fecha/Hora')
        ax2.set_ylabel('Humedad (%)')
        ax2.legend()
        
        # Propiedades psicrométricas
        props = ['W (kg_vp/kg_AS)', 'h (kJ/kg_AS)', 'Tpr (°C)']
        for prop in props:
            ax3.plot(self.datos['Fecha_Hora'], self.datos[prop], label=prop)
        ax3.set_title('Propiedades Psicrométricas')
        ax3.set_xlabel('Fecha/Hora')
        ax3.set_ylabel('Valor')
        ax3.legend()
        
        plt.tight_layout()
        return fig

    def graficar_correlaciones(self):
        """Genera matriz de correlaciones."""
        # Seleccionar variables numéricas
        numeric_cols = [col for col in self.datos.columns 
                       if self.datos[col].dtype in ['float64', 'int64']]
        
        # Calcular correlaciones
        corr = self.datos[numeric_cols].corr()
        
        # Crear figura
        plt.figure(figsize=(15, 12))
        sns.heatmap(corr, annot=True, cmap='coolwarm', center=0, fmt='.2f')
        plt.title('Matriz de Correlaciones')
        plt.xticks(rotation=45, ha='right')
        plt.yticks(rotation=0)
        
        return plt.gcf()


if __name__ == "__main__":
    calculadora = CalculadoraPropiedades()
    interfaz = InterfazGraficaMejorada(calculadora)
    interfaz.iniciar_interfaz()
