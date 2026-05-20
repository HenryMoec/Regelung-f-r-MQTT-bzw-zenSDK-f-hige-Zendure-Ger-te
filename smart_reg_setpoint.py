#smart_reg_setpoint v1.7.8

def calculate_setpoint(p1, powerActual, zero_idle, last_sent_values, now, time_idle, min_power, time_zero, time_fast):
    u_sys_next = 0
    state = "idle"
    zero_next = 0.0
    zero_fast = 0.0
    
    # Dynamischen Korrekturfaktor (Gain) bestimmen
    if abs(p1) > 200:
        gain = 0.7  # Grobregelung: 70% Korrektur
    else:
        gain = 0.9  # Feinregelung: 40% Korrektur (etwas agiler als 30%)

    # Berechnete Korrektur basierend auf P1 und Gain
    correction = int(p1 * gain)

    # REPARATUR: Nur numerische Werte (int/float) summieren, um den Typenfehler mit 'last_state' zu verhindern
    last_total_sent = sum([v for k, v in last_sent_values.items() if k != "active" and isinstance(v, (int, float))])

    if powerActual < 0 or (powerActual == 0 and last_sent_values.get("active", False) and last_total_sent > 0 and last_sent_values.get("last_state") == "input"):
        # Wir laden aktuell (Basis ist der letzte gesendete Wert, um Kleben bei kleinen Korrekturen zu verhindern)
        base_val = -last_total_sent if last_total_sent > 0 else powerActual
        u_sys_next = min(0, base_val + correction)
        state = "input"
    elif powerActual > 0 or (powerActual == 0 and last_sent_values.get("active", False) and last_total_sent > 0 and last_sent_values.get("last_state") == "output"):
        # Wir entladen aktuell
        base_val = last_total_sent if last_total_sent > 0 else powerActual
        u_sys_next = max(0, base_val + correction)
        state = "output"
    
    elif zero_idle == float('inf') and not last_sent_values.get("active", False):
        zero_idle = now + time_idle
        return True, u_sys_next, state, zero_idle, zero_next, zero_fast
    elif zero_idle < now or last_sent_values.get("active", False):
        if p1 < -min_power:
            u_sys_next = int(p1 * 0.6) # Erster Sprung aus dem Stand
            state = "input"
            zero_idle = float('inf')
        elif p1 >= 0:
            u_sys_next = int(p1 * 0.6) # Erster Sprung aus dem Stand
            state = "output"
            zero_idle = float('inf')
        else:
            return True, u_sys_next, state, zero_idle, zero_next, zero_fast

    # --- Asymmetrisches Tacho-Feedback Rate-Limiting ---
    if last_sent_values.get("active", False) and last_total_sent > 0:
        # Toleranzbereich berechnen (10% vom letzten gesendeten Sollwert, mindestens aber 40W)
        tolerance = max(40, int(last_total_sent * 0.10))
        is_in_target_range = abs(abs(powerActual) - last_total_sent) <= tolerance
        
        if not is_in_target_range:
            if state == "output":
                # ENTLASTUNG: Wenn der neue Wunsch höher ist als der alte, der Speicher aber noch hinterherhinkt -> Blockieren
                if u_sys_next > last_total_sent:
                    u_sys_next = last_total_sent
                # Wenn der neue Wunsch NIEDRIGER ist (Notbremse) -> Erlauben!
            elif state == "input":
                # BELADUNG: (Werte sind negativ) Wenn der neue Wunsch noch MEHR Ladung fordert (kleinerer Wert) -> Blockieren
                if u_sys_next < -last_total_sent:
                    u_sys_next = -last_total_sent
                # Wenn weniger Ladung gefordert wird (Richtung 0) -> Erlauben!
    # ---------------------------------------------------------

    zero_next = now + time_zero
    zero_fast = now + time_fast
    
    return False, u_sys_next, state, zero_idle, zero_next, zero_fast

#Änderungshistorie
#Zeile 18: isinstance(v, (int, float)) hinzugefügt, um String-Einträge ('last_state') auszufiltern (v1.7.8 - Fix)
#Zeile 9: Gain von 0.8 zu 0.7 geändert
#Zeile 8: Schwelle Grob-/Feinregelung von 100 auf 300 geändert
#Zeile 20 & 25: Berechnungsbasis von powerActual auf stabilen last_total_sent umgestellt (v1.7.7 - Anti-Kleb-Fix)
#Zeile 49-66: Asymmetrische Tacho-Feedback-Bremse integriert (v1.7.7)
