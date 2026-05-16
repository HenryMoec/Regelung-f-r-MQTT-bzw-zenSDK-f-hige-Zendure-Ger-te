import time

last_active_time = {}

def calculate_v113(devices, need, mode="output"):
    global last_active_time
    results = {d["id"]: 0 for d in devices}
    if need <= 0: return results

    now = time.time()
    is_discharge = (mode == "output")
    
    # WICHTIG: Wir übernehmen die Sortierung der App (kein erneutes sorted())
    # Das verhindert Leader-Konflikte zwischen App und Distribution.
    active_devs = []
    total_active_limit = 0

    for d in devices:
        d_id = d["id"]
        limit = d.get("max_out", 2400) if is_discharge else d.get("max_in", 2400)
        
        # SoC-Stopps
        if not is_discharge and d["soc"] >= d.get("max_soc", 100): continue 
        if is_discharge and d["soc"] <= d.get("min_soc", 5): continue 
        if limit <= 0: continue

        is_actually_working = abs(d.get("actual", 0)) > 10
        was_recently_active = (now - last_active_time.get(d_id, 0)) < 120
        
        # Original 1.1.3 Threshold logic
        threshold = 0.80 if (is_actually_working or was_recently_active) else 0.85

        if len(active_devs) == 0 or need > (total_active_limit * threshold):
            active_devs.append((d, limit))
            total_active_limit += limit
            last_active_time[d_id] = now
        else:
            if was_recently_active:
                active_devs.append((d, limit))
                total_active_limit += limit
            else:
                break

    if not active_devs or total_active_limit == 0:
        return results

    # --- VERBESSERTE PROPORTIONALE VERTEILUNG ---
    remaining_power = need
    
    # Wir nutzen eine Kopie des Gesamtlimits, um den Anteil sauber zu halten
    fixed_total_limit = total_active_limit

    for i, (d, limit) in enumerate(active_devs):
        # Für den letzten Speicher nehmen wir einfach den Rest (vermeidet Rundungsfehler)
        if i == len(active_devs) - 1:
            pwr = remaining_power
        else:
            # Proportionaler Anteil am ursprünglichen Gesamtlimit
            pwr = int(need * (limit / fixed_total_limit))
        
        val = min(limit, pwr)
        results[d["id"]] = val
        remaining_power -= val

    return results
