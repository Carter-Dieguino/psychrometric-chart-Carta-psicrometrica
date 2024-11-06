import math
import tkinter as tk
from tkinter import filedialog, messagebox
import pandas as pd
from tkinter import ttk
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime

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
            # Fórmula para temperaturas <= 0°C
            C1 = -5.6745359e3
            C2 = 6.3925247e0
            C3 = -9.6778430e-3
            C4 = 6.2215701e-7
            C5 = 2.0747825e-9
            C6 = -9.4840240e-13
            C7 = 4.1635019e0
            ln_pws = (C1 / Tbs_K) + C2 + C3 * Tbs_K + C4 * Tbs_K ** 2 + C5 * Tbs_K ** 3 + C6 * Tbs_K ** 4 + C7 * math.log(Tbs_K)
        else:
            # Fórmula para temperaturas > 0°C
            C8 = -5.8002206e3
            C9 = 1.3914993e0
            C10 = -4.8640239e-2
            C11 = 4.1764768e-5
            C12 = -1.4452093e-8
            C13 = 6.5459673e0
            ln_pws = (C8 / Tbs_K) + C9 + C10 * Tbs_K + C11 * Tbs_K ** 2 + C12 * Tbs_K ** 3 + C13 * math.log(Tbs_K)

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

    def temperatura_punto_rocio_old(self, Tbs, Pv_Pa):
        if Pv_Pa <= 0:
            Pv_Pa = 0.00001
        Pv = Pv_Pa  # Mantener en Pa
        if -60 < Tbs < 0:
            return -60.450 + 7.0322 * math.log(Pv) + 0.3700 * (math.log(Pv)) ** 2
        elif 0 < Tbs < 70:
            return -35.957 - 1.8726 * math.log(Pv) + 1.1689 * (math.log(Pv)) ** 2
        return None

    def temperatura_punto_rocio(self, Pv_Pa):
        # Fórmula más precisa para calcular Tpr a partir de Pv
        Pv_hPa = Pv_Pa / 100  # Convertir Pa a hPa
        if Pv_hPa <= 0:
            Pv_hPa = 0.01
        gamma = math.log(Pv_hPa / 6.112)
        Tpr = (243.5 * gamma) / (17.67 - gamma)
        return Tpr

    def entalpia(self, Tbs, W):
        return 1.006 * Tbs + W * (2501 + 1.805 * Tbs)

    def calcular_tbh_desde_tbs_tpr(self, Tbs, Tpr, presionAtm_kPa):
        # Método iterativo para calcular Tbh a partir de Tbs y Tpr
        # Estimación inicial
        Tbh = Tbs - 1
        tolerancia = 1e-6
        max_iter = 100
        pvs_Tpr = self.calcular_pvs(Tpr)
        for i in range(max_iter):
            pvs_Tbh = self.calcular_pvs(Tbh)
            # Ecuación psicrométrica
            pHR = pvs_Tbh - 0.000662 * presionAtm_kPa * (Tbs - Tbh)
            error = pHR - pvs_Tpr
            if abs(error) < tolerancia:
                break
            # Derivada numérica
            delta = 1e-5
            f1 = self.ecuacion_psicrometrica(Tbh + delta, Tbs, presionAtm_kPa, pvs_Tpr)
            f0 = self.ecuacion_psicrometrica(Tbh, Tbs, presionAtm_kPa, pvs_Tpr)
            deriv = (f1 - f0) / delta
            if deriv == 0:
                deriv = tolerancia
            Tbh = Tbh - f0 / deriv
        return Tbh

    def ecuacion_psicrometrica(self, Tbh, Tbs, presionAtm_kPa, pvs_Tpr):
        pvs_Tbh = self.calcular_pvs(Tbh)
        pHR = pvs_Tbh - 0.000662 * presionAtm_kPa * (Tbs - Tbh)
        return pHR - pvs_Tpr

    def calcular_propiedades_desde_Tbs_Tpr(self, Tbs, Tpr, presionAt):
        pvs_Tbs = self.calcular_pvs(Tbs)
        pvs_Tpr = self.calcular_pvs(Tpr)
        Hr = (pvs_Tpr / pvs_Tbs) * 100
        Pv = pvs_Tpr
        W = self.razon_humedad(Pv * 1000, presionAt * 1000)  # Convertir kPa a Pa
        Ws = self.razon_humedad_saturada(pvs_Tbs * 1000, presionAt * 1000)
        Gsaturacion = self.grado_saturacion(W, Ws)
        Veh = self.volumen_especifico(Tbs, presionAt * 1000, W)
        h = self.entalpia(Tbs, W)
        Tbh = self.calcular_tbh_desde_tbs_tpr(Tbs, Tpr, presionAt)
        resultados = {
            "Tbs (°C)": Tbs,
            "Tbh (°C)": Tbh,
            "φ (%)": Hr,
            "Tpr (°C)": Tpr,
            "Pvs (kPa)": pvs_Tbs,
            "Pv (kPa)": Pv,
            "Ws (kg_vp/kg_AS)": Ws,
            "W (kg_vp/kg_AS)": W,
            "μ [G_sat] (%)": Gsaturacion,
            "Veh (m³/kg_AS)": Veh,
            "h (kJ/kg_AS)": h
        }
        return resultados

    def calcular_propiedades_desde_Tbs_Hr(self, Tbs, Hr, presionAt):
        if Hr <= 0 or Hr > 100:
            raise ValueError("La humedad relativa debe estar entre 0 y 100%.")
        pvs = self.calcular_pvs(Tbs)
        Pv = self.calcular_pv(Hr, pvs)
        W = self.razon_humedad(Pv * 1000, presionAt * 1000)  # Convertir kPa a Pa
        Ws = self.razon_humedad_saturada(pvs * 1000, presionAt * 1000)
        Gsaturacion = self.grado_saturacion(W, Ws)
        Veh = self.volumen_especifico(Tbs, presionAt * 1000, W)
        Tpr = self.temperatura_punto_rocio_old(Tbs, Pv * 1000)
        h = self.entalpia(Tbs, W)
        Tbh = self.bulbo_humedo(presionAt * 1000, Tbs, W)
        resultados = {
            "Tbs (°C)": Tbs,
            "Tbh (°C)": Tbh,
            "φ (%)": Hr,
            "Tpr (°C)": Tpr,
            "Pvs (kPa)": pvs,
            "Pv (kPa)": Pv,
            "Ws (kg_vp/kg_AS)": Ws,
            "W (kg_vp/kg_AS)": W,
            "μ [G_sat] (%)": Gsaturacion,
            "Veh (m³/kg_AS)": Veh,
            "h (kJ/kg_AS)": h
        }
        return resultados

    def calcular_propiedades_desde_Tbs_Tbh(self, Tbs, Tbh, presionAt):
        if Tbs < Tbh:
            raise ValueError("La temperatura de bulbo seco debe ser mayor o igual a la de bulbo húmedo.")
        Hr = self.calcular_humedad_relativa_desde_bulbo_humedo(Tbs, Tbh, presionAt)
        resultados = self.calcular_propiedades_desde_Tbs_Hr(Tbs, Hr, presionAt)
        # Reemplazamos Tbh con el valor proporcionado por el usuario
        resultados["Tbh (°C)"] = Tbh
        return resultados

    def bulbo_humedo(self, presionAt_Pa, Tbs, W, iter=100):
        Tbh = Tbs - 5  # Estimación inicial
        x0 = Tbh
        tolerancia = 1e-6

        for i in range(iter):
            pvs_Tbh = self.calcular_pvs(x0) * 1000  # Convertir kPa a Pa
            Ws_Tbh = self.razon_humedad_saturada(pvs_Tbh, presionAt_Pa)
            numerator = (2501 - 2.381 * x0) * Ws_Tbh - 1.006 * (Tbs - x0)
            denominator = 2501 + 1.805 * Tbs - 4.186 * x0
            W_calc = numerator / denominator
            error = W - W_calc
            if abs(error) < tolerancia:
                break
            # Derivada numérica
            delta = 1e-5
            f1 = self.funcion_bulbo_humedo(x0 + delta, presionAt_Pa, Tbs, W)
            f0 = self.funcion_bulbo_humedo(x0, presionAt_Pa, Tbs, W)
            deriv = (f1 - f0) / delta
            if deriv == 0:
                deriv = tolerancia
            x0 = x0 - f0 / deriv
        return x0

    def funcion_bulbo_humedo(self, Tbh, presionAt_Pa, Tbs, W):
        pvs_Tbh = self.calcular_pvs(Tbh) * 1000  # Convertir kPa a Pa
        Ws_Tbh = self.razon_humedad_saturada(pvs_Tbh, presionAt_Pa)
        numerator = (2501 - 2.381 * Tbh) * Ws_Tbh - 1.006 * (Tbs - Tbh)
        denominator = 2501 + 1.805 * Tbs - 4.186 * Tbh
        W_calc = numerator / denominator
        return W - W_calc

    def calcular_humedad_relativa_desde_bulbo_humedo(self, Tbs, Tbh, presionAt_kPa):
        pvs_Tbh = self.calcular_pvs(Tbh)
        pvs_Tbs = self.calcular_pvs(Tbs)
        pHR = pvs_Tbh - 0.000662 * presionAt_kPa * (Tbs - Tbh)
        if Tbs >= Tbh and pHR <= pvs_Tbs and pHR > 0:
            Hr = (pHR / pvs_Tbs) * 100
            return Hr
        else:
            raise ValueError("Error en los valores ingresados. Verifica que Tbs >= Tbh y que las temperaturas estén en rangos razonables.")









class InterfazGrafica:
    def __init__(self, calculadora):
        self.calculadora = calculadora
        self.root = None
        self.variables = {}
        self.inputs = {}
        self.check_vars = {}
        self.delay_timer = None
        self.calculo_automatico = False  # Ahora inicia en modo manual
        self.last_calculated_vars = {}  # Almacenar las últimas variables calculadas

    def iniciar_interfaz(self):
        self.root = tk.Tk()
        self.root.title("Calculadora de Propiedades Psicrométricas 2024 Diego Ramos")
        self.root.geometry("1400x700")

        # Estilos
        style = ttk.Style(self.root)
        style.theme_use('clam')
        style.configure('TButton', font=('Arial', 10))
        style.configure('Treeview.Heading', font=('Arial', 10, 'bold'))

        # Crear un contenedor principal
        self.main_frame = ttk.Frame(self.root)
        self.main_frame.pack(fill='both', expand=True)

        # Crear los frames
        self.frame_entradas = ttk.Frame(self.main_frame)
        self.frame_botones = ttk.Frame(self.main_frame)
        self.frame_leyenda = ttk.Frame(self.main_frame)
        self.frame_tabla = ttk.Frame(self.main_frame)

        # Empaquetar los frames verticalmente
        self.frame_entradas.pack(fill='x', padx=10, pady=5)
        self.frame_botones.pack(fill='x', padx=10, pady=5)
        self.frame_leyenda.pack(fill='both', padx=10, pady=5, expand=True)
        self.frame_tabla.pack(fill='both', expand=True)

        self.crear_entradas()
        self.crear_botones()
        self.crear_leyenda()
        self.crear_tabla()
        self.root.mainloop()

    def crear_entradas(self):
        frame = self.frame_entradas

        # Configurar el grid del frame_entradas
        for i in range(12):  # Hasta 12 columnas posibles
            frame.columnconfigure(i, weight=1)
        for i in range(4):  # Hasta 4 filas posibles
            frame.rowconfigure(i, weight=1)

        propiedades = ["Altura (m)", "Tbs (°C)", "Tbh (°C)", "φ (%)", "Tpr (°C)",
                       "Pvs (kPa)", "Pv (kPa)", "Ws (kg_vp/kg_AS)", "W (kg_vp/kg_AS)",
                       "μ [G_sat] (%)", "Veh (m³/kg_AS)", "h (kJ/kg_AS)"]

        input_props = ["Altura (m)", "Tbs (°C)", "Tbh (°C)", "φ (%)", "Tpr (°C)"]

        self.variables = {}
        self.inputs = {}
        self.check_vars = {}

        for i, prop in enumerate(propiedades):
            row = i // 4
            col = (i % 4) * 3

            if prop in input_props:
                var_check = tk.BooleanVar(value=False)
                check = ttk.Checkbutton(frame, variable=var_check)
                check.grid(row=row, column=col, sticky='e', padx=5, pady=5)
                self.check_vars[prop] = var_check
            else:
                var_check = None
                col -= 1  # Ajustar la columna para propiedades sin checkbox

            label = ttk.Label(frame, text=prop)
            label.grid(row=row, column=col + 1, sticky='e', padx=5, pady=5)

            var = tk.StringVar()
            entry = ttk.Entry(frame, textvariable=var)
            entry.grid(row=row, column=col + 2, sticky='we', padx=5, pady=5)
            var.trace_add('write', self.on_input_change)
            self.variables[prop] = var
            self.inputs[prop] = entry

        # Expandir las columnas de las entradas
        for i in range(len(propiedades)):
            col = (i % 4) * 3 + 2  # Columna del widget de entrada
            frame.columnconfigure(col, weight=1)

        # Agregar opción de cálculo automático o manual
        self.calculo_var = tk.StringVar(value="Manual")  # Ahora inicia en "Manual"
        frame_opciones = ttk.Frame(self.frame_entradas)
        frame_opciones.grid(row=4, column=0, columnspan=12, pady=5)

        ttk.Label(frame_opciones, text="Modo de Cálculo:").pack(side='left', padx=5)
        opciones = [("Automático", "Automatico"), ("Manual", "Manual")]
        for texto, valor in opciones:
            rb = ttk.Radiobutton(frame_opciones, text=texto, variable=self.calculo_var, value=valor, command=self.cambio_modo_calculo)
            rb.pack(side='left', padx=5)

        if self.calculo_var.get() == "Manual":
            self.boton_calcular = ttk.Button(frame_opciones, text="Calcular", command=self.calculate_properties)
            self.boton_calcular.pack(side='left', padx=5)

    def crear_botones(self):
        frame_botones = self.frame_botones

        boton_guardar = ttk.Button(frame_botones, text="Guardar Excel", command=self.guardar_excel)
        boton_guardar.pack(side='left', padx=5)

        boton_limpiar = ttk.Button(frame_botones, text="Limpiar", command=self.limpiar_entradas)
        boton_limpiar.pack(side='left', padx=5)

        boton_psicrometrica = ttk.Button(frame_botones, text="Graficar Psicrométrica", command=self.graficar_psicrometrica)
        boton_psicrometrica.pack(side='left', padx=5)

        boton_climograma = ttk.Button(frame_botones, text="Graficar Climograma o Temp&Humed", command=self.graficar_climograma)
        boton_climograma.pack(side='left', padx=5)

    def crear_leyenda(self):
        descripciones = {
            "Altura (m)": "Altura sobre el nivel del mar en metros.",
            "Tbs (°C)": "Temperatura de Bulbo Seco en grados Celsius.",
            "Tbh (°C)": "Temperatura de Bulbo Húmedo en grados Celsius.",
            "φ (%)": "Humedad Relativa en porcentaje.",
            "Tpr (°C)": "Temperatura de Punto de Rocío en grados Celsius.",
            "Pvs (kPa)": "Presión de vapor de saturación en kilopascales.",
            "Pv (kPa)": "Presión de vapor parcial en kilopascales.",
            "Ws (kg_vp/kg_AS)": "Razón de humedad de saturación.",
            "W (kg_vp/kg_AS)": "Razón de humedad actual.",
            "μ [G_sat] (%)": "Grado de saturación en porcentaje.",
            "Veh (m³/kg_AS)": "Volumen específico del aire húmedo.",
            "h (kJ/kg_AS)": "Entalpía del aire húmedo."
        }

        frame = self.frame_leyenda

        # Configurar el grid
        columns = 3
        rows = 4

        # Lista de variables y descripciones
        items = list(descripciones.items())

        for index, (var, desc) in enumerate(items):
            row = index % rows
            col = (index // rows) * 2  # *2 porque tenemos etiqueta de variable y descripción

            label_var = ttk.Label(frame, text=var, font=('Arial', 10, 'bold'))
            label_var.grid(row=row, column=col, sticky='e', padx=5, pady=2)

            label_desc = ttk.Label(frame, text=desc, wraplength=200)
            label_desc.grid(row=row, column=col + 1, sticky='w', padx=5, pady=2)

        # Expandir columnas y filas
        for i in range(columns * 2):
            frame.columnconfigure(i, weight=1)
        for i in range(rows):
            frame.rowconfigure(i, weight=1)

    def crear_tabla(self):
        columnas = ("Eliminar", "#", "Fecha", "Hora", "Altura (m)", "Tbs (°C)", "Tbh (°C)", "φ (%)",
                    "Tpr (°C)", "Pvs (kPa)", "Pv (kPa)", "Ws (kg_vp/kg_AS)",
                    "W (kg_vp/kg_AS)", "μ [G_sat] (%)", "Veh (m³/kg_AS)", "h (kJ/kg_AS)")
        self.tabla = ttk.Treeview(self.frame_tabla, columns=columnas, show='headings', selectmode='browse')
        for col in columnas:
            self.tabla.heading(col, text=col)
            self.tabla.column(col, anchor='center')

        # Añadir barras de desplazamiento
        scrollbar_vertical = ttk.Scrollbar(self.frame_tabla, orient="vertical", command=self.tabla.yview)
        scrollbar_vertical.pack(side='right', fill='y')

        scrollbar_horizontal = ttk.Scrollbar(self.frame_tabla, orient="horizontal", command=self.tabla.xview)
        scrollbar_horizontal.pack(side='bottom', fill='x')

        self.tabla.configure(yscrollcommand=scrollbar_vertical.set, xscrollcommand=scrollbar_horizontal.set)
        self.tabla.pack(fill='both', expand=True)

        # Añadir evento para doble clic
        self.tabla.bind("<Double-1>", self.on_double_click)

    def limpiar_entradas(self):
        # Limpiar los campos de entrada y desmarcar los checkboxes
        for prop in self.variables:
            self.variables[prop].set('')
        for prop in self.check_vars:
            self.check_vars[prop].set(False)
        # Resetear las variables de último cálculo
        self.last_calculated_vars = {}

    def cambio_modo_calculo(self):
        if self.calculo_var.get() == "Manual":
            self.calculo_automatico = False
            if not hasattr(self, 'boton_calcular'):
                self.boton_calcular = ttk.Button(self.root, text="Calcular", command=self.calculate_properties)
                self.boton_calcular.pack(pady=5)
        else:
            self.calculo_automatico = True
            if hasattr(self, 'boton_calcular'):
                self.boton_calcular.destroy()
                del self.boton_calcular

    def on_input_change(self, *args):
        # Seleccionar o deseleccionar el checkbox cuando el usuario modifica el campo
        for prop, var in self.variables.items():
            if prop in self.check_vars:
                current_value = var.get().strip()
                if current_value != '':
                    self.check_vars[prop].set(True)
                else:
                    self.check_vars[prop].set(False)
        if self.calculo_automatico:
            # Cancel any existing timer
            if self.delay_timer is not None:
                self.root.after_cancel(self.delay_timer)
            # Start a new timer
            self.delay_timer = self.root.after(5000, self.delayed_calculate_properties)  # 5 segundos

    def delayed_calculate_properties(self):
        self.delay_timer = None
        self.calculate_properties()

    def calculate_properties(self):
        # Limpiar variables
        provided_vars = {}
        input_props = ["Altura (m)", "Tbs (°C)", "Tbh (°C)", "φ (%)", "Tpr (°C)"]
        for prop in input_props:
            if prop in self.check_vars and self.check_vars[prop].get():
                value = self.variables[prop].get()
                if value.strip() != '':
                    try:
                        provided_vars[prop] = float(value)
                    except ValueError:
                        # Not a valid number
                        messagebox.showerror("Error", f"El valor ingresado en '{prop}' no es válido.")
                        return

        # Verificar si las variables han cambiado desde el último cálculo
        if provided_vars == self.last_calculated_vars:
            return  # No hay cambios, no se realiza el cálculo

        self.last_calculated_vars = provided_vars.copy()  # Actualizar las variables del último cálculo

        # Guardar el estado actual de las casillas de verificación
        selected_checks = {prop: var.get() for prop, var in self.check_vars.items()}

        # Necesitamos al menos Altura y dos variables más
        if "Altura (m)" in provided_vars:
            altura = provided_vars["Altura (m)"]
            known_props = [prop for prop in ["Tbs (°C)", "Tbh (°C)", "φ (%)", "Tpr (°C)"] if prop in provided_vars]

            if len(known_props) >= 2:
                # Realizar el cálculo
                Tbs = provided_vars.get("Tbs (°C)", None)
                Tbh = provided_vars.get("Tbh (°C)", None)
                Hr = provided_vars.get("φ (%)", None)
                Tpr = provided_vars.get("Tpr (°C)", None)

                presionAt = self.calculadora.calcular_presion(altura)

                try:
                    if Tbs is not None and Hr is not None:
                        # Calcular desde Tbs y Hr
                        resultados = self.calculadora.calcular_propiedades_desde_Tbs_Hr(Tbs, Hr, presionAt)
                    elif Tbs is not None and Tbh is not None:
                        # Calcular desde Tbs y Tbh
                        resultados = self.calculadora.calcular_propiedades_desde_Tbs_Tbh(Tbs, Tbh, presionAt)
                    elif Tbs is not None and Tpr is not None:
                        # Calcular desde Tbs y Tpr
                        resultados = self.calculadora.calcular_propiedades_desde_Tbs_Tpr(Tbs, Tpr, presionAt)
                    else:
                        messagebox.showerror("Error", "No se pudo calcular con las variables proporcionadas.")
                        return

                    # Actualizar las variables (solo las que no fueron proporcionadas)
                    for prop, value in resultados.items():
                        if prop in self.variables and prop not in provided_vars:
                            self.variables[prop].set(round(value, 6))  # Mayor precisión

                    # Restaurar el estado de las casillas de verificación
                    for prop, var in self.check_vars.items():
                        var.set(selected_checks[prop])

                    # Agregar a la tabla
                    self.agregar_a_tabla(altura, resultados)

                except Exception as e:
                    messagebox.showerror("Error", f"Ocurrió un error al calcular: {e}")

            else:
                # No hay suficientes variables
                messagebox.showwarning("Advertencia", "Debe seleccionar y proporcionar al menos dos variables psicrométricas además de la altura.")
        else:
            # Falta la altura
            messagebox.showwarning("Advertencia", "Debe ingresar y seleccionar la Altura y al menos dos variables psicrométricas.")

    def agregar_a_tabla(self, altura, resultados):
        idx = len(self.tabla.get_children()) + 1
        fecha_actual = datetime.now().strftime('%Y-%m-%d')
        hora_actual = datetime.now().strftime('%H:%M:%S')
        valores = ("Eliminar", idx, fecha_actual, hora_actual, altura,
                   resultados.get("Tbs (°C)", ""),
                   resultados.get("Tbh (°C)", ""),
                   resultados.get("φ (%)", ""),
                   resultados.get("Tpr (°C)", ""),
                   resultados.get("Pvs (kPa)", ""),
                   resultados.get("Pv (kPa)", ""),
                   resultados.get("Ws (kg_vp/kg_AS)", ""),
                   resultados.get("W (kg_vp/kg_AS)", ""),
                   resultados.get("μ [G_sat] (%)", ""),
                   resultados.get("Veh (m³/kg_AS)", ""),
                   resultados.get("h (kJ/kg_AS)", ""))
        self.tabla.insert("", "end", values=valores)

    def guardar_excel(self):
        try:
            ruta_guardado = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel Files", "*.xlsx")], parent=self.root)
            if ruta_guardado:
                datos_guardar = [self.tabla.item(item)['values'][1:] for item in self.tabla.get_children()]
                columnas = ["#", "Fecha", "Hora", "Altura (m)", "Tbs (°C)", "Tbh (°C)", "φ (%)",
                            "Tpr (°C)", "Pvs (kPa)", "Pv (kPa)", "Ws (kg_vp/kg_AS)",
                            "W (kg_vp/kg_AS)", "μ [G_sat] (%)", "Veh (m³/kg_AS)", "h (kJ/kg_AS)"]
                df = pd.DataFrame(datos_guardar, columns=columnas)
                df.to_excel(ruta_guardado, index=False)
                messagebox.showinfo("Éxito", f"Los datos se han guardado correctamente en '{ruta_guardado}'.")
            else:
                messagebox.showwarning("Advertencia", "No se ha seleccionado una ubicación para guardar el archivo.")
        except Exception as e:
            messagebox.showerror("Error", f"Ocurrió un error al guardar el archivo: {e}")

    def on_double_click(self, event):
        # Obtener item y columna seleccionados
        item = self.tabla.identify_row(event.y)
        column = self.tabla.identify_column(event.x)
        if item:
            col_index = int(column.replace('#', '')) - 1  # Índice de columna
            if col_index == 0:
                # Si es la columna 'Eliminar', activar función de eliminar
                respuesta = messagebox.askyesno("Confirmación", "¿Desea eliminar esta fila?")
                if respuesta:
                    self.tabla.delete(item)
                    self.actualizar_indices_tabla()
            else:
                # Si es cualquier otra columna, copiar contenido al portapapeles
                valor = self.tabla.item(item, 'values')[col_index]
                self.root.clipboard_clear()
                self.root.clipboard_append(str(valor))
                messagebox.showinfo("Copiado", f"Se copió al portapapeles: {valor}")

    def actualizar_indices_tabla(self):
        # Actualizar los índices de la tabla después de eliminar una fila
        for idx, item in enumerate(self.tabla.get_children()):
            valores = self.tabla.item(item, 'values')
            nuevos_valores = (valores[0], idx + 1) + valores[2:]
            self.tabla.item(item, values=nuevos_valores)
            
    def graficar_psicrometrica(self):
        try:
            # Verificar que haya datos en la tabla
            datos_tabla = [self.tabla.item(item)['values'] for item in self.tabla.get_children()]
            if not datos_tabla:
                raise ValueError("No hay datos en la tabla para graficar.")

            # Obtener rangos de Tbs y W basados en los datos
            Tbs_min = min(float(row[5]) for row in datos_tabla if row[5] != '')
            Tbs_max = max(float(row[5]) for row in datos_tabla if row[5] != '')
            Tbs_range = np.linspace(Tbs_min - 5, Tbs_max + 5, 200)

            # Usar la presión atmosférica correspondiente a la altura promedio de los datos
            alturas = [float(row[4]) for row in datos_tabla if row[4] != '']
            if alturas:
                altura_promedio = sum(alturas) / len(alturas)
            else:
                altura_promedio = 0
            presionAt = self.calculadora.calcular_presion(altura_promedio)

            fig, ax = plt.subplots(figsize=(12, 8))

            Hr_values = set()
            Tbh_values = set()
            Tpr_values = set()
            h_values = set()
            if datos_tabla:
                T_data = []
                W_data = []
                for data_row in datos_tabla:
                    if data_row[5] != '' and data_row[12] != '':
                        T = float(data_row[5])  # Tbs
                        W = float(data_row[12])  # W
                        T_data.append(T)
                        W_data.append(W)
                        Hr = float(data_row[7])  # φ (%)
                        Tbh = float(data_row[6])  # Tbh
                        Tpr = float(data_row[8])  # Tpr
                        h = float(data_row[15])  # h
                        Hr_values.add(Hr)
                        Tbh_values.add(Tbh)
                        Tpr_values.add(Tpr)
                        h_values.add(h)
                # Dibujar los puntos una sola vez
                ax.scatter(T_data, W_data, color='black', marker='o', label='Datos Ingresados')

            # Dibujar líneas de humedad relativa constante
            Hr_values.update([10.0, 100.0])  # Añadir 10% y 100% como referencia
            for Hr in Hr_values:
                W_Hr = []
                for T in Tbs_range:
                    pvs = self.calculadora.calcular_pvs(T)
                    Pv = (Hr / 100) * pvs
                    W_point = self.calculadora.razon_humedad(Pv * 1000, presionAt * 1000)
                    W_Hr.append(W_point)
                ax.plot(Tbs_range, W_Hr, label=f'HR {Hr:.2f}%')

            # Dibujar líneas de entalpía constante
            for h in h_values:
                W_h = []
                for T in Tbs_range:
                    W_point = (h - 1.006 * T) / (2501 + 1.86 * T)
                    W_h.append(W_point)
                ax.plot(Tbs_range, W_h, linestyle='--', color='red', linewidth=0.5)
                ax.text(Tbs_range[-1], W_h[-1], f'{h:.2f} kJ/kg', color='red', fontsize=8)

            # Dibujar líneas de temperatura de bulbo húmedo constante
            for Tbh in Tbh_values:
                W_Tbh = []
                for T in Tbs_range:
                    if T >= Tbh:
                        pvs_Tbh = self.calculadora.calcular_pvs(Tbh) * 1000  # Convertir kPa a Pa
                        Ws_Tbh = self.calculadora.razon_humedad_saturada(pvs_Tbh, presionAt * 1000)
                        numerator = (2501 - 2.381 * Tbh) * Ws_Tbh - 1.006 * (T - Tbh)
                        denominator = 2501 + 1.805 * T - 4.186 * Tbh
                        W_point = numerator / denominator
                        W_Tbh.append(W_point)
                    else:
                        W_Tbh.append(None)
                ax.plot(Tbs_range, W_Tbh, linestyle='-.', color='green', linewidth=0.5)
                # Mover el texto al lado izquierdo
                for idx, W_val in enumerate(W_Tbh):
                    if W_val is not None:
                        ax.text(Tbs_range[idx], W_val, f'Tbh {Tbh:.2f}°C', color='green', fontsize=8, verticalalignment='bottom')
                        break

            # Dibujar líneas de temperatura de punto de rocío constante
            for Tpr in Tpr_values:
                W_Tpr = []
                for T in Tbs_range:
                    if T >= Tpr:
                        pvs_Tpr = self.calculadora.calcular_pvs(Tpr)
                        Pv = pvs_Tpr
                        W_point = self.calculadora.razon_humedad(Pv * 1000, presionAt * 1000)
                        W_Tpr.append(W_point)
                    else:
                        W_Tpr.append(None)
                ax.plot(Tbs_range, W_Tpr, linestyle=':', color='blue', linewidth=0.5)
                # Ajustar la posición de la etiqueta para evitar superposición
                label_pos = Tbs_range[-1] - 5  # Mover un poco a la izquierda
                ax.text(label_pos, W_Tpr[-1], f'Tpr {Tpr:.2f}°C', color='blue', fontsize=8)

            # Configurar ejes
            ax.set_xlabel('Temperatura de Bulbo Seco Tbs (°C)')
            ax.set_ylabel('Razón de Humedad W (kg_vp/kg_AS)')
            ax.set_title('Carta Psicrométrica')
            ax.grid(True)
            ax.legend()
            plt.tight_layout()
            plt.show()
        except Exception as e:
            messagebox.showerror("Error", f"Error al generar el gráfico psicrométrico: {e}")

    def graficar_climograma(self):
        try:
            datos_tabla = [self.tabla.item(item)['values'] for item in self.tabla.get_children()]
            if not datos_tabla:
                raise ValueError("No hay datos en la tabla para graficar.")

            fechas = [datetime.strptime(row[2] + ' ' + row[3], '%Y-%m-%d %H:%M:%S') for row in datos_tabla]
            Tbs_list = [float(row[5]) for row in datos_tabla if row[5] != '']
            Hr_list = [float(row[7]) for row in datos_tabla if row[7] != '']

            fig, ax1 = plt.subplots(figsize=(14, 8))
            ax1.set_xlabel("Fecha y Hora")
            ax1.set_ylabel("Temperatura (°C)", color="tab:red")
            ax1.plot(fechas, Tbs_list, color="red", marker="o", linestyle="-", label="Tbs (°C)", markersize=3)
            ax1.tick_params(axis="y", labelcolor="tab:red")

            ax2 = ax1.twinx()
            ax2.set_ylabel("Humedad Relativa (%)", color="tab:blue")
            ax2.plot(fechas, Hr_list, color="blue", marker="o", linestyle="-", label="φ (%)", markersize=3)
            ax2.tick_params(axis="y", labelcolor="tab:blue")

            fig.autofmt_xdate()
            ax1.legend(loc='upper left')
            ax2.legend(loc='upper right')
            plt.title("Dependencia de la humedad relativa en función de la temperatura")
            plt.tight_layout()
            plt.show()
        except Exception as e:
            messagebox.showerror("Error", f"Error al generar el climograma: {e}")

if __name__ == "__main__":
    calculadora = CalculadoraPropiedades()
    interfaz = InterfazGrafica(calculadora)
    interfaz.iniciar_interfaz()
