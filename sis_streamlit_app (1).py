
# SCADA SIS — Streamlit (Opción B Smart‑relay) — Corporate + Graphviz
# Run: pip install -r requirements.txt && streamlit run sis_streamlit_app.py
import time, json, random
import streamlit as st
import pandas as pd

st.set_page_config(page_title="SCADA SIS — Smart‑relay (Corporate)", layout="wide")

# -------- Brand --------
BRAND = {
    "name": "Satgarden",
    "primary": "#0d47a1",
    "accent":  "#64b5f6",
    "ok":      "#00e676",
    "warn":    "#ffa726",
    "err":     "#f44336",
    "bg":      "#0a1929",
    "panel":   "#112033",
    "text":    "#e0f2ff",
}
if "brand" not in st.session_state:
    st.session_state.brand = BRAND.copy()

# -------- FSM/Sim --------
STATE = ("IDLE","PREHEAT","CRANK","RUN","COOLDOWN","FAULT")
ALT_TARGET = 13.8
BAT_MIN = 11.8
MAX_ATT = 3

def bootstrap():
    if "cfg" not in st.session_state:
        st.session_state.cfg = {
            "TEMP_START": 18,
            "DT": 2,
            "MIN_RUNTIME_S": 60,
            "START_DEBOUNCE": 3,
            "STOP_DEBOUNCE": 5,
            "noise": False,
        }
    if "sim" not in st.session_state:
        st.session_state.sim = {
            "temp": 22.0,
            "vbat": 12.8,
            "rpm": 0,
            "fsm": "IDLE",
            "auto": True,
            "alternator": False,
            "runTime": 0,
            "attempts": 0,
            "startCounter": 0,
            "stopCounter": 0,
            "faultAltKO": False,
            "faultStartStuck": False,
            "faultSensorBias": 0.0,
            "hist": [],
            "events": [],
        }
bootstrap()

def log(msg, level="info"):
    st.session_state.sim["events"].insert(0, f"[{time.strftime('%H:%M:%S')}] {msg} | {level}")

def to(state):
    st.session_state.sim["fsm"] = state

def start_seq():
    sim, cfg = st.session_state.sim, st.session_state.cfg
    if sim["vbat"] < BAT_MIN:
        log("A001 Batería baja. Arranque cancelado.","err"); to("IDLE"); return
    sim["attempts"] += 1; to("PREHEAT"); log("Precalentando bujías","info")
    sim["preheat_until"] = time.time() + 6

def crank():
    sim = st.session_state.sim
    to("CRANK"); sag = 0.7 + random.random()*0.2
    sim["vbat"] = max(10.8, sim["vbat"] - sag); log("Motor de arranque ACTIVADO","info")
    sim["crank_until"] = time.time() + 2.5

def run():
    sim = st.session_state.sim; to("RUN"); sim["rpm"] = 3000
    sim["alternator"] = not sim["faultAltKO"]; sim["runTime"]=0; sim["startCounter"]=0; sim["stopCounter"]=0
    log(f"Motor en marcha. Alternador {'ON' if sim['alternator'] else 'KO'}.","ok")

def stop(by_user=False):
    sim, cfg = st.session_state.sim, st.session_state.cfg
    if sim["fsm"] == "RUN" and sim["runTime"] < cfg["MIN_RUNTIME_S"] and by_user:
        log(f"Paro bloqueado: faltan {cfg['MIN_RUNTIME_S']-sim['runTime']}s","warn"); return
    sim["rpm"]=0; sim["alternator"]=False; to("COOLDOWN"); log("Motor detenido","ok")
    sim["cooldown_until"] = time.time() + 0.8

def tick():
    sim, cfg = st.session_state.sim, st.session_state.cfg; now = time.time()
    # timers
    if sim.get("preheat_until") and now >= sim["preheat_until"] and sim["fsm"]=="PREHEAT":
        sim["preheat_until"] = None; crank()
    if sim.get("crank_until") and now >= sim["crank_until"] and sim["fsm"]=="CRANK":
        sim["crank_until"] = None
        success = (not sim["faultStartStuck"]) and sim["vbat"]>11.6 and (sim["temp"]+sim["faultSensorBias"]) <= cfg["TEMP_START"]+1.0
        if success: run()
        else:
            log("Arranque fallido","warn")
            if sim["attempts"] < MAX_ATT: sim["retry_at"] = now + 5.0; log(f"Reintento {sim['attempts']+1}/{MAX_ATT} en 5s","warn")
            else: to("FAULT"); log("A002 Fallo de arranque","err")
    if sim.get("retry_at") and now >= sim["retry_at"] and sim["fsm"] in ("IDLE","FAULT","CRANK","PREHEAT"):
        sim["retry_at"] = None; start_seq()
    if sim.get("cooldown_until") and now >= sim["cooldown_until"] and sim["fsm"]=="COOLDOWN":
        sim["cooldown_until"] = None; to("IDLE")

    # telemetry / control
    shown = (sim["temp"] + sim["faultSensorBias"]) + (random.random()*0.4-0.2 if st.session_state.cfg["noise"] else 0.0)
    sim["hist"].append(shown); sim["hist"]=sim["hist"][-600:]
    if sim["fsm"]=="RUN":
        sim["runTime"] += 1
        if sim["alternator"] and sim["vbat"] < ALT_TARGET: sim["vbat"] = min(ALT_TARGET, sim["vbat"] + 0.02)
        if shown >= (cfg["TEMP_START"]+cfg["DT"]): sim["stopCounter"] += 1
        else: sim["stopCounter"] = 0
        if sim["auto"] and sim["stopCounter"] >= cfg["STOP_DEBOUNCE"] and sim["runTime"] >= cfg["MIN_RUNTIME_S"]: stop(False)
    else:
        sim["vbat"] = max(10.8, sim["vbat"] - 0.001)
        if sim["auto"] and sim["fsm"] in ("IDLE","FAULT"):
            if shown <= cfg["TEMP_START"]: sim["startCounter"] += 1
            else: sim["startCounter"] = 0
            if sim["startCounter"] >= cfg["START_DEBOUNCE"]:
                if sim["fsm"]=="FAULT": sim["attempts"] = 0
                start_seq()

# -------- Corporate header --------
def header():
    b = st.session_state.brand
    st.markdown(f"""
    <style>
    .sg-wrap {{ background: linear-gradient(135deg, {b['primary']}, #0b2e6b); padding:12px 16px; border-radius:12px; color:{b['text']};
                display:flex; align-items:center; justify-content:space-between; gap:10px; box-shadow:0 6px 28px rgba(0,0,0,.45); }}
    .sg-chip {{ background: rgba(255,255,255,.08); border:1px solid rgba(255,255,255,.15); padding:6px 10px; border-radius:999px; font-size:12px; display:flex; align-items:center; gap:8px; }}
    .sg-led {{ width:10px; height:10px; border-radius:50%; background:#3a3a3a; display:inline-block; }}
    .ok {{ background:{b['ok']}; box-shadow:0 0 12px {b['ok']}; }}
    .warn {{ background:{b['warn']}; box-shadow:0 0 12px {b['warn']}; }}
    .err {{ background:{b['err']}; box-shadow:0 0 12px {b['err']}; }}
    </style>
    """, unsafe_allow_html=True)
    sim = st.session_state.sim
    led_motor = "ok" if sim["fsm"]=="RUN" else ("warn" if sim["fsm"]=="CRANK" else "")
    led_bat = "err" if sim["vbat"]<11.8 else ("warn" if sim["vbat"]<12.3 else "ok")
    st.markdown(f"""
    <div class="sg-wrap">
      <div><b>SCADA SIS — {b['name']}</b> (Smart‑relay)</div>
      <div style="display:flex; gap:10px;">
        <div class="sg-chip"><span class="sg-led {'ok' if sim['auto'] else ''}"></span>Auto</div>
        <div class="sg-chip"><span class="sg-led {led_motor}"></span>Motor</div>
        <div class="sg-chip"><span class="sg-led {led_bat}"></span>Batería</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

# -------- Graphviz synoptic --------
def dot_for_state():
    from graphviz import Digraph
    b = st.session_state.brand
    sim, cfg = st.session_state.sim, st.session_state.cfg
    g = Digraph("G", graph_attr={"rankdir":"LR","bgcolor":"#0e1a2a"})
    g.attr("node", fontname="Segoe UI", fontsize="10", style="rounded,filled", color="#456", fillcolor=st.session_state.brand["panel"], fontcolor="#cfe8ff", margin="0.08")
    g.attr("edge", fontname="Segoe UI", fontsize="10")
    def node(name, on=False, warn=False, err=False, note=""):
        fill, pen = "#22313f", "#607d8b"
        if on: fill, pen = "#174a24", b["ok"]
        if warn: fill, pen = "#5a3808", b["warn"]
        if err: fill, pen = "#5a1a1a", b["err"]
        lab = f"<<b>{name}</b><br/>{note}>" if note else f"<<b>{name}</b>>"
        g.node(name, label=lab, fillcolor=fill, color=pen)
    def edge(a,b,label="",kind="power",active=False):
        base = "#ef5350" if kind=="power" else "#42a5f5"
        col = b["ok"] if active else base
        g.edge(a,b, label=label, color=col, penwidth="3" if active else "1.5")

    running = sim["fsm"]=="RUN"; cranking = sim["fsm"]=="CRANK"; heating = sim["fsm"]=="PREHEAT"
    node("BATERÍA", on=sim["vbat"]>=BAT_MIN, warn=(12.3>sim["vbat"]>=BAT_MIN), err=sim["vbat"]<BAT_MIN, note=f"{sim['vbat']:.1f}V")
    node("FUSIBLE 30A", on=True)
    node("SECCIONADOR", on=True, note="ON")
    node("LLAVE", on=True, warn=cranking or heating, note="ON/START")
    node("RELÉ BUJÍAS", warn=heating, note="GLOW")
    node("SOLENOIDE ARR.", on=cranking, note="50")
    node("MOTOR ARR.", on=cranking, note="M")
    node("MOTOR DIÉSEL", on=running, note="RUN" if running else "OFF")
    node("ALTERNADOR", on=sim["alternator"], note="D+")
    node("CONTACTOR VENT.", on=running, note="A1/A2")
    node("VENTILADOR", on=running)
    node("SMART‑RELAY", on=True)
    node("SENSOR TEMP", on=True, note=f"{(sim['temp']+sim['faultSensorBias']):.1f}°C")

    edge("BATERÍA","FUSIBLE 30A","30","power",True)
    edge("FUSIBLE 30A","SECCIONADOR","30","power",True)
    edge("SECCIONADOR","LLAVE","30","power",True)
    edge("LLAVE","RELÉ BUJÍAS","15→87","power",heating)
    edge("LLAVE","SOLENOIDE ARR.","15→50","power",cranking)
    edge("ALTERNADOR","BATERÍA","D+→B+","power",sim["alternator"])
    edge("CONTACTOR VENT.","VENTILADOR","","power",running)
    edge("SOLENOIDE ARR.","MOTOR ARR.","","power",cranking or running)
    edge("SENSOR TEMP","SMART‑RELAY","AI","ctrl",True)
    edge("SMART‑RELAY","RELÉ BUJÍAS","DO GLOW","ctrl",heating)
    edge("SMART‑RELAY","CONTACTOR VENT.","DO FAN","ctrl",running)
    edge("LLAVE","SOLENOIDE ARR.","START 50","ctrl",cranking)
    return g

# -------- UI --------
header()
st.title("SCADA SIS — Opción B (Smart‑relay)")

tab_sim, tab_guide, tab_io, tab_bom, tab_comm, tab_sec, tab_ladder = st.tabs(
    ["Simulador","Guía","I/O","Materiales","Comisionado","Seguridad","Ladder"]
)

with tab_sim:
    colL, colR = st.columns([1.0,1.15], gap="large")
    cfg = st.session_state.cfg; sim = st.session_state.sim

    with colL:
        st.subheader("Parámetros")
        cfg["TEMP_START"] = st.slider("Temp. arranque", 5, 25, cfg["TEMP_START"], 1)
        cfg["DT"] = st.slider("ΔT histeresis", 1, 10, cfg["DT"], 1)
        st.caption(f"Temp. paro: **{cfg['TEMP_START']+cfg['DT']} °C**")
        colA, colB = st.columns(2)
        with colA:
            cfg["MIN_RUNTIME_S"] = st.slider("Tiempo mínimo en marcha (s)", 10, 300, cfg["MIN_RUNTIME_S"], 10)
            cfg["START_DEBOUNCE"] = st.slider("Debounce arranque (s)", 1, 10, cfg["START_DEBOUNCE"], 1)
        with colB:
            cfg["STOP_DEBOUNCE"] = st.slider("Debounce paro (s)", 1, 15, cfg["STOP_DEBOUNCE"], 1)
            cfg["noise"] = st.checkbox("Ruido sensor ±0.2°C", value=cfg["noise"])

        st.subheader("Simulación")
        sim["temp"] = st.slider("Temp. simulada (°C)", -5.0, 35.0, float(sim["temp"]), 0.5)
        sim["vbat"] = st.slider("Voltaje batería (V)", 10.8, 14.0, float(sim["vbat"]), 0.1)
        col1, col2, col3 = st.columns(3)
        with col1: sim["auto"] = st.toggle("Auto", value=sim["auto"])
        with col2:
            if st.button("Arranque manual (START)"): start_seq()
        with col3:
            if st.button("Paro"): stop(True)

        st.subheader("Fallos / pruebas")
        f1, f2, f3 = st.columns(3)
        with f1: sim["faultAltKO"] = st.toggle("Alternador KO", value=sim["faultAltKO"])
        with f2: sim["faultStartStuck"] = st.toggle("Relé START pegado", value=sim["faultStartStuck"])
        with f3:
            bias = st.toggle("Sesgo sensor +0.8°C", value=sim["faultSensorBias"]>0.0)
            sim["faultSensorBias"] = 0.8 if bias else 0.0

        st.subheader("Config")
        cfg_json = json.dumps(cfg, indent=2)
        st.download_button("⬇ Exportar configuración", data=cfg_json, file_name="sis-config.json", mime="application/json")
        upcfg = st.file_uploader("⬆ Importar configuración (JSON)", type=["json"], accept_multiple_files=False, key="cfg_upl")
        if upcfg is not None:
            try: st.session_state.cfg.update(json.load(upcfg)); st.success("Configuración importada")
            except Exception as e: st.error(f"Error importando JSON: {e}")

        st.subheader("LOG")
        st.text_area("Eventos", "\n".join(st.session_state.sim["events"]), height=240)

    with colR:
        st.subheader("KPIs")
        k1, k2, k3 = st.columns(3)
        k1.metric("Temperatura", f"{(sim['temp']+sim['faultSensorBias']):.1f} °C")
        k2.metric("Batería", f"{sim['vbat']:.1f} V")
        k3.metric("Estado", sim["fsm"])

        st.subheader("Gráfica temperatura")
        st.line_chart(pd.DataFrame({"T": st.session_state.sim["hist"]}))

        st.subheader("Sinótico eléctrico (Graphviz)")
        from graphviz import Source
        st.graphviz_chart(dot_for_state(), use_container_width=True)
        st.caption("Convención: rojo=potencia, azul=control, verde=activo.")

    # "tick" por interacción
    tick()

with tab_guide:
    st.markdown("""
**Arquitectura (campo)**  
1) B+ → Fusible 30 A → Seccionador → bus potencia.  
2) Smart‑relay 12/24 V DC.  
3) **DO→85/86**: `IGN`, `GLOW`, `START`, `FAN`.  
4) **DI/AI**: `TSENS`, `D+` (RUN_FB), `E-STOP` (NC), `MAN_START` (NO).  
5) **E‑STOP** en serie con IGN (corte duro).

**Secuencia**  
`IDLE → PREHEAT (6–8 s) → CRANK (2–3 s) → RUN (≥ min_run) → STOP`  
Histeresis ΔT, debounce, reintentos y watchdog de START.
""")

with tab_io:
    st.markdown("""
### Mapa I/O — LOGO! 8 12/24RCE
| Tag | Tipo | Dirección | Descripción |
|---|---|---|---|
| TSENS | AI | AI1 (AM2: AI1) | Temperatura ambiente |
| RUN_FB | DI | I1 | D+ alternador |
| EMERG | DI | I2 | Paro emergencia (NC) |
| MAN_START | DI | I3 | Arranque manual (NO) |
| IGN | DO | Q1 | Relé IGN (15) |
| GLOW | DO | Q2 | Relé bujías |
| START | DO | Q3 | Relé arranque (50) |
| FAN | DO | Q4 | Contactor ventilador |
""")

with tab_bom:
    st.markdown("""
### Materiales (Opción B)
- Smart‑relay LOGO! 8 12/24RCE + AM2 (si AI 4–20 mA/PT100)
- Seccionador + Fusible 30 A
- Relé IGN 12 V 40 A / Relé GLOW 12 V 70 A / Relé START 12 V 40 A
- Contactor FAN bobina 12 V DC
- Sensor temp NTC/PT100 + Tx 4–20 mA
- E‑STOP NC con enclavamiento; baliza/LED 12 V
- Envolvente IP65 carril DIN; borneros 1.5–6 mm²
""")

with tab_comm:
    st.markdown("""
### Plan de pruebas (FAT/SAT)
1. Inspección: polaridad, apriete, etiquetado, continuidad a 31.  
2. Alimentación: medir B+ tras fusible; caída < 0.2 V.  
3. Entradas: simular TSENS y RUN_FB; ver estados en HMI.  
4. Bobinas: forzar Q1..Q4 y medir 85/86.  
5. Arranque seguro sin combustible: watchdog de START (<=3 s).  
6. RUN: D+ activo y carga a batería (~13.8 V).  
7. Paro: elevar TSENS > setpoint+ΔT tras min_run.  
8. Alarmas: batería baja, fallo arranque, emergencia, sensor fuera de rango.  
9. Exportar config JSON y checklist firmado.
""")

with tab_sec:
    st.markdown("""
### Seguridad y mejores prácticas
- E‑STOP en serie con IGN; supresión de bobinas con diodo.  
- Separación potencia/control; masas cortas y limpias.  
- Envolvente IP65; prensaestopas y etiquetado.  
- Prueba mensual de arranque y revisión anual de bornes.
""")

with tab_ladder:
    st.markdown("""
#### Plantilla Ladder (pseudocódigo LOGO!)
```
Network 1: Condición de arranque
  START_REQ = (TSENS <= SETPOINT) TON(START_DB)

Network 2: Secuencia
  IGN = START_REQ OR RUN
  GLOW = PLS(START_REQ) TON(T_PREHEAT)
  START = (T_PREHEAT.DN) TON(T_CRANK) AND NOT RUN_FB AND RETRY<3

Network 3: Detección RUN
  RUN = RUN_FB OR (START AND T_CRANK.ELAP>=1.0)

Network 4: Paro
  STOP_REQ = (TSENS >= SETPOINT+DT) TON(STOP_DB) AND T_RUN >= MIN_RUN
  RUN = RUN AND NOT STOP_REQ

Network 5: Seguridad
  START = START AND NOT WATCHDOG_EXCEEDED AND EMERG=OK
  RETRY = CTU(START_FAIL)
```
""")
