# Regelung für MQTT bzw zenSDK fähige Zendure Geräte

Ich stelle hier eine lokale Regelung für Zendure Geräte bereit, als Alternative oder AddOn zu Z-HA

# Funktionen
- Die Regelung funktioniert wahlweise über MQTT oder über Z-HA Entitäten. 
- Bei Betrieb über MQTT absolut Cloudfrei. Auch zur Ersteinrichtung eines Gerätes, wird keine Cloud benötigt.
- einstellbares Target
  > Z-HA regelt den Shelly immer auf 0, meine Version enthält eine einstellbare Nullpunktverschiebung. So kann wahlweise in leichten Bezug oder leichte Einspeisung geregelt werden.
- einstellbares Deadband
  > „Ruhezone“ ums Target, in der keine Regelvorgänge stattfinden. In ruhigen Phasen (zb Abends) reduziert diese Systematik die Regelvorgänge auf ein Minimum
- Wahlweise zenSDK oder MQTT
  >Beim Einrichten eines Gerätes, müssen ca 10 Entitäten angelegt werden. Je nachdem, ob man da die Z-HA Entitäten oder die MQTT Entitäten einträgt, läuft die Steuerung über zenSDK oder MQTT.
  > MQTT
    Vorteil: neue Geräte, die von Z-HA noch nicht unterstützt werden, können hier schnell und einfach eingebunden werden.
    Nachteil: Die MQTT Daten werden seitens der Zendure Geräte nur alle 5s gepuplisht. Das macht die Regelung etwas träger als bei Z-HA
- Multigeräteunterstützung:
  > Die Regelung unterstützt auch mehrere Geräte. Für jedes Gerät muss nur einmalig eine ID und ca 10 MQTT Entitäten angelegt werden, dann ist es direkt integriert. Das Laden/Entladen passiert dabei seriell und nicht parallel wie in HEMS. Nur wenn 1 Gerät alleine die Last nicht mehr stemmen kann, werden weitere Geräte zugeschalten.
es wird nur AC-Laden unterstützt. DC-Laden und Laden über die Offgrid Steckdose habe ich funktional entfernt, weil die Regelung eigentlich nur für mich gedacht war und ich diese Funktionen nicht brauche.
- Die Ermittlung des Setpoints habe ich geändert. Z-HA arbeitet hier differenzbasiert, was diverse Hysteresen und Wartezeiten mit sich bringt, damit das System nicht überschwingt. Ich habe die Setpointermittlung anders gebaut. Ich springe grob Richtung Target (80%) und regele den Rest dann langsam aus. Diese Art der Regelung kommt weitestgehend ohne die Hysteresen und Wartezeiten aus.

# Voraussetzungen
- Home Assistant
- MQTT bzw zenSDK fähiges Gerät
- MQTT Broker (zb Mosquitto)
- AppDaemon
- Studio Code Server
- optional: Z-HA Integration

# Einrichtungsanweisungen
- Helfer anlegen:
  - input_boolean.zendure_bridge_py_aktiviert // Schalter zum aktivieren/deaktivieren der Regelung
  - input_number.p1_sensor_target // Regelziel in W; >0 = gewollter Netzbezug, <0 = gewollte Einspeisung
  - input_number.p1_sensor_deathband // "Ruhebereich" ums Target, in diesen werden alle Regelvorgänge unterbunden
  - optional: input_select.zendure_source_mode // Auswahl ob MQTT oder Z-HA verwendet werden soll. Als Optionen "mqtt" und "z-ha" eintragen. Falls diese Entität fehlt wird standardmäßig MQTT genutzt
  - optional: input_select.zendure_active_pack // Auswahl des aktiven Speichers. Optionen können sein: "L1"/"L2"/"L1/L2" usw. Falls diese Entität fehlt, werden standartmäßig alle Speicher genutzt.

    <img width="250" height="300" alt="image" src="https://github.com/user-attachments/assets/ca00a03c-f031-4be7-90b5-f55f8cef9c53" />

- MQTT Broker in HA installieren und einrichten
- in der Zendure App in den Geräteeinstellungen MQTT suchen und die Daten eures MQTT Brokers eintragen
- AppDaemon installieren
- Studio Code Server installieren
- Z-HA installieren
- AppDaemon Startseite öffnen und Host Name kopieren
  <img width="965" height="497" alt="image" src="https://github.com/user-attachments/assets/8c6c251c-2d3a-4242-accd-e89591c68f2f" />
- Studio Code Server öffnen und im Suchfeld den Host Namen von AppDaemon eingeben
- Dann solltest du im richtigen AppDaemon Ordner gelandet sein (liegt da schon eine apps.yaml? Dann bist du richtig).

  <img width="285" height="571" alt="image" src="https://github.com/user-attachments/assets/71fefbe2-dbfc-4735-912b-193d048115b4" />

- Code aus der meiner apps.yaml in deine apps.yaml kopieren
- jetzt kommt der nervige Teil. Du musst deinen P1 Sensor (p1_entity) sowie deine MQTT und Z-HA Entitäten eintragen
   - An dieser Stelle entscheidet sich auch wie viele Geräte du hast. 3 Geräte sind angelegt, hast du weniger lösche die überflüßigen
   - Ausserdem werden an dieser Stelle eure gewünschten Leistungsbegrenzungen für jedes Gerät angegeben.

     <img width="400" height="300" alt="image" src="https://github.com/user-attachments/assets/5b35803a-aba1-4a0e-9191-e58950599956" />

- Im selben Ordner in der die apps.yaml liegt müsst ihr nun 2 Dateien anlegen:
   - smart_reg_app.py
   - smart_reg_distribution.py
   - smart_reg_setpoint.py
   - In diese kopiert ihr den Inhalt der hier entsprechend benannten Dateien.
- input_boolean.zendure_bridge_py_aktiviert irgendwo aufs Dashboard ziehen und aktivieren. Unter optimalen Bedingungen sollte die Regelung nun starten
