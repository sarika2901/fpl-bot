import requests

url = "https://fantasy.premierleague.com/api/bootstrap-static/"
response = requests.get(url)
data = response.json()
players = data['elements']

# print(f"Total players found: {len(players)}")

sorted_players = sorted(players, key= lambda p: p["total_points"], reverse=True)

print("\nTop 10 Players by Total Points:\n")

element_types = data['element_types']



for i, player in enumerate(sorted_players[:10], start = 1):
    name = f"{player["first_name"]} {player["second_name"]}"
    points = player["total_points"]
    element_type_id = player["element_type"]
    if element_type_id == 3:
        element_type_name = "Midfielder"
        print(f"{i}. {name} - {points} points - {element_type_name}")

   




