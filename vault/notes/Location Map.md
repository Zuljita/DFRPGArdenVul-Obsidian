---
tags:
  - note
  - map
generated_by: scripts/location_graph.py
---

# Location Map

Auto-generated adjacency map of Arden Vul locations, clustered by graph community. Only **confirmed** edges (explicit connection, ≥2 independent signals, or LLM-cited) are drawn. Edge labels show inferred type/direction where known. This is inferred from text and may contain errors.

```mermaid
flowchart LR
  subgraph c_n_Glory_of_Thoth["Glory of Thoth cluster"]
    n_Forum_of_Arden_Vul["Forum of Arden Vul"]
    n_Pyramid_of_Thoth["Pyramid of Thoth"]
    n_Tower_of_Scrutiny["Tower of Scrutiny"]
    n_Howling_Caves["Howling Caves"]
    n_Cliff_Face["Cliff Face"]
    n_Narsileon["Narsileon"]
    n_Newmarket["Newmarket"]
    n_Well_of_Light["Well of Light"]
    n_Sighing_Stair["Sighing Stair"]
    n_Temple_of_Set["Temple of Set"]
    n_Glory_of_Thoth["Glory of Thoth"]
    n_Great_Hall["Great Hall"]
    n_Great_Cavern["Great Cavern"]
    n_Great_Chasm["Great Chasm"]
    n_Upper_Goblintown["Upper Goblintown"]
    n_Goblin_Market["Goblin Market"]
    n_Waterfall["Waterfall"]
  end
  subgraph c_n_Cloister["Cloister cluster"]
    n_Halls_of_the_Troll_Thegn["Halls of the Troll Thegn"]
    n_Troll_Lifts["Troll Lifts"]
  end
  subgraph c_n_Hubs["Hubs cluster"]
    n_Long_Stair["Long Stair"]
    n_Arden_Vul["Arden Vul"]
    n_Gosterwick["Gosterwick"]
    n_Beacon["Beacon"]
    n_Goblin_Forum["Goblin Forum"]
  end
  subgraph c_n_The_Obsidian_Gates["The Obsidian Gates cluster"]
    n_Hall_of_Forty_Pillars["Hall of Forty Pillars"]
    n_The_Obsidian_Gates["The Obsidian Gates"]
  end
  subgraph c_n_Arena["Arena cluster"]
    n_Arena["Arena"]
    n_Inn_of_the_Lost["Inn of the Lost"]
  end
  subgraph c_n_Southern_Necropolis_of_Set["Southern Necropolis of Set cluster"]
    n_Tomb_of_Theskalon["Tomb of Theskalon"]
    n_Southern_Necropolis_of_Set["Southern Necropolis of Set"]
  end
  n_Gosterwick --> n_Arden_Vul
  n_Arden_Vul --> n_Gosterwick
  n_Arden_Vul --> n_Long_Stair
  n_Beacon --> n_Goblin_Forum
  n_Gosterwick --> n_Beacon
  n_Long_Stair --> n_Arden_Vul
  n_Goblin_Forum --> n_Beacon
  n_Long_Stair --> n_Great_Cavern
  n_Beacon --> n_Gosterwick
  n_Beacon --> n_Glory_of_Thoth
  n_Arden_Vul --- n_Pyramid_of_Thoth
  n_Glory_of_Thoth --> n_Well_of_Light
  n_Well_of_Light --> n_Glory_of_Thoth
  n_Beacon --> n_Great_Cavern
  n_Cliff_Face --> n_Long_Stair
  n_Beacon --> n_Cloister
  n_Arena --- n_Beacon
  n_Beacon --> n_Arden_Vul
  n_Great_Cavern --> n_Long_Stair
  n_Glory_of_Thoth --> n_Beacon
  n_Gosterwick --> n_Newmarket
  n_Great_Cavern --> n_Beacon
  n_Beacon --> n_Pyramid_of_Thoth
  n_Arden_Vul --> n_Great_Cavern
  n_Arden_Vul --> n_Newmarket
  n_Arden_Vul --> n_Well_of_Light
  n_Goblin_Market --> n_Beacon
  n_Beacon --> n_Well_of_Light
  n_Upper_Goblintown --> n_Well_of_Light
  n_Arena --- n_Inn_of_the_Lost
  n_Inn_of_the_Lost --> n_Arena
  n_Arden_Vul --> n_Beacon
  n_Newmarket --> n_Gosterwick
  n_Goblin_Forum --> n_Arden_Vul
  n_Glory_of_Thoth --> n_Great_Chasm
  n_Goblin_Market -->|passage| n_Glory_of_Thoth
  n_Cliff_Face --> n_Arden_Vul
  n_Great_Cavern --> n_Goblin_Forum
  n_Beacon --> n_Goblin_Market
  n_Beacon --> n_Goblintown
  n_Well_of_Light --> n_Howling_Caves
  n_Forum_of_Arden_Vul --- n_Pyramid_of_Thoth
  n_Forum_of_Arden_Vul --- n_Tower_of_Scrutiny
  n_Gosterwick --- n_Narsileon
  n_Beacon --- n_Sundered_Span
  n_Glory_of_Thoth --> n_Great_Hall
  n_Goblin_Forum --> n_Upper_Goblintown
  n_Well_of_Light --> n_Goblin_Market
  n_Cloister --> n_Beacon
  n_Glory_of_Thoth -->|passage| n_Goblin_Market
  n_Beacon --- n_Great_Chasm
  n_Hall_of_Forty_Pillars --> n_The_Obsidian_Gates
  n_Howling_Caves --> n_Cliff_Face
  n_Gosterwick --- n_Imperial_Road
  n_Narsileon --- n_Newmarket
  n_Sighing_Stair --- n_Temple_of_Set
  n_Tomb_of_Theskalon --> n_Southern_Necropolis_of_Set
  n_Halls_of_the_Troll_Thegn --- n_Troll_Lifts
  n_Great_Cavern --> n_Great_Chasm
  n_Howling_Caves --> n_Upper_Goblintown
  n_Well_of_Light --> n_Arden_Vul
  n_Long_Stair --> n_Upper_Goblintown
  n_Howling_Caves --> n_Goblin_Market
  n_Gosterwick --> n_Upper_Goblintown
  n_Great_Cavern --> n_Arden_Vul
  n_Obelisk --> n_Arden_Vul
  n_Arden_Vul --> n_Obelisk
  n_Cliff_Face --> n_Great_Cavern
  n_Cliff_Face --> n_Howling_Caves
  n_Well_of_Light --> n_Beacon
  n_Upper_Goblintown --> n_Goblin_Forum
  n_Beacon --> n_Azure_Keep
  n_Tomb_of_Archon_Marius --> n_Beacon
  n_Upper_Goblintown --> n_Arden_Vul
  n_Waterfall --> n_Great_Cavern
  n_Arden_Vul --- n_Burdock_Valley
  n_Goblin_Forum --- n_Goblin_Market
  n_Long_Stair --> n_Cliff_Face
  n_Pyramid_of_Thoth --- n_Well_of_Light
  n_Goblin_Forum --- n_Sighing_Stair
  n_Beacon --- n_Tomb_of_Archon_Marius
  n_Gosterwick --- n_Upper_Market
  n_Great_Chasm --- n_Varumani_Lifts
  n_Gosterwick --- n_Vetucaster
```
