import appdaemon.plugins.hass.hassapi as hass
import smart_reg_distribution as dist
import time
from collections import deque
from math import sqrt

class SmartRegManagerLike(hass.Hass):
    def initialize(self):
        # Konfiguration laden
        self.p1_entity = self.args["p1_entity"]
        self.target_w_entity = self.args["target_w"]
        self.enable_entity = self.args["enable_entity"]
        self.deadband_entity = self.args.get("deadband_w", 30)
        self.packs = self.args["packs"]
        
        # --- zenZDK Core Variablen ---
        self.zorder = deque([25, -25], maxlen=8)
        self.zero_idle = float('inf') 
        self.zero_next = 0.0           
        self.zero_fast = 0.0           
        
        # Regel-Parameter
        self.threshold = 2.0           
        self.time_zero = 2.0           
        self.time_fast = 2.0          
        self.time_idle = 2.0           
        self.min_power = 50            
        
        # Zustands-Variablen
        self.last_sent_values = {}
        self.leader_id = None
        self.current_p1 = 0 # Neu: Um den p1-Status für apply verfügbar zu machen

        self.listen_state(self.update_power, self.p1_entity)
        # NEU: Listener für die Packauswahl und den Quellen-Modus
        self.listen_state(self.update_power, "input_select.zendure_active_pack")
        self.listen_state(self.update_power, "input_select.zendure_source_mode")
        
        self.log(f"!!! V1.6.10 - APPLY-BLOCKING DEADBAND !!!")

    def get_ha_val(self, key_or_val):
        """Hilfsfunktion zum sicheren Auslesen von HA-Entitäten."""
        if isinstance(key_or_val, str) and any(x in key_or_val for x in ["input_number.", "sensor.", "number.", "select."]):
            res = self.get_state(key_or_val)
            if res in [None, "unknown", "unavailable"]: return 0.0
            try: return float(res)
            except: return 0.0
        try: return float(key_or_val)
        except: return 0.0

    def update_power(self, entity, attribute, old, new, kwargs):
        if self.get_state(self.enable_entity) != "on":
            return

        try:
            # Zustand des Shellys direkt holen, um Fehler bei Dropdown-Triggern zu vermeiden
            p1_val = self.get_state(self.p1_entity)
            if p1_val in [None, "unknown", "unavailable"]: return
            
            # 1. P1-Wert (Netzabweichung)
            shelly = float(p1_val)
            target = self.get_ha_val(self.target_w_entity)
            p1_raw = int(shelly - target)
            
            # --- Deadband Anwendung ---
            deadband = abs(self.get_ha_val(self.deadband_entity))
            if abs(p1_raw) < deadband:
                self.current_p1 = 0
            else:
                self.current_p1 = p1_raw
            
            p1 = self.current_p1
            # ---------------------------

            # 2. Rauschfilter & Sprungerkennung
            avg = sum(self.zorder) / len(self.zorder) if len(self.zorder) > 1 else 0
            stddev = min(50, sqrt(sum([pow(i - avg, 2) for i in self.zorder]) / len(self.zorder)) if len(self.zorder) > 0 else 0)
            
            isFast = abs(p1 - avg) > (self.threshold * stddev)
            if isFast: 
                self.zorder.clear()
            self.zorder.append(p1)

            # 3. Timings
            now = time.time()
            if now < self.zero_next or (now < self.zero_fast and not isFast):
                return

            # 4. Aktuelle Daten der aktiven Packs sammeln
            selection = self.get_state("input_select.zendure_active_pack")
            active_list = [x.strip().lower() for x in str(selection).split("/")] if selection else []
            
            # NEU: Gewählten Quellen-Modus abfragen (liefert z.B. "mqtt" oder "z-ha")
            source_mode = str(self.get_state("input_select.zendure_source_mode")).lower()

            powerActual = 0
            temp_devices = []
            all_states = self.get_state()

            for p in self.packs:
                p_id = p["id"]
                
                # NEU: ID am Unterstrich aufspalten (z.B. "l1_mqtt" -> "l1", "mqtt")
                if "_" not in p_id:
                    continue
                base_id, p_mode = p_id.lower().split("_", 1)
                
                # NEU: Kombinierter Filter für Modus-Suffix und aktive Whitelist
                if p_mode != source_mode:
                    continue
                if base_id not in active_list:
                    continue

                r_out = float(all_states.get(p["battery_output_entity"], {}).get("state") or 0)
                r_in = float(all_states.get(p["battery_input_entity"], {}).get("state") or 0)
                p_real = r_out - r_in
                powerActual += p_real
                
                soc = float(all_states.get(p["soc_entity"], {}).get("state") or 0)
                min_soc = float(all_states.get(p.get("minsoc_entity"), {}).get("state") or 5)
                max_soc = float(all_states.get(p.get("maxsoc_entity"), {}).get("state") or 100)
                
                temp_devices.append({
                    "id": p_id, 
                    "soc": soc,
                    "min_soc": min_soc,
                    "max_soc": max_soc,
                    "max_out": float(p.get("max_out_w", 2400)),
                    "max_in": float(p.get("max_in_w", 2400)), 
                    "working": True,
                    "actual": p_real
                })

            # 5. Sollwert-Ermittlung (v1.7.0 - Dual-Phase Control)
            u_sys_next = 0
            state = "idle"
            
            # Dynamischen Korrekturfaktor (Gain) bestimmen
            if abs(p1) > 100:
                gain = 0.8  # Grobregelung: 80% Korrektur
            else:
                gain = 0.4  # Feinregelung: 40% Korrektur (etwas agiler als 30%)

            # Berechnete Korrektur basierend auf P1 und Gain
            correction = int(p1 * gain)

            if powerActual < 0:
                # Wir laden aktuell. Neuer Wert = Aktuelle Leistung + gedämpfte Korrektur
                u_sys_next = min(0, powerActual + correction)
                state = "input"
            elif powerActual > 0:
                # Wir entladen aktuell.
                u_sys_next = max(0, powerActual + correction)
                state = "output"
            
            elif self.zero_idle == float('inf') and not self.last_sent_values.get("active", False):
                self.zero_idle = now + self.time_idle
                return
            elif self.zero_idle < now or self.last_sent_values.get("active", False):
                if p1 < -self.min_power:
                    u_sys_next = int(p1 * gain) # Erster Sprung aus dem Stand
                    state = "input"
                    self.zero_idle = float('inf')
                elif p1 >= 0:
                    u_sys_next = int(p1 * gain) # Erster Sprung aus dem Stand
                    state = "output"
                    self.zero_idle = float('inf')
                else:
                    return

            self.zero_next = now + self.time_zero
            self.zero_fast = now + self.time_fast

            # 6. Bucket-Sortierung
            is_discharge = (state == "output")
            temp_devices.sort(key=lambda d: int(min(d["soc"], 99) / 10), reverse=is_discharge)
            
            if temp_devices:
                new_leader = temp_devices[0]['id']
                if new_leader != self.leader_id:
                    self.log(f"Leader-Wechsel: {self.leader_id} -> {new_leader}")
                    self.leader_id = new_leader

            # 7. Verteilung & Monitoring
            soc_info = {d["id"]: int(d["soc"]) for d in temp_devices}
            
            if state == "output":
                res = dist.calculate_v113(temp_devices, abs(u_sys_next), "output")
                self.log(f"MONITOR: P1={int(shelly)}W | Set={int(u_sys_next)}W | Dist={res} | SoCs={soc_info}")
                self.apply(res, "output")
                self.last_sent_values["active"] = True
            elif state == "input":
                res = dist.calculate_v113(temp_devices, abs(u_sys_next), "input")
                self.log(f"MONITOR: P1={int(shelly)}W | Set={int(u_sys_next)}W | Dist={res} | SoCs={soc_info}")
                self.apply(res, "input")
                self.last_sent_values["active"] = True
            else:
                if self.last_sent_values.get("active", False):
                    self.log(f"MONITOR: System geht in IDLE (P1={int(shelly)}W) | SoCs={soc_info}")
                    self.apply({}, "idle")
                    self.last_sent_values["active"] = False

        except Exception as e:
            self.log(f"Fehler: {e}")

    def apply(self, pwr_map, mode):
        """Service-Calls an Home Assistant mit dynamischen Modes."""
        if self.current_p1 == 0 and self.last_sent_values.get("active", False) and mode != "idle":
            return

        mode_config = self.args.get("ac_mode_values", {})
        raw_variants = mode_config.get(mode, [mode]) if mode != "idle" else []

        for p in self.packs:
            p_id = p["id"]
            val = pwr_map.get(p_id, 0)
            last_val = self.last_sent_values.get(p_id, -999)
            
            # --- NEU: Zielgerichtete Modus-Auswahl zur Fehlermeldungs-Vermeidung ---
            # Wir filtern die Varianten passend zum ID-Suffix des aktuellen Packs
            if "_mqtt" in p_id.lower():
                variants = [v for v in raw_variants if "mode" in v]
            elif "_z-ha" in p_id.lower():
                variants = [v for v in raw_variants if "mode" not in v]
            else:
                variants = raw_variants
            # ----------------------------------------------------------------------
            
            current_mode = self.get_state(p["ac_mode_entity"])
            mode_is_correct = (current_mode in variants) or (mode == "idle")
            
            if abs(val - last_val) > 5 or (val == 0 and last_val != 0) or not mode_is_correct:
                try:
                    if mode != "idle" and not mode_is_correct:
                        for variant in variants:
                            self.call_service("select/select_option", 
                                              entity_id=p["ac_mode_entity"], 
                                              option=variant)

                    if mode == "output":
                        self.call_service("number/set_value", entity_id=p["out_limit_entity"], value=val)
                        self.call_service("number/set_value", entity_id=p["in_limit_entity"], value=0)
                    elif mode == "input":
                        self.call_service("number/set_value", entity_id=p["in_limit_entity"], value=val)
                        self.call_service("number/set_value", entity_id=p["out_limit_entity"], value=0)
                    else:
                        self.call_service("number/set_value", entity_id=p["out_limit_entity"], value=0)
                        self.call_service("number/set_value", entity_id=p["in_limit_entity"], value=0)
                    
                    self.last_sent_values[p_id] = val
                except Exception as e:
                    self.log(f"Sende-Fehler an {p_id}: {e}")

                    
# --- ÄNDERUNGSVERZEICHNIS ---
# v1.6.10 (2026-05-14):
# - Zeile 140: int(d["soc"] / 10) zu int(min(d["soc"], 99) / 10), reverse=is_discharge)
# - Zeile 26: self.time_idle = 5.0 auf self.time_idle = 2.0 
# - Zeile 25: self.time_fast = 10.0 auf self.time_fast = 5.0
# - Zeile 42: Variable self.current_p1 eingeführt, um Deadband-Status global zu speichern.
# - Zeile 66-70: Deadband setzt nun current_p1 auf 0.
# - Zeile 163-167: In der apply-Methode wird das Senden neuer Befehle blockiert, 
#   wenn current_p1 == 0 ist. Die Berechnung läuft im Hintergrund stabil weiter.
# v1.7.1 (2026-05-15):
# - Integration input_select.zendure_active_pack zur dynamischen Aktivierung von Speichern.
# - Case-insensitive ID-Vergleich (l1, l2, l3) für Whitelist-Abgleich integriert.
# v1.7.5 (2026-05-16):
# - Integration von input_select.zendure_source_mode zur Umschaltung zwischen MQTT und Z-HA.
# - ID-Splitting am Unterstrich zur parallelen Filterung von Basis-ID und Suffix-Modus.
# - Zeile 53: p1_val Direktabfrage über get_state implementiert, um String-Crashes bei Dropdown-Auslösung zu verhindern.
