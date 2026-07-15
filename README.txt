FLOOR LAYOUT PLANNER V5 – FLERE ROM

Nytt:
- Flere rom i samme prosjekt og samme webvisning.
- Hvert rom kan bestå av så mange rektangler som nødvendig.
- L-formede rom støttes fortsatt.
- Hvert rom har egne innstillinger og egen optimalisering.
- Minimum skjøteavstand fylles alltid i web-UI.
- Gammelt én-roms JSON-format konverteres automatisk ved innlasting.
- Egen PNG og CSV per rom i <config>_output-mappen.

Kjør:
    python laminate_planner.py example_project.json --host 0.0.0.0 --no-browser

Eksempel på rom:
    {
      "id": "stue",
      "name": "Stue",
      "origin": {"x": 0, "y": 0},
      "rectangles": [
        {"x": 0, "y": 0, "width": 4600, "height": 3600},
        {"x": 0, "y": 3600, "width": 3000, "height": 2400}
      ],
      "settings": {
        "orientation": "horizontal"
      }
    }

origin plasserer rommet i den samlede etasjevisningen.
Rektanglene bruker lokale koordinater inni rommet.


V6 – ALLE VEGGER OG LOKALE RADBREDder

Radgeneratoren bruker nå hele bordstriper i stedet for én målelinje gjennom
midten av raden.

Dette betyr:
- innhakk som starter midt i en bordbredde oppdages
- L-formede armer vurderes separat
- alle horisontale/vertikale veggskift inngår i radbredde-score
- optimizeren kan flytte hele radnettet for å unngå smale lokale striper
- både første/siste yttervegg og innvendige parallelle vegger vurderes

Smaleste rad i webgrensesnittet er nå det smaleste lokale fragmentet i hele
rommet, ikke maksimumsbredden for en nominell rad.


V7 – TO-TRINNS OPTIMALISERING OG PROFILERING

Fase 1:
- Alle globale kombinasjoner testes uten lokal radoptimalisering.
- Dette er den billige grovsorteringen.

Fase 2:
- Bare de beste kandidatene lokaloptimaliseres.
- Antallet styres med:
      "local_optimize_top_n": 12

Webgrensesnittet viser:
- aktiv fase
- kandidater per sekund
- brukt tid og estimert resttid
- antall prosesser
- grovsøk og finjustering
- akkumulert tid til plan-generering, lokal optimalisering og scoring
- antall lokale radvarianter som er testet

Dette reduserer normalt beregningsmengden kraftig sammenlignet med å
lokaloptimalisere alle globale kandidater.
