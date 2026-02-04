# Google Find My Tools Add-on

Dieses Add-on ermöglicht die Nutzung der Google Find My Tools in Home Assistant.

## Funktion

Das Add-on startet einen Docker-Container mit einer grafischen Oberfläche (via noVNC), um den interaktiven Login-Prozess bei Google durchzuführen.

## Einrichtung

1.  Starte das Add-on.
2.  Klicke auf **"WEB UI ÖFFNEN"**, um die grafische Oberfläche zu sehen.
3.  Warte kurz, bis der Chrome-Browser startet und die Google-Login-Seite anzeigt.
4.  Melde dich mit deinem Google-Konto an.
5.  Sobald der Login erfolgreich war und das "oauth_token" empfangen wurde, werden die Credentials (Secrets) ausgelesen.

## Secrets / Anmeldedaten

Das Add-on speichert die erfolgreichen Anmeldedaten (`secrets.json`) automatisch in deinem **Share**-Ordner unter:

`/share/google_find_my_secrets.json`

Diese Datei kann dann von anderen Integrationen oder Skripten genutzt werden.

## Hinweise

-   Der Login muss manuell über die Web UI durchgeführt werden.
-   Wenn das Add-on neu gestartet wird, wird die `secrets.json` neu generiert. Falls du die Datei dauerhaft sichern willst, kopiere sie an einen anderen Ort.
