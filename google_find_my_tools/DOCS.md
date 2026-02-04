# Google Find My Tools Add-on

Dieses Add-on ermöglicht die Nutzung der Google Find My Tools in Home Assistant.

## Funktion

Das Add-on startet einen Docker-Container mit einer grafischen Oberfläche (via noVNC), um den interaktiven Login-Prozess bei Google durchzuführen.

## Einrichtung

1.  Starte das Add-on.
2.  Klicke auf **"WEB UI ÖFFNEN"**, um die grafische Oberfläche zu sehen.
3.  Warte kurz, bis der Chrome-Browser startet und die Google-Login-Seite anzeigt.
4.  **Erster Login:** Melde dich mit deinem Google-Konto an.
5.  Das Skript wird nun automatisch deine Geräteliste abrufen und das **erste Gerät** auswählen, um eine Standortabfrage zu starten.
6.  **Zweiter Login:** Es öffnet sich erneut ein Login-Fenster (oder eine Bestätigung). Dies ist notwendig, um den vollen Zugriff für die `secrets.json` zu generieren. Führe auch diesen Login durch.
7.  Sobald beide Schritte erfolgreich waren, beendet sich das Add-on und speichert die Daten.

## Secrets / Anmeldedaten

Das Add-on speichert die erfolgreichen Anmeldedaten (`secrets.json`) automatisch in deinem **Share**-Ordner unter:

`/share/google_find_my_secrets.json`

Diese Datei kann dann von anderen Integrationen oder Skripten genutzt werden.

## Hinweise

-   Der Login muss manuell über die Web UI durchgeführt werden.
-   Du musst **mindestens ein Gerät** in deinem "Google Find My Device"-Netzwerk haben, damit der Prozess funktioniert.
-   Wenn das Add-on neu gestartet wird, wird die `secrets.json` neu generiert (falls du den Prozess erneut durchläufst). Sicher dir die Datei am besten, wenn alles geklappt hat.
