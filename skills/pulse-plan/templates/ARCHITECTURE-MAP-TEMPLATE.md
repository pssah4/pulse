<!-- The layers of the architecture map, written by the pulse-plan skill on
     request or by pulse-realign. Replace the example layers below with the
     project's own, top to bottom as a request passes through the system,
     five to ten of them. `## <id>: <name>` opens a layer, the paragraph
     under it says what the layer holds, `- <id>: <name>` names a group in
     it (worth it from about eight features on). Keep the ids short and
     stable: specs and decision records name them as
     `layer: <layer>/<group>`, and pulse check (C11) holds every such line
     to this file. `pulse arch` builds the map from it. Project file:
     _devprocess/architecture-map.md. -->

# Architecture map

## ui: User interface

What people see and operate.

- nav: Navigation
- set: Settings

## app: Application

The use cases: what the system does with a request.

## data: Data

Where state lives and who owns it.

## ops: Operations

Build, release, logging, and monitoring.
