# ZE-SilentSync

ZE-SilentSync ist eine Lösung zur zentralisierten Softwareverteilung und Verwaltung für Windows Netzwerke. Das System ermöglicht Administratoren die effiziente Steuerung von Softwareinstallationen auf Client Computern.

## Hauptfunktionen

*   **Software Repository**
    Zentrales Hochladen und Verwalten von MSI Installationsdateien.

*   **Gezielte Verteilung**
    Zuweisung von Softwarepaketen an spezifische Computer oder Active Directory Organisationseinheiten (OUs).

*   **Zeitgesteuerte Deployments**
    Planung von Softwareverteilungen durch definierte Zeitfenster.

*   **Auditierung**
    Lückenlose Protokollierung aller Administratorzugriffe und Änderungen im System.

*   **Active Directory Integration**
    Nahtlose Anbindung an bestehende Verzeichnisdienste für Authentifizierung und Strukturdaten.

## Komponenten

Die Architektur besteht aus drei Hauptkomponenten:
1.  **Backend:** Python basierte API zur Steuerung und Datenhaltung.
2.  **Frontend:** Webbasierte Benutzeroberfläche für Administratoren.
3.  **Agent:** Leistungsfähiger Rust Client für die Ausführung auf Endgeräten.

## Erste Schritte

Für die Installation und Konfiguration konsultieren Sie bitte die Datei **SETUP.md**. Dort finden Sie detaillierte Anweisungen für Docker und manuelle Deployments sowie Schritte für die Erstkonfiguration.
