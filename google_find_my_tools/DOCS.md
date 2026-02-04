# Google Find My Tools Add-on

Dieses Add-on ermöglicht die Nutzung der Google Find My Tools in Home Assistant.

## Funktion

Das Add-on startet einen Docker-Container mit einer grafischen Oberfläche (via noVNC). Darin öffnet sich ein Terminal, in dem das Original-Skript der "GoogleFindMyTools" läuft.

## Einrichtung

1.  Starte das Add-on.
2.  Klicke auf **"WEB UI ÖFFNEN"**.
3.  Du siehst nun einen Linux-Desktop. Eventuell ist das Terminal-Fenster ("Google Find My Tools - Interactive Shell") bereits offen. Falls nicht, warte kurz.
4.  **Interaktiver Modus:** Da das Skript nun sichtbar im Terminal läuft, folge den Anweisungen direkt am Bildschirm:
    -   Das Skript wird dich auffordern, `Enter` zu drücken, um den Login zu starten.
    -   Es öffnet sich das Chrome-Fenster für den Login.
    -   Nach dem Login kehrst du zum Terminal zurück.
    -   Wähle dort (per Nummerneingabe) ein Gerät aus.
    -   Führe den zweiten Login durch, falls gefordert.
    -   Sobald alles durchgelaufen ist, kopiert das Skript automatisch die `secrets.json`.

## Secrets / Anmeldedaten

Das Add-on speichert die erfolgreichen Anmeldedaten (`secrets.json`) automatisch in deinem **Share**-Ordner unter:

`/share/google_find_my_secrets.json`

## Hinweise

-   Wenn das Skript abstürzt oder sich schließt, kannst du das Add-on einfach neu starten (Restart).
-   Wenn du fertig bist und die Meldung "Secrets copied successfully!" siehst, kannst du das Fenster schließen oder das Add-on stoppen.
