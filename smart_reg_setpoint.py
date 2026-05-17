def calculate_setpoint(p1, powerActual, zero_idle, last_sent_values, now, time_idle, min_power, time_zero, time_fast):
    u_sys_next = 0
    state = "idle"
    zero_next = 0.0
    zero_fast = 0.0
    
    # Dynamischen Korrekturfaktor (Gain) bestimmen
    if abs(p1) > 300:
        gain = 0.7  # Grobregelung: 70% Korrektur
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

    zero_next = now + time_zero
    zero_fast = now + time_fast
    
    return False, u_sys_next, state, zero_idle, zero_next, zero_fast

#Änderungshistorie
#Zeile 9: Gain von 0.8 zu 0.7 geändert
#Zeile 8: Schwelle Grob-/Feinregelung von 100 auf 300 geändert
