# Floor Layout Planner

## Features

✔ Multiple rooms

✔ L-shaped rooms

✔ Live optimization

✔ PNG export

✔ CSV export

✔ Multi-process optimizer

---

## Install

pip install -r requirements.txt

---

## Run

python laminate_planner.py example_project.json

## Benchmark / Profile

Benchmark plan generation for all rooms in a project:

python tools/benchmark_engine.py stue_project.json --mode plan --repeat 20

Benchmark coarse candidate evaluation for one room:

python tools/benchmark_engine.py stue_project.json --room hallway --mode coarse --sample-size 20

Run a cProfile capture for one representative refine evaluation:

python tools/benchmark_engine.py stue_project.json --room hallway --mode refine --profile --profile-output refine.prof

Compare two configs and print timing deltas for the same room ids:

python tools/benchmark_engine.py stue_project.json --compare-config stue_project_optimized.json --room gang --mode plan --repeat 20
