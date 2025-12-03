# Projektstatus – SVO2 Handler & Viewer/Annotator

Stand: aktuelle Session (nach Implementierung von Export, Depth, Viewer)

## Kernfunktionen
- **SVO2 Handler GUI** (`svo_handler.gui_app`):
  - Frame-Extraktion (Left/Right), Downsample per FPS-Slider (keep-every-N).
  - Depth-Export optional (32-bit `.npy`), Depth-Mode wählbar (Default NEURAL_PLUS).
  - Export nach `DRONE_DATA` (Linke/rechte Auswahl), Warnungen bei FAT32/Low space.
  - Fortschrittsbalken mit bekannter Total Frame Count; Manifest mit Optionen/Depth-Mode.
- **Viewer/Annotator** (`svo_handler.viewer_app`):
  - Laden von JPG+NPY Paaren, Navigation ±1/±5.
  - Depth-Visualisierung mit Min/Max-Slider (1–10 m, 10–40 m), ungültige Werte schwarz.
  - AOI: Rechteck zeichnen, bewegen, resizen; Stats (Mean/Min/Max/Std) im UI.
  - Front/Back-Klasse (YOLO class_id 0/1), Label-Export `.txt` neben JPG und Kopie in Bucket.
  - Bucket-Kopie + CSV-Log: Ordnerstruktur `<direction>/<position>/<dist>` unter Training-Root (Default `/media/angelo/DRONE_DATA1/YoloTrainingV1`), Distanzbuckets near/mid/far.
  - Training-Root persistent (`~/.svo_viewer_config`), last processed Bild (`~/.svo_viewer_state`) -> beim Start zum nächsten Bild springen.
  - BBox wird angezeigt, Koordinaten und Stats im UI; BBox bleibt bei Zoom/Resize erhalten. Clear-Button.
  - RGB- und Depth-Zoom per Mauswheel (Cursor-zentriert), Zoom-Focus für Crop.

## Gelöste Probleme / Learnings
- **ZED API Umstellungen**: `set_from_svo_file`, `get_camera_information`, `retrieve_image` (snake_case) → angepasst.
  - Depth-Mode Auswahl, Depth-Export klappt mit pyzed 5.0.
- **Depth Masking**: Ungültige Werte (NaN/<=0/out-of-range) schwarz; nicht in Stats.
  - AOI-Stats nur innerhalb Min/Max.
- **YOLO-Labels**: Schreiben funktioniert; Label in Bucket kopiert; CSV enthält BBox und Stats.
- **Navigation**: Nach Umbenennen/Annotieren wird automatisch das nächste Bild geladen; last_processed wird persistiert.
- **Bucket-Struktur**: Automatisches Anlegen nur, wenn keine vorhandenen Buckets mit Daten → keine Überschreibung.
- **BBox-Schrumpfen**: gefixt durch getrennte Anzeige-Updates und `show_rect`-Flag.
- **Zoom**: RGB/Depth Zoom zentriert auf Cursor; BBox bleibt erhalten.
- **Depth-Export**: `.npy` gleichnamig zum JPG; Manifest enthält `export_depth` und `depth_mode`.

## Offene Punkte / Bekannte Probleme
- **Scaling / Resize**: Beim Vergrößern des Fensters wachsen die Images immer noch iterativ; derzeit wird nach Resize ein einmaliger Re-Render per Timer (50 ms) gestartet, aber es kommt zu sichtbarem „Anwachsen“, wenn die GUI größer gezogen wird. Ziel: sofortige Endgröße ohne mehrfaches Rendern.
- **RGB-Render**: Bei großem Resize wird eventuell nicht die finale Breite/Höhe sofort erreicht; evtl. doppelte Render-Pipeline (zwei Passes) oder fixierte Zielgröße mit `devicePixelRatio` berücksichtigen.
- **BBox-Overlay**: Bleibt erhalten, aber weitere Tests nötig beim extremen Zoom/Resize.
- **Performance**: Eventuell Rendering-Throttling noch tunen, um Flackern/Iterationen zu vermeiden (z.B. festen Target-Snapshot nach Resize-Ende).
- **Fehlerfälle**:
  - Kein explizites Handling, falls Label-Write/Pillow scheitert (es gibt Statusmeldung, aber kein Retry).
  - Kein Undo für Umbenennen/Kopieren.

## Nächste Schritte (technische TODOs)
- **Scaling-Fix**: Überarbeiten der Render-Strategie
  - Ein einziger Render nach Resize-Ende (z.B. mittels Resize-Timeout + Render, ohne Zwischenschritte).
  - Sicherstellen, dass `contentsRect` und Label-Größe konsistent genutzt werden; ggf. Pixmap an `devicePixelRatio` anpassen.
- **BBox-Funktionen**:
  - Optional: Undo/History für AOI/Umbenennen.
  - Option, BBox-Edit (Handles) noch präziser oder Snap zu Min/Max.
- **Robustheit**:
  - Bessere Fehleranzeigen im UI (z.B. fehlende Schreibrechte beim Label-Kopie).
  - Option für konfigurierbaren Training-Root im GUI speichern/anzeigen (bereits vorhanden, ggf. Validierungs-Feedback verbessern).
- **Daten-Export**:
  - Optionale globale CSV/JSON für alle Annotationen (derzeit pro Root `annotations.csv`).
  - Konfig für Label-Klassen-Mapping (aktuell hart 0=front, 1=back).
- **Feature-Ideen**:
  - Snapshot/Backup vor Umbenennen/Kopieren.
  - Quick-jump zu unannotierten Bildern.
  - Anzeigen der Label-Datei/Preview im UI.

## Pfad-Übersicht
- `src/svo_handler/gui_app.py`: SVO2 Frame/Depth Exporter.
- `src/svo_handler/extraction.py`: Worker für Frames/Depth + Manifest/Progress.
- `src/svo_handler/viewer_app.py`: Viewer/Annotator (RGB+Depth, AOI, YOLO-Export, Bucket-Kopie).
- `src/svo_handler/training_export.py`: Bucket-Logik, CSV-Append.
- `docs/fieldtest-learnings.md`: ZED/Field-Test Lessons (LOSSLESS, FAT32 etc.).
- `docs/frame-export.md`: Export-Plan/GUI-Status.
- `docs/viewer-annotator-plan.md`: Ziele für Viewer/Annotator.
- `docs/status.md`: Diese Übersicht.
