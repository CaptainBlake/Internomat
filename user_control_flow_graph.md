# Internomat User Control Flow Graph

```mermaid
flowchart TD
    A[App Launch] --> B[Initialize DB]
    B --> C[Load Settings]
    C --> D[Reconcile Demo Flags from Cache]
    D --> E[Build Main GUI + Tabs]
    E --> F[Default Tab: Team Builder]

    %% Global navigation
    F --> N{User switches tab}
    N --> TB[Team Builder]
    N --> MR[Map Roulette]
    N --> LB[Leaderboard]
    N --> ST[Statistics]
    N --> TR[Stat Tracker]
    N --> SG[Settings]

    %% Team Builder
    subgraph TEAM_BUILDER[Team Builder]
      TB --> TB1[Add Player via Steam URL]
      TB1 --> TB1A[Resolve Steam ID + Fetch Profile]
      TB1A --> TB1B[Upsert Player in DB]
      TB1B --> TB1C[Refresh Player Pool Table]

      TB --> TB2[Update Players]
      TB2 --> TB2A[Get players due by cooldown]
      TB2A --> TB2B[Run player update pipeline async]
      TB2B --> TB2C[MatchZy sync (pipeline pre-step)]
      TB2C --> TB2D[Leetify API / Selenium fallback per player]
      TB2D --> TB2E[Update player rows in DB]
      TB2E --> EV1[Emit Players Updated Event]
      EV1 --> TB2F[Refresh Team Builder player pool]
      EV1 --> LBREF[Invalidate/Refresh Leaderboard]

      TB --> TB3[Add/Remove players to Selected Pool]
      TB3 --> TB4[Generate Teams]
      TB4 --> TB5[Balance algorithm computes CT/T]
      TB5 --> TB6[Render result tables + diff]

      TB --> TB7[Remove Player]
      TB7 --> TB8[Delete from DB]
      TB8 --> TB1C
    end

    %% Map roulette
    subgraph MAP_ROULETTE[Map Roulette]
      MR --> MR1[Spin / Roll action]
      MR1 --> MR2[Map selection service]
      MR2 --> MR3[Render selected map]
    end

    %% Statistics tabs
    subgraph STATISTICS_STACK[Statistics Tabs]
      LB --> LB1[Refresh Stat Overview]
      LB1 --> LB2[Query top kills/deaths/rating/damage]
      LB2 --> LB3[Render 4 leaderboard tables]

      ST --> ST1[Refresh Statistics]
      ST1 --> ST2[Load overview + recent maps]
      ST2 --> ST3[Lazy load cached parsed payloads]
      ST3 --> ST4[Render overview cards + map list]
      ST4 --> ST5[User opens scoreboard/timeline]
      ST5 --> ST6[Render per-map details]

      TR --> TR1[Refresh Stat Tracker]
      TR1 --> TR2[Load tracker overview metrics]
      TR2 --> TR3[Render tracker widgets]
    end

    %% Settings
    subgraph SETTINGS[Settings]
      SG --> SG1[Edit settings controls]
      SG1 --> SG2[Save Settings]
      SG2 --> SG3[Persist to DB settings table]

      SG --> SG4[Import/Export Players]
      SG4 --> SG5[Read/Write players JSON]
      SG5 --> SG6[Refresh Team Builder player pool]

      SG --> SG7[Import/Export Settings]
      SG7 --> SG8[Read/Write settings JSON]
      SG8 --> SG3

      SG --> SG9[Clear Cache]
      SG9 --> SG10[Confirm dialog]
      SG10 --> SG11[Delete demos folder contents]
      SG11 --> SG12[Reset demo flags in DB]
      SG12 --> SG13[Trigger data refresh]

      SG --> SG14[Sync MatchZy]
      SG14 --> SG15[Query MySQL MatchZy tables]
      SG15 --> SG16[Upsert matches/maps/player stats]
      SG16 --> SG17{Import match players enabled?}
      SG17 -->|Yes| SG18[Import/update player pool from match stats]
      SG17 -->|No| SG19[Skip pool import]

      SG --> SG20[Sync Demos]
      SG20 --> SG21[FTP scan/download demos]
      SG21 --> SG22[Matcher parse stage]
      SG22 --> SG23[Parser/cache stage]
      SG23 --> SG24[Reconcile demo flags]
      SG24 --> SG25{Import match players enabled?}
      SG25 -->|Yes| SG26[Import/update players from parsed cache match-map rows]
      SG25 -->|No| SG27[Skip pool import]
      SG26 --> SG28[Refresh Team Builder player pool]
      SG27 --> SG29[Continue]

      SG --> SG30[Unified Sync]
      SG30 --> SG14
      SG30 --> SG20
    end

    %% Cross-tab update propagation
    SG16 --> DU1[Data Updated Event]
    SG23 --> DU1
    SG12 --> DU1
    DU1 --> LB1
    DU1 --> ST1
    DU1 --> TR1

    SG18 --> EV1
    SG26 --> EV1

    %% System responses
    subgraph SYSTEM_RESPONSES[System Responses]
      SR1[Progress dialog updates]
      SR2[Info/Error popup]
      SR3[Logger stream update]
    end

    SG14 --> SR1
    SG20 --> SR1
    SG30 --> SR1
    TB2 --> SR1

    TB1A --> SR2
    SG10 --> SR2
    SG14 --> SR2
    SG20 --> SR2

    A --> SR3
    TB --> SR3
    SG --> SR3
    ST --> SR3

```
