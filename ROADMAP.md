## V2

## Keynotes
- steam auth for fetching data from: https://steamcommunity.com/id/<STEAMPROFILE>/gcpd/730?tab=matchhistoryscrimmage
    - https://pypi.org/project/pysteamauth/
- importing data from demos via awpy or something similiar : https://awpy.readthedocs.io/en/latest/examples/parse_demo.html
- Base rating from leetify (?)  : https://api-public-docs.cs-prod.leetify.com/ 
    - got api key

## pipeline
- Enter new player with steamprofile-link (to get their steam-id)
- Fetch data from leetify API for base-Ranking (no more guessing)

## Host-process
- Login into steam 
- Fetch data from scrimmage page
- update local player.db with match values from https://steamcommunity.com/id/<STEAMPROFILE>/gcpd/730?tab=matchhistoryscrimmage
- eval internal values
- using internal values for balancing teams (old alg. with 500-1000 iterations)
- using leetify value if player is new (need to create a mask to project /estimate leetify values to internal values )
- once player played more than X matches, use internal value



## structure

Player.db (something like that:)
- Player ; steamid ; Leetify values [] ; Intern values []

History.db (used to store fetched match history)
- MatchID ; evals [] ; (opt.) demo.dem
