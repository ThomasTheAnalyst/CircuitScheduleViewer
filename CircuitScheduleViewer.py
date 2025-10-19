# @title Motta Plotter
"""
# Motta Plotter

Motta Plotter is a Python tool (designed for Google Colab or Jupyter)
to visualize the behavior and configuration of 'Clickiemota' devices via the Clickie API.

Its main functions are:
1.  **Fetch Configuration:** Connects to the Clickie API to retrieve the
    active JSON configuration for a specified device.
2.  **Parse & Plot Behavior:** Interprets the JSON schedule and plots the
    *actual* ON/OFF state of each relay for a selected date range.
3.  **Plot Configuration:** Generates a second chart showing the *programmed*
    weekly schedule for each relay.
4.  **Generate Alerts:** Compares actual behavior against the schedule and
    prints alerts for discrepancies.
5.  **Integrate with G-Suite:** Includes functions to upload the generated
    plot to a specific Google Drive folder and log the action as a "ticket"
    in a specific Google Sheet.

**NOTE FOR REPOSITORY USE:**
This script is ready to run, but you must fill in the placeholder
variables in the '--- USER CONFIGURATION ---' section below.
These include API credentials, client/company IDs, and G-Suite IDs.
"""

import requests
import json
import ipywidgets as widgets
from IPython.display import display, clear_output
import matplotlib.pyplot as plt
import matplotlib.cm as cm
import numpy as np
from datetime import datetime, timedelta
import pandas as pd
import os

# --- INTEGRACIÓN CON GOOGLE SHEETS Y DRIVE ---
# (Librerías mantenidas para la funcionalidad de tickets)
import gspread
from google.auth import default
from google.colab import auth
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import google.auth.transport.requests

# --- CONFIGURACIÓN DE USUARIO (REEMPLAZAR PLACEHOLDERS) ---

# Credenciales de la API de Clickie
USERNAME = "your-email@clickie.io" # <--- PLACEHOLDER
PASSWORD = "Your-API-Password"   # <--- PLACEHOLDER

# ID de cuenta para la API v4 (el '33' en el código original)
CLICKIE_V4_API_ACCOUNT_ID = "33" # <--- PLACEHOLDER (Ajustar si es necesario)

# Configuración de empresas/clientes
# Reemplaza con los clientes y IDs reales que usas.
APP_CONFIG = {
    "Client A": {"companyId": 111, "clickiemotaModel": 318}, # <--- PLACEHOLDER
    "Client B": {"companyId": 222, "clickiemotaModel": 318}, # <--- PLACEHOLDER
    "Client C": {"companyId": 333, "clickiemotaModel": 318}, # <--- PLACEHOLDER
    "Internal": {"companyId": 444, "clickiemotaModel": 318}, # <--- PLACEHOLDER
}

# Configuración de Google Drive y Sheets para la bitácora
GOOGLE_DRIVE_PARENT_FOLDER = "Your_Parent_Folder_Name" # <--- PLACEHOLDER (Ej: "Colbún")
GOOGLE_DRIVE_CHILD_FOLDER = "Your_Child_Folder_Name"   # <--- PLACEHOLDER (Ej: "Tickets Colbún")
GOOGLE_SHEET_ID = "YOUR_GOOGLE_SHEET_ID_HERE"          # <--- PLACEHOLDER (Ej: "1UgoygciTkeAOOrEntfY3lGQrOp3Eqp-6Whi9KDjI01U")
GOOGLE_SHEET_NAME = "Your_Sheet_Tab_Name"              # <--- PLACEHOLDER (Ej: "Historial Tickets")

# URL del sistema de tickets (para el hipervínculo en el Sheet)
SUPPORT_TICKET_URL_PREFIX = "http://your.support-system.com/a/tickets/" # <--- PLACEHOLDER (Ej: "http://soporte.efizity.com/a/tickets/")

# --- Variables globales auxiliares ---
building_map = {}
device_map = {}
token_global = None
headers_global = None
company_id_global = None
clickiemota_model_global = None
fig_global = None # <--- Variable para guardar el gráfico

# --- Obtener token ---
def obtener_token():
    url = "https://api.clickie.io/v1/public/auth"
    data = {"username": USERNAME, "password": PASSWORD}
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    r = requests.post(url, data=data, headers=headers)
    r.raise_for_status()
    token = r.json().get("data", {}).get("Token")
    if not token:
        raise ValueError("No se pudo obtener token")
    return token

# --- Widgets ---
# (Se mantienen los widgets originales)
empresa_dropdown = widgets.Dropdown(options=list(APP_CONFIG.keys()), description='Empresa:', value=list(APP_CONFIG.keys())[0])
sucursal_dropdown = widgets.Combobox(options=[], description='Sucursal:', ensure_option=True, placeholder='Escribe para filtrar...')
clickiemota_dropdown = widgets.Dropdown(options=[], description='Clickiemota:')
start_date_picker = widgets.DatePicker(description='Fecha inicio:', disabled=False)
end_date_picker = widgets.DatePicker(description='Fecha fin:', disabled=False)
output = widgets.Output()

# --- WIDGETS PARA BITÁCORA ---
ticket_input = widgets.Text(description='N° Ticket:', placeholder='Ej: 12345')
tipo_extension_dropdown = widgets.Dropdown(options=['Extensión Iluminación', 'Extensión Clima', 'Extensión Iluminación y Clima'], description='Tipo:', value='Extensión Iluminación')

# --- Cargar sucursales ---
def cargar_buildings(change):
    global building_map, token_global, headers_global, company_id_global, clickiemota_model_global
    with output:
        try:
            config = APP_CONFIG[empresa_dropdown.value]
            company_id_global = config["companyId"]
            clickiemota_model_global = config["clickiemotaModel"]
            token_global = obtener_token()
            headers_global = {"Authorization": token_global, "Content-Type": "application/json"}
            url = f"https://api.clickie.io/v1/companies/{company_id_global}/buildings"
            r = requests.get(url, headers=headers_global)
            r.raise_for_status()
            buildings = r.json()["data"]
            building_map = {b["building_name"]: b["id_building"] for b in buildings}
            sucursal_dropdown.options = list(building_map.keys())
            sucursal_dropdown.value = ""
        except Exception as e:
            clear_output()
            print(f"❌ Error al cargar sucursales (verifica credenciales y APP_CONFIG): {e}")


# --- Cargar Clickiemotas ---
def cargar_clickiemotas(change):
    global device_map
    if not sucursal_dropdown.value or sucursal_dropdown.value not in building_map:
        device_map = {}; clickiemota_dropdown.options = []; return
    building_id = building_map[sucursal_dropdown.value]
    url = f"https://api.clickie.io/v1/companies/{company_id_global}/devices"
    r = requests.get(url, headers=headers_global)
    r.raise_for_status()
    devices = r.json()["data"]
    filtered = [d for d in devices if d["id_building"] == building_id and d["id_device_model"] == clickiemota_model_global]
    device_map = {(d.get("setup_name") or d["device_identifier"]): d["device_identifier"] for d in filtered}
    clickiemota_dropdown.options = list(device_map.keys())
    if device_map: clickiemota_dropdown.value = list(device_map.keys())[0]

# --- Mostrar, guardar temporalmente y visualizar JSON ---
def mostrar_y_visualizar_json(b):
    global fig_global
    with output:
        clear_output()
        if not all([clickiemota_dropdown.value, start_date_picker.value, end_date_picker.value]):
            print("Selecciona una Clickiemota y ambas fechas."); return

        try:
            headers_api = {"Authorization": token_global, "Account": CLICKIE_V4_API_ACCOUNT_ID} # <--- Se usa el placeholder
            device_id = device_map[clickiemota_dropdown.value].replace("CMWS", "")
            url = f"https://v4.api.clickie.io/clickiemotas/{device_id}/configurations/active"
            r = requests.get(url, headers=headers_api)

            if r.status_code != 200:
                print(f"❌ Error al obtener JSON (status {r.status_code}):\n{r.text}"); return

            data = r.json()
            config_str = data.get("data", {}).get("config")
            if not config_str:
                print("❌ La respuesta no contiene la clave 'data' o 'config'.\n", data); return

            config_data = json.loads(config_str)
            temp_filename = "temp_config.json"
            with open(temp_filename, "w") as f: json.dump(config_data, f, indent=2)

            print("Configuración descargada. Graficando...")

            start_date_for_plot = start_date_picker.value - timedelta(days=1)
            end_date_for_plot = end_date_picker.value + timedelta(days=1)

            print(f"Rango del gráfico (extendido): {start_date_for_plot.strftime('%d-%m-%Y')} al {end_date_for_plot.strftime('%d-%m-%Y')}")

            fig_global = visualizar_json(
                temp_filename,
                start_date_for_plot.strftime('%d-%m-%Y'),
                end_date_for_plot.strftime('%d-%m-%Y')
            )
            os.remove(temp_filename)
        except Exception as e:
            print(f"❌ Error al interpretar JSON: {e}\n{r.text}")

# --- FUNCIÓN PARA VISUALIZAR Y GRAFICAR ---
# (Esta función es lógica pura, no contiene datos sensibles y se deja intacta)
def visualizar_json(json_file, start_date, end_date):
    with open(json_file, 'r', encoding='utf-8') as f: data = json.load(f)
    if isinstance(data, list): data = data[0]
    config = data.get('config', data)
    relay_control = config['lambda_functions']['GG_relay_control']
    channel_schedules = relay_control['channel_schedules']
    global_special_days = relay_control['special_days']

    def get_relay_channels(relay_cfg): return set(relay_cfg.get('channel_addresses', []) + relay_cfg.get('registers', []))
    def normalize_date_str(date_str): d, m = [int(x) for x in date_str.replace('-', ' ').replace('/', ' ').split()]; return f"{d:02d}-{m:02d}"
    def time_to_seconds(t): h, m, s = map(int, t.split(':')); return h * 3600 + m * 60 + s

    def get_special_config_for_day(device, relay, date_str):
        device_special_days = device.get('special_days', {})
        config_x_relay = device['config_x_relay']
        date_str_norm = normalize_date_str(date_str)
        special_group = next((group for group, days in global_special_days.items() if date_str_norm in [normalize_date_str(d) for d in days]), None)
        if not special_group: return None
        for special_cfg in device_special_days.values():
            if special_group in special_cfg['day_groups']:
                relay_cfg = special_cfg['config_x_relay'].get(relay)
                if relay_cfg: return relay_cfg
                relay_channels = get_relay_channels(config_x_relay[relay])
                for special_group_cfg in special_cfg['config_x_relay'].values():
                    if relay_channels & get_relay_channels(special_group_cfg): return special_group_cfg
        return None

    any_ww_device = any(d.get('device_type', '').startswith('WW-') for d in relay_control['devices'].values())

    def get_on_periods(relay_cfg, weekday_num):
        config_type = relay_cfg.get('config')
        if config_type == 'manual_apagado': return [["00:00:00", "23:59:59"]]
        elif config_type == 'manual_encendido': return [] if not any_ww_device else [["00:00:00", "23:59:59"]]
        elif config_type == 'automatico':
            sched_name = relay_cfg.get('schedule')
            sched = channel_schedules.get(sched_name, {})
            for group in sched.values():
                if isinstance(group, dict):
                    if weekday_num in group.get('days', []):
                        on_periods = group.get('on') or (group.get('status', {}).get('on') if 'status' in group else None)
                        return on_periods if on_periods is not None else [["00:00:00", "23:59:59"]]
                elif isinstance(group, list): return group
            if 'on' in sched: return sched['on']
            if 'status' in sched and 'on' in sched['status']: return sched['status']['on']
            if isinstance(sched, list): return sched
        return [["00:00:00", "23:59:59"]]

    def invert_periods(periods):
        if not periods: return [[0, 86400]]
        periods_sec = sorted([[time_to_seconds(p[0]), time_to_seconds(p[1])] for p in periods if len(p) == 2])
        result, last_end = [], 0
        for start, end in periods_sec:
            if start > last_end: result.append([last_end, start])
            last_end = max(last_end, end)
        if last_end < 86400: result.append([last_end, 86400])
        return result

    start_dt = datetime.strptime(start_date, '%d-%m-%Y'); end_dt = datetime.strptime(end_date, '%d-%m-%Y')
    date_list = [start_dt + timedelta(days=i) for i in range((end_dt - start_dt).days + 1)]
    plot_data, relay_labels = [], []
    for device_name, device in relay_control['devices'].items():
        for relay in device['config_x_relay'].keys():
            relay_label = f"{device_name}:{relay}"
            if relay_label not in relay_labels: relay_labels.append(relay_label)
            for date in date_list:
                relay_cfg = get_special_config_for_day(device, relay, f"{date.day}-{date.month}") or device['config_x_relay'].get(relay)
                periods = get_on_periods(relay_cfg, date.isoweekday())
                config_type = relay_cfg.get('config')
                on_intervals = []
                if any_ww_device:
                    if periods != [] and config_type != 'manual_apagado':
                        if periods == [["00:00:00", "23:59:59"]] or config_type == 'manual_encendido': on_intervals.append([0, 86400])
                        else: on_intervals.extend([[time_to_seconds(p[0]), time_to_seconds(p[1])] for p in periods if len(p) == 2 and time_to_seconds(p[0]) < time_to_seconds(p[1])])
                else:
                    if periods == []: on_intervals.append([0, 86400])
                    elif periods != [["00:00:00", "23:59:59"]] and config_type != 'manual_apagado': on_intervals.extend(invert_periods(periods))
                for start_sec, end_sec in on_intervals:
                    plot_data.append({'relay': relay_label, 'date': date.strftime('%d-%m-%Y'), 'start': start_sec, 'end': end_sec})

    unique_days = sorted(list(set(d['date'] for d in plot_data) | set(d.strftime('%d-%m-%Y') for d in date_list)), key=lambda x: datetime.strptime(x, '%d-%m-%Y'), reverse=True)

    # --- ALERTS ---
    def sec_to_hhmm(sec):
        if sec <= 0: return "00:00"
        if sec >= 24*3600: return "23:59"
        h = sec // 3600; m = (sec % 3600) // 60
        return f"{h:02d}:{m:02d}"

    def subtract_periods(expected, actual):
        result = []
        for exp_start, exp_end in expected:
            uncovered = []; cur = exp_start
            for act_start, act_end in sorted(actual):
                if act_end <= cur: continue
                if act_start > cur:
                    uncovered.append((cur, min(act_start, exp_end)))
                cur = max(cur, act_end)
                if cur >= exp_end: break
            if cur < exp_end:
                uncovered.append((cur, exp_end))
            result.extend(uncovered)
        return result

    def invert_periods_for_alerts(periods_list):
        if not periods_list: return [[0, 24*3600]]
        periods_sec = []
        for p in periods_list:
            if len(p) == 2:
                h1, m1, s1 = map(int, p[0].split(":")); h2, m2, s2 = map(int, p[1].split(":"))
                start_sec = h1 * 3600 + m1 * 60 + s1; end_sec = h2 * 3600 + m2 * 60 + s2
                periods_sec.append([start_sec, end_sec])
        periods_sec = sorted(periods_sec)
        result = []; last_end = 0
        for start, end in periods_sec:
            if start > last_end: result.append((last_end, start))
            last_end = max(last_end, end)
        if last_end < 24*3600: result.append((last_end, 24*3600))
        return result

    alerts = []
    for relay_label in relay_labels:
        try: device_name, relay_name = relay_label.split(":", 1)
        except ValueError: continue
        device = relay_control['devices'].get(device_name)
        if not device: continue
        config_x_relay = device.get('config_x_relay', {}); relay_cfg = config_x_relay.get(relay_name)
        if not relay_cfg or relay_cfg.get('config') not in ('automatico', 'manual_encendido', 'manual_apagado'): continue

        for day_str in unique_days:
            actual_on_periods = [(e['start'], e['end']) for e in plot_data if e['relay'] == relay_label and e['date'] == day_str]
            config_type = relay_cfg.get('config')
            weekday_num = datetime.strptime(day_str, '%d-%m-%Y').isoweekday()
            normal_on_periods = []

            if config_type == 'manual_apagado': normal_on_periods = []
            elif config_type == 'manual_encendido': normal_on_periods = [(0, 24*3600)]
            elif config_type == 'automatico':
                sched_name = relay_cfg.get('schedule')
                if not sched_name or sched_name not in channel_schedules: continue
                sched = channel_schedules[sched_name]; periods = []
                for group in sched.values():
                    if isinstance(group, dict):
                        days = group.get('days', []); on_p = group.get('on') or (group.get('status', {}).get('on') if 'status' in group else None)
                        if days and weekday_num in days and on_p is not None: periods = on_p; break
                    elif isinstance(group, list): periods = group

                if any_ww_device:
                    if periods == []: normal_on_periods = [(0, 24*3600)]
                    elif periods == [["00:00:00", "23:59:59"]]: normal_on_periods = []
                    else:
                        temp_periods = []
                        for p in periods:
                            if len(p) == 2:
                                start_s = time_to_seconds(p[0]); end_s = time_to_seconds(p[1])
                                if start_s < end_s: temp_periods.append((start_s, end_s))
                        normal_on_periods = temp_periods
                else:
                    if periods == []: normal_on_periods = [(0, 24*3600)]
                    elif periods == [["00:00:00", "23:59:59"]]: normal_on_periods = []
                    else: normal_on_periods = invert_periods_for_alerts(periods)

            uncovered = subtract_periods(normal_on_periods, actual_on_periods)
            for norm_start, norm_end in uncovered:
                if norm_start < norm_end:
                    start_str = sec_to_hhmm(norm_start); end_str = sec_to_hhmm(norm_end)
                    if start_str != end_str:
                        alerts.append(
                            f"⚠️ ALERTA: {relay_label} está APAGADO el {day_str} de {start_str} a {end_str}, cuando debería estar ENCENDIDO."
                        )

    if alerts:
        print("\n".join(reversed(alerts)))
    else:
        print("✅ Sin alertas: Todos los relés están ENCENDIDOS en su programación normal.")

    # --- FIRST PLOT ---
    num_rows = len(relay_labels) * len(unique_days)
    fig_height = max(4, 0.25 * num_rows)
    fig, ax = plt.subplots(figsize=(14, fig_height))
    colors = plt.get_cmap('tab20', len(relay_labels))
    relay_color_map = {label: colors(i) for i, label in enumerate(relay_labels)}
    yticks, yticklabels = [], []
    for i, relay_label in enumerate(relay_labels):
        device_name, relay = relay_label.split(":", 1)
        for j, day in enumerate(unique_days):
            y = i * len(unique_days) + j
            yticks.append(y); yticklabels.append(f"{relay} {day}")
            ax.barh(y, 86400, left=0, height=0.8, color='#eeeeee', edgecolor='none')
            for entry in plot_data:
                if entry['relay'] == relay_label and entry['date'] == day:
                    ax.barh(y, entry['end']-entry['start'], left=entry['start'], height=0.8, color=relay_color_map.get(relay_label, "#1f77b4"), edgecolor='none')
    ax.set_yticks(yticks); ax.set_yticklabels(yticklabels); ax.set_xlim(0, 86400)
    ax.set_xticks([i*3600 for i in range(25)]); ax.set_xticklabels([f"{i:02d}:00" for i in range(25)])
    ax.set_xlabel('Hora del día'); ax.set_title(f'Comportamiento Registrado en {sucursal_dropdown.value}\n(ENCENDIDO = Color, APAGADO = Gris)'); ax.grid(axis='x', linestyle='--', alpha=0.5)
    plt.tight_layout(); plt.show()

    # --- SECOND PLOT ---
    relay_channel_data = [{"Relés": f"{d_name}:{r_name}", "Canales": ', '.join(map(str, r_cfg.get('registers', []) or r_cfg.get('channel_addresses', [])))} for d_name, d in relay_control['devices'].items() for r_name, r_cfg in d['config_x_relay'].items()]
    df = pd.DataFrame(relay_channel_data)
    if not df.empty:
        fig2, ax2 = plt.subplots(figsize=(8, len(df) * 0.5 + 1)); ax2.axis('off')
        table = ax2.table(cellText=df.values, colLabels=df.columns, loc='center')
        table.auto_set_font_size(False); table.set_fontsize(10); table.auto_set_column_width(col=list(range(len(df.columns))))
        plt.title("Relés y sus canales"); plt.show()

    # --- THIRD PLOT ---
    num_rows = len(relay_labels) * 7
    fig_height = max(4, 0.25 * num_rows)
    fig3, ax3 = plt.subplots(figsize=(14, fig_height))
    yticks = []
    yticklabels = []
    weekday_names = ['Lun', 'Mar', 'Mie', 'Jue', 'Vie', 'Sab', 'Dom']

    for i, relay_label in enumerate(relay_labels):
        device_name, relay = relay_label.split(":", 1)
        device = relay_control['devices'][device_name]
        config_x_relay = device['config_x_relay']
        relay_cfg = config_x_relay[relay]
        for j, weekday_num in enumerate(range(7, 0, -1)):
            y = i*7 + j
            yticks.append(y)
            yticklabels.append(f"{relay} {weekday_names[weekday_num-1]}")
            ax3.barh(y, 24*3600, left=0, height=0.8, color='#eeeeee', edgecolor='none')
            config_type = relay_cfg.get('config')
            if config_type == 'manual_apagado':
                continue
            elif config_type == 'manual_encendido':
                ax3.barh(y, 24*3600, left=0, height=0.8, color=relay_color_map[relay_label], edgecolor='none')
            elif config_type == 'automatico' and 'schedule' in relay_cfg:
                sched_name = relay_cfg['schedule']
                sched = channel_schedules[sched_name]
                periods = []
                for group in sched.values():
                    if isinstance(group, dict):
                        days = group.get('days', [])
                        on_periods = group.get('on') or (group.get('status', {}).get('on') if 'status' in group else None)
                        if days and weekday_num in days and on_periods is not None:
                            periods = on_periods
                            break
                    elif isinstance(group, list):
                        periods = group
                def invert_periods(periods):
                    if not periods:
                        return [[0, 24*3600]]
                    periods_sec = []
                    for p in periods:
                        if len(p) == 2:
                            h1, m1, s1 = map(int, p[0].split(":")); h2, m2, s2 = map(int, p[1].split(":"))
                            start_sec = h1 * 3600 + m1 * 60 + s1; end_sec = h2 * 3600 + m2 * 60 + s2
                            periods_sec.append([start_sec, end_sec])
                    periods_sec = sorted(periods_sec)
                    result = []; last_end = 0
                    for start, end in periods_sec:
                        if start > last_end:
                            result.append([last_end, start])
                        last_end = max(last_end, end)
                    if last_end < 24*3600:
                        result.append([last_end, 24*3600])
                    return result
                if any_ww_device:
                    if periods == []:
                        ax3.barh(y, 24*3600, left=0, height=0.8, color=relay_color_map[relay_label], edgecolor='none')
                    elif periods == [["00:00:00", "23:59:59"]]:
                        continue
                    else:
                        for p in periods:
                            if len(p) == 2:
                                h1, m1, s1 = map(int, p[0].split(":")); h2, m2, s2 = map(int, p[1].split(":"))
                                start_sec = h1 * 3600 + m1 * 60 + s1; end_sec = h2 * 3600 + m2 * 60 + s2
                                if start_sec < end_sec:
                                    ax3.barh(y, end_sec - start_sec, left=start_sec, height=0.8, color=relay_color_map[relay_label], edgecolor='none')
                else:
                    if periods == []:
                        ax3.barh(y, 24*3600, left=0, height=0.8, color=relay_color_map[relay_label], edgecolor='none')
                    elif periods == [["00:00:00", "23:59:59"]]:
                        continue
                    else:
                        for inv_start, inv_end in invert_periods(periods):
                            if inv_start < inv_end:
                                ax3.barh(y, inv_end - inv_start, left=inv_start, height=0.8, color=relay_color_map[relay_label], edgecolor='none')
    ax3.set_yticks(yticks); ax3.set_yticklabels(yticklabels)
    ax3.set_xlim(0, 24*3600); ax3.set_xticks([i*3600 for i in range(0,25,1)])
    ax3.set_xticklabels([f"{i:02d}:00" for i in range(0,25,1)])
    ax3.set_xlabel('Hora del día'); ax3.set_title('Programación normal de relés (ENCENDIDO = Color, APAGADO = Gris)')
    ax3.grid(axis='x', linestyle='--', alpha=0.5)
    plt.tight_layout(); plt.show()

    return fig

# --- FUNCIÓN PARA CREAR TICKET EN GOOGLE SHEETS ---
# (Funcionalidad mantenida, usando placeholders)
def crear_ticket_en_bitacora(b):
    with output:
        clear_output()
        if not fig_global:
            print("❌ Error: Primero debes generar un gráfico."); return
        if not all([ticket_input.value, sucursal_dropdown.value, start_date_picker.value, end_date_picker.value]):
            print("❌ Error: Debes completar todos los campos."); return

        print("🔄 Procesando ticket...")
        try:
            auth.authenticate_user()
            creds, _ = default()
            drive_service = build('drive', 'v3', credentials=creds)

            # Usa los placeholders de G-Drive
            PARENT_FOLDER_NAME = GOOGLE_DRIVE_PARENT_FOLDER
            CHILD_FOLDER_NAME = GOOGLE_DRIVE_CHILD_FOLDER

            parent_query = f"name='{PARENT_FOLDER_NAME}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
            response = drive_service.files().list(q=parent_query, spaces='drive', fields='files(id)').execute()
            parent_files = response.get('files', [])
            if parent_files: parent_folder_id = parent_files[0].get('id')
            else:
                folder_metadata = {'name': PARENT_FOLDER_NAME, 'mimeType': 'application/vnd.google-apps.folder'}
                folder = drive_service.files().create(body=folder_metadata, fields='id').execute()
                parent_folder_id = folder.get('id')

            child_query = f"name='{CHILD_FOLDER_NAME}' and mimeType='application/vnd.google-apps.folder' and '{parent_folder_id}' in parents and trashed=false"
            response = drive_service.files().list(q=child_query, spaces='drive', fields='files(id)').execute()
            child_files = response.get('files', [])
            if child_files: child_folder_id = child_files[0].get('id')
            else:
                folder_metadata = {'name': CHILD_FOLDER_NAME, 'mimeType': 'application/vnd.google-apps.folder', 'parents': [parent_folder_id]}
                folder = drive_service.files().create(body=folder_metadata, fields='id').execute()
                child_folder_id = folder.get('id')

            print("📤 Subiendo gráfico a Google Drive...")
            plot_filename = "temp_plot.png"
            fig_global.savefig(plot_filename, bbox_inches='tight', dpi=150)
            file_metadata = {'name': f"ticket_{ticket_input.value}_{sucursal_dropdown.value}.png", 'parents': [child_folder_id]}
            media = MediaFileUpload(plot_filename, mimetype='image/png')
            file = drive_service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
            link_adjunto = file.get('webViewLink')
            drive_service.permissions().create(fileId=file.get('id'), body={'role': 'reader', 'type': 'anyone'}).execute()
            os.remove(plot_filename)
            print(f"✅ Gráfico subido. Link: {link_adjunto}")

            authed_session = google.auth.transport.requests.AuthorizedSession(creds)
            user_info = authed_session.get("https://www.googleapis.com/oauth2/v3/userinfo").json()
            email_prefix = user_info.get('email', 'desconocido').split('@')[0]
            name_parts = [name.capitalize() for name in email_prefix.split('.')]
            programador = ' '.join(name_parts)

            print("📝 Escribiendo en Google Sheets...")
            gc = gspread.authorize(creds)
            
            # Usa los placeholders de G-Sheets
            SHEET_ID = GOOGLE_SHEET_ID
            SHEET_NAME = GOOGLE_SHEET_NAME
            
            worksheet = gc.open_by_key(SHEET_ID).worksheet(SHEET_NAME)

            next_row = len(worksheet.get_all_values()) + 1
            
            # Usa el placeholder de la URL del sistema de tickets
            link_formula = f'=SI(ESBLANCO(B{next_row});"";HIPERVINCULO("{SUPPORT_TICKET_URL_PREFIX}" & B{next_row}; "TK" & B{next_row}))'

            fecha_hoy = datetime.now().strftime('%d/%m/%Y')
            fecha_inicio_exacta = start_date_picker.value.strftime('%d/%m/%Y')
            fecha_final_exacta = end_date_picker.value.strftime('%d/%m/%Y')

            new_row = [
                fecha_hoy, ticket_input.value, empresa_dropdown.value, sucursal_dropdown.value,
                "Resuelto", fecha_inicio_exacta, fecha_final_exacta, tipo_extension_dropdown.value,
                programador,
                "",              # 1ª Revisión
                link_formula,    # Link (con fórmula)
                link_adjunto     # Adjunto
            ]

            worksheet.append_row(new_row, value_input_option='USER_ENTERED')
            print(f"\n✅ ¡Éxito! Ticket '{ticket_input.value}' fue agregado a la bitácora.")
        except Exception as e:
            print(f"❌ Ocurrió un error: {e}")

# --- Eventos y visualización (CON ALINEACIÓN CORREGIDA) ---
empresa_dropdown.observe(cargar_buildings, names='value')
sucursal_dropdown.observe(cargar_clickiemotas, names='value')

# Grupo 1: Controles para el gráfico
controles_grafico = widgets.VBox([
    empresa_dropdown, sucursal_dropdown, clickiemota_dropdown,
    start_date_picker, end_date_picker
])
# Layout para los botones con un margen izquierdo para alinearlos con los campos de entrada
button_layout = widgets.Layout(margin='5px 0 0 90px')

boton_graficar = widgets.Button(description="Visualizar JSON", layout=button_layout)
boton_graficar.on_click(mostrar_y_visualizar_json)
grupo_grafico = widgets.VBox([controles_grafico, boton_graficar])

# Grupo 2: Controles para la bitácora
controles_bitacora = widgets.VBox([ticket_input, tipo_extension_dropdown])
boton_crear_ticket = widgets.Button(description="Crear Ticket", layout=button_layout)
boton_crear_ticket.on_click(crear_ticket_en_bitacora)
grupo_bitacora = widgets.VBox([controles_bitacora, boton_crear_ticket])

# Layout para alinear las dos columnas verticales en su parte inferior
box_layout = widgets.Layout(display='flex',
                            flex_flow='row',
                            align_items='flex-start')

# Aplicamos el layout al HBox que contiene los dos grupos
display(widgets.HBox([grupo_grafico, grupo_bitacora], layout=box_layout))
display(output)

# Inicializa la carga de datos
cargar_buildings(None)