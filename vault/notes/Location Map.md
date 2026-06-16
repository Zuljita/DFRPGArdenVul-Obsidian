---
tags:
  - note
  - map
generated_by: scripts/location_graph.py
---

# Location Map

Auto-generated adjacency map of Arden Vul locations, clustered by graph community. Only **confirmed** edges are drawn: a curated typed edge (`config/location_edges_seed.json`), an explicit page connection, or one backed by ≥2 independent signals. Travel/staging artifacts (e.g. teleporting from the Beacon base) are suppressed. Edge labels show the connection type. Inferred from canon + Vallium's route plans; may contain errors.

```mermaid
flowchart LR
  subgraph c_n_Glory_of_Thoth["Glory of Thoth cluster"]
    n_Forum_of_Arden_Vul["Forum of Arden Vul"]
    n_Pyramid_of_Thoth["Pyramid of Thoth"]
    n_Tower_of_Scrutiny["Tower of Scrutiny"]
    n_Goblin_Forum["Goblin Forum"]
    n_Goblin_Market["Goblin Market"]
    n_Great_Hall["Great Hall"]
    n_Great_Pyramid["Great Pyramid"]
    n_Cliff_Face["Cliff Face"]
    n_Howling_Caves["Howling Caves"]
    n_Glory_of_Thoth["Glory of Thoth"]
    n_Upper_Goblintown["Upper Goblintown"]
    n_Goblintown["Goblintown"]
    n_Square_Tower_East_of_Forum["Square Tower (East of Forum)"]
  end
  subgraph c_n_Beacon["Beacon cluster"]
    n_Beacon["Beacon"]
    n_Cloister["Cloister"]
    n_Rudishva_Bastion["Rudishva Bastion"]
    n_Chasm_Floor["Chasm Floor"]
    n_Tomb_of_Archon_Marius["Tomb of Archon Marius"]
  end
  subgraph c_n_Newmarket["Newmarket cluster"]
    n_Narsileon["Narsileon"]
    n_Newmarket["Newmarket"]
  end
  subgraph c_n_Great_Chasm["Great Chasm cluster"]
    n_Halls_of_the_Troll_Thegn["Halls of the Troll Thegn"]
    n_Troll_Lifts["Troll Lifts"]
    n_Great_Chasm["Great Chasm"]
    n_Varumani_Lifts["Varumani Lifts"]
    n_Sundered_Span["Sundered Span"]
  end
  subgraph c_n_Hubs["Hubs cluster"]
    n_Arden_Vul["Arden Vul"]
    n_Long_Stair["Long Stair"]
    n_Gosterwick["Gosterwick"]
    n_Great_Cavern["Great Cavern"]
  end
  subgraph c_n_Temple_of_Set["Temple of Set cluster"]
    n_Sighing_Stair["Sighing Stair"]
    n_Temple_of_Set["Temple of Set"]
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
    n_Southern_Necropolis_of_Set["Southern Necropolis of Set"]
    n_Tomb_of_Theskalon["Tomb of Theskalon"]
  end
  n_Arden_Vul ---|road| n_Gosterwick
  n_Arden_Vul ---|climb| n_Long_Stair
  n_Beacon ---|teleporter| n_Gosterwick
  n_Great_Cavern ---|passage| n_Long_Stair
  n_Glory_of_Thoth ---|passage| n_Well_of_Light
  n_Arden_Vul ---|contains| n_Pyramid_of_Thoth
  n_Beacon ---|teleporter| n_Cloister
  n_Gosterwick ---|road| n_Newmarket
  n_Cliff_Face ---|climb| n_Long_Stair
  n_Arena ---|passage| n_Inn_of_the_Lost
  n_Glory_of_Thoth ---|stairs| n_Pyramid_of_Thoth
  n_Glory_of_Thoth ---|passage| n_Goblin_Market
  n_Arden_Vul ---|climb| n_Cliff_Face
  n_Upper_Goblintown ---|passage| n_Well_of_Light
  n_Gosterwick ---|road| n_Narsileon
  n_Goblin_Forum ---|passage| n_Upper_Goblintown
  n_Goblin_Forum ---|passage| n_Goblin_Market
  n_Howling_Caves ---|passage| n_Well_of_Light
  n_Cliff_Face ---|passage| n_Howling_Caves
  n_Arden_Vul ---|contains| n_Obelisk
  n_Narsileon ---|road| n_Newmarket
  n_Sighing_Stair ---|passage| n_Temple_of_Set
  n_Halls_of_the_Troll_Thegn ---|lift| n_Troll_Lifts
  n_Glory_of_Thoth ---|passage| n_Great_Hall
  n_Great_Cavern ---|passage| n_Great_Chasm
  n_Goblin_Forum ---|passage| n_Temple_of_Set
  n_Great_Cavern ---|passage| n_Waterfall
  n_Forum_of_Arden_Vul ---|passage| n_Pyramid_of_Thoth
  n_Forum_of_Arden_Vul ---|passage| n_Tower_of_Scrutiny
  n_Goblin_Forum ---|stairs| n_Sighing_Stair
  n_Southern_Necropolis_of_Set ---|passage| n_Tomb_of_Theskalon
  n_Cliff_Face ---|passage| n_Great_Cavern
  n_Goblin_Market ---|passage| n_Well_of_Light
  n_Azure_Keep ---|contains| n_Gosterwick
  n_Burdock_Valley ---|contains| n_Gosterwick
  n_Hall_of_Forty_Pillars ---|passage| n_The_Obsidian_Gates
  n_Gosterwick ---|road| n_Imperial_Road
  n_Great_Chasm ---|lift| n_Varumani_Lifts
  n_Goblin_Market ---|passage| n_Howling_Caves
  n_Arden_Vul ---|contains| n_Burdock_Valley
  n_Pyramid_of_Thoth ---|stairs| n_Well_of_Light
  n_Gosterwick ---|contains| n_Totey_Lake
  n_Gosterwick ---|contains| n_Upper_Market
  n_Gosterwick ---|road| n_Vetucaster
  n_Goblin_Forum --- n_Great_Cavern
  n_Great_Chasm ---|lift| n_Troll_Lifts
  n_Arden_Vul ---|contains| n_Forum_of_Arden_Vul
  n_Forum_of_Arden_Vul ---|passage| n_Square_Tower_East_of_Forum
  n_Arena ---|lift| n_Troll_Lifts
  n_Sundered_Span ---|passage| n_Troll_Lifts
  n_Beacon ---|teleporter| n_Rudishva_Bastion
  n_Chasm_Floor ---|passage| n_Rudishva_Bastion
  n_Chasm_Floor ---|passage| n_Great_Chasm
  n_Cloister ---|passage| n_Tomb_of_Archon_Marius
  n_Glory_of_Thoth --- n_Goblintown
  n_Newmarket --- n_Temple_of_Thoth
  n_Glory_of_Thoth --- n_Upper_Goblintown
  n_Howling_Caves --- n_Upper_Goblintown
  n_Long_Stair --- n_Upper_Goblintown
  n_Glory_of_Thoth --- n_Temple_of_Thoth
  n_Great_Hall --- n_Great_Pyramid
  n_Goblin_Forum --- n_Red_Bridge_of_Set
  n_Great_Chasm --- n_Tomb_of_Archon_Marius
```
